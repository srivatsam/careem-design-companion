"""Deterministic offline Model for LLM_PROVIDER=mock.

It plays the part of the LLM inside the real OpenAI Agents SDK loop (tool calls, tool outputs, structured final
output, output guardrails), driven only by the latest user message and the tool results already in `input`.
Output items are built exactly like the SDK's Chat Completions converter builds them.
"""
from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from agents.items import ModelResponse
from agents.models.fake_id import FAKE_RESPONSES_ID
from agents.models.interface import Model
from agents.usage import Usage

from app.agent import prompts
from app.data import taxonomy as tx
from app.schemas import TasteProfile

UNGROUNDED_ID = "p_mock_ungrounded"
# The distinctive phrase llm_agent.RETRY_INSTRUCTION carries; see get_response's `corrected`.
_CORRECTION_MARK = "use_these_ids"

_ARABIC = re.compile(r"[؀-ۿ]")
_MEDICAL = re.compile(r"pregnan|allerg|breastfeed|eczema|asthma|medical|doctor|حامل|حمل|حساسية|رضاعة", re.I)
_INJECTION = re.compile(r"ignore (all |your |the |previous )*(rules|instructions)|system prompt|reveal (your|the) prompt|"
                        r"discount code|promo code|coupon|تجاهل (القواعد|التعليمات)|كود خصم|كوبون", re.I)
_ANCHOR = re.compile(r"(?i:similar to|something like|tell me about|like|مثل|يشبه|عن)\s+([A-Z0-9][^,.;!?؟\n]*)")
_BUDGET = re.compile(r"(?:under|below|less than|max(?:imum)?|up to|within|أقل من|تحت|حتى)\s*(?:aed|dhs|درهم)?\s*(\d{2,5})", re.I)
_SAVE = re.compile(r"\b(save|wishlist|add (them|it) to)\b|احفظ|المفضلة", re.I)


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                parts.append(c.get("text") or "")
            else:
                parts.append(getattr(c, "text", "") or "")
        return " ".join(parts)
    return ""


