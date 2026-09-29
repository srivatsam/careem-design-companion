"""Rule-based taste-profile extraction from free text (English and Arabic).

Used by the guided quiz, by the no-LLM fallback, and by the mock model. The LLM path does the same job better;
this keeps the product working when the model is down (PRD guardrail: fallback).
"""
from __future__ import annotations

import re

from app.data import taxonomy as tx
from app.schemas import TasteProfile

NEG_EN = r"(?:not|no|without|hate|dislike|don't like|do not like|avoid|never|less|too)"
NEG_AR = r"(?:لا أحب|لا احب|أكره|اكره|بدون|غير|ما أحب|ما احب|ليس|مش|أقل)"

STRENGTH_WORDS = {
    "very light": 1, "barely there": 1, "skin scent": 1, "خفيف جدا": 1, "خفيف جداً": 1,
    "light": 2, "lighter": 2, "subtle": 2, "soft": 2, "not too strong": 2, "not strong": 2, "خفيف": 2, "ناعم": 2,
    "moderate": 3, "medium": 3, "متوسط": 3,
    "strong": 4, "stronger": 4, "long lasting": 4, "long-lasting": 4, "قوي": 4, "يدوم": 4, "ثابت": 4,
    "very strong": 5, "beast mode": 5, "قوي جدا": 5, "قوي جداً": 5,
}
SEASON_WORDS = {
    "spring": "spring", "summer": "summer", "autumn": "autumn", "fall": "autumn", "winter": "winter", "hot weather": "summer",
    "الربيع": "spring", "ربيع": "spring", "الصيف": "summer", "صيف": "summer", "الخريف": "autumn", "خريف": "autumn",
    "الشتاء": "winter", "شتاء": "winter", "حر": "summer", "للصيف": "summer", "للشتاء": "winter", "للربيع": "spring", "للخريف": "autumn",
}
OCCASION_WORDS = {
    "office": "office", "work": "office", "daily": "everyday", "everyday": "everyday", "every day": "everyday", "casual": "everyday",
    "evening": "evening", "night": "evening", "nights": "evening", "party": "evening", "club": "evening", "date": "date", "romantic": "date",
    "special event": "date", "special events": "date", "special occasion": "date", "special occasions": "date",
    "wedding": "wedding", "gift": "gift", "present": "gift", "gym": "outdoor", "sport": "outdoor", "outdoor": "outdoor", "beach": "outdoor",
    "العمل": "office", "الدوام": "office", "يومي": "everyday", "المساء": "evening", "سهرة": "evening", "ليل": "evening", "موعد": "date",
    "مناسبة خاصة": "date", "مناسبات خاصة": "date",
    "زفاف": "wedding", "عرس": "wedding", "هدية": "gift", "هديه": "gift", "رياضة": "outdoor",
    "للمساء": "evening", "للسهرة": "evening", "للعمل": "office", "للدوام": "office", "للزفاف": "wedding", "للعرس": "wedding",
    "للرياضة": "outdoor", "للهدية": "gift", "للاستخدام اليومي": "everyday", "لليومي": "everyday",
}
MOOD_WORDS = {
    "romantic": "romantic", "sexy": "romantic", "seductive": "romantic", "energetic": "energetic", "fresh": "energetic", "clean": "calm",
    "cozy": "cozy", "cosy": "cozy", "warm": "cozy", "comforting": "cozy", "bold": "bold", "confident": "bold", "powerful": "bold",
    "elegant": "elegant", "classy": "elegant", "sophisticated": "elegant", "playful": "playful", "fun": "playful", "sweet": "playful",
    "calm": "calm", "relaxed": "calm", "mysterious": "mysterious", "dark": "mysterious", "smoky": "mysterious",
    "رومانسي": "romantic", "جذاب": "romantic", "منعش": "energetic", "نشيط": "energetic", "دافئ": "cozy", "مريح": "cozy",
    "جريء": "bold", "قوي": "bold", "أنيق": "elegant", "راقي": "elegant", "مرح": "playful", "هادئ": "calm", "غامض": "mysterious",
}
GENDER_WORDS = {"for men": "men", "for him": "men", "masculine": "men", "my husband": "men", "my brother": "men", "my father": "men",
                "for women": "women", "for her": "women", "feminine": "women", "my wife": "women", "my sister": "women", "my mother": "women",
                "للرجال": "men", "رجالي": "men", "زوجي": "men", "أخي": "men", "للنساء": "women", "نسائي": "women", "زوجتي": "women", "أختي": "women", "أمي": "women"}

