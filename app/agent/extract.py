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
    "wedding": "wedding", "gift": "gift", "present": "gift", "gym": "outdoor", "sport": "outdoor", "outdoor": "outdoor", "beach": "outdoor",
    "العمل": "office", "الدوام": "office", "يومي": "everyday", "المساء": "evening", "سهرة": "evening", "ليل": "evening", "موعد": "date",
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


def is_off_topic(text: str) -> bool:
    if re.search(r"perfume|scent|fragrance|smell|cologne|eau de|oud|عطر|رائحة|ريحة|عود|بخور", text, re.I):
        return False
    return bool(re.search(r"weather|stock|crypto|bitcoin|football|recipe|homework|python|javascript|politic|election|طقس|أسهم|كرة", text, re.I))


def wants_recommendation(text: str) -> bool:
    return bool(re.search(r"recommend|suggest|pick|show me|what should|find me|looking for|i want|i need|give me|options|layer|layering|pair|goes well with|what goes|"
                          r"اقترح|رشح|أريد|ابغى|ابي|أبحث|بدي|ما هو أفضل|أعطني|طبق|يطبق|تطبيق|يناسب مع", text, re.I))


def says_yes(text: str) -> bool:
    return bool(re.fullmatch(r"\s*(?:yes|yes please|yeah|yep|sure|ok|okay|save|save it|save them|do it|please|نعم|أجل|اي|ايوه|أيوه|تمام|احفظ|احفظها|موافق)[.! ]*\s*", text.strip(), re.I))