def _get(item: Any, key: str) -> Any:
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def _current_turn(items: list[Any]) -> tuple[str, list[tuple[str, dict, dict]]]:
    """Returns the latest user text and the (tool name, args, parsed output) calls made after it."""
    last_user = -1
    for i, it in enumerate(items):
        if _get(it, "role") == "user":
            last_user = i
    text = _text_of(_get(items[last_user], "content")) if last_user >= 0 else ""
    calls: dict[str, tuple[str, dict]] = {}
    ordered: list[tuple[str, dict, dict]] = []
    for it in items[last_user + 1:]:
        kind = _get(it, "type")
        if kind == "function_call":
            try:
                args = json.loads(_get(it, "arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls[_get(it, "call_id")] = (_get(it, "name"), args)
        elif kind == "function_call_output":
            name, args = calls.get(_get(it, "call_id"), ("?", {}))
            raw = _get(it, "output")
            try:
                out = json.loads(raw if isinstance(raw, str) else _text_of(raw))
            except (json.JSONDecodeError, TypeError):
                out = {"raw": raw}
            ordered.append((name, args, out if isinstance(out, dict) else {"raw": out}))
    return text, ordered


def _strip_al(word: str) -> str:
    return word[2:] if word.startswith("ال") and len(word) > 3 else word


def parse_filters(text: str) -> dict:
    """Keyword parse of free text into search_perfumes arguments."""
    low = text.lower()
    args: dict[str, Any] = {"liked_notes": [], "disliked_notes": [], "families": [], "avoid_families": [], "moods": [],
                            "strength": None, "budget_aed": None, "gender": None, "text": text}

    def add(key: str, values: list[str]) -> None:
        for v in values:
            if v not in args[key]:
                args[key].append(v)

    # Negations first, then remove them so positive keywords do not re-add them.
    if re.search(r"\b(not|no|less|without|hate|don'?t like)\s+(too\s+)?sweet", low):
        add("avoid_families", ["gourmand"])
        low = re.sub(r"\b(not|no|less|without|hate|don'?t like)\s+(too\s+)?sweet\w*", " ", low)
    for m in re.finditer(r"\b(?:hate|dislike|don'?t like|do not like|no|without|allergic to)\s+([a-z][a-z ]{1,25}?)(?=[,.;!?]|\s+(?:and|or|but|please|under|below)\b|$)", low):
        note = tx.normalise_note(m.group(1))
        if note:
            add("disliked_notes", [note])
            low = low.replace(m.group(0), " ")
    ar_notes = {spec["ar"]: master for master, spec in tx.load()["notes"].items() if spec.get("ar")}
    for m in re.finditer(r"(?:لا أحب|لا احب|أكره|اكره|بدون)\s+(\S+)", text):
        word = _strip_al(m.group(1).strip("،.؟!"))
        if word in ar_notes:
            add("disliked_notes", [ar_notes[word]])
            text = text.replace(m.group(0), " ")
        elif word in ("حلو", "الحلو"):
            add("avoid_families", ["gourmand"])
            text = text.replace(m.group(0), " ")

    for kw, upd in prompts.MOCK_HINTS.items():
        hit = (kw in text) if _ARABIC.search(kw) else re.search(rf"\b{re.escape(kw)}\b", low)
        if hit:
            for key, values in upd.items():
                if key == "families" and set(values) & set(args["avoid_families"]):
                    continue
                add(key, values)
    m = _BUDGET.search(text)
    if m:
        args["budget_aed"] = float(m.group(1))
    if re.search(r"\b(light|subtle|soft)\b|خفيف", low + text):
        args["strength"] = 2
    elif re.search(r"\b(strong|intense|long[- ]lasting|beast)\b|قوي", low + text):
        args["strength"] = 4
    if re.search(r"\bfor (a )?(men|him|man)\b|رجالي", low + text):
        args["gender"] = "men"
    elif re.search(r"\bfor (a )?(women|her|woman)\b|نسائي", low + text):
        args["gender"] = "women"
    return args


_GUIDED_RE = re.compile(r"Guided mode: active \(question (\d+) of up to (\d+)\)")
_PROFILE_RE = re.compile(r"Current taste profile \(JSON\): (\{.*\})\n")
# The server's "you have enough, recommend now" instruction (llm_agent.instructions force_line).
_FORCE_RE = re.compile(r"Do NOT ask another question this turn")
# The server's "this message answers THIS question" instruction (llm_agent.instructions pending_line).
_PENDING_RE = re.compile(r"The shopper is answering: .*?\(topic: ([a-z_]+)\)")
# The moments the shopper picked in guided match (llm_agent.instructions feel_line).
_FEEL_RE = re.compile(r"The shopper wants to feel \(moments they picked\): (.+)\n")


def _guided_state(system_instructions: str | None) -> tuple[bool, int, int]:
    m = _GUIDED_RE.search(system_instructions or "")
    if not m:
        return False, 0, 0
    return True, int(m.group(1)), int(m.group(2))


def _profile_from_instructions(system_instructions: str | None) -> TasteProfile:
    m = _PROFILE_RE.search(system_instructions or "")
    if not m:
        return TasteProfile()
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return TasteProfile()
    try:
        return TasteProfile(**data)
    except (TypeError, ValueError):
        return TasteProfile()


def _feel(system_instructions: str | None) -> str | None:
    """The first moment the shopper picked, so the closing reply can name it the way a real model would."""
    m = _FEEL_RE.search(system_instructions or "")
    return m.group(1).split(" | ")[0].strip() if m else None


def _pending_topic(system_instructions: str | None) -> str | None:
    m = _PENDING_RE.search(system_instructions or "")
    return m.group(1) if m else None


def filters_from_profile(prof: TasteProfile, text: str) -> dict:
    """Search filters for the FINAL guided turn: everything the interview collected, not just the last message.

    The real model does this by reading the taste profile in its session context; the mock has to do it
    explicitly so the forced closing turn recommends against the whole profile (dislikes, strength, budget,
    occasion) rather than against four words of the last answer.
    """
    args = parse_filters(text)
    for key, values in (("liked_notes", prof.liked_notes), ("disliked_notes", prof.disliked_notes),
                        ("families", prof.families), ("avoid_families", prof.avoid_families),
                        ("moods", prof.moods)):
        for v in values:
            if v not in args[key]:
                args[key].append(v)
    args["liked_notes"] = [n for n in args["liked_notes"] if n not in args["disliked_notes"]]
    args["families"] = [f for f in args["families"] if f not in args["avoid_families"]]
    if prof.strength is not None:
        args["strength"] = prof.strength
    if prof.budget_aed is not None:
        args["budget_aed"] = prof.budget_aed
    if prof.gender:
        args["gender"] = prof.gender
    args["text"] = " ".join(filter(None, [prof.free_text, text]))[:400]
    return args


def _guided_signal_count(prof: TasteProfile) -> int:
    """"At least 2 strong signals" for guided match: notes, families, moods, an anchor perfume or a budget --
    deliberately narrower than TasteProfile.signal_count() so an incidental gender/occasion picked up from the
    instant "who is this for?" answer doesn't finish the interview after a single turn."""
    return sum([
        bool(prof.liked_notes), bool(prof.disliked_notes), bool(prof.families), bool(prof.avoid_families),
        bool(prof.moods), bool(prof.anchor_perfume), prof.budget_aed is not None,
    ])


# Deterministic adaptive question bank, by branch: gift (recipient) vs self, then the shared remainder.
# Every quick_reply is worded so the extractor (app.agent.extract) reads it correctly regardless of which
# question it answers -- e.g. dislike answers spell out the negation ("No oud") since a bare note name reads
# as liked. Each question has a stable id: `_guided_asked_ids` matches its exact reply text back out of the
# conversation history so a skipped question is asked once, never repeated, across the whole run.
_GUIDED_Q_TABLE: dict[str, dict] = {
    "style": dict(reply={"en": "What's their style?", "ar": "ما الأسلوب الذي يناسبها؟"},
                 quick_replies={"en": ["Bold and confident", "Romantic", "Elegant", "Playful and sweet"],
                                "ar": ["جريء وواثق", "رومانسي", "أنيق", "مرح وحلو"]},
                 multi_select=False, applies=lambda p: not p.moods, topic="recipient"),
    "worn": dict(reply={"en": "What scents do they usually wear?", "ar": "ما النفحات التي تحبها عادة؟"},
                quick_replies={"en": ["Vanilla", "Oud", "Citrus", "Woody"], "ar": ["فانيليا", "عود", "حمضيات", "خشبي"]},
                multi_select=True, applies=lambda p: not p.liked_notes, topic="liked_scents"),
    "occasion": dict(reply={"en": "What's the occasion?", "ar": "ما المناسبة؟"},
                     quick_replies={"en": ["Everyday", "The office", "Evening out", "A special date"],
                                    "ar": ["يومي", "العمل", "سهرة", "موعد خاص"]},
                     multi_select=False, applies=lambda p: not p.occasions and not p.moods and not p.scenarios,
                     topic="occasion"),
    "loved": dict(reply={"en": "Which scents do you love?", "ar": "ما الروائح التي تحبها؟"},
                 quick_replies={"en": ["Vanilla", "Oud", "Rose", "Citrus"], "ar": ["فانيليا", "عود", "ورد", "حمضيات"]},
                 multi_select=True, applies=lambda p: not p.liked_notes, topic="liked_scents"),
    "avoid": dict(reply={"en": "Anything you'd like to avoid?", "ar": "هل هناك ما تفضّل تجنبه؟"},
                 quick_replies={"en": ["No oud", "No musk", "Not too sweet", "Nothing to avoid"],
                                "ar": ["بدون عود", "بدون مسك", "ليس حلواً جداً", "لا شيء"]},
                 multi_select=True, applies=lambda p: not p.disliked_notes, topic="disliked_scents"),
    "budget": dict(reply={"en": "What's your budget, roughly?", "ar": "ما ميزانيتك تقريباً؟"},
                  quick_replies={"en": ["Under AED 150", "Under AED 300", "Under AED 500", "No limit"],
                                 "ar": ["أقل من 150 درهم", "أقل من 300 درهم", "أقل من 500 درهم", "بدون حد"]},
                  multi_select=False, applies=lambda p: p.budget_aed is None, topic="budget"),
}


def _guided_order(gift: bool) -> list[str]:
    return (["style", "worn"] if gift else ["occasion", "loved"]) + ["avoid", "budget"]


def _guided_asked_ids(items: list, arabic: bool) -> set[str]:
    texts = {_text_of(_get(it, "content")).strip() for it in items if _get(it, "role") == "assistant"}
    return {qid for qid, spec in _GUIDED_Q_TABLE.items() if spec["reply"]["en"] in texts or spec["reply"]["ar"] in texts}


def _guided_question(prof: TasteProfile, arabic: bool, asked_ids: set[str]) -> dict | None:
    gift = (prof.guided_for or "").startswith("gift")
    lang = "ar" if arabic else "en"
    for qid in _guided_order(gift):
        spec = _GUIDED_Q_TABLE[qid]
        if qid in asked_ids or not spec["applies"](prof):
            continue
        return {"reply": spec["reply"][lang], "quick_replies": spec["quick_replies"][lang],
               "multi_select": spec["multi_select"], "topic": spec["topic"]}
    return None


def _anchor(text: str) -> str | None:
    m = _ANCHOR.search(text)
    if not m:
        return None
    phrase = re.split(r"\s+(?:but|under|below|and|please|for)\s+|\s+(?:لكن|تحت|أقل)\s+", m.group(1))[0].strip()
    return phrase or None


class MockModel(Model):
    """Scripted stand-in for the chat model. Deterministic for a given input."""

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing,
                           *, previous_response_id=None, conversation_id=None, prompt=None, **kwargs) -> ModelResponse:
        items = [{"role": "user", "content": input}] if isinstance(input, str) else list(input)
        text, calls = _current_turn(items)
        corrected = any(_CORRECTION_MARK in _text_of(_get(it, "content")) for it in items
                        if _get(it, "role") == "system")
        arabic = bool(_ARABIC.search(text))
        guided_active, g_index, g_max = _guided_state(system_instructions)

        if _MEDICAL.search(text):
            return self._final(reply=prompts.MOCK_DOCTOR_AR if arabic else prompts.MOCK_DOCTOR_EN, intent="declined")
        if _INJECTION.search(text):
            return self._final(reply=prompts.MOCK_REFUSE_AR if arabic else prompts.MOCK_REFUSE_EN, intent="declined")

        if not calls:
            if _SAVE.search(text):
                ids = self._shown_earlier(system_instructions)
                return self._tool("save_wishlist", {"perfume_ids": ids[:3]})
            anchor = _anchor(text)
            if guided_active:
                prof = _profile_from_instructions(system_instructions)
                forced = bool(_FORCE_RE.search(system_instructions or ""))
                if forced:
                    if prof.anchor_perfume_id:
                        return self._tool("find_similar", {"perfume_id": prof.anchor_perfume_id,
                                                           "max_price": prof.budget_aed})
                    return self._tool("search_perfumes", filters_from_profile(prof, text))
                if anchor and not prof.anchor_perfume_id:
                    # "I like <perfume>": look it up so the next question can be built from its real notes.
                    return self._tool("get_perfume", {"name_or_id": anchor})
                q = _guided_question(prof, arabic, _guided_asked_ids(items, arabic))
                if _guided_signal_count(prof) >= 2 or g_index > g_max or q is None:
                    return self._tool("search_perfumes", filters_from_profile(prof, text))
                return self._final(reply="", question=q["reply"], topic=q["topic"], intent="chat",
                                   quick_replies=q["quick_replies"], multi_select=q["multi_select"])
            if anchor:
                return self._tool("get_perfume", {"name_or_id": anchor})
            return self._tool("search_perfumes", parse_filters(text))

        name, args, out = calls[-1]
        if name == "save_wishlist":
            if out.get("needs_consent"):
                reply = "هل تريد أن أحفظ هذه العطور في قائمة المفضلة؟" if arabic else "Shall I save these to your wishlist?"
                return self._final(reply=reply, intent="wishlist", ask_consent=True)
            reply = "تم الحفظ في قائمة المفضلة." if arabic else "Saved to your wishlist."
            return self._final(reply=reply, intent="wishlist")

        if name == "get_perfume":
            if not out.get("found"):
                return self._final(reply=prompts.MOCK_NOT_FOUND_AR if arabic else prompts.MOCK_NOT_FOUND_EN,
                                   intent="lookup")
            if guided_active:
                # Adaptive example from the PRD: ask what the shopper likes most about a perfume they named,
                # with quick_replies built from that perfume's real notes (a tool result, never invented).
                notes = ((out.get("key_notes_ar") if arabic else out.get("key_notes")) or out.get("key_notes") or [])[:4]
                reply = (f"ما الذي يعجبك أكثر في {out.get('name')}؟" if arabic else f"What do you like most about {out.get('name')}?")
                return self._final(reply="", question=reply, topic="anchor_feedback", intent="chat",
                                   quick_replies=notes, multi_select=False,
                                   profile_updates={"anchor_perfume_id": out.get("perfume_id"), "anchor_perfume": out.get("name")})
            if re.search(r"tell me about|what is|عن", text, re.I) and not re.search(r"similar|like|مثل|يشبه", text, re.I):
                return self._final(reply=self._describe(out, arabic), intent="lookup",
                                   chips=[f"more_like:{out['perfume_id']}"],
                                   profile_updates={})
            budget = parse_filters(text)["budget_aed"]
            return self._tool("find_similar", {"perfume_id": out["perfume_id"], "max_price": budget})

        if name in ("search_perfumes", "find_similar"):
            results = out.get("results") or []
            if not results:
                reply = ("لم أجد عطوراً تطابق كل هذه الشروط. هل نخفف أحدها، مثل الميزانية؟" if arabic else
                         "I couldn't find perfumes matching all of that. Shall we relax one filter, like the budget?")
                return self._final(reply=reply, intent="chat", chips=["cheaper", "lighter"])
            top = results[:3]
            picks = [{"perfume_id": r["perfume_id"], "reason": self._reason(r, arabic)} for r in top]
            if "MOCK_UNGROUNDED" in text and picks and (not corrected or "MOCK_UNGROUNDED_ALWAYS" in text):
                # `corrected` mirrors a real model taking the server's retry note ("use only ids your tools
                # returned") and fixing itself, so the retry path can be tested offline.
                picks[-1] = {"perfume_id": UNGROUNDED_ID, "reason": "Invented pick for testing."}
            first = top[0]
            feel = _feel(system_instructions)
            if feel:
                reply = (f"هذه الخيارات تليق بـ«{feel}». أقترح البدء بـ {first['name']} من {first.get('brand')}."
                         if arabic else
                         f"For \u201c{feel}\u201d, these three carry the mood. I would start with {first['name']} by "
                         f"{first.get('brand')}.")
            else:
                reply = (f"هذه الخيارات تناسب ما وصفته. أقترح البدء بـ {first['name']} من {first.get('brand')}."
                         if arabic else
                         f"These three share what you described. I would start with {first['name']} by {first.get('brand')}.")
            updates = {}
            if name == "search_perfumes":
                updates = {k: v for k, v in args.items() if k != "text" and v not in (None, [], "")}
            else:
                updates = {"anchor_perfume_id": args.get("perfume_id")}
            chips = ["less_sweet", "fresher", "cheaper", f"more_like:{top[0]['perfume_id']}"]
            return self._final(reply=reply, intent="recommend", picks=picks, chips=chips, profile_updates=updates)

        if name == "suggest_layering" and out.get("found"):
            partner = out["partner"]
            reply = (f"جرّب طبقة من {partner['name']}." if arabic else f"Try layering it with {partner['name']}.")
            return self._final(reply=reply, intent="recommend", layering={
                "base_perfume_id": out["base_perfume_id"], "partner_perfume_id": partner["perfume_id"],
                "reason": out.get("reason") or ""})
        return self._final(reply="كيف أساعدك في اختيار عطر؟" if arabic else "How can I help you choose a perfume?",
                           intent="chat")

    def stream_response(self, *args, **kwargs) -> AsyncIterator[Any]:
        raise NotImplementedError("MockModel does not stream")

    # ---- builders mirroring agents.models.chatcmpl_converter ------------------------------------------------
    @staticmethod
    def _tool(name: str, arguments: dict) -> ModelResponse:
        call = ResponseFunctionToolCall(
            id=FAKE_RESPONSES_ID,
            call_id=f"call_{uuid.uuid4().hex[:16]}",
            arguments=json.dumps(arguments, ensure_ascii=False),
            name=name,
            type="function_call",
        )
        return ModelResponse(output=[call], usage=Usage(), response_id=None)

    @staticmethod
    def _final(reply: str, intent: str, picks: list | None = None, chips: list | None = None, layering: dict | None = None,
               profile_updates: dict | None = None, ask_consent: bool = False, quick_replies: list | None = None,
               multi_select: bool = False, ask_reason: str | None = None, question: str | None = None,
               topic: str | None = None) -> ModelResponse:
        payload = {
            "reply": reply,
            "question": question,
            "topic": topic,
            "intent": intent,
            "picks": picks or [],
            "layering": layering,
            "chips": chips or [],
            "profile_updates": profile_updates or None,
            "ask_consent": ask_consent,
            "quick_replies": quick_replies or [],
            "multi_select": multi_select,
            "ask_reason": ask_reason,
        }
        msg = ResponseOutputMessage(
            id=FAKE_RESPONSES_ID,
            content=[ResponseOutputText(text=json.dumps(payload, ensure_ascii=False), type="output_text",
                                        annotations=[], logprobs=[])],
            role="assistant",
            status="completed",
            type="message",
        )
        return ModelResponse(output=[msg], usage=Usage(), response_id=None)

    # ---- wording ---------------------------------------------------------------------------------------------
    @staticmethod
    def _reason(r: dict, arabic: bool) -> str:
        if arabic:
            notes = "، ".join((r.get("key_notes_ar") or r.get("key_notes") or [])[:3])
            fam = r.get("family_ar") or tx.label("families", r.get("family") or "", "ar")
            return f"{r['name']} عطر {fam} بنفحات {notes}، قوته {r.get('strength')} من 5، والسعر {r.get('price')}."
        notes = ", ".join((r.get("key_notes") or [])[:3])
        return f"{r['name']} is a {r.get('family')} scent with {notes}, strength {r.get('strength')}/5, {r.get('price')}."

    @staticmethod
    def _describe(p: dict, arabic: bool) -> str:
        if arabic:
            notes = "، ".join((p.get("key_notes_ar") or p.get("key_notes") or [])[:4])
            return f"{p['name']} من {p.get('brand')}: عطر {p.get('family_ar') or p.get('family')} بنفحات {notes}، السعر {p.get('price')}."
        notes = ", ".join((p.get("key_notes") or [])[:4])
        return f"{p['name']} by {p.get('brand')} is a {p.get('family')} scent with {notes}, priced {p.get('price')}."

    @staticmethod
    def _shown_earlier(system_instructions: str | None) -> list[str]:
        m = re.search(r"Perfumes shown earlier \(JSON\): (\[.*\])", system_instructions or "")
        if not m:
            return []
        try:
            return [d["perfume_id"] for d in json.loads(m.group(1))]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []
