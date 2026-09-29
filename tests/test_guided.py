""""Guided match": an AI-interview quiz where each question and its quick replies adapt to what the shopper
already said. Covers the new /api/guide/start and /api/guide/finish endpoints, the 5-question cap, the
rule-based fallback when the model is unavailable, and quick_replies sanitising in the agent layer."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient


def _make_client(tmp_path, llm_provider: str):
    import importlib
    import os

    os.environ["LLM_PROVIDER"] = llm_provider
    os.environ["DATABASE_PATH"] = str(tmp_path / f"guided_{llm_provider}.db")
    from app.config import settings
    settings.database_path = os.environ["DATABASE_PATH"]
    settings.llm_provider = llm_provider
    settings.brand_filter = ""
    from app.data.db import Database
    from app.pipeline.importer import import_csv
    import_csv("data/seed/seed_catalogue.csv", "seed", "unverified", replace=True, db=Database(settings.database_path))
    from app.agent import recommender
    recommender.set_catalogue(None)
    import app.main as main
    importlib.reload(main)
    return main, TestClient(main.app)


@pytest.fixture()
def mock_client(tmp_path_factory):
    _, client = _make_client(tmp_path_factory.mktemp("mock"), "mock")
    return client


@pytest.fixture()
def none_client(tmp_path_factory):
    _, client = _make_client(tmp_path_factory.mktemp("none"), "none")
    return client


def _new_session(client, lang="en"):
    return client.post("/api/session", json={"lang": lang}).json()["session_id"]


def _answer_for_and_skip_scenarios(client, sid, who="For me"):
    """Q1, then skipping the instant scenario step: the rest of the interview runs exactly as it did before
    scenarios existed. Returns the reply to the skip (the first model-written or rule-based question)."""
    r = client.post("/api/chat", json={"session_id": sid, "message": who}).json()
    assert r["next_question"]["topic"] == "scenario"
    return client.post("/api/chat", json={"session_id": sid, "message": "Skip"}).json()


# ---------------------------------------------------------------------------------------------------------------
# Guided start: the first question is instant (id "guided_for"), no model call needed.
# ---------------------------------------------------------------------------------------------------------------
def test_guided_start_returns_the_first_question_instantly(none_client):
    sid = _new_session(none_client)
    r = none_client.post("/api/guide/start", json={"session_id": sid}).json()
    assert r["guided"] is True
    assert not r["picks"]
    q = r["next_question"]
    assert q["id"] == "guided_for"
    assert q["index"] == 1 and q["max_index"] == 5
    assert len(q["options"]) >= 3
    assert not q["multi"]


def test_guided_start_is_localized_to_arabic(none_client):
    sid = _new_session(none_client, lang="ar")
    r = none_client.post("/api/guide/start", json={"session_id": sid, "lang": "ar"}).json()
    q = r["next_question"]
    assert any("؀" <= ch <= "ۿ" for ch in q["question"])
    assert all(any("؀" <= ch <= "ۿ" for ch in o["label"]) for o in q["options"])


# ---------------------------------------------------------------------------------------------------------------
# Adaptive question generation via the mock model: gift vs self branches, progress numbers, quick replies.
# ---------------------------------------------------------------------------------------------------------------
def test_guided_gift_branch_asks_about_the_recipient(mock_client):
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "A gift for her"}).json()
    assert r["guided"] is True
    q = r["next_question"]
    # Q2 is the instant scenario step, worded for the recipient.
    assert q["topic"] == "scenario" and q["index"] == 2 and "her" in q["question"]
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "Skip"}).json()
    q = r["next_question"]
    assert q is not None and q["index"] == 3 and q["max_index"] == 5
    assert 2 <= len(q["options"]) <= 6
    assert all(len(o["label"]) <= 40 for o in q["options"])


def test_guided_self_branch_asks_about_occasion_or_notes(mock_client):
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"}).json()
    assert r["guided"] is True
    assert r["next_question"] is not None


def test_guided_finishes_early_once_it_has_two_strong_signals(mock_client):
    """Fix (problem 4): once the gate is satisfied the interview stops asking -- the only question it still
    asks is budget, as the last one, because budget is a hard filter it cannot guess."""
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "A gift for her"})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "Romantic"})
    budget_turn = mock_client.post("/api/chat", json={"session_id": sid, "message": "Vanilla, Rose"}).json()
    assert not budget_turn["picks"]
    assert budget_turn["next_question"]["topic"] == "budget"

    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "Under AED 300"}).json()
    assert len(r["picks"]) == 3
    assert r["guided"] is True
    assert r["next_question"] is None
    # "what I learned" summary tags, built from the taste profile the interview collected.
    labels = [c["label"] for c in r["profile_summary"]]
    assert any(lbl.startswith("For:") for lbl in labels)
    assert any(lbl.startswith("Loves:") for lbl in labels)
    assert any(lbl.startswith("Budget:") for lbl in labels)


# ---------------------------------------------------------------------------------------------------------------
# The 5-question cap is enforced server-side, regardless of what the model wants to do.
# ---------------------------------------------------------------------------------------------------------------
def test_guided_never_asks_more_than_five_questions(mock_client):
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    seen_indexes = []
    picks_len = 0
    for _ in range(6):
        r = mock_client.post("/api/chat", json={"session_id": sid, "message": "Skip this question"}).json()
        if r["guided"] and r["next_question"]:
            seen_indexes.append(r["next_question"]["index"])
        if r["picks"]:
            picks_len = len(r["picks"])
            break
    assert max(seen_indexes) <= 5
    assert picks_len == 3  # the cap forced a recommendation


def test_guided_never_asks_more_than_five_questions_in_fallback_mode(none_client):
    sid = _new_session(none_client)
    none_client.post("/api/guide/start", json={"session_id": sid})
    none_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    seen_indexes = []
    picks_len = 0
    for _ in range(6):
        r = none_client.post("/api/chat", json={"session_id": sid, "message": "Skip this question"}).json()
        if r["guided"] and r["next_question"]:
            seen_indexes.append(r["next_question"]["index"])
        if r["picks"]:
            picks_len = len(r["picks"])
            break
    assert max(seen_indexes) <= 5
    assert picks_len == 3
    # A skipped question is asked once and never repeated.
    assert len(seen_indexes) == len(set(seen_indexes))


# ---------------------------------------------------------------------------------------------------------------
# "Show my picks now": always available from question 2 onward, produces picks from whatever is known so far.
# ---------------------------------------------------------------------------------------------------------------
def test_show_my_picks_now_finishes_from_partial_answers(mock_client):
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    r = mock_client.post("/api/guide/finish", json={"session_id": sid}).json()
    assert len(r["picks"]) == 3
    assert r["guided"] is True
    # The session leaves guided mode: a later chat message is answered normally, not as another question.
    r2 = mock_client.post("/api/chat", json={"session_id": sid, "message": "fresh citrus scent"}).json()
    assert r2["guided"] is False


# ---------------------------------------------------------------------------------------------------------------
# Fallback: with the model unavailable, guided match still completes using the rule-based question set.
# ---------------------------------------------------------------------------------------------------------------
def test_guided_completes_with_rule_based_questions_when_llm_disabled(none_client):
    sid = _new_session(none_client)
    r = none_client.post("/api/guide/start", json={"session_id": sid}).json()
    assert r["next_question"]["id"] == "guided_for"
    r = _answer_for_and_skip_scenarios(none_client, sid)
    assert r["next_question"] is not None
    assert r["next_question"]["id"] in ("liked_notes", "disliked_notes", "mood", "budget")


def test_guided_falls_back_when_the_agent_run_errors_mid_interview(mock_client, monkeypatch):
    import sys
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})

    main_mod = sys.modules["app.main"]

    async def boom(ctx, text, history):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", boom)
    r = main_mod.__dict__  # no-op to keep flake quiet
    resp = mock_client.post("/api/chat", json={"session_id": sid, "message": "vanilla"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["next_question"] is not None or body["picks"]


# ---------------------------------------------------------------------------------------------------------------
# quick_replies sanitising in the agent layer: strip, dedupe, cap count and length, plain text only.
# ---------------------------------------------------------------------------------------------------------------
def test_sanitise_quick_replies_caps_count_length_and_dedupes():
    from app.agent.llm_agent import sanitise_quick_replies

    raw = ["Vanilla", " vanilla ", "Oud", "<script>Rose</script>", "A" * 100] + [f"opt{i}" for i in range(10)]
    out = sanitise_quick_replies(raw)
    assert len(out) <= 6
    assert "Vanilla" in out and "vanilla " not in out  # deduped case-insensitively, original casing kept
    assert not any("<" in o or ">" in o for o in out)
    assert all(len(o) <= 40 for o in out)


def test_sanitise_ask_reason_strips_and_caps():
    from app.agent.llm_agent import sanitise_ask_reason

    assert sanitise_ask_reason(None) is None
    assert sanitise_ask_reason("  ") is None
    long = "x" * 200
    out = sanitise_ask_reason(long)
    assert out is not None and len(out) <= 140


# ---------------------------------------------------------------------------------------------------------------
# Live-fix problem 1: the prompt must not contain a literal example sentence the model can parrot verbatim
# regardless of context (the observed live bug: "Great, a gift for her." echoed back for "For me" too).
# ---------------------------------------------------------------------------------------------------------------
def test_prompt_has_no_hardcoded_acknowledgement_example_to_parrot():
    from app.agent.prompts import SYSTEM_PROMPT

    assert "Great, a gift for her" not in SYSTEM_PROMPT
    assert "written fresh" in SYSTEM_PROMPT or "write fresh" in SYSTEM_PROMPT
    # The recommend-reply guidance now describes the three jobs of the reply in prose. There is no example
    # sentence at all -- neither a literal one nor a placeholder template -- so there is nothing to copy, and
    # in particular no id-shaped placeholder the model could hand back as a perfume_id.
    assert "<perfume_id>" not in SYSTEM_PROMPT
    assert not re.search(r"<[a-z_]+>", SYSTEM_PROMPT)


def test_sanitise_question_keeps_one_short_question_sentence():
    """Fix: `AgentOutput.question` must end up as ONE short question sentence, even when the model wrote a
    long, rambling reply-shaped question (the observed live bug) -- keep only the final sentence that ends
    with a question mark, in English or Arabic."""
    from app.agent.llm_agent import sanitise_question

    assert sanitise_question(None) is None
    assert sanitise_question("   ") is None

    multi = "Great, noted! What occasion is it for?"
    assert sanitise_question(multi) == "What occasion is it for?"

    long_no_mark = ("To help you best, could you tell me what kind of occasions you want the perfume for. "
                    "For example, everyday wear, special events, or work.")
    out = sanitise_question(long_no_mark)
    assert out is not None and len(out) <= 120 and out != long_no_mark

    arabic = "تم، جيد. ما المناسبة؟"
    assert sanitise_question(arabic) == "ما المناسبة؟"

    capped = "x" * 200 + "?"
    out = sanitise_question(capped)
    assert out is not None and len(out) <= 120


def test_next_question_uses_the_dedicated_question_field_not_reply(mock_client, monkeypatch):
    """Fix: the server must build next_question.question from AgentOutput.question, not from `reply` (the
    observed live bug: `reply` and `next_question.text` were the same long text)."""
    import sys

    sid = _new_session(mock_client)
    main_mod = sys.modules["app.main"]
    from app.agent.llm_agent import AgentOutput, AgentRunResult
    from app.schemas import TasteProfile

    async def fake_run_agent(ctx, text, history):
        out = AgentOutput(reply="Great, noted.", question="What occasion is it for?", intent="chat",
                          quick_replies=["Everyday", "Work", "Evening"])
        return AgentRunResult(output=out, seen_ids=set(), tool_calls=[], profile=TasteProfile())

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "hello"}).json()
    assert r["reply"] == "Great, noted."
    assert r["next_question"]["question"] == "What occasion is it for?"
    assert r["next_question"]["question"] != r["reply"]


def test_ground_drops_unsanitary_quick_replies(mock_client):
    import asyncio
    import sys

    from app.agent.llm_agent import AgentContext, AgentOutput, ground
    from app.data.db import Database
    from app.schemas import TasteProfile

    main_mod = sys.modules["app.main"]
    ctx = AgentContext(session_id="s_qr", language="en", profile=TasteProfile(), db=Database(main_mod.db.path),
                       catalogue=main_mod.catalogue)
    out = AgentOutput(reply="q", intent="chat", quick_replies=["A", "a", "B", "  C  ", "D", "E", "F", "G"], multi_select=True)
    grounded = ground(out, ctx)
    assert len(grounded.quick_replies) <= 6
    assert grounded.quick_replies == list(dict.fromkeys(grounded.quick_replies))


# ---------------------------------------------------------------------------------------------------------------
# /api/quiz keeps working for the cached floating widget (backward compatibility).
# ---------------------------------------------------------------------------------------------------------------
def test_legacy_quiz_endpoint_still_works(none_client):
    sid = _new_session(none_client)
    r = none_client.post("/api/quiz", json={"session_id": sid, "answers": {
        "liked_notes": ["vanilla"], "disliked_notes": ["rose"], "mood": "cozy", "strength": "4", "budget_aed": "300"}}).json()
    assert len(r["picks"]) == 3


def test_session_reset_clears_taste_and_guided_progress_but_keeps_the_session(mock_client):
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "A gift for her"})
    r = mock_client.post("/api/session/reset", json={"session_id": sid})
    assert r.status_code == 200 and r.json()["session_id"] == sid
    # A new guided run starts from the first question again, with nothing carried over.
    d = mock_client.post("/api/guide/start", json={"session_id": sid}).json()
    assert d["guided"] is True and d["next_question"]["id"] == "guided_for"
    assert d["next_question"]["index"] == 1
    assert not d.get("profile_summary")


# ---------------------------------------------------------------------------------------------------------------
# Fix 1: guided match must not recommend right after "who is this for?" alone -- gender/recipient never counts
# as a taste signal, and at least 2 questions beyond Q1 must be answered before recommending (unless the
# shopper asks for picks directly, or the 5-question cap is reached).
# ---------------------------------------------------------------------------------------------------------------
def test_guided_signal_count_excludes_gender_and_unresolved_anchor():
    from app.schemas import TasteProfile

    assert TasteProfile(gender="women", guided_for="gift_her").guided_signal_count() == 0
    assert TasteProfile(liked_notes=["vanilla"], moods=["cozy"]).guided_signal_count() == 2
    assert TasteProfile(anchor_perfume="Sauvage").guided_signal_count() == 0  # not yet resolved in the catalogue
    assert TasteProfile(anchor_perfume="Sauvage", anchor_perfume_id="p1").guided_signal_count() == 1


def test_guided_should_recommend_gate(none_client):
    """Exercises app.main.guided_should_recommend directly against the scenarios from the fix."""
    import sys

    from app.schemas import TasteProfile

    main_mod = sys.modules["app.main"]
    weak = TasteProfile(guided_for="gift_her")
    strong = TasteProfile(liked_notes=["vanilla"], moods=["cozy"])
    # "Who is this for?" alone, right after Q1 (0 questions answered beyond it): never recommend.
    assert main_mod.guided_should_recommend(weak, 0, 2, "A gift for her") is False
    # 2 strong signals AND 2 questions answered beyond Q1: recommend.
    assert main_mod.guided_should_recommend(strong, 2, 4, "Vanilla, Rose") is True
    # 2 strong signals but only 1 question answered beyond Q1: still too early.
    assert main_mod.guided_should_recommend(strong, 1, 3, "Vanilla, Rose") is False
    # The shopper directly asking for picks always short-circuits the gate.
    assert main_mod.guided_should_recommend(weak, 0, 2, "Show my picks now") is True
    # The 5-question cap always short-circuits the gate too.
    assert main_mod.guided_should_recommend(weak, 0, 6, "Skip") is True


def test_guided_holds_premature_picks_from_the_model(mock_client, monkeypatch):
    """Reproduces the live bug (Flow 1): the model recommends right after "who is this for?" with only a
    gender signal. The server must hold those picks and ask another question instead."""
    import sys

    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})

    main_mod = sys.modules["app.main"]
    from app.schemas import AgentReply, TasteProfile

    async def premature_llm_chat(s, text, lang, guided=None):
        ids = main_mod.catalogue.ids[:3]
        picks = [main_mod.card(main_mod.catalogue.get(pid), lang) for pid in ids]
        return AgentReply(session_id=s["session_id"], language=lang, reply="Here are 3 picks for you.",
                          picks=picks, intent="recommend", profile=TasteProfile(guided_for="gift_her"), guided=True)

    monkeypatch.setattr(main_mod, "llm_chat", premature_llm_chat)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "A gift for her"}).json()
    assert not r["picks"]
    assert r["guided"] is True
    assert r["next_question"] is not None


# ---------------------------------------------------------------------------------------------------------------
# Fix 3: a named perfume the profile has already resolved (an "anchor") is handed to the LLM agent as grounded
# real facts, so the model can describe it correctly even on a turn where it doesn't re-call get_perfume.
# ---------------------------------------------------------------------------------------------------------------
def test_llm_chat_grounds_anchor_perfume_facts_into_agent_context(mock_client, monkeypatch):
    import sys

    sid = _new_session(mock_client)
    main_mod = sys.modules["app.main"]
    captured = {}
    real_run_agent = main_mod.llm_agent.run_agent

    async def spy(ctx, text, history):
        captured["ctx"] = ctx
        return await real_run_agent(ctx, text, history)

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", spy)
    mock_client.post("/api/chat", json={"session_id": sid, "message": "Something like Aventus"})
    ctx = captured["ctx"]
    assert ctx.anchor_context is not None
    assert ctx.anchor_context["name"] == "Aventus"
    assert ctx.anchor_context["family"]
    assert ctx.anchor_context["perfume_id"] in ctx.seen_ids


# ---------------------------------------------------------------------------------------------------------------
# Fix 4: a server-side safety net swaps a final pick when 2 or more of the 3 share a brand.
# ---------------------------------------------------------------------------------------------------------------
def test_swap_duplicate_brand_picks_keeps_at_most_one_pick_per_brand(mock_client):
    import sys

    main_mod = sys.modules["app.main"]
    from app.schemas import TasteProfile

    cat = main_mod.catalogue
    dior_rows = [p for p in cat.perfumes.values() if p["brand_name"] == "Dior"]
    assert len(dior_rows) >= 2
    other = next(p for p in cat.perfumes.values() if p["brand_name"] != "Dior")
    picks = [main_mod.card(dior_rows[0], "en"), main_mod.card(dior_rows[1], "en"), main_mod.card(other, "en")]
    pool = [{"perfume": p, "score": 0.5} for p in cat.perfumes.values()]

    out = main_mod.swap_duplicate_brand_picks(picks, TasteProfile(), "en", pool, seen_ids=set())
    brands = [p.brand for p in out]
    counts = {b: brands.count(b) for b in set(brands)}
    assert all(c <= 1 for c in counts.values()), brands


def test_swap_duplicate_brand_picks_leaves_already_diverse_picks_alone(mock_client):
    import sys

    main_mod = sys.modules["app.main"]
    from app.schemas import TasteProfile

    cat = main_mod.catalogue
    rows = []
    seen_brands = set()
    for p in cat.perfumes.values():
        if p["brand_name"] not in seen_brands:
            rows.append(p)
            seen_brands.add(p["brand_name"])
        if len(rows) == 3:
            break
    picks = [main_mod.card(p, "en") for p in rows]
    pool = [{"perfume": p, "score": 0.5} for p in cat.perfumes.values()]

    out = main_mod.swap_duplicate_brand_picks(picks, TasteProfile(), "en", pool, seen_ids=set())
    assert [p.perfume_id for p in out] == [p.perfume_id for p in picks]


def test_llm_chat_swaps_out_a_duplicate_brand_final_pick(mock_client, monkeypatch):
    """Reproduces the live bug (Flow 2's picks): 2 of 3 final picks sharing a brand get diversified server-side."""
    import sys

    sid = _new_session(mock_client)
    main_mod = sys.modules["app.main"]
    cat = main_mod.catalogue
    dior_rows = [p for p in cat.perfumes.values() if p["brand_name"] == "Dior"]
    other = next(p for p in cat.perfumes.values() if p["brand_name"] != "Dior")
    from app.agent.llm_agent import AgentOutput, AgentRunResult, Pick
    from app.schemas import TasteProfile

    async def fake_run_agent(ctx, text, history):
        out = AgentOutput(reply="Here are three picks close to Sauvage.", intent="recommend", picks=[
            Pick(perfume_id=dior_rows[0]["perfume_id"], reason="r1"),
            Pick(perfume_id=dior_rows[1]["perfume_id"], reason="r2"),
            Pick(perfume_id=other["perfume_id"], reason="r3"),
        ])
        seen = {dior_rows[0]["perfume_id"], dior_rows[1]["perfume_id"], other["perfume_id"]}
        return AgentRunResult(output=out, seen_ids=seen, tool_calls=["search_perfumes"], profile=TasteProfile())

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "something fresh"}).json()
    brands = [p["brand"] for p in r["picks"]]
    assert len(brands) == 3
    counts = {b: brands.count(b) for b in set(brands)}
    assert all(c <= 1 for c in counts.values()), brands


