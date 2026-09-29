"""In-memory catalogue with hybrid scoring: 50% note/accord match, 30% semantic match, 20% quality signal.

The LLM never ranks; it only explains. Everything here is deterministic so the guided quiz works with no model.
"""
from __future__ import annotations

import difflib
import math
import re
import threading

import numpy as np

from app.config import settings
from app.data import taxonomy as tx
from app.data.db import Database
from app.schemas import TasteProfile

_WORD = re.compile(r"[a-z0-9؀-ۿ]+")

# Kaggle rows store name/brand as lowercase hyphen-slugs ("le-male-le-parfum"); seed rows and Arabic text are
# already proper strings (mixed case or contain spaces) and must be left untouched.
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def humanize_slug(value: str) -> str:
    """"le-male-le-parfum" -> "Le Male Le Parfum"; "300-km-h-supersonic" -> "300 Km H Supersonic".

    Only strings that look like a slug (lowercase, hyphen-separated, no spaces) are transformed; anything
    else (already-proper names, Arabic text) is returned unchanged.
    """
    if not value or not _SLUG_RE.match(value):
        return value
    return " ".join(part.capitalize() for part in value.split("-"))


def _name_prefix(name: str, n: int = 3) -> str:
    """First `n` words of a perfume name, lowercased: used to spot near-duplicate line extensions
    ("300 Km H Quantum" / "300 Km H Supersonic" / "300 Km H Surfer")."""
    return " ".join(_WORD.findall((name or "").lower())[:n])


# Generic wording that marks the end of a product LINE name and the start of a concentration/edition suffix:
# "Sauvage Eau De Toilette", "Sauvage Elixir" and "Sauvage" are all the same line.
_LINE_STOP_WORDS = {"eau", "edp", "edt", "edc", "parfum", "parfums", "perfume", "cologne", "elixir",
                    "extrait", "intense", "absolu", "absolue", "essence", "spray", "pour", "homme", "femme",
                    "him", "her", "men", "women", "for", "sport", "fraiche", "fraîche", "limited", "edition",
                    "concentree", "concentrée"}


def line_key(name: str) -> str:
    """The product-line name inside a perfume name: the leading words before any concentration/edition wording.

    "Sauvage" -> "sauvage"; "Sauvage Eau De Toilette" -> "sauvage"; "Guido Maria Kretschmer For Him" ->
    "guido maria kretschmer". Used to spot flankers of an anchor perfume (same brand, same line) so
    "something like Sauvage" never comes back with three Sauvages.
    """
    words = _WORD.findall((name or "").lower())
    head = []
    for w in words:
        if w in _LINE_STOP_WORDS:
            break
        head.append(w)
    return " ".join(head) if head else _name_prefix(name, 2)


_MIN_LINE_CHARS = 3  # a one-or-two-letter line name ("Y") is too generic to prefix-match on


def _same_line(a: list[str], b: list[str]) -> bool:
    """True when two line names are the same line: equal, or one a leading-word prefix of the other
    ("club de nuit" vs "club de nuit milestone"). Guards against very short, generic line names."""
    if not a or not b:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(" ".join(short)) < _MIN_LINE_CHARS:
        return a == b
    return long_[:len(short)] == short


def normalize_brand(value: str | None) -> str:
    """Case/format-insensitive brand key: "jean-paul-gaultier", "Jean Paul Gaultier" and "jean  paul-gaultier"
    all normalise to "jean paul gaultier", so a BRAND_FILTER written as a slug still matches humanized rows."""
    if not value:
        return ""
    return re.sub(r"[-\s]+", " ", value.strip().lower()).strip()


# Filler words ignored when checking whether a query "contains" a catalogue name (see find_by_name).
_NAME_FILLER = {"by", "perfume", "the", "eau", "de", "parfum", "edp", "edt", "for"}

