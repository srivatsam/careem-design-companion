"""Perfume Selection Agent: FastAPI service serving the embeddable widget and the agent API."""
from __future__ import annotations

import asyncio
import hashlib
import json
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
from app.agent.recommender import Catalogue, get_catalogue, normalize_brand
from app.config import settings
from app.data import scenarios as sc
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

# Interactive API reference lives under /api so /docs can serve the client project guide (app/static/docs).
app = FastAPI(title="Perfume Selection Agent", version="0.1.0",
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
              swagger_ui_oauth2_redirect_url=None)
db = Database()


# ----------------------------------------------------------------------------- usage tracking
TRACKED_PATHS = {"/api/chat", "/api/refine", "/api/quiz", "/api/guide/start", "/api/guide/finish"}
_IPV4_PORT = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3}):\d+$")
_IPV6_PORT = re.compile(r"^\[(.+)\]:\d+$")


def client_ip(request: Request) -> str:
    """Caller address without the port (Azure App Service sends "ip:port" in X-Forwarded-For)."""
    raw = request.headers.get("x-forwarded-for", request.client.host if request.client else "?")
    ip = raw.split(",")[0].strip()
    m = _IPV4_PORT.match(ip) or _IPV6_PORT.match(ip)
    return m.group(1) if m else ip


def visitor_id_for(request: Request) -> str:
    """Anonymous, stable id for one person's browser: a salted hash, so the address itself is never stored."""
    salt = settings.admin_token or "psa"
    raw = f"{salt}|{client_ip(request)}|{request.headers.get('user-agent', '')}"
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:12]


def _tracked_user_text(path: str, body: dict) -> str:
    if path == "/api/chat":
        return str(body.get("message") or "")
    if path == "/api/refine":
        return f"[refine] {body.get('chip') or ''}"
    if path == "/api/quiz":
        return "[quiz] " + json.dumps(body.get("answers") or {}, ensure_ascii=False)[:500]
    return "[guided: start]" if path == "/api/guide/start" else "[guided: show my picks now]"