# ---------------------------------------------------------------------------------------------------------------
# Live-fix problem 2: reply text must always agree with the final picks (root cause: the model's own `reply`
# can name a perfume that never made it into its structured `picks`, or the server can change the picks
# relative to what the model chose -- either way the cards and the words must match), and the "something like
# X" variety rule (at most one pick from the anchor's brand, never the anchor itself) must hold unconditionally.
# ---------------------------------------------------------------------------------------------------------------
def test_template_reply_for_picks_names_the_first_pick(mock_client):
    import sys

    main_mod = sys.modules["app.main"]
    from app.schemas import TasteProfile

    cat = main_mod.catalogue
    row = next(p for p in cat.perfumes.values() if len(p["name"]) >= 5)
    pick = main_mod.card(row, "en")

    out = main_mod.template_reply_for_picks([pick], TasteProfile(), "en")
    assert pick.name in out and pick.brand in out

    anchor_out = main_mod.template_reply_for_picks([pick], TasteProfile(anchor_perfume="Dior Sauvage"), "en")
    assert "Dior Sauvage" in anchor_out and pick.name in anchor_out


def test_mentions_offpick_perfume_detects_a_named_perfume_outside_the_allowed_set(mock_client):
    import sys

    main_mod = sys.modules["app.main"]
    cat = main_mod.catalogue
    row = next(p for p in cat.perfumes.values() if len(p["name"]) >= 5)
    sentence = f"I would start with {row['name']} by {row['brand_name']}."

    assert main_mod._mentions_offpick_perfume(sentence, set()) is True
    assert main_mod._mentions_offpick_perfume(sentence, {row["perfume_id"]}) is False
    assert main_mod._mentions_offpick_perfume("A short, generic reply with no perfume name.", set()) is False
    assert main_mod._mentions_offpick_perfume("", set()) is False