# Extra mood/occasion vocabulary so free text nudges the content vector even without an LLM.
MOOD_NOTE_HINTS: dict[str, list[str]] = {
    "romantic": ["rose", "jasmine", "vanilla", "peony"],
    "energetic": ["bergamot", "lemon", "grapefruit", "mint", "orange"],
    "cozy": ["vanilla", "tonka bean", "amber", "benzoin", "sandalwood"],
    "bold": ["oud", "leather", "incense", "pepper", "tobacco"],
    "elegant": ["iris", "sandalwood", "rose", "musk", "cedar"],
    "playful": ["berries", "apple", "sugar", "cherry", "tropical fruits"],
    "calm": ["clean notes", "sea notes", "tea", "green notes", "musk"],
    "mysterious": ["incense", "oud", "labdanum", "myrrh", "smoke"],
}


class _CatalogueState:
    """Everything Catalogue.reload() builds, as one immutable snapshot.

    A reload builds a brand new instance from scratch and Catalogue swaps a single reference to it
    (`self._state = new_state`), which is atomic under the GIL. Readers therefore always see either the
    fully-old or the fully-new snapshot, never a mix of old and new arrays/indexes mid-reload.
    """
    __slots__ = ("perfumes", "ids", "notes", "accord_names", "dim_index", "dim", "matrix", "row_of", "unit",
                 "quality", "bags", "idf", "embeddings", "_name_index", "_flanker_cache")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))
        if self._flanker_cache is None:
            self._flanker_cache = {}


