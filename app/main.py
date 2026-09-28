"""Perfume Selection Agent: FastAPI service serving the embeddable widget and the agent API."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent import extract as ex
from app.agent import images
from app.agent.cards import card, layering_card, template_reason
from app.agent.recommender import Catalogue, get_catalogue
from app.config import settings
from app.data import taxonomy as tx
from app.data.db import Database
from app.schemas import AgentReply, Chip, PerfumeCard, QuizQuestion, TasteProfile

log = logging.getLogger("perfume-agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).with_name("static")

try:  # the LLM layer is optional at runtime: without it the guided quiz and rule-based chat still work
    from app.agent import llm_agent
except Exception as exc:  # pragma: no cover
    llm_agent = None
    log.warning("LLM agent unavailable: %s", exc)

app = FastAPI(title="Perfume Selection Agent", version="0.1.0")
db = Database()


def _embedder():
    if not settings.embeddings_enabled:
        return None
    from openai import AzureOpenAI

    client = AzureOpenAI(api_key=settings.azure_openai_api_key, api_version=settings.azure_openai_api_version,
                         azure_endpoint=settings.azure_openai_endpoint)

    def embed(texts: list[str]):
        out = []
        for i in range(0, len(texts), 64):
            resp = client.embeddings.create(model=settings.azure_openai_embed_deployment, input=texts[i:i + 64])
            out.extend([d.embedding for d in resp.data])
        return out

    return embed


catalogue: Catalogue = get_catalogue(db, _embedder())
log.info("catalogue loaded: %d perfumes, llm=%s, embeddings=%s", len(catalogue.ids), settings.llm_enabled, catalogue.embeddings is not None)

# ----------------------------------------------------------------------------- i18n
T = {
    "en": {
        "greeting": "Hi! I'm your perfume advisor. Tell me what you like in your own words, or answer 5 quick questions.",
        "q_liked": "Which scents do you love?", "q_disliked": "Anything you dislike?", "q_mood": "What mood are you after?",
        "q_strength": "How strong should it be?", "q_budget": "Budget per bottle?", "none": "Nothing in particular", "no_budget": "No limit",
        "skip": "Skip", "under": "Under AED {n}",
        "results": "Here are 3 picks for you, plus one to layer with the first.",
        "results_anchor": "Based on {name}, here are 3 close matches, plus one to layer with the first.",
        "not_found": "I can't find \"{name}\" in my catalogue, so I won't guess about it. Tell me what you like about it (notes, mood) and I'll find close matches.",
        "declined_medical": "I can't give medical or allergy advice. Please check the ingredient list on the product and ask a doctor or pharmacist.",
        "declined_injection": "I can only help with perfume advice and I stick to my rules. What kind of scent are you after?",
        "declined_offtopic": "I'm a perfume advisor, so that's outside what I can help with. Want a recommendation?",
        "declined_brand": "This advisor covers {brand} only. Tell me what you like and I'll pick from their range.",
        "ask_consent": "Save these to a wishlist for this session? Reply yes to confirm.",
        "saved": "Saved {n} to your wishlist.", "not_saved": "Okay, nothing saved.",
        "refined": "Refined. Here are 3 new picks.",
        "no_results": "Nothing matches all of that. Try loosening the budget or the dislikes.",
        "chips": {"less_sweet": "Less sweet", "fresher": "Fresher", "cheaper": "Cheaper", "stronger": "Stronger", "lighter": "Lighter", "more_like": "More like {n}"},
        "fallback_note": "AI is resting; these picks are rule-based.",
    },
    "ar": {
        "greeting": "أهلاً! أنا مستشار العطور. صف لي ما تحبه بكلماتك، أو أجب عن 5 أسئلة سريعة.",
        "q_liked": "ما الروائح التي تحبها؟", "q_disliked": "هل هناك ما لا تحبه؟", "q_mood": "ما المزاج الذي تبحث عنه؟",
        "q_strength": "ما مدى قوة العطر؟", "q_budget": "الميزانية للزجاجة؟", "none": "لا شيء محدد", "no_budget": "بدون حد",
        "skip": "تخطي", "under": "أقل من {n} درهم",
        "results": "إليك 3 ترشيحات، مع عطر لتطبيقه فوق الأول.",
        "results_anchor": "بناءً على {name}، إليك 3 عطور قريبة منه، مع عطر لتطبيقه فوق الأول.",
        "not_found": "لا أجد \"{name}\" في الكتالوج، ولن أخمن عنه. أخبرني بما يعجبك فيه (النفحات، المزاج) وسأجد عطوراً قريبة.",
        "declined_medical": "لا أستطيع تقديم نصائح طبية أو عن الحساسية. راجع قائمة المكونات على المنتج واستشر طبيباً أو صيدلياً.",
        "declined_injection": "أساعد في اختيار العطور فقط وألتزم بقواعدي. ما نوع العطر الذي تبحث عنه؟",
        "declined_offtopic": "أنا مستشار عطور، وهذا خارج ما أستطيع المساعدة فيه. هل تريد ترشيحاً؟",
        "declined_brand": "هذا المستشار يغطي {brand} فقط. أخبرني بما تحب وسأختار من مجموعتهم.",
        "ask_consent": "هل أحفظ هذه في قائمة أمنياتك لهذه الجلسة؟ أجب بنعم للتأكيد.",
        "saved": "تم حفظ {n} في قائمة أمنياتك.", "not_saved": "حسناً، لم يُحفظ شيء.",
        "refined": "تم التعديل. إليك 3 ترشيحات جديدة.",
        "no_results": "لا يوجد ما يطابق كل ذلك. جرّب توسيع الميزانية أو تقليل الاستثناءات.",
        "chips": {"less_sweet": "أقل حلاوة", "fresher": "أكثر انتعاشاً", "cheaper": "أرخص", "stronger": "أقوى", "lighter": "أخف", "more_like": "مثل رقم {n}"},
        "fallback_note": "الذكاء الاصطناعي يستريح؛ هذه الترشيحات مبنية على القواعد.",
    },
}
QUIZ_NOTES = ["vanilla", "oud", "rose", "musk", "jasmine", "bergamot", "sandalwood", "amber", "coffee", "berries", "sea notes", "lavender", "incense", "tobacco", "peach", "tea"]
BUDGETS = [150, 300, 500, 1000]


def lang_of(text: str | None, fallback: str) -> str:
    if text and re.search(r"[؀-ۿ]", text):
        return "ar"
    if text and re.search(r"[A-Za-z]{3,}", text) and not re.search(r"[؀-ۿ]", text):
        return "en"
    return fallback if fallback in T else "en"


def quiz(lang: str) -> list[QuizQuestion]:
    t = T[lang]
    notes = [Chip(id=n, label=tx.note_label(n, lang)) for n in QUIZ_NOTES]
    return [
        QuizQuestion(id="liked_notes", question=t["q_liked"], multi=True, options=notes + [Chip(id="skip", label=t["skip"])]),
        QuizQuestion(id="disliked_notes", question=t["q_disliked"], multi=True, options=notes + [Chip(id="skip", label=t["none"])]),
        QuizQuestion(id="mood", question=t["q_mood"], multi=False, options=[Chip(id=m, label=tx.label("moods", m, lang)) for m in tx.load()["moods"]]),
        QuizQuestion(id="strength", question=t["q_strength"], multi=False, options=[Chip(id=str(i), label=tx.label("strengths", i, lang)) for i in range(1, 6)]),
        QuizQuestion(id="budget", question=t["q_budget"], multi=False, options=[Chip(id=str(b), label=t["under"].format(n=b)) for b in BUDGETS] + [Chip(id="0", label=t["no_budget"])]),
    ]


def refine_chips(lang: str, picks: list[PerfumeCard]) -> list[Chip]:
    c = T[lang]["chips"]
    chips = [Chip(id=k, label=c[k]) for k in ("less_sweet", "fresher", "cheaper", "stronger", "lighter")]
    chips += [Chip(id=f"more_like:{p.perfume_id}", label=c["more_like"].format(n=i + 1)) for i, p in enumerate(picks[:3])]
    return chips


# ----------------------------------------------------------------------------- rate limit
_buckets: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now = time.time()
    q = _buckets[ip]
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_minute:
        raise HTTPException(429, "Too many requests, slow down a little.")
    q.append(now)


# ----------------------------------------------------------------------------- session helpers
class SessionBody(BaseModel):
    lang: str | None = None
    session_id: str | None = None   # resume an earlier session (the widget stores it locally)


class ChatBody(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)
    lang: str | None = None


class QuizBody(BaseModel):
    session_id: str
    answers: dict
    lang: str | None = None


class RefineBody(BaseModel):
    session_id: str
    chip: str
    lang: str | None = None


class WishlistBody(BaseModel):
    session_id: str
    perfume_ids: list[str]
    consent: bool = False


class FeedbackBody(BaseModel):
    session_id: str
    perfume_id: str
    thumbs: int | None = None
    clicked: bool = False


class EventBody(BaseModel):
    session_id: str | None = None
    name: str = Field(max_length=64)
    props: dict = Field(default_factory=dict)


def load_session(session_id: str) -> dict:
    s = db.get_session(session_id)
    if not s:
        raise HTTPException(404, "Unknown session; start a new one.")
    s["profile"].setdefault("taste", {})
    s["profile"].setdefault("pending_consent", [])
    return s


def taste(s: dict) -> TasteProfile:
    return TasteProfile(**s["profile"]["taste"])


def set_taste(s: dict, p: TasteProfile) -> None:
    s["profile"]["taste"] = p.model_dump()


def brand_block(lang: str, text: str) -> str | None:
    if not settings.brand_filter:
        return None
    other = [b for b in {p["brand_name"] for p in catalogue.perfumes.values()} if b.lower() != settings.brand_filter.lower()]
    for b in other:
        if len(b) >= 4 and re.search(rf"\b{re.escape(b)}\b", text, re.I):
            return T[lang]["declined_brand"].format(brand=settings.brand_filter)
    return None


# ----------------------------------------------------------------------------- recommendation assembly
def apply_hard(prof: TasteProfile, hard: TasteProfile) -> TasteProfile:
    """Merges deterministic constraints into a profile and removes contradictions in the constraints' favour."""
    prof = prof.merge(hard)
    prof.liked_notes = [n for n in prof.liked_notes if n not in prof.disliked_notes]
    prof.families = [f for f in prof.families if f not in prof.avoid_families]
    return prof