_ANCHOR_RE = re.compile(
    r"(?:similar to|smells? like|like|love|loves|wear|wears|own|already have|reminds me of|such as|tell me about|about|what is|info on|dupe (?:of|for)"
    r"|مثل|يشبه|شبيه بـ?|أخبرني عن|اخبرني عن|ما هو|بديل)\s+([A-Z\u0600-\u06FF][\w'&.\-\u0600-\u06FF ]{2,40}?)"
    r"(?=\s+(?:but|and|by|which|that|though|for|لكن|بس|ولكن|من)\b|[,.!?؟]|$)",
    re.I,
)
_LOOKUP_RE = re.compile(r"tell me about|what is|info on|أخبرني عن|اخبرني عن|ما هو", re.I)
_AR_NOTE_LABELS = None

# Words that make a message plausibly about a perfume, independent of any specific note/brand name.
_PERFUME_CUE_RE = re.compile(r"perfume|scent|fragrance|smell|cologne|eau de|oud|عطر|رائحة|ريحة|عود|بخور", re.I)

# Anchor triggers ("what is X", "tell me about X") that are just as likely to introduce a general-knowledge
# question ("What is the capital of France?") as a perfume name. Anything else in _ANCHOR_RE ("like", "similar
# to", "wear", "already have", ...) is inherently about a thing the user owns/likes/wears, which in this
# product is always a perfume, so those stay ungated.
_AMBIGUOUS_ANCHOR_TRIGGERS = ("tell me about", "about", "what is", "info on", "أخبرني عن", "اخبرني عن", "ما هو")


def has_perfume_cue(text: str) -> bool:
    return bool(_PERFUME_CUE_RE.search(text or ""))


def _is_ambiguous_anchor_trigger(matched_text: str) -> bool:
    t = matched_text.strip().lower()
    return any(t.startswith(trig) for trig in _AMBIGUOUS_ANCHOR_TRIGGERS)


def anchor_needs_confirmation(text: str) -> bool:
    """True when extract_profile's anchor_perfume (if any) came from an ambiguous trigger ("what is X",
    "tell me about X") and the message has no other perfume cue. Callers should only trust such an anchor
    when it actually resolves in the catalogue; otherwise it is more likely a general-knowledge question
    than an unknown perfume, and should be dropped instead of reported as "not found"."""
    a = _ANCHOR_RE.search(text or "")
    if not a:
        return False
    return _is_ambiguous_anchor_trigger(a.group(0)) and not has_perfume_cue(text)


def _is_taxonomy_phrase(cand: str) -> bool:
    global _AR_NOTE_LABELS
    if _AR_NOTE_LABELS is None:
        _AR_NOTE_LABELS = {spec["ar"] for spec in tx.load()["notes"].values()} | {f["ar"] for f in tx.load()["families"].values()}
    c = cand.strip().lower()
    if tx.normalise_note(c) is not None:
        return True
    syns = {w for group in tx.load()["family_synonyms"].values() for w in group}
    if c in syns:
        return True
    if _has_arabic(c):
        # Arabic has no capitalisation cue, so any descriptive word (note, family, strength, mood) means "not a name".
        vocab = _AR_NOTE_LABELS | syns | set(STRENGTH_WORDS) | set(MOOD_WORDS) | set(SEASON_WORDS) | set(OCCASION_WORDS)
        words = [w[2:] if w.startswith("ال") else w for w in c.split()]
        return any(w in vocab or ("ل" + w) in vocab for w in words)
    return False


_CHEAPER_RE = re.compile(r"cheaper|less expensive|more affordable|lower price|budget version|dupe|أرخص|بديل|أقل سعر", re.I)
_BUDGET_RE = re.compile(
    r"(?:under|below|less than|max|maximum|up to|budget(?: of| is)?|around|within|أقل من|تحت|بحدود|حوالي|ميزانيتي|بميزانية)\s*(?:aed|dhs|dh|درهم)?\s*([0-9][0-9,]{1,6})\s*(?:aed|dhs|dh|درهم|dirhams)?",
    re.I,
)
_BUDGET_RE2 = re.compile(r"(?:aed|dhs|dh)\s*([0-9][0-9,]{1,6})|([0-9][0-9,]{1,6})\s*(?:aed|dhs|dh|dirhams|درهم)", re.I)


