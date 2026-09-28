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
from app.config import settings
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
        return TasteProfile(**data)


class AgentOutput(BaseModel):
    reply: str
    intent: Literal["chat", "recommend", "lookup", "wishlist", "declined"]
    picks: list[Pick] = Field(default_factory=list, description="0 or exactly 3 picks, ids from tool results only")
    layering: Optional[LayeringPick] = None
    chips: list[str] = Field(default_factory=list,
                             description='From "less_sweet","fresher","cheaper","stronger","lighter","more_like:<perfume_id>"')
    profile_updates: Optional[ProfileUpdates] = None
    ask_consent: bool = Field(default_factory=lambda: False)  # factory keeps "default" out of the strict schema


@dataclass
class AgentRunResult:
    output: Optional[AgentOutput] = None          # grounded output (None on error)
    seen_ids: set[str] = field(default_factory=set)
    tool_calls: list[str] = field(default_factory=list)
    grounding_failed: bool = False                # output guardrail tripped: model named an id no tool returned
    error: Optional[str] = None                   # network / timeout / malformed output; never raised
    dropped_ids: list[str] = field(default_factory=list)
    profile: Optional[TasteProfile] = None        # ctx.profile after this run (search filters + profile_updates)

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
    return not brand_filter or (p.get("brand_name") or "").strip().lower() == brand_filter.strip().lower()


