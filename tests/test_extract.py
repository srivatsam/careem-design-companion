"""Unit tests for the rule-based extractor's guardrail helpers (app/agent/extract.py)."""
from __future__ import annotations

from app.agent import extract as ex


# ---------------------------------------------------------------------------------------------------------------
# Off-topic gate: season/weather words are perfume-relevant; follow-up phrases bypass the keyword gate (fix 8).
# ---------------------------------------------------------------------------------------------------------------
def test_is_off_topic_treats_season_and_weather_qualifiers_as_perfume_relevant():
    assert ex.is_off_topic("What's good for hot weather?") is False
    assert ex.is_off_topic("Something for a humid summer") is False
    assert ex.is_off_topic("Best scent for this season") is False


def test_is_off_topic_still_declines_plain_weather_or_other_off_topic_questions():
    assert ex.is_off_topic("What's the weather tomorrow?") is True
    assert ex.is_off_topic("What's the latest football score?") is True
    assert ex.is_off_topic("Tell me a python recipe") is True


def test_refers_to_shown_picks_matches_follow_up_phrases():
    assert ex.refers_to_shown_picks("Compare the first two") is True
    assert ex.refers_to_shown_picks("which one is better") is True
    assert ex.refers_to_shown_picks("I'll take these") is True
    assert ex.refers_to_shown_picks("What's the weather tomorrow?") is False


# ---------------------------------------------------------------------------------------------------------------
# Ambiguous anchor triggers ("what is X", "tell me about X") vs. general-knowledge questions (fix 11).
# ---------------------------------------------------------------------------------------------------------------
def test_anchor_needs_confirmation_for_general_knowledge_question():
    assert ex.anchor_needs_confirmation("What is the capital of France?") is True


def test_anchor_needs_confirmation_false_with_a_perfume_cue():
    assert ex.anchor_needs_confirmation("Tell me about Moonlight Oud 99") is False
    assert ex.anchor_needs_confirmation("What is this fragrance called?") is False


def test_anchor_needs_confirmation_false_for_non_ambiguous_triggers():
    # "like"/"similar to"/... are inherently about a perfume in this product; never gated.
    assert ex.anchor_needs_confirmation("I like Baccarat Rouge 540") is False


def test_anchor_needs_confirmation_false_without_any_anchor_match():
    assert ex.anchor_needs_confirmation("I want something fresh for summer") is False


def test_extract_profile_still_extracts_the_ambiguous_candidate_for_downstream_catalogue_lookup():
    # extract.py has no catalogue access, so it still extracts the raw candidate; callers with catalogue
    # access decide whether to trust it (see anchor_needs_confirmation + main.py's resolve_anchor).
    p = ex.extract_profile("What is the capital of France?")
    assert p.anchor_perfume == "capital of France"