def _has_arabic(text: str) -> bool:
    return bool(re.search(r"[؀-ۿ]", text))


def _note_mentions(text: str) -> list[tuple[str, int]]:
    """All (master_note, position) pairs found in the text, using the synonym index and Arabic labels."""
    found: list[tuple[str, int]] = []
    lowered = text.lower()
    for key, master in tx.synonym_index().items():
        if len(key) < 3:
            continue
        for m in re.finditer(rf"(?<![a-z]){re.escape(key)}(?:s|es)?(?![a-z])", lowered):
            found.append((master, m.start()))
    for master, spec in tx.load()["notes"].items():
        ar = spec["ar"]
        for m in re.finditer(re.escape(ar), text):
            found.append((master, m.start()))
        for m in re.finditer("ال" + re.escape(ar), text):
            found.append((master, m.start()))
    # Dedupe by (note, position)
    return sorted(set(found), key=lambda x: x[1])


POS_EN = r"(?:love|loves|like|likes|adore|want|prefer|enjoy)"
POS_AR = r"(?:أحب|احب|وأحب|واحب|يعجبني|أفضل|أريد|ابغى|ابي)"


def _negated(text: str, pos: int) -> bool:
    """True when a negation precedes the mention within a short window and no positive verb comes after it."""
    window = text[max(0, pos - 32):pos].lower()
    neg = list(re.finditer(rf"(?<![a-z\u0600-\u06FF])(?:{NEG_EN}|{NEG_AR})(?![a-z\u0600-\u06FF])", window))
    if not neg:
        return False
    last_neg = neg[-1].end()
    between = window[last_neg:]
    if re.search(rf"(?<![a-z\u0600-\u06FF])(?:{POS_EN}|{POS_AR})(?![a-z\u0600-\u06FF])", between):
        return False
    return len(between.split()) <= 3


def extract_profile(text: str) -> TasteProfile:
    prof = TasteProfile(free_text=text.strip())
    if not text or not text.strip():
        return prof
    lowered = text.lower()

    anchor_span = None
    a = _ANCHOR_RE.search(text)
    if a:
        cand = re.sub(r"^(?:عطر|perfume|fragrance|the)\s+", "", a.group(1).strip(" .,"), flags=re.I)
        if len(cand) >= 3 and not _is_taxonomy_phrase(cand) and not re.fullmatch(r"(?:it|this|that|something|one|them|me|you|my \w+|a \w+)", cand, re.I):
            # "what is X" / "tell me about X" are just as likely to introduce a general-knowledge question
            # ("What is the capital of France?") as a perfume lookup. The candidate is still extracted here
            # (a caller with catalogue access may find it really is a perfume name), but callers should treat
            # an *unresolved* ambiguous anchor as "no anchor" rather than "unknown perfume" -- see
            # anchor_needs_confirmation().
            prof.anchor_perfume = cand
            anchor_span = (a.start(1), a.end(1))
            if _CHEAPER_RE.search(text):
                prof.free_text = prof.free_text  # budget relative to anchor is resolved by the caller
                prof.anchor_cheaper = True  # type: ignore[attr-defined]

    def in_anchor(pos: int) -> bool:
        return anchor_span is not None and anchor_span[0] <= pos < anchor_span[1]

    # Notes: liked vs disliked by negation window.
    for master, pos in _note_mentions(text):
        if in_anchor(pos):
            continue
        if _negated(text, pos):
            if master not in prof.disliked_notes:
                prof.disliked_notes.append(master)
        elif master not in prof.liked_notes and master not in prof.disliked_notes:
            prof.liked_notes.append(master)

    # Families with negation ("not sweet" -> avoid gourmand).
    for fam, syns in tx.load()["family_synonyms"].items():
        for syn in syns:
            for m in re.finditer(rf"(?<![a-z؀-ۿ]){re.escape(syn)}(?![a-z؀-ۿ])", lowered if not _has_arabic(syn) else text):
                if _negated(text, m.start()):
                    if fam not in prof.avoid_families:
                        prof.avoid_families.append(fam)
                elif fam not in prof.families:
                    prof.families.append(fam)
    prof.families = [f for f in prof.families if f not in prof.avoid_families]

    for phrase, level in sorted(STRENGTH_WORDS.items(), key=lambda kv: -len(kv[0])):
        m = re.search(rf"(?<![a-z\u0600-\u06FF]){re.escape(phrase)}(?![a-z\u0600-\u06FF])", lowered)
        if m and not in_anchor(m.start()):
            prof.strength = level
            break
    for phrase, season in SEASON_WORDS.items():
        if re.search(rf"(?<![a-z؀-ۿ]){re.escape(phrase)}(?![a-z؀-ۿ])", lowered):
            if season not in prof.seasons:
                prof.seasons.append(season)
    for phrase, occ in OCCASION_WORDS.items():
        if re.search(rf"(?<![a-z؀-ۿ]){re.escape(phrase)}(?![a-z؀-ۿ])", lowered):
            if occ not in prof.occasions:
                prof.occasions.append(occ)
    for phrase, mood in MOOD_WORDS.items():
        for m in re.finditer(rf"(?<![a-z؀-ۿ]){re.escape(phrase)}(?![a-z؀-ۿ])", lowered):
            if not _negated(text, m.start()) and mood not in prof.moods:
                prof.moods.append(mood)
    for phrase, gender in GENDER_WORDS.items():
        if phrase in lowered:
            prof.gender = gender
            break

    m = _BUDGET_RE.search(text) or _BUDGET_RE2.search(text)
    if m:
        raw = next(g for g in m.groups() if g)
        try:
            prof.budget_aed = float(raw.replace(",", ""))
        except ValueError:
            pass

    return prof


