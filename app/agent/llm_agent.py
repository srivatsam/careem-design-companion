"""LLM agent layer: an OpenAI Agents SDK agent (Azure OpenAI or the offline MockModel) with catalogue tools,
structured output, grounding checks and a consent-gated wishlist action.

The server calls `run_agent(ctx, user_message, history)`; it never raises. When the result has `error` set or
`grounding_failed` is True, the server should fall back to the rule-based recommender.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from agents import (
    Agent,
    GuardrailFunctionOutput,
    ModelSettings,
    OpenAIChatCompletionsModel,
    OutputGuardrailTripwireTriggered,
    RunContextWrapper,
    Runner,
    function_tool,
    output_guardrail,
    set_tracing_disabled,
)

from app.agent.cards import price_label
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.recommender import diversify, normalize_brand
from app.config import settings
from app.data import scenarios
from app.data import taxonomy as tx
from app.data.db import Database
from app.schemas import TasteProfile

log = logging.getLogger(__name__)

# No OpenAI platform key is configured for tracing and api.openai.com is unreachable from the deployment.
set_tracing_disabled(True)

RUN_TIMEOUT_S = 30.0
MAX_TURNS = 8
MAX_HISTORY = 12
SEARCH_LIMIT = 8
ALLOWED_CHIPS = {"less_sweet", "fresher", "cheaper", "stronger", "lighter"}

# One corrective retry when the model's picks name ids no tool returned. Kept well inside RUN_TIMEOUT_S so the
# retry cannot push the turn past the server's own budget.
RETRY_BUDGET_S = RUN_TIMEOUT_S * 0.5
RETRY_INSTRUCTION = (
    "Correction: your previous answer used perfume_id values that no tool returned, so it was discarded. "
    "Call search_perfumes (or find_similar / get_perfume) now, then use ONLY perfume_id values returned by "
    "your tools in this turn, copied exactly from their use_these_ids list."
)


# ---------------------------------------------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class AgentContext:
    session_id: str
    language: str                      # "en" | "ar"
    profile: TasteProfile
    db: Database
    catalogue: Any                     # app.agent.recommender.Catalogue
    seen_ids: set[str] = field(default_factory=set)       # every perfume_id any tool returned this run
    wishlist_consent: bool = False
    brand_filter: str = ""
    last_results: list[str] = field(default_factory=list)  # ids returned by the most recent search/similar call
    tool_calls: list[str] = field(default_factory=list)    # tool names in call order, for analytics
    tool_log: list[dict] = field(default_factory=list)     # per call: {tool, args, n, ids} -- one INFO summary
                                                            # line per turn is built from this (never secrets)
    tool_seconds: float = 0.0                              # wall time spent inside tool implementations
    last_layering: Optional[dict] = None  # set by suggest_layering_impl; backfills output.layering if the
                                           # model called the tool but left the structured field empty
    guided: bool = False                  # "Guided match": one AI-authored question per turn, quick_replies required
    guided_question_index: int = 0        # 1-based; question 1 ("who is this for?") is answered before the model runs
    guided_max: int = 5
    anchor_context: Optional[dict] = None  # compact() of the profile's resolved anchor perfume (fix: grounded
                                            # real facts, from a server-side lookup, so the model can describe
                                            # a named perfume correctly without necessarily re-calling get_perfume)
    guided_topics_asked: list[str] = field(default_factory=list)  # topics already asked this guided run (fix:
                                                                   # stops the model re-asking the same topic)
    pending_question: Optional[dict] = None  # {"question": str, "topic": str} -- the question THIS turn's
                                              # message is answering (fix: told to the model so its own
                                              # profile_updates agree with the server's deterministic reading)
    force_recommend: bool = False  # fix: guided match finishing (cap reached, enough signals, or "show my
                                    # picks now") lets the model write the closing turn when true -- it must
                                    # recommend now, not ask another question


# ---------------------------------------------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------------------------------------------
class Pick(BaseModel):
    perfume_id: str
    reason: str = Field(description="One sentence using only this perfume's catalogue fields.")


class LayeringPick(BaseModel):
    base_perfume_id: str
    partner_perfume_id: str
    reason: str


class ProfileUpdates(BaseModel):
    """Same fields as TasteProfile, all optional: only what the model learned this turn."""
    liked_notes: Optional[list[str]] = None
    disliked_notes: Optional[list[str]] = None
    families: Optional[list[str]] = None
    avoid_families: Optional[list[str]] = None
    moods: Optional[list[str]] = None
    occasions: Optional[list[str]] = None
    seasons: Optional[list[str]] = None
    strength: Optional[int] = Field(default=None, description="1 (very light) to 5 (very strong)")
    budget_aed: Optional[float] = None
    anchor_perfume: Optional[str] = None
    anchor_perfume_id: Optional[str] = None
    brand: Optional[str] = None
    gender: Optional[str] = Field(default=None, description="women | men | unisex")
    guided_for: Optional[str] = Field(default=None, description="self | gift_her | gift_him | gift_unsure")

    def to_profile(self) -> TasteProfile:
        data = {k: v for k, v in self.model_dump().items() if v is not None}
        if "strength" in data:
            data["strength"] = min(5, max(1, int(data["strength"])))
        for key in ("liked_notes", "disliked_notes"):
            if key in data:
                data[key] = normalise_notes(data[key])
        for key in ("families", "avoid_families"):
            if key in data:
                data[key] = normalise_families(data[key])
        if "moods" in data:
            data["moods"] = [m for m in data["moods"] if m in tx.load()["moods"]]
        if data.get("guided_for") not in (None, "self", "gift_her", "gift_him", "gift_unsure"):
            data.pop("guided_for", None)
        return TasteProfile(**data)


GUIDED_TOPICS = ("recipient", "occasion", "liked_scents", "disliked_scents", "strength", "budget",
                 "anchor_feedback", "other")


class AgentOutput(BaseModel):
    reply: str
    question: Optional[str] = Field(
        default=None,
        description='Present only when `reply` asks the shopper something: ONE short question sentence '
                    '(aim for 12 words or fewer), separate from `reply`. Example answers go in quick_replies, '
                    'never appended here. `reply` may hold one short warm acknowledgement instead, and must '
                    'not repeat this question.')
    topic: Optional[Literal["recipient", "occasion", "liked_scents", "disliked_scents", "strength", "budget",
                            "anchor_feedback", "other"]] = Field(
        default=None, description="Present only alongside `question`: the single topic it covers, so the "
                                  "server can stop you asking about the same topic twice.")
    intent: Literal["chat", "recommend", "lookup", "wishlist", "declined"]
    picks: list[Pick] = Field(default_factory=list, description="0 or exactly 3 picks, ids from tool results only")
    layering: Optional[LayeringPick] = None
    chips: list[str] = Field(default_factory=list,
                             description='From "less_sweet","fresher","cheaper","stronger","lighter","more_like:<perfume_id>"')
    profile_updates: Optional[ProfileUpdates] = None
    ask_consent: bool = Field(default_factory=lambda: False)  # factory keeps "default" out of the strict schema
    quick_replies: list[str] = Field(default_factory=list,
                                     description="0 to 6 short tappable answers (2-4 words) for the question in `reply`")
    multi_select: bool = Field(default_factory=lambda: False, description="True if several quick_replies can be chosen at once")
    ask_reason: Optional[str] = Field(default=None, description='Short one-line "why I\'m asking" hint, optional')


@dataclass
class AgentRunResult:
    model_calls: int = 0                          # LLM round trips this turn (tool loop iterations + 1)
    seconds: float = 0.0                          # wall time of the whole agent run
    tool_seconds: float = 0.0                     # of which, inside catalogue tools
    retried: bool = False                         # a corrective second run was needed (unknown pick ids)
    output: Optional[AgentOutput] = None          # grounded output (None on error)
    seen_ids: set[str] = field(default_factory=set)
    tool_calls: list[str] = field(default_factory=list)
    grounding_failed: bool = False                # output guardrail tripped: model named an id no tool returned
    error: Optional[str] = None                   # network / timeout / malformed output; never raised
    dropped_ids: list[str] = field(default_factory=list)
    profile: Optional[TasteProfile] = None        # ctx.profile after this run (search filters + profile_updates)
    pick_filter_profile: Optional[TasteProfile] = None  # ctx.profile as the TOOLS saw it, before this turn's
                                                         # profile_updates were merged in. The server re-checks
                                                         # the model's picks against this, so an inference the
                                                         # model made *after* choosing them (a strength or
                                                         # gender guess) cannot disqualify picks the catalogue
                                                         # had already cleared for the same request.

    @property
    def ok(self) -> bool:
        return self.error is None and not self.grounding_failed and self.output is not None


# ---------------------------------------------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------------------------------------------
def _arabic_note_index() -> dict[str, str]:
    return {spec["ar"]: master for master, spec in tx.load()["notes"].items() if spec.get("ar")}


def normalise_notes(values: list[str] | None) -> list[str]:
    out: list[str] = []
    ar = _arabic_note_index()
    for v in values or []:
        v = (v or "").strip()
        if not v:
            continue
        master = ar.get(v) or tx.normalise_note(v) or v.lower()
        if master not in out:
            out.append(master)
    return out


def normalise_families(values: list[str] | None) -> list[str]:
    syn = tx.load().get("family_synonyms", {})
    out: list[str] = []
    for v in values or []:
        key = (v or "").strip().lower()
        fam = key if key in tx.load()["families"] else next((f for f, words in syn.items() if key in words), None)
        if fam and fam not in out:
            out.append(fam)
    return out


def key_notes(p: dict, limit: int = 6) -> list[str]:
    order = {"top": 0, "heart": 1, "middle": 1, "base": 2}
    notes = sorted(p.get("notes") or [], key=lambda n: order.get(n.get("layer"), 3))
    out: list[str] = []
    for n in notes:
        if n.get("note") and n["note"] not in out:
            out.append(n["note"])
    return out[:limit]


def compact(p: dict, lang: str = "en", score: float | None = None) -> dict:
    """Small, JSON-safe view of a perfume row for the model (never the whole row)."""
    notes = key_notes(p)
    desc = (p.get("description_ar") if lang == "ar" else p.get("description")) or p.get("description") or ""
    d = {
        "perfume_id": p["perfume_id"],
        "name": p.get("name"),
        "brand": p.get("brand_name"),
        "family": p.get("family"),
        "key_notes": notes,
        "strength": p.get("strength"),
        "price": price_label(p, lang),
        "price_aed": p.get("price_aed"),
        "description": desc[:220],
    }
    if lang == "ar":
        d["key_notes_ar"] = [tx.note_label(n, "ar") for n in notes]
        d["family_ar"] = tx.label("families", p.get("family") or "", "ar")
    if score is not None:
        d["match"] = int(round(float(score) * 100))
    return d


def _perfume_notes(p: dict) -> set[str]:
    return {n.get("note") for n in (p.get("notes") or []) if n.get("note")}


def _violates(p: dict, profile: TasteProfile) -> bool:
    """Defence in depth on top of the catalogue's hard filters."""
    if profile.disliked_notes and _perfume_notes(p) & set(profile.disliked_notes):
        return True
    if profile.budget_aed is not None and p.get("price_aed") is not None and float(p["price_aed"]) > profile.budget_aed:
        return True
    return False


