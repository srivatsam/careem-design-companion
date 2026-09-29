"""Scenario library for guided match: moods and moments a shopper can picture, mapped onto the taxonomy.

A shopper who does not speak perfume can still say "barefoot on a beach at sunset". Each scenario (and each of its
three follow-up moments) carries a deterministic taste mapping that only uses taxonomy values the recommender
understands: liked notes, families, moods, occasions, seasons and, for moments, a strength level. The same library
reads guided answers (option id or title, either language) and free chat ("a beach holiday", "حفلة فخمة"), so both
paths agree on what a moment means.

Every string here is plain text. The widget renders titles and captions with textContent and picks the motif SVG
from its own static table; MOTIFS is the whitelist both sides share.
"""
from __future__ import annotations

import re
from functools import lru_cache

from app.schemas import TasteProfile

MAX_SCENARIOS = 3

# The abstract motifs the widget knows how to draw (see ICONS.motifs in app/static/widget.js).
MOTIFS = ("sun_waves", "sparkle", "flame", "petals", "candle", "linen", "briefcase", "spice", "citrus", "moon_stars")

_TASTE_LISTS = ("liked_notes", "families", "moods", "occasions", "seasons")


def _s(en: str, ar: str) -> dict:
    return {"en": en, "ar": ar}


# Order matters: it is the grid order (5 across on desktop, 2 across on phones), arranged so no two cards of the
# same family colour sit next to each other in either layout.
SCENARIOS: list[dict] = [
    {
        "id": "beach", "family": "aquatic", "motif": "sun_waves",
        "title": _s("Barefoot on a beach at sunset", "حافي القدمين على شاطئ الغروب"),
        "caption": _s("Salt air, warm skin, golden light", "نسيم مالح وبشرة دافئة وضوء ذهبي"),
        "short": _s("beach", "أجواء الشاطئ"),
        "taste": {"families": ["aquatic", "fresh"], "liked_notes": ["sea notes", "citrus"], "moods": ["calm"],
                  "seasons": ["summer"]},
        "keywords": {"en": ["beach", "beaches", "seaside", "by the sea", "coast", "shore"],
                     "ar": ["شاطئ", "شواطئ", "بحر"]},
        "moments": [
            {"id": "beach_sunrise_swim", "family": "aquatic",
             "title": _s("Sunrise swim, salty skin", "سباحة الفجر وملح على البشرة"),
             "caption": _s("Crisp, airy and barely there", "منعش وخفيف كالنسيم"),
             "taste": {"liked_notes": ["sea notes", "mineral notes"], "families": ["aquatic"], "moods": ["calm"],
                       "strength": 2},
             "keywords": {"en": ["sunrise swim", "morning swim"], "ar": ["سباحة الفجر", "سباحة الصباح"]}},
            {"id": "beach_golden_hour", "family": "fruity",
             "title": _s("Golden hour on the sand", "الساعة الذهبية على الرمال"),
             "caption": _s("Juicy fruit on sun-warmed skin", "فاكهة عصيرية على بشرة دفّأتها الشمس"),
             "taste": {"liked_notes": ["tropical fruits", "orange"], "families": ["fruity"], "moods": ["playful"],
                       "strength": 3},
             "keywords": {"en": ["golden hour"], "ar": ["الساعة الذهبية"]}},
            {"id": "beach_island", "family": "floral",
             "title": _s("A tropical island escape", "هروب إلى جزيرة استوائية"),
             "caption": _s("Coconut, white flowers, soft vanilla", "جوز الهند وزهور بيضاء وفانيليا ناعمة"),
             "taste": {"liked_notes": ["tropical fruits", "white flowers", "vanilla"], "families": ["floral"],
                       "moods": ["romantic"], "strength": 3},
             "keywords": {"en": ["tropical island", "island"], "ar": ["جزيرة استوائية", "جزيرة"]}},
        ],
    },
    {
        "id": "rooftop", "family": "amber", "motif": "sparkle",
        "title": _s("Walking into a rooftop party", "أدخل حفلة راقية على السطح"),
        "caption": _s("City lights and every eye on you", "أضواء المدينة وكل الأنظار نحوك"),
        "short": _s("rooftop party", "أجواء الحفلة"),
        "taste": {"families": ["amber"], "liked_notes": ["amber", "pepper"], "moods": ["bold"],
                  "occasions": ["evening"]},
        "keywords": {"en": ["party", "parties", "rooftop", "gala", "night out", "clubbing"],
                     "ar": ["حفلة", "حفلات", "سهرة فاخرة"]},
        "moments": [
            {"id": "rooftop_city_lights", "family": "fruity",
             "title": _s("Sequins and city lights", "ترتر وأضواء المدينة"),
             "caption": _s("Bright, fizzy and a little daring", "مشرق وفوّار وجريء قليلاً"),
             "taste": {"liked_notes": ["berries", "pepper"], "families": ["fruity"], "moods": ["playful"],
                       "strength": 3},
             "keywords": {"en": ["sequins", "city lights"], "ar": ["أضواء المدينة"]}},
            {"id": "rooftop_velvet_lounge", "family": "woody",
             "title": _s("The velvet lounge after midnight", "الصالة المخملية بعد منتصف الليل"),
             "caption": _s("Dark, smoky and magnetic", "داكن ومدخّن وآسر"),
             "taste": {"liked_notes": ["oud", "leather", "incense"], "families": ["woody"], "moods": ["mysterious"],
                       "strength": 4},
             "keywords": {"en": ["after midnight", "velvet lounge"], "ar": ["بعد منتصف الليل"]}},
            {"id": "rooftop_golden_entrance", "family": "amber",
             "title": _s("A golden entrance", "دخول ذهبي يخطف الأنظار"),
             "caption": _s("Saffron, amber and a trail that lingers", "زعفران وعنبر وأثر يدوم"),
             "taste": {"liked_notes": ["saffron", "amber", "vanilla"], "families": ["amber"], "moods": ["bold"],
                       "strength": 4},
             "keywords": {"en": ["grand entrance", "golden entrance"], "ar": ["دخول ذهبي"]}},
        ],
    },
    {
        "id": "fireside", "family": "gourmand", "motif": "flame",
        "title": _s("Wrapped in cashmere by the fire", "ملتفّ بالكشمير قرب المدفأة"),
        "caption": _s("Soft, warm and close to the skin", "ناعم ودافئ وقريب من البشرة"),
        "short": _s("fireside", "أجواء المدفأة"),
        "taste": {"families": ["gourmand", "woody"], "liked_notes": ["vanilla", "sandalwood"], "moods": ["cozy"],
                  "seasons": ["winter"]},
        "keywords": {"en": ["fireplace", "by the fire", "fireside", "cashmere", "cozy night in", "cosy night in",
                            "snuggled up"],
                     "ar": ["مدفأة", "قرب النار", "كشمير"]},
        "moments": [
            {"id": "fireside_cocoa", "family": "gourmand",
             "title": _s("Hot cocoa and a good book", "كاكاو ساخن وكتاب جميل"),
             "caption": _s("Creamy, sweet and comforting", "كريمي وحلو ومريح"),
             "taste": {"liked_notes": ["chocolate", "milk", "tonka bean"], "families": ["gourmand"],
                       "moods": ["cozy"], "strength": 3},
             "keywords": {"en": ["hot cocoa", "hot chocolate"], "ar": ["كاكاو ساخن", "شوكولاتة ساخنة"]}},
            {"id": "fireside_crackling_logs", "family": "woody",
             "title": _s("Crackling logs on a quiet night", "حطب يطقطق في ليلة هادئة"),
             "caption": _s("Smoky woods and soft resins", "أخشاب مدخّنة وراتنجات ناعمة"),
             "taste": {"liked_notes": ["smoke", "sandalwood", "resins"], "families": ["woody"], "moods": ["cozy"],
                       "strength": 4},
             "keywords": {"en": ["crackling logs", "log fire", "wood fire"], "ar": ["حطب"]}},
            {"id": "fireside_honey_spice", "family": "amber",
             "title": _s("Honey, cinnamon and a warm blanket", "عسل وقرفة وبطانية دافئة"),
             "caption": _s("Golden, spiced and snug", "ذهبي ومتبّل ودافئ"),
             "taste": {"liked_notes": ["honey", "cinnamon", "amber"], "families": ["amber"], "moods": ["cozy"],
                       "strength": 3},
             "keywords": {"en": ["warm blanket"], "ar": ["بطانية دافئة"]}},
        ],
    },
    {
        "id": "garden", "family": "floral", "motif": "petals",
        "title": _s("A spring garden in full bloom", "حديقة ربيعية في أوج تفتّحها"),
        "caption": _s("Fresh petals and dewy green leaves", "بتلات طازجة وأوراق خضراء ندية"),
        "short": _s("garden", "أجواء الحديقة"),
        "taste": {"families": ["floral", "green"], "liked_notes": ["peony", "green notes"], "moods": ["romantic"],
                  "seasons": ["spring"]},
        "keywords": {"en": ["garden", "gardens", "in bloom", "blooming", "flower field"],
                     "ar": ["حديقة", "حدائق", "ربيع مزهر"]},
        "moments": [
            {"id": "garden_morning_dew", "family": "green",
             "title": _s("Morning dew on the petals", "ندى الصباح على البتلات"),
             "caption": _s("Green, dewy and delicate", "أخضر وندي ورقيق"),
             "taste": {"liked_notes": ["green notes", "lily", "violet"], "families": ["green"], "moods": ["calm"],
                       "strength": 2},
             "keywords": {"en": ["morning dew"], "ar": ["ندى الصباح"]}},
            {"id": "garden_rose_armful", "family": "floral",
             "title": _s("An armful of fresh roses", "باقة كبيرة من الورد الطازج"),
             "caption": _s("Classic rose with a juicy glow", "ورد كلاسيكي بلمسة عصيرية"),
             "taste": {"liked_notes": ["rose", "peony", "berries"], "families": ["floral"], "moods": ["romantic"],
                       "strength": 3},
             "keywords": {"en": ["armful of roses", "bouquet of roses"], "ar": ["باقة ورد"]}},
            {"id": "garden_orange_blossom", "family": "fresh",
             "title": _s("Orange blossom in the sun", "زهر البرتقال تحت الشمس"),
             "caption": _s("Radiant white flowers with citrus", "زهور بيضاء مشرقة بلمسة حمضيات"),
             "taste": {"liked_notes": ["orange blossom", "jasmine", "bergamot"], "families": ["floral"],
                       "moods": ["energetic"], "strength": 3},
             "keywords": {"en": ["blossom in the sun"], "ar": ["زهر البرتقال تحت الشمس"]}},
        ],
    },
    {
        "id": "date", "family": "fruity", "motif": "candle",
        "title": _s("A candlelit first date", "موعد أول على ضوء الشموع"),
        "caption": _s("Close, warm and quietly unforgettable", "قريب ودافئ ولا يُنسى"),
        "short": _s("date night", "أجواء الموعد"),
        "taste": {"families": ["floral", "fruity"], "liked_notes": ["rose", "peach"], "moods": ["romantic"],
                  "occasions": ["date"]},
        "keywords": {"en": ["date night", "first date", "candlelit", "candlelight", "romantic dinner"],
                     "ar": ["موعد أول", "موعد غرامي", "ضوء الشموع", "عشاء رومانسي"]},
        "moments": [
            {"id": "date_slow_dance", "family": "gourmand",
             "title": _s("A slow dance, close and warm", "رقصة هادئة قريبة ودافئة"),
             "caption": _s("Creamy vanilla and soft musk", "فانيليا كريمية ومسك ناعم"),
             "taste": {"liked_notes": ["vanilla", "musk", "sandalwood"], "families": ["gourmand"],
                       "moods": ["romantic"], "strength": 3},
             "keywords": {"en": ["slow dance"], "ar": ["رقصة هادئة"]}},
            {"id": "date_terrace_dinner", "family": "fruity",
             "title": _s("Dinner on a moonlit terrace", "عشاء على شرفة تحت ضوء القمر"),
             "caption": _s("Juicy peach and fresh petals", "خوخ عصيري وبتلات طازجة"),
             "taste": {"liked_notes": ["peach", "rose", "pear"], "families": ["fruity"], "moods": ["playful"],
                       "strength": 3},
             "keywords": {"en": ["moonlit terrace", "moonlit dinner"], "ar": ["شرفة تحت ضوء القمر"]}},
            {"id": "date_whisper_mystery", "family": "woody",
             "title": _s("A whisper of mystery", "همسة من الغموض"),
             "caption": _s("Dark rose with a smoky edge", "ورد داكن بلمسة مدخّنة"),
             "taste": {"liked_notes": ["rose", "oud", "incense"], "families": ["amber"], "moods": ["mysterious"],
                       "strength": 4},
             "keywords": {"en": ["whisper of mystery"], "ar": ["همسة من الغموض"]}},
        ],
    },
    {
        "id": "linen", "family": "green", "motif": "linen",
        "title": _s("Fresh linen on a crisp morning", "ملاءات نظيفة في صباح منعش"),
        "caption": _s("Clean, bright and effortless", "نظيف ومشرق وبلا تكلّف"),
        "short": _s("fresh linen", "أجواء الصباح المنعش"),
        "taste": {"families": ["fresh"], "liked_notes": ["clean notes", "bergamot"], "moods": ["calm"],
                  "occasions": ["everyday"]},
        "keywords": {"en": ["fresh linen", "clean laundry", "clean sheets", "just showered",
                            "fresh out of the shower", "crisp morning"],
                     "ar": ["ملاءات نظيفة", "غسيل نظيف", "بعد الاستحمام", "رائحة النظافة"]},
        "moments": [
            {"id": "linen_white_curtains", "family": "aquatic",
             "title": _s("Sunlight through white curtains", "شمس تتسلل عبر ستائر بيضاء"),
             "caption": _s("Soft musk and airy cotton", "مسك ناعم وقطن خفيف"),
             "taste": {"liked_notes": ["clean notes", "musk", "aldehydes"], "families": ["fresh"], "moods": ["calm"],
                       "strength": 2},
             "keywords": {"en": ["white curtains"], "ar": ["ستائر بيضاء"]}},
            {"id": "linen_green_tea", "family": "green",
             "title": _s("Green tea on the balcony", "شاي أخضر على الشرفة"),
             "caption": _s("Leafy, calm and serene", "أوراق خضراء وهدوء وصفاء"),
             "taste": {"liked_notes": ["tea", "green notes"], "families": ["green"], "moods": ["calm"],
                       "strength": 2},
             "keywords": {"en": ["tea on the balcony"], "ar": ["شاي على الشرفة"]}},
            {"id": "linen_out_the_door", "family": "fresh",
             "title": _s("Out the door, full of energy", "أخرج من البيت بكامل طاقتي"),
             "caption": _s("Zesty citrus and cool mint", "حمضيات منعشة ونعناع بارد"),
             "taste": {"liked_notes": ["lemon", "grapefruit", "mint"], "families": ["fresh"], "moods": ["energetic"],
                       "strength": 2},
             "keywords": {"en": ["full of energy"], "ar": ["بكامل طاقتي"]}},
        ],
    },
    {
        "id": "boardroom", "family": "woody", "motif": "briefcase",
        "title": _s("Owning the boardroom", "أقود الاجتماع بثقة"),
        "caption": _s("Polished, sharp and quietly powerful", "أنيق وحاد وقوي بهدوء"),
        "short": _s("boardroom", "أجواء الاجتماع"),
        "taste": {"families": ["woody", "fresh"], "liked_notes": ["vetiver", "cedar"], "moods": ["elegant"],
                  "occasions": ["office"]},
        "keywords": {"en": ["boardroom", "board meeting", "big meeting", "presentation", "power suit",
                            "client meeting"],
                     "ar": ["اجتماع", "اجتماعات", "عرض تقديمي"]},
        "moments": [
            {"id": "boardroom_first_meeting", "family": "fresh",
             "title": _s("Crisp suit, first meeting", "بدلة أنيقة وأول اجتماع"),
             "caption": _s("Bright bergamot over clean woods", "برغموت مشرق فوق أخشاب نظيفة"),
             "taste": {"liked_notes": ["bergamot", "cedar", "herbs"], "families": ["fresh"], "moods": ["energetic"],
                       "strength": 3},
             "keywords": {"en": ["job interview", "first meeting"], "ar": ["مقابلة عمل"]}},
            {"id": "boardroom_big_decision", "family": "woody",
             "title": _s("Leather chair, big decision", "كرسي جلدي وقرار كبير"),
             "caption": _s("Leather, vetiver and quiet confidence", "جلد وفيتيفر وثقة هادئة"),
             "taste": {"liked_notes": ["leather", "vetiver", "pepper"], "families": ["woody"], "moods": ["bold"],
                       "strength": 4},
             "keywords": {"en": ["big decision"], "ar": ["قرار كبير"]}},
            {"id": "boardroom_quiet_luxury", "family": "floral",
             "title": _s("Quiet luxury, all day long", "فخامة هادئة طوال اليوم"),
             "caption": _s("Powdery iris and soft woods", "سوسن بودري وأخشاب ناعمة"),
             "taste": {"liked_notes": ["iris", "sandalwood", "musk"], "families": ["floral"], "moods": ["elegant"],
                       "strength": 3},
             "keywords": {"en": ["quiet luxury"], "ar": ["فخامة هادئة"]}},
        ],
    },
    {
        "id": "souk", "family": "amber", "motif": "spice",
        "title": _s("Wandering a spice souk at dusk", "أتجوّل في سوق التوابل عند المغيب"),
        "caption": _s("Saffron, warm spice and glowing lanterns", "زعفران وتوابل دافئة وفوانيس مضيئة"),
        "short": _s("souk", "أجواء السوق"),
        "taste": {"families": ["amber"], "liked_notes": ["saffron", "cardamom"], "moods": ["mysterious"],
                  "seasons": ["autumn"]},
        "keywords": {"en": ["souk", "souq", "bazaar", "spice market", "old market"],
                     "ar": ["سوق", "أسواق", "بازار"]},
        "moments": [
            {"id": "souk_saffron_rose", "family": "floral",
             "title": _s("Saffron and rose from the stalls", "زعفران وورد من الأكشاك"),
             "caption": _s("Rich, rosy and regal", "غني ووردي وملكي"),
             "taste": {"liked_notes": ["saffron", "rose", "oud"], "families": ["amber"], "moods": ["elegant"],
                       "strength": 4},
             "keywords": {"en": ["saffron and rose"], "ar": ["زعفران وورد"]}},
            {"id": "souk_incense_lanes", "family": "amber",
             "title": _s("Incense drifting through the lanes", "بخور يتهادى بين الأزقة"),
             "caption": _s("Smoky, resinous and deep", "مدخّن وراتنجي وعميق"),
             "taste": {"liked_notes": ["incense", "myrrh", "resins"], "families": ["amber"], "moods": ["mysterious"],
                       "strength": 4},
             "keywords": {"en": ["incense drifting"], "ar": ["بخور يتهادى"]}},
            {"id": "souk_dates_coffee", "family": "gourmand",
             "title": _s("Dates, coffee and cardamom", "تمر وقهوة وهيل"),
             "caption": _s("Warm, sweet and welcoming", "دافئ وحلو ومرحِّب"),
             "taste": {"liked_notes": ["dried fruits", "coffee", "cardamom"], "families": ["gourmand"],
                       "moods": ["cozy"], "strength": 3},
             "keywords": {"en": ["dates and coffee", "arabic coffee"], "ar": ["تمر وقهوة", "قهوة عربية"]}},
        ],
    },
    {
        "id": "citrus_grove", "family": "fresh", "motif": "citrus",
        "title": _s("A citrus grove on the Riviera", "بستان حمضيات على المتوسط"),
        "caption": _s("Sunny zest, green leaves, sea breeze", "قشر حمضيات مشمس وأوراق خضراء ونسيم البحر"),
        "short": _s("citrus grove", "أجواء البستان"),
        "taste": {"families": ["fresh"], "liked_notes": ["lemon", "bergamot"], "moods": ["energetic"],
                  "seasons": ["summer"]},
        "keywords": {"en": ["citrus grove", "lemon grove", "orange grove", "mediterranean", "amalfi", "riviera",
                            "orchard"],
                     "ar": ["بستان حمضيات", "بستان ليمون", "المتوسط"]},
        "moments": [
            {"id": "citrus_lemon_trees", "family": "fresh",
             "title": _s("Lemon trees at high noon", "أشجار الليمون وقت الظهيرة"),
             "caption": _s("Zesty, sparkling and bright", "حمضي وفوّار ومشرق"),
             "taste": {"liked_notes": ["lemon", "citrus", "ginger"], "families": ["fresh"], "moods": ["energetic"],
                       "strength": 2},
             "keywords": {"en": ["lemon trees"], "ar": ["أشجار الليمون"]}},
            {"id": "citrus_fig_shade", "family": "green",
             "title": _s("Lunch in the shade of a fig tree", "غداء في ظل شجرة تين"),
             "caption": _s("Green fig, leaves and a creamy hint", "تين أخضر وأوراق ولمسة كريمية"),
             "taste": {"liked_notes": ["fig", "green notes"], "families": ["green"], "moods": ["calm"],
                       "strength": 2},
             "keywords": {"en": ["fig tree"], "ar": ["شجرة تين"]}},
            {"id": "citrus_neroli_terrace", "family": "floral",
             "title": _s("Neroli on a sunny terrace", "نيرولي على شرفة مشمسة"),
             "caption": _s("White flowers with a citrus glow", "زهور بيضاء بلمعة حمضيات"),
             "taste": {"liked_notes": ["orange blossom", "bergamot", "musk"], "families": ["floral"],
                       "moods": ["elegant"], "strength": 3},
             "keywords": {"en": ["sunny terrace"], "ar": ["شرفة مشمسة"]}},
        ],
    },
    {
        "id": "desert_night", "family": "gourmand", "motif": "moon_stars",
        "title": _s("A desert night under the stars", "ليلة في الصحراء تحت النجوم"),
        "caption": _s("Cool sand, oud smoke, endless sky", "رمال باردة ودخان العود وسماء بلا نهاية"),
        "short": _s("desert night", "أجواء ليل الصحراء"),
        "taste": {"families": ["woody", "amber"], "liked_notes": ["oud", "amber"], "moods": ["mysterious"],
                  "occasions": ["evening"]},
        "keywords": {"en": ["desert", "dunes", "under the stars", "starry night", "camping"],
                     "ar": ["صحراء", "كثبان", "تحت النجوم", "مخيم"]},
        "moments": [
            {"id": "desert_campfire", "family": "woody",
             "title": _s("Oud by the campfire", "عود قرب نار المخيم"),
             "caption": _s("Smoky, rich and timeless", "مدخّن وغني وخالد"),
             "taste": {"liked_notes": ["oud", "smoke", "leather"], "families": ["woody"], "moods": ["bold"],
                       "strength": 4},
             "keywords": {"en": ["campfire"], "ar": ["نار المخيم"]}},
            {"id": "desert_cool_sand", "family": "amber",
             "title": _s("Cool sand after sunset", "رمال باردة بعد الغروب"),
             "caption": _s("Dry woods and soft amber", "أخشاب جافة وعنبر ناعم"),
             "taste": {"liked_notes": ["amber", "sandalwood", "mineral notes"], "families": ["amber"],
                       "moods": ["calm"], "strength": 3},
             "keywords": {"en": ["cool sand"], "ar": ["رمال باردة"]}},
            {"id": "desert_moonlight_musk", "family": "gourmand",
             "title": _s("Moonlight and white musk", "ضوء القمر ومسك أبيض"),
             "caption": _s("Clean musk with a silky glow", "مسك نظيف بلمعة حريرية"),
             "taste": {"liked_notes": ["musk", "white flowers", "powdery notes"], "families": ["amber"],
                       "moods": ["calm"], "strength": 3},
             "keywords": {"en": ["moonlight"], "ar": ["ضوء القمر"]}},
        ],
    },
]


# ----------------------------------------------------------------------------------------------------------------
# Lookups
# ----------------------------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _index() -> tuple[dict[str, dict], dict[str, dict], dict[str, str]]:
    """(scenario by id, moment by id, moment id -> its scenario id)."""
    scen = {s["id"]: s for s in SCENARIOS}
    moments: dict[str, dict] = {}
    parent: dict[str, str] = {}
    for s in SCENARIOS:
        for m in s["moments"]:
            moments[m["id"]] = m
            parent[m["id"]] = s["id"]
    return scen, moments, parent


def scenario(sid: str) -> dict | None:
    return _index()[0].get(sid)


def moment(mid: str) -> dict | None:
    return _index()[1].get(mid)


def parent_of(mid: str) -> str | None:
    return _index()[2].get(mid)


def item(any_id: str) -> dict | None:
    """A scenario or a moment, by id."""
    return scenario(any_id) or moment(any_id)


def _lang(lang: str) -> str:
    return "ar" if lang == "ar" else "en"


def title(any_id: str, lang: str) -> str:
    it = item(any_id)
    return it["title"][_lang(lang)] if it else any_id


def short(sid: str, lang: str) -> str:
    s = scenario(sid)
    return s["short"][_lang(lang)] if s else sid


def option(any_id: str, lang: str) -> dict:
    """The option fields for one card: id, label (the title), caption, motif, family. A moment draws its parent
    scenario's motif in its own family colour."""
    it = item(any_id)
    lg = _lang(lang)
    motif = it.get("motif") or scenario(parent_of(any_id) or "")["motif"]
    return {"id": any_id, "label": it["title"][lg], "caption": it["caption"][lg], "motif": motif,
            "family": it["family"]}


def scenario_options(lang: str) -> list[dict]:
    return [option(s["id"], lang) for s in SCENARIOS]


def moment_options(scenario_ids: list[str], lang: str) -> list[dict]:
    """The follow-up moments for the FIRST chosen scenario, plus one moment from the second when there is one."""
    chosen = [s for s in scenario_ids if scenario(s)]
    if not chosen:
        return []
    ids = [m["id"] for m in scenario(chosen[0])["moments"]]
    if len(chosen) > 1:
        ids.append(scenario(chosen[1])["moments"][0]["id"])
    return [option(mid, lang) for mid in ids]


# ----------------------------------------------------------------------------------------------------------------
# Taste mapping
# ----------------------------------------------------------------------------------------------------------------
def profile_for(scenario_ids: list[str] = (), moment_ids: list[str] = (), with_strength: bool = True) -> TasteProfile:
    """The deterministic taste reading of chosen scenarios and moments. A moment brings its parent scenario along
    (so a moment typed in free chat still records where it came from) and, in guided match, a strength level;
    free chat leaves strength to the shopper's own words, since strength is a hard filter."""
    scen_ids = [s for s in dict.fromkeys(scenario_ids) if scenario(s)][:MAX_SCENARIOS]
    mom_ids = [m for m in dict.fromkeys(moment_ids) if moment(m)]
    for m in mom_ids:
        p = parent_of(m)
        if p and p not in scen_ids:
            scen_ids.append(p)
    data: dict[str, list] = {k: [] for k in _TASTE_LISTS}
    strength = None
    for spec in [scenario(s)["taste"] for s in scen_ids] + [moment(m)["taste"] for m in mom_ids]:
        for key in _TASTE_LISTS:
            for v in spec.get(key, []):
                if v not in data[key]:
                    data[key].append(v)
        if with_strength and spec.get("strength") is not None:
            strength = spec["strength"]
    return TasteProfile(scenarios=scen_ids, moments=mom_ids, strength=strength, **data)