def match_scores(ranked: list[dict], ids: list[str]) -> dict[str, int]:
    """Maps raw hybrid scores to a 45..97 display range: part absolute score, part rank within this query's pool."""
    if not ranked:
        return {i: 60 for i in ids}
    scores = [r["score"] for r in ranked]
    lo, hi = min(scores), max(scores)
    by_id = {r["perfume"]["perfume_id"]: r["score"] for r in ranked}
    out = {}
    for i in ids:
        sc = by_id.get(i, lo)
        rel = (sc - lo) / (hi - lo) if hi > lo else 1.0
        absolute = min(1.0, sc / 0.85)
        out[i] = int(round(45 + 52 * (0.4 * rel + 0.6 * absolute)))
    return out


def build_results(s: dict, prof: TasteProfile, text: str | None, lang: str, reasons: dict[str, str] | None = None,
                  exclude: list[str] = (), intro: str | None = None, fallback: bool = False) -> AgentReply:
    res = catalogue.recommend(prof, text, k=3) if not exclude else {"picks": catalogue.search(prof, text, limit=3, exclude_ids=exclude), "layering": None}
    if exclude and not res["picks"]:
        res = catalogue.recommend(prof, text, k=3)
    elif exclude and res["picks"]:
        res["layering"] = catalogue.layering_partner(res["picks"][0]["perfume"]["perfume_id"], prof)
    picks: list[PerfumeCard] = []
    pool = catalogue.search(prof, text, limit=40, exclude_ids=exclude)
    ms = match_scores(pool, [r["perfume"]["perfume_id"] for r in res["picks"]])
    for r in res["picks"]:
        p = r["perfume"]
        reason = (reasons or {}).get(p["perfume_id"]) or template_reason(p, prof, lang)
        c = card(p, lang, None, reason)
        c.match_score = ms.get(p["perfume_id"], 60)
        picks.append(c)
        images.request_generation(p)
    layering = None
    if res["layering"] and picks:
        layering = layering_card(picks[0].perfume_id, res["layering"], lang, picks[0].name)
        images.request_generation(res["layering"]["perfume"])
    if not picks:
        db.add_review("zero_results", {"text": text, "profile": prof.model_dump(exclude_defaults=True), "lang": lang})
        reply = T[lang]["no_results"]
    else:
        reply = intro or T[lang]["results"]
    s["last_results"] = [p.perfume_id for p in picks]
    db.add_event(s["session_id"], "results_shown", {"n": len(picks), "fallback": fallback})
    return AgentReply(session_id=s["session_id"], language=lang, reply=reply, picks=picks, layering=layering,
                      chips=refine_chips(lang, picks) if picks else [], fallback_used=fallback,
                      intent="recommend", profile=prof)