def _brand_ok(p: dict, brand_filter: str) -> bool:
    brand = normalize_brand(brand_filter)
    return not brand or normalize_brand(p.get("brand_name")) == brand


MAX_PER_BRAND_IN_CANDIDATES = 2
CANDIDATE_POOL_MULTIPLIER = 4  # fetch this many times `limit` from the catalogue before diversifying/filtering


def _candidate_rows(ctx: AgentContext, raw_rows: list[dict], limit: int) -> list[dict]:
    """Shared by search_perfumes_impl/find_similar_impl (fix: the candidate list an agent tool hands to the
    model must itself be diversified -- at most 2 per brand, no near-duplicate names -- or the model ends up
    choosing 3 picks from whatever brand happened to dominate the raw ranking). A brand filter narrows the
    catalogue to one brand already, so the variety rule is relaxed then (there is nothing to diversify against)."""
    filtered = [r for r in raw_rows if not _violates(r["perfume"], ctx.profile) and _brand_ok(r["perfume"], ctx.brand_filter)]
    if ctx.brand_filter:
        return filtered[:limit]
    return diversify(filtered, limit=limit, max_per_brand=MAX_PER_BRAND_IN_CANDIDATES)


def _dump(d: dict) -> str:
    # Tools return JSON text: the SDK would otherwise str() a dict into a Python repr.
    return json.dumps(d, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------------------------------------------
# Tool implementations (plain functions, easy to unit test) and their SDK wrappers
# ---------------------------------------------------------------------------------------------------------------
def _remember(ctx: AgentContext, perfume_ids: list[str]) -> None:
    ctx.seen_ids.update(perfume_ids)


def _trace(ctx: AgentContext, tool: str, args: dict, ids: list[str], seconds: float = 0.0) -> None:
    """Records one tool call for the turn summary line (see `_turn_summary`). Catalogue data only -- never
    headers, keys or free user text beyond the short search string the model itself composed."""
    ctx.tool_seconds += seconds
    ctx.tool_log.append({
        "tool": tool,
        "args": {k: v for k, v in args.items() if v not in (None, [], "", 0)},
        "n": len(ids),
        "ids": ids[:8],
        "ms": int(seconds * 1000),
    })


def _merge_profile(profile: TasteProfile, update: TasteProfile) -> TasteProfile:
    """TasteProfile.merge, plus: a newly liked note/family stops being disliked/avoided, and vice versa."""
    merged = profile.merge(update)
    pairs = (("liked_notes", "disliked_notes"), ("families", "avoid_families"))
    for pos, neg in pairs:
        new_pos, new_neg = set(getattr(update, pos)), set(getattr(update, neg))
        setattr(merged, neg, [x for x in getattr(merged, neg) if x not in new_pos or x in new_neg])
        setattr(merged, pos, [x for x in getattr(merged, pos) if x not in new_neg])
    return merged


def search_perfumes_impl(ctx: AgentContext, liked_notes: list[str] | None = None, disliked_notes: list[str] | None = None,
                         families: list[str] | None = None, avoid_families: list[str] | None = None,
                         moods: list[str] | None = None, strength: int | None = None, budget_aed: float | None = None,
                         gender: str | None = None, text: str = "") -> dict:
    ctx.tool_calls.append("search_perfumes")
    t0 = time.perf_counter()
    update = TasteProfile(
        liked_notes=normalise_notes(liked_notes), disliked_notes=normalise_notes(disliked_notes),
        families=normalise_families(families), avoid_families=normalise_families(avoid_families),
        moods=[m for m in (moods or []) if m in tx.load()["moods"]],
        strength=min(5, max(1, int(strength))) if strength else None,
        budget_aed=float(budget_aed) if budget_aed else None,
        gender=(gender or None),
    )
    ctx.profile = _merge_profile(ctx.profile, update)
    rows = ctx.catalogue.search(ctx.profile, text=text or None, limit=SEARCH_LIMIT * CANDIDATE_POOL_MULTIPLIER)
    candidates = _candidate_rows(ctx, rows, SEARCH_LIMIT)
    results = [compact(r["perfume"], ctx.language, r.get("score")) for r in candidates]
    ids = [r["perfume_id"] for r in results]
    _remember(ctx, ids)
    ctx.last_results = ids
    if not results:
        try:
            ctx.db.add_review("zero_results", {"session_id": ctx.session_id, "profile": ctx.profile.model_dump(), "text": text})
        except Exception:  # pragma: no cover - analytics must never break the run
            log.exception("could not record zero_results")
    _trace(ctx, "search_perfumes", {"liked": liked_notes, "disliked": disliked_notes, "fam": families,
                                    "avoid": avoid_families, "moods": moods, "strength": strength,
                                    "budget": budget_aed, "gender": gender, "text": (text or "")[:60]},
           ids, time.perf_counter() - t0)
    return {"count": len(results), "use_these_ids": ids, "results": results}


def get_perfume_impl(ctx: AgentContext, name_or_id: str) -> dict:
    ctx.tool_calls.append("get_perfume")
    t0 = time.perf_counter()
    q = (name_or_id or "").strip()
    p = (ctx.catalogue.get(q) if q else None) or (ctx.catalogue.find_by_name(q) if q else None)
    if not p:
        _trace(ctx, "get_perfume", {"q": q[:60], "found": False}, [], time.perf_counter() - t0)
        return {"found": False, "query": q[:80]}
    if not _brand_ok(p, ctx.brand_filter):
        _trace(ctx, "get_perfume", {"q": q[:60], "found": False, "why": "brand"}, [], time.perf_counter() - t0)
        return {"found": False, "query": q[:80], "reason": "brand_out_of_scope"}
    d = compact(p, ctx.language)
    d["found"] = True
    d["notes_by_layer"] = {layer: [n["note"] for n in p.get("notes") or [] if n.get("layer") == layer]
                           for layer in ("top", "heart", "base")}
    accords = p.get("accords") or {}
    d["accords"] = [a for a, _ in sorted(accords.items(), key=lambda kv: -kv[1])[:5]]
    d["rating"] = p.get("rating")
    _remember(ctx, [p["perfume_id"]])
    _trace(ctx, "get_perfume", {"q": q[:60]}, [p["perfume_id"]], time.perf_counter() - t0)
    return d


def find_similar_impl(ctx: AgentContext, perfume_id: str, max_price: float | None = None) -> dict:
    ctx.tool_calls.append("find_similar")
    t0 = time.perf_counter()
    base = ctx.catalogue.get(perfume_id)
    if not base:
        _trace(ctx, "find_similar", {"base": perfume_id[:40], "found": False}, [], time.perf_counter() - t0)
        return {"found": False, "perfume_id": perfume_id}
    rows = ctx.catalogue.similar(perfume_id, limit=SEARCH_LIMIT * CANDIDATE_POOL_MULTIPLIER,
                                 max_price=max_price or None, profile=ctx.profile)
    rows = [r for r in rows if r["perfume"]["perfume_id"] != perfume_id]
    candidates = _candidate_rows(ctx, rows, SEARCH_LIMIT)
    results = [compact(r["perfume"], ctx.language, r.get("score")) for r in candidates]
    ids = [r["perfume_id"] for r in results]
    _remember(ctx, ids + [perfume_id])
    ctx.last_results = ids
    _trace(ctx, "find_similar", {"base": perfume_id, "max_price": max_price}, ids, time.perf_counter() - t0)
    return {"found": True, "base": compact(base, ctx.language), "count": len(results),
            "use_these_ids": ids, "results": results}


def suggest_layering_impl(ctx: AgentContext, perfume_id: str) -> dict:
    ctx.tool_calls.append("suggest_layering")
    t0 = time.perf_counter()
    if not ctx.catalogue.get(perfume_id):
        return {"found": False, "perfume_id": perfume_id}
    lay = ctx.catalogue.layering_partner(perfume_id, profile=ctx.profile)
    if not lay:
        return {"found": False, "perfume_id": perfume_id}
    partner = lay["perfume"]
    _remember(ctx, [perfume_id, partner["perfume_id"]])
    reason = lay.get("reason_ar") if ctx.language == "ar" else lay.get("reason_en")
    ctx.last_layering = {"base_perfume_id": perfume_id, "partner_perfume_id": partner["perfume_id"], "reason": reason}
    _trace(ctx, "suggest_layering", {"base": perfume_id}, [partner["perfume_id"]], time.perf_counter() - t0)
    return {
        "found": True,
        "base_perfume_id": perfume_id,
        "partner": compact(partner, ctx.language),
        "reason": reason,
    }


def save_wishlist_impl(ctx: AgentContext, perfume_ids: list[str]) -> dict:
    ctx.tool_calls.append("save_wishlist")
    valid = [pid for pid in dict.fromkeys(perfume_ids or []) if pid in ctx.seen_ids]
    rejected = [pid for pid in (perfume_ids or []) if pid not in ctx.seen_ids]
    if not ctx.wishlist_consent:
        return {"needs_consent": True, "perfume_ids": valid}
    if valid:
        ctx.db.add_wishlist(ctx.session_id, valid)
    return {"saved": valid, "rejected": rejected}


@function_tool
def search_perfumes(ctx: RunContextWrapper[AgentContext], liked_notes: list[str], disliked_notes: list[str],
                    families: list[str], avoid_families: list[str], moods: list[str], strength: Optional[int],
                    budget_aed: Optional[float], gender: Optional[str], text: str) -> str:
    """Search the store catalogue. Returns up to 8 perfumes; `use_these_ids` lists the only perfume_id values
    you may put in `picks` after this call.

    Args:
        liked_notes: Notes the user loves, e.g. ["vanilla", "oud"]. Empty list if none.
        disliked_notes: Notes to exclude completely, e.g. ["rose"]. Empty list if none.
        families: Wanted families: floral, fresh, aquatic, green, fruity, gourmand, woody, amber.
        avoid_families: Families to avoid, e.g. ["gourmand"] for "not sweet".
        moods: Mood keys: romantic, energetic, cozy, bold, elegant, playful, calm, mysterious.
        strength: 1 (very light) to 5 (very strong), or null.
        budget_aed: Maximum price in AED, or null.
        gender: women, men or unisex, or null.
        text: The user's own words describing what they want.
    """
    return _dump(search_perfumes_impl(ctx.context, liked_notes, disliked_notes, families, avoid_families, moods,
                                      strength, budget_aed, gender, text))


@function_tool
def get_perfume(ctx: RunContextWrapper[AgentContext], name_or_id: str) -> str:
    """Look up one perfume by perfume_id or by name. Returns {"found": false} if it is not in the catalogue.

    Args:
        name_or_id: A perfume_id from an earlier tool result, or the perfume name the user typed.
    """
    return _dump(get_perfume_impl(ctx.context, name_or_id))


@function_tool
def find_similar(ctx: RunContextWrapper[AgentContext], perfume_id: str, max_price: Optional[float]) -> str:
    """Find catalogue perfumes similar to a given perfume, optionally under a maximum price in AED. Its
    `use_these_ids` lists the only perfume_id values you may put in `picks` after this call.

    Args:
        perfume_id: The perfume_id from get_perfume or a search result.
        max_price: Maximum price in AED, or null.
    """
    return _dump(find_similar_impl(ctx.context, perfume_id, max_price))


@function_tool
def suggest_layering(ctx: RunContextWrapper[AgentContext], perfume_id: str) -> str:
    """Suggest one catalogue perfume to layer with the given perfume, with a short reason.

    Args:
        perfume_id: The perfume_id to build the layering on.
    """
    return _dump(suggest_layering_impl(ctx.context, perfume_id))


@function_tool
def save_wishlist(ctx: RunContextWrapper[AgentContext], perfume_ids: list[str]) -> str:
    """Save perfumes to the user's wishlist. Only call after the user explicitly said yes to saving.

    Args:
        perfume_ids: perfume_ids shown in this conversation.
    """
    return _dump(save_wishlist_impl(ctx.context, perfume_ids))


TOOLS = [search_perfumes, get_perfume, find_similar, suggest_layering, save_wishlist]


# ---------------------------------------------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------------------------------------------
def ungrounded_pick_ids(output: AgentOutput, ctx: AgentContext) -> list[str]:
    return [p.perfume_id for p in output.picks if p.perfume_id not in ctx.seen_ids]


@output_guardrail
def grounding_guardrail(ctx: RunContextWrapper[AgentContext], agent: Agent, output: AgentOutput) -> GuardrailFunctionOutput:
    bad = ungrounded_pick_ids(output, ctx.context)
    return GuardrailFunctionOutput(output_info={"ungrounded": bad}, tripwire_triggered=bool(bad))


QUICK_REPLY_MAX = 6
QUICK_REPLY_LEN = 40
ASK_REASON_LEN = 140
QUESTION_LEN = 120


def sanitise_quick_replies(values: list[str] | None) -> list[str]:
    """Strips, dedupes (case-insensitively) and caps quick_replies to plain, short text: at most 6 items,
    each at most 40 characters, no markup or control characters."""
    out: list[str] = []
    seen: set[str] = set()
    for v in values or []:
        s = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>]", "", str(v or ""))).strip()
        if not s:
            continue
        s = s[:QUICK_REPLY_LEN].strip()
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= QUICK_REPLY_MAX:
            break
    return out