def feel_titles(prof: TasteProfile, lang: str, limit: int = 3) -> list[str]:
    """What the shopper wants to feel, in their language: a chosen moment stands in for its own scenario."""
    out: list[str] = []
    covered = {parent_of(m) for m in prof.moments}
    for m in prof.moments:
        if moment(m):
            out.append(title(m, lang))
    for s in prof.scenarios:
        if scenario(s) and s not in covered:
            out.append(title(s, lang))
    return out[:limit]


# ----------------------------------------------------------------------------------------------------------------
# Reading answers and free text
# ----------------------------------------------------------------------------------------------------------------
_NORM_RE = re.compile(r"[\W_]+", re.UNICODE)                 # punctuation (Latin and Arabic) and underscores
_AR_MARKS_RE = re.compile(r"[ـً-ٰٟ]")    # tatweel and short-vowel marks
_AR_PREFIX = r"(?:وال|بال|فال|لل|ال|و|ب|ل|ف)?"


def _norm(text: str) -> str:
    """Lower case, Arabic marks dropped, every run of punctuation one space, padded so `in` matches whole words."""
    return " " + " ".join(_NORM_RE.sub(" ", _AR_MARKS_RE.sub("", (text or "").lower())).split()) + " "


def match_options(text: str, option_ids: list[str]) -> list[str]:
    """The pending question's options named in `text`, in the order they appear: an exact option id first, then
    the title in either language (case- and punctuation-insensitive, so a multi-select answer joined with commas
    and a title that itself holds a comma both read correctly)."""
    raw = (text or "").strip().lower()
    if raw in option_ids:
        return [raw]
    hay = _norm(text)
    found: list[tuple[int, str]] = []
    for oid in option_ids:
        it = item(oid)
        needles = [oid.replace("_", " ")] + ([it["title"]["en"], it["title"]["ar"]] if it else [])
        best = None
        for needle in needles:
            n = _norm(needle)
            if n.strip() and n in hay:
                pos = hay.index(n)
                best = pos if best is None else min(best, pos)
        if best is not None:
            found.append((best, oid))
    return [oid for _, oid in sorted(found)]