def test_llm_chat_regenerates_reply_when_it_names_a_perfume_outside_the_final_picks(mock_client, monkeypatch):
    """Reproduces Flow B's mismatch: the model's `reply` names a perfume ("Bleu de Chanel") that is not among
    its own structured `picks` -- the server must replace the reply with a safe template naming the actual
    first pick, regardless of why the mismatch happened."""
    import sys

    sid = _new_session(mock_client)
    main_mod = sys.modules["app.main"]
    cat = main_mod.catalogue
    from app.agent.llm_agent import AgentOutput, AgentRunResult, Pick
    from app.schemas import TasteProfile

    seen_brands: set[str] = set()
    rows = []
    for p in cat.perfumes.values():
        if p["brand_name"] not in seen_brands and len(p["name"]) >= 5:
            rows.append(p)
            seen_brands.add(p["brand_name"])
        if len(rows) == 3:
            break
    off_pick = next(p for p in cat.perfumes.values()
                    if p["perfume_id"] not in {r["perfume_id"] for r in rows} and len(p["name"]) >= 5)

    async def fake_run_agent(ctx, text, history):
        out = AgentOutput(
            reply=f"I would start with {off_pick['name']} by {off_pick['brand_name']}: it is light and fresh.",
            intent="recommend", picks=[Pick(perfume_id=r["perfume_id"], reason="fits") for r in rows])
        return AgentRunResult(output=out, seen_ids={r["perfume_id"] for r in rows}, tool_calls=["search_perfumes"],
                              profile=TasteProfile())

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "something fresh"}).json()
    assert off_pick["name"] not in r["reply"]
    expected = main_mod.template_reply_for_picks([main_mod.card(rows[0], "en")], TasteProfile(), "en")
    assert r["reply"] == expected
    assert {p["perfume_id"] for p in r["picks"]} == {r_["perfume_id"] for r_ in rows}