def is_lookup(text: str) -> bool:
    return bool(_LOOKUP_RE.search(text))


def wants_wishlist(text: str) -> bool:
    return bool(re.search(r"\b(?:save|wishlist|wish list|bookmark|keep (?:them|these|it))\b|احفظ|حفظ|قائمة الأمنيات|قائمة أمنياتي", text, re.I))


def is_medical(text: str) -> bool:
    return bool(re.search(r"pregnan|allerg|asthma|rash|eczema|safe (?:for|during)|breastfeed|medical|doctor|حامل|حساسية|ربو|طبي|آمن", text, re.I))


def is_injection(text: str) -> bool:
    return bool(re.search(r"ignore (?:your|all|the) (?:rules|instructions)|system prompt|discount code|coupon|reveal your|jailbreak|developer mode|تجاهل (?:القواعد|التعليمات)|كود خصم|رمز خصم", text, re.I))


_SEASON_HINT_RE = re.compile(
    r"hot weather|cold weather|warm weather|humid|summer|winter|spring season|autumn|fall season|season|"
    r"صيف|شتاء|حر|رطوبة|خريف|ربيع|موسم",
    re.I,
)

# Words/phrases that mean the message is a follow-up about perfumes already shown (see main.py chat(), which
# also checks whether the text names one of the session's shown picks directly).
_SHOWN_PICKS_RE = re.compile(
    r"\b(?:first|second|third|these|them|which one|compare)\b|"
    r"الأول(?:ى)?|الثاني(?:ة)?|الثالث(?:ة)?|هذه|هؤلاء|قارن|مقارنة|أيهما|ايهما",
    re.I,
)


def is_off_topic(text: str) -> bool:
    if has_perfume_cue(text):
        return False
    if _SEASON_HINT_RE.search(text):
        return False
    return bool(re.search(r"weather|stock|crypto|bitcoin|football|recipe|homework|python|javascript|politic|election|طقس|أسهم|كرة", text, re.I))


def refers_to_shown_picks(text: str) -> bool:
    return bool(_SHOWN_PICKS_RE.search(text or ""))


def wants_recommendation(text: str) -> bool:
    return bool(re.search(r"recommend|suggest|pick|show me|what should|find me|looking for|i want|i need|give me|options|layer|layering|pair|goes well with|what goes|"
                          r"اقترح|رشح|أريد|ابغى|ابي|أبحث|بدي|ما هو أفضل|أعطني|طبق|يطبق|تطبيق|يناسب مع", text, re.I))


def says_yes(text: str) -> bool:
    return bool(re.fullmatch(r"\s*(?:yes|yes please|yeah|yep|sure|ok|okay|save|save it|save them|do it|please|نعم|أجل|اي|ايوه|أيوه|تمام|احفظ|احفظها|موافق)[.! ]*\s*", text.strip(), re.I))