def sanitise_ask_reason(value: str | None) -> str | None:
    if not value:
        return None
    s = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>]", "", str(value))).strip()
    return s[:ASK_REASON_LEN].strip() or None


def sanitise_question(value: str | None) -> str | None:
    """Fix: keeps `AgentOutput.question` to one short question sentence. Strips control characters/markup and
    collapses whitespace like the other sanitisers; when the model wrote several sentences (the observed live
    bug -- a long, rambling `reply`-shaped question), keeps only the last one that ends with a question mark
    (Latin '?' or Arabic '؟'), falling back to the last sentence when none does. Caps length at QUESTION_LEN."""
    if not value:
        return None
    s = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>]", "", str(value))).strip()
    if not s:
        return None
    parts = [p.strip() for p in re.split(r"(?<=[.!?؟])\s+", s) if p.strip()]
    if len(parts) > 1:
        question_parts = [p for p in parts if p.endswith(("?", "؟"))]
        s = question_parts[-1] if question_parts else parts[-1]
    return s[:QUESTION_LEN].strip() or None


def ground(output: AgentOutput, ctx: AgentContext) -> AgentOutput:
    """Drops every pick / layering / chip id that no tool returned this run, and picks that break the user's hard
    filters (disliked notes, budget). Records a review_queue entry when anything is dropped."""
    seen = ctx.seen_ids
    dropped: list[str] = []
    violations: list[str] = []
    picks = []
    used: set[str] = set()
    for p in output.picks:
        if p.perfume_id not in seen:
            dropped.append(p.perfume_id)
            continue
        if p.perfume_id in used:
            continue
        row = ctx.catalogue.get(p.perfume_id)
        if row is None:
            dropped.append(p.perfume_id)
            continue
        if _violates(row, ctx.profile) or not _brand_ok(row, ctx.brand_filter):
            violations.append(p.perfume_id)
            continue
        used.add(p.perfume_id)
        picks.append(p)
    layering = output.layering
    if layering is None and ctx.last_layering:
        # The tool ran and found a compatible partner this turn, but the model's structured output left
        # `layering` empty (e.g. intent="chat" after a "what would layer well with X" follow-up): use the
        # tool's own result so the UI still gets a layering card.
        ll = ctx.last_layering
        if ll["base_perfume_id"] in seen and ll["partner_perfume_id"] in seen:
            layering = LayeringPick(base_perfume_id=ll["base_perfume_id"], partner_perfume_id=ll["partner_perfume_id"],
                                    reason=ll.get("reason") or "")
    if layering and (layering.base_perfume_id not in seen or layering.partner_perfume_id not in seen):
        dropped += [i for i in (layering.base_perfume_id, layering.partner_perfume_id) if i not in seen]
        layering = None
    chips = []
    for c in output.chips:
        if c in ALLOWED_CHIPS or (c.startswith("more_like:") and c.split(":", 1)[1] in seen):
            if c not in chips:
                chips.append(c)
    if dropped or violations:
        try:
            if dropped:
                ctx.db.add_review("ungrounded", {"session_id": ctx.session_id, "dropped_ids": dropped,
                                                 "seen_ids": sorted(seen)[:50], "reply": output.reply[:300]})
            if violations:
                ctx.db.add_review("constraint_violation", {"session_id": ctx.session_id, "dropped_ids": violations,
                                                           "profile": ctx.profile.model_dump()})
        except Exception:  # pragma: no cover
            log.exception("could not record grounding review")
    quick_replies = sanitise_quick_replies(output.quick_replies)
    return output.model_copy(update={
        "picks": picks, "layering": layering, "chips": chips,
        "quick_replies": quick_replies, "multi_select": bool(output.multi_select) if quick_replies else False,
        "ask_reason": sanitise_ask_reason(output.ask_reason) if quick_replies else None,
        "question": sanitise_question(output.question) if quick_replies else None,
        "topic": output.topic if quick_replies else None,
    })


