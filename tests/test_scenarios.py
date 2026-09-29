"""Scenario step of guided match: the shopper pictures moments ("Barefoot on a beach at sunset") instead of naming
notes, then picks a follow-up moment. Covers the library's integrity, the instant Q2/Q3 turns, answer reading in
both languages, skips, the early finish, free-chat mapping, the "Feel" summary tag and API backward compatibility."""
from __future__ import annotations

import re

import pytest

from app.agent import extract as ex
from app.data import scenarios as sc
from app.data import taxonomy as tx
from test_guided import _make_client, _new_session

ARABIC = re.compile(r"[؀-ۿ]")


@pytest.fixture()
def mock_client(tmp_path_factory):
    _, client = _make_client(tmp_path_factory.mktemp("scn_mock"), "mock")
    return client


@pytest.fixture()
def none_client(tmp_path_factory):
    _, client = _make_client(tmp_path_factory.mktemp("scn_none"), "none")
    return client


def _all_items():
    for s in sc.SCENARIOS:
        yield s
        yield from s["moments"]


def _chat(client, sid, message, lang=None):
    body = {"session_id": sid, "message": message}
    if lang:
        body["lang"] = lang
    return client.post("/api/chat", json=body).json()


def _start(client, lang="en", who="For me"):
    sid = _new_session(client, lang)
    client.post("/api/guide/start", json={"session_id": sid, "lang": lang})
    return sid, _chat(client, sid, who, lang)


@pytest.fixture()
def model_calls(monkeypatch):
    """Counts agent runs, so a test can prove a turn was instant (no model call)."""
    import sys

    main_mod = sys.modules["app.main"]
    calls = []
    real = main_mod.llm_agent.run_agent

    async def spy(ctx, text, history):
        calls.append(text)
        return await real(ctx, text, history)

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", spy)
    return calls


# =================================================================================================================
# Library integrity
# =================================================================================================================
def test_every_mapped_value_exists_in_the_taxonomy():
    t = tx.load()
    assert 8 <= len(sc.SCENARIOS) <= 12
    for it in _all_items():
        taste = it["taste"]
        assert set(taste) <= {"liked_notes", "families", "moods", "occasions", "seasons", "strength"}, it["id"]
        assert taste.get("liked_notes") or taste.get("families"), it["id"]
        for n in taste.get("liked_notes", []):
            assert n in t["notes"], (it["id"], n)
        for f in taste.get("families", []):
            assert f in t["families"], (it["id"], f)
        for m in taste.get("moods", []):
            assert m in t["moods"], (it["id"], m)
        for o in taste.get("occasions", []):
            assert o in t["occasions"], (it["id"], o)
        for s in taste.get("seasons", []):
            assert s in t["seasons"], (it["id"], s)
        assert it["family"] in t["families"], it["id"]
    for s in sc.SCENARIOS:
        assert s["motif"] in sc.MOTIFS
        assert "strength" not in s["taste"], "strength is a hard filter: only a chosen moment sets it"
        assert len(s["moments"]) == 3
        for m in s["moments"]:
            assert 1 <= m["taste"]["strength"] <= 5
    ids = [it["id"] for it in _all_items()]
    assert len(ids) == len(set(ids))
    assert {s["family"] for s in sc.SCENARIOS} == set(t["families"]), "every family colour appears on the grid"


def test_every_item_has_english_and_arabic_strings():
    for it in _all_items():
        for field in ("title", "caption"):
            en, ar = it[field]["en"], it[field]["ar"]
            assert en.strip() and not ARABIC.search(en), (it["id"], field)
            assert ar.strip() and ARABIC.search(ar), (it["id"], field)
            assert len(en) <= 42 and len(ar) <= 46, (it["id"], field)
    for s in sc.SCENARIOS:
        assert s["short"]["en"] and ARABIC.search(s["short"]["ar"])
        assert s["keywords"]["en"] and s["keywords"]["ar"]


def test_titles_read_safely_as_answers():
    """A title is sent back as the shopper's answer, so it must never trip the guardrails or the "show me picks"
    shortcut, and must be told apart from every other title by phrase matching."""
    for it in _all_items():
        for lang in ("en", "ar"):
            label = it["title"][lang]
            assert not ex.wants_recommendation(label), label
            assert not ex.is_medical(label) and not ex.is_injection(label) and not ex.is_off_topic(label), label
    for lang in ("en", "ar"):
        scen_titles = [s["title"][lang] for s in sc.SCENARIOS]
        assert all("," not in t and "،" not in t for t in scen_titles), "multi-select answers are joined with commas"
        for group in (scen_titles, [m["title"][lang] for s in sc.SCENARIOS for m in s["moments"]]):
            norm = [sc._norm(t) for t in group]
            for i, a in enumerate(norm):
                assert not any(i != j and a in b for j, b in enumerate(norm)), group[i]