# =================================================================================================================
# Guided match: interpreting an answer against the question it actually answers
# =================================================================================================================
# Live bug: a guided answer was read on its own ("vanilla" answering "Anything you dislike?" was stored as a
# LIKED note) and whole answers were lost (occasion, strength, the named anchor perfume). Everything below reads
# the shopper's message as an answer to the pending question FIRST, deterministically and independently of the
# model, and only then falls back to the generic free-text extraction -- constrained by that question's topic.

GUIDED_TOPICS = ("recipient", "scenario", "scenario_moment", "occasion", "liked_scents", "disliked_scents",
                 "strength", "budget", "anchor_feedback", "other")

# Answers that store nothing but still count the topic as asked.
_SKIP_OPTION_IDS = {"skip", "none", "no_budget", "nothing"}
_SKIP_RE = re.compile(
    r"^\s*(?:skip|skip (?:this|it)(?: question)?|none|nothing|nothing (?:in particular|to avoid|specific)|"
    r"no(?:ne)? preference|no preferences|not sure|i don'?t know|don'?t know|doesn'?t matter|any|anything|whatever|"
    r"تخطي|تخطى|تجاوز|لا شيء|لا شيء محدد|لا شئ|لا أعرف|لا اعرف|لا يهم|أي شيء|اي شيء)\s*[.!؟?]*\s*$",
    re.I,
)
_NO_BUDGET_RE = re.compile(r"no limit|no budget|unlimited|any (?:budget|price)|price (?:is )?no|doesn'?t matter|"
                           r"بدون حد|بلا حد|لا يوجد حد|مفتوح|لا يهم", re.I)
_BUDGET_RANGE_RE = re.compile(r"([0-9][0-9,]{1,6})\s*(?:-|–|—|to|and|إلى|الى|حتى|و)\s*([0-9][0-9,]{1,6})")
_NUMBER_RE = re.compile(r"([0-9][0-9,]{1,6})")
# "(1-2)" / "(4-5)" hints inside a strength option label ("Light (1-2)", "Strong (4-5)").
_LEVEL_HINT_RE = re.compile(r"\(?\s*([1-5])\s*(?:-|–|—|to)\s*([1-5])\s*\)?")

_GUIDED_FOR_RE = {
    "gift_her": re.compile(r"gift.*\bher\b|\bher\b.*gift|for her|\bwife\b|\bmother\b|\bsister\b|\bgirlfriend\b|"
                           r"هدية.*لها|لها|زوجتي|أمي|أختي", re.I),
    "gift_him": re.compile(r"gift.*\bhim\b|\bhim\b.*gift|for him|\bhusband\b|\bfather\b|\bbrother\b|\bboyfriend\b|"
                           r"هدية.*له|زوجي|أخي", re.I),
    "gift_unsure": re.compile(r"unsure|not sure|don'?t know|\bgift\b|هدية|لا أعرف", re.I),
    "self": re.compile(r"for me|myself|\bme\b|لي أنا|لنفسي", re.I),
}
GUIDED_FOR_VALUES = ("gift_her", "gift_him", "gift_unsure", "self")
GUIDED_FOR_GENDER = {"gift_her": "women", "gift_him": "men"}


def parse_guided_for(text: str) -> str | None:
    """The answer to guided match's instant first question ("who is this for?"): a plain phrase, not a taxonomy
    term, so it needs its own small parser rather than extract_profile."""
    for value in GUIDED_FOR_VALUES:
        if _GUIDED_FOR_RE[value].search(text or ""):
            return value
    return None


def _split_answer(text: str) -> list[str]:
    """A multi-select answer arrives comma-separated ("vanilla, rose"); single answers come back as one part."""
    parts = [p.strip(" .!؟?،") for p in re.split(r"[,،;؛/]|\band\b|\bor\b", text or "")]
    return [p for p in parts if p]


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().strip(" .!؟?،")).lower()