# ---------------------------------------------------------------------------------------------------------------
# Agent assembly
# ---------------------------------------------------------------------------------------------------------------
def instructions(ctx_wrapper: RunContextWrapper[AgentContext], agent: Agent) -> str:
    ctx = ctx_wrapper.context
    lang = "Arabic" if ctx.language == "ar" else "English"
    profile = ctx.profile.model_dump(exclude_defaults=True)
    brand = (f"{ctx.brand_filter} (only this brand is in scope; other brands are out of scope)"
             if ctx.brand_filter else "none (all brands in the catalogue)")
    guided = (f"active (question {ctx.guided_question_index} of up to {ctx.guided_max})" if ctx.guided else "inactive")
    anchor_line = (
        f"- Anchor perfume already looked up (JSON, real catalogue facts -- use ONLY these if you describe it, "
        f"never your own memory of it; still call find_similar with its perfume_id for similar picks): "
        f"{json.dumps(ctx.anchor_context, ensure_ascii=False)}\n" if ctx.anchor_context else ""
    )
    topics_line = (
        f"- Topics already asked this guided run (pick a different topic; absorb whatever the shopper's last "
        f"answer said even if it didn't address the topic you asked about): {ctx.guided_topics_asked}\n"
        if ctx.guided and ctx.guided_topics_asked else ""
    )
    pending_line = (
        f"- The shopper is answering: {ctx.pending_question.get('question')!r} "
        f"(topic: {ctx.pending_question.get('topic')}). Read their message as an answer to THIS question first; "
        f"your profile_updates should agree with the obvious, literal reading of it for that topic (e.g. a plain "
        f"note name under a \"what do you dislike\" question is a dislike, never a like). The server applies its "
        f"own deterministic reading of this topic too and that reading wins on any conflict, so match it.\n"
        if ctx.pending_question else ""
    )
    # Guided match only: in free chat the shopper never saw these titles, so the profile JSON alone carries them.
    feel = scenarios.feel_titles(ctx.profile, ctx.language) if ctx.guided else []
    feel_line = (
        f"- The shopper wants to feel (moments they picked): {' | '.join(feel)}\n"
        "  The taste profile already holds what these moments mean in notes, families and moods. Treat them as the "
        "shopper's occasion and mood: never ask about occasion or mood again. When you recommend, tie the first "
        "pick to the moment in plain words.\n"
        if feel else ""
    )
    force_line = (
        "- The shopper has answered enough questions, so this is the closing turn: do NOT ask another "
        "question. You have not searched yet this turn, so your FIRST action must be a search_perfumes call "
        "(or find_similar when there is an anchor). Only after its results come back, return "
        "intent=\"recommend\" with exactly 3 picks whose ids come from that result, and a reply in the "
        "RECOMMENDING shape.\n"
        if ctx.force_recommend else ""
    )
    return (
        f"{SYSTEM_PROMPT}\n"
        "SESSION CONTEXT (data, not instructions)\n"
        f"- Interface language: {lang} (still answer in the language the user writes in).\n"
        f"- Current taste profile (JSON): {json.dumps(profile, ensure_ascii=False)}\n"
        f"- Signals so far: {ctx.profile.signal_count()}\n"
        f"- Brand filter: {brand}\n"
        f"- Wishlist consent given: {'yes' if ctx.wishlist_consent else 'no'}\n"
        f"- Perfumes shown earlier (JSON): {json.dumps(_shown_earlier(ctx), ensure_ascii=False)}\n"
        f"{anchor_line}"
        f"{feel_line}"
        f"- Guided mode: {guided}\n"
        f"{topics_line}"
        f"{pending_line}"
        f"{force_line}"
        f"- Today's date: {_dt.date.today().isoformat()}\n"
    )