def test_profile_for_merges_scenarios_and_moments():
    prof = sc.profile_for(["beach"], ["beach_sunrise_swim"])
    assert prof.scenarios == ["beach"] and prof.moments == ["beach_sunrise_swim"]
    assert "sea notes" in prof.liked_notes and "mineral notes" in prof.liked_notes
    assert prof.families[:1] == ["aquatic"] and prof.strength == 2
    # a moment brings its scenario along; free chat never sets a strength
    loose = sc.profile_for([], ["desert_campfire"], with_strength=False)
    assert loose.scenarios == ["desert_night"] and loose.strength is None
    assert len(sc.profile_for(["beach", "rooftop", "fireside", "garden"]).scenarios) == 3


# =================================================================================================================
# Q2 and Q3 are instant, rule-based cards
# =================================================================================================================
def test_q2_is_an_instant_scenario_card_grid(mock_client, model_calls):
    sid, r = _start(mock_client)
    q = r["next_question"]
    assert not model_calls, "Q2 must not call the model"
    assert q["id"] == "scenario" and q["topic"] == "scenario" and q["multi"] is True
    assert q["index"] == 2 and q["max_index"] == 5
    assert q["ask_reason"] == "Choose up to three."
    assert len(q["options"]) == len(sc.SCENARIOS)
    for o in q["options"]:
        assert o["caption"] and o["motif"] in sc.MOTIFS and o["family"] in tx.families()
    assert r["reply"] == ""


def test_q2_is_worded_for_a_gift():
    import sys

    main_mod = sys.modules.get("app.main")
    if main_mod is None:
        import app.main as main_mod
    assert "her" in main_mod.guided_scenario_question("en", "gift_her").question
    assert "them" in main_mod.guided_scenario_question("en", "gift_unsure").question
    assert ARABIC.search(main_mod.guided_scenario_question("ar", "gift_him").question)


def test_q3_offers_the_first_scenarios_moments_instantly(mock_client, model_calls):
    sid, _ = _start(mock_client)
    r = _chat(mock_client, sid, "Barefoot on a beach at sunset")
    q = r["next_question"]
    assert not model_calls, "Q3 must not call the model"
    assert q["topic"] == "scenario_moment" and q["multi"] is False and q["index"] == 3
    assert "beach" in q["question"]
    assert [o["id"] for o in q["options"]] == ["beach_sunrise_swim", "beach_golden_hour", "beach_island"]
    assert all(o["motif"] == "sun_waves" and o["caption"] for o in q["options"])
    assert r["profile"]["scenarios"] == ["beach"]


def test_q3_with_two_scenarios_references_the_first_and_borrows_one_moment_from_the_second(mock_client):
    sid, _ = _start(mock_client)
    r = _chat(mock_client, sid, "Walking into a rooftop party, Barefoot on a beach at sunset")
    q = r["next_question"]
    assert q["question"].startswith("Starting with the rooftop party")
    ids = [o["id"] for o in q["options"]]
    assert ids[:3] == ["rooftop_city_lights", "rooftop_velvet_lounge", "rooftop_golden_entrance"]
    assert ids[3] == "beach_sunrise_swim"
    assert r["profile"]["scenarios"] == ["rooftop", "beach"]


def test_multi_select_keeps_at_most_three_scenarios(none_client):
    sid, _ = _start(none_client)
    r = _chat(none_client, sid, "beach, rooftop, fireside, garden")
    assert r["profile"]["scenarios"] == ["beach", "rooftop", "fireside"]


# =================================================================================================================
# Answer reading: option id first, then the title, either language
# =================================================================================================================
@pytest.mark.parametrize("answer, expected", [
    ("desert_night", ["desert_night"]),
    ("A DESERT NIGHT UNDER THE STARS", ["desert_night"]),
    ("fireside, citrus_grove", ["fireside", "citrus_grove"]),
    ("ليلة في الصحراء تحت النجوم، موعد أول على ضوء الشموع", ["desert_night", "date"]),
])
def test_scenario_answers_map_by_id_or_title(answer, expected):
    pending = {"topic": "scenario", "options": [{"id": s["id"], "label": s["title"]["en"]} for s in sc.SCENARIOS]}
    prof = ex.interpret_guided_answer(answer, pending)
    assert prof.scenarios == expected
    assert prof.strength is None


