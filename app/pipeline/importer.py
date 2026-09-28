"""Imports a perfume CSV (Kaggle Fragrantica schema or a generic brand CSV) into the catalogue.

Usage:
    python -m app.pipeline.importer data/raw/fra_cleaned.csv --source kaggle-fragrantica --licence "scraped; prototype only"
    python -m app.pipeline.importer data/seed/seed_catalogue.csv --source seed --licence unverified --replace

Every row gets: normalised notes, accords 0..100, an inferred family, strength, seasons, occasions, moods,
a generated description (en, ar), a price (catalogue price if present, otherwise an estimate flagged as such),
and the source and licence recorded on the row. Rows failing the completeness rule are stored but not recommendable.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from pathlib import Path

from app.data import taxonomy as tx
from app.data.db import Database, new_id

csv.field_size_limit(10_000_000)

# Column aliases: canonical -> possible header names (lower-cased) in the source CSV.
COLUMNS = {
    "name": ["perfume", "name", "fragrance", "title", "perfume_name"],
    "brand": ["brand", "house", "brand_name", "company"],
    "country": ["country"],
    "gender": ["gender", "for_gender"],
    "rating": ["rating value", "rating", "rating_value", "score"],
    "rating_count": ["rating count", "rating_count", "votes", "number_votes"],
    "year": ["year", "launch_year", "launch year"],
    "top": ["top", "top notes", "top_notes", "notes_top"],
    "middle": ["middle", "heart", "middle notes", "heart notes", "middle_notes", "notes_middle"],
    "base": ["base", "base notes", "base_notes", "notes_base"],
    "notes": ["notes", "all notes", "all_notes"],
    "accords": ["accords", "main accords", "main_accords"],
    "description": ["description", "desc", "about"],
    "description_ar": ["description_ar", "desc_ar"],
    "price": ["price_aed", "price", "price aed"],
    "currency": ["currency"],
    "image_url": ["image_url", "image", "img", "picture"],
    "product_url": ["product_url", "url", "link"],
    "concentration": ["concentration", "type"],
    "longevity": ["longevity"],
    "sillage": ["sillage"],
}

NICHE = {"creed", "tom ford", "maison francis kurkdjian", "xerjoff", "roja parfums", "roja dove", "amouage", "byredo", "le labo",
         "parfums de marly", "initio parfums prives", "initio", "nishane", "by kilian", "kilian", "frederic malle", "diptyque",
         "penhaligon's", "memo paris", "clive christian", "bond no 9", "serge lutens", "maison margiela", "acqua di parma",
         "louis vuitton", "chanel exclusifs", "guerlain", "atelier cologne", "juliette has a gun", "mancera", "montale",
         "tiziana terenzi", "orto parisi", "nasomatto", "escentric molecules", "kayali", "ormonde jayne", "bdk parfums",
         "matiere premiere", "lattafa pride", "ex nihilo", "hermes", "hermès", "chanel", "dior"}
VALUE = {"lattafa", "armaf", "rasasi", "ajmal", "swiss arabian", "al haramain", "afnan", "zimaya", "maison alhambra",
         "fragrance world", "ard al zaafaran", "nabeel", "al rehab", "lattafa perfumes", "paris corner", "french avenue",
         "emper", "ajmal perfumes", "asdaaf", "milestone", "zara", "bath & body works", "victoria's secret", "the body shop",
         "avon", "oriflame", "yardley", "adidas", "playboy", "nautica", "arabiyat", "khadlaj"}


def _lower_map(header: list[str]) -> dict[str, str]:
    """Canonical column -> actual header."""
    lowered = {h.lower().strip(): h for h in header}
    out = {}
    for canon, aliases in COLUMNS.items():
        for a in aliases:
            if a in lowered:
                out[canon] = lowered[a]
                break
    return out


def split_list(text: str | None) -> list[str]:
    if not text:
        return []
    text = text.strip()
    if text.lower() in {"", "nan", "none", "null", "unknown", "-"}:
        return []
    if text.startswith("["):
        try:
            return [str(x) for x in json.loads(text.replace("'", '"'))]
        except Exception:
            text = text.strip("[]")
    parts = re.split(r"[,;|/]| and ", text)
    return [p.strip().strip("'\"") for p in parts if p.strip().strip("'\"")]


def infer_family(accords: dict[str, int], master_notes: list[str]) -> str:
    score: dict[str, float] = {f: 0.0 for f in tx.families()}
    for accord, strength in accords.items():
        fam = tx.accord_family(accord)
        if fam:
            score[fam] += strength
    if not any(score.values()):
        for n in master_notes:
            score[tx.note_family(n)] += 1
    if not any(score.values()):
        return "floral"
    return max(score.items(), key=lambda kv: kv[1])[0]


def infer_strength(family: str, accords: dict[str, int], master_notes: list[str], longevity: str | None, sillage: str | None) -> int:
    lookup = {"very weak": 1, "weak": 2, "moderate": 3, "long lasting": 4, "eternal": 5,
              "intimate": 2, "strong": 4, "enormous": 5}
    votes = [lookup[v.lower().strip()] for v in (longevity, sillage) if v and v.lower().strip() in lookup]
    if votes:
        return round(sum(votes) / len(votes))
    base = tx.load()["family_defaults"][family]["strength"]
    heavy = {"oud", "incense", "leather", "tobacco", "amber", "patchouli", "coffee", "smoke", "animalic notes"}
    light = {"sea notes", "clean notes", "citrus", "bergamot", "lemon", "grapefruit", "green notes", "tea", "mint", "aldehydes"}
    n_heavy = sum(1 for n in master_notes if n in heavy)
    n_light = sum(1 for n in master_notes if n in light)
    strength = base + (1 if n_heavy >= 2 else 0) - (1 if n_light >= 3 else 0)
    return max(1, min(5, strength))


def infer_tags(family: str, strength: int, master_notes: list[str]) -> tuple[list[str], list[str], list[str]]:
    d = tx.load()["family_defaults"][family]
    seasons = list(d["seasons"])
    moods = list(d["moods"])
    occasions = ["everyday"] if strength <= 3 else []
    if strength <= 2:
        occasions += ["office", "outdoor"]
    if strength >= 3 and family in {"amber", "woody", "gourmand"}:
        occasions += ["evening"]
    if family in {"floral", "gourmand", "amber"}:
        occasions += ["date"]
    if family in {"floral", "fresh"}:
        occasions += ["wedding"]
    if "oud" in master_notes or "rose" in master_notes or "saffron" in master_notes:
        if "elegant" not in moods:
            moods.append("elegant")
        if "evening" not in occasions:
            occasions.append("evening")
    if family in {"amber", "woody"} and strength >= 4:
        seasons = ["autumn", "winter"]
    if family in {"fresh", "aquatic"} and strength <= 2:
        seasons = ["spring", "summer"]
    occasions.append("gift")
    return seasons, list(dict.fromkeys(occasions)), moods


def _price_band(brand: str) -> tuple[int, int]:
    b = brand.lower().strip()
    if b in NICHE:
        return (750, 1400)
    if b in VALUE:
        return (70, 220)
    return (280, 520)


def estimate_price(brand: str, name: str) -> float:
    lo, hi = _price_band(brand)
    h = int(hashlib.sha1(f"{brand}|{name}".lower().encode()).hexdigest(), 16)
    return float(lo + (h % (hi - lo + 1)) // 5 * 5)


def build_description(name: str, brand: str, family: str, notes: list[dict], accords: dict[str, int], lang: str) -> str:
    def names(layer: str) -> list[str]:
        seen = []
        for n in notes:
            if n["layer"] == layer and n["note"] not in seen:
                seen.append(n["note"])
        return seen[:4]

    top, heart, base = names("top"), names("heart"), names("base")
    top_accords = [a for a, _ in sorted(accords.items(), key=lambda kv: -kv[1])[:3]]
    if lang == "ar":
        fam = tx.label("families", family, "ar")
        lab = lambda xs: "، ".join(tx.note_label(x, "ar") for x in xs)  # noqa: E731
        parts = [f"{name} من {brand} عطر {fam}."]
        if top:
            parts.append(f"يفتتح بـ{lab(top)}")
        if heart:
            parts.append(f"وقلبه {lab(heart)}")
        if base:
            parts.append(f"على قاعدة من {lab(base)}")
        text = " ".join(parts).rstrip() + "."
        if top_accords:
            text += " الطابع العام: " + "، ".join(tx.load()["accords_ar"].get(a, a) for a in top_accords) + "."
        return text
    fam = tx.label("families", family, "en").lower()
    parts = [f"{name} by {brand} is a {fam} fragrance."]
    if top:
        parts.append("It opens with " + ", ".join(top))
    if heart:
        parts.append(("over a heart of " if top else "It has a heart of ") + ", ".join(heart))
    if base:
        parts.append(("and settles on " if (top or heart) else "It settles on ") + ", ".join(base))
    text = " ".join(parts).rstrip(".") + "."
    if top_accords:
        text += " Main accords: " + ", ".join(top_accords) + "."
    return text


def parse_accords(row: dict, cols: dict[str, str]) -> dict[str, int]:
    accords: dict[str, int] = {}
    # Kaggle Fragrantica: mainaccord1..mainaccord5 (ranked). Generic: "accords" column "sweet:90, woody:60" or a list.
    ranked = [row.get(f"mainaccord{i}") for i in range(1, 6)]
    ranked = [a.strip().lower() for a in ranked if a and a.strip() and a.strip().lower() != "nan"]
    for i, a in enumerate(ranked):
        accords[a] = [100, 80, 65, 50, 40][i]
    if not accords and "accords" in cols:
        for item in split_list(row.get(cols["accords"])):
            if ":" in item:
                a, s = item.split(":", 1)
                try:
                    accords[a.strip().lower()] = max(0, min(100, int(float(s))))
                except ValueError:
                    accords[a.strip().lower()] = 60
            else:
                accords[item.lower()] = max(30, 100 - 15 * len(accords))
    return accords


def import_csv(path: str, source: str, licence: str, replace: bool = False, db: Database | None = None,
               delimiter: str | None = None, encoding: str | None = None, limit: int | None = None) -> dict:
    db = db or Database()
    p = Path(path)
    raw = p.read_bytes()
    text = None
    for enc in ([encoding] if encoding else ["utf-8-sig", "latin-1"]):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise SystemExit("could not decode file")
    if delimiter is None:
        first = text.splitlines()[0]
        delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    cols = _lower_map(reader.fieldnames or [])
    if "name" not in cols or "brand" not in cols:
        raise SystemExit(f"CSV needs name and brand columns; found {reader.fieldnames}")

    stats = {"rows": 0, "imported": 0, "duplicates": 0, "not_recommendable": 0, "unknown_notes": 0}
    unknown_notes: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    now = time.time()

    with db.tx() as c:
        if replace:
            for t in ("perfume_note", "perfume_accord", "perfume_embedding", "layering_pair", "perfume", "brand"):
                c.execute(f"DELETE FROM {t}")
        # Note table mirrors the taxonomy.
        for master, spec in tx.load()["notes"].items():
            c.execute("INSERT OR REPLACE INTO note(note_id, name_ar, family, synonyms) VALUES (?,?,?,?)",
                      (master, spec["ar"], spec["family"], json.dumps(spec.get("synonyms", []), ensure_ascii=False)))
        brand_ids = {r["name"].lower(): r["brand_id"] for r in c.execute("SELECT brand_id, name FROM brand")}

        for row in reader:
            stats["rows"] += 1
            if limit and stats["rows"] > limit:
                break
            name = (row.get(cols["name"]) or "").strip()
            brand = (row.get(cols["brand"]) or "").strip()
            if not name or not brand:
                continue
            name = re.sub(r"\s+", " ", name)
            # Kaggle names often repeat the brand ("Aventus Creed for men"): strip trailing brand + audience.
            name = re.sub(rf"\s+{re.escape(brand)}\s*(for (women|men|women and men))?$", "", name, flags=re.I).strip() or name
            name = re.sub(r"\s+for (women|men|women and men)$", "", name, flags=re.I).strip() or name
            key = (brand.lower(), name.lower())
            if key in seen:
                stats["duplicates"] += 1
                continue
            seen.add(key)

            notes: list[dict] = []
            raw_by_layer = {
                "top": split_list(row.get(cols.get("top", ""), "")),
                "heart": split_list(row.get(cols.get("middle", ""), "")),
                "base": split_list(row.get(cols.get("base", ""), "")),
            }
            if not any(raw_by_layer.values()) and "notes" in cols:
                raw_by_layer["heart"] = split_list(row.get(cols["notes"]))
            for layer, raws in raw_by_layer.items():
                for r in raws:
                    master = tx.normalise_note(r)
                    if master is None:
                        unknown_notes[r.lower()] = unknown_notes.get(r.lower(), 0) + 1
                        continue
                    notes.append({"note": master, "layer": layer, "raw": r})
            master_notes = list(dict.fromkeys(n["note"] for n in notes))
            accords = parse_accords(row, cols)
            family = infer_family(accords, master_notes)
            longevity = row.get(cols.get("longevity", ""), None) if "longevity" in cols else None
            sillage = row.get(cols.get("sillage", ""), None) if "sillage" in cols else None
            strength = infer_strength(family, accords, master_notes, longevity, sillage)
            seasons, occasions, moods = infer_tags(family, strength, master_notes)

            description = (row.get(cols.get("description", ""), "") or "").strip() if "description" in cols else ""
            if not description or description.lower() == "nan":
                description = build_description(name, brand, family, notes, accords, "en")
            description_ar = (row.get(cols.get("description_ar", ""), "") or "").strip() if "description_ar" in cols else ""
            if not description_ar or description_ar.lower() == "nan":
                description_ar = build_description(name, brand, family, notes, accords, "ar")

            price, price_source = None, "none"
            if "price" in cols:
                try:
                    price = float(str(row.get(cols["price"], "")).replace(",", "").strip() or "nan")
                    if price == price:  # not NaN
                        price_source = "catalogue"
                    else:
                        price = None
                except ValueError:
                    price = None
            if price is None:
                price, price_source = estimate_price(brand, name), "estimated"

            def num(col: str):
                if col not in cols:
                    return None
                try:
                    v = float(str(row.get(cols[col], "")).replace(",", ".").strip())
                    return v if v == v else None
                except ValueError:
                    return None

            rating, rating_count, year = num("rating"), num("rating_count"), num("year")
            recommendable = int(bool(family) and len(master_notes) >= 3 and bool(description))
            if not recommendable:
                stats["not_recommendable"] += 1

            bid = brand_ids.get(brand.lower())
            if not bid:
                bid = new_id("b_")
                c.execute("INSERT INTO brand(brand_id, name, country) VALUES (?,?,?)",
                          (bid, brand, (row.get(cols.get("country", ""), None) or None) if "country" in cols else None))
                brand_ids[brand.lower()] = bid
            pid = "p_" + hashlib.sha1(f"{brand}|{name}".lower().encode()).hexdigest()[:12]
            c.execute("DELETE FROM perfume WHERE perfume_id=?", (pid,))
            c.execute(
                """INSERT INTO perfume(perfume_id, name, brand_id, brand_name, launch_year, concentration, gender, family, strength,
                   seasons, occasions, moods, description, description_ar, image_url, product_url, price_aed, price_source,
                   rating, rating_count, source, licence, recommendable)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, name, bid, brand, int(year) if year else None,
                 (row.get(cols.get("concentration", ""), None) or None) if "concentration" in cols else None,
                 (row.get(cols.get("gender", ""), None) or None) if "gender" in cols else None,
                 family, strength, json.dumps(seasons), json.dumps(occasions), json.dumps(moods),
                 description, description_ar,
                 (row.get(cols.get("image_url", ""), None) or None) if "image_url" in cols else None,
                 (row.get(cols.get("product_url", ""), None) or None) if "product_url" in cols else None,
                 price, price_source, rating, int(rating_count) if rating_count else None, source, licence, recommendable),
            )
            for n in notes:
                c.execute("INSERT OR IGNORE INTO perfume_note(perfume_id, note_id, layer, raw_name) VALUES (?,?,?,?)",
                          (pid, n["note"], n["layer"], n["raw"]))
            for a, s in accords.items():
                c.execute("INSERT OR REPLACE INTO perfume_accord(perfume_id, accord, strength) VALUES (?,?,?)", (pid, a, s))
            stats["imported"] += 1

        for raw, count in sorted(unknown_notes.items(), key=lambda kv: -kv[1])[:500]:
            c.execute("INSERT INTO review_queue(kind, payload, created_at) VALUES ('unknown_note', ?, ?)",
                      (json.dumps({"note": raw, "count": count, "source": source}), now))
    stats["unknown_notes"] = len(unknown_notes)
    return stats


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--source", required=True)
    ap.add_argument("--licence", required=True)
    ap.add_argument("--replace", action="store_true", help="wipe the catalogue first")
    ap.add_argument("--delimiter")
    ap.add_argument("--encoding")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--db")
    args = ap.parse_args(argv)
    db = Database(args.db) if args.db else Database()
    stats = import_csv(args.csv, args.source, args.licence, args.replace, db, args.delimiter, args.encoding, args.limit)
    print(json.dumps(stats))


if __name__ == "__main__":
    main(sys.argv[1:])