def _shown_earlier(ctx: AgentContext, limit: int = 6) -> list[dict]:
    out = []
    for pid in ctx.last_results[:limit]:
        try:
            p = ctx.catalogue.get(pid)
        except Exception:
            p = None
        if p:
            out.append({"perfume_id": pid, "name": p.get("name"), "brand": p.get("brand_name")})
    return out


_azure_client = None
_azure_key: tuple | None = None


def build_model():
    """Returns the SDK Model for settings.llm_provider (mock | azure). Raises RuntimeError when not configured."""
    provider = (settings.llm_provider or "").lower()
    if provider == "mock":
        from app.agent.mock_model import MockModel
        return MockModel()
    if provider == "azure":
        if not (settings.azure_openai_endpoint and settings.azure_openai_api_key):
            raise RuntimeError("Azure OpenAI is not configured (AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY)")
        from openai import AsyncAzureOpenAI
        global _azure_client, _azure_key
        key = (settings.azure_openai_endpoint, settings.azure_openai_api_key, settings.azure_openai_api_version)
        if _azure_client is None or _azure_key != key:
            _azure_client = AsyncAzureOpenAI(
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=settings.azure_openai_endpoint,
                timeout=RUN_TIMEOUT_S,
                max_retries=1,
            )
            _azure_key = key
        return OpenAIChatCompletionsModel(model=settings.azure_openai_chat_deployment, openai_client=_azure_client)
    raise RuntimeError(f"LLM provider {provider!r} is disabled")