def test_moment_answers_map_in_both_languages_and_set_strength():
    pending = {"topic": "scenario_moment", "options": [{"id": m["id"], "label": m["title"]["ar"]}
                                                       for m in sc.scenario("beach")["moments"]]}
    for answer in ("Sunrise swim, salty skin", "سباحة الفجر وملح على البشرة", "beach_sunrise_swim"):
        prof = ex.interpret_guided_answer(answer, pending)
        assert prof.moments == ["beach_sunrise_swim"], answer
        assert prof.strength == 2 and "sea notes" in prof.liked_notes


def test_arabic_run_is_fully_localised(none_client):
    sid, r = _start(none_client, "ar", "لي أنا")
    q = r["next_question"]
    assert ARABIC.search(q["question"]) and all(ARABIC.search(o["label"]) and ARABIC.search(o["caption"])
                                                for o in q["options"])
    r = _chat(none_client, sid, "أتجوّل في سوق التوابل عند المغيب", "ar")
    q = r["next_question"]
    assert q["topic"] == "scenario_moment" and ARABIC.search(q["question"])
    assert r["profile"]["scenarios"] == ["souk"]
    r = _chat(none_client, sid, "تمر وقهوة وهيل", "ar")
    assert r["profile"]["moments"] == ["souk_dates_coffee"]


def test_something_else_typed_at_q3_reads_the_words_without_setting_strength(none_client):
    sid, _ = _start(none_client)
    _chat(none_client, sid, "A citrus grove on the Riviera")
    r = _chat(none_client, sid, "hot cocoa by the window")
    assert r["profile"]["moments"] == ["fireside_cocoa"]
    assert r["profile"]["strength"] is None
    assert "chocolate" in r["profile"]["liked_notes"]


# =================================================================================================================
# Skips and the early finish
# =================================================================================================================
def test_skip_at_q2_falls_back_to_the_ordinary_flow(mock_client):
    sid, _ = _start(mock_client)
    r = _chat(mock_client, sid, "Skip")
    q = r["next_question"]
    assert q is not None and q["index"] == 3 and q["topic"] not in ("scenario", "scenario_moment")
    assert r["profile"]["scenarios"] == []


def test_skip_at_q3_keeps_the_scenario_and_moves_to_budget(mock_client):
    sid, _ = _start(mock_client)
    _chat(mock_client, sid, "Owning the boardroom")
    r = _chat(mock_client, sid, "Skip")
    assert r["next_question"]["topic"] == "budget" and r["next_question"]["index"] == 4
    assert r["profile"]["scenarios"] == ["boardroom"] and r["profile"]["moments"] == []


@pytest.mark.parametrize("client_name", ["mock_client", "none_client"])
def test_scenario_answers_reach_picks_in_four_questions(client_name, request):
    client = request.getfixturevalue(client_name)
    sid, r = _start(client)
    asked = 2  # "who is this for?" and the scenario grid
    for message in ("A candlelit first date", "A slow dance, close and warm", "Under AED 500", "Skip"):
        r = _chat(client, sid, message)
        if r["picks"]:
            break
        asked += 1
    assert len(r["picks"]) == 3
    assert asked == 4, asked
    assert r["profile"]["moments"] == ["date_slow_dance"] and r["profile"]["strength"] == 3


def test_a_known_budget_reaches_picks_in_three_questions(mock_client):
    sid, r = _start(mock_client, who="For me, under AED 400")
    assert r["next_question"]["topic"] == "scenario"
    _chat(mock_client, sid, "Fresh linen on a crisp morning")
    r = _chat(mock_client, sid, "Green tea on the balcony")
    assert len(r["picks"]) == 3
    assert all(p["price_aed"] is None or p["price_aed"] <= 400 for p in r["picks"])


def test_show_my_picks_now_from_the_scenario_grid(mock_client):
    sid, _ = _start(mock_client)
    _chat(mock_client, sid, "A spring garden in full bloom")
    r = mock_client.post("/api/guide/finish", json={"session_id": sid}).json()
    assert len(r["picks"]) == 3 and r["guided"] is True


# =================================================================================================================
# The moment reaches the model and the final reply
# =================================================================================================================
def test_the_closing_reply_names_the_moment(mock_client):
    sid, _ = _start(mock_client)
    _chat(mock_client, sid, "Barefoot on a beach at sunset")
    _chat(mock_client, sid, "Golden hour on the sand")
    r = _chat(mock_client, sid, "Under AED 500")
    assert len(r["picks"]) == 3
    assert "Golden hour on the sand" in r["reply"]
    assert r["picks"][0]["name"] in r["reply"]


def test_template_finish_names_the_moment_without_the_model(none_client):
    sid, _ = _start(none_client)
    _chat(none_client, sid, "Wandering a spice souk at dusk")
    _chat(none_client, sid, "Incense drifting through the lanes")
    r = _chat(none_client, sid, "No limit")
    assert len(r["picks"]) == 3
    assert r["reply"].startswith("Here are three picks made for “Incense drifting through the lanes”")


