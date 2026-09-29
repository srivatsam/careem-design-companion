"""Unit tests for perfume card image selection (app/agent/cards.py)."""
from __future__ import annotations

from app.agent.cards import fragrantica_image_url, image_url_for, template_reason
from app.schemas import TasteProfile


def test_fragrantica_image_url_extracts_trailing_id():
    url = "https://www.fragrantica.com/perfume/xerjoff/accento-overdose-pride-edition-74630.html"
    assert fragrantica_image_url(url) == "https://fimgs.net/mdimg/perfume/375x500.74630.jpg"


def test_fragrantica_image_url_rejects_non_fragrantica_domains():
    assert fragrantica_image_url("https://www.google.com/search?tbm=shop&q=74630") is None
    assert fragrantica_image_url("https://notfragrantica.com/perfume/x/y-74630.html") is None
    assert fragrantica_image_url("https://fragrantica.com.evil.tld/x-1.html") is None


def test_fragrantica_image_url_requires_a_trailing_numeric_id():
    assert fragrantica_image_url("https://www.fragrantica.com/perfume/xerjoff/accento-overdose.html") is None
    assert fragrantica_image_url("https://www.fragrantica.com/designers/xerjoff.html") is None


def test_fragrantica_image_url_handles_missing_input():
    assert fragrantica_image_url(None) is None
    assert fragrantica_image_url("") is None


def test_image_url_for_prefers_the_row_own_image_url():
    p = {"perfume_id": "p1", "image_url": "https://cdn.example.com/p1.jpg",
         "product_url": "https://www.fragrantica.com/perfume/x/y-123.html"}
    assert image_url_for(p) == "https://cdn.example.com/p1.jpg"


def test_image_url_for_falls_back_to_fragrantica_photo():
    p = {"perfume_id": "p1", "image_url": None,
         "product_url": "https://www.fragrantica.com/perfume/x/y-123.html"}
    assert image_url_for(p) == "https://fimgs.net/mdimg/perfume/375x500.123.jpg"


def test_image_url_for_falls_back_to_svg_endpoint():
    p = {"perfume_id": "p1", "image_url": None, "product_url": None}
    assert image_url_for(p) == "/api/image/p1"

    p2 = {"perfume_id": "p2", "image_url": "", "product_url": "https://www.google.com/search?q=x"}
    assert image_url_for(p2) == "/api/image/p2"


# ---------------------------------------------------------------------------------------------------------------
# template_reason wording: strength and price are separate facts, not "wears X at Y" (fix 12).
# ---------------------------------------------------------------------------------------------------------------
def _perfume(price_aed=140, price_source="estimated"):
    return {
        "perfume_id": "p1", "name": "Amber Nights", "brand_name": "Test House", "family": "woody",
        "notes": [{"note": "vanilla", "layer": "base"}, {"note": "cedar", "layer": "base"}, {"note": "bergamot", "layer": "top"}],
        "strength": 4, "price_aed": price_aed, "price_source": price_source,
    }


def test_template_reason_separates_strength_and_price():
    reason = template_reason(_perfume(), TasteProfile(liked_notes=["vanilla"]), "en")
    assert reason == "Amber Nights has the vanilla you like. It wears strong and costs ~AED 140 (est.)."
    assert "wears strong at" not in reason  # price must no longer read as if it sets the strength


def test_template_reason_handles_missing_price_gracefully():
    reason = template_reason(_perfume(price_aed=None, price_source="none"), TasteProfile(liked_notes=["vanilla"]), "en")
    assert reason == "Amber Nights has the vanilla you like. It wears strong."
    assert "costs" not in reason


def test_template_reason_arabic_separates_strength_and_price():
    reason = template_reason(_perfume(), TasteProfile(liked_notes=["vanilla"]), "ar")
    assert "وسعره" in reason  # "and its price" -- a separate clause, not bundled into the strength clause
    assert "~140 درهم (تقديري)" in reason


def test_template_reason_arabic_handles_missing_price_gracefully():
    reason = template_reason(_perfume(price_aed=None, price_source="none"), TasteProfile(liked_notes=["vanilla"]), "ar")
    assert "وسعره" not in reason