def next_question(prof: TasteProfile, lang: str) -> QuizQuestion | None:
    qs = {q.id: q for q in quiz(lang)}
    if not prof.liked_notes and not prof.families and not prof.anchor_perfume:
        return qs["liked_notes"]
    if not prof.disliked_notes and not prof.avoid_families:
        return qs["disliked_notes"]
    if not prof.moods and not prof.occasions:
        return qs["mood"]
    if prof.strength is None:
        return qs["strength"]
    if prof.budget_aed is None:
        return qs["budget"]
    return None


def resolve_anchor(prof: TasteProfile, lang: str) -> tuple[TasteProfile, str | None, str | None]:
    """Returns (profile, intro text, not-found reply)."""
    if not prof.anchor_perfume:
        return prof, None, None
    p = catalogue.find_by_name(prof.anchor_perfume)
    if not p:
        db.add_review("zero_results", {"anchor": prof.anchor_perfume, "lang": lang})
        return prof, None, T[lang]["not_found"].format(name=prof.anchor_perfume)
    prof.anchor_perfume_id = p["perfume_id"]
    prof.anchor_perfume = p["name"]
    if prof.anchor_cheaper and p.get("price_aed"):
        prof.budget_aed = float(p["price_aed"]) - 1
    return prof, T[lang]["results_anchor"].format(name=p["name"]), None