def _match_option(part: str, options: list[dict]) -> dict | None:
    """Matches one answer fragment to one of the pending question's options, by id or label, case-insensitively.
    Also accepts a label with its parenthetical stripped ("Light" for "Light (1-2)")."""
    p = _norm(part)
    if not p:
        return None
    for opt in options or []:
        oid, label = _norm(opt.get("id")), _norm(opt.get("label"))
        bare = _norm(re.sub(r"\(.*?\)", " ", opt.get("label") or ""))
        if p in {oid, label, bare} or _norm(oid.replace("_", " ")) == p:
            return opt
    for opt in options or []:
        label, bare = _norm(opt.get("label")), _norm(re.sub(r"\(.*?\)", " ", opt.get("label") or ""))
        if len(p) >= 3 and (p == bare or (bare and (p in bare or bare in p)) or (label and p in label)):
            return opt
    return None


def _is_skip(opt: dict | None, part: str) -> bool:
    if opt and _norm(opt.get("id")) in _SKIP_OPTION_IDS:
        return True
    return bool(_SKIP_RE.match(part or ""))


def _family_of(value: str) -> str | None:
    key = _norm(value)
    if not key:
        return None
    if key in tx.load()["families"]:
        return key
    for fam, words in tx.load()["family_synonyms"].items():
        if key in {w.lower() for w in words}:
            return fam
    return None


def _strength_level(value: str) -> int | None:
    """"Lighter" / "Light (1-2)" / "خفيف" / "3" -> a 1..5 strength. Word wins over any number in the label."""
    raw = (value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"[1-5]", raw):
        return int(raw)
    low = raw.lower()
    for phrase, level in sorted(STRENGTH_WORDS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?<![a-z؀-ۿ]){re.escape(phrase)}(?![a-z؀-ۿ])", low):
            return level
    hint = _LEVEL_HINT_RE.search(raw)
    if hint:
        lo, hi = int(hint.group(1)), int(hint.group(2))
        return lo if lo <= 2 else hi if lo >= 4 else lo
    m = re.search(r"[1-5]", raw)
    return int(m.group(0)) if m else None


def _budget_value(value: str) -> tuple[float | None, bool]:
    """Returns (budget, no_limit). Handles "200-400" (-> 400), "Under 200", "400 AED", "No limit"."""
    raw = (value or "").strip()
    if not raw:
        return None, False
    if _NO_BUDGET_RE.search(raw):
        return None, True
    if re.fullmatch(r"0+", raw):
        return None, True
    rng = _BUDGET_RANGE_RE.search(raw)
    if rng:
        try:
            return max(float(rng.group(1).replace(",", "")), float(rng.group(2).replace(",", ""))), False
        except ValueError:
            return None, False
    m = _NUMBER_RE.search(raw)
    if m:
        try:
            n = float(m.group(1).replace(",", ""))
        except ValueError:
            return None, False
        return (n, False) if n > 0 else (None, True)
    return None, False


def _add(values: list[str], value: str | None) -> None:
    if value and value not in values:
        values.append(value)