def test_llm_chat_tops_up_to_three_picks_when_all_model_picks_fail_constraints(mock_client, monkeypatch):
    """Root cause confirmed live (atelier-noor.azurewebsites.net, "Lighter" turn of Flow B): the model's own 3
    picks can all fail catalogue.passes() after a just-updated constraint (there, strength), leaving intent=
    "recommend" with an EMPTY picks list, a reply claiming "these three picks...", and a redundant
    next_question all at once. The server must always finish the recommendation with 3 real picks instead."""
    import sys

    sid = _new_session(mock_client)
    main_mod = sys.modules["app.main"]
    cat = main_mod.catalogue
    from app.agent.llm_agent import AgentOutput, AgentRunResult, Pick
    from app.schemas import TasteProfile

    bad_picks = [p for p in cat.perfumes.values() if p.get("price_aed") and p["price_aed"] > 200][:3]
    assert len(bad_picks) == 3
    assert sum(1 for p in cat.perfumes.values() if p.get("price_aed") and p["price_aed"] <= 200) >= 3

    async def fake_run_agent(ctx, text, history):
        out = AgentOutput(reply="These three picks share a fresh and airy character.", intent="recommend",
                          picks=[Pick(perfume_id=p["perfume_id"], reason="r") for p in bad_picks],
                          quick_replies=["Everyday", "Work"], question="What occasion is it for?", topic="occasion")
        return AgentRunResult(output=out, seen_ids={p["perfume_id"] for p in bad_picks}, tool_calls=["search_perfumes"],
                              profile=TasteProfile())

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "under AED 200 please"}).json()
    assert len(r["picks"]) == 3
    assert r["next_question"] is None
    assert "these three picks" not in r["reply"].lower()


def test_llm_chat_diversifies_anchor_brand_final_picks_and_excludes_the_anchor_itself(mock_client, monkeypatch):
    """Reproduces Flow B's final turn: the model recommends the anchor itself plus two of its own brand's
    flankers ("Sauvage", "Sauvage Eau de Toilette", "Sauvage Very Cool Spray" on live). The server must drop
    the anchor from the picks and cap the anchor's brand at one pick, with no score-margin exception."""
    import sys

    sid = _new_session(mock_client)
    main_mod = sys.modules["app.main"]
    cat = main_mod.catalogue
    dior_rows = [p for p in cat.perfumes.values() if p["brand_name"] == "Dior"]
    assert len(dior_rows) >= 3
    anchor = dior_rows[0]
    from app.agent.llm_agent import AgentOutput, AgentRunResult, Pick
    from app.schemas import TasteProfile

    async def fake_run_agent(ctx, text, history):
        out = AgentOutput(reply="These are close to what you like.", intent="recommend", picks=[
            Pick(perfume_id=anchor["perfume_id"], reason="r0"),
            Pick(perfume_id=dior_rows[1]["perfume_id"], reason="r1"),
            Pick(perfume_id=dior_rows[2]["perfume_id"], reason="r2"),
        ])
        seen = {anchor["perfume_id"], dior_rows[1]["perfume_id"], dior_rows[2]["perfume_id"]}
        return AgentRunResult(output=out, seen_ids=seen, tool_calls=["find_similar"],
                              profile=TasteProfile(anchor_perfume=anchor["name"], anchor_perfume_id=anchor["perfume_id"]))

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": f"Something like {anchor['name']}"}).json()
    assert len(r["picks"]) == 3
    pick_ids = [p["perfume_id"] for p in r["picks"]]
    assert anchor["perfume_id"] not in pick_ids
    brands = [p["brand"] for p in r["picks"]]
    counts = {b: brands.count(b) for b in set(brands)}
    assert all(c <= 1 for c in counts.values()), brands
    assert r["reply"] != "These are close to what you like."


# ---------------------------------------------------------------------------------------------------------------
# Live-fix problem 3: only a genuine AI outage gets the "AI is resting" note and fallback_used=True. A soft
# grounding miss (the model responded, the server just distrusted its picks) falls back quietly, same as the
# "held early picks" path.
# ---------------------------------------------------------------------------------------------------------------
def test_soft_grounding_miss_falls_back_quietly_without_ai_resting_note(mock_client, monkeypatch):
    import sys

    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    main_mod = sys.modules["app.main"]
    from app.agent.llm_agent import AgentOutput, AgentRunResult
    from app.schemas import TasteProfile

    async def fake_run_agent(ctx, text, history):
        out = AgentOutput(reply="", intent="recommend", picks=[])
        return AgentRunResult(output=out, seen_ids=set(), tool_calls=["search_perfumes"],
                              grounding_failed=True, profile=TasteProfile())

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "vanilla"}).json()
    assert r["fallback_used"] is False
    assert "resting" not in r["reply"].lower()
    assert r["next_question"] is not None


