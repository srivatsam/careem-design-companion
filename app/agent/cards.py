"""Turns a catalogue perfume dict into the localized PerfumeCard the widget renders."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from app.data import taxonomy as tx
from app.schemas import LayeringSuggestion, NoteGroup, PerfumeCard

# Fragrantica product page: https://www.fragrantica.com/perfume/<brand>/<slug>-<id>.html
# Fragrantica bottle photo for that id: https://fimgs.net/mdimg/perfume/375x500.<id>.jpg
_FRAGRANTICA_ID_RE = re.compile(r"-(\d+)\.html$")


def fragrantica_image_url(product_url: str | None) -> str | None:
    """The real bottle photo URL for a Fragrantica product page, or None if it can't be derived."""
    if not product_url:
        return None
    try:
        host = (urlparse(product_url).netloc or "").lower()
    except ValueError:
        return None
    if not (host == "fragrantica.com" or host.endswith(".fragrantica.com")):
        return None
    m = _FRAGRANTICA_ID_RE.search(product_url)
    if not m:
        return None
    return f"https://fimgs.net/mdimg/perfume/375x500.{m.group(1)}.jpg"


def image_url_for(p: dict) -> str:
    """Real photo when we have one, else the generated SVG bottle at /api/image/<perfume_id>."""
    return (p.get("image_url") or fragrantica_image_url(p.get("product_url"))
            or f"/api/image/{p['perfume_id']}")


def price_label(p: dict, lang: str) -> str:
    price = p.get("price_aed")
    if price is None:
        return "—"
    amount = f"{int(round(price)):,}"
    if lang == "ar":
        return f"~{amount} درهم (تقديري)" if p.get("price_source") == "estimated" else f"{amount} درهم"
    return f"~AED {amount} (est.)" if p.get("price_source") == "estimated" else f"AED {amount}"


def key_notes(p: dict, lang: str, n: int = 4) -> list[str]:
    order = {"base": 0, "heart": 1, "top": 2}
    seen: list[str] = []
    for note in sorted(p["notes"], key=lambda x: order.get(x["layer"], 3)):
        if note["note"] not in seen:
            seen.append(note["note"])
    # Prefer the strongest accord families first: keep insertion order but cap.
    return [tx.note_label(x, lang) for x in seen[:n]]


def card(p: dict, lang: str, score: float | None = None, reason: str | None = None) -> PerfumeCard:
    groups = NoteGroup()
    for note in p["notes"]:
        lst = getattr(groups, note["layer"], None)
        if lst is not None and tx.note_label(note["note"], lang) not in lst:
            lst.append(tx.note_label(note["note"], lang))
    accords = [a for a, _ in sorted(p["accords"].items(), key=lambda kv: -kv[1])[:4]]
    if lang == "ar":
        accords = [tx.load()["accords_ar"].get(a, a) for a in accords]
    return PerfumeCard(
        perfume_id=p["perfume_id"],
        name=p["name"],
        brand=p["brand_name"],
        family=p["family"],
        family_label=tx.label("families", p["family"], lang),
        notes=groups,
        key_notes=key_notes(p, lang),
        accords=accords,
        strength=p["strength"],
        strength_label=tx.label("strengths", p["strength"], lang),
        price_aed=p.get("price_aed"),
        price_source=p.get("price_source") or "none",
        price_label=price_label(p, lang),
        image_url=image_url_for(p),
        product_url=p.get("product_url") or product_search_url(p),
        description=p["description_ar"] if lang == "ar" else p["description"],
        reason=reason,
        match_score=int(round(min(1.0, max(0.0, score)) * 100)) if score is not None else None,
        rating=p.get("rating"),
        rating_count=p.get("rating_count"),
    )


def product_search_url(p: dict) -> str:
    from urllib.parse import quote_plus
    return "https://www.google.com/search?tbm=shop&q=" + quote_plus(f"{p['brand_name']} {p['name']} perfume")


def layering_card(base_id: str, partner: dict, lang: str, base_name: str) -> LayeringSuggestion:
    reason = partner["reason_ar"] if lang == "ar" else partner["reason_en"]
    pname = partner["perfume"]["name"]
    lead = f"جرّب {pname} فوق {base_name}. " if lang == "ar" else f"Try {pname} over {base_name}. "
    return LayeringSuggestion(base_perfume_id=base_id, partner=card(partner["perfume"], lang), reason=lead + reason)


def template_reason(p: dict, profile, lang: str) -> str:
    """Deterministic one-line reason from catalogue fields, for the no-LLM path."""
    notes = key_notes(p, lang, 3)
    fam = tx.label("families", p["family"], lang).lower() if lang != "ar" else tx.label("families", p["family"], "ar")
    liked = [tx.note_label(n, lang) for n in getattr(profile, "liked_notes", []) if n in {x["note"] for x in p["notes"]}]
    strength = tx.label("strengths", p["strength"], lang).lower() if lang != "ar" else tx.label("strengths", p["strength"], "ar")
    has_price = p.get("price_aed") is not None
    if lang == "ar":
        why = f"يحتوي على {'، '.join(liked)} التي تحبها" if liked else f"طابعه {fam} مع {'، '.join(notes)}"
        price_part = f" وسعره {price_label(p, 'ar')}" if has_price else ""
        return f"{why}. ثباته {strength}{price_part}."
    why = f"has the {', '.join(liked)} you like" if liked else f"is a {fam} scent built on {', '.join(notes)}"
    price_part = f" and costs {price_label(p, 'en')}" if has_price else ""
    return f"{p['name']} {why}. It wears {strength}{price_part}."