def rule_based_chat(s: dict, text: str, lang: str, fallback: bool) -> AgentReply:
    prof = taste(s).merge(ex.extract_profile(text))
    prof, intro, not_found = resolve_anchor(prof, lang)
    set_taste(s, prof)
    if not_found:
        prof.anchor_perfume, prof.anchor_cheaper = None, False  # never carry an unresolved name into later turns
        set_taste(s, prof)
        return AgentReply(session_id=s["session_id"], language=lang, reply=not_found, intent="lookup", profile=prof,
                          next_question=None, fallback_used=fallback)
    if ex.wants_wishlist(text) and s.get("last_results"):
        s["profile"]["pending_consent"] = list(s["last_results"])
        return AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["ask_consent"], intent="wishlist", profile=prof, fallback_used=fallback)
    asked = (ex.wants_recommendation(text) and prof.signal_count() >= 1) or prof.anchor_perfume_id
    q = next_question(prof, lang)
    if prof.signal_count() >= 2 or asked or q is None:
        return build_results(s, prof, text, lang, intro=intro, fallback=fallback)
    reply = (T[lang]["fallback_note"] + " " if fallback else "") + q.question
    return AgentReply(session_id=s["session_id"], language=lang, reply=reply, next_question=q, intent="chat",
                      profile=prof, fallback_used=fallback)


# ----------------------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    return {"ok": True, "perfumes": len(catalogue.ids), "llm": settings.llm_enabled, "provider": settings.llm_provider,
            "embeddings": catalogue.embeddings is not None, "brand_filter": settings.brand_filter or None}


@app.post("/api/session")
def create_session(body: SessionBody, request: Request):
    rate_limit(request)
    lang = body.lang if body.lang in T else settings.default_lang if settings.default_lang in T else "en"
    s = db.get_session(body.session_id) if body.session_id else None
    if s:
        s["language"] = lang
        db.save_session(s)
        db.add_event(s["session_id"], "session_resumed", {"lang": lang})
    else:
        s = db.create_session(lang)
        db.add_event(s["session_id"], "session_started", {"lang": lang})
    return {"session_id": s["session_id"], "language": lang, "greeting": T[lang]["greeting"],
            "quiz": [q.model_dump() for q in quiz(lang)], "brand_filter": settings.brand_filter}