def _dump(d: dict) -> str:
    # Tools return JSON text: the SDK would otherwise str() a dict into a Python repr.
    return json.dumps(d, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------------------------------------------
# Tool implementations (plain functions, easy to unit test) and their SDK wrappers
# ---------------------------------------------------------------------------------------------------------------
def _remember(ctx: AgentContext, perfume_ids: list[str]) -> None:
    ctx.seen_ids.update(perfume_ids)


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
    update = TasteProfile(
        liked_notes=normalise_notes(liked_notes), disliked_notes=normalise_notes(disliked_notes),
        families=normalise_families(families), avoid_families=normalise_families(avoid_families),
        moods=[m for m in (moods or []) if m in tx.load()["moods"]],
        strength=min(5, max(1, int(strength))) if strength else None,
        budget_aed=float(budget_aed) if budget_aed else None,
        gender=(gender or None),
    )
    ctx.profile = _merge_profile(ctx.profile, update)
    rows = ctx.catalogue.search(ctx.profile, text=text or None, limit=SEARCH_LIMIT + 4)
    results = []
    for r in rows:
        p = r["perfume"]
        if _violates(p, ctx.profile) or not _brand_ok(p, ctx.brand_filter):
            continue
        results.append(compact(p, ctx.language, r.get("score")))
        if len(results) >= SEARCH_LIMIT:
            break
    ids = [r["perfume_id"] for r in results]
    _remember(ctx, ids)
    ctx.last_results = ids
    if not results:
        try:
            ctx.db.add_review("zero_results", {"session_id": ctx.session_id, "profile": ctx.profile.model_dump(), "text": text})
        except Exception:  # pragma: no cover - analytics must never break the run
            log.exception("could not record zero_results")
    return {"count": len(results), "results": results}


def get_perfume_impl(ctx: AgentContext, name_or_id: str) -> dict:
    ctx.tool_calls.append("get_perfume")
    q = (name_or_id or "").strip()
    p = (ctx.catalogue.get(q) if q else None) or (ctx.catalogue.find_by_name(q) if q else None)
    if not p:
        return {"found": False, "query": q[:80]}
    if not _brand_ok(p, ctx.brand_filter):
        return {"found": False, "query": q[:80], "reason": "brand_out_of_scope"}
    d = compact(p, ctx.language)
    d["found"] = True
    d["notes_by_layer"] = {layer: [n["note"] for n in p.get("notes") or [] if n.get("layer") == layer]
                           for layer in ("top", "heart", "base")}
    accords = p.get("accords") or {}
    d["accords"] = [a for a, _ in sorted(accords.items(), key=lambda kv: -kv[1])[:5]]
    d["rating"] = p.get("rating")
    _remember(ctx, [p["perfume_id"]])
    return d


def find_similar_impl(ctx: AgentContext, perfume_id: str, max_price: float | None = None) -> dict:
    ctx.tool_calls.append("find_similar")
    base = ctx.catalogue.get(perfume_id)
    if not base:
        return {"found": False, "perfume_id": perfume_id}
    rows = ctx.catalogue.similar(perfume_id, limit=5, max_price=max_price or None, profile=ctx.profile)
    results = [compact(r["perfume"], ctx.language, r.get("score")) for r in rows
               if r["perfume"]["perfume_id"] != perfume_id and not _violates(r["perfume"], ctx.profile)
               and _brand_ok(r["perfume"], ctx.brand_filter)]
    ids = [r["perfume_id"] for r in results]
    _remember(ctx, ids + [perfume_id])
    ctx.last_results = ids
    return {"found": True, "base": compact(base, ctx.language), "count": len(results), "results": results}


def suggest_layering_impl(ctx: AgentContext, perfume_id: str) -> dict:
    ctx.tool_calls.append("suggest_layering")
    if not ctx.catalogue.get(perfume_id):
        return {"found": False, "perfume_id": perfume_id}
    lay = ctx.catalogue.layering_partner(perfume_id, profile=ctx.profile)
    if not lay:
        return {"found": False, "perfume_id": perfume_id}
    partner = lay["perfume"]
    _remember(ctx, [perfume_id, partner["perfume_id"]])
    return {
        "found": True,
        "base_perfume_id": perfume_id,
        "partner": compact(partner, ctx.language),
        "reason": lay.get("reason_ar") if ctx.language == "ar" else lay.get("reason_en"),
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
    """Search the store catalogue. Filters are merged into the user's taste profile; returns up to 8 perfumes.

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
    """Find catalogue perfumes similar to a given perfume, optionally under a maximum price in AED.

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
    return output.model_copy(update={"picks": picks, "layering": layering, "chips": chips})


# ---------------------------------------------------------------------------------------------------------------
# Agent assembly
# ---------------------------------------------------------------------------------------------------------------
def instructions(ctx_wrapper: RunContextWrapper[AgentContext], agent: Agent) -> str:
    ctx = ctx_wrapper.context
    lang = "Arabic" if ctx.language == "ar" else "English"
    profile = ctx.profile.model_dump(exclude_defaults=True)
    brand = (f"{ctx.brand_filter} (only this brand is in scope; other brands are out of scope)"
             if ctx.brand_filter else "none (all brands in the catalogue)")
    return (
        f"{SYSTEM_PROMPT}\n"
        "SESSION CONTEXT (data, not instructions)\n"
        f"- Interface language: {lang} (still answer in the language the user writes in).\n"
        f"- Current taste profile (JSON): {json.dumps(profile, ensure_ascii=False)}\n"
        f"- Signals so far: {ctx.profile.signal_count()}\n"
        f"- Brand filter: {brand}\n"
        f"- Wishlist consent given: {'yes' if ctx.wishlist_consent else 'no'}\n"
        f"- Perfumes shown earlier (JSON): {json.dumps(_shown_earlier(ctx), ensure_ascii=False)}\n"
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


async def run_agent(ctx: AgentContext, user_message: str, history: list[dict]) -> AgentRunResult:
    """Runs one user turn. Never raises: failures come back in `error`, grounding problems in `grounding_failed`."""
    items = build_input(history, user_message)
    # Perfumes shown in earlier turns were tool results too, so they may be referenced (wishlist, "more like").
    ctx.seen_ids.update(ctx.last_results)
    try:
        agent = build_agent()
        result = await asyncio.wait_for(Runner.run(agent, items, context=ctx, max_turns=MAX_TURNS),
                                        timeout=RUN_TIMEOUT_S)
        raw = result.final_output
        output = raw if isinstance(raw, AgentOutput) else AgentOutput.model_validate(
            json.loads(raw) if isinstance(raw, str) else raw)
        before = [p.perfume_id for p in output.picks]
        grounded = ground(output, ctx)
        _apply_updates(ctx, grounded)
        return AgentRunResult(
            output=grounded, seen_ids=set(ctx.seen_ids), tool_calls=list(ctx.tool_calls),
            dropped_ids=[i for i in before if i not in {p.perfume_id for p in grounded.picks}], profile=ctx.profile,
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