@app.middleware("http")
async def track_usage(request: Request, call_next):
    if request.method != "POST" or request.url.path not in TRACKED_PATHS:
        return await call_next(request)
    started = time.time()
    raw_request = await request.body()
    response = await call_next(request)
    chunks = [chunk async for chunk in response.body_iterator]
    raw_response = b"".join(chunks)
    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    rebuilt = Response(content=raw_response, status_code=response.status_code, headers=headers,
                       media_type=response.media_type)
    try:
        if response.status_code == 200:
            body, out = json.loads(raw_request or b"{}"), json.loads(raw_response or b"{}")
            if isinstance(body, dict) and isinstance(out, dict):
                path = request.url.path
                picks = [{"perfume_id": p.get("perfume_id"), "name": p.get("name"), "brand": p.get("brand")}
                         for p in (out.get("picks") or []) if isinstance(p, dict)]
                user_text = _tracked_user_text(path, body)
                visitor = visitor_id_for(request)
                ms = int((time.time() - started) * 1000)
                db.add_chat_log(session_id=body.get("session_id"), visitor_id=visitor, endpoint=path,
                                lang=out.get("language"), user_text=user_text, reply_text=out.get("reply"),
                                question_text=(out.get("next_question") or {}).get("question"),
                                intent=out.get("intent"), picks=picks, fallback_used=out.get("fallback_used"),
                                latency_ms=ms)
                shown = re.sub(r"\s+", " ", user_text)[:200].replace('"', "'")
                log.info('usage visitor=%s session=%s endpoint=%s lang=%s intent=%s picks=%d ms=%d text="%s"',
                         visitor, body.get("session_id"), path, out.get("language"), out.get("intent"),
                         len(picks), ms, shown)
    except Exception:  # tracking never changes or blocks a reply
        log.warning("usage tracking skipped for one turn", exc_info=True)
    return rebuilt


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
        "picks_template": "Here are 3 picks that match what you described. I would start with {name} by {brand}.",
        "start_with": "I would start with {name} by {brand}.",
        "picks_template_anchor": "Here are 3 picks close to {anchor}. I would start with {name} by {brand}.",
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
        "g_q_for": "Who is this perfume for?",
        "g_for_me": "For me", "g_gift_her": "A gift for her", "g_gift_him": "A gift for him", "g_gift_unsure": "A gift, unsure of their taste",
        "g_for_label": {"self": "me", "gift_her": "a gift for her", "gift_him": "a gift for him", "gift_unsure": "a gift"},
        "g_sum_for": "For: {v}", "g_sum_loves": "Loves: {v}", "g_sum_avoid": "Avoid: {v}", "g_sum_mood": "Mood: {v}", "g_sum_budget": "Budget: AED {v}",
        "g_sum_like": "Like: {v}", "g_sum_occasion": "Occasion: {v}", "g_sum_strength": "Strength: {v}",
        "g_intro": "Let's find the right pick together.", "g_show_picks": "Show my picks now, please.",
        "g_finished": "Here's what I learned about you, and three picks that fit.",
        "g_finished_feel": "Here are three picks made for \u201c{v}\u201d, shaped by everything you told me.",
        "g_q_scenario": {"self": "Pick the moments you want this scent for",
                         "gift_her": "Pick the moments you picture her wearing it",
                         "gift_him": "Pick the moments you picture him wearing it",
                         "gift_unsure": "Pick the moments you picture them wearing it"},
        "g_scenario_hint": "Choose up to three.",
        "g_q_moment": "Which {v} moment feels just right?",
        "g_q_moment_multi": "Starting with the {v}, which moment feels just right?",
        "g_sum_feel": "Feel: {v}",
    },
    "ar": {
        "greeting": "أهلاً! أنا مستشار العطور. صف لي ما تحبه بكلماتك، أو أجب عن 5 أسئلة سريعة.",
        "q_liked": "ما الروائح التي تحبها؟", "q_disliked": "هل هناك ما لا تحبه؟", "q_mood": "ما المزاج الذي تبحث عنه؟",
        "q_strength": "ما مدى قوة العطر؟", "q_budget": "الميزانية للزجاجة؟", "none": "لا شيء محدد", "no_budget": "بدون حد",
        "skip": "تخطي", "under": "أقل من {n} درهم",
        "results": "إليك 3 ترشيحات، مع عطر لتطبيقه فوق الأول.",
        "results_anchor": "بناءً على {name}، إليك 3 عطور قريبة منه، مع عطر لتطبيقه فوق الأول.",
        "picks_template": "إليك 3 ترشيحات تناسب ما وصفته. أقترح البدء بـ {name} من {brand}.",
        "start_with": "أقترح البدء بـ {name} من {brand}.",
        "picks_template_anchor": "إليك 3 ترشيحات قريبة من {anchor}. أقترح البدء بـ {name} من {brand}.",
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
        "g_q_for": "لمن هذا العطر؟",
        "g_for_me": "لي أنا", "g_gift_her": "هدية لها", "g_gift_him": "هدية له", "g_gift_unsure": "هدية، ولا أعرف ذوقها بدقة",
        "g_for_label": {"self": "لي", "gift_her": "هدية لها", "gift_him": "هدية له", "gift_unsure": "هدية"},
        "g_sum_for": "لمن: {v}", "g_sum_loves": "يحب: {v}", "g_sum_avoid": "يتجنب: {v}", "g_sum_mood": "المزاج: {v}", "g_sum_budget": "الميزانية: {v} درهم",
        "g_sum_like": "مثل: {v}", "g_sum_occasion": "المناسبة: {v}", "g_sum_strength": "القوة: {v}",
        "g_intro": "لنجد الاختيار المناسب معاً.", "g_show_picks": "أرني ترشيحاتي الآن من فضلك.",
        "g_finished": "إليك ما تعلمته عنك، وثلاثة اختيارات تناسبك.",
        "g_finished_feel": "إليك ثلاثة اختيارات صُمّمت لـ«{v}»، بناءً على كل ما أخبرتني به.",
        "g_q_scenario": {"self": "اختر اللحظات التي تريد أن يرافقك فيها هذا العطر",
                         "gift_her": "اختر اللحظات التي تتخيلها فيها بهذا العطر",
                         "gift_him": "اختر اللحظات التي تتخيله فيها بهذا العطر",
                         "gift_unsure": "اختر اللحظات التي تتخيل فيها صاحب الهدية بهذا العطر"},
        "g_scenario_hint": "اختر حتى ثلاث لحظات.",
        "g_q_moment": "أي لحظة من {v} تبدو مثالية؟",
        "g_q_moment_multi": "لنبدأ مع {v}: أي لحظة تبدو مثالية؟",
        "g_sum_feel": "الأجواء: {v}",
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


DEFAULT_CHIP_IDS = ["fresher", "cheaper", "stronger"]


def default_chip_ids(picks: list[PerfumeCard]) -> list[str]:
    """Rule-based fallback refine chips, capped at 4: 3 generic tweaks plus "more like" the first pick."""
    ids = list(DEFAULT_CHIP_IDS)
    if picks:
        ids.append(f"more_like:{picks[0].perfume_id}")
    return ids[:4]


def _chip_label(lang: str, chip_id: str, picks: list[PerfumeCard]) -> str | None:
    c = T[lang]["chips"]
    if chip_id.startswith("more_like:"):
        pid = chip_id.split(":", 1)[1]
        idx = next((i for i, p in enumerate(picks) if p.perfume_id == pid), 0)
        return c["more_like"].format(n=idx + 1)
    return c.get(chip_id)


def refine_chips(lang: str, picks: list[PerfumeCard], chip_ids: list[str] | None = None) -> list[Chip]:
    """Builds the localized refine chips shown under a results card, capped at 4.

    `chip_ids`, when given, are ids the model already chose and validated this turn (see llm_agent.ground);
    used as-is when there are at least 2 usable ones, else this falls back to a sensible rule-based default
    set. The rule-based/quiz/refine paths always call this with no `chip_ids`, so they always get the
    default set, capped at 4 the same way.
    """
    ids = list(dict.fromkeys(chip_ids or []))
    valid = [i for i in ids if _chip_label(lang, i, picks) is not None]
    if len(valid) < 2:
        valid = default_chip_ids(picks)
    chips = []
    for cid in valid[:4]:
        label = _chip_label(lang, cid, picks)
        if label is not None:
            chips.append(Chip(id=cid, label=label))
    return chips


# ----------------------------------------------------------------------------- rate limit
_buckets: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    ip = client_ip(request)
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


class GuideBody(BaseModel):
    session_id: str
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


def _has_recommendation_context(s: dict, text: str) -> bool:
    """True when the off-topic keyword gate should be skipped and the message let through to the LLM (or
    rule-based) path instead: we already showed picks this session (recommendation context), or the message
    plainly refers back to them ("the first one", "compare them", or one of the shown picks by name)."""
    last = s.get("last_results") or []
    if last:
        return True
    return ex.refers_to_shown_picks(text)


def brand_block(lang: str, text: str) -> str | None:
    if not settings.brand_filter:
        return None
    wanted = normalize_brand(settings.brand_filter)
    other = [b for b in {p["brand_name"] for p in catalogue.perfumes.values()} if normalize_brand(b) != wanted]
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


QUESTION_TURN_REPLY_MAX = 120  # fix: a question turn's `reply` must be at most one short acknowledgement


def swap_duplicate_brand_picks(picks: list[PerfumeCard], prof: TasteProfile, lang: str, pool: list[dict],
                               seen_ids: set[str]) -> list[PerfumeCard]:
    """Fix: server-side safety net for the LLM agent's own 3 picks. The candidate lists its tools return are
    now diversified (see llm_agent's search_perfumes/find_similar), but the model can still choose several
    picks from one brand out of what it was shown. When 2 or 3 of the final picks share a brand, keep one of
    them and swap the rest for an alternative that isn't already used -- preferring a perfume this turn's
    tools actually returned (`seen_ids`), then the wider catalogue ranking. Keeping exactly one same-brand
    pick is intentional: for "something like X" it's fine for one pick to share X's brand, and outside that it
    just means one repeat is tolerated, two or more is not.

    The rule is unconditional, with no score-margin escape hatch: "at most one pick per brand" only relaxes
    when there is genuinely no unused brand left to swap to. (An earlier version only swapped within a small
    score margin, which let a second pick from one brand survive whenever the runners-up scored a little
    lower -- the live "two Lattafa picks" case -- even though plenty of other brands were available. The
    rule-based recommend() path has always diversified unconditionally; this now matches it.)
    """
    if len(picks) < 3:
        return picks
    brand_of = {p.perfume_id: normalize_brand(p.brand) for p in picks}
    brands = [brand_of[p.perfume_id] for p in picks]
    dup_brand = next((b for b in brands if brands.count(b) >= 2), None)
    if dup_brand is None:
        return picks
    keep_one = True
    to_swap: list[int] = []
    for i, b in enumerate(brands):
        if b != dup_brand:
            continue
        if keep_one:
            keep_one = False
            continue
        to_swap.append(i)
    if not to_swap:
        return picks
    ranked_pool = sorted(pool, key=lambda r: -r["score"])
    used_ids = {p.perfume_id for p in picks}
    used_brands = {b for i, b in enumerate(brands) if i not in to_swap}
    for i in to_swap:
        alt = None
        for prefer_seen in (True, False):
            for r in ranked_pool:
                cand = r["perfume"]
                if cand["perfume_id"] in used_ids or normalize_brand(cand["brand_name"]) in used_brands:
                    continue
                if not catalogue.passes(cand, prof):
                    continue  # hard constraints (budget, dislikes, strength, anchor line) always win
                if prefer_seen and cand["perfume_id"] not in seen_ids:
                    continue
                alt = r
                break
            if alt:
                break
        if alt is None:
            continue
        new_card = card(alt["perfume"], lang, alt["score"], template_reason(alt["perfume"], prof, lang))
        picks[i] = new_card
        used_ids.add(new_card.perfume_id)
        used_brands.add(normalize_brand(new_card.brand))
        images.request_generation(alt["perfume"])
    return picks


def _why_fails(p: dict, prof: TasteProfile) -> str:
    """Instrumentation only: the first hard filter a perfume fails, for the per-turn summary line."""
    if not p.get("recommendable"):
        return "not_recommendable"
    if prof.anchor_perfume_id and p["perfume_id"] in catalogue.anchor_flanker_ids(prof.anchor_perfume_id):
        return "anchor_flanker"
    if prof.budget_aed is not None and p.get("price_aed") is not None and p["price_aed"] > prof.budget_aed:
        return f"budget({p['price_aed']}>{prof.budget_aed})"
    notes = {n["note"] for n in p.get("notes") or []}
    for d in prof.disliked_notes:
        if (tx.normalise_note(d) or "") in notes:
            return f"disliked({d})"
    if prof.avoid_families and p.get("family") in prof.avoid_families:
        return f"avoid_family({p['family']})"
    if prof.strength is not None and abs(p["strength"] - prof.strength) > 2:
        return f"strength({p['strength']}vs{prof.strength})"
    if prof.gender and p.get("gender") and prof.gender.lower() in {"men", "women"} \
            and p["gender"].lower() not in {prof.gender.lower(), "unisex"}:
        return f"gender({p['gender']}vs{prof.gender})"
    if normalize_brand(prof.brand or settings.brand_filter) and \
            normalize_brand(p["brand_name"]) != normalize_brand(prof.brand or settings.brand_filter):
        return "brand"
    return "other"


def template_reply_for_picks(picks: list[PerfumeCard], prof: TasteProfile, lang: str) -> str:
    """Fix: a safe, template reply naming only the first of the FINAL picks. Used whenever the server changes
    the model's own picks (top-up, brand-variety swap), or when the model's own reply text named a perfume
    that isn't among the final picks (or the resolved anchor) -- so the text shown and the cards shown always
    agree, regardless of why the picks changed."""
    if not picks:
        return T[lang]["no_results"]
    top = picks[0]
    if prof.anchor_perfume:
        return T[lang]["picks_template_anchor"].format(anchor=prof.anchor_perfume, name=top.name, brand=top.brand)
    return T[lang]["picks_template"].format(name=top.name, brand=top.brand)


_MIN_MENTIONED_NAME_LEN = 5


_name_lookup_cache: tuple[int, dict[str, set[str]], int, set[str]] | None = None
_NAME_TOKEN = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)

# Fix (the main cause of the advisor's own words being thrown away): ~3,500 catalogue perfumes have a
# one-word name that is an ordinary scent or English word -- "Fresh", "Vanilla", "Amber", "Sweet", "Woody",
# "Summer", "Citrus", "Nothing", "Perfect". The off-pick scan below read every warm, specific sentence
# ("these three are all fresh and clean") as naming a perfume the cards do not show, and deleted it. So a
# ONE-WORD catalogue name only counts as naming a perfume when it is not everyday scent vocabulary AND it is
# written capitalised in the reply, the way a proper name is. Multi-word names ("Rose Goldea") always count.
_GENERIC_EXTRA = {
    "perfect", "nothing", "everything", "something", "always", "forever", "moment", "moments", "essence",
    "elegant", "elegance", "classic", "modern", "simple", "pure", "clean", "soft", "warm", "cool", "light",
    "strong", "bold", "daily", "night", "nights", "day", "days", "evening", "evenings", "morning", "office",
    "work", "party", "summer", "winter", "spring", "autumn", "beach", "sun", "rain", "sea", "ocean", "water",
    "air", "earth", "fire", "gift", "love", "dream", "dreams", "secret", "story", "one", "two", "three",
    "first", "yes", "man", "woman", "men", "women", "her", "him", "you", "me", "more", "less", "best",
    "good", "great", "nice", "happy", "free", "new", "now", "today", "here", "there", "this", "that",
    "scent", "perfume", "fragrance", "notes", "note", "price", "budget", "brand", "start", "style",
}


def _generic_name_words() -> set[str]:
    """One-word perfume names that are really just scent vocabulary, so they never count as a perfume mention:
    every taxonomy note and its synonyms, every family and family synonym, plus common English words."""
    t = tx.load()
    words = set(_GENERIC_EXTRA) | set(t["families"]) | set(t["moods"]) | set(t["occasions"]) | set(t["seasons"])
    for master, spec in t["notes"].items():
        words.add(master)
        words.update(spec.get("synonyms") or [])
    for fam, syns in (t.get("family_synonyms") or {}).items():
        words.add(fam)
        words.update(syns)
    # A note like "tonka bean" contributes its individual words too: a reply saying "tonka" must stay safe.
    return {w for phrase in list(words) for w in _NAME_TOKEN.findall(str(phrase).lower())}


def _name_lookup() -> tuple[dict[str, set[str]], int]:
    """Lower-cased perfume name (as word tokens joined by one space) -> perfume ids, plus the longest name
    length in words. Cached per catalogue snapshot, so checking a reply costs a few dictionary lookups."""
    global _name_lookup_cache
    perfumes = catalogue.perfumes
    key = id(perfumes)
    if _name_lookup_cache is None or _name_lookup_cache[0] != key:
        lookup: dict[str, set[str]] = {}
        longest = 1
        for pid, p in perfumes.items():
            name = p.get("name") or ""
            if len(name) < _MIN_MENTIONED_NAME_LEN:
                continue
            tokens = _NAME_TOKEN.findall(name.lower())
            if not tokens:
                continue
            lookup.setdefault(" ".join(tokens), set()).add(pid)
            longest = max(longest, len(tokens))
        _name_lookup_cache = (key, lookup, min(longest, 8), _generic_name_words())
    return _name_lookup_cache[1], _name_lookup_cache[2]


def _mentioned_perfume_ids(text: str) -> list[set[str]]:
    """The catalogue perfumes named in `text`: one set of candidate ids per name found (several perfumes can
    share a name). Longest names win, so "Sauvage Elixir" is read as that perfume and never as "Sauvage".

    A one-word name only counts when it is written capitalised (a proper name, not "a fresh scent") and is not
    everyday scent vocabulary -- see _generic_name_words."""
    if not text:
        return []
    lookup, longest = _name_lookup()
    generic = _name_lookup_cache[3] if _name_lookup_cache else set()
    raw = _NAME_TOKEN.findall(text)
    tokens = [t.lower() for t in raw]
    found: list[set[str]] = []
    i = 0
    while i < len(tokens):
        for n in range(min(longest, len(tokens) - i), 0, -1):
            ids = lookup.get(" ".join(tokens[i:i + n]))
            if not ids:
                continue
            if n == 1 and (tokens[i] in generic or not raw[i][:1].isupper()):
                continue  # ordinary word, or the same word written in lower case: not a perfume mention
            found.append(ids)
            i += n - 1
            break
        i += 1
    return found


def _mentions_offpick_perfume(text: str, allowed_ids: set[str], ignore: list[str] = ()) -> bool:
    """True when `text` names a catalogue perfume that is not in `allowed_ids`: a sign the reply talks about
    a perfume the cards do not show, or, on a question turn, about a perfume that was never resolved as the
    anchor. Very short names are skipped to avoid false positives. Phrases in `ignore` (the shopper's own
    moment titles) are blanked out first."""
    for phrase in ignore or ():
        if phrase:
            text = re.sub(re.escape(phrase), " ", text or "", flags=re.I)
    return any(not (ids & allowed_ids) for ids in _mentioned_perfume_ids(text))


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟])\s+")


def reconcile_reply_with_picks(reply: str, picks: list[PerfumeCard], allowed_ids: set[str],
                               dropped_names: list[str], prof: TasteProfile, lang: str,
                               ignore: list[str] = ()) -> str:
    """Keeps the advisor's own words wherever they agree with the cards. Sentences that name a perfume the
    cards do not show are removed; when no remaining sentence names one of the final picks, a short
    "start with" sentence for the first pick is added. The plain template is the last resort."""
    if not picks:
        return T[lang]["no_results"]
    dropped = [n.lower() for n in dropped_names if n]
    kept = [sent for sent in _SENTENCE_SPLIT.split((reply or "").strip())
            if sent and not _mentions_offpick_perfume(sent, allowed_ids, ignore)
            and not any(n in sent.lower() for n in dropped)]
    if not kept:
        return template_reply_for_picks(picks, prof, lang)
    final_names = [c.name.lower() for c in picks]
    if not any(n in " ".join(kept).lower() for n in final_names):
        start_with = T[lang]["start_with"].format(name=picks[0].name, brand=picks[0].brand)
        closing = kept.pop() if len(kept) > 1 and kept[-1].rstrip().endswith(("?", "؟")) else None
        kept.append(start_with)
        if closing:
            kept.append(closing)
    return " ".join(kept)


CHAT_ANSWER_REPLY_MAX = 280  # an ordinary chat turn that answers something AND offers quick replies


def _names_unshown_perfume(sent: str, allowed_ids: set[str]) -> bool:
    """True when a sentence names something that looks like a perfume or house the shopper cannot see.

    On a turn with no cards, the reply must not describe a specific perfume. `_mentions_offpick_perfume`
    catches the ones in our catalogue; this catches the other half -- a perfume the model invented or
    remembered, which is never in the catalogue and so never matches a name. Two or more capitalised words in
    a row is a proper name ("L'Eau d'Issey by Issey Miyake"); ordinary acknowledgements and comparisons do not
    contain one. Scripts without capitals (Arabic) never trip it, so the sentence-count and length caps remain
    their only limit there.
    """
    if _mentions_offpick_perfume(sent, allowed_ids):
        return True
    lookup, _ = _name_lookup()
    # Blank out the names and brands of the perfumes the shopper CAN see, so a sentence that legitimately
    # names them is not then re-read as an unknown proper name. Names hold lower-case particles ("Bleu de
    # Chanel Eau de Parfum"), which would otherwise split into runs that match nothing.
    for pid in allowed_ids:
        row = catalogue.get(pid)
        for value in ((row or {}).get("name"), (row or {}).get("brand_name")):
            if value and len(value) >= 3:
                sent = re.sub(re.escape(value), " ", sent, flags=re.I)

    def unknown(run: list[str]) -> bool:
        if len(run) < 2:
            return False
        return not (lookup.get(" ".join(w.lower() for w in run)) or set()) & allowed_ids

    run: list[str] = []
    for tok in _NAME_TOKEN.findall(sent):
        if tok[:1].isupper():
            run.append(tok)
            continue
        if unknown(run):
            return True
        run = []
    return unknown(run)


def trim_question_turn_reply(reply: str, question: str, allowed_ids: set[str], guided: bool) -> str:
    """What survives of the advisor's own text on a turn whose question is shown separately.

    The question itself belongs in `next_question`, so a sentence that repeats it -- or is just another
    question -- is dropped, as is any sentence about a perfume the shopper cannot see. Whatever is left is the
    advisor's acknowledgement or its short answer, and it is kept: guided mode allows one short sentence (its
    rule is "empty or ONE short acknowledgement"), ordinary chat allows a two-sentence answer.

    Fix: this used to blank the whole `reply` whenever it ran past 120 characters, which threw away real
    answers -- a "how do these two compare?" follow-up came back as an empty bubble with a question under it.
    """
    kept: list[str] = []
    for sent in _SENTENCE_SPLIT.split((reply or "").strip()):
        sent = sent.strip()
        if not sent or sent.endswith(("?", "؟")):
            continue
        if _is_same_sentence(sent, question) or _names_unshown_perfume(sent, allowed_ids):
            continue
        kept.append(sent)
    if not kept:
        return ""
    if guided:
        return kept[0] if len(kept[0]) <= QUESTION_TURN_REPLY_MAX else ""
    out = " ".join(kept[:2])
    return out if len(out) <= CHAT_ANSWER_REPLY_MAX else ""


def _is_same_sentence(a: str, b: str) -> bool:
    """Fix: a question turn's `reply` must never be a second copy of the question itself (the live bug: the
    rule-based dislike turn showed "Anything you dislike?" as both the reply and the question)."""
    norm = lambda v: re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", (v or "").lower())
    na, nb = norm(a), norm(b)
    return bool(na) and bool(nb) and (na == nb or na in nb or nb in na)


def build_results(s: dict, prof: TasteProfile, text: str | None, lang: str, reasons: dict[str, str] | None = None,
                  exclude: list[str] = (), intro: str | None = None, fallback: bool = False) -> AgentReply:
    # Fix: recommend() is used on BOTH paths so the anchor/flanker exclusion and the one-pick-per-brand rule
    # hold for refine and "more like" too (search() alone returns the raw ranking, flankers and all).
    res = catalogue.recommend(prof, text, k=3, exclude_ids=exclude)
    if exclude and not res["picks"]:
        res = catalogue.recommend(prof, text, k=3)
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


def resolve_anchor(prof: TasteProfile, lang: str, text: str = "") -> tuple[TasteProfile, str | None, str | None]:
    """Returns (profile, intro text, not-found reply)."""
    if not prof.anchor_perfume:
        return prof, None, None
    p = catalogue.find_by_name(prof.anchor_perfume)
    if not p:
        if ex.anchor_needs_confirmation(text):
            # Ambiguous trigger ("what is X" / "tell me about X") with no other perfume cue and no catalogue
            # match: more likely a general-knowledge question than an unknown perfume. Drop the anchor
            # silently instead of claiming it's "not found", and let normal chat handling take over.
            prof.anchor_perfume, prof.anchor_cheaper = None, False
            return prof, None, None
        db.add_review("zero_results", {"anchor": prof.anchor_perfume, "lang": lang})
        return prof, None, T[lang]["not_found"].format(name=prof.anchor_perfume)
    prof.anchor_perfume_id = p["perfume_id"]
    prof.anchor_perfume = p["name"]
    if prof.anchor_cheaper and p.get("price_aed"):
        prof.budget_aed = float(p["price_aed"]) - 1
    return prof, T[lang]["results_anchor"].format(name=p["name"]), None


# ----------------------------------------------------------------------------- guided match
GUIDED_MAX = 5
GUIDED_FALLBACK_FIELDS = ["liked_notes", "disliked_notes", "mood", "budget"]


def guided_state(s: dict) -> dict:
    g = s["profile"].setdefault("guided", {})
    g.setdefault("active", False)
    g.setdefault("count", 0)
    g.setdefault("asked", [])
    g.setdefault("asked_topics", [])
    g.setdefault("pending", None)     # the question the NEXT message answers (see set_pending_question)
    return g


def set_pending_question(g: dict, q: QuizQuestion | None) -> None:
    """Fix: remembers the guided question that was just asked, so the next message can be interpreted as an
    answer to THAT question (topic, option ids and labels, multi flag) rather than read on its own -- the live
    bug where "vanilla" answering "Anything you dislike?" was stored as a liked note."""
    if q is None:
        g["pending"] = None
        return
    g["pending"] = {"id": q.id, "question": q.question, "topic": q.topic, "multi": bool(q.multi),
                    "options": [{"id": o.id, "label": o.label} for o in q.options]}


def take_pending_question(g: dict) -> dict | None:
    pending = g.get("pending")
    g["pending"] = None
    return pending


def apply_guided_answer(prof: TasteProfile, answer: TasteProfile) -> TasteProfile:
    """Merges the deterministic reading of a guided answer into the profile, letting it WIN over anything
    already there (including the model's own profile_updates) for the fields it speaks about: a note the
    shopper just said they dislike stops being a liked note, and vice versa."""
    merged = prof.merge(answer)
    if answer.disliked_notes:
        merged.liked_notes = [n for n in merged.liked_notes if n not in answer.disliked_notes]
    if answer.liked_notes:
        merged.disliked_notes = [n for n in merged.disliked_notes if n not in answer.liked_notes]
    if answer.avoid_families:
        merged.families = [f for f in merged.families if f not in answer.avoid_families]
    if answer.families:
        merged.avoid_families = [f for f in merged.avoid_families if f not in answer.families]
    for field in ("strength", "budget_aed", "guided_for", "gender", "anchor_perfume", "anchor_perfume_id"):
        value = getattr(answer, field)
        if value is not None:
            setattr(merged, field, value)
    return merged


# Fix: maps a model-authored question's `topic` to the equivalent guided_fallback_question() field id, and
# back, so a topic asked by the model (no rule-based id) and a topic asked by the rule-based fallback (no
# `topic` value) both count toward "already asked" in the other's bookkeeping.
_TOPIC_TO_FALLBACK_FIELD = {"liked_scents": "liked_notes", "disliked_scents": "disliked_notes",
                           "occasion": "mood", "budget": "budget"}
_FALLBACK_FIELD_TO_TOPIC = {v: k for k, v in _TOPIC_TO_FALLBACK_FIELD.items()}


def _asked_fallback_ids(g: dict) -> list[str]:
    mapped = {_TOPIC_TO_FALLBACK_FIELD[t] for t in g.get("asked_topics", []) if t in _TOPIC_TO_FALLBACK_FIELD}
    return list(dict.fromkeys(list(g["asked"]) + list(mapped)))


def _record_asked_question(g: dict, q: QuizQuestion) -> None:
    g["asked"].append(q.id)
    topic = _FALLBACK_FIELD_TO_TOPIC.get(q.id) or (q.topic if q.topic in SCENARIO_TOPICS else None)
    if topic and topic not in g["asked_topics"]:
        g["asked_topics"].append(topic)


def guided_for_question(lang: str) -> QuizQuestion:
    t = T[lang]
    opts = [Chip(id="self", label=t["g_for_me"]), Chip(id="gift_her", label=t["g_gift_her"]),
            Chip(id="gift_him", label=t["g_gift_him"]), Chip(id="gift_unsure", label=t["g_gift_unsure"])]
    return QuizQuestion(id="guided_for", question=t["g_q_for"], multi=False, options=opts, index=1,
                        max_index=GUIDED_MAX, topic="recipient")


SCENARIO_TOPICS = ("scenario", "scenario_moment")


def _card_chips(options: list[dict]) -> list[Chip]:
    return [Chip(id=o["id"], label=o["label"], caption=o["caption"], motif=o["motif"], family=o["family"])
            for o in options]


def guided_scenario_question(lang: str, guided_for: str | None) -> QuizQuestion:
    """Q2, instant and rule-based: the shopper picks up to three moments they want this scent for, as cards."""
    t = T[lang]
    question = t["g_q_scenario"].get(guided_for or "self", t["g_q_scenario"]["self"])
    return QuizQuestion(id="scenario", question=question, multi=True, options=_card_chips(sc.scenario_options(lang)),
                        ask_reason=t["g_scenario_hint"], topic="scenario")


def guided_moment_question(lang: str, scenario_ids: list[str]) -> QuizQuestion | None:
    """Q3, instant and rule-based: the follow-up moments for the first chosen scenario (plus one from the second
    when two or three were chosen). Single select; the widget adds its own "Something else" free-text card."""
    options = sc.moment_options(scenario_ids, lang)
    if not options:
        return None
    t = T[lang]
    key = "g_q_moment_multi" if len(scenario_ids) > 1 else "g_q_moment"
    return QuizQuestion(id="scenario_moment", question=t[key].format(v=sc.short(scenario_ids[0], lang)), multi=False,
                        options=_card_chips(options), topic="scenario_moment")


def guided_budget_question(lang: str) -> QuizQuestion:
    t = T[lang]
    opts = [Chip(id=str(b), label=t["under"].format(n=b)) for b in BUDGETS] + [Chip(id="0", label=t["no_budget"])]
    return QuizQuestion(id="budget", question=t["q_budget"], multi=False, options=opts, topic="budget")


def guided_fallback_question(prof: TasteProfile, lang: str, asked: list[str]) -> QuizQuestion | None:
    """Deterministic next guided question when the model is unavailable: works through a fixed field order,
    skipping anything already known or already asked (so a skipped question is never repeated).

    Fix: every rule-based question now carries its `topic`, so the answer to it can be interpreted against the
    question it actually answers (see set_pending_question / extract.interpret_guided_answer), and so the
    model's topic bookkeeping and this one stay in step.
    """
    t = T[lang]
    if "liked_notes" not in asked and not prof.liked_notes:
        opts = [Chip(id=n, label=tx.note_label(n, lang)) for n in QUIZ_NOTES[:6]]
        return QuizQuestion(id="liked_notes", question=t["q_liked"], multi=True, options=opts, topic="liked_scents")
    if "disliked_notes" not in asked and not prof.disliked_notes:
        opts = [Chip(id=n, label=tx.note_label(n, lang)) for n in QUIZ_NOTES[:6]]
        return QuizQuestion(id="disliked_notes", question=t["q_disliked"], multi=True, options=opts,
                            topic="disliked_scents")
    if "mood" not in asked and not prof.moods and not prof.occasions:
        opts = [Chip(id=m, label=tx.label("moods", m, lang)) for m in list(tx.load()["moods"])[:6]]
        return QuizQuestion(id="mood", question=t["q_mood"], multi=False, options=opts, topic="occasion")
    if "budget" not in asked and prof.budget_aed is None:
        return guided_budget_question(lang)
    return None


def _join_labels(values: list[str], limit: int = 4, sep: str = ", ") -> str:
    return sep.join(values[:limit])


def build_profile_summary(prof: TasteProfile, lang: str) -> list[Chip]:
    """The short "what I learned" tags shown above the picks once guided match finishes.

    Fix: every known signal appears (for / loves / avoid / the anchor perfume / occasion or mood / strength /
    budget), and every value is localised through the taxonomy labels -- the live Arabic run showed an
    untranslated "يحب: floral".
    """
    t = T[lang]
    sep = "، " if lang == "ar" else ", "
    tags: list[Chip] = []
    if prof.guided_for:
        label = t["g_for_label"].get(prof.guided_for, prof.guided_for)
        tags.append(Chip(id="for", label=t["g_sum_for"].format(v=label)))
    feel = sc.feel_titles(prof, lang)
    if feel:
        tags.append(Chip(id="feel", label=t["g_sum_feel"].format(v=" · ".join(feel))))
    loves = [tx.note_label(n, lang) for n in prof.liked_notes] + [tx.label("families", f, lang) for f in prof.families]
    if loves:
        tags.append(Chip(id="loves", label=t["g_sum_loves"].format(v=_join_labels(loves, 4, sep))))
    avoid = ([tx.note_label(n, lang) for n in prof.disliked_notes]
             + [tx.label("families", f, lang) for f in prof.avoid_families])
    if avoid:
        tags.append(Chip(id="avoid", label=t["g_sum_avoid"].format(v=_join_labels(avoid, 4, sep))))
    if prof.anchor_perfume:
        tags.append(Chip(id="like", label=t["g_sum_like"].format(v=prof.anchor_perfume)))
    occasions = [tx.label("occasions", o, lang) for o in prof.occasions]
    if occasions:
        tags.append(Chip(id="occasion", label=t["g_sum_occasion"].format(v=_join_labels(occasions, 3, sep))))
    if prof.moods:
        tags.append(Chip(id="mood", label=t["g_sum_mood"].format(v=_join_labels([tx.label("moods", m, lang) for m in prof.moods], 3, sep))))
    if prof.strength is not None:
        tags.append(Chip(id="strength", label=t["g_sum_strength"].format(v=tx.label("strengths", prof.strength, lang))))
    if prof.budget_aed:
        tags.append(Chip(id="budget", label=t["g_sum_budget"].format(v=int(prof.budget_aed))))
    return tags


def _qr_slug(text: str, i: int) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return f"qr{i}_{s}"[:40] if s else f"qr{i}"


# The answer to guided match's instant first question ("who is this for?") is a plain phrase, not taxonomy
# vocabulary, so it has its own small parser; it now lives next to the rest of the guided answer reading.
parse_guided_for = ex.parse_guided_for


def guided_finish(s: dict, prof: TasteProfile, lang: str, fallback: bool = False) -> AgentReply:
    """The deterministic closing turn: rule-based picks plus the template reply. Used as the fallback whenever
    the AI is unavailable or its closing turn fails the server-side consistency checks."""
    g = guided_state(s)
    g["active"], g["pending"] = False, None
    feel = sc.feel_titles(prof, lang, limit=1)
    intro = T[lang]["g_finished_feel"].format(v=feel[0]) if feel else T[lang]["g_finished"]
    reply = build_results(s, prof, prof.free_text or None, lang, intro=intro, fallback=fallback)
    reply.guided = True
    reply.profile_summary = build_profile_summary(prof, lang)
    return reply


async def guided_recommend_now(s: dict, text: str, lang: str) -> AgentReply:
    """Fix (problem 5): the FINAL guided turn -- the 5-question cap, the early finish, or "show my picks now".

    With the AI available, let the agent write the closing turn (a reply naming the first pick, plus a per-pick
    reason tied to the shopper's own answers); llm_chat's existing consistency checks still apply, so a reply
    that disagrees with the final cards is replaced by the template. Without the AI, or when the agent returns
    no picks, fall back to the deterministic guided_finish().
    """
    g = guided_state(s)
    if settings.llm_enabled and llm_agent is not None:
        reply = await llm_chat(s, text, lang, guided={"index": g.get("count", 1), "max": GUIDED_MAX,
                                                      "topics_asked": list(g.get("asked_topics") or []),
                                                      "force": True})
        if reply is not None and reply.picks:
            g["active"], g["pending"] = False, None
            reply.guided = True
            reply.profile_summary = build_profile_summary(reply.profile, lang)
            return reply
        s.pop("_llm_soft_miss", None)  # the AI answered, it just didn't produce usable picks: stay quiet
    return guided_finish(s, taste(s), lang)


def guided_should_recommend(prof: TasteProfile, questions_answered_after_q1: int, next_index: int, text: str) -> bool:
    """Fix: "who is this for?" alone is a weak signal, so guided match must not recommend right after it.
    Recommend only once at least 2 questions beyond Q1 have been answered (a skip counts as answered) AND the
    profile holds at least 2 real taste signals (gender/recipient alone never counts -- see
    TasteProfile.guided_signal_count), OR the shopper directly asks for picks, OR the 5-question cap is reached."""
    if next_index > GUIDED_MAX:
        return True
    if ex.wants_recommendation(text):
        return True
    return questions_answered_after_q1 >= 2 and prof.guided_signal_count() >= 2


def read_guided_answer(s: dict, pending: dict | None, text: str) -> TasteProfile:
    """Fix (problem 1): interprets the shopper's message as the answer to the question that was actually asked,
    deterministically and BEFORE any model call, then resolves a named perfume through the catalogue. The
    result is merged into the session profile so the model sees the correct reading too."""
    answer = ex.interpret_guided_answer(text, pending)
    if answer.anchor_perfume and not answer.anchor_perfume_id:
        row = catalogue.find_by_name(answer.anchor_perfume)
        if row:
            answer.anchor_perfume, answer.anchor_perfume_id = row["name"], row["perfume_id"]
            if answer.anchor_cheaper and row.get("price_aed"):
                answer.budget_aed = float(row["price_aed"]) - 1
        else:
            answer.anchor_perfume, answer.anchor_cheaper = None, False  # never carry an unresolved name forward
    prof = apply_guided_answer(taste(s), answer)
    set_taste(s, prof)
    return answer


def _guided_question_reply(s: dict, g: dict, prof: TasteProfile, q: QuizQuestion, lang: str, next_index: int,
                           fallback: bool = False) -> AgentReply:
    """Returns one rule-based guided question turn. Fix: the `reply` is never a second copy of the question --
    it stays empty (or carries only the "AI is resting" note), and the question is shown via next_question."""
    _record_asked_question(g, q)
    g["count"] = next_index
    q.index, q.max_index = next_index, GUIDED_MAX
    set_pending_question(g, q)
    return AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["fallback_note"] if fallback else "",
                      next_question=q, intent="chat", profile=prof, guided=True, fallback_used=fallback)


async def guided_turn(s: dict, text: str, lang: str) -> AgentReply:
    """One turn of the guided-match interview: reads the answer against the question it answers, then tries the
    AI-authored adaptive question, falls back to the deterministic rule-based question set, and enforces both
    the 5-question cap and the early finish server-side either way."""
    g = guided_state(s)
    pending = take_pending_question(g)
    answer = read_guided_answer(s, pending, text)
    prof = taste(s)
    if g["count"] == 1 and not prof.guided_for:
        # Older sessions (and any turn where no pending question was stored) still answer Q1 here.
        gf = parse_guided_for(text)
        if gf:
            prof.guided_for = gf
            prof.gender = prof.gender or ex.GUIDED_FOR_GENDER.get(gf)
            set_taste(s, prof)
    # NB: topics are recorded when a question is ASKED (see _record_asked_question and the model-question
    # path below), not here. Q1's own "recipient" topic is deliberately left unrecorded so the gift branch can
    # still follow up about the recipient's style, which the system prompt asks for.
    next_index = g["count"] + 1
    # g["count"] is the number of questions asked (and, at this point, answered) so far, including the instant
    # Q1 ("who is this for?"); subtract 1 so Q1 itself never counts toward the "2 questions beyond Q1" gate.
    answered_after_q1 = g["count"] - 1

    if next_index > GUIDED_MAX:
        return await guided_recommend_now(s, text, lang)

    # Scenario step (instant, rule-based, no model call): after "who is this for?" the shopper picks moments they
    # picture (Q2), then the follow-up moment for the first one (Q3). A skip, or an answer that names no
    # scenario, falls through to the ordinary flow below; so does a direct "show me picks".
    pending_topic = (pending or {}).get("topic")
    if not ex.wants_recommendation(text):
        if pending_topic == "recipient":
            return _guided_question_reply(s, g, prof, guided_scenario_question(lang, prof.guided_for), lang,
                                          next_index)
        if pending_topic == "scenario" and answer.scenarios:
            if "occasion" not in g["asked_topics"]:
                g["asked_topics"].append("occasion")  # the moments answer the occasion/mood topic too
            q = guided_moment_question(lang, answer.scenarios)
            if q is not None:
                return _guided_question_reply(s, g, prof, q, lang, next_index)

    # Fix (problem 4): finish as soon as enough is known instead of asking another question -- unless the
    # budget is still unknown, in which case budget is asked as the last question.
    if guided_should_recommend(prof, answered_after_q1, next_index, text):
        if prof.budget_aed is None and "budget" not in _asked_fallback_ids(g) and not ex.wants_recommendation(text):
            return _guided_question_reply(s, g, prof, guided_budget_question(lang), lang, next_index)
        return await guided_recommend_now(s, text, lang)

    reply: AgentReply | None = None
    if settings.llm_enabled and llm_agent is not None:
        reply = await llm_chat(s, text, lang, guided={"index": next_index, "max": GUIDED_MAX,
                                                       "topics_asked": list(g["asked_topics"]),
                                                       "pending": pending})
    if reply is not None:
        # Fix: the deterministic reading of the answered question always wins over the model's own
        # profile_updates for that topic (the live bug: "vanilla" under "anything you dislike?").
        gate_prof = apply_guided_answer(reply.profile, answer)
        reply.profile = gate_prof
        set_taste(s, gate_prof)
        if reply.picks:
            if guided_should_recommend(gate_prof, answered_after_q1, next_index, text):
                g["active"], g["pending"] = False, None
                reply.profile_summary = build_profile_summary(gate_prof, lang)
                return reply
            # Held: the model recommended too early. Ask the next most useful question instead, via the same
            # deterministic rule-based question logic the no-LLM fallback uses -- simplest reliable option
            # (an extra model call just to get a question is possible but not worth the latency/cost here).
            db.add_event(s["session_id"], "guided_picks_held", {"count": g["count"]})
            q = guided_fallback_question(gate_prof, lang, _asked_fallback_ids(g))
            if q is None:
                return await guided_recommend_now(s, text, lang)
            return _guided_question_reply(s, g, gate_prof, q, lang, next_index)
        if reply.next_question is not None:
            topic = reply.next_question.topic
            if topic and topic in g["asked_topics"]:
                # Fix: the model repeated a topic it already asked about (even if its own dedup missed that
                # the shopper's last answer addressed something else). Discard its question and ask the next
                # rule-based question on an unasked topic instead.
                db.add_event(s["session_id"], "guided_topic_repeated", {"topic": topic})
                q = guided_fallback_question(gate_prof, lang, _asked_fallback_ids(g))
                if q is None:
                    return await guided_recommend_now(s, text, lang)
                return _guided_question_reply(s, g, gate_prof, q, lang, next_index)
            if topic and topic not in g["asked_topics"]:
                g["asked_topics"].append(topic)
            g["count"] = next_index
            set_pending_question(g, reply.next_question)
            return reply
        # An informative interjection with neither picks nor a next question (e.g. a perfume lookup mid
        # interview): return it as-is without consuming a question slot -- and keep the question pending, since
        # it is still unanswered and the NEXT message is the one that answers it.
        g["pending"] = pending
        return reply

    # No usable model response this turn: fall back to the deterministic rule-based question. Distinguish a
    # genuine AI outage (llm_chat raised/timed out) from a soft grounding miss (the model responded, we just
    # didn't trust its output) -- only a genuine outage gets the "AI is resting" note and fallback_used=True;
    # a soft miss (or the "held early picks" path above) stays quiet, since the AI is not actually unavailable.
    genuine_outage = bool(settings.llm_enabled) and not s.pop("_llm_soft_miss", False)
    prof = taste(s)
    if answered_after_q1 >= 1 and ex.wants_recommendation(text):
        # No-LLM fallback: a direct "show me picks" request finishes the interview early too (skip the very
        # first turn, which only just answered "who is this for?" and may contain those words incidentally).
        return guided_finish(s, prof, lang, fallback=genuine_outage)
    q = guided_fallback_question(prof, lang, _asked_fallback_ids(g))
    if q is None:
        return guided_finish(s, prof, lang, fallback=genuine_outage)
    if genuine_outage:
        db.add_event(s["session_id"], "fallback_used", {})
    return _guided_question_reply(s, g, prof, q, lang, next_index, fallback=genuine_outage)


def rule_based_chat(s: dict, text: str, lang: str, fallback: bool) -> AgentReply:
    prof = taste(s).merge(ex.extract_profile(text)).merge(sc.profile_from_text(text))
    prof, intro, not_found = resolve_anchor(prof, lang, text)
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


@app.post("/api/session/reset")
def reset_session(body: SessionBody, request: Request):
    """Start over: clear what the advisor learned (taste, conversation, guided progress); keep the wishlist."""
    rate_limit(request)
    s = load_session(body.session_id or "")
    s["profile"] = {"taste": {}, "pending_consent": []}
    s["history"] = []
    s["last_results"] = []
    db.save_session(s)
    db.add_event(s["session_id"], "session_reset", {})
    return {"ok": True, "session_id": s["session_id"]}


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
        elif ex.is_off_topic(text) and not _has_recommendation_context(s, text):
            reply = AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["declined_offtopic"], intent="declined", profile=taste(s))

    if reply is None and guided_state(s)["active"]:
        reply = await guided_turn(s, text, lang)

    if reply is None and settings.llm_enabled and llm_agent is not None:
        reply = await llm_chat(s, text, lang)

    if reply is None:
        # Fix: only a genuine AI outage (llm_chat raised/timed out) shows the "AI is resting" note; a soft
        # grounding miss (the model responded, we just didn't trust its output) falls back quietly.
        genuine_outage = bool(settings.llm_enabled) and not s.pop("_llm_soft_miss", False)
        reply = rule_based_chat(s, text, lang, fallback=genuine_outage)
        if reply.fallback_used:
            db.add_event(s["session_id"], "fallback_used", {})

    s["history"].append({"role": "assistant", "text": _history_text(reply)})
    db.save_session(s)
    return reply


def _history_text(reply: AgentReply) -> str:
    """What an assistant turn contributed to the conversation. A question turn's `reply` is often deliberately
    empty (the question lives in next_question), so record the question instead of a blank turn."""
    if reply.reply:
        return reply.reply
    return reply.next_question.question if reply.next_question else ""


async def llm_chat(s: dict, text: str, lang: str, guided: dict | None = None) -> AgentReply | None:
    """Runs the Agents SDK agent; returns None when the caller should fall back to rules.

    `guided`, when given (`{"index": <1-based question number about to be asked>, "max": <cap>}`), puts the
    agent in guided-match mode for this turn: the system prompt's GUIDED MODE section applies, and the model's
    quick_replies are mapped onto the returned `next_question` with progress numbers attached.
    """
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
        elif ex.is_lookup(text) and not ex.anchor_needs_confirmation(text):
            # Explicit "tell me about X" for something not in the catalogue: answer deterministically, never guess.
            db.add_review("zero_results", {"anchor": hard.anchor_perfume, "lang": lang})
            return AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["not_found"].format(name=hard.anchor_perfume),
                              intent="lookup", profile=prof)
        # else: an ambiguous, unresolved anchor ("what is <general knowledge>") with no other perfume cue --
        # drop it and let the LLM agent handle the message on its own (its system prompt covers scope).
    prof = apply_hard(prof, hard_only)
    if not guided:
        # Free chat that sounds like a moment ("a beach holiday", "for a fancy party") reads through the same
        # scenario library as guided match, so both paths agree on what that moment means.
        prof = prof.merge(sc.profile_from_text(text))
    # Fix: when the profile already has a resolved anchor (this turn or an earlier one), hand the model its
    # real catalogue facts directly -- grounded, not the model's own memory of it -- so it can describe the
    # perfume correctly even for a turn where it doesn't call get_perfume/find_similar again.
    anchor_row = catalogue.get(prof.anchor_perfume_id) if prof.anchor_perfume_id else None
    anchor_ctx = llm_agent.compact(anchor_row, lang) if anchor_row else None
    ctx = llm_agent.AgentContext(session_id=s["session_id"], language=lang, profile=prof, db=db, catalogue=catalogue,
                                 seen_ids=set(s.get("last_results") or []), wishlist_consent=bool(s.get("consent_wishlist")),
                                 brand_filter=settings.brand_filter, last_results=list(s.get("last_results") or []),
                                 guided=bool(guided), guided_question_index=(guided or {}).get("index", 0),
                                 guided_max=(guided or {}).get("max", GUIDED_MAX), anchor_context=anchor_ctx,
                                 guided_topics_asked=list((guided or {}).get("topics_asked") or []),
                                 pending_question=(guided or {}).get("pending") or None,
                                 force_recommend=bool((guided or {}).get("force")))
    s.pop("_llm_soft_miss", None)
    t_turn = time.perf_counter()
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
        # The model invented every pick: use the rule-based picks instead. It DID respond (this is not a true
        # outage), so the caller's fallback should stay quiet -- no "AI is resting" note.
        s["_llm_soft_miss"] = True
        return None
    prof = apply_hard(result.profile or prof, hard_only)  # the user's own negations always win over the model
    if prof.anchor_perfume and not prof.anchor_perfume_id:
        prof, _, not_found = resolve_anchor(prof, lang, text)
        if not_found:
            # Never carry an unresolved "like X" name into later turns: it would keep re-searching for it
            # and writing a review_queue row on every subsequent message.
            prof.anchor_perfume, prof.anchor_cheaper = None, False
    set_taste(s, prof)
    # Fix: re-check the model's picks against the constraints the TOOLS applied when it chose them, plus the
    # shopper's own deterministic hard filters -- not against a profile the model itself widened afterwards.
    # A `profile_updates` guess made in the same breath as the picks (a strength or gender the shopper never
    # stated) used to disqualify perfumes the catalogue had already cleared for that very search, which threw
    # away the model's reply along with them.
    pick_prof = prof
    if result.pick_filter_profile is not None:
        pick_prof = apply_hard(result.pick_filter_profile, hard_only)
        pick_prof.anchor_perfume = prof.anchor_perfume
        pick_prof.anchor_perfume_id = prof.anchor_perfume_id
    original_pick_ids = [p.perfume_id for p in out.picks]
    picks: list[PerfumeCard] = []
    drop_why: list[str] = []      # instrumentation: why each of the model's own picks did not survive
    for pick in out.picks[:3]:
        p = catalogue.get(pick.perfume_id)
        if p and prof.anchor_perfume_id and p["perfume_id"] == prof.anchor_perfume_id:
            drop_why.append(f"{pick.perfume_id}:anchor")
            continue  # fix: "something like X" must never return X itself as a pick
        if p and catalogue.passes(p, pick_prof):
            picks.append(card(p, lang, None, pick.reason))
            images.request_generation(p)
        elif p:
            drop_why.append(f"{pick.perfume_id}:{_why_fails(p, pick_prof)}")
            db.add_review("constraint_violation", {"perfume_id": p["perfume_id"], "session_id": s["session_id"]})
        else:
            drop_why.append(f"{pick.perfume_id}:unknown_id")
    kept_after_filter = len(picks)
    brand_swaps = 0
    if out.intent == "recommend" and len(picks) < 3:
        # Top up with our own ranking so the results card always shows 3 grounded picks -- including when
        # EVERY one of the model's own picks got dropped (e.g. all failed catalogue.passes() after a
        # just-updated constraint like strength), not just when 1 or 2 survived: live bug (problem 2) showed
        # intent="recommend" with an empty picks list, a reply claiming "these three picks...", and a
        # redundant next_question all at once -- always finishing the recommendation here avoids that state.
        for r in catalogue.search(prof, text, limit=3 - len(picks), exclude_ids=[c.perfume_id for c in picks]):
            picks.append(card(r["perfume"], lang, r["score"], template_reason(r["perfume"], prof, lang)))
    if picks:
        # Fix (latency): the brand-variety swap needs the whole ranked catalogue, but only when two picks
        # actually share a brand -- which is rare. Building 24k scored rows on every recommendation turn cost
        # about a second of pure server time for nothing. Check for a duplicate brand first.
        needs_swap = (out.intent == "recommend" and len(picks) == 3
                      and len({normalize_brand(c.brand) for c in picks}) < 3)
        if needs_swap and not prof.brand and not settings.brand_filter:
            # Fix: the model's own picks can still end up brand-heavy even though its tool candidates were
            # diversified (it only sees a diversified list, it isn't forced to pick diversely from it). The
            # full ranked catalogue is needed here so every pick's real score is found rather than
            # defaulting to 0; `pool` below then reuses its top 40 instead of scoring the catalogue twice.
            swap_pool = catalogue.search(prof, text, limit=len(catalogue.ids))
            before_swap = [c.perfume_id for c in picks]
            picks = swap_duplicate_brand_picks(picks, prof, lang, swap_pool, ctx.seen_ids)
            brand_swaps = sum(1 for a, b in zip(before_swap, [c.perfume_id for c in picks]) if a != b)
            pool = swap_pool[:40]
        else:
            pool = catalogue.search(prof, text, limit=40)
        ms = match_scores(pool, [c.perfume_id for c in picks])
        for c in picks:
            c.match_score = ms.get(c.perfume_id, 60)
    layering = None
    if out.layering:
        # Not gated on `picks`: a layering follow-up about an earlier pick (intent="chat", no new picks this
        # turn) should still surface a structured layering card.
        partner = catalogue.get(out.layering.partner_perfume_id)
        base = catalogue.get(out.layering.base_perfume_id) or (catalogue.get(picks[0].perfume_id) if picks else None)
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
    chips = refine_chips(lang, picks, out.chips) if picks else []
    next_question = None
    if not picks and out.quick_replies:
        # A clarifying question with tappable quick replies: guided match always sends these; ordinary chat
        # sends them too whenever the reply asks a question (PRD "same quick answers in normal chat").
        opts = [Chip(id=_qr_slug(qr, i), label=qr) for i, qr in enumerate(out.quick_replies)]
        # Fix: the question shown to the shopper comes from the model's dedicated `question` field (one short
        # sentence, already sanitised by ground()) so it never duplicates -- or rambles on past -- `reply`.
        # Falls back to `reply` for backward compatibility if the model left `question` empty.
        question_text = out.question or out.reply
        next_question = QuizQuestion(id="guided_q" if guided else "chat_q", question=question_text, multi=bool(out.multi_select),
                                     options=opts, ask_reason=out.ask_reason, topic=out.topic,
                                     index=(guided or {}).get("index") if guided else None,
                                     max_index=(guided or {}).get("max") if guided else None)
    profile_summary = build_profile_summary(prof, lang) if guided and picks else []

    final_reply = out.reply or ""
    reply_path = "model"
    if picks and out.intent == "recommend":
        # Fix: reply text and result cards must always agree. If the server changed the model's own picks
        # (top-up, brand-variety swap, dropping the anchor) or the model's own reply names a perfume that
        # isn't among the final picks (or the anchor/layering partner), fall back to a safe template that
        # names only the actual first pick.
        final_ids = {c.perfume_id for c in picks}
        allowed_ids = set(final_ids)
        if prof.anchor_perfume_id:
            allowed_ids.add(prof.anchor_perfume_id)
        if layering:
            allowed_ids.add(layering.base_perfume_id)
            allowed_ids.add(layering.partner.perfume_id)
        dropped_names = [(catalogue.get(pid) or {}).get("name", "") for pid in original_pick_ids if pid not in final_ids]
        survivors = sum(1 for pid in original_pick_ids if pid in final_ids)
        # The shopper's own moment titles ("Golden hour on the sand") may echo a perfume name; they are never
        # read as naming a perfume the cards do not show.
        feel = sc.feel_titles(prof, lang, limit=6)
        if survivors < 2 or not final_reply.strip():
            # Most of the model's picks were replaced, so its description is about other perfumes.
            final_reply = template_reply_for_picks(picks, prof, lang)
            reply_path = "template"
        elif dropped_names or _mentions_offpick_perfume(final_reply, allowed_ids, feel):
            before_rec = final_reply
            final_reply = reconcile_reply_with_picks(final_reply, picks, allowed_ids, dropped_names, prof, lang,
                                                     ignore=feel)
            reply_path = "template" if final_reply == template_reply_for_picks(picks, prof, lang) \
                else ("reconciled" if final_reply != before_rec else "model")
    elif next_question is not None:
        # A question turn's reply is the acknowledgement (or short answer) that goes above the question: keep
        # the advisor's own sentences, minus any that repeat the question or describe a perfume not shown.
        # The perfumes currently on the shopper's screen count as shown, so a follow-up about them ("how do
        # the first two compare?") keeps the advisor's answer instead of coming back as an empty bubble.
        allowed_ids = set(s.get("last_results") or [])
        if prof.anchor_perfume_id:
            allowed_ids.add(prof.anchor_perfume_id)
        trimmed = trim_question_turn_reply(final_reply, next_question.question, allowed_ids, bool(guided))
        if trimmed != final_reply:
            reply_path = "trimmed" if trimmed else "stripped"
        final_reply = trimmed

    log.info("llm_chat sid=%s intent=%s | model_picks=%s kept=%d dropped=%s topped_up=%d brand_swaps=%d | "
             "reply=%s | agent=%.1fs post=%.1fs total=%.1fs",
             s["session_id"][:8], out.intent, original_pick_ids, kept_after_filter, drop_why,
             max(0, len(picks) - kept_after_filter) if out.intent == "recommend" else 0, brand_swaps,
             reply_path, result.seconds, time.perf_counter() - t_turn - result.seconds,
             time.perf_counter() - t_turn)

    return AgentReply(session_id=s["session_id"], language=lang, reply=final_reply, picks=picks, layering=layering, chips=chips,
                      intent=out.intent, profile=prof, next_question=next_question, guided=bool(guided),
                      profile_summary=profile_summary)


@app.post("/api/guide/start")
def guide_start(body: GuideBody, request: Request):
    """Starts "Guided match": the first question ("who is this for?") is instant, no model call."""
    rate_limit(request)
    s = load_session(body.session_id)
    lang = body.lang if body.lang in T else s["language"]
    s["language"] = lang
    g = guided_state(s)
    g["active"], g["count"], g["asked"], g["asked_topics"] = True, 1, ["guided_for"], []
    db.add_event(s["session_id"], "guided_started", {})
    q = guided_for_question(lang)
    set_pending_question(g, q)
    reply = AgentReply(session_id=s["session_id"], language=lang, reply=T[lang]["g_intro"],
                       next_question=q, intent="chat", profile=taste(s), guided=True)
    s["history"].append({"role": "assistant", "text": reply.reply})
    db.save_session(s)
    return reply


@app.post("/api/guide/finish")
async def guide_finish(body: GuideBody, request: Request):
    """"Show my picks now": forces a recommendation from whatever the guided interview has learned so far."""
    rate_limit(request)
    s = load_session(body.session_id)
    lang = body.lang if body.lang in T else s["language"]
    db.add_event(s["session_id"], "guided_finished_early", {"count": guided_state(s).get("count", 0)})
    reply = await guided_recommend_now(s, T[lang]["g_show_picks"], lang)
    s["history"].append({"role": "assistant", "text": reply.reply})
    db.save_session(s)
    return reply


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


@app.get("/api/admin/usage")
def admin_usage(days: int = 7, authorization: str = Header(default="")):
    if authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(401, "Unauthorized")
    days = max(1, min(90, days))
    return db.usage_summary(time.time() - days * 86400)


@app.get("/api/admin/conversations")
def admin_conversations(days: int = 7, limit: int = 50, authorization: str = Header(default="")):
    if authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(401, "Unauthorized")
    days, limit = max(1, min(90, days)), max(1, min(200, limit))
    return {"conversations": db.recent_conversations(time.time() - days * 86400, limit)}


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
        return FileResponse(STATIC_DIR / "widget.js", media_type="application/javascript",
                            headers={"Cache-Control": "public, max-age=300, stale-while-revalidate=86400"})

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