@app.post("/api/chat")
async def chat(body: ChatBody, request: Request):
    rate_limit(request)
    s = load_session(body.session_id)
    lang = lang_of(body.message, body.lang or s["language"])
    s["language"] = lang
    text = body.message.strip()
    db.add_event(s["session_id"], "chat_message_sent", {"len": len(text), "lang": lang})
    s["history"].append({"role": "user", "text": text})

    reply: AgentReply | None = None
    # Consent round-trip for the wishlist (PRD: actions need an explicit yes).
    pending = s["profile"].get("pending_consent") or []
    if pending:
        if ex.says_yes(text):
            db.add_wishlist(s["session_id"], pending)
            s["consent_wishlist"] = 1
            db.add_event(s["session_id"], "wishlist_saved", {"n": len(pending)})
            reply = AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["saved"].format(n=len(pending)), intent="wishlist", profile=taste(s))
        elif re.fullmatch(r"\s*(no|nope|don't|do not|لا|كلا)[.! ]*\s*", text, re.I):
            reply = AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["not_saved"], intent="chat", profile=taste(s))
        s["profile"]["pending_consent"] = []

    # Cheap deterministic guardrails before any model call.
    if reply is None:
        blocked = brand_block(lang, text)
        if ex.is_injection(text):
            reply = AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["declined_injection"], intent="declined", profile=taste(s))
        elif ex.is_medical(text):
            reply = AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["declined_medical"], intent="declined", profile=taste(s))
        elif blocked:
            reply = AgentReply(session_id=s["session_id"], language=lang, reply=blocked, intent="declined", profile=taste(s))
        elif ex.is_off_topic(text):
            reply = AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["declined_offtopic"], intent="declined", profile=taste(s))

    if reply is None and settings.llm_enabled and llm_agent is not None:
        reply = await llm_chat(s, text, lang)

    if reply is None:
        reply = rule_based_chat(s, text, lang, fallback=bool(settings.llm_enabled))
        if reply.fallback_used:
            db.add_event(s["session_id"], "fallback_used", {})

    s["history"].append({"role": "assistant", "text": reply.reply})
    db.save_session(s)
    return reply


async def llm_chat(s: dict, text: str, lang: str) -> AgentReply | None:
    """Runs the Agents SDK agent; returns None when the caller should fall back to rules."""
    prof = taste(s)
    hard = ex.extract_profile(text)  # high-precision negations, budgets and strength are enforced even if the model misses them
    hard_only = TasteProfile(disliked_notes=hard.disliked_notes, avoid_families=hard.avoid_families, budget_aed=hard.budget_aed,
                             strength=hard.strength, seasons=hard.seasons, occasions=hard.occasions)
    if hard.anchor_perfume:
        anchor = catalogue.find_by_name(hard.anchor_perfume)
        if anchor:
            hard_only.anchor_perfume, hard_only.anchor_perfume_id = anchor["name"], anchor["perfume_id"]
            if hard.anchor_cheaper and anchor.get("price_aed"):
                hard_only.budget_aed = float(anchor["price_aed"]) - 1
        elif ex.is_lookup(text):
            # Explicit "tell me about X" for something not in the catalogue: answer deterministically, never guess.
            db.add_review("zero_results", {"anchor": hard.anchor_perfume, "lang": lang})
            return AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["not_found"].format(name=hard.anchor_perfume),
                              intent="lookup", profile=prof)
    prof = apply_hard(prof, hard_only)
    ctx = llm_agent.AgentContext(session_id=s["session_id"], language=lang, profile=prof, db=db, catalogue=catalogue,
                                 seen_ids=set(s.get("last_results") or []), wishlist_consent=bool(s.get("consent_wishlist")),
                                 brand_filter=settings.brand_filter, last_results=list(s.get("last_results") or []))
    try:
        result = await asyncio.wait_for(llm_agent.run_agent(ctx, text, s["history"][:-1]), timeout=45)
    except Exception as exc:
        log.warning("agent failed: %s", exc)
        db.add_review("agent_error", {"error": str(exc)[:300]})
        return None
    if result.error or result.output is None:
        log.warning("agent error=%s", result.error)
        db.add_review("agent_error", {"error": str(result.error)[:300]})
        return None
    out = result.output
    db.add_event(s["session_id"], "agent_turn", {"tools": result.tool_calls, "intent": out.intent, "grounding_failed": result.grounding_failed, "dropped": result.dropped_ids})
    if result.grounding_failed and not out.picks and out.intent == "recommend":
        return None  # the model invented every pick: use the rule-based picks instead
    prof = apply_hard(result.profile or prof, hard_only)  # the user's own negations always win over the model
    if prof.anchor_perfume and not prof.anchor_perfume_id:
        prof, _, _ = resolve_anchor(prof, lang)
    set_taste(s, prof)
    picks: list[PerfumeCard] = []
    for pick in out.picks[:3]:
        p = catalogue.get(pick.perfume_id)
        if p and catalogue.passes(p, prof):
            picks.append(card(p, lang, None, pick.reason))
            images.request_generation(p)
        elif p:
            db.add_review("constraint_violation", {"perfume_id": p["perfume_id"], "session_id": s["session_id"]})
    if out.intent == "recommend" and 0 < len(picks) < 3:
        # Top up with our own ranking so the results card always shows 3 grounded picks.
        for r in catalogue.search(prof, text, limit=3 - len(picks), exclude_ids=[c.perfume_id for c in picks]):
            picks.append(card(r["perfume"], lang, r["score"], template_reason(r["perfume"], prof, lang)))
    if picks:
        ms = match_scores(catalogue.search(prof, text, limit=40), [c.perfume_id for c in picks])
        for c in picks:
            c.match_score = ms.get(c.perfume_id, 60)
    layering = None
    if out.layering and picks:
        partner = catalogue.get(out.layering.partner_perfume_id)
        base = catalogue.get(out.layering.base_perfume_id) or catalogue.get(picks[0].perfume_id)
        if partner and base:
            layering = layering_card(base["perfume_id"], {"perfume": partner, "reason_en": out.layering.reason, "reason_ar": out.layering.reason}, lang, base["name"])
    elif picks:
        lp = catalogue.layering_partner(picks[0].perfume_id, prof)
        if lp:
            layering = layering_card(picks[0].perfume_id, lp, lang, picks[0].name)
    if picks:
        s["last_results"] = [p.perfume_id for p in picks]
        db.add_event(s["session_id"], "results_shown", {"n": len(picks), "fallback": False})
    if getattr(out, "ask_consent", False) and s.get("last_results"):
        s["profile"]["pending_consent"] = list(s["last_results"])
    chips = refine_chips(lang, picks) if picks else []
    return AgentReply(session_id=s["session_id"], language=lang, reply=out.reply, picks=picks, layering=layering, chips=chips,
                      intent=out.intent, profile=prof)


@app.post("/api/quiz")
def quiz_submit(body: QuizBody, request: Request):
    rate_limit(request)
    s = load_session(body.session_id)
    lang = body.lang if body.lang in T else s["language"]
    a = body.answers or {}
    prof = taste(s)
    prof.liked_notes = [n for n in a.get("liked_notes", []) if n != "skip" and tx.normalise_note(n)]
    prof.disliked_notes = [n for n in a.get("disliked_notes", []) if n != "skip" and tx.normalise_note(n)]
    moods = a.get("moods") or ([a["mood"]] if a.get("mood") else [])
    prof.moods = [m for m in moods if m in tx.load()["moods"]]
    try:
        prof.strength = int(a["strength"]) if a.get("strength") not in (None, "", "skip") else None
    except (TypeError, ValueError):
        prof.strength = None
    try:
        b = float(a.get("budget_aed") or 0)
        prof.budget_aed = b if b > 0 else None
    except (TypeError, ValueError):
        prof.budget_aed = None
    set_taste(s, prof)
    db.add_event(s["session_id"], "quiz_completed", {})
    reply = build_results(s, prof, None, lang)
    s["history"].append({"role": "assistant", "text": reply.reply})
    db.save_session(s)
    return reply


@app.post("/api/refine")
def refine(body: RefineBody, request: Request):
    rate_limit(request)
    s = load_session(body.session_id)
    lang = body.lang if body.lang in T else s["language"]
    prof = taste(s)
    chip = body.chip
    last = list(s.get("last_results") or [])
    exclude = last
    if chip == "less_sweet":
        prof.avoid_families = list(dict.fromkeys(prof.avoid_families + ["gourmand"]))
        prof.families = [f for f in prof.families if f != "gourmand"]
        prof.disliked_notes = list(dict.fromkeys(prof.disliked_notes + ["sugar", "caramel"]))
    elif chip == "fresher":
        prof.families = list(dict.fromkeys(["fresh"] + prof.families))
        prof.moods = list(dict.fromkeys(["energetic"] + prof.moods))
        prof.avoid_families = [f for f in prof.avoid_families if f != "fresh"]
    elif chip == "cheaper":
        prices = [catalogue.get(pid)["price_aed"] for pid in last if catalogue.get(pid) and catalogue.get(pid)["price_aed"]]
        cap = (max(prices) if prices else (prof.budget_aed or 500)) * 0.6
        prof.budget_aed = max(50.0, round(cap / 10) * 10)
    elif chip == "stronger":
        prof.strength = min(5, (prof.strength or 3) + 1)
    elif chip == "lighter":
        prof.strength = max(1, (prof.strength or 3) - 1)
    elif chip.startswith("more_like:"):
        pid = chip.split(":", 1)[1]
        if catalogue.get(pid):
            prof.anchor_perfume_id = pid
            prof.anchor_perfume = catalogue.get(pid)["name"]
            exclude = [x for x in last if x != pid] + [pid]
    else:
        raise HTTPException(400, "Unknown chip")
    set_taste(s, prof)
    db.add_event(s["session_id"], "refine_used", {"chip": chip.split(":")[0]})
    reply = build_results(s, prof, prof.free_text or None, lang, exclude=exclude, intro=T[lang]["refined"])
    if chip == "cheaper" and len(reply.picks) < 3:
        prices = [catalogue.get(pid)["price_aed"] for pid in last if catalogue.get(pid) and catalogue.get(pid)["price_aed"]]
        if prices:
            prof.budget_aed = max(prices) - 1  # at least cheaper than the priciest pick shown
            set_taste(s, prof)
            reply = build_results(s, prof, prof.free_text or None, lang, exclude=exclude, intro=T[lang]["refined"])
    s["history"].append({"role": "assistant", "text": reply.reply})
    db.save_session(s)
    return reply


