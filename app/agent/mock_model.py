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

UNGROUNDED_ID = "p_mock_ungrounded"

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
        arabic = bool(_ARABIC.search(text))

        if _MEDICAL.search(text):
            return self._final(reply=prompts.MOCK_DOCTOR_AR if arabic else prompts.MOCK_DOCTOR_EN, intent="declined")
        if _INJECTION.search(text):
            return self._final(reply=prompts.MOCK_REFUSE_AR if arabic else prompts.MOCK_REFUSE_EN, intent="declined")

        if not calls:
            if _SAVE.search(text):
                ids = self._shown_earlier(system_instructions)
                return self._tool("save_wishlist", {"perfume_ids": ids[:3]})
            anchor = _anchor(text)
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
            if "MOCK_UNGROUNDED" in text and picks:
                picks[-1] = {"perfume_id": UNGROUNDED_ID, "reason": "Invented pick for testing."}
            reply = "إليك ثلاثة خيارات تناسب ما وصفته." if arabic else "Here are three picks that match what you described."
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
               profile_updates: dict | None = None, ask_consent: bool = False) -> ModelResponse:
        payload = {
            "reply": reply,
            "intent": intent,
            "picks": picks or [],
            "layering": layering,
            "chips": chips or [],
            "profile_updates": profile_updates or None,
            "ask_consent": ask_consent,
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