def test_genuine_agent_error_still_shows_the_ai_resting_note(mock_client, monkeypatch):
    import sys

    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    main_mod = sys.modules["app.main"]

    async def boom(ctx, text, history):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", boom)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "vanilla"}).json()
    assert r["fallback_used"] is True
    assert "resting" in r["reply"].lower()


def test_held_premature_picks_path_stays_quiet_too(mock_client, monkeypatch):
    """The "held early picks" fix (problem set 1) must also never show the AI-resting note or fallback_used."""
    import sys

    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    main_mod = sys.modules["app.main"]
    from app.schemas import AgentReply, TasteProfile

    async def premature_llm_chat(s, text, lang, guided=None):
        ids = main_mod.catalogue.ids[:3]
        picks = [main_mod.card(main_mod.catalogue.get(pid), lang) for pid in ids]
        return AgentReply(session_id=s["session_id"], language=lang, reply="Here are 3 picks for you.",
                          picks=picks, intent="recommend", profile=TasteProfile(guided_for="gift_her"), guided=True)

    monkeypatch.setattr(main_mod, "llm_chat", premature_llm_chat)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "A gift for her"}).json()
    assert r["fallback_used"] is False
    assert "resting" not in r["reply"].lower()


# ---------------------------------------------------------------------------------------------------------------
# Live-fix problem 4: a model-authored question must not repeat a topic already covered, and a question turn's
# reply must stay to a short acknowledgement (no recommendations, no perfume descriptions, no repeated question).
# ---------------------------------------------------------------------------------------------------------------
def test_guided_topic_repeat_is_replaced_with_a_rule_based_question_on_a_new_topic(mock_client, monkeypatch):
    import sys

    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    main_mod = sys.modules["app.main"]
    from app.agent.llm_agent import AgentOutput, AgentRunResult
    from app.schemas import TasteProfile

    async def fake_run_agent(ctx, text, history):
        out = AgentOutput(reply="", question="What occasion is it for?", topic="occasion", intent="chat",
                          quick_replies=["Everyday", "Work", "Evening"])
        return AgentRunResult(output=out, seen_ids=set(), tool_calls=[], profile=TasteProfile(guided_for="self"))

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    r1 = _answer_for_and_skip_scenarios(mock_client, sid)
    assert r1["next_question"]["topic"] == "occasion"

    r2 = mock_client.post("/api/chat", json={"session_id": sid, "message": "Everyday"}).json()
    # The model tried to ask about "occasion" again: the server must swap in a different, unasked topic.
    assert r2["next_question"] is not None
    assert r2["next_question"]["topic"] != "occasion"
    assert r2["next_question"]["id"] in ("liked_notes", "disliked_notes", "budget")


def test_question_turn_reply_drops_perfume_prose(mock_client, monkeypatch):
    """Reproduces Flow A turn 3 / Flow B turn 3: the model recommends or describes a perfume in `reply` on a
    turn with no picks. That prose must never reach the shopper.

    The server used to blank the whole reply once it ran past a length limit, which also threw away real
    answers (a "how do these compare?" follow-up came back as an empty bubble). It now drops only the
    sentences that name a perfume the cards do not show and keeps the rest of the advisor's own words."""
    import sys

    sid = _new_session(mock_client)
    main_mod = sys.modules["app.main"]
    from app.agent.llm_agent import AgentOutput, AgentRunResult
    from app.schemas import TasteProfile

    long_reply = ("Soft floral scents for a gift share a gentle, elegant character. I would start with "
                 "L'Eau d'Issey by Issey Miyake: it is a classic soft floral with a light strength that suits "
                 "your preference. What occasion is this gift for?")

    async def fake_run_agent(ctx, text, history):
        out = AgentOutput(reply=long_reply, question="What occasion is this gift for?", topic="occasion",
                          intent="chat", quick_replies=["Everyday", "Work", "Evening"])
        return AgentRunResult(output=out, seen_ids=set(), tool_calls=[], profile=TasteProfile())

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "Soft floral scents"}).json()
    assert "Issey" not in r["reply"] and "start with" not in r["reply"]
    assert "?" not in r["reply"]
    assert r["next_question"]["question"] == "What occasion is this gift for?"


def test_question_turn_short_clean_reply_is_kept(mock_client, monkeypatch):
    import sys

    sid = _new_session(mock_client)
    main_mod = sys.modules["app.main"]
    from app.agent.llm_agent import AgentOutput, AgentRunResult
    from app.schemas import TasteProfile

    async def fake_run_agent(ctx, text, history):
        out = AgentOutput(reply="Got it.", question="What occasion is it for?", topic="occasion", intent="chat",
                          quick_replies=["Everyday", "Work", "Evening"])
        return AgentRunResult(output=out, seen_ids=set(), tool_calls=[], profile=TasteProfile())

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "hello"}).json()
    assert r["reply"] == "Got it."
    assert r["next_question"]["question"] == "What occasion is it for?"


# =================================================================================================================
# Live-fix problem 1: an answer is interpreted against the question it actually answers.
# Reproduces the transcript: Q4 "Anything you dislike?" answered "vanilla" was stored as a LIKED note, and the
# occasion / strength / anchor answers never reached the profile at all.
# =================================================================================================================
def _dislike_pending():
    return {"topic": "disliked_scents", "id": "disliked_notes", "multi": True,
            "options": [{"id": n, "label": n} for n in ["vanilla", "oud", "rose", "musk", "jasmine", "bergamot"]]}


def _strength_pending():
    return {"topic": "strength", "id": "guided_q", "multi": False,
            "options": [{"id": "qr0", "label": "Light (1-2)"}, {"id": "qr1", "label": "Medium (3)"},
                        {"id": "qr2", "label": "Strong (4-5)"}]}


def _occasion_pending():
    return {"topic": "occasion", "id": "guided_q", "multi": False,
            "options": [{"id": "qr0", "label": "Everyday"}, {"id": "qr1", "label": "Special events"},
                        {"id": "qr2", "label": "Work"}, {"id": "qr3", "label": "Casual"},
                        {"id": "qr4", "label": "Evening"}]}


def _budget_pending():
    return {"topic": "budget", "id": "budget", "multi": False,
            "options": [{"id": "200", "label": "Under AED 200"}, {"id": "500", "label": "Under AED 500"},
                        {"id": "0", "label": "No limit"}]}


def test_dislike_answer_lands_in_dislikes_not_likes():
    """The exact live bug: "vanilla" answering "Anything you dislike?" must never become a liked note."""
    from app.agent.extract import interpret_guided_answer

    a = interpret_guided_answer("vanilla", _dislike_pending())
    assert a.disliked_notes == ["vanilla"]
    assert a.liked_notes == []
    # Multi-select answers arrive comma-separated, and an explicit negation means the same thing here.
    a = interpret_guided_answer("vanilla, no musk", _dislike_pending())
    assert set(a.disliked_notes) == {"vanilla", "musk"}
    assert a.liked_notes == []
    # "Not too sweet" is a family to avoid, not a note.
    assert "gourmand" in interpret_guided_answer("Not too sweet", _dislike_pending()).avoid_families


def test_liked_answer_keeps_an_explicit_negation_as_a_dislike():
    from app.agent.extract import interpret_guided_answer

    pending = {"topic": "liked_scents", "id": "liked_notes", "multi": True,
               "options": [{"id": "vanilla", "label": "Vanilla"}, {"id": "oud", "label": "Oud"}]}
    a = interpret_guided_answer("Vanilla", pending)
    assert a.liked_notes == ["vanilla"] and a.disliked_notes == []
    a = interpret_guided_answer("no oud", pending)
    assert a.disliked_notes == ["oud"] and a.liked_notes == []


def test_strength_answers_map_to_a_level_in_both_languages():
    from app.agent.extract import interpret_guided_answer

    p = _strength_pending()
    assert interpret_guided_answer("Lighter", p).strength == 2           # the live transcript's answer
    assert interpret_guided_answer("Light (1-2)", p).strength == 2       # the option label verbatim
    assert interpret_guided_answer("Very light", p).strength == 1
    assert interpret_guided_answer("خفيف", p).strength == 2
    assert interpret_guided_answer("Medium (3)", p).strength == 3
    assert interpret_guided_answer("Moderate", p).strength == 3
    assert interpret_guided_answer("Strong (4-5)", p).strength == 4
    assert interpret_guided_answer("قوي", p).strength == 4


def test_occasion_answers_map_to_taxonomy_occasions_in_both_languages():
    from app.agent.extract import interpret_guided_answer

    p = _occasion_pending()
    assert interpret_guided_answer("Everyday", p).occasions == ["everyday"]   # the live transcript's answer
    assert interpret_guided_answer("Work", p).occasions == ["office"]
    assert interpret_guided_answer("Casual", p).occasions == ["everyday"]
    assert interpret_guided_answer("Evening", p).occasions == ["evening"]
    assert interpret_guided_answer("Special events", p).occasions == ["date"]
    assert interpret_guided_answer("يومي", p).occasions == ["everyday"]
    assert interpret_guided_answer("المساء", p).occasions == ["evening"]


def test_budget_answers_parse_numbers_ranges_and_no_limit_in_both_languages():
    from app.agent.extract import interpret_guided_answer

    p = _budget_pending()
    assert interpret_guided_answer("200-400", p).budget_aed == 400          # a range caps at its top
    assert interpret_guided_answer("Under 200", p).budget_aed == 200
    assert interpret_guided_answer("Under AED 500", p).budget_aed == 500
    assert interpret_guided_answer("أقل من 200", p).budget_aed == 200
    assert interpret_guided_answer("400 AED", p).budget_aed == 400
    assert interpret_guided_answer("No limit", p).budget_aed is None
    assert interpret_guided_answer("بدون حد", p).budget_aed is None


def test_recipient_and_skip_answers():
    from app.agent.extract import interpret_guided_answer

    recipient = {"topic": "recipient", "id": "guided_for", "multi": False,
                 "options": [{"id": "self", "label": "For me"}, {"id": "gift_her", "label": "A gift for her"}]}
    a = interpret_guided_answer("A gift for her", recipient)
    assert a.guided_for == "gift_her" and a.gender == "women"
    assert interpret_guided_answer("For me", recipient).guided_for == "self"
    # A skip stores nothing at all (the topic still counts as asked, server-side).
    skipped = interpret_guided_answer("Skip", _dislike_pending())
    assert skipped.signal_count() == 0
    assert interpret_guided_answer("Nothing to avoid", _dislike_pending()).signal_count() == 0


def test_anchor_answer_becomes_the_anchor_perfume():
    from app.agent.extract import interpret_guided_answer

    pending = {"topic": "liked_scents", "id": "liked_notes", "multi": True,
               "options": [{"id": "vanilla", "label": "Vanilla"}]}
    assert interpret_guided_answer("Something like Dior Sauvage", pending).anchor_perfume == "Dior Sauvage"
    assert interpret_guided_answer("I wear Aventus", pending).anchor_perfume == "Aventus"


def test_guided_answer_is_read_against_the_pending_question_end_to_end(none_client):
    """The whole transcript in the rule-based path: the dislike answer lands in dislikes, and the occasion,
    strength and budget answers all reach the profile."""
    sid = _new_session(none_client)
    none_client.post("/api/guide/start", json={"session_id": sid})
    r = _answer_for_and_skip_scenarios(none_client, sid)
    assert r["next_question"]["topic"] == "liked_scents"
    r = none_client.post("/api/chat", json={"session_id": sid, "message": "rose"}).json()
    assert r["profile"]["liked_notes"] == ["rose"]
    assert r["next_question"]["topic"] == "disliked_scents"
    r = none_client.post("/api/chat", json={"session_id": sid, "message": "vanilla"}).json()
    assert r["profile"]["disliked_notes"] == ["vanilla"]
    assert "vanilla" not in r["profile"]["liked_notes"]


def test_deterministic_reading_beats_the_models_profile_updates(mock_client, monkeypatch):
    """Fix: even when the model reads the answer the wrong way round (here: "vanilla" under a dislike question
    reported back as a LIKED note), the server's deterministic reading of the asked topic wins."""
    import sys

    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    main_mod = sys.modules["app.main"]
    from app.agent.llm_agent import AgentOutput, AgentRunResult
    from app.schemas import TasteProfile

    questions = iter([("disliked_scents", "Anything you dislike?"), ("budget", "What's your budget?")])

    async def fake_run_agent(ctx, text, history):
        topic, question = next(questions, ("other", "Anything else?"))
        # The model misreads the dislike answer as a like -- exactly the live failure mode.
        return AgentRunResult(output=AgentOutput(reply="", question=question, topic=topic, intent="chat",
                                                 quick_replies=["Vanilla", "Oud", "Rose"]),
                              seen_ids=set(), tool_calls=[],
                              profile=TasteProfile(guided_for="self", liked_notes=["vanilla"]))

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    r = _answer_for_and_skip_scenarios(mock_client, sid)
    assert r["next_question"]["topic"] == "disliked_scents"
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "vanilla"}).json()
    assert r["profile"]["disliked_notes"] == ["vanilla"]
    assert "vanilla" not in r["profile"]["liked_notes"]


def test_rule_based_guided_questions_carry_a_topic_and_never_echo_the_question_as_the_reply(none_client):
    """Live bug: the rule-based question turn set `reply` to a second copy of the question, and carried no
    topic, so the next answer could not be read against it."""
    sid = _new_session(none_client)
    none_client.post("/api/guide/start", json={"session_id": sid})
    for message in ("For me", "rose", "Skip"):
        r = none_client.post("/api/chat", json={"session_id": sid, "message": message}).json()
        q = r["next_question"]
        if not q:
            break
        assert q["topic"], q
        assert r["reply"] != q["question"]
        assert r["reply"] == "" or len(r["reply"]) <= 120


def test_pending_question_is_handed_to_the_model(mock_client, monkeypatch):
    """The model is told which question the message answers (llm_agent's "The shopper is answering:" line)."""
    import sys

    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    main_mod = sys.modules["app.main"]
    captured = {}
    real = main_mod.llm_agent.run_agent

    async def spy(ctx, text, history):
        captured["pending"] = ctx.pending_question
        return await real(ctx, text, history)

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", spy)
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    assert "pending" not in captured  # Q2 (the scenario cards) is instant: no model call
    mock_client.post("/api/chat", json={"session_id": sid, "message": "Skip"})
    assert captured["pending"] is not None
    assert captured["pending"]["topic"] == "scenario"
    assert captured["pending"]["question"]


def test_instructions_name_the_question_being_answered():
    from app.agent.llm_agent import AgentContext, instructions
    from app.schemas import TasteProfile

    class _Wrapper:
        def __init__(self, ctx):
            self.context = ctx

    ctx = AgentContext(session_id="s", language="en", profile=TasteProfile(), db=None, catalogue=None,
                       guided=True, pending_question={"question": "Anything you dislike?", "topic": "disliked_scents"})
    text = instructions(_Wrapper(ctx), None)
    assert "The shopper is answering:" in text
    assert "Anything you dislike?" in text and "disliked_scents" in text


# =================================================================================================================
# Live-fix problem 2: the summary tags show every known signal, localised through the taxonomy.
# =================================================================================================================
def test_profile_summary_covers_every_signal_in_english(none_client):
    import sys

    main_mod = sys.modules["app.main"]
    from app.schemas import TasteProfile

    prof = TasteProfile(guided_for="self", liked_notes=["vanilla"], families=["floral"], disliked_notes=["oud"],
                        avoid_families=["gourmand"], anchor_perfume="Sauvage", occasions=["everyday"],
                        moods=["cozy"], strength=2, budget_aed=300)
    labels = [c["label"] for c in [chip.model_dump() for chip in main_mod.build_profile_summary(prof, "en")]]
    assert any(l.startswith("For:") for l in labels)
    assert any(l.startswith("Loves:") and "vanilla" in l and "Floral" in l for l in labels)
    assert any(l.startswith("Avoid:") and "oud" in l for l in labels)
    assert any(l.startswith("Like:") and "Sauvage" in l for l in labels)
    assert any(l.startswith("Occasion:") and "Everyday" in l for l in labels)
    assert any(l.startswith("Strength:") and "Light" in l for l in labels)
    assert any(l.startswith("Budget:") and "300" in l for l in labels)


def test_profile_summary_is_fully_localised_in_arabic(none_client):
    """Live bug: the Arabic run showed an untranslated "يحب: floral" and the stilted "لِـ:" recipient label."""
    import sys

    main_mod = sys.modules["app.main"]
    from app.schemas import TasteProfile

    prof = TasteProfile(guided_for="gift_her", families=["floral"], liked_notes=["rose"], disliked_notes=["oud"],
                        occasions=["everyday"], moods=["cozy"], strength=2, budget_aed=200)
    labels = [chip.label for chip in main_mod.build_profile_summary(prof, "ar")]
    joined = " ".join(labels)
    assert "floral" not in joined and "everyday" not in joined and "rose" not in joined
    assert "زهري" in joined and "يومي" in joined and "خفيف" in joined
    assert any(l.startswith("لمن:") for l in labels)
    assert "لِـ" not in joined
    # Every value is Arabic text, not a raw taxonomy key.
    assert all(any("؀" <= ch <= "ۿ" for ch in l) for l in labels)


# =================================================================================================================
# Live-fix problem 3: anchor and variety on every path that produces final picks.
# =================================================================================================================
def test_line_key_groups_flankers_of_one_product_line():
    from app.agent.recommender import line_key

    assert line_key("Sauvage") == line_key("Sauvage Eau de Toilette") == line_key("Sauvage Elixir") == "sauvage"
    assert line_key("Guido Maria Kretschmer For Him") == "guido maria kretschmer"
    assert line_key("Bleu de Chanel Eau de Parfum") == "bleu de chanel"


def test_anchor_flanker_ids_covers_the_anchor_and_its_line(mock_client):
    """The transcript's failure: anchor "Sauvage" came back with "Sauvage Eau de Parfum" and "Sauvage Eau de
    Toilette" as two of the three picks."""
    import sys

    main_mod = sys.modules["app.main"]
    cat = main_mod.catalogue
    edt = next(p for p in cat.perfumes.values() if p["name"] == "Sauvage Eau de Toilette")
    # A second Sauvage flanker, so the pair can be exercised against the real catalogue rows.
    fake = dict(edt, perfume_id="p_fake_sauvage", name="Sauvage")
    cat.perfumes[fake["perfume_id"]] = fake
    try:
        flankers = cat.anchor_flanker_ids("p_fake_sauvage")
        assert "p_fake_sauvage" in flankers          # the anchor itself
        assert edt["perfume_id"] in flankers         # its flanker, same brand and same line
        # A ranking with that anchor never returns either of them.
        from app.schemas import TasteProfile
        prof = TasteProfile(anchor_perfume_id="p_fake_sauvage", anchor_perfume="Sauvage")
        ids = [r["perfume"]["perfume_id"] for r in cat.search(prof, None, limit=40)]
        assert edt["perfume_id"] not in ids
        assert "p_fake_sauvage" not in ids
    finally:
        cat.perfumes.pop("p_fake_sauvage", None)
        cat._flanker_cache.pop("p_fake_sauvage", None)


def test_guided_finish_excludes_the_anchor_and_keeps_one_pick_per_brand(mock_client):
    """/api/guide/finish: the anchor perfume itself is never a pick, and no brand appears twice."""
    import sys

    main_mod = sys.modules["app.main"]
    anchor = main_mod.catalogue.find_by_name("Aventus")
    assert anchor is not None

    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "Something like Aventus"})
    r = mock_client.post("/api/guide/finish", json={"session_id": sid}).json()
    assert len(r["picks"]) == 3
    ids = [p["perfume_id"] for p in r["picks"]]
    assert anchor["perfume_id"] not in ids
    brands = [p["brand"] for p in r["picks"]]
    assert len(set(brands)) == 3, brands
    assert any(c["id"] == "like" for c in r["profile_summary"])


def test_build_results_keeps_one_pick_per_brand_on_the_refine_path(mock_client):
    """The refine / "more like" path used the raw ranking, so it could return several rows of one brand."""
    sid = _new_session(mock_client)
    first = mock_client.post("/api/chat", json={"session_id": sid, "message": "woody oud perfume"}).json()
    assert first["picks"]
    r = mock_client.post("/api/refine", json={"session_id": sid, "chip": "cheaper"}).json()
    brands = [p["brand"] for p in r["picks"]]
    assert len(set(brands)) == len(brands), brands


def test_hard_constraints_survive_the_variety_rules(mock_client):
    """Variety must never override a hard constraint: budget, dislikes and strength still hold."""
    import sys

    main_mod = sys.modules["app.main"]
    from app.schemas import TasteProfile

    prof = TasteProfile(budget_aed=300, disliked_notes=["oud"], avoid_families=["gourmand"], strength=2)
    picks = main_mod.catalogue.recommend(prof, None, k=3)["picks"]
    assert picks
    for r in picks:
        p = r["perfume"]
        assert p["price_aed"] is None or p["price_aed"] <= 300
        assert "oud" not in {n["note"] for n in p["notes"]}
        assert p["family"] != "gourmand"
        assert abs(p["strength"] - 2) <= 2


# =================================================================================================================
# Live-fix problem 4 and 5: finish early once enough is known, and let the AI write the closing turn.
# =================================================================================================================
def test_guided_finishes_in_three_or_four_questions(mock_client):
    """Target: a shopper who answers usefully is done in 3 to 4 questions, not 5."""
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    answers = ["For me", "Everyday", "Vanilla, Rose", "Under AED 500", "Skip"]
    asked = 1  # the instant "who is this for?"
    for message in answers:
        r = mock_client.post("/api/chat", json={"session_id": sid, "message": message}).json()
        if r["picks"]:
            break
        assert r["next_question"] is not None
        asked += 1
    assert r["picks"], "guided match never finished"
    assert 3 <= asked <= 4, asked