def _keyword_hits(text: str, keywords: dict) -> int | None:
    """Earliest position of any keyword (either language) in `text`, skipping negated mentions ("not the
    beach"), or None."""
    from app.agent.extract import _negated  # local import: extract imports this module

    low = (text or "").lower()
    best = None
    for kw in keywords.get("en", []):
        for m in re.finditer(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", low):
            if not _negated(text, m.start()):
                best = m.start() if best is None else min(best, m.start())
    for kw in keywords.get("ar", []):
        for m in re.finditer(rf"(?<![\w]){_AR_PREFIX}{re.escape(kw)}(?![\w])", text or ""):
            if not _negated(text, m.start()):
                best = m.start() if best is None else min(best, m.start())
    return best


def match_text(text: str) -> tuple[list[str], list[str]]:
    """Scenario-like free text ("I want to smell like a beach holiday", "لحفلة فخمة") -> (scenario ids, moment
    ids), in the order they are mentioned. A moment implies its scenario."""
    if not text or not text.strip():
        return [], []
    scen: list[tuple[int, str]] = []
    moms: list[tuple[int, str]] = []
    for s in SCENARIOS:
        pos = _keyword_hits(text, s["keywords"])
        for m in s["moments"]:
            mpos = _keyword_hits(text, m.get("keywords") or {})
            if mpos is not None:
                moms.append((mpos, m["id"]))
                pos = mpos if pos is None else min(pos, mpos)
        if pos is not None:
            scen.append((pos, s["id"]))
    return [s for _, s in sorted(scen)][:MAX_SCENARIOS], [m for _, m in sorted(moms)][:1]


def profile_from_text(text: str) -> TasteProfile:
    """Free chat: the scenario reading of a message, strength left out (see profile_for)."""
    scen, moms = match_text(text)
    if not scen and not moms:
        return TasteProfile()
    return profile_for(scen, moms, with_strength=False)


def interpret_answer(text: str, pending: dict, topic: str) -> TasteProfile:
    """Reads a guided answer to the scenario question (up to 3 scenarios) or the moment question (one moment).
    Options are matched deterministically first; typed words ("Something else") go through the keyword matcher
    and the ordinary free-text extraction, and never set a strength on their own."""
    from app.agent.extract import extract_profile

    option_ids = [o.get("id") for o in (pending or {}).get("options") or [] if o.get("id")]
    hits = match_options(text, option_ids)
    if topic == "scenario":
        chosen = [h for h in hits if scenario(h)][:MAX_SCENARIOS]
        if chosen:
            return profile_for(chosen, []).model_copy(update={"free_text": text})
    else:
        chosen = [h for h in hits if moment(h)][:1]
        if chosen:
            return profile_for([], chosen).model_copy(update={"free_text": text})
    scen, moms = match_text(text)
    if topic == "scenario_moment":
        scen = []  # a typed moment adds its own notes; it does not re-open the scenario list
    prof = extract_profile(text)
    if scen or moms:
        prof = prof.merge(profile_for(scen, moms, with_strength=False))
    return prof