def build_agent(model=None) -> Agent[AgentContext]:
    return Agent[AgentContext](
        name="perfume_advisor",
        instructions=instructions,
        tools=TOOLS,
        output_type=AgentOutput,
        output_guardrails=[grounding_guardrail],
        model=model if model is not None else build_model(),
        model_settings=ModelSettings(temperature=0.3),
    )


def build_input(history: list[dict], user_message: str) -> list[dict]:
    items: list[dict] = []
    for turn in (history or [])[-MAX_HISTORY:]:
        role = turn.get("role")
        text = (turn.get("text") or "").strip()
        if role in ("user", "assistant") and text:
            items.append({"role": role, "content": text[:2000]})
    items.append({"role": "user", "content": (user_message or "")[:2000]})
    return items


def _apply_updates(ctx: AgentContext, output: AgentOutput | None) -> None:
    if output is not None and output.profile_updates is not None:
        try:
            ctx.profile = _merge_profile(ctx.profile, output.profile_updates.to_profile())
        except Exception:  # malformed partial profile: ignore it rather than fail the turn
            log.warning("ignored invalid profile_updates", exc_info=True)


def _turn_summary(ctx: AgentContext, res: AgentRunResult) -> None:
    """One low-noise INFO line per turn: what the model asked the catalogue for, what came back, what it
    finally picked and what the grounding check made of it. Catalogue data and timings only."""
    tools = ";".join(
        f"{t['tool']}({','.join(f'{k}={v}' for k, v in t['args'].items())})->{t['n']}@{t['ms']}ms"
        for t in ctx.tool_log) or "none"
    out = res.output
    log.info(
        "agent turn sid=%s lang=%s guided=%s force=%s | tools=%s | model_calls=%d t=%.1fs tools=%.1fs%s | "
        "intent=%s picks=%s ungrounded=%s dropped=%s%s",
        ctx.session_id[:8], ctx.language, int(ctx.guided), int(ctx.force_recommend), tools,
        res.model_calls, res.seconds, res.tool_seconds, " RETRIED" if res.retried else "",
        out.intent if out else "-", [p.perfume_id for p in out.picks] if out else [],
        res.dropped_ids if res.grounding_failed else [], [] if res.grounding_failed else res.dropped_ids,
        f" error={res.error}" if res.error else "",
    )


