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


class Catalogue:
    def __init__(self, db: Database, embedder=None):
        self.db = db
        self.embedder = embedder  # optional callable(list[str]) -> np.ndarray (n, d), used for semantic scoring
        self._lock = threading.Lock()
        self.reload()

    # ------------------------------------------------------------------ build
    def reload(self) -> None:
        with self._lock:
            perfumes = self.db.all_perfumes()
            self.perfumes: dict[str, dict] = {p["perfume_id"]: p for p in perfumes}
            self.ids: list[str] = [p["perfume_id"] for p in perfumes]
            self.notes = list(tx.load()["notes"].keys())
            self.accord_names = sorted({a for p in perfumes for a in p["accords"]})
            self.dim_index = {n: i for i, n in enumerate(self.notes)}
            base = len(self.notes)
            for i, a in enumerate(self.accord_names):
                self.dim_index["accord:" + a] = base + i
            fam_base = len(self.dim_index)
            for i, f in enumerate(tx.families()):
                self.dim_index["family:" + f] = fam_base + i
            self.dim = len(self.dim_index)
            self.matrix = np.zeros((len(perfumes), self.dim), dtype=np.float32)
            self.row_of: dict[str, int] = {}
            layer_w = {"top": 0.8, "heart": 1.0, "base": 1.2}
            for r, p in enumerate(perfumes):
                self.row_of[p["perfume_id"]] = r
                v = self.matrix[r]
                for n in p["notes"]:
                    v[self.dim_index[n["note"]]] += layer_w.get(n["layer"], 1.0)
                for a, s in p["accords"].items():
                    v[self.dim_index["accord:" + a]] += 1.5 * s / 100.0
                v[self.dim_index["family:" + p["family"]]] += 1.0
            norms = np.linalg.norm(self.matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self.unit = self.matrix / norms
            # Quality: Bayesian-ish rating shrunk toward 3.8 by vote count, scaled 0..1.
            self.quality = np.zeros(len(perfumes), dtype=np.float32)
            for r, p in enumerate(perfumes):
                rating = p.get("rating") or 3.8
                votes = p.get("rating_count") or 0
                shrunk = (rating * votes + 3.8 * 200) / (votes + 200)
                pop = math.log1p(votes) / math.log1p(50000)
                self.quality[r] = max(0.0, min(1.0, 0.7 * (shrunk - 2.5) / 2.5 + 0.3 * pop))
            # Keyword bags for the non-embedding semantic fallback.
            self.bags: list[set[str]] = []
            df: dict[str, int] = {}
            for p in perfumes:
                words = set(_WORD.findall((p["description"] + " " + p["description_ar"] + " " + p["name"] + " " + p["brand_name"]).lower()))
                words |= {a for a in p["accords"]} | {"family:" + p["family"]}
                words |= set(p["moods"]) | set(p["seasons"]) | set(p["occasions"])
                words |= {n["note"] for n in p["notes"]}
                self.bags.append(words)
                for w in words:
                    df[w] = df.get(w, 0) + 1
            n_docs = max(1, len(perfumes))
            self.idf = {w: math.log((n_docs + 1) / (c + 0.5)) for w, c in df.items()}
            self.embeddings: np.ndarray | None = None
            if self.embedder is not None:
                self._load_embeddings()
            self._name_index = {(p["brand_name"] + " " + p["name"]).lower(): pid for pid, p in self.perfumes.items()}
            self._name_index.update({p["name"].lower(): pid for pid, p in self.perfumes.items() if p["name"].lower() not in self._name_index})

    def _load_embeddings(self) -> None:
        stored = self.db.load_embeddings()
        if len(stored) < len(self.ids):
            missing = [pid for pid in self.ids if pid not in stored]
            texts = [self.perfumes[pid]["description"] + " " + ", ".join(self.perfumes[pid]["accords"]) for pid in missing]
            try:
                vecs = self.embedder(texts)
            except Exception:
                self.embeddings = None
                return
            with self.db.tx() as c:
                for pid, v in zip(missing, vecs):
                    arr = np.asarray(v, dtype=np.float32)
                    c.execute("INSERT OR REPLACE INTO perfume_embedding(perfume_id, model, vector) VALUES (?,?,?)",
                              (pid, settings.azure_openai_embed_deployment, arr.tobytes()))
                    stored[pid] = arr.tobytes()
        mat = np.stack([np.frombuffer(stored[pid], dtype=np.float32) for pid in self.ids]) if self.ids else np.zeros((0, 1))
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.embeddings = mat / norms

    # ------------------------------------------------------------------ lookup
    def get(self, perfume_id: str) -> dict | None:
        return self.perfumes.get(perfume_id)

    def find_by_name(self, name: str) -> dict | None:
        q = re.sub(r"\s+", " ", (name or "").lower().strip())
        if not q:
            return None
        if q in self._name_index:
            return self.perfumes[self._name_index[q]]
        # Contained name (e.g. "baccarat rouge 540 by mfk" or "aventus creed").
        best, best_len = None, 0
        for key, pid in self._name_index.items():
            nm = self.perfumes[pid]["name"].lower()
            if len(nm) >= 4 and nm in q and len(nm) > best_len:
                best, best_len = pid, len(nm)
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
    def passes(self, p: dict, profile: TasteProfile) -> bool:
        """Public hard-filter check (disliked notes, avoided families, budget, brand, gender, completeness)."""
        return self._passes(p, profile)

    def _passes(self, p: dict, profile: TasteProfile) -> bool:
        if not p["recommendable"]:
            return False
        brand = (profile.brand or settings.brand_filter or "").lower().strip()
        if brand and p["brand_name"].lower() != brand:
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
    def recommend(self, profile: TasteProfile, text: str | None = None, k: int = 3) -> dict:
        ranked = self.search(profile, text, limit=max(30, k * 10))
        picks: list[dict] = []
        single_family = len(profile.families) == 1 and not profile.liked_notes
        for cand in ranked:
            fam = cand["perfume"]["family"]
            # Diversify: the top 3 must not all share a family unless one family was asked for.
            if not single_family and len(picks) == k - 1 and picks and all(x["perfume"]["family"] == fam for x in picks):
                continue
            if any(x["perfume"]["brand_name"] == cand["perfume"]["brand_name"] and x["perfume"]["name"] == cand["perfume"]["name"] for x in picks):
                continue
            picks.append(cand)
            if len(picks) == k:
                break
        if len(picks) < k:
            for cand in ranked:
                if cand not in picks:
                    picks.append(cand)
                if len(picks) == k:
                    break
        layering = self.layering_partner(picks[0]["perfume"]["perfume_id"], profile) if picks else None
        return {"picks": picks, "layering": layering}


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