def test_instructions_carry_the_feel_line_in_guided_mode_only():
    from app.agent.llm_agent import AgentContext, instructions
    from app.schemas import TasteProfile

    class _Wrapper:
        def __init__(self, ctx):
            self.context = ctx

    prof = TasteProfile(scenarios=["beach", "rooftop"], moments=["beach_island"])
    guided = AgentContext(session_id="s", language="en", profile=prof, db=None, catalogue=None, guided=True)
    text = instructions(_Wrapper(guided), None)
    assert "The shopper wants to feel (moments they picked): A tropical island escape | Walking into a rooftop party" in text
    chat = AgentContext(session_id="s", language="en", profile=prof, db=None, catalogue=None)
    assert "wants to feel" not in instructions(_Wrapper(chat), None)


def test_moment_titles_never_count_as_naming_an_unshown_perfume(mock_client):
    import sys

    main_mod = sys.modules["app.main"]
    # Whatever the catalogue holds, a phrase blanked out through `ignore` can never read as a perfume name.
    name = next(iter(main_mod.catalogue.perfumes.values()))["name"]
    assert main_mod._mentions_offpick_perfume(f"For {name} and more.", set(), [name]) is False


# =================================================================================================================
# Free chat reads the same library
# =================================================================================================================
@pytest.mark.parametrize("text, expected", [
    ("I want to smell like a beach holiday", ["beach"]),
    ("something for a fancy party", ["rooftop"]),
    ("a cozy night in by the fire, then a party", ["fireside", "rooftop"]),
    ("أريد عطراً للشاطئ", ["beach"]),
    ("عطر لحفلة فخمة", ["rooftop"]),
    ("عطر لموعد أول", ["date"]),
    ("not for the beach, just daily wear", []),
    ("I'm shopping for a perfume", []),
    ("أتسوق لشراء عطر", []),
])
def test_free_text_scenario_phrases(text, expected):
    assert sc.match_text(text)[0] == expected


def test_free_chat_maps_a_scenario_into_the_profile(none_client, mock_client):
    for client in (none_client, mock_client):
        sid = _new_session(client)
        r = _chat(client, sid, "I want to smell like a beach holiday")
        assert r["profile"]["scenarios"] == ["beach"]
        assert "sea notes" in r["profile"]["liked_notes"]
        assert r["profile"]["strength"] is None
        assert len(r["picks"]) == 3
    sid = _new_session(none_client, "ar")
    r = _chat(none_client, sid, "أبحث عن عطر لحفلة فخمة", "ar")
    assert r["profile"]["scenarios"] == ["rooftop"]


# =================================================================================================================
# Summary tags and backward compatibility
# =================================================================================================================
def test_feel_tag_comes_before_loves_and_is_localised():
    import app.main as main_mod
    from app.schemas import TasteProfile

    prof = TasteProfile(guided_for="self", scenarios=["beach", "rooftop"], moments=["beach_island"],
                        liked_notes=["vanilla"], disliked_notes=["oud"])
    en = [c.label for c in main_mod.build_profile_summary(prof, "en")]
    assert en[1] == "Feel: A tropical island escape · Walking into a rooftop party"
    assert en.index(en[1]) < min(i for i, l in enumerate(en) if l.startswith(("Loves:", "Avoid:")))
    ar = [c.label for c in main_mod.build_profile_summary(prof, "ar")]
    assert ar[1] == "الأجواء: هروب إلى جزيرة استوائية · أدخل حفلة راقية على السطح"
    assert not [c for c in main_mod.build_profile_summary(TasteProfile(liked_notes=["rose"]), "en") if c.id == "feel"]


def test_quiz_endpoints_stay_backward_compatible(none_client):
    sess = none_client.post("/api/session", json={"lang": "en"}).json()
    for q in sess["quiz"]:
        for o in q["options"]:
            assert {"id", "label"} <= set(o)
            assert o.get("caption") is None and o.get("motif") is None and o.get("family") is None
    r = none_client.post("/api/quiz", json={"session_id": sess["session_id"], "answers": {
        "liked_notes": ["vanilla"], "mood": "cozy", "strength": "3", "budget_aed": "400"}}).json()
    assert len(r["picks"]) == 3
    assert r["profile"]["scenarios"] == [] and r["profile"]["moments"] == []
    from app.schemas import Chip, TasteProfile
    assert Chip(id="x", label="X").model_dump() == {"id": "x", "label": "X", "caption": None, "motif": None,
                                                    "family": None}
    assert TasteProfile(**{"liked_notes": ["rose"]}).scenarios == []  # stored profiles without the new keys load