@app.post("/api/wishlist")
def wishlist_add(body: WishlistBody, request: Request):
    rate_limit(request)
    s = load_session(body.session_id)
    if not body.consent:
        raise HTTPException(400, "Consent required to save a wishlist.")
    ids = [pid for pid in body.perfume_ids if catalogue.get(pid)]
    db.add_wishlist(s["session_id"], ids)
    s["consent_wishlist"] = 1
    db.save_session(s)
    db.add_event(s["session_id"], "wishlist_saved", {"n": len(ids)})
    return {"wishlist": [card(catalogue.get(pid), s["language"]).model_dump() for pid in db.get_wishlist(s["session_id"]) if catalogue.get(pid)]}


@app.get("/api/wishlist")
def wishlist_get(session_id: str):
    s = load_session(session_id)
    return {"wishlist": [card(catalogue.get(pid), s["language"]).model_dump() for pid in db.get_wishlist(session_id) if catalogue.get(pid)]}


@app.post("/api/feedback")
def feedback(body: FeedbackBody, request: Request):
    rate_limit(request)
    load_session(body.session_id)
    if body.thumbs not in (None, 1, -1):
        raise HTTPException(400, "thumbs must be 1, -1 or null")
    db.add_feedback(body.session_id, body.perfume_id, body.thumbs, body.clicked)
    db.add_event(body.session_id, "pick_clicked" if body.clicked else "feedback_given", {"perfume_id": body.perfume_id, "thumbs": body.thumbs})
    return {"ok": True}


@app.post("/api/events")
def events(body: EventBody, request: Request):
    rate_limit(request)
    db.add_event(body.session_id, re.sub(r"[^a-z_]", "", body.name.lower())[:64] or "unknown", body.props)
    return {"ok": True}


@app.get("/api/perfume/{perfume_id}")
def perfume(perfume_id: str, lang: str = "en"):
    p = catalogue.get(perfume_id)
    if not p:
        raise HTTPException(404, "Not found")
    return card(p, lang if lang in T else "en").model_dump()


@app.get("/api/image/{perfume_id}")
def image(perfume_id: str):
    pid = perfume_id.removesuffix(".svg").removesuffix(".png")
    p = catalogue.get(pid)
    if not p:
        raise HTTPException(404, "Not found")
    png = images.cached_png(pid)
    if png:
        return FileResponse(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
    images.request_generation(p)
    return Response(images.svg_for(p), media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=600"})


@app.get("/api/admin/summary")
def admin_summary(authorization: str = Header(default="")):
    if authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(401, "Unauthorized")
    return db.admin_summary()


@app.post("/api/admin/reload")
def admin_reload(authorization: str = Header(default="")):
    if authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(401, "Unauthorized")
    catalogue.reload()
    return {"ok": True, "perfumes": len(catalogue.ids)}


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def any_error(_: Request, exc: Exception):
    log.exception("unhandled error")
    db.add_event(None, "error_shown", {"error": str(exc)[:200]})
    return JSONResponse({"error": "Something went wrong. Please try again."}, status_code=500)


if STATIC_DIR.exists():
    @app.get("/widget.js")
    def widget_js():
        return FileResponse(STATIC_DIR / "widget.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