async def run_agent(ctx: AgentContext, user_message: str, history: list[dict]) -> AgentRunResult:
    """Runs one user turn. Never raises: failures come back in `error`, grounding problems in `grounding_failed`."""
    t_start = time.perf_counter()
    items = build_input(history, user_message)
    # Perfumes shown in earlier turns were tool results too, so they may be referenced (wishlist, "more like").
    ctx.seen_ids.update(ctx.last_results)
    if ctx.anchor_context and ctx.anchor_context.get("perfume_id"):
        # A server-side lookup (same catalogue data a get_perfume call would return) is as trustworthy as a
        # tool call: count it as seen so grounding doesn't punish the model for not re-calling get_perfume.
        ctx.seen_ids.add(ctx.anchor_context["perfume_id"])
    res = await _run_once(ctx, items, deadline=t_start + RUN_TIMEOUT_S)
    if res.grounding_failed and time.perf_counter() - t_start < RETRY_BUDGET_S:
        # The model named perfume_ids no tool returned -- in practice because it answered without searching at
        # all, and invented plausible-looking ids. One corrective retry is far better than throwing the turn
        # away: the fallback costs the shopper the advisor's own words, and this usually costs ~3s.
        res = await _run_once(ctx, items, deadline=t_start + RUN_TIMEOUT_S, extra=RETRY_INSTRUCTION)
        res.retried = True
    res.seconds = time.perf_counter() - t_start
    res.tool_seconds = ctx.tool_seconds
    _turn_summary(ctx, res)
    return res