class Catalogue:
    def __init__(self, db: Database, embedder=None):
        self.db = db
        self.embedder = embedder  # optional callable(list[str]) -> np.ndarray (n, d), used for semantic scoring
        self._lock = threading.Lock()
        self._state: _CatalogueState | None = None
        self.reload()

    def __getattr__(self, name):
        # Only hit when normal lookup fails, i.e. for the fields that live on the current _CatalogueState
        # (self.db/self.embedder/self._lock/self._state are real instance attributes and never land here).
        if name in _CatalogueState.__slots__:
            state = self.__dict__.get("_state")
            if state is not None:
                return getattr(state, name)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    # ------------------------------------------------------------------ build
    def reload(self) -> None:
        """Rebuilds the catalogue from the database and publishes it in one atomic step."""
        state = self._build_state()
        with self._lock:
            self._state = state

    def _build_state(self) -> _CatalogueState:
        perfumes_list = self.db.all_perfumes()
        for p in perfumes_list:
            raw_name, raw_brand = p["name"], p["brand_name"]
            p["name"] = humanize_slug(raw_name)
            p["brand_name"] = humanize_slug(raw_brand)
            # Some rows repeat the brand at the start of the name slug ("Victoria S Secret Victoria S Secret
            # Beach Angel"): strip one leading occurrence so the display name isn't doubled.
            brand_low, name_low = p["brand_name"].lower(), p["name"].lower()
            if brand_low and name_low.startswith(brand_low + " "):
                stripped = p["name"][len(p["brand_name"]) + 1:].strip()
                if stripped and stripped.lower() != brand_low:
                    p["name"] = stripped
            # Generated descriptions open with "<name> by <brand>": show the readable forms there too.
            for key in ("description", "description_ar"):
                text = p.get(key) or ""
                if raw_name != p["name"] and text.startswith(raw_name + " "):
                    text = p["name"] + text[len(raw_name):]
                if raw_brand != p["brand_name"]:
                    text = text.replace(f" {raw_brand} ", f" {p['brand_name']} ", 1)
                p[key] = text
        perfumes: dict[str, dict] = {p["perfume_id"]: p for p in perfumes_list}
        ids: list[str] = [p["perfume_id"] for p in perfumes_list]
        notes = list(tx.load()["notes"].keys())
        accord_names = sorted({a for p in perfumes_list for a in p["accords"]})
        dim_index = {n: i for i, n in enumerate(notes)}
        base = len(notes)
        for i, a in enumerate(accord_names):
            dim_index["accord:" + a] = base + i
        fam_base = len(dim_index)
        for i, f in enumerate(tx.families()):
            dim_index["family:" + f] = fam_base + i
        dim = len(dim_index)
        matrix = np.zeros((len(perfumes_list), dim), dtype=np.float32)
        row_of: dict[str, int] = {}
        layer_w = {"top": 0.8, "heart": 1.0, "base": 1.2}
        for r, p in enumerate(perfumes_list):
            row_of[p["perfume_id"]] = r
            v = matrix[r]
            for n in p["notes"]:
                v[dim_index[n["note"]]] += layer_w.get(n["layer"], 1.0)
            for a, s in p["accords"].items():
                v[dim_index["accord:" + a]] += 1.5 * s / 100.0
            v[dim_index["family:" + p["family"]]] += 1.0
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        unit = matrix / norms
        # Quality: Bayesian-ish rating shrunk toward 3.8 by vote count, scaled 0..1.
        quality = np.zeros(len(perfumes_list), dtype=np.float32)
        for r, p in enumerate(perfumes_list):
            rating = p.get("rating") or 3.8
            votes = p.get("rating_count") or 0
            shrunk = (rating * votes + 3.8 * 200) / (votes + 200)
            pop = math.log1p(votes) / math.log1p(50000)
            quality[r] = max(0.0, min(1.0, 0.7 * (shrunk - 2.5) / 2.5 + 0.3 * pop))
        # Keyword bags for the non-embedding semantic fallback.
        bags: list[set[str]] = []
        df: dict[str, int] = {}
        for p in perfumes_list:
            words = set(_WORD.findall((p["description"] + " " + p["description_ar"] + " " + p["name"] + " " + p["brand_name"]).lower()))
            words |= {a for a in p["accords"]} | {"family:" + p["family"]}
            words |= set(p["moods"]) | set(p["seasons"]) | set(p["occasions"])
            words |= {n["note"] for n in p["notes"]}
            bags.append(words)
            for w in words:
                df[w] = df.get(w, 0) + 1
        n_docs = max(1, len(perfumes_list))
        idf = {w: math.log((n_docs + 1) / (c + 0.5)) for w, c in df.items()}
        embeddings = self._compute_embeddings(ids, perfumes)
        name_index = {(p["brand_name"] + " " + p["name"]).lower(): pid for pid, p in perfumes.items()}
        name_index.update({p["name"].lower(): pid for pid, p in perfumes.items() if p["name"].lower() not in name_index})
        return _CatalogueState(perfumes=perfumes, ids=ids, notes=notes, accord_names=accord_names,
                               dim_index=dim_index, dim=dim, matrix=matrix, row_of=row_of, unit=unit,
                               quality=quality, bags=bags, idf=idf, embeddings=embeddings, _name_index=name_index)

    def _compute_embeddings(self, ids: list[str], perfumes: dict[str, dict]) -> np.ndarray | None:
        if self.embedder is None:
            return None
        stored = self.db.load_embeddings()
        if len(stored) < len(ids):
            missing = [pid for pid in ids if pid not in stored]
            texts = [perfumes[pid]["description"] + " " + ", ".join(perfumes[pid]["accords"]) for pid in missing]
            try:
                vecs = self.embedder(texts)
            except Exception:
                return None
            with self.db.tx() as c:
                for pid, v in zip(missing, vecs):
                    arr = np.asarray(v, dtype=np.float32)
                    c.execute("INSERT OR REPLACE INTO perfume_embedding(perfume_id, model, vector) VALUES (?,?,?)",
                              (pid, settings.azure_openai_embed_deployment, arr.tobytes()))
                    stored[pid] = arr.tobytes()
        mat = np.stack([np.frombuffer(stored[pid], dtype=np.float32) for pid in ids]) if ids else np.zeros((0, 1))
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms

    # ------------------------------------------------------------------ lookup
    def get(self, perfume_id: str) -> dict | None:
        return self.perfumes.get(perfume_id)

    def find_by_name(self, name: str) -> dict | None:
        # Names are stored humanized (spaces, no hyphens); accept a query typed either way ("le male le
        # parfum" or "le-male-le-parfum"), case-insensitive.
        q = re.sub(r"[-\s]+", " ", (name or "").lower().strip())
        if not q:
            return None
        if q in self._name_index:
            return self.perfumes[self._name_index[q]]
        # Contained name (e.g. "baccarat rouge 540 by mfk" or "aventus creed"): only count it when the
        # catalogue name appears on whole-word boundaries AND covers most of the query's meaningful words
        # (ignoring filler words and the candidate's own brand). Without this, an invented longer name like
        # "Moonlight Oud 99 by Atelier Noor" would wrongly match an unrelated real perfume "Moonlight" just
        # because its name is a short substring of the query.
        q_words = q.split()
        best, best_score = None, (0.0, 0)
        for pid in set(self._name_index.values()):
            p = self.perfumes[pid]
            nm = p["name"].lower()
            if len(nm) < 4 or not re.search(rf"(?<!\w){re.escape(nm)}(?!\w)", q):
                continue
            brand_words = set(p["brand_name"].lower().split())
            meaningful = [w for w in q_words if w not in _NAME_FILLER and w not in brand_words]
            if not meaningful:
                continue
            nm_words = set(nm.split())
            coverage = sum(1 for w in meaningful if w in nm_words) / len(meaningful)
            if coverage < 0.6:
                continue
            score = (coverage, len(nm))
            if score > best_score:
                best, best_score = pid, score
        if best:
            return self.perfumes[best]
        matches = difflib.get_close_matches(q, list(self._name_index.keys()), n=1, cutoff=0.82)
        if matches:
            return self.perfumes[self._name_index[matches[0]]]
        return None

    # ------------------------------------------------------------------ vectors
    def _profile_vector(self, profile: TasteProfile) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for n in profile.liked_notes:
            m = tx.normalise_note(n)
            if m:
                v[self.dim_index[m]] += 2.0
                v[self.dim_index["family:" + tx.note_family(m)]] += 0.3
        for f in profile.families:
            if "family:" + f in self.dim_index:
                v[self.dim_index["family:" + f]] += 2.0
        for m in profile.moods:
            for n in MOOD_NOTE_HINTS.get(m, []):
                v[self.dim_index[n]] += 0.5
        if profile.anchor_perfume_id and profile.anchor_perfume_id in self.row_of:
            v += 3.0 * self.unit[self.row_of[profile.anchor_perfume_id]]
        for f in profile.avoid_families:
            if "family:" + f in self.dim_index:
                v[self.dim_index["family:" + f]] -= 1.5
        return v

    def _content_scores(self, profile: TasteProfile) -> np.ndarray:
        v = self._profile_vector(profile)
        n = np.linalg.norm(v)
        if n == 0:
            return np.full(len(self.ids), 0.5, dtype=np.float32)
        sims = self.unit @ (v / n)
        return np.clip((sims + 0.15) / 0.9, 0, 1).astype(np.float32)

    def _semantic_scores(self, text: str | None, profile: TasteProfile) -> np.ndarray:
        query = " ".join(filter(None, [text or "", profile.free_text])).strip()
        if not query:
            return np.full(len(self.ids), 0.5, dtype=np.float32)
        if self.embeddings is not None and self.embedder is not None:
            try:
                q = np.asarray(self.embedder([query])[0], dtype=np.float32)
                q = q / (np.linalg.norm(q) or 1.0)
                sims = self.embeddings @ q
                return np.clip((sims - 0.1) / 0.5, 0, 1).astype(np.float32)
            except Exception:
                pass
        words = set(_WORD.findall(query.lower()))
        # Expand words through the taxonomy so "citrusy" hits the fresh family and "sweet" hits gourmand.
        for fam, syns in tx.load()["family_synonyms"].items():
            if words & set(syns):
                words.add("family:" + fam)
        for w in list(words):
            m = tx.normalise_note(w)
            if m:
                words.add(m)
        words = {w for w in words if w in self.idf}
        if not words:
            return np.full(len(self.ids), 0.5, dtype=np.float32)
        denom = sum(self.idf[w] for w in words) or 1.0
        out = np.zeros(len(self.ids), dtype=np.float32)
        for r, bag in enumerate(self.bags):
            out[r] = sum(self.idf[w] for w in words & bag) / denom
        # Rescale so a query matching a third of its weighted words already reads as a good match.
        return np.clip(out * 2.5, 0, 1)

    # ------------------------------------------------------------------ filters
    def anchor_flanker_ids(self, anchor_id: str | None) -> set[str]:
        """The anchor perfume itself plus its flankers: same brand AND same product line ("Sauvage Eau de
        Toilette" for anchor "Sauvage"). Recommending those back is the "you asked for something like X, here
        is X" bug, so every ranking path filters them out via _passes(). Cached per catalogue snapshot."""
        state = self.__dict__.get("_state")
        if not anchor_id or state is None:
            return set()
        cached = state._flanker_cache.get(anchor_id)
        if cached is not None:
            return cached
        anchor = state.perfumes.get(anchor_id)
        if not anchor:
            state._flanker_cache[anchor_id] = set()
            return set()
        brand, line = normalize_brand(anchor["brand_name"]), line_key(anchor["name"])
        out = {anchor_id}
        if line:
            words = line.split()
            for pid, p in state.perfumes.items():
                if normalize_brand(p["brand_name"]) != brand:
                    continue
                if _same_line(words, line_key(p["name"]).split()):
                    out.add(pid)
        state._flanker_cache[anchor_id] = out
        return out

    def passes(self, p: dict, profile: TasteProfile) -> bool:
        """Public hard-filter check (disliked notes, avoided families, budget, brand, gender, completeness)."""
        return self._passes(p, profile)

    def _passes(self, p: dict, profile: TasteProfile) -> bool:
        if not p["recommendable"]:
            return False
        if profile.anchor_perfume_id and p["perfume_id"] in self.anchor_flanker_ids(profile.anchor_perfume_id):
            return False  # never recommend the anchor itself, nor a flanker of the same line
        brand = normalize_brand(profile.brand or settings.brand_filter)
        if brand and normalize_brand(p["brand_name"]) != brand:
            return False
        if profile.budget_aed is not None and p["price_aed"] is not None and p["price_aed"] > profile.budget_aed:
            return False
        if profile.disliked_notes:
            notes = {n["note"] for n in p["notes"]}
            for d in profile.disliked_notes:
                m = tx.normalise_note(d)
                if m and m in notes:
                    return False
                if m is None and d.lower() in {f for f in tx.families()} and p["family"] == d.lower():
                    return False
        if profile.avoid_families and p["family"] in profile.avoid_families:
            return False
        if profile.strength is not None and abs(p["strength"] - profile.strength) > 2:
            return False
        if profile.gender and p.get("gender"):
            g, pg = profile.gender.lower(), p["gender"].lower()
            if g in {"men", "women"} and pg not in {g, "unisex"}:
                return False
        return True

    def _strength_fit(self, p: dict, profile: TasteProfile) -> float:
        if profile.strength is None:
            return 1.0
        return max(0.0, 1.0 - 0.25 * abs(p["strength"] - profile.strength))

    def _season_fit(self, p: dict, profile: TasteProfile) -> float:
        if not profile.seasons and not profile.occasions:
            return 1.0
        hits, total = 0, 0
        if profile.seasons:
            total += 1
            hits += 1 if set(profile.seasons) & set(p["seasons"]) else 0
        if profile.occasions:
            total += 1
            hits += 1 if set(profile.occasions) & set(p["occasions"]) else 0
        return 0.6 + 0.4 * hits / total

    # ------------------------------------------------------------------ search
    def search(self, profile: TasteProfile, text: str | None = None, limit: int = 10, exclude_ids=()) -> list[dict]:
        if not self.ids:
            return []
        content = self._content_scores(profile)
        semantic = self._semantic_scores(text, profile)
        total = 0.5 * content + 0.3 * semantic + 0.2 * self.quality
        results = []
        excluded = set(exclude_ids)
        if profile.anchor_perfume_id:
            excluded.add(profile.anchor_perfume_id)  # "like X" never returns X itself
        for r, pid in enumerate(self.ids):
            if pid in excluded:
                continue
            p = self.perfumes[pid]
            if not self._passes(p, profile):
                continue
            fit = self._strength_fit(p, profile) * self._season_fit(p, profile)
            score = float(total[r]) * (0.7 + 0.3 * fit)
            results.append({"perfume": p, "score": round(score, 4),
                            "components": {"content": round(float(content[r]), 3), "semantic": round(float(semantic[r]), 3),
                                           "quality": round(float(self.quality[r]), 3), "fit": round(fit, 3)}})
        results.sort(key=lambda x: -x["score"])
        return results[:limit]

    def similar(self, perfume_id: str, limit: int = 5, max_price: float | None = None, profile: TasteProfile | None = None) -> list[dict]:
        if perfume_id not in self.row_of:
            return []
        base = TasteProfile(anchor_perfume_id=perfume_id)
        if profile:
            base = profile.merge(base)
        if max_price is not None:
            base.budget_aed = max_price
        anchor_row = self.row_of[perfume_id]
        sims = self.unit @ self.unit[anchor_row]
        out = []
        for r in np.argsort(-sims):
            pid = self.ids[int(r)]
            if pid == perfume_id:
                continue
            p = self.perfumes[pid]
            if not self._passes(p, base):
                continue
            out.append({"perfume": p, "score": round(float(0.8 * sims[r] + 0.2 * self.quality[r]), 4),
                        "components": {"similarity": round(float(sims[r]), 3), "quality": round(float(self.quality[r]), 3)}})
            if len(out) >= limit:
                break
        return out

    # ------------------------------------------------------------------ layering
    def layering_partner(self, perfume_id: str, profile: TasteProfile | None = None) -> dict | None:
        p = self.perfumes.get(perfume_id)
        if not p:
            return None
        rules = tx.load()["layering_rules"]
        partners_fams = [(r["b"], r) for r in rules if r["a"] == p["family"]] + [(r["a"], r) for r in rules if r["b"] == p["family"]]
        if not partners_fams:
            return None
        clashes = {frozenset(pair) for pair in tx.load()["clashing_notes"]}
        my_notes = {n["note"] for n in p["notes"]}
        prof = profile or TasteProfile()
        best, best_score, best_rule = None, -1.0, None
        for fam, rule in partners_fams:
            for pid in self.ids:
                if pid == perfume_id:
                    continue
                q = self.perfumes[pid]
                if q["family"] != fam or not self._passes(q, prof):
                    continue
                q_notes = {n["note"] for n in q["notes"]}
                if any(frozenset((a, b)) in clashes for a in my_notes for b in q_notes):
                    continue
                shared = len(my_notes & q_notes)
                if shared > 2:  # too similar to add anything
                    continue
                if abs(q["strength"] - p["strength"]) > 2:
                    continue
                score = 0.5 * shared + float(self.quality[self.row_of[pid]]) - 0.1 * abs(q["strength"] - p["strength"])
                if score > best_score:
                    best, best_score, best_rule = q, score, rule
        if not best:
            return None
        return {"perfume": best, "reason_en": best_rule["reason_en"], "reason_ar": best_rule["reason_ar"]}

    # ------------------------------------------------------------------ recommend
    def recommend(self, profile: TasteProfile, text: str | None = None, k: int = 3, exclude_ids=()) -> dict:
        ranked = self.search(profile, text, limit=max(30, k * 10), exclude_ids=exclude_ids)
        picks: list[dict] = []
        single_family = len(profile.families) == 1 and not profile.liked_notes
        seen_brands: set[str] = set()
        seen_prefixes: set[str] = set()
        for cand in ranked:
            p = cand["perfume"]
            fam = p["family"]
            # Diversify: the top 3 must not all share a family unless one family was asked for.
            if not single_family and len(picks) == k - 1 and picks and all(x["perfume"]["family"] == fam for x in picks):
                continue
            if any(x["perfume"]["brand_name"] == p["brand_name"] and x["perfume"]["name"] == p["name"] for x in picks):
                continue
            # Diversify: at most one perfume per brand, and skip near-duplicate line extensions (same
            # leading words, e.g. "300 Km H Quantum" / "300 Km H Supersonic"). Relaxed below when there
            # are too few candidates left to fill k picks (e.g. a brand filter narrows the catalogue).
            brand = normalize_brand(p["brand_name"])
            prefix = _name_prefix(p["name"])
            if brand in seen_brands or (prefix and prefix in seen_prefixes):
                continue
            picks.append(cand)
            seen_brands.add(brand)
            if prefix:
                seen_prefixes.add(prefix)
            if len(picks) == k:
                break
        if len(picks) < k:
            # Too few candidates to keep brand/name diversity: relax it and fill with the next best
            # matches, still skipping exact brand+name duplicates already picked.
            for cand in ranked:
                if cand in picks:
                    continue
                p = cand["perfume"]
                if any(x["perfume"]["brand_name"] == p["brand_name"] and x["perfume"]["name"] == p["name"] for x in picks):
                    continue
                picks.append(cand)
                if len(picks) == k:
                    break
        layering = self.layering_partner(picks[0]["perfume"]["perfume_id"], profile) if picks else None
        return {"picks": picks, "layering": layering}