def test_budget_is_asked_last_when_the_gate_is_already_satisfied(mock_client, monkeypatch):
    """Fix: once the gate is satisfied the only remaining question is budget -- and only when it is unknown."""
    import sys

    main_mod = sys.modules["app.main"]
    from app.schemas import TasteProfile

    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "Everyday"})
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "Vanilla, Rose"}).json()
    assert not r["picks"]
    assert r["next_question"]["topic"] == "budget"
    assert r["next_question"]["id"] == "budget"

    # With a budget already known, the same gate recommends straight away instead.
    sid2 = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid2})
    mock_client.post("/api/chat", json={"session_id": sid2, "message": "For me"})
    mock_client.post("/api/chat", json={"session_id": sid2, "message": "Everyday"})
    r2 = mock_client.post("/api/chat", json={"session_id": sid2, "message": "Vanilla and rose, under AED 400"}).json()
    assert len(r2["picks"]) == 3
    assert r2["next_question"] is None


def test_forced_finish_lets_the_ai_write_the_closing_reply(mock_client, monkeypatch):
    """Fix (problem 5): on the finish path the AI writes the closing turn (a reply naming the first pick and
    per-pick reasons), instead of the generic "Here's what I learned about you" template."""
    import sys

    main_mod = sys.modules["app.main"]
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "Everyday"})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "Vanilla, Rose"})
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "Under AED 500"}).json()
    assert len(r["picks"]) == 3
    assert r["reply"] != main_mod.T["en"]["g_finished"]
    assert r["picks"][0]["name"] in r["reply"]
    assert all(p["reason"] for p in r["picks"])
    assert r["fallback_used"] is False
    assert r["profile_summary"]


def test_forced_finish_falls_back_to_the_template_when_the_ai_fails(mock_client, monkeypatch):
    import sys

    main_mod = sys.modules["app.main"]
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "Everyday"})

    async def boom(ctx, text, history):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", boom)
    r = mock_client.post("/api/guide/finish", json={"session_id": sid}).json()
    assert len(r["picks"]) == 3
    assert r["reply"].startswith(main_mod.T["en"]["g_finished"])
    assert r["guided"] is True


def test_forced_finish_tells_the_model_not_to_ask_another_question(mock_client, monkeypatch):
    import sys

    main_mod = sys.modules["app.main"]
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    captured = {}
    real = main_mod.llm_agent.run_agent

    async def spy(ctx, text, history):
        captured["force"] = ctx.force_recommend
        return await real(ctx, text, history)

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", spy)
    mock_client.post("/api/guide/finish", json={"session_id": sid})
    assert captured.get("force") is True


def test_question_turn_reply_is_never_a_second_copy_of_the_question(mock_client, monkeypatch):
    """Live bug (transcript Q4): the turn showed "Anything you dislike?" as BOTH the reply and the question."""
    import sys

    main_mod = sys.modules["app.main"]
    assert main_mod._is_same_sentence("Anything you dislike?", "Anything you dislike?") is True
    assert main_mod._is_same_sentence("Got it.", "Anything you dislike?") is False

    sid = _new_session(mock_client)
    from app.agent.llm_agent import AgentOutput, AgentRunResult
    from app.schemas import TasteProfile

    async def echoing(ctx, text, history):
        out = AgentOutput(reply="Anything you dislike?", question="Anything you dislike?",
                          topic="disliked_scents", intent="chat", quick_replies=["Vanilla", "Oud"])
        return AgentRunResult(output=out, seen_ids=set(), tool_calls=[], profile=TasteProfile())

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", echoing)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "hello"}).json()
    assert r["reply"] == ""
    assert r["next_question"]["question"] == "Anything you dislike?"


def test_an_interjection_turn_keeps_the_question_pending(mock_client, monkeypatch):
    """A mid-interview perfume lookup answers nothing: the question stays pending, so the NEXT message is still
    read against it (otherwise a dislike answer is read as a like again)."""
    import sys

    main_mod = sys.modules["app.main"]
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})

    state = {"turn": 0}
    from app.agent.llm_agent import AgentOutput, AgentRunResult
    from app.schemas import TasteProfile

    async def fake_run_agent(ctx, text, history):
        state["turn"] += 1
        if state["turn"] == 1:
            out = AgentOutput(reply="", question="Anything you dislike?", topic="disliked_scents",
                              intent="chat", quick_replies=["Vanilla", "Oud"])
        else:  # an interjection: no picks, no question
            out = AgentOutput(reply="I can't find that perfume in our catalogue.", intent="lookup")
        return AgentRunResult(output=out, seen_ids=set(), tool_calls=[], profile=TasteProfile(guided_for="self"))

    monkeypatch.setattr(main_mod.llm_agent, "run_agent", fake_run_agent)
    _answer_for_and_skip_scenarios(mock_client, sid)
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "What is Moonlight Oud 99?"}).json()
    assert not r["picks"] and r["next_question"] is None
    # The dislike question was never answered, so this answer must still be read as a dislike.
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "vanilla"}).json()
    assert r["profile"]["disliked_notes"] == ["vanilla"]
    assert "vanilla" not in r["profile"]["liked_notes"]


def test_brand_variety_has_no_score_margin_escape_hatch(mock_client):
    """Live case: two Lattafa picks survived because the runners-up scored a little lower. "At most one pick
    per brand" relaxes only when no unused brand is left, never because of a score gap."""
    import sys

    main_mod = sys.modules["app.main"]
    from app.schemas import TasteProfile

    cat = main_mod.catalogue
    dup_rows = [p for p in cat.perfumes.values() if p["brand_name"] == "Lattafa"][:2]
    assert len(dup_rows) == 2
    other = next(p for p in cat.perfumes.values() if p["brand_name"] not in ("Lattafa",))
    picks = [main_mod.card(dup_rows[0], "en"), main_mod.card(dup_rows[1], "en"), main_mod.card(other, "en")]
    # A pool where every alternative scores clearly WORSE than the duplicate picks.
    pool = [{"perfume": p, "score": 0.9 if p["brand_name"] in ("Lattafa", other["brand_name"]) else 0.1}
            for p in cat.perfumes.values()]

    out = main_mod.swap_duplicate_brand_picks(picks, TasteProfile(), "en", pool, seen_ids=set())
    brands = [p.brand for p in out]
    assert len(set(brands)) == 3, brands


def test_guided_finish_keeps_one_brand_per_pick_on_the_ai_path(mock_client):
    sid = _new_session(mock_client)
    mock_client.post("/api/guide/start", json={"session_id": sid})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "For me"})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "Everyday"})
    mock_client.post("/api/chat", json={"session_id": sid, "message": "Vanilla"})
    r = mock_client.post("/api/chat", json={"session_id": sid, "message": "Under AED 300"}).json()
    assert len(r["picks"]) == 3
    brands = [p["brand"] for p in r["picks"]]
    assert len(set(brands)) == 3, brands
    for p in r["picks"]:                       # the budget constraint survives the variety swap
        assert p["price_aed"] is None or p["price_aed"] <= 300


def test_reconcile_reply_keeps_the_advisors_words_and_drops_sentences_about_missing_perfumes(mock_client):
    import app.main as main
    from app.agent.cards import card
    cat = main.catalogue
    ids = [pid for pid in cat.ids if len(cat.get(pid)["name"]) >= 6][:4]
    picks = [card(cat.get(pid), "en") for pid in ids[:3]]
    gone = cat.get(ids[3])["name"]
    reply = (f"For a fresh office scent these stay light and clean. I would start with {gone}: it is the freshest. "
             "Would you like something longer lasting?")
    out = main.reconcile_reply_with_picks(reply, picks, set(ids[:3]), [gone], main.TasteProfile(), "en")
    assert out.startswith("For a fresh office scent these stay light and clean.")
    assert gone not in out
    assert picks[0].name in out
    assert out.rstrip().endswith("Would you like something longer lasting?")