async def _run_once(ctx: AgentContext, items: list[dict], deadline: float,
                    extra: str | None = None) -> AgentRunResult:
    """One agent run. `extra` appends a short corrective system note for the retry path."""
    timeout = max(1.0, deadline - time.perf_counter())
    try:
        agent = build_agent()
        run_items = items if not extra else items + [{"role": "system", "content": extra}]
        result = await asyncio.wait_for(Runner.run(agent, run_items, context=ctx, max_turns=MAX_TURNS),
                                        timeout=timeout)
        raw = result.final_output
        output = raw if isinstance(raw, AgentOutput) else AgentOutput.model_validate(
            json.loads(raw) if isinstance(raw, str) else raw)
        before = [p.perfume_id for p in output.picks]
        grounded = ground(output, ctx)
        searched_with = ctx.profile.model_copy(deep=True)
        _apply_updates(ctx, grounded)
        return AgentRunResult(
            model_calls=len(getattr(result, "raw_responses", []) or []),
            output=grounded, seen_ids=set(ctx.seen_ids), tool_calls=list(ctx.tool_calls),
            dropped_ids=[i for i in before if i not in {p.perfume_id for p in grounded.picks}], profile=ctx.profile,
            pick_filter_profile=searched_with,
        )
    except OutputGuardrailTripwireTriggered as exc:
        raw = exc.guardrail_result.agent_output
        grounded = ground(raw, ctx) if isinstance(raw, AgentOutput) else None
        bad = (exc.guardrail_result.output.output_info or {}).get("ungrounded", [])
        log.warning("grounding guardrail tripped for session %s: %s", ctx.session_id, bad)
        return AgentRunResult(output=grounded, seen_ids=set(ctx.seen_ids), tool_calls=list(ctx.tool_calls),
                              grounding_failed=True, dropped_ids=list(bad), profile=ctx.profile)
    except (asyncio.TimeoutError, TimeoutError):
        return AgentRunResult(seen_ids=set(ctx.seen_ids), tool_calls=list(ctx.tool_calls), profile=ctx.profile,
                              error=f"timeout after {RUN_TIMEOUT_S:.0f}s")
    except Exception as exc:  # network, auth, max turns, malformed structured output, tool bugs...
        log.warning("agent run failed: %s", exc, exc_info=True)
        return AgentRunResult(seen_ids=set(ctx.seen_ids), tool_calls=list(ctx.tool_calls), profile=ctx.profile,
                              error=f"{type(exc).__name__}: {exc}"[:500])


AFFIRMATIVE = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "please do", "save", "save it", "save them",
               "نعم", "أجل", "اكيد", "أكيد", "تمام", "موافق", "احفظ", "احفظها", "ايوه", "إيه"}


def is_affirmative(text: str) -> bool:
    """Helper for the server: True when the user's reply is a plain yes (used to grant wishlist consent after the
    agent returned ask_consent=True on the previous turn)."""
    t = (text or "").strip().lower().strip(".!؟? ")
    return t in AFFIRMATIVE or t.startswith(("yes ", "yes,", "sure ", "نعم ", "نعم،"))