def interpret_guided_answer(text: str, pending: dict | None) -> TasteProfile:
    """Reads `text` as the answer to `pending` -- the guided question that was actually asked.

    `pending` is {"topic", "id", "multi", "question", "options": [{"id", "label"}]} as stored by the server when
    it asked the question. The answer is first matched against the question's own options (by id or label,
    case-insensitively; a multi-select answer arrives comma-separated); anything unmatched falls back to the
    generic free-text extraction, constrained by the topic -- so under "what do you dislike?" an extracted note
    becomes a DISLIKE, never a like. Returns only what this answer says; the caller merges it into the profile.
    """
    text = (text or "").strip()
    topic = (pending or {}).get("topic")
    if not text or topic not in GUIDED_TOPICS:
        return extract_profile(text)

    options = (pending or {}).get("options") or []
    if topic in ("scenario", "scenario_moment"):
        # Scenario titles are whole phrases (some hold a comma or an "and"), so they are matched as phrases by the
        # scenario library rather than split into fragments like note chips.
        if _SKIP_RE.match(text) or any(_norm(o.get("id")) in _SKIP_OPTION_IDS and _norm(text) in
                                       {_norm(o.get("id")), _norm(o.get("label"))} for o in options):
            return TasteProfile(free_text=text)
        from app.data import scenarios as sc
        return sc.interpret_answer(text, pending, topic)
    pairs = [(_match_option(part, options), part) for part in _split_answer(text)]
    answers = [(opt, part) for opt, part in pairs if not _is_skip(opt, part)]
    prof = TasteProfile(free_text=text)
    if not answers:
        return prof  # an explicit skip stores nothing; the topic still counts as asked

    base = extract_profile(text)
    tokens = [(opt.get("id") or "", opt.get("label") or "", part) if opt else ("", "", part) for opt, part in answers]

    if topic == "recipient":
        prof = base
        value = next((tid for tid, _, _ in tokens if tid in GUIDED_FOR_VALUES), None) or parse_guided_for(text)
        if value:
            prof.guided_for = value
            prof.gender = prof.gender or GUIDED_FOR_GENDER.get(value)
        return prof

    if topic in ("liked_scents", "anchor_feedback"):
        for tid, label, part in tokens:
            negative = extract_profile(part)
            if negative.disliked_notes or negative.avoid_families:
                # An explicit negation inside a "what do you love?" answer ("no oud", "not too sweet") still
                # means a dislike -- never map that fragment onto the option it happens to name.
                for n in negative.disliked_notes:
                    _add(prof.disliked_notes, n)
                for f in negative.avoid_families:
                    _add(prof.avoid_families, f)
                continue
            for cand in (tid, label, part):
                note = tx.normalise_note(cand) if cand else None
                if note:
                    _add(prof.liked_notes, note)
                    break
                fam = _family_of(cand)
                if fam:
                    _add(prof.families, fam)
                    break
        for n in base.liked_notes:
            _add(prof.liked_notes, n)
        for n in base.disliked_notes:     # an explicit negation inside the answer still wins ("no oud")
            _add(prof.disliked_notes, n)
        for f in base.families:
            _add(prof.families, f)
        for f in base.avoid_families:
            _add(prof.avoid_families, f)
        prof.anchor_perfume = base.anchor_perfume       # "something like X" / "I wear X" -> the anchor
        prof.anchor_cheaper = base.anchor_cheaper

    elif topic == "disliked_scents":
        for tid, label, part in tokens:
            for cand in (tid, label, part):
                note = tx.normalise_note(cand) if cand else None
                if note:
                    _add(prof.disliked_notes, note)
                    break
                fam = _family_of(cand)
                if fam:
                    _add(prof.avoid_families, fam)
                    break
        # Under "what do you dislike?" every note the free-text extractor finds is a dislike, however it was
        # phrased ("vanilla" and "no vanilla" mean the same thing here). Same for families.
        for n in base.liked_notes + base.disliked_notes:
            _add(prof.disliked_notes, n)
        for f in base.families + base.avoid_families:
            _add(prof.avoid_families, f)

    elif topic == "strength":
        level = None
        for tid, label, part in tokens:
            level = next((lv for lv in (_strength_level(part), _strength_level(label), _strength_level(tid))
                          if lv is not None), None)
            if level is not None:
                break
        prof.strength = level if level is not None else base.strength

    elif topic == "occasion":
        moods, occasions = tx.load()["moods"], tx.load()["occasions"]
        for tid, label, part in tokens:
            for cand in (tid, label, part):
                key = _norm(cand)
                if not key:
                    continue
                if key in occasions:
                    _add(prof.occasions, key)
                    break
                if key in moods:
                    _add(prof.moods, key)
                    break
                if key in OCCASION_WORDS:
                    _add(prof.occasions, OCCASION_WORDS[key])
                    break
                if key in MOOD_WORDS:
                    _add(prof.moods, MOOD_WORDS[key])
                    break
        for o in base.occasions:
            _add(prof.occasions, o)
        for m in base.moods:
            _add(prof.moods, m)
        for s in base.seasons:
            _add(prof.seasons, s)

    elif topic == "budget":
        for tid, label, part in tokens:
            for cand in (tid, label, part):
                value, no_limit = _budget_value(cand)
                if no_limit:
                    return prof                 # "No limit": budget stays unknown, the topic counts as asked
                if value is not None:
                    prof.budget_aed = value
                    break
            if prof.budget_aed is not None:
                break
        if prof.budget_aed is None:
            prof.budget_aed = base.budget_aed

    # High-precision extras the shopper volunteered alongside their answer ("Everyday, under 300").
    if prof.budget_aed is None and topic != "budget":
        prof.budget_aed = base.budget_aed
    if prof.strength is None and topic != "strength":
        prof.strength = base.strength
    if prof.signal_count() == 0:
        return base  # the answer did not fit its topic at all: better a generic reading than nothing
    return prof