def diversify(ranked: list[dict], limit: int, max_per_brand: int = 2) -> list[dict]:
    """Caps a ranked candidate list (as returned by Catalogue.search/similar) at `max_per_brand` items per
    brand and skips near-duplicate line-extension names (same leading words), keeping rank order -- the same
    idea as recommend()'s top-3 diversification, but for the larger candidate lists shown to the LLM agent's
    tools (fix: the model was picking from tool results that were themselves undiversified, so it sometimes
    saw -- and picked -- several flankers of one brand). Falls back to filling any remaining slots from
    whatever is left (still skipping exact brand+name duplicates) when there are too few diverse candidates.
    """
    picks: list[dict] = []
    brand_counts: dict[str, int] = {}
    seen_prefixes: set[str] = set()
    chosen_ids: set[int] = set()
    for cand in ranked:
        p = cand["perfume"]
        brand = normalize_brand(p["brand_name"])
        prefix = _name_prefix(p["name"])
        if brand_counts.get(brand, 0) >= max_per_brand:
            continue
        if prefix and prefix in seen_prefixes:
            continue
        picks.append(cand)
        chosen_ids.add(id(cand))
        brand_counts[brand] = brand_counts.get(brand, 0) + 1
        if prefix:
            seen_prefixes.add(prefix)
        if len(picks) >= limit:
            return picks
    if len(picks) < limit:
        for cand in ranked:
            if id(cand) in chosen_ids:
                continue
            p = cand["perfume"]
            if any(x["perfume"]["brand_name"] == p["brand_name"] and x["perfume"]["name"] == p["name"] for x in picks):
                continue
            picks.append(cand)
            if len(picks) >= limit:
                break
    return picks


_catalogue: Catalogue | None = None
_cat_lock = threading.Lock()


def get_catalogue(db: Database | None = None, embedder=None) -> Catalogue:
    global _catalogue
    with _cat_lock:
        if _catalogue is None:
            _catalogue = Catalogue(db or Database(), embedder)
        return _catalogue


def set_catalogue(cat: Catalogue | None) -> None:
    global _catalogue
    with _cat_lock:
        _catalogue = cat
