/*
 * Perfume selection agent: embeddable chat widget.
 * Vanilla JS, one file, no build step, no external fonts or CDNs. Everything renders inside a Shadow DOM.
 *
 * Embed:  <script src="/widget.js" data-lang="en" data-brand=""></script>
 *   data-lang   "en" | "ar"          initial language (the in-widget toggle overrides it until the page's data-lang changes)
 *   data-brand  optional brand name  sent to POST /api/session as "brand"
 *   data-api    optional API origin  defaults to the origin that served widget.js
 *   data-mode   "page"               opt-in full-page mode: mounts inline (not fixed), always open, no launcher/close button
 *   data-mount  CSS selector         required with data-mode="page"; the element the widget mounts inside
 *
 * Server strings are only ever inserted with textContent. innerHTML is used for the static SVG icons below.
 */
(function () {
  'use strict';
  if (window.PerfumeWidget) return;

  // ---------------------------------------------------------------- config
  var SCRIPT = document.currentScript || (function () {
    var list = document.querySelectorAll('script[src]');
    for (var i = list.length - 1; i >= 0; i--) if (/widget\.js(?:[?#]|$)/.test(list[i].src)) return list[i];
    return null;
  })();
  function attr(name) { return SCRIPT ? (SCRIPT.getAttribute(name) || '').trim() : ''; }
  function normLang(v) { v = String(v || '').toLowerCase(); return v.indexOf('ar') === 0 ? 'ar' : v.indexOf('en') === 0 ? 'en' : ''; }

  var ATTR_LANG = normLang(attr('data-lang'));
  var BRAND = attr('data-brand');
  var MODE = attr('data-mode') === 'page' ? 'page' : 'floating';
  var MOUNT_SEL = attr('data-mount');
  var API = attr('data-api');
  if (!API) {
    try { API = new URL(SCRIPT && SCRIPT.src ? SCRIPT.src : location.href, location.href).origin; } catch (e) { API = ''; }
  }
  API = API.replace(/\/+$/, '');

  var store = {
    get: function (k) { try { return window.localStorage.getItem('psa_' + k); } catch (e) { return null; } },
    set: function (k, v) {
      try {
        if (v == null) window.localStorage.removeItem('psa_' + k);
        else window.localStorage.setItem('psa_' + k, String(v));
      } catch (e) { /* storage blocked: run without persistence */ }
    }
  };

  function initialLang() {
    var stored = normLang(store.get('lang'));
    if (ATTR_LANG) return stored && store.get('lang_attr') === ATTR_LANG ? stored : ATTR_LANG;
    return stored || normLang(document.documentElement.lang) || 'en';
  }

  // ---------------------------------------------------------------- strings
  var I18N = {
    en: {
      launcher: 'Find your scent',
      title: 'Find your scent',
      subtitle: 'Your perfume guide',
      brandSubtitle: 'Picks from {brand}',
      openLabel: 'Open the perfume finder',
      close: 'Close',
      langToggle: 'العربية',
      langToggleLabel: 'التبديل إلى العربية',
      startOver: 'Start over',
      tabChat: 'Assistant',
      tabWishlist: 'Wishlist ({n})',
      greeting: "Hi! Tell me a mood, a note you love, or a perfume you already wear, and I'll bring you three picks plus a layering idea.",
      heroTitle: 'Find a scent that feels like you',
      // the headline split so the closing phrase can carry the brand gradient
      heroTitleLead: 'Find a scent that ',
      heroTitleEm: 'feels like you',
      heroSub: 'Describe a mood, an occasion, or a perfume you already love, and get three tailored picks with a layering idea in under a minute.',
      tryAsking: 'Or try asking',
      starter1: 'A fresh scent for the office under AED 300',
      starter2: 'Something like Dior Sauvage',
      starter3: 'A warm oud for evenings',
      starter4: 'A gift for my mother',
      // phone labels: the chip reads short in the scroll row, the full prompt above is what gets sent
      starter1Short: 'Fresh for the office',
      starter2Short: 'Like Dior Sauvage',
      starter3Short: 'Warm oud for evenings',
      starter4Short: 'A gift for my mother',
      startQuiz: 'Let the advisor guide you',
      startQuizSub: 'A few quick questions, tailored to your answers.',
      startChat: 'Tell me what you want',
      startChatSub: 'Describe a mood, a note, or a perfume you love.',
      chatPrompt: "Tell me what you're looking for: a mood, an occasion, notes you love, or a perfume you already wear.",
      placeholder: 'Tell me a mood, a note, or a perfume you love…',
      placeholderShort: 'A mood, a note, a perfume…',
      send: 'Send',
      quizProgress: 'Question {i} of up to {n}',
      next: 'Next',
      seePicks: 'See my picks',
      noPreference: 'No preference',
      typing: 'Searching the atelier for your matches…',
      guidedThinking: 'Thinking about your next question…',
      guidedContinue: 'Continue',
      guidedSkip: 'Skip',
      guidedShowPicks: 'Show my picks now',
      guidedWhatLearned: 'What I learned',
      scenarioContinue: 'Continue with {n}',
      somethingElse: 'Something else',
      somethingElseSub: 'Describe your moment in your own words',
      placeholderMoment: 'Describe your moment…',
      resultsTitle: 'Your top picks',
      match: 'match',
      matchFmt: '{n}% match',
      estTooltip: 'Estimated price for the prototype',
      noPrice: 'Price not available',
      viewProduct: 'View product',
      viewShort: 'View',
      layerWith: 'Layer it with',
      layerOn: 'On top of {name}',
      details: 'Details',
      lessDetails: 'Less',
      notesTop: 'Top',
      notesHeart: 'Heart',
      notesBase: 'Base',
      thumbsUp: 'I like this',
      thumbsDown: 'Not for me',
      save: 'Save to wishlist',
      saved: 'Saved to wishlist',
      consent: 'Save picks to a wishlist for this session?',
      yes: 'Yes',
      no: 'No',
      wishlistTitle: 'Saved for this session',
      wishlistEmpty: 'Nothing saved yet. Tap the heart on a pick to keep it here for this session.',
      refineTitle: 'Refine',
      refine: { less_sweet: 'Less sweet', fresher: 'Fresher', cheaper: 'Cheaper', stronger: 'Stronger', lighter: 'Lighter', more_like: 'More like pick {n}' },
      error: 'Sorry, something went wrong on our side. Please try again.',
      errorNetwork: "We couldn't reach the server. Check your connection and try again.",
      errorBusy: 'Lots of people are searching right now. Please try again in a moment.',
      tryAgain: 'Try again',
      fallbackNote: 'AI is resting; showing rule-based picks'
    },
    ar: {
      launcher: 'اعثر على عطرك',
      title: 'اعثر على عطرك',
      subtitle: 'دليلك إلى العطور',
      brandSubtitle: 'اختيارات من {brand}',
      openLabel: 'افتح مساعد اختيار العطور',
      close: 'إغلاق',
      langToggle: 'English',
      langToggleLabel: 'Switch to English',
      startOver: 'البدء من جديد',
      tabChat: 'المساعد',
      tabWishlist: 'المفضلة ({n})',
      greeting: 'مرحباً! أخبرني بمزاج تحبه، أو نفحة تفضّلها، أو عطر تستخدمه حالياً، وسأقترح عليك ثلاثة اختيارات مع فكرة للمزج.',
      heroTitle: 'اعثر على عطر يشبهك',
      heroTitleLead: 'اعثر على عطر ',
      heroTitleEm: 'يشبهك',
      heroSub: 'صف مزاجاً أو مناسبة أو عطراً تحبه بالفعل، واحصل على ثلاثة اختيارات مناسبة لك مع فكرة للمزج في أقل من دقيقة.',
      tryAsking: 'أو جرّب أن تسأل',
      starter1: 'عطر منعش للمكتب بأقل من 300 درهم',
      starter2: 'شيء يشبه Dior Sauvage',
      starter3: 'عود دافئ للسهرات',
      starter4: 'هدية لأمي',
      starter1Short: 'منعش للمكتب',
      starter2Short: 'يشبه Dior Sauvage',
      starter3Short: 'عود دافئ للسهرات',
      starter4Short: 'هدية لأمي',
      startQuiz: 'دع المستشار يرشدك',
      startQuizSub: 'بضعة أسئلة سريعة، تتكيّف مع إجاباتك.',
      startChat: 'أخبرني بما تريد',
      startChatSub: 'صف مزاجاً أو نفحة أو عطراً تحبه.',
      chatPrompt: 'أخبرني بما تبحث عنه: مزاج، أو مناسبة، أو نفحات تحبها، أو عطر تستخدمه حالياً.',
      placeholder: 'أخبرني بمزاج أو نفحة أو عطر تحبه…',
      placeholderShort: 'مزاج أو نفحة أو عطر…',
      send: 'إرسال',
      quizProgress: 'السؤال {i} من {n} كحد أقصى',
      next: 'التالي',
      seePicks: 'اعرض اختياراتي',
      noPreference: 'لا تفضيل',
      typing: 'نبحث في المتجر عن أقرب العطور لذوقك…',
      guidedThinking: 'أفكر في سؤالك التالي…',
      guidedContinue: 'متابعة',
      guidedSkip: 'تخطي',
      guidedShowPicks: 'اعرض اختياراتي الآن',
      guidedWhatLearned: 'ما تعلمته عنك',
      scenarioContinue: 'متابعة ({n})',
      somethingElse: 'لحظة أخرى',
      somethingElseSub: 'صف لحظتك بكلماتك',
      placeholderMoment: 'صف لحظتك…',
      resultsTitle: 'أفضل اختياراتك',
      match: 'تطابق',
      matchFmt: 'تطابق {n}%',
      estTooltip: 'سعر تقديري للنموذج الأولي',
      noPrice: 'السعر غير متوفر',
      viewProduct: 'عرض المنتج',
      viewShort: 'عرض',
      layerWith: 'امزجه مع',
      layerOn: 'فوق {name}',
      details: 'التفاصيل',
      lessDetails: 'أقل',
      notesTop: 'الافتتاحية',
      notesHeart: 'القلب',
      notesBase: 'القاعدة',
      thumbsUp: 'أعجبني',
      thumbsDown: 'لا يناسبني',
      save: 'أضف إلى المفضلة',
      saved: 'محفوظ في المفضلة',
      consent: 'هل تريد حفظ الاختيارات في قائمة مفضلة لهذه الجلسة؟',
      yes: 'نعم',
      no: 'لا',
      wishlistTitle: 'محفوظ لهذه الجلسة',
      wishlistEmpty: 'لا يوجد شيء محفوظ بعد. اضغط على القلب في أي اختيار لحفظه هنا لهذه الجلسة.',
      refineTitle: 'عدّل النتائج',
      refine: { less_sweet: 'أقل حلاوة', fresher: 'أكثر انتعاشاً', cheaper: 'أرخص', stronger: 'أقوى', lighter: 'أخف', more_like: 'أقرب إلى الاختيار {n}' },
      error: 'عذراً، حدث خطأ من جهتنا. يرجى المحاولة مرة أخرى.',
      errorNetwork: 'تعذّر الاتصال بالخادم. تحقّق من اتصالك وحاول مرة أخرى.',
      errorBusy: 'هناك طلبات كثيرة الآن. يرجى المحاولة بعد لحظات.',
      tryAgain: 'حاول مرة أخرى',
      fallbackNote: 'الذكاء الاصطناعي في استراحة؛ نعرض اختيارات مبنية على القواعد'
    }
  };

  function t(key, vars) {
    var s = (I18N[S.lang] && I18N[S.lang][key]);
    if (s == null) s = I18N.en[key];
    if (s == null) return key;
    if (vars) s = s.replace(/\{(\w+)\}/g, function (m, k) { return vars[k] != null ? vars[k] : m; });
    return s;
  }

  // ---------------------------------------------------------------- icons (static markup only)
  var ICONS = {
    bottle: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 2h4v3h-4zM9 5h6v2.2c2.4.8 4 3 4 5.6V19a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3v-6.2c0-2.6 1.6-4.8 4-5.6z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M8 14h8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    send: '<svg viewBox="0 0 24 24" aria-hidden="true" class="flip"><path d="M4 12h14M12 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    restart: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4.5h4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    heart: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" fill="var(--heart-fill, none)" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
    up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 11v9H4v-9zM7 11l4-8a2.5 2.5 0 0 1 2.5 2.5V9h5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.3 20H7" fill="var(--thumb-fill, none)" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 13V4h3v9zM17 13l-4 8a2.5 2.5 0 0 1-2.5-2.5V15h-5a2 2 0 0 1-2-2.3l1.2-7A2 2 0 0 1 6.7 4H17" fill="var(--thumb-fill, none)" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    external: '<svg viewBox="0 0 24 24" aria-hidden="true" class="flip"><path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    quiz: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="4" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 9.5l1.5 1.5L12 8.5M8 15h8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    chat: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-8l-4 3.5V16H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    info: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12 11v5M12 8h.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    layers: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l8 4-8 4-8-4zM4 12l8 4 8-4M4 16l8 4 8-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12.5l4 4 8-9" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    pencil: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19h4L19.5 8.5a2.1 2.1 0 0 0-3-3L6 16z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M14.5 7.5l2 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>'
  };

  // Scenario motifs for guided match's moment cards: small abstract drawings in the card's family colour
  // (--fam fills, --fam-i lines). Static markup only; the server names a motif by key and nothing else, and an
  // unknown key simply leaves the tile as a plain colour swatch.
  var MOTIFS = (function () {
    var F = 'var(--fam)', I = 'var(--fam-i)';
    function svg(body) { return '<svg viewBox="0 0 48 48" aria-hidden="true" focusable="false">' + body + '</svg>'; }
    function ring(n, shape) {
      var out = '';
      for (var k = 0; k < n; k++) out += shape.replace('{r}', 'rotate(' + (k * 360 / n) + ' 24 24)');
      return out;
    }
    function star(cx, cy, r, fill, op) {
      var a = r * 0.28;
      return '<path d="M' + cx + ' ' + (cy - r) + 'C' + (cx + a) + ' ' + (cy - a) + ' ' + (cx + a) + ' ' + (cy - a) + ' ' + (cx + r) + ' ' + cy +
        'C' + (cx + a) + ' ' + (cy + a) + ' ' + (cx + a) + ' ' + (cy + a) + ' ' + cx + ' ' + (cy + r) +
        'C' + (cx - a) + ' ' + (cy + a) + ' ' + (cx - a) + ' ' + (cy + a) + ' ' + (cx - r) + ' ' + cy +
        'C' + (cx - a) + ' ' + (cy - a) + ' ' + (cx - a) + ' ' + (cy - a) + ' ' + cx + ' ' + (cy - r) + 'z" fill="' + fill + '" opacity="' + (op || 1) + '"/>';
    }
    var wave = function (y) {
      return '<path d="M6 ' + y + 'c3 0 3-2.6 6-2.6s3 2.6 6 2.6 3-2.6 6-2.6 3 2.6 6 2.6 3-2.6 6-2.6 3 2.6 6 2.6" fill="none" stroke="' + I + '" stroke-width="2.4" stroke-linecap="round"/>';
    };
    return {
      sun_waves: svg('<path d="M14 29a10 10 0 0 1 20 0z" fill="' + F + '"/>' +
        '<path d="M24 11v3M12.5 16.5l2 2M35.5 16.5l-2 2M8 26h3M37 26h3" stroke="' + F + '" stroke-width="2.4" stroke-linecap="round"/>' +
        wave(35) + '<g opacity=".55">' + wave(41) + '</g>'),
      sparkle: svg(star(21, 20, 13, F) + star(35, 34, 6.5, I, 0.8) + '<circle cx="11" cy="36" r="2.2" fill="' + I + '" opacity=".55"/>' +
        '<circle cx="38" cy="11" r="1.8" fill="' + F + '" opacity=".7"/>'),
      flame: svg('<path d="M24 5c2.2 7.2 11.5 11 11.5 21.5a11.5 11.5 0 0 1-23 0c0-5.2 2.7-8.3 5.2-10.8.4 3.5 2 5.6 4.3 6.6C21 15.8 22 10.4 24 5z" fill="' + F + '"/>' +
        '<path d="M24 25.5c1.3 3.1 5.2 4.6 5.2 8.5a5.2 5.2 0 0 1-10.4 0c0-2.7 1.7-4.1 3.1-5.2.2 1.5.9 2.3 1.7 2.7-.1-2.5.1-4.1.4-6z" fill="#fff" opacity=".6"/>'),
      petals: svg('<g fill="' + F + '" opacity=".88">' + ring(5, '<ellipse cx="24" cy="13.5" rx="6.4" ry="9.5" transform="{r}"/>') + '</g>' +
        '<circle cx="24" cy="24" r="5" fill="' + I + '"/><circle cx="22.4" cy="22.4" r="1.6" fill="#fff" opacity=".6"/>'),
      candle: svg('<circle cx="24" cy="15" r="11" fill="' + F + '" opacity=".2"/>' +
        '<path d="M24 5.5c2.8 3.8 4.3 6.4 4.3 9a4.3 4.3 0 0 1-8.6 0c0-2.6 1.5-5.2 4.3-9z" fill="' + F + '"/>' +
        '<path d="M24 19v4" stroke="' + I + '" stroke-width="2" stroke-linecap="round"/>' +
        '<rect x="17" y="23" width="14" height="20" rx="3.5" fill="' + I + '"/><path d="M20 27v10" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".45"/>'),
      linen: svg('<path d="M5 11h38" stroke="' + I + '" stroke-width="2.4" stroke-linecap="round"/>' +
        '<path d="M11 11h26v22c-2.2 0-3.2 2.6-6.5 2.6S26.2 33 24 33s-3.2 2.6-6.5 2.6S13.2 33 11 33z" fill="' + F + '"/>' +
        '<path d="M19 14v15M29 14v15" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".5"/>' +
        '<rect x="15" y="8" width="3.5" height="7" rx="1.2" fill="' + I + '"/><rect x="29.5" y="8" width="3.5" height="7" rx="1.2" fill="' + I + '"/>'),
      briefcase: svg('<path d="M18 16v-3.2A3.2 3.2 0 0 1 21.2 9.6h5.6a3.2 3.2 0 0 1 3.2 3.2V16" fill="none" stroke="' + I + '" stroke-width="2.6"/>' +
        '<rect x="7" y="16" width="34" height="23" rx="5" fill="' + F + '"/><path d="M7 26h34" stroke="#fff" stroke-width="2" opacity=".45"/>' +
        '<rect x="20.5" y="23" width="7" height="6" rx="1.8" fill="' + I + '"/>'),
      spice: svg('<g fill="' + F + '">' + ring(8, '<ellipse cx="24" cy="12.5" rx="3.6" ry="8.2" transform="{r}"/>') + '</g>' +
        '<g fill="' + I + '" opacity=".75">' + ring(8, '<circle cx="24" cy="15" r="1.5" transform="{r}"/>') + '</g>' +
        '<circle cx="24" cy="24" r="3.4" fill="' + I + '"/>'),
      citrus: svg('<circle cx="24" cy="24" r="17" fill="' + F + '"/><circle cx="24" cy="24" r="13.4" fill="#fff" opacity=".62"/>' +
        '<g fill="' + F + '" opacity=".78">' + ring(8, '<path d="M24 24L24.9 12.3A11.8 11.8 0 0 1 31.7 15.2z" transform="{r}"/>') + '</g>' +
        '<circle cx="24" cy="24" r="1.8" fill="#fff"/>'),
      moon_stars: svg('<path d="M27 8.5a15.5 15.5 0 1 0 13 23.2A12.6 12.6 0 0 1 27 8.5z" fill="' + F + '"/>' +
        star(38.5, 12, 5, I, 0.85) + star(10, 12, 3.4, I, 0.6) + '<circle cx="40" cy="24" r="1.6" fill="' + I + '" opacity=".6"/>')
    };
  })();

  // The signature motif: eight abstract bottles walking the spectrum, one per scent family. Purely decorative,
  // built here from static markup (no server strings ever reach innerHTML).
  ICONS.spectrum = (function () {
    var order = ['aquatic', 'green', 'fresh', 'amber', 'woody', 'fruity', 'floral', 'gourmand'];
    var heights = [74, 58, 86, 64, 92, 62, 78, 56];
    var parts = '';
    for (var i = 0; i < order.length; i++) {
      var cx = 46 + i * 88, h = heights[i], top = 118 - h, f = 'var(--f-' + order[i] + ')';
      parts += '<ellipse cx="' + cx + '" cy="122" rx="32" ry="6" fill="' + f + '" opacity=".22"/>' +
        '<rect x="' + (cx - 9) + '" y="' + (top - 16) + '" width="18" height="20" rx="6" fill="' + f + '" opacity=".55"/>' +
        '<rect x="' + (cx - 26) + '" y="' + top + '" width="52" height="' + h + '" rx="17" fill="' + f + '" opacity=".92"/>' +
        '<rect x="' + (cx - 26) + '" y="' + top + '" width="52" height="' + h + '" rx="17" fill="url(#psa-gloss)"/>';
    }
    return '<svg viewBox="0 0 736 132" aria-hidden="true" focusable="false">' +
      '<defs><linearGradient id="psa-gloss" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="#fff" stop-opacity=".48"/><stop offset=".6" stop-color="#fff" stop-opacity="0"/>' +
      '</linearGradient></defs>' + parts + '</svg>';
  })();

  // ---------------------------------------------------------------- the scent spectrum
  // Perfume is invisible, so colour makes it visible: every scent family owns a hue. The eight names below are
  // the only keys the CSS knows ([data-fam=...] blocks set --fam / --fam-t / --fam-i / --fam-s / --fam-b).
  var FAMILIES = ['fresh', 'green', 'aquatic', 'floral', 'fruity', 'gourmand', 'woody', 'amber'];

  // Single words that place a note, a mood or an answer chip on the spectrum. Longest match wins, so
  // "sea notes" reaches 'aquatic' before "notes" reaches nothing.
  var NOTE_FAMILY = {
    citrus: 'fresh', bergamot: 'fresh', lemon: 'fresh', lime: 'fresh', grapefruit: 'fresh', neroli: 'fresh',
    orange: 'fresh', mandarin: 'fresh', petitgrain: 'fresh', fresh: 'fresh', energetic: 'fresh', cologne: 'fresh',
    aquatic: 'aquatic', marine: 'aquatic', sea: 'aquatic', ozonic: 'aquatic', water: 'aquatic', salt: 'aquatic',
    green: 'green', herbal: 'green', basil: 'green', mint: 'green', tea: 'green', fig: 'green', grass: 'green',
    galbanum: 'green', bamboo: 'green', cucumber: 'green',
    floral: 'floral', flower: 'floral', rose: 'floral', jasmine: 'floral', iris: 'floral', violet: 'floral',
    tuberose: 'floral', peony: 'floral', ylang: 'floral', lavender: 'floral', lily: 'floral', orchid: 'floral',
    freesia: 'floral', magnolia: 'floral', romantic: 'floral', gardenia: 'floral',
    fruity: 'fruity', peach: 'fruity', apple: 'fruity', pear: 'fruity', berry: 'fruity', raspberry: 'fruity',
    cherry: 'fruity', plum: 'fruity', coconut: 'fruity', lychee: 'fruity', pineapple: 'fruity', apricot: 'fruity',
    gourmand: 'gourmand', vanilla: 'gourmand', caramel: 'gourmand', chocolate: 'gourmand', sweet: 'gourmand',
    honey: 'gourmand', tonka: 'gourmand', praline: 'gourmand', almond: 'gourmand', coffee: 'gourmand',
    cocoa: 'gourmand', cozy: 'gourmand', sugar: 'gourmand',
    woody: 'woody', wood: 'woody', oud: 'woody', cedar: 'woody', sandalwood: 'woody', vetiver: 'woody',
    patchouli: 'woody', oakmoss: 'woody', leather: 'woody', birch: 'woody', cypress: 'woody', pine: 'woody',
    amber: 'amber', musk: 'amber', incense: 'amber', saffron: 'amber', spicy: 'amber', spice: 'amber',
    oriental: 'amber', resin: 'amber', benzoin: 'amber', labdanum: 'amber', elegant: 'amber', myrrh: 'amber',
    cardamom: 'amber', cinnamon: 'amber', pepper: 'amber'
  };
  var NOTE_KEYS = Object.keys(NOTE_FAMILY).sort(function (a, b) { return b.length - a.length; });

  function hashPick(s, list) {
    var n = 0;
    s = String(s || '');
    for (var i = 0; i < s.length; i++) n = (n * 31 + s.charCodeAt(i)) >>> 0;
    return list[n % list.length];
  }
  // The family a card belongs to. Unknown families fall back to a stable hash so a card keeps one colour.
  function familyKey(card) {
    var f = String(card.family || '').toLowerCase();
    if (FAMILIES.indexOf(f) >= 0) return f;
    var guess = textFamily([card.family_label, card.name].join(' '));
    return guess || hashPick(card.name || card.perfume_id, FAMILIES);
  }
  // The family a free-text phrase (a note, a mood, an answer chip) sits closest to, or '' when nothing matches.
  function textFamily(s) {
    s = String(s == null ? '' : s).toLowerCase();
    if (!s) return '';
    for (var i = 0; i < NOTE_KEYS.length; i++) if (s.indexOf(NOTE_KEYS[i]) >= 0) return NOTE_FAMILY[NOTE_KEYS[i]];
    return '';
  }

  var REFINE_RE = /^(less_sweet|fresher|cheaper|stronger|lighter|more_like:.+)$/;

  // ---------------------------------------------------------------- state
  var S = {
    mode: MODE,
    lang: initialLang(),
    sessionId: store.get('session_id'),
    session: null,
    ready: false,
    busy: false,
    open: false,
    tab: 'chat',
    entries: [],
    wishlist: [],
    saved: {},
    consent: false,
    pendingSave: null,
    thumbs: {},
    pendingEvents: [],
    seq: 0
  };
  S.consent = !!S.sessionId && store.get('consent') === S.sessionId;

  // ---------------------------------------------------------------- dom helpers
  function h(tag, attrs, kids) {
    var el = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (!Object.prototype.hasOwnProperty.call(attrs, k)) continue;
        var v = attrs[k];
        if (v == null || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k === 'text') el.textContent = v;
        else if (k === 'icon') el.innerHTML = ICONS[v] || '';
        else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? '' : v);
      }
    }
    add(el, kids);
    return el;
  }
  function add(el, kids) {
    if (kids == null) return el;
    if (!Array.isArray(kids)) kids = [kids];
    for (var i = 0; i < kids.length; i++) {
      var c = kids[i];
      if (c == null || c === false) continue;
      el.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
    }
    return el;
  }
  function safeUrl(u) {
    if (!u || typeof u !== 'string') return null;
    try {
      var url = new URL(u, API || location.href);
      return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
    } catch (e) { return null; }
  }
  function plain(s) { return String(s == null ? '' : s).replace(/\*\*|__/g, '').trim(); }
  function initials(name) {
    var words = String(name || '').replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/).filter(Boolean);
    var out = words.slice(0, 2).map(function (w) { return Array.from(w)[0]; }).join('');
    return (out || '?').toUpperCase();
  }
  // A family-tinted wrapper: everything inside inherits --fam / --fam-t / --fam-i / --fam-s / --fam-b.
  function famAttr(card) { return familyKey(card); }

  // ---------------------------------------------------------------- api
  function api(method, path, body) {
    var opts = { method: method, headers: { Accept: 'application/json' } };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    return fetch(API + path, opts).then(function (res) {
      return res.text().then(function (txt) {
        var data = null;
        try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = null; }
        if (!res.ok || !data) {
          var err = new Error((data && data.error) || ('HTTP ' + res.status));
          err.status = res.status; err.path = path;
          throw err;
        }
        return data;
      });
    }, function () {
      var err = new Error('network'); err.status = 0; err.path = path; throw err;
    });
  }

  function track(name, props) {
    props = props || {};
    if (!S.ready) { S.pendingEvents.push([name, props]); return; }
    props.lang = props.lang || S.lang;
    try {
      fetch(API + '/api/events', {
        method: 'POST', keepalive: true,
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ session_id: S.sessionId, name: name, props: props })
      }).catch(function () {});
    } catch (e) { /* analytics never breaks the UI */ }
  }

  var sessionPromise = null;
  function ensureSession() {
    if (S.session) return Promise.resolve(S.session);
    if (sessionPromise) return sessionPromise;
    var body = { lang: S.lang };
    if (S.sessionId) body.session_id = S.sessionId;
    if (BRAND) body.brand = BRAND;
    sessionPromise = api('POST', '/api/session', body).then(function (d) {
      sessionPromise = null;
      applySession(d);
      return d;
    }, function (err) {
      sessionPromise = null;
      throw err;
    });
    return sessionPromise;
  }

  function applySession(d) {
    if (d.session_id && d.session_id !== S.sessionId) {
      S.sessionId = d.session_id;
      S.wishlist = []; S.saved = {}; S.thumbs = {};
      S.consent = store.get('consent') === S.sessionId;
    }
    store.set('session_id', S.sessionId);
    S.session = d;
    S.ready = true;
    renderChrome();
    var q = S.pendingEvents; S.pendingEvents = [];
    q.forEach(function (e) { track(e[0], e[1]); });
    if (S.consent) loadWishlist();
    S.entries.forEach(function (e) { if (e.k === 'start') refresh(e); });
  }

  // ---------------------------------------------------------------- styles
  // "The scent spectrum". Perfume is invisible; colour makes it visible. Eight families, eight hues, each with a
  // vivid value (--f-x), a tint surface (--f-x-t), AA-verified text for that tint (--f-x-i, >=5.2:1 in both
  // themes), a photo stage (--f-x-s, kept light in dark mode so white product shots multiply onto it) and a
  // hairline (--f-x-b). [data-fam=...] maps one family onto the generic --fam* names its subtree reads.
  var CSS = [
    ':host{all:initial}',
    '.psa{',
    // brand: violet -> magenta -> warm orange
    '--brand-1:#7c3aed;--brand-2:#c4249b;--brand-3:#ff7a2f;',
    '--grad:linear-gradient(118deg,var(--brand-1),var(--brand-2) 56%,var(--brand-3));',
    '--grad-btn:linear-gradient(118deg,#7c3aed,#b91d8f);',       // white on either stop >= 5.7:1
    '--grad-text:linear-gradient(100deg,#6d28d9,#c31e7c 52%,#d9591a);', // 6.8 / 5.3 / 3.8 on --bg (large text)
    '--brand-ink:#ffffff;--brand-soft:rgba(124,58,237,.09);--brand-soft-2:rgba(124,58,237,.16);',
    '--brand-line:rgba(124,58,237,.30);--ring:rgba(124,58,237,.45);',
    // neutrals: near-white with a violet cast
    '--bg:#fbfaff;--bg-2:#f2effa;--surface:rgba(255,255,255,.74);--surface-solid:#ffffff;--surface-2:rgba(124,58,237,.07);',
    '--ink:#171226;--ink-2:#4a4460;--ink-3:#655e7d;',
    '--border:rgba(23,18,38,.10);--border-2:rgba(23,18,38,.17);--hair:rgba(255,255,255,.70);',
    '--danger:#a8231f;--danger-soft:#fdeceb;--danger-line:rgba(168,35,31,.22);--good:#0b7353;',
    '--shine:rgba(255,255,255,.75);--ph-ink:rgba(23,18,38,.45);',
    '--sh-1:0 1px 2px rgba(26,14,54,.05),0 6px 16px rgba(26,14,54,.06);',
    '--sh-2:0 2px 6px rgba(26,14,54,.06),0 14px 34px rgba(60,20,110,.10);',
    '--sh-3:0 10px 24px rgba(26,14,54,.10),0 30px 72px rgba(74,22,126,.16);',
    '--sh-brand:0 4px 12px rgba(124,58,237,.30),0 14px 30px rgba(185,29,143,.20);',
    '--r-1:10px;--r-2:14px;--r-3:18px;--r-4:22px;--r-5:28px;',
    '--t-1:160ms;--t-2:220ms;--t-3:280ms;--ease:cubic-bezier(.2,.9,.3,1);--tap:36px;',
    '--font:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans","Noto Sans Arabic",sans-serif;',
    '--font-display:"SF Pro Display","Segoe UI Variable Display",system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;',
    '--font-num:ui-rounded,"SF Pro Rounded","Segoe UI Variable Display",system-ui,-apple-system,"Segoe UI",sans-serif;',
    // family scale, light theme
    '--f-fresh:#a9d91c;--f-fresh-t:#f5fae4;--f-fresh-i:#58710f;--f-fresh-s:#eef7d2;--f-fresh-b:#d8ee99;',
    '--f-green:#12c08a;--f-green-t:#e3f7f1;--f-green-i:#0b7353;--f-green-s:#d0f2e8;--f-green-b:#94e3ca;',
    '--f-aquatic:#1cb2e8;--f-aquatic-t:#e4f6fc;--f-aquatic-i:#116d8e;--f-aquatic-s:#d2f0fa;--f-aquatic-b:#99dcf5;',
    '--f-floral:#f5568f;--f-floral-t:#feebf2;--f-floral-i:#a93b63;--f-floral-s:#fddde9;--f-floral-b:#fab3cd;',
    '--f-fruity:#ff6b52;--f-fruity-t:#ffedea;--f-fruity-i:#a64635;--f-fruity-s:#ffe1dc;--f-fruity-b:#ffbcb1;',
    '--f-gourmand:#a95ac8;--f-gourmand-t:#f5ebf8;--f-gourmand-i:#8748a0;--f-gourmand-s:#eedef4;--f-gourmand-b:#d8b5e6;',
    '--f-woody:#a3663e;--f-woody-t:#f4ede8;--f-woody-i:#895634;--f-woody-s:#ede0d8;--f-woody-b:#d6baa8;',
    '--f-amber:#e8a22a;--f-amber-t:#fcf4e5;--f-amber-i:#875e18;--f-amber-s:#faecd4;--f-amber-b:#f5d59f;',
    // default family tokens, so anything outside a [data-fam] subtree still looks deliberate
    '--fam:var(--brand-1);--fam-t:var(--brand-soft);--fam-i:var(--ink-2);--fam-s:var(--brand-soft);--fam-b:var(--border);',
    'font-family:var(--font);font-size:15px;line-height:1.5;color:var(--ink);-webkit-font-smoothing:antialiased;',
    '-moz-osx-font-smoothing:grayscale;text-align:start;font-variant-numeric:tabular-nums}',
    '.psa:lang(ar){font-family:"SF Arabic","Geeza Pro","Noto Sans Arabic","Noto Naskh Arabic","Segoe UI",Tahoma,system-ui,sans-serif;line-height:1.65;',
    '--font-display:"SF Arabic","Geeza Pro","Noto Sans Arabic","Segoe UI",Tahoma,system-ui,sans-serif}',
    // deep ink-indigo dark theme: luminous colour, never grey-brown
    '@media (prefers-color-scheme:dark){.psa{',
    '--brand-1:#a78bfa;--brand-2:#f472b6;--brand-3:#fdba74;',
    '--grad-btn:linear-gradient(118deg,#a78bfa,#f472b6);',
    '--grad-text:linear-gradient(100deg,#b69bff,#ff86c4 52%,#ffb26b);',
    '--brand-ink:#180f2e;--brand-soft:rgba(167,139,250,.14);--brand-soft-2:rgba(167,139,250,.22);',
    '--brand-line:rgba(167,139,250,.38);--ring:rgba(167,139,250,.55);',
    '--bg:#0b0a1a;--bg-2:#141130;--surface:rgba(46,40,86,.58);--surface-solid:#211d3c;--surface-2:rgba(255,255,255,.07);',
    '--ink:#f2effb;--ink-2:#c4bde0;--ink-3:#9a92bd;',
    '--border:rgba(255,255,255,.11);--border-2:rgba(255,255,255,.20);--hair:rgba(255,255,255,.10);',
    '--danger:#ffb1a3;--danger-soft:#3a1620;--danger-line:rgba(255,177,163,.28);--good:#3dcb9f;',
    '--shine:rgba(255,255,255,.14);--ph-ink:rgba(23,18,38,.55);',
    '--sh-1:0 1px 2px rgba(0,0,0,.35),0 6px 16px rgba(0,0,0,.30);',
    '--sh-2:0 2px 8px rgba(0,0,0,.40),0 16px 38px rgba(0,0,0,.42);',
    '--sh-3:0 10px 26px rgba(0,0,0,.48),0 34px 80px rgba(60,10,110,.44);',
    '--sh-brand:0 4px 14px rgba(167,139,250,.32),0 16px 34px rgba(244,114,182,.22);',
    '--f-fresh:#b8e045;--f-fresh-t:#2d3711;--f-fresh-i:#a9d91c;--f-fresh-s:#e7f4bf;--f-fresh-b:#4c620d;',
    '--f-green:#3dcb9f;--f-green-t:#09312b;--f-green-i:#12c08a;--f-green-s:#bdedde;--f-green-b:#08563e;',
    '--f-aquatic:#45c0ec;--f-aquatic-t:#0b2d42;--f-aquatic-i:#1cb2e8;--f-aquatic-s:#bfe9f9;--f-aquatic-b:#0d5068;',
    '--f-floral:#f774a3;--f-floral-t:#3f182d;--f-floral-i:#f66498;--f-floral-s:#fcd0e0;--f-floral-b:#6e2740;',
    '--f-fruity:#ff8671;--f-fruity-t:#401d1f;--f-fruity-i:#ff6b52;--f-fruity-s:#ffd6cf;--f-fruity-b:#733025;',
    '--f-gourmand:#b878d2;--f-gourmand-t:#2d193a;--f-gourmand-i:#ba7bd3;--f-gourmand-s:#e7d1f0;--f-gourmand-b:#4c285a;',
    '--f-woody:#b48261;--f-woody-t:#2b1c1a;--f-woody-i:#b78868;--f-woody-s:#e5d4c9;--f-woody-b:#492e1c;',
    '--f-amber:#ecb350;--f-amber-t:#3c2a15;--f-amber-i:#e8a22a;--f-amber-s:#f9e5c3;--f-amber-b:#684913}}',
    '@media (pointer:coarse){.psa{--tap:44px}}',
    '[data-fam=fresh]{--fam:var(--f-fresh);--fam-t:var(--f-fresh-t);--fam-i:var(--f-fresh-i);--fam-s:var(--f-fresh-s);--fam-b:var(--f-fresh-b)}',
    '[data-fam=green]{--fam:var(--f-green);--fam-t:var(--f-green-t);--fam-i:var(--f-green-i);--fam-s:var(--f-green-s);--fam-b:var(--f-green-b)}',
    '[data-fam=aquatic]{--fam:var(--f-aquatic);--fam-t:var(--f-aquatic-t);--fam-i:var(--f-aquatic-i);--fam-s:var(--f-aquatic-s);--fam-b:var(--f-aquatic-b)}',
    '[data-fam=floral]{--fam:var(--f-floral);--fam-t:var(--f-floral-t);--fam-i:var(--f-floral-i);--fam-s:var(--f-floral-s);--fam-b:var(--f-floral-b)}',
    '[data-fam=fruity]{--fam:var(--f-fruity);--fam-t:var(--f-fruity-t);--fam-i:var(--f-fruity-i);--fam-s:var(--f-fruity-s);--fam-b:var(--f-fruity-b)}',
    '[data-fam=gourmand]{--fam:var(--f-gourmand);--fam-t:var(--f-gourmand-t);--fam-i:var(--f-gourmand-i);--fam-s:var(--f-gourmand-s);--fam-b:var(--f-gourmand-b)}',
    '[data-fam=woody]{--fam:var(--f-woody);--fam-t:var(--f-woody-t);--fam-i:var(--f-woody-i);--fam-s:var(--f-woody-s);--fam-b:var(--f-woody-b)}',
    '[data-fam=amber]{--fam:var(--f-amber);--fam-t:var(--f-amber-t);--fam-i:var(--f-amber-i);--fam-s:var(--f-amber-s);--fam-b:var(--f-amber-b)}',
    '*,*::before,*::after{box-sizing:border-box}',
    'button,input{font:inherit;color:inherit;margin:0;font-variant-numeric:inherit}',
    'button{cursor:pointer;-webkit-tap-highlight-color:transparent}',
    'button:disabled{cursor:default}',
    ':focus-visible{outline:2px solid var(--brand-2);outline-offset:2px;border-radius:var(--r-1)}',
    '::selection{background:var(--brand-soft-2);color:var(--ink)}',
    'svg{width:20px;height:20px;display:block;flex:none}',
    '[dir=rtl] svg.flip{transform:scaleX(-1)}',
    '.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}',
    // ---- glass: translucent surface, fine light border, soft coloured shadow; solid where blur is unsupported
    '.glass{background:var(--surface-solid);border:1px solid var(--border);box-shadow:var(--sh-1)}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.glass{background:var(--surface);-webkit-backdrop-filter:saturate(1.7) blur(16px);backdrop-filter:saturate(1.7) blur(16px)}}',
    // scrollbars, caret and other browser surfaces wear the palette too
    '.list,.wl{scrollbar-width:thin;scrollbar-color:var(--border-2) transparent}',
    '.list::-webkit-scrollbar,.wl::-webkit-scrollbar{width:10px}',
    '.list::-webkit-scrollbar-thumb,.wl::-webkit-scrollbar-thumb{background:var(--border-2);border:3px solid transparent;background-clip:content-box;border-radius:999px}',
    '.list::-webkit-scrollbar-thumb:hover,.wl::-webkit-scrollbar-thumb:hover{background:var(--brand-line);background-clip:content-box}',
    // ---- launcher
    '.launcher{position:fixed;z-index:2147483000;bottom:20px;inset-inline-end:20px;display:flex;align-items:center;gap:9px;height:54px;padding-inline:17px 22px;',
    'border:0;border-radius:999px;background:var(--grad-btn);color:#fff;font-weight:650;font-size:15px;letter-spacing:-.01em;box-shadow:var(--sh-brand);',
    'transition:transform var(--t-2) var(--ease),box-shadow var(--t-2) var(--ease)}',
    '.launcher::before{content:"";position:absolute;inset:0;border-radius:inherit;background:linear-gradient(180deg,rgba(255,255,255,.28),transparent 58%);pointer-events:none}',
    '.launcher:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(124,58,237,.38),0 20px 44px rgba(185,29,143,.26)}',
    '.launcher:active{transform:translateY(0)}',
    '.launcher[hidden]{display:none}',
    // ---- panel
    '.panel{position:fixed;z-index:2147483001;bottom:20px;inset-inline-end:20px;width:420px;height:min(720px,calc(100vh - 40px));display:flex;flex-direction:column;',
    'background:var(--bg);border:1px solid var(--border-2);border-radius:var(--r-5);box-shadow:var(--sh-3);overflow:hidden;isolation:isolate;',
    'animation:psa-panel var(--t-3) var(--ease)}',
    // atmosphere inside the floating panel: the host page's background is not ours to style
    '.panel::before{content:"";position:absolute;inset:-30%;z-index:-1;pointer-events:none;',
    'background:radial-gradient(38% 34% at 16% 12%,rgba(124,58,237,.30),transparent 64%),',
    'radial-gradient(34% 32% at 88% 6%,rgba(224,51,142,.26),transparent 66%),',
    'radial-gradient(44% 40% at 84% 88%,rgba(255,138,61,.22),transparent 66%),',
    'radial-gradient(40% 36% at 8% 92%,rgba(34,178,232,.22),transparent 66%);',
    'animation:psa-drift 48s var(--ease) infinite alternate}',
    '@media (prefers-color-scheme:dark){.panel::before{',
    'background:radial-gradient(38% 34% at 16% 12%,rgba(139,92,246,.42),transparent 64%),',
    'radial-gradient(34% 32% at 88% 6%,rgba(236,72,153,.34),transparent 66%),',
    'radial-gradient(44% 40% at 84% 88%,rgba(251,146,60,.24),transparent 66%),',
    'radial-gradient(40% 36% at 8% 92%,rgba(56,189,248,.28),transparent 66%)}}',
    '.panel[hidden]{display:none}',
    // rise and fade only: no scale, so the panel's measured width is its real width from the first frame
    '@keyframes psa-panel{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}',
    '@keyframes psa-drift{from{transform:translate3d(0,0,0) scale(1)}to{transform:translate3d(2.5%,-2%,0) scale(1.12)}}',
    '@keyframes psa-rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}',
    '@keyframes psa-shim{from{transform:translateX(-120%)}to{transform:translateX(120%)}}',
    '@keyframes psa-shim-rtl{from{transform:translateX(120%)}to{transform:translateX(-120%)}}',
    '@media (min-width:640px) and (max-width:1024px){.panel{width:440px;height:min(780px,calc(100vh - 40px))}}',
    '@media (max-width:419px){.psa .head{gap:6px;padding-inline:14px 6px}.head .mark{width:32px;height:32px}}',
    '@media (max-width:639px){.panel{inset:0;width:100%;height:100%;height:100dvh;border:0;border-radius:0}.launcher{bottom:16px;inset-inline-end:16px}}',
    // ---- page mode: mounted inline, always open, the host page owns the backdrop
    '.psa[data-mode=page]{display:block;width:100%;height:100%}',
    '.psa[data-mode=page] .launcher{display:none}',
    '.psa[data-mode=page] .panel{position:static;inset:auto;width:100%;height:100%;max-width:none;border:0;border-radius:0;box-shadow:none;background:transparent;animation:none}',
    '.psa[data-mode=page] .panel::before{display:none}',
    // the host page owns brand + language switch (see index.html); avoid duplicating them inside the widget
    '.psa[data-mode=page] .head{display:none}',
    // full-bleed bars (border spans the whole width) but their content aligns to the same 880px column as .list
    '.psa[data-mode=page] .tabs{padding-inline:max(20px,calc((100% - 880px)/2 + 20px))}',
    '.psa[data-mode=page] .list{max-width:880px;margin-inline:auto;width:100%;padding:28px 20px;gap:18px}',
    '.psa[data-mode=page] .wl{max-width:880px;margin-inline:auto;width:100%;padding:28px 20px;gap:14px}',
    '.psa[data-mode=page] .consent{max-width:880px;margin-inline:auto;width:100%}',
    '.psa[data-mode=page] .composer{max-width:880px;margin-inline:auto;width:100%;border-top:0;background:transparent;padding-block:16px}',
    // ---- header (floating mode): gradient band
    '.head{position:relative;display:flex;align-items:center;gap:10px;padding:14px 12px 12px 16px;padding-inline:16px 10px;',
    'background:var(--grad);color:#fff;isolation:isolate}',
    '.head::after{content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(180deg,rgba(255,255,255,.16),rgba(0,0,0,.06))}',
    '.mark{width:36px;height:36px;border-radius:12px;display:grid;place-items:center;background:rgba(255,255,255,.22);color:#fff;flex:none;',
    'box-shadow:inset 0 1px 0 rgba(255,255,255,.4)}',
    '.titles{flex:1;min-width:0}',
    '.title{margin:0;font-family:var(--font-display);font-size:16.5px;font-weight:700;letter-spacing:-.015em;line-height:1.25;color:#fff;',
    'white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.subtitle{margin:1px 0 0;font-size:12.5px;color:rgba(255,255,255,.82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.iconbtn{width:var(--tap);height:var(--tap);display:grid;place-items:center;border:0;border-radius:var(--r-1);background:transparent;color:#fff;',
    'transition:background var(--t-1) var(--ease)}',
    '.iconbtn:hover{background:rgba(255,255,255,.20)}',
    '.langbtn{flex:none;height:32px;padding:0 12px;border:1px solid rgba(255,255,255,.42);border-radius:999px;background:rgba(255,255,255,.14);',
    'font-size:13px;font-weight:650;color:#fff;transition:background var(--t-1) var(--ease)}',
    '@media (pointer:coarse){.langbtn{height:40px}}',
    '.langbtn:hover{background:rgba(255,255,255,.28)}',
    '.langbtn:lang(ar),.langbtn[lang=ar]{font-family:"SF Arabic","Geeza Pro","Noto Sans Arabic",Tahoma,system-ui,sans-serif}',
    // ---- tabs
    '.tabs{position:relative;display:flex;align-items:center;gap:6px;padding:6px 12px 0;border-bottom:1px solid var(--border)}',
    '.psa[data-mode=page] .tabs{background:var(--surface);-webkit-backdrop-filter:saturate(1.6) blur(14px);backdrop-filter:saturate(1.6) blur(14px)}',
    // touch screens: solid tab bar (mobile WebKit can paint a backdrop-filter bar blank over scrolling content)
    '@media (hover:none),(pointer:coarse){.psa[data-mode=page] .tabs{-webkit-backdrop-filter:none;backdrop-filter:none;background:var(--surface-solid)}}',
    '.restart-link{display:none}',
    '.psa[data-mode=page] .restart-link{display:inline-flex;align-items:center;margin-inline-start:auto;height:var(--tap);padding:0 6px;border:0;background:none;',
    'font-size:13px;font-weight:650;color:var(--ink-3);border-radius:var(--r-1);transition:color var(--t-1) var(--ease)}',
    '.psa[data-mode=page] .restart-link:hover{color:var(--brand-2)}',
    '.tab{position:relative;border:0;background:none;padding:8px 10px 12px;min-height:var(--tap);font-size:14px;font-weight:600;color:var(--ink-3);',
    'transition:color var(--t-1) var(--ease)}',
    '.tab:hover{color:var(--ink-2)}',
    '.tab[aria-selected=true]{color:var(--ink)}',
    '.tab[aria-selected=true]::after{content:"";position:absolute;inset-inline:8px;bottom:-1px;height:3px;border-radius:3px 3px 0 0;background:var(--grad)}',
    // ---- body
    '.body{flex:1;min-height:0;display:flex;flex-direction:column}',
    '.list{position:relative;flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:16px;display:flex;flex-direction:column;gap:12px}',
    '.list[hidden]{display:none}',
    '.psa-in{animation:psa-rise var(--t-3) var(--ease) both}',
    // ---- messages
    '.msg{max-width:86%;padding:11px 15px;border-radius:var(--r-3);white-space:pre-wrap;overflow-wrap:anywhere;margin:0;font-size:15px}',
    '.bot{align-self:flex-start;color:var(--ink);background:var(--surface-solid);border:1px solid var(--border);box-shadow:var(--sh-1);border-end-start-radius:6px}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.bot{background:var(--surface);-webkit-backdrop-filter:saturate(1.7) blur(16px);backdrop-filter:saturate(1.7) blur(16px)}}',
    '.user{align-self:flex-end;background:var(--grad-btn);color:#fff;border-end-end-radius:6px;box-shadow:var(--sh-1)}',
    '@media (prefers-color-scheme:dark){.user{color:var(--brand-ink)}}',
    '.wrap{display:flex;flex-direction:column;gap:10px;align-self:stretch}',
    '.note{display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-3);margin:0}',
    '.note svg{width:15px;height:15px;color:var(--brand-2)}',
    '.err{align-self:flex-start;max-width:86%;display:flex;flex-direction:column;gap:10px;padding:12px 15px;border-radius:var(--r-3);border-end-start-radius:6px;',
    'background:var(--danger-soft);border:1px solid var(--danger-line);color:var(--ink)}',
    // ---- chips
    '.chips{display:flex;flex-wrap:wrap;gap:8px}',
    '.chip{position:relative;min-height:var(--tap);padding:7px 15px;border:1px solid var(--border-2);border-radius:999px;background:var(--surface-solid);',
    'font-size:14px;font-weight:550;line-height:1.2;color:var(--ink);text-align:center;box-shadow:var(--sh-1);',
    'transition:transform var(--t-1) var(--ease),border-color var(--t-1) var(--ease),box-shadow var(--t-1) var(--ease),background var(--t-1) var(--ease)}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.chip{background:var(--surface);-webkit-backdrop-filter:saturate(1.6) blur(12px);backdrop-filter:saturate(1.6) blur(12px)}}',
    // a chip whose answer lands on the spectrum wears that family: tinted face, matching dot
    '.chip[data-fam]{background:var(--fam-t);border-color:var(--fam-b);color:var(--fam-i);font-weight:600;',
    'padding-inline-start:32px}',
    '.chip[data-fam]::before{content:"";position:absolute;inset-inline-start:13px;top:50%;width:9px;height:9px;margin-top:-4.5px;border-radius:50%;',
    'background:var(--fam);box-shadow:0 0 0 3px color-mix(in srgb,var(--fam) 22%,transparent)}',
    '@media (hover:hover){.chip:hover:not(:disabled):not([aria-pressed=true]){transform:translateY(-2px);border-color:var(--brand-line);box-shadow:var(--sh-2)}}',
    '.chip[aria-pressed=true]{background:var(--grad-btn);border-color:transparent;color:#fff;box-shadow:var(--sh-brand);font-weight:650}',
    '@media (prefers-color-scheme:dark){.chip[aria-pressed=true]{color:var(--brand-ink)}}',
    // a chosen answer stays on its own family: it fills with that family\'s ink (>=5.1:1 against the label)
    '.chip[data-fam][aria-pressed=true]{background:var(--fam-i);border-color:var(--fam-i);color:var(--surface-solid);',
    'box-shadow:0 3px 10px color-mix(in srgb,var(--fam) 40%,transparent)}',
    '.chip[aria-pressed=true]::before{background:currentColor;box-shadow:none}',
    '.chip:disabled{opacity:.5;box-shadow:none}',
    // ---- start cards
    '.starts{display:grid;gap:10px;align-self:stretch}',
    '.start{position:relative;display:flex;align-items:center;gap:13px;width:100%;padding:16px;border-radius:var(--r-4);text-align:start;isolation:isolate;',
    'border:1px solid transparent;background:var(--grad-btn);color:#fff;box-shadow:var(--sh-brand);',
    'transition:transform var(--t-2) var(--ease),box-shadow var(--t-2) var(--ease)}',
    '@media (prefers-color-scheme:dark){.start{color:var(--brand-ink)}}',
    '.start::after{content:"";position:absolute;inset:0;z-index:-1;border-radius:inherit;background:linear-gradient(180deg,rgba(255,255,255,.22),transparent 60%)}',
    '.start:hover{transform:translateY(-2px);box-shadow:0 10px 22px rgba(124,58,237,.34),0 22px 48px rgba(185,29,143,.24)}',
    '.start:disabled{opacity:.6;transform:none}',
    '.start .ic{width:44px;height:44px;border-radius:var(--r-2);display:grid;place-items:center;background:rgba(255,255,255,.24);color:inherit;flex:none;',
    'box-shadow:inset 0 1px 0 rgba(255,255,255,.4)}',
    '.start .ic svg{width:22px;height:22px}',
    '.start b{display:block;font-family:var(--font-display);font-size:16px;font-weight:700;letter-spacing:-.01em}',
    '.start small{display:block;font-size:13.5px;opacity:.88;margin-top:1px}',
    '.start .go{margin-inline-start:auto;flex:none;opacity:.82;transition:transform var(--t-2) var(--ease)}',
    '.start:hover .go{transform:translateX(3px)}',
    '[dir=rtl] .start:hover .go{transform:translateX(-3px)}',
    // the second start card (free chat) stays quiet so the guided card is the one call to action
    '.start[data-start=chat]{background:var(--surface-solid);color:var(--ink);border-color:var(--border);box-shadow:var(--sh-1)}',
    '.start[data-start=chat]::after{display:none}',
    '.start[data-start=chat] .ic{background:var(--brand-soft);color:var(--brand-2)}',
    '.start[data-start=chat] small{color:var(--ink-3);opacity:1}',
    '.start[data-start=chat]:hover{border-color:var(--brand-line);box-shadow:var(--sh-2)}',
    // ---- hero / empty state
    '.empty-state{display:flex;flex-direction:column;gap:20px;align-self:stretch;padding:4px 2px}',
    '@media (min-width:760px){.psa[data-mode=page] .empty-state:only-child{flex:1;justify-content:center;padding-block:8px}}',
    '.hero-title{margin:0;font-family:var(--font-display);font-size:clamp(32px,6.2vw,58px);font-weight:700;line-height:1.06;letter-spacing:-.035em;',
    'max-width:15ch;text-wrap:balance}',
    '.hero-title:lang(ar){letter-spacing:0;line-height:1.28}',
    '.hero-em{background:var(--grad-text);-webkit-background-clip:text;background-clip:text;color:transparent;-webkit-text-fill-color:transparent}',
    '.hero-sub{margin:-4px 0 0;font-size:16.5px;line-height:1.55;color:var(--ink-2);max-width:52ch}',
    // the spectrum ribbon: eight bottles, eight families, the concept stated without a word
    '.spectrum{display:none}',
    '@media (min-width:700px){.spectrum{display:block;margin:2px 0 -2px;pointer-events:none}}',
    '.spectrum svg{width:100%;height:auto;max-height:118px}',
    '.starters-label{margin:8px 0 -4px;font-size:12.5px;font-weight:700;color:var(--ink-3);text-transform:uppercase;letter-spacing:.08em}',
    '.starters-label:lang(ar){letter-spacing:0;text-transform:none}',
    '.starters{display:grid;grid-template-columns:1fr;gap:10px}',
    '@media (min-width:560px){.starters{grid-template-columns:1fr 1fr}}',
    '.starter{position:relative;min-height:var(--tap);padding:14px 18px 14px 42px;padding-inline:42px 18px;border:1px solid var(--border);border-radius:var(--r-4);',
    'background:var(--surface-solid);box-shadow:var(--sh-1);text-align:start;font-size:14.5px;font-weight:550;line-height:1.4;color:var(--ink);',
    'transition:transform var(--t-2) var(--ease),border-color var(--t-2) var(--ease),box-shadow var(--t-2) var(--ease)}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.starter{background:var(--surface);-webkit-backdrop-filter:saturate(1.6) blur(14px);backdrop-filter:saturate(1.6) blur(14px)}}',
    '.starter::before{content:"";position:absolute;inset-inline-start:18px;top:50%;width:11px;height:11px;margin-top:-5.5px;border-radius:50%;',
    'background:var(--fam);box-shadow:0 0 0 4px color-mix(in srgb,var(--fam) 20%,transparent)}',
    '.starter:hover{transform:translateY(-2px);border-color:var(--fam-b);box-shadow:var(--sh-2)}',
    '.starter:disabled{opacity:.55;transform:none}',
    // ---- generic card + guided question
    '.card{align-self:stretch;border-radius:var(--r-4);padding:18px;background:var(--surface-solid);border:1px solid var(--border);box-shadow:var(--sh-2)}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.card{background:var(--surface);-webkit-backdrop-filter:saturate(1.7) blur(18px);backdrop-filter:saturate(1.7) blur(18px)}}',
    // the question card is a card, not a banner: it stops well short of the reading column on wide screens
    '.psa[data-mode=page] .card{max-width:660px}',
    '.quiz{display:flex;flex-direction:column;gap:14px}',
    '.quiz .row-end{margin-top:2px;padding-top:13px;border-top:1px solid var(--border)}',
    '.progress{display:flex;align-items:center;gap:12px;font-size:12.5px;font-weight:600;color:var(--ink-3)}',
    '.progress span:first-child{white-space:nowrap}',
    '.bar{flex:1;height:6px;border-radius:999px;background:var(--surface-2);overflow:hidden;box-shadow:inset 0 1px 2px rgba(23,18,38,.08)}',
    // each question is a freshly rendered card, so the fill arrives at its width: nothing to tween, no layout thrash
    '.bar i{display:block;height:100%;background:var(--grad);border-radius:999px}',
    '.q{margin:0;font-family:var(--font-display);font-size:19px;font-weight:700;letter-spacing:-.018em;line-height:1.28;color:var(--ink);text-wrap:balance}',
    '.q:lang(ar){letter-spacing:0;line-height:1.5}',
    '.row-end{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:8px}',
    // ---- scenario cards (guided Q2 "pick the moments", Q3 "which moment"): a family-tinted card grid
    '.psa[data-mode=page] .card.quiz.scn-q{max-width:880px}',
    '.scn{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));grid-auto-rows:1fr;gap:10px}',
    '.scard{position:relative;display:block;width:100%;height:100%;min-height:96px;padding:12px;border-radius:var(--r-3);',
    'border:1px solid var(--border);color:var(--ink);text-align:start;box-shadow:var(--sh-1);',
    'background:radial-gradient(140% 120% at 100% 0%,var(--fam-t),transparent 64%),var(--surface-solid);',
    'transition:transform var(--t-1) var(--ease),border-color var(--t-1) var(--ease),box-shadow var(--t-1) var(--ease),background var(--t-1) var(--ease)}',
    '[dir=rtl] .scard{background:radial-gradient(140% 120% at 0% 0%,var(--fam-t),transparent 64%),var(--surface-solid)}',
    '.scard:focus-visible{border-radius:var(--r-3)}',
    '.scard-art{float:right;width:36px;height:36px;margin:-3px -3px 4px 8px;border-radius:11px;display:grid;place-items:center;',
    'background:linear-gradient(150deg,var(--fam-s),var(--fam-t));box-shadow:inset 0 0 0 1px var(--fam-b)}',
    '[dir=rtl] .scard-art{float:left;margin:-3px 8px 4px -3px}',
    '.scard-art svg{width:30px;height:30px}',
    '.scard b{display:block;font-family:var(--font-display);font-size:14px;font-weight:700;line-height:1.3;letter-spacing:-.01em;overflow-wrap:normal}',
    '.scard b:lang(ar){letter-spacing:0;line-height:1.45}',
    '.scard small{display:block;margin-top:4px;font-size:12.5px;line-height:1.4;color:var(--ink-2)}',
    '.scard-check{position:absolute;top:6px;inset-inline-end:6px;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;',
    'background:var(--fam-i);color:var(--surface-solid);box-shadow:0 0 0 2px var(--surface-solid);opacity:0;transform:scale(.5);',
    'transition:opacity var(--t-1) var(--ease),transform var(--t-2) var(--ease)}',
    '.scard-check svg{width:14px;height:14px}',
    '@media (hover:hover){.scard:hover:not([aria-disabled=true]):not(:disabled){transform:translateY(-2px);border-color:var(--fam-b);box-shadow:var(--sh-2)}}',
    // chosen: the card fills with its family tint and wears a check
    '.scard[aria-pressed=true]{background:var(--fam-t);border-color:var(--fam-i);',
    'box-shadow:0 0 0 1px var(--fam-i),0 8px 20px color-mix(in srgb,var(--fam) 28%,transparent)}',
    '.scard[aria-pressed=true] b{color:var(--fam-i)}',
    '.scard[aria-pressed=true] .scard-check{opacity:1;transform:none}',
    '.scard[aria-disabled=true]{opacity:.48;cursor:default;box-shadow:none}',
    '.scard:disabled{opacity:.5;box-shadow:none}',
    // "something else": a quiet dashed card that hands over to the composer
    '.scard.other{border-style:dashed;border-color:var(--brand-line);background:transparent;box-shadow:none}',
    '.scard.other .scard-art{background:var(--brand-soft);box-shadow:none;color:var(--brand-2)}',
    '.scard.other .scard-art svg{width:20px;height:20px}',
    // the entrance: a short stagger on arrival only (a re-render after a tap never replays it)
    '.psa-in .scard{animation:psa-rise var(--t-3) var(--ease) both;animation-delay:calc(var(--i,0) * 32ms)}',
    // Q3 moments: fewer, larger cards, three across
    '.scn.big{grid-template-columns:repeat(3,1fr);gap:12px}',
    '.scn.big .scard{min-height:128px;padding:14px}',
    '.scn.big .scard-art{float:none;width:48px;height:48px;margin:0 0 10px;border-radius:14px}',
    '.scn.big .scard-art svg{width:38px;height:38px}',
    '.scn.big .scard b{font-size:15.5px}',
    '.scn.big .scard small{font-size:13px}',
    // the grid follows the question card's own width (phone, 420px floating panel, or the wide page column)
    '.scn-q{container:scn / inline-size}',
    '@container scn (max-width:520px){',
    '.scn{grid-template-columns:1fr 1fr;gap:8px}',
    '.scn.big{grid-template-columns:1fr;gap:8px}',
    '.scn.big .scard{display:flex;align-items:center;gap:13px;min-height:78px;padding:12px 14px}',
    '.scn.big .scard-art{flex:none;margin:0;width:46px;height:46px}',
    '.scn.big .scard-txt{flex:1;min-width:0}',
    '.scn.big .scard b{font-size:15px}',
    '}',
    // ---- buttons
    '.btn{min-height:var(--tap);padding:9px 20px;border-radius:999px;border:1px solid transparent;font-size:14px;font-weight:650;display:inline-flex;',
    'align-items:center;justify-content:center;gap:7px;text-decoration:none;white-space:nowrap;',
    'transition:transform var(--t-1) var(--ease),box-shadow var(--t-1) var(--ease),border-color var(--t-1) var(--ease),background var(--t-1) var(--ease)}',
    '.primary{background:var(--grad-btn);color:#fff;box-shadow:var(--sh-brand)}',
    '@media (prefers-color-scheme:dark){.primary{color:var(--brand-ink)}}',
    '.primary:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 8px 18px rgba(124,58,237,.34),0 18px 38px rgba(185,29,143,.22)}',
    '.ghost{background:var(--surface-solid);border-color:var(--border-2);color:var(--ink);box-shadow:var(--sh-1)}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.ghost{background:var(--surface);-webkit-backdrop-filter:saturate(1.6) blur(12px);backdrop-filter:saturate(1.6) blur(12px)}}',
    '.ghost:hover:not(:disabled){transform:translateY(-1px);border-color:var(--brand-line);color:var(--brand-2);box-shadow:var(--sh-2)}',
    '.btn:disabled{opacity:.5;transform:none;box-shadow:none}',
    '.btn svg{width:16px;height:16px}',
    // ---- results
    '.results{display:flex;flex-direction:column;gap:14px;align-self:stretch}',
    '.rhead{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin:6px 2px 0}',
    '.rhead h3{margin:0;font-family:var(--font-display);font-size:13px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2)}',
    '.rhead:lang(ar) h3{letter-spacing:0;text-transform:none;font-size:14px}',
    '.picks{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:16px}',
    '@media (min-width:760px){.psa[data-mode=page] .picks{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;align-items:stretch}}',
    '.pick{position:relative;display:flex;flex-direction:column;gap:11px;border-radius:var(--r-4);padding:13px;',
    'background:var(--surface-solid);border:1px solid var(--border);box-shadow:var(--sh-2);',
    'transition:transform var(--t-2) var(--ease),box-shadow var(--t-2) var(--ease),border-color var(--t-2) var(--ease)}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.pick{background:var(--surface);-webkit-backdrop-filter:saturate(1.7) blur(18px);backdrop-filter:saturate(1.7) blur(18px)}}',
    '@media (hover:hover){.pick:hover{transform:translateY(-3px);border-color:var(--fam-b);',
    'box-shadow:0 12px 26px rgba(26,14,54,.12),0 30px 64px color-mix(in srgb,var(--fam) 26%,transparent)}}',
    '.results.psa-in .pick{animation:psa-rise var(--t-3) var(--ease) both;animation-delay:calc(var(--i,0) * 70ms)}',
    '.ptop{display:flex;gap:11px;align-items:flex-start}',
    // ---- the family-tinted stage: white product photos multiply onto a colour field
    '.media{position:relative;width:64px;height:64px;flex:none;border-radius:var(--r-2);overflow:hidden;isolation:isolate;',
    'background:linear-gradient(155deg,var(--fam-s),#fff 82%)}',
    '.media.sm{width:52px;height:52px;border-radius:var(--r-2);border:1px solid var(--fam-b)}',
    '.media img{width:100%;height:100%;object-fit:cover;display:block;mix-blend-mode:multiply}',
    // real photos are portrait bottle shots on white: always give them height:auto so aspect-ratio actually
    // applies (the base .media{height:64px} rule above otherwise wins, since aspect-ratio never overrides a
    // definite height) -- compact+capped in the 420px floating panel, uncapped for the page-mode grid below.
    '.media.portrait{width:100%;height:auto;aspect-ratio:4/5;max-height:262px;border-radius:var(--r-3);border:1px solid var(--fam-b);',
    'background:radial-gradient(110% 78% at 50% 4%,#fff,transparent 58%),linear-gradient(158deg,var(--fam-s),var(--fam-t))}',
    '.media.portrait img{width:100%;height:100%;object-fit:contain;padding:8px}',
    '.psa[data-mode=page] .media.portrait{max-height:none}',
    '.psa[data-mode=page] .media.portrait img{padding:10px}',
    // phone: the page-mode pick card turns into a compact tile beside the name/brand/match, with the reason,
    // notes and actions running full width below -- about one and a half cards fit a 390x844 screen.
    '@media (max-width:559px){',
    '.psa[data-mode=page] .pick{display:grid;grid-template-columns:106px 1fr;column-gap:13px;row-gap:9px}',
    '.psa[data-mode=page] .media.portrait{grid-column:1;grid-row:1/span 2;width:106px;height:134px;max-height:134px;aspect-ratio:auto}',
    '.psa[data-mode=page] .media.portrait img{padding:6px}',
    '.psa[data-mode=page] .ptop{grid-column:2;grid-row:1;align-self:start;gap:9px}',
    '.psa[data-mode=page] .ptop .rank{font-size:21px}',
    '.psa[data-mode=page] .ptop .score{width:40px;height:40px;padding-top:14px}',
    '.psa[data-mode=page] .ptop .score b{font-size:13px}',
    '.psa[data-mode=page] .ptop .name{font-size:15.5px}',
    '.psa[data-mode=page] .pick>.reason,.psa[data-mode=page] .pick>.tags,.psa[data-mode=page] .pick>.meta,',
    '.psa[data-mode=page] .pick>.detail,.psa[data-mode=page] .pick>.actions{grid-column:1/-1}',
    '}',
    // shimmer while the photo is still travelling: the tile reads as loading, never as blank
    '.media.ld::after{content:"";position:absolute;inset:0;z-index:2;pointer-events:none;',
    'background:linear-gradient(100deg,transparent 18%,var(--shine) 50%,transparent 82%);animation:psa-shim 1.5s var(--ease) infinite}',
    '[dir=rtl] .media.ld::after{animation-name:psa-shim-rtl}',
    '.ph{width:100%;height:100%;display:grid;place-items:center;font-family:var(--font-num);font-weight:700;font-size:19px;letter-spacing:.01em;color:var(--fam-i)}',
    '.media.sm .ph{font-size:15px}',
    '.media.portrait .ph{font-size:34px}',
    // ---- rank, name, family pill, match ring
    '.rank{flex:none;font-family:var(--font-num);font-size:26px;font-weight:800;line-height:1;letter-spacing:-.05em;color:var(--fam-i);',
    'opacity:.85;margin-top:-1px}',
    '.info{flex:1;min-width:0}',
    '.name{margin:0;font-family:var(--font-display);font-size:16.5px;font-weight:700;letter-spacing:-.018em;line-height:1.24;overflow-wrap:anywhere}',
    '.name:lang(ar){letter-spacing:0}',
    '.brandrow{display:flex;align-items:center;flex-wrap:wrap;gap:5px 7px;margin:5px 0 0}',
    '.brand{margin:0;font-size:13px;font-weight:550;color:var(--ink-2)}',
    '.fampill{display:inline-flex;align-items:center;gap:5px;padding:2px 9px 2px 7px;padding-inline:7px 9px;border-radius:999px;',
    'background:var(--fam-t);border:1px solid var(--fam-b);color:var(--fam-i);font-size:11.5px;font-weight:700;letter-spacing:.01em}',
    '.fampill::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--fam);flex:none}',
    '.score{flex:none;position:relative;width:46px;height:46px;display:flex;align-items:baseline;justify-content:center;border-radius:50%;',
    'background:conic-gradient(var(--fam) calc(var(--m,0) * 1%),var(--fam-t) 0);font-variant-numeric:tabular-nums;padding-top:16px}',
    '.score::before{content:"";position:absolute;inset:4px;border-radius:50%;background:var(--surface-solid)}',
    '.score b{position:relative;font-family:var(--font-num);font-size:15px;font-weight:800;letter-spacing:-.04em;color:var(--fam-i);line-height:1}',
    '.score i{position:relative;font-style:normal;font-size:9.5px;font-weight:700;color:var(--fam-i);opacity:.85;margin-inline-start:.5px}',
    // ---- reason, notes, meta
    '.reason{margin:0;font-size:14.5px;line-height:1.5;color:var(--ink-2)}',
    '.tags{display:flex;flex-wrap:wrap;gap:6px;margin:0;padding:0;list-style:none}',
    '.tag{padding:3px 10px;border-radius:999px;background:var(--fam-t);border:1px solid var(--fam-b);color:var(--fam-i);',
    'font-size:12.5px;font-weight:600}',
    '.meta{display:flex;align-items:center;flex-wrap:wrap;gap:5px 10px;font-size:13px;color:var(--ink-2)}',
    '.price{font-family:var(--font-num);font-weight:700;font-size:14.5px;color:var(--ink);font-variant-numeric:tabular-nums}',
    '.price.est{text-decoration:underline dotted var(--ink-3);text-underline-offset:3px;cursor:help}',
    '.dot-sep{width:3px;height:3px;border-radius:50%;background:var(--ink-3);opacity:.7}',
    '.more{margin-inline-start:auto;border:0;background:none;padding:5px 2px;font-size:13px;font-weight:700;color:var(--brand-2);border-radius:var(--r-1)}',
    '.more:hover{text-decoration:underline;text-underline-offset:3px}',
    // page mode: Details always sits on its own start-aligned line, consistently, instead of an unpredictable right float
    '.psa[data-mode=page] .more{flex:1 1 100%;margin-inline-start:0;text-align:start;padding:2px}',
    '.detail{display:grid;gap:5px;font-size:13px;line-height:1.5;color:var(--ink-2);padding:12px 14px;border-radius:var(--r-2);',
    'background:var(--fam-t);border:1px solid var(--fam-b)}',
    '.detail b{color:var(--fam-i);font-weight:700}',
    '.detail p{margin:0}',
    // ---- card actions
    '.actions{display:flex;align-items:center;gap:5px;margin-top:auto;padding-top:3px}',
    '.actions .btn{flex:1;min-width:0}',
    '@media (min-width:760px){.psa[data-mode=page] .actions{flex-wrap:wrap;row-gap:8px}.psa[data-mode=page] .actions .btn{flex:1 1 100%}}',
    '.tbtn{width:var(--tap);height:var(--tap);flex:none;display:grid;place-items:center;border:1px solid transparent;border-radius:var(--r-1);',
    'background:transparent;color:var(--ink-3);transition:background var(--t-1) var(--ease),color var(--t-1) var(--ease),transform var(--t-1) var(--ease)}',
    '.tbtn:hover{background:var(--surface-2);color:var(--ink)}',
    '.tbtn[aria-pressed=true]{color:var(--brand-1);background:var(--brand-soft);--thumb-fill:var(--brand-soft-2)}',
    '.tbtn.heart[aria-pressed=true]{color:var(--brand-2);background:var(--brand-soft);--heart-fill:currentColor;transform:scale(1.06)}',
    // ---- layering
    '.layer{display:flex;flex-direction:column;gap:10px;padding:15px;border-radius:var(--r-4);border:1px solid var(--fam-b);',
    'background:var(--fam-t);box-shadow:inset 0 1px 0 var(--hair)}',
    '.layer .lab{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:800;color:var(--fam-i);text-transform:uppercase;letter-spacing:.09em}',
    '.layer .lab:lang(ar){letter-spacing:0;text-transform:none;font-size:13px}',
    '.layer .lab svg{width:16px;height:16px}',
    '.lrow{display:flex;align-items:center;gap:12px;width:100%;padding:0;border:0;background:none;text-align:start}',
    '.lrow .info .name{font-size:15px}',
    '.layer p{margin:0;font-size:13.5px;line-height:1.5;color:var(--ink-2)}',
    '.link{display:inline-flex;align-items:center;gap:5px;font-size:13px;font-weight:700;color:var(--fam-i);text-decoration:none;',
    'border-radius:var(--r-1)}',
    '.link:hover{text-decoration:underline;text-underline-offset:3px}',
    '.link svg{width:14px;height:14px}',
    '.refine{display:flex;flex-direction:column;gap:9px;margin-top:2px}',
    '.refine .lab{font-size:12px;font-weight:800;color:var(--ink-3);text-transform:uppercase;letter-spacing:.09em}',
    '.refine .lab:lang(ar){letter-spacing:0;text-transform:none;font-size:13px}',
    // ---- typing: a gradient sweep through three dots
    '.typing{align-self:flex-start;display:flex;align-items:center;gap:9px;padding:13px 16px;border-radius:var(--r-3);border-end-start-radius:6px;',
    'background:var(--surface-solid);border:1px solid var(--border);box-shadow:var(--sh-1)}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.typing{background:var(--surface);-webkit-backdrop-filter:saturate(1.7) blur(16px);backdrop-filter:saturate(1.7) blur(16px)}}',
    '.dot{width:9px;height:9px;border-radius:50%;flex:none;background:var(--brand-1);animation:psa-dot 1.25s infinite var(--ease)}',
    '.dot:nth-child(2){background:var(--brand-2);animation-delay:.16s}',
    '.dot:nth-child(3){background:var(--brand-3);animation-delay:.32s}',
    '@keyframes psa-dot{0%,72%,100%{opacity:.34;transform:translateY(0) scale(.82)}36%{opacity:1;transform:translateY(-5px) scale(1)}}',
    '.typing-label{font-size:13.5px;font-weight:550;color:var(--ink-2)}',
    // ---- "what I learned"
    '.tags.learned{margin:0 2px}',
    '.tags.learned .tag{background:var(--brand-soft);border-color:var(--brand-line);color:var(--ink-2);font-weight:600;padding-inline-start:9px}',
    // the moment the shopper pictured leads the summary, framed by the brand gradient
    '.tags.learned .tag[data-k=feel]{border-color:transparent;color:var(--ink);',
    'background:linear-gradient(var(--surface-solid),var(--surface-solid)) padding-box,var(--grad) border-box}',
    // ---- consent + composer
    '.consent{display:flex;align-items:center;flex-wrap:wrap;gap:9px 12px;margin:0 12px 10px;padding:13px 15px;border-radius:var(--r-3);font-size:14px;',
    'background:var(--surface-solid);border:1px solid var(--brand-line);box-shadow:var(--sh-2)}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.consent{background:var(--surface);-webkit-backdrop-filter:saturate(1.7) blur(18px);backdrop-filter:saturate(1.7) blur(18px)}}',
    '.consent[hidden]{display:none}',
    '.consent span{flex:1 1 180px}',
    '.consent .btn{min-height:34px;padding:5px 16px}',
    '@media (pointer:coarse){.consent .btn{min-height:40px}}',
    '.composer{display:flex;align-items:center;gap:9px;padding:11px 12px;padding-bottom:calc(11px + env(safe-area-inset-bottom,0px));',
    'border-top:1px solid var(--border);background:var(--bg)}',
    '.composer[hidden]{display:none}',
    '.input{flex:1;min-width:0;height:48px;padding:0 18px;border:1px solid var(--border-2);border-radius:999px;color:var(--ink);font-size:16px;outline:none;',
    'caret-color:var(--brand-2);background:var(--surface-solid);box-shadow:var(--sh-1);transition:border-color var(--t-1) var(--ease),box-shadow var(--t-1) var(--ease)}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.input{background:var(--surface);-webkit-backdrop-filter:saturate(1.7) blur(16px);backdrop-filter:saturate(1.7) blur(16px)}}',
    '.input::placeholder{color:var(--ink-3);opacity:1}',
    '.input:focus{border-color:transparent;box-shadow:0 0 0 2px var(--ring),var(--sh-2)}',
    '.send{width:48px;height:48px;flex:none;display:grid;place-items:center;border:0;border-radius:50%;background:var(--grad-btn);color:#fff;',
    'box-shadow:var(--sh-brand);transition:transform var(--t-1) var(--ease),box-shadow var(--t-1) var(--ease),opacity var(--t-1) var(--ease)}',
    '@media (prefers-color-scheme:dark){.send{color:var(--brand-ink)}}',
    '.send:hover:not(:disabled){transform:scale(1.05)}',
    '.send:disabled{opacity:.38;box-shadow:none}',
    // ---- wishlist
    '.wl{flex:1;min-height:0;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}',
    '.wl[hidden]{display:none}',
    '.wl h3{margin:0 2px;font-family:var(--font-display);font-size:13px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2)}',
    '.wl h3:lang(ar){letter-spacing:0;text-transform:none;font-size:14px}',
    '.wlitem{display:flex;align-items:center;gap:13px;padding:12px;border-radius:var(--r-3);background:var(--surface-solid);',
    'border:1px solid var(--border);box-shadow:var(--sh-1);transition:transform var(--t-2) var(--ease),box-shadow var(--t-2) var(--ease)}',
    '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){',
    '.wlitem{background:var(--surface);-webkit-backdrop-filter:saturate(1.7) blur(16px);backdrop-filter:saturate(1.7) blur(16px)}}',
    '@media (hover:hover){.wlitem:hover{transform:translateY(-2px);box-shadow:var(--sh-2)}}',
    '.wlitem .info{display:flex;flex-direction:column;gap:3px}',
    '.wlitem .link{margin-inline-start:auto;flex:none;color:var(--brand-2)}',
    '.empty{margin:28px 8px;text-align:center;color:var(--ink-3);font-size:14.5px;line-height:1.6;max-width:44ch;margin-inline:auto}',
    // ================================================================ touch
    // No 300ms delay, no double-tap zoom, no grey flash. Touch gets a press state instead of hover, and
    // every hover flourish is neutralised so a tap does not leave a card stuck in its hover pose.
    'button,a,input,summary,.chip,.scard,.starter,.tab,.tbtn,.btn,.more,.link{touch-action:manipulation}',
    'button,a,input,summary{-webkit-tap-highlight-color:transparent}',
    '@media (hover:none){',
    '.chip:active:not(:disabled),.starter:active:not(:disabled),.btn:active:not(:disabled),.scard:active:not(:disabled):not([aria-disabled=true]),',
    '.start:active:not(:disabled),.tbtn:active,.send:active:not(:disabled),.launcher:active{transform:scale(.97)}',
    '.launcher:hover{transform:none;box-shadow:var(--sh-brand)}',
    '.start:hover{transform:none;box-shadow:var(--sh-brand)}',
    '.start:hover .go,[dir=rtl] .start:hover .go{transform:none}',
    '.start[data-start=chat]:hover{transform:none;border-color:var(--border);box-shadow:var(--sh-1)}',
    '.starter:hover{transform:none;border-color:var(--border);box-shadow:var(--sh-1)}',
    '.primary:hover:not(:disabled){transform:none;box-shadow:var(--sh-brand)}',
    '.ghost:hover:not(:disabled){transform:none;border-color:var(--border-2);color:var(--ink);box-shadow:var(--sh-1)}',
    '.send:hover:not(:disabled){transform:none}',
    '.iconbtn:hover{background:transparent}',
    '.langbtn:hover{background:rgba(255,255,255,.14)}',
    '.tbtn:hover{background:transparent;color:var(--ink-3)}',
    '.tbtn[aria-pressed=true]:hover{background:var(--brand-soft);color:var(--brand-1)}',
    '.tbtn.heart[aria-pressed=true]:hover{background:var(--brand-soft);color:var(--brand-2)}',
    '.more:hover,.link:hover{text-decoration:none}',
    '.tab:hover{color:var(--ink-3)}',
    '.tab[aria-selected=true]:hover{color:var(--ink)}',
    '.psa[data-mode=page] .restart-link:hover{color:var(--ink-3)}',
    '}',
    // ================================================================ dynamic viewport + keyboard
    // --psa-kb is what the on-screen keyboard is covering right now, measured from visualViewport (see
    // syncViewport). It stays 0 whenever the browser already shrank the layout viewport itself
    // (interactive-widget=resizes-content), so the composer is never pushed up twice.
    '.psa{--psa-kb:0px}',
    '.psa[data-mode=page] .panel{padding-bottom:var(--psa-kb)}',
    '.list{-webkit-overflow-scrolling:touch;overscroll-behavior:contain}',
    '.wl{-webkit-overflow-scrolling:touch;overscroll-behavior:contain}',
    '.composer{padding-left:calc(12px + env(safe-area-inset-left,0px));padding-right:calc(12px + env(safe-area-inset-right,0px))}',
    // floating mode, full screen: the panel owns the visible area, keyboard and notch included
    '@media (max-width:639px){',
    '.panel{height:calc(100dvh - var(--psa-kb))}',
    '.head{padding-top:calc(14px + env(safe-area-inset-top,0px))}',
    '.psa .head{padding-inline-start:max(16px,env(safe-area-inset-left,0px))}',
    '}',
    // ================================================================ phones
    '@media (max-width:559px){',
    // chrome gives its height back to the conversation
    '.psa[data-mode=page] .tabs{padding:2px 14px 0}',
    '.psa[data-mode=page] .tab{padding:6px 8px 10px;font-size:13.5px}',
    '.psa[data-mode=page] .tab[aria-selected=true]::after{inset-inline:6px}',
    '.psa[data-mode=page] .restart-link{font-size:13px;padding:0 4px}',
    '.psa[data-mode=page] .list{padding:14px 16px;gap:14px;overflow-x:hidden}',
    '.psa[data-mode=page] .wl{padding:14px 16px;gap:10px;overflow-x:hidden}',
    '.psa[data-mode=page] .composer{padding-block:10px}',
    '.consent{margin:0 14px 8px;padding:11px 14px}',
    // hero: headline, sub, the one call to action and the starters all fit a 375x667 screen
    '.psa[data-mode=page] .empty-state{gap:12px;padding:0}',
    '.hero-title{font-size:clamp(28px,7.6vw,36px);line-height:1.08;letter-spacing:-.03em;max-width:none}',
    '.hero-sub{font-size:14.5px;line-height:1.5;margin:0;display:-webkit-box;-webkit-line-clamp:3;',
    '-webkit-box-orient:vertical;overflow:hidden}',
    '.start{padding:13px 14px;gap:11px;border-radius:var(--r-3)}',
    '.start .ic{width:40px;height:40px}',
    '.start .ic svg{width:20px;height:20px}',
    '.start b{font-size:15px}',
    '.start small{font-size:12.5px}',
    '.starters-label{margin:2px 0 -2px;font-size:11.5px}',
    '.msg{max-width:92%}',
    '.err{max-width:92%}',
    // guided question: full-width stacked answers, then a thumb-reachable action row
    '.psa[data-mode=page] .card{padding:15px}',
    '.quiz{gap:12px}',
    '.q{font-size:17.5px}',
    '.quiz .chips{display:grid;grid-template-columns:1fr;gap:8px}',
    '.quiz .chip{width:100%;min-height:48px;display:flex;align-items:center;justify-content:flex-start;',
    'text-align:start;padding:11px 16px;line-height:1.3}',
    '.quiz .chip[data-fam]{padding-inline:34px 16px}',
    '.quiz .chip[data-fam]::before{inset-inline-start:14px}',
    '.quiz .row-end{justify-content:stretch;gap:8px;padding-top:11px}',
    '.quiz .row-end .btn{flex:1 1 calc(50% - 4px);min-height:46px;padding-inline:12px}',
    '.quiz .row-end .primary{flex:1 1 100%}',
    // scenario cards on a phone: compact type so two across never truncates a title
    '.scard{min-height:88px;padding:10px 11px}',
    '.scard b{font-size:13.5px;line-height:1.24}',
    '.scard b:lang(ar){line-height:1.36}',
    '.scard small{font-size:12px;line-height:1.34;margin-top:3px}',
    '.scard small:lang(ar){line-height:1.45}',
    '.scard-art{width:28px;height:28px;border-radius:9px}',
    '.scard-art svg{width:24px;height:24px}',
    '.scn.big .scard{padding:12px 14px}',
    // picks: the compact tile card, tightened, with a real tap target on Details
    '.psa[data-mode=page] .picks{gap:14px}',
    '.psa[data-mode=page] .pick{padding:12px}',
    '.psa[data-mode=page] .media.portrait{grid-row:1}',
    '.psa[data-mode=page] .ptop{align-self:center}',
    '.psa[data-mode=page] .more{min-height:44px;display:inline-flex;align-items:center;padding:0 2px}',
    '.psa[data-mode=page] .meta{gap:4px 10px}',
    '.psa[data-mode=page] .actions{gap:4px;flex-wrap:nowrap}',
    '.psa[data-mode=page] .actions .btn{flex:1 1 auto;min-width:0;padding-inline:12px}',
    '.brandrow{gap:4px 6px}',
    '.fampill{max-width:100%;overflow:hidden}',
    '.wlitem{flex-wrap:wrap;gap:10px 12px}',
    '.wlitem .info{flex:1 1 0;min-width:0}',
    '.wlitem .link{flex:1 1 100%;margin-inline-start:0;justify-content:center;min-height:44px;',
    'border:1px solid var(--border-2);border-radius:999px;color:var(--brand-2)}',
    '.empty{margin:24px auto}',
    '}',
    // ---- rows that would otherwise wrap into ragged stacks scroll sideways instead, with snap
    // (phones, and landscape phones where height is the scarce axis)
    '@media (max-width:559px),(max-height:500px) and (orientation:landscape){',
    '.starters{display:flex;flex-wrap:nowrap;overflow-x:auto;gap:8px;scroll-snap-type:x proximity;',
    'overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch;scrollbar-width:none;',
    'margin-inline:-16px;padding-inline:16px;padding-block:2px;scroll-padding-inline:16px}',
    '.starters::-webkit-scrollbar{display:none}',
    '.starter{flex:0 0 auto;scroll-snap-align:start;max-width:none;min-height:46px;white-space:nowrap;',
    'padding-inline:34px 16px;padding-block:11px;border-radius:999px;font-size:14px}',
    '.starter::before{inset-inline-start:14px;width:9px;height:9px;margin-top:-4.5px;',
    'box-shadow:0 0 0 3px color-mix(in srgb,var(--fam) 20%,transparent)}',
    '.pick .tags,.tags.learned{flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-x:contain;',
    'scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch;scrollbar-width:none;padding-block:2px}',
    '.pick .tags::-webkit-scrollbar,.tags.learned::-webkit-scrollbar{display:none}',
    '.pick .tag,.tags.learned .tag{flex:0 0 auto;scroll-snap-align:start;white-space:nowrap}',
    '.refine .chips{flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:none;',
    'scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch;margin-inline:-16px;padding-inline:16px;',
    'padding-block:2px;scroll-padding-inline:16px}',
    '.refine .chips::-webkit-scrollbar{display:none}',
    '.refine .chip{flex:0 0 auto;scroll-snap-align:start;white-space:nowrap}',
    '}',
    // ---- small phones: the photo tile gives width back to the name and the match ring
    '@media (max-width:360px){',
    '.psa[data-mode=page] .pick{grid-template-columns:92px 1fr;column-gap:10px}',
    '.psa[data-mode=page] .media.portrait{width:92px;height:116px;max-height:116px}',
    '.psa[data-mode=page] .ptop{gap:7px}',
    '.psa[data-mode=page] .ptop .rank{font-size:19px}',
    '.psa[data-mode=page] .ptop .score{width:36px;height:36px;padding-top:12px}',
    '.psa[data-mode=page] .ptop .score b{font-size:12px}',
    '.psa[data-mode=page] .ptop .score i{font-size:8.5px}',
    '.psa[data-mode=page] .ptop .name{font-size:15px}',
    '.psa[data-mode=page] .list,.psa[data-mode=page] .wl{padding-inline:14px}',
    '.starters,.refine .chips{margin-inline:-14px;padding-inline:14px;scroll-padding-inline:14px}',
    '.hero-title{font-size:clamp(25px,7.6vw,30px)}',
    '.psa[data-mode=page] .actions .btn{padding-inline:8px}',
    '}',
    // ---- landscape phones: hide the decoration, clamp the prose, keep composer + conversation usable
    '@media (max-height:500px) and (orientation:landscape){',
    '.spectrum{display:none}',
    '.psa[data-mode=page] .empty-state:only-child{flex:none;justify-content:flex-start}',
    '.psa[data-mode=page] .empty-state{gap:9px;padding:0}',
    '.psa[data-mode=page] .list{padding-block:8px;gap:8px}',
    '.psa[data-mode=page] .tabs{padding-block:0}',
    '.psa[data-mode=page] .tab{padding:5px 8px 8px}',
    '.psa[data-mode=page] .composer{padding-block:8px}',
    '.hero-title{font-size:clamp(24px,4.4vw,32px);line-height:1.06;max-width:none}',
    '.hero-sub{font-size:14px;margin:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}',
    '.start{padding:8px 14px}',
    '.start .ic{width:36px;height:36px}',
    '.start small{display:none}',
    '.starters-label{display:none}',
    '}',
    // ---- large phones / small tablets: two columns beats one stretched card per row
    '@media (min-width:560px) and (max-width:759px){',
    '.psa[data-mode=page] .picks{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:stretch}',
    '}',
    // ---- every control clears 44px on a touch screen, at any width
    '@media (pointer:coarse){',
    '.consent .btn{min-height:44px;padding:6px 20px}',
    '.langbtn{height:44px}',
    '.link{min-height:44px;align-items:center}',
    '.psa[data-mode=page] .more{min-height:44px;display:inline-flex;align-items:center}',
    '.wlitem .link{justify-content:center}',
    '}',
    // ---- motion is a courtesy, never a toll
    '@media (prefers-reduced-motion:reduce){.psa *,.psa *::before,.psa *::after{',
    'animation-duration:1ms!important;animation-iteration-count:1!important;transition-duration:1ms!important;scroll-behavior:auto!important}',
    '.panel::before,.media.ld::after{animation:none!important}.psa .scard{animation-delay:0s!important}}'
  ].join('\n');

  // ---------------------------------------------------------------- shell
  var host = document.createElement('div');
  host.id = 'psa-widget-host';
  if (MODE === 'page') { host.style.display = 'block'; host.style.width = '100%'; host.style.height = '100%'; host.style.minHeight = '0'; }
  var root = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host;
  var styleEl = document.createElement('style');
  styleEl.textContent = CSS;
  root.appendChild(styleEl);

  var R = {}; // refs
  R.app = h('div', { class: 'psa', 'data-mode': MODE });
  R.launcher = h('button', { class: 'launcher', type: 'button', onclick: function () { openPanel(); } }, [
    h('span', { icon: 'bottle' }), R.launcherLabel = h('span')
  ]);
  R.title = h('h2', { class: 'title', id: 'psa-title' });
  R.subtitle = h('p', { class: 'subtitle' });
  R.langBtn = h('button', { class: 'langbtn', type: 'button', onclick: function () { setLang(S.lang === 'ar' ? 'en' : 'ar'); } });
  R.restartBtn = h('button', { class: 'iconbtn restart', type: 'button', icon: 'restart', onclick: startOver });
  R.closeBtn = h('button', { class: 'iconbtn close', type: 'button', icon: 'close', onclick: function () { closePanel(); } });
  R.tabChat = h('button', { class: 'tab', type: 'button', role: 'tab', onclick: function () { setTab('chat'); } });
  R.tabWish = h('button', { class: 'tab', type: 'button', role: 'tab', onclick: function () { setTab('wishlist'); } });
  R.pageRestart = h('button', { class: 'restart-link', type: 'button', onclick: startOver });
  R.list = h('div', { class: 'list', role: 'log', 'aria-live': 'polite' });
  R.wl = h('div', { class: 'wl', hidden: true });
  R.consentText = h('span');
  R.consentYes = h('button', { class: 'btn primary', type: 'button', onclick: function () { answerConsent(true); } });
  R.consentNo = h('button', { class: 'btn ghost', type: 'button', onclick: function () { answerConsent(false); } });
  R.consent = h('div', { class: 'consent', role: 'alertdialog', hidden: true }, [R.consentText, R.consentYes, R.consentNo]);
  R.input = h('input', { class: 'input', type: 'text', autocomplete: 'off', enterkeyhint: 'send', maxlength: '500' });
  R.send = h('button', { class: 'send', type: 'submit', icon: 'send' });
  R.composer = h('form', { class: 'composer', onsubmit: function (ev) { ev.preventDefault(); sendTyped(); } }, [R.input, R.send]);
  R.panel = h('section', { class: 'panel', role: MODE === 'page' ? 'region' : 'dialog', 'aria-labelledby': MODE === 'page' ? null : 'psa-title', hidden: true }, [
    h('header', { class: 'head' }, [
      h('div', { class: 'mark', icon: 'bottle' }),
      h('div', { class: 'titles' }, [R.title, R.subtitle]),
      R.langBtn, R.restartBtn, R.closeBtn
    ]),
    h('div', { class: 'tabs', role: 'tablist' }, [R.tabChat, R.tabWish, R.pageRestart]),
    h('div', { class: 'body' }, [R.list, R.wl, R.consent, R.composer])
  ]);
  add(R.app, [R.launcher, R.panel]);
  root.appendChild(R.app);

  R.input.addEventListener('input', syncSend);

  // ---------------------------------------------------------------- dynamic viewport + on-screen keyboard
  // A phone moves the goalposts twice: browser toolbars slide in and out, and the keyboard covers the
  // bottom of the visible area. --psa-kb is how much is covered *right now*, measured rather than guessed.
  // It stays 0 when the browser already shrank the layout viewport itself (interactive-widget=
  // resizes-content), so the composer is never lifted twice.
  var vv = window.visualViewport || null;
  var kbRaf = 0;
  function syncViewport() {
    kbRaf = 0;
    var inset = vv ? Math.round(window.innerHeight - vv.height - vv.offsetTop) : 0;
    if (!(inset > 24)) inset = 0;   // below that it is toolbar jitter, not a keyboard
    R.app.style.setProperty('--psa-kb', inset + 'px');
    // page mode owns the whole document, so the host page's own layout can follow the keyboard too
    if (S.mode === 'page') {
      try { document.documentElement.style.setProperty('--psa-kb', inset + 'px'); } catch (e) {}
    }
  }
  function queueViewportSync() { if (!kbRaf) kbRaf = requestAnimationFrame(syncViewport); }
  if (vv) {
    vv.addEventListener('resize', queueViewportSync);
    vv.addEventListener('scroll', queueViewportSync);
  }
  window.addEventListener('resize', queueViewportSync);
  window.addEventListener('orientationchange', function () { setTimeout(syncViewport, 250); });
  // Page mode owns the whole screen: the document itself never scrolls (only the conversation does). Phone
  // browsers can still nudge it when focus moves or the keyboard closes, which would push the top bar away.
  if (S.mode === 'page') {
    window.addEventListener('scroll', function () {
      if (window.scrollY || window.pageYOffset) { try { window.scrollTo(0, 0); } catch (e) {} }
    }, { passive: true });
  }
  syncViewport();

  // Focusing the composer: bring the newest message back above the keyboard once it has finished animating.
  R.input.addEventListener('focus', function () {
    queueViewportSync();
    setTimeout(function () {
      syncViewport();
      var last = R.list.lastElementChild;
      if (last && !R.list.hidden) scrollTo(last);
      // the pinned composer must not be scrolled away with the page in full-page mode
      if (S.mode === 'page' && window.scrollY) { try { window.scrollTo(0, 0); } catch (e) {} }
    }, 320);
  });

  // Phone-sized copy: a placeholder that fits the field, starter chips that fit one scrolling row.
  var NARROW = window.matchMedia ? window.matchMedia('(max-width:559px),(max-height:500px) and (orientation:landscape)') : null;
  function narrow() { return !!(NARROW && NARROW.matches); }
  if (NARROW) {
    var onNarrow = function () {
      renderChrome();
      S.entries.forEach(function (e) { if (e.k === 'start') refresh(e); });
    };
    if (NARROW.addEventListener) NARROW.addEventListener('change', onNarrow);
    else if (NARROW.addListener) NARROW.addListener(onNarrow);
  }

  R.panel.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && S.mode !== 'page') closePanel();
    if (ev.key === '/' && !ev.metaKey && !ev.ctrlKey && !ev.altKey) {
      var tgt = ev.target, tag = tgt && tgt.tagName;
      var inTextField = tag === 'INPUT' || tag === 'TEXTAREA' || (tgt && tgt.isContentEditable);
      if (!inTextField) { ev.preventDefault(); focusInput(); }
    }
  });

  function renderChrome() {
    R.app.setAttribute('lang', S.lang);
    R.app.setAttribute('dir', S.lang === 'ar' ? 'rtl' : 'ltr');
    R.launcherLabel.textContent = t('launcher');
    R.launcher.setAttribute('aria-label', t('openLabel'));
    R.title.textContent = t('title');
    var brand = (S.session && S.session.brand_filter) || BRAND;
    R.subtitle.textContent = brand ? t('brandSubtitle', { brand: brand }) : t('subtitle');
    R.langBtn.textContent = t('langToggle');
    R.langBtn.setAttribute('lang', S.lang === 'ar' ? 'en' : 'ar');
    R.langBtn.setAttribute('aria-label', t('langToggleLabel'));
    R.restartBtn.setAttribute('aria-label', t('startOver'));
    R.restartBtn.setAttribute('title', t('startOver'));
    R.pageRestart.textContent = t('startOver');
    R.closeBtn.setAttribute('aria-label', t('close'));
    R.tabChat.textContent = t('tabChat');
    R.tabWish.textContent = t('tabWishlist', { n: S.wishlist.length });
    R.tabChat.setAttribute('aria-selected', String(S.tab === 'chat'));
    R.tabWish.setAttribute('aria-selected', String(S.tab === 'wishlist'));
    R.consentText.textContent = t('consent');
    R.consentYes.textContent = t('yes');
    R.consentNo.textContent = t('no');
    // narrow screens get the short placeholder so nothing is clipped; the label stays the full sentence
    R.input.setAttribute('placeholder', t(narrow() ? 'placeholderShort' : 'placeholder'));
    R.input.setAttribute('aria-label', t('placeholder'));
    R.send.setAttribute('aria-label', t('send'));
    if (S.mode === 'page') R.panel.setAttribute('aria-label', t('title'));
    syncSend();
  }

  function syncSend() { R.send.disabled = S.busy || !R.input.value.trim(); }

  // ---------------------------------------------------------------- transcript
  function push(e) {
    e.id = ++S.seq;
    S.entries.push(e);
    e.el = renderEntry(e);
    // Entrances are for arrivals only: a re-render (refresh) must not replay the fade-and-rise.
    if (e.el.classList) e.el.classList.add('psa-in');
    R.list.appendChild(e.el);
    scrollTo(e.el);
    persistConversation();
    return e;
  }
  function refresh(e) {
    if (!e.el || !e.el.parentNode) return;
    var n = renderEntry(e);
    e.el.parentNode.replaceChild(n, e.el);
    e.el = n;
    persistConversation();
  }
  function removeEntry(e) {
    var i = S.entries.indexOf(e);
    if (i >= 0) S.entries.splice(i, 1);
    if (e.el && e.el.parentNode) e.el.parentNode.removeChild(e.el);
    persistConversation();
  }

  // ---------------------------------------------------------------- conversation persistence (sessionStorage)
  // Survives refresh/back (not tab close, not other tabs -- deliberate: sessionStorage, not localStorage).
  // Only plain, JSON-safe data is stored; restored entries render through the exact same renderEntry() path
  // as live ones, so they get the same textContent-only DOM construction and the same live event handlers.
  var CONV_MAX = 30;
  var CONV_KINDS = { start: 1, user: 1, bot: 1, results: 1, guided: 1 };
  function convKey() { return S.sessionId ? 'psa_conv_' + S.sessionId : null; }
  function persistConversation() {
    var key = convKey();
    if (!key) return;
    try {
      var slim = S.entries.filter(function (e) { return CONV_KINDS[e.k]; }).slice(-CONV_MAX).map(function (e) {
        switch (e.k) {
          case 'start': return { k: 'start', chosen: e.chosen || null };
          case 'user': return { k: 'user', text: e.text };
          case 'bot': return { k: 'bot', text: e.text || null, i18n: e.i18n || null, fallback: !!e.fallback, quick: e.quick || null, mode: e.mode || null, used: !!e.used };
          case 'results': return { k: 'results', reply: e.reply, stale: !!e.stale, open: e.open || null };
          case 'guided': return { k: 'guided', question: e.question, sel: e.sel || [] };
        }
      });
      window.sessionStorage.setItem(key, JSON.stringify(slim));
    } catch (err) { /* storage blocked or over quota: run without persistence */ }
  }
  function clearPersistedConversation() {
    var key = convKey();
    if (!key) return;
    try { window.sessionStorage.removeItem(key); } catch (err) { /* ignore */ }
  }
  // Returns true if at least one entry was restored (caller should then skip pushing a fresh 'start' entry).
  function restoreConversation() {
    var key = convKey();
    if (!key) return false;
    var saved;
    try {
      var raw = window.sessionStorage.getItem(key);
      saved = raw ? JSON.parse(raw) : null;
    } catch (err) { return false; }
    if (!Array.isArray(saved) || !saved.length) return false;
    saved.forEach(function (e) {
      if (!e || !CONV_KINDS[e.k]) return;
      e.id = ++S.seq;
      e.el = renderEntry(e);
      R.list.appendChild(e.el);
      S.entries.push(e);
    });
    syncCards();
    return S.entries.length > 0;
  }
  function rerenderAll() { S.entries.forEach(refresh); syncCards(); }
  // Short entries: stick to the bottom. Tall entries (results): show their top.
  function scrollTo(el, top) {
    var list = R.list;
    requestAnimationFrame(function () {
      if (!el.parentNode) return;
      if (top || el.offsetHeight > list.clientHeight - 24) list.scrollTop = Math.max(0, el.offsetTop - 12);
      else list.scrollTop = list.scrollHeight;
    });
  }

  function renderEntry(e) {
    switch (e.k) {
      case 'user': return h('p', { class: 'msg user' }, e.text);
      case 'bot': return renderBot(e);
      case 'start': return renderStart(e);
      case 'guided': return renderGuided(e);
      case 'results': return renderResults(e);
      case 'error': return renderError(e);
      case 'typing': return h('div', { class: 'typing', role: 'status' }, e.label ? [
        h('span', { class: 'dot' }), h('span', { class: 'dot' }), h('span', { class: 'dot' }), h('span', { class: 'typing-label' }, e.label)
      ] : [
        h('span', { class: 'dot' }), h('span', { class: 'dot' }), h('span', { class: 'dot' }), h('span', { class: 'sr', text: t('typing') })
      ]);
    }
    return h('div');
  }

  function renderBot(e) {
    var kids = [];
    var text = e.i18n ? t(e.i18n) : e.text;
    if (text) kids.push(h('p', { class: 'msg bot' }, text));
    if (e.fallback) kids.push(fallbackNote());
    if (e.quick && e.quick.length && !e.used) {
      kids.push(h('div', { class: 'chips' }, e.quick.map(function (c) {
        return h('button', { class: 'chip', type: 'button', disabled: S.busy, onclick: function () { onQuick(e, c); } }, c.label || c.id);
      })));
    }
    return h('div', { class: 'wrap' }, kids);
  }

  function fallbackNote() { return h('p', { class: 'note' }, [h('span', { icon: 'info' }), t('fallbackNote')]); }

  var STARTERS = ['starter1', 'starter2', 'starter3', 'starter4'];
  // if a starter's own words do not land on the spectrum, these keep each dot distinct and sensible
  var STARTER_FAM = ['fresh', 'aquatic', 'woody', 'floral'];

  function renderStart(e) {
    if (S.mode === 'page') {
      if (e.chosen) return h('div');
      return h('div', { class: 'wrap empty-state' }, [
        h('h1', { class: 'hero-title' }, [
          t('heroTitleLead'),
          h('span', { class: 'hero-em' }, t('heroTitleEm'))
        ]),
        h('p', { class: 'hero-sub' }, t('heroSub')),
        h('div', { class: 'spectrum', icon: 'spectrum', 'aria-hidden': 'true' }),
        h('button', { class: 'start', type: 'button', 'data-start': 'guided', onclick: startGuided }, [
          h('span', { class: 'ic', icon: 'quiz' }),
          h('span', null, [h('b', null, t('startQuiz')), h('small', null, t('startQuizSub'))]),
          h('span', { class: 'go', icon: 'send', 'aria-hidden': 'true' })
        ]),
        h('p', { class: 'starters-label' }, t('tryAsking')),
        h('div', { class: 'starters' }, STARTERS.map(function (key, i) {
          // The chip is labelled for the space it has; the full prompt is always what gets sent.
          var text = t(key), label = narrow() ? t(key + 'Short') : text;
          return h('button', {
            class: 'starter', type: 'button', 'data-fam': textFamily(text) || STARTER_FAM[i],
            title: label === text ? null : text,
            onclick: function () { sendChat(text, 'starter'); }
          }, label);
        }))
      ]);
    }
    var greeting = (S.session && S.session.greeting) || t('greeting');
    var kids = [h('p', { class: 'msg bot' }, greeting)];
    if (!e.chosen) {
      kids.push(h('div', { class: 'starts' }, [
        h('button', { class: 'start', type: 'button', 'data-start': 'guided', onclick: startGuided }, [
          h('span', { class: 'ic', icon: 'quiz' }),
          h('span', null, [h('b', null, t('startQuiz')), h('small', null, t('startQuizSub'))]),
          h('span', { class: 'go', icon: 'send', 'aria-hidden': 'true' })
        ]),
        h('button', { class: 'start', type: 'button', 'data-start': 'chat', onclick: startChat }, [
          h('span', { class: 'ic', icon: 'chat' }),
          h('span', null, [h('b', null, t('startChat')), h('small', null, t('startChatSub'))]),
          h('span', { class: 'go', icon: 'send', 'aria-hidden': 'true' })
        ])
      ]));
    }
    return h('div', { class: 'wrap' }, kids);
  }

  // ---------------------------------------------------------------- guided match
  // One AI-authored question per turn (server: POST /api/guide/start then POST /api/chat), each with its own
  // tappable quick replies. A "guided" entry always holds the *current* question; the server enforces the
  // 5-question cap and decides when to stop early, so the client just renders whatever it is sent.
  function startGuided() {
    if (S.busy) return;
    markStart('guided');
    track('guided_started', {});
    request('/api/guide/start', function () { return { session_id: S.sessionId, lang: S.lang }; }, t('guidedThinking'));
  }

  var SCENARIO_MAX = 3;
  function isScenarioQuestion(q) {
    return (q.topic === 'scenario' || q.topic === 'scenario_moment') &&
      (q.options || []).some(function (c) { return c.motif || c.caption; });
  }

  function renderGuided(e) {
    var q = e.question, sel = e.sel || [], multi = !!q.multi;
    var i = q.index || 1, n = q.max_index || 5;
    var cards = isScenarioQuestion(q);
    var kids = [
      h('div', { class: 'progress' }, [
        h('span', null, t('quizProgress', { i: i, n: n })),
        h('span', { class: 'bar' }, h('i', { style: 'width:' + Math.round(i / n * 100) + '%' }))
      ]),
      h('p', { class: 'q' }, q.question)
    ];
    if (q.ask_reason) kids.push(h('p', { class: 'note' }, [h('span', { icon: 'info' }), q.ask_reason]));
    if (cards) kids.push(renderScenarioCards(e));
    else kids.push(h('div', { class: 'chips', role: 'group', 'aria-label': q.question }, (q.options || []).map(function (c) {
      // an answer that names a note, an accord or a mood wears that family's colour
      var fam = textFamily(c.id) || textFamily(c.label);
      if (multi) {
        return h('button', {
          class: 'chip', type: 'button', 'data-id': c.id, 'data-fam': fam || null,
          'aria-pressed': String(sel.indexOf(c.id) >= 0), disabled: S.busy,
          onclick: function () { toggleGuidedChip(e, c.id); }
        }, c.label || c.id);
      }
      return h('button', {
        class: 'chip', type: 'button', 'data-id': c.id, 'data-fam': fam || null, disabled: S.busy,
        onclick: function () { sendGuidedAnswer(e, [c]); }
      }, c.label || c.id);
    })));
    var actions = [];
    if (multi) {
      // the scenario grid counts what is chosen, so the shopper sees the pick before sending it
      var label = cards && sel.length ? t('scenarioContinue', { n: sel.length }) : t('guidedContinue');
      actions.push(h('button', {
        class: 'btn primary', type: 'button', 'data-continue': '', disabled: S.busy || !sel.length,
        onclick: function () { sendGuidedAnswer(e, (q.options || []).filter(function (c) { return sel.indexOf(c.id) >= 0; })); }
      }, label));
    }
    actions.push(h('button', { class: 'btn ghost', type: 'button', disabled: S.busy, onclick: function () { skipGuided(e); } }, t('guidedSkip')));
    if (i >= 2) {
      actions.push(h('button', { class: 'btn ghost', type: 'button', disabled: S.busy, onclick: showGuidedPicksNow }, t('guidedShowPicks')));
    }
    kids.push(h('div', { class: 'row-end' }, actions));
    return h('div', { class: 'card quiz' + (cards ? ' scn-q' : ''), 'data-guided-id': q.id }, kids);
  }

  // Scenario and moment cards: title, sub-caption and a motif in the card's family colour. Every string goes in
  // as text; the motif comes from the static MOTIFS table by whitelisted key, the colour from the family list.
  function renderScenarioCards(e) {
    var q = e.question, sel = e.sel || [], multi = !!q.multi;
    var big = q.topic === 'scenario_moment';
    var full = multi && sel.length >= SCENARIO_MAX;
    var items = (q.options || []).map(function (c, idx) {
      var fam = FAMILIES.indexOf(c.family) >= 0 ? c.family : (textFamily(c.id) || textFamily(c.label) || null);
      var art = h('span', { class: 'scard-art', 'aria-hidden': 'true' });
      if (c.motif && Object.prototype.hasOwnProperty.call(MOTIFS, c.motif)) art.innerHTML = MOTIFS[c.motif];
      var on = sel.indexOf(c.id) >= 0;
      var blocked = full && !on;
      return h('button', {
        class: 'scard', type: 'button', 'data-id': c.id, 'data-fam': fam, style: '--i:' + idx,
        'aria-pressed': multi ? String(on) : null, 'aria-disabled': blocked ? 'true' : null, disabled: S.busy,
        onclick: function () {
          if (multi) { if (!blocked) toggleGuidedChip(e, c.id); }
          else sendGuidedAnswer(e, [c]);
        }
      }, [
        art,
        h('span', { class: 'scard-txt' }, [h('b', null, c.label || c.id), c.caption ? h('small', null, c.caption) : null]),
        multi ? h('span', { class: 'scard-check', 'aria-hidden': 'true', icon: 'check' }) : null
      ]);
    });
    if (big) {
      // "Something else": the shopper describes their own moment in the composer; the server reads it as the
      // answer to this question.
      items.push(h('button', {
        class: 'scard other', type: 'button', 'data-other': '', style: '--i:' + items.length, disabled: S.busy,
        onclick: function () { describeOwnMoment(); }
      }, [
        h('span', { class: 'scard-art', 'aria-hidden': 'true', icon: 'pencil' }),
        h('span', { class: 'scard-txt' }, [h('b', null, t('somethingElse')), h('small', null, t('somethingElseSub'))])
      ]));
    }
    return h('div', { class: 'scn' + (big ? ' big' : ''), role: 'group', 'aria-label': q.question }, items);
  }

  function describeOwnMoment() {
    if (S.busy) return;
    track('guided_something_else', {});
    R.input.setAttribute('placeholder', t('placeholderMoment'));
    focusInput();
  }

  function toggleGuidedChip(e, id) {
    var sel = (e.sel || []).slice(), at = sel.indexOf(id);
    if (at >= 0) sel.splice(at, 1); else sel.push(id);
    e.sel = sel;
    // a re-render replaces the buttons: keep keyboard focus on the one just toggled
    var root0 = R.app.getRootNode ? R.app.getRootNode() : document;
    var hadFocus = e.el && root0.activeElement && e.el.contains(root0.activeElement);
    refresh(e);
    if (hadFocus && e.el) {
      var nodes = e.el.querySelectorAll('[data-id]');
      for (var k = 0; k < nodes.length; k++) if (nodes[k].getAttribute('data-id') === id) { nodes[k].focus({ preventScroll: true }); break; }
    }
  }

  function sendGuidedAnswer(e, chosen) {
    if (S.busy || !chosen.length) return;
    var labels = chosen.map(function (c) { return c.label || c.id; }).join(', ');
    removeEntry(e);
    push({ k: 'user', text: labels });
    track('guided_answer', { index: (e.question || {}).index, count: chosen.length });
    request('/api/chat', function () { return { session_id: S.sessionId, message: labels, lang: S.lang }; }, t('guidedThinking'));
  }

  function skipGuided(e) {
    if (S.busy) return;
    var label = t('guidedSkip');
    removeEntry(e);
    push({ k: 'user', text: label });
    track('guided_skip', { index: (e.question || {}).index });
    request('/api/chat', function () { return { session_id: S.sessionId, message: label, lang: S.lang }; }, t('guidedThinking'));
  }

  function showGuidedPicksNow() {
    if (S.busy) return;
    abandonGuided();
    track('guided_show_picks_now', {});
    request('/api/guide/finish', function () { return { session_id: S.sessionId, lang: S.lang }; }, t('typing'));
  }

  function abandonGuided() {
    S.entries.slice().forEach(function (e) { if (e.k === 'guided') removeEntry(e); });
  }

  // ---------------------------------------------------------------- chat
  function startChat() {
    if (S.busy) return;
    markStart('chat');
    push({ k: 'bot', i18n: 'chatPrompt' });
    focusInput();
    ensureSession().catch(function () {});
  }

  function markStart(how) {
    S.entries.slice().forEach(function (e) {
      if (e.k !== 'start' || e.chosen) return;
      e.chosen = how;
      // page mode: drop the hero entirely (rather than re-rendering it empty) so it disappears in the same
      // synchronous step as the first message is queued -- no orphan flex:1 div, no jump from centered to top.
      if (S.mode === 'page') removeEntry(e);
      else refresh(e);
    });
  }

  function sendTyped() {
    var text = R.input.value.trim();
    if (!text || S.busy) return;
    R.input.value = '';
    syncSend();
    sendChat(text, 'typed');
  }

  function sendChat(text, source) {
    R.input.setAttribute('placeholder', t(narrow() ? 'placeholderShort' : 'placeholder'));
    markStart('chat');
    abandonGuided();
    push({ k: 'user', text: text });
    track('chat_message_sent', { source: source, length: text.length });
    request('/api/chat', function () { return { session_id: S.sessionId, message: text, lang: S.lang }; });
  }

  function onQuick(e, chip) {
    if (S.busy) return;
    e.used = true;
    refresh(e);
    if (e.mode === 'refine' && REFINE_RE.test(chip.id)) refine(chip);
    else sendChat(chip.label || chip.id, 'quick_reply');
  }

  function refine(chip) {
    if (S.busy) return;
    push({ k: 'user', text: chip.label || chip.id });
    track('refine_used', { chip: chip.id });
    request('/api/refine', function () { return { session_id: S.sessionId, chip: chip.id, lang: S.lang }; });
  }

  // ---------------------------------------------------------------- requests
  var typingEntry = null;
  function setBusy(b, label) {
    S.busy = b;
    syncSend();
    var nodes = R.list.querySelectorAll('.chip,.scard,.btn,.start,.starter');
    for (var i = 0; i < nodes.length; i++) nodes[i].disabled = b;
    if (b && !typingEntry) typingEntry = push({ k: 'typing', label: label || null });
    if (!b && typingEntry) { removeEntry(typingEntry); typingEntry = null; }
  }

  function withSession(fn, retry) {
    if (S.session) { fn(); return; }
    setBusy(true);
    ensureSession().then(function () { setBusy(false); fn(); }, function (err) { setBusy(false); showError(err, retry); });
  }

  function request(path, bodyFn, typingLabel) {
    if (S.busy) return;
    setBusy(true, typingLabel);
    ensureSession()
      .then(function () { return api('POST', path, bodyFn()); })
      .then(function (reply) { setBusy(false); handleReply(reply, path); },
        function (err) { setBusy(false); showError(err, function () { request(path, bodyFn, typingLabel); }); });
  }

  function handleReply(r, path) {
    var picks = (r && r.picks) || [];
    var hasPicks = picks.length > 0;
    if (r.guided && !hasPicks && r.next_question) {
      // Guided match: the AI-authored question gets its own card (progress, quick replies, skip, show-picks-
      // now) instead of a chat bubble -- see renderGuided().
      push({ k: 'guided', question: r.next_question, sel: [] });
      track('guided_question_shown', { index: r.next_question.index, max: r.next_question.max_index, multi: !!r.next_question.multi });
      maybeRefocusComposer();
      return;
    }
    var bot = { k: 'bot', text: plain(r.reply), fallback: !!r.fallback_used && !hasPicks };
    if (r.next_question && r.next_question.options && r.next_question.options.length) {
      // Ordinary chat clarifying question: same idea as guided match's quick replies, but rendered inline
      // as tappable chips under the bot's message (PRD: "the same quick answers appear in normal chat").
      var q = plain(r.next_question.question);
      if (q && bot.text.indexOf(q) < 0) bot.text = bot.text ? bot.text + '\n\n' + q : q;
      bot.quick = r.next_question.options;
      bot.mode = 'send';
    } else if (!hasPicks && r.chips && r.chips.length) {
      bot.quick = r.chips;
      bot.mode = 'refine';
    }
    var botShown = !!(bot.text || bot.quick || bot.fallback);
    if (botShown) push(bot);
    if (hasPicks) {
      S.entries.forEach(function (e) { if (e.k === 'results' && !e.stale) { e.stale = true; refresh(e); } });
      var res = push({ k: 'results', reply: r });
      syncCards();
      track('results_shown', { source: path, count: Math.min(picks.length, 3), intent: r.intent || '', has_layering: !!r.layering, perfume_ids: picks.slice(0, 3).map(function (p) { return p.perfume_id; }) });
      scrollTo(botShown ? bot.el : res.el, true);
    }
    if (r.fallback_used) track('fallback_used', { source: path });
    maybeRefocusComposer();
  }

  // Page mode, fine-pointer devices only (never steals the on-screen keyboard on touch): once a reply has
  // finished rendering, return focus to the composer so a keyboard user isn't left stranded on the old typing
  // indicator's position -- unless they've already moved focus somewhere deliberate (e.g. tabbed into a pick).
  function maybeRefocusComposer() {
    if (S.mode !== 'page') return;
    if (!window.matchMedia || !window.matchMedia('(pointer:fine)').matches) return;
    var active = root.activeElement;
    var neutral = !active || active === document.body || active === R.panel || active === R.input;
    if (!neutral) return;
    focusInput();
  }

  function showError(err, retry) {
    var key = err && err.status === 0 ? 'errorNetwork' : err && (err.status === 429 || err.status === 503) ? 'errorBusy' : 'error';
    if (window.console && console.warn) console.warn('[perfume-widget]', err && err.path, err && err.status, err && err.message);
    push({ k: 'error', key: key, retry: retry });
    track('error_shown', { endpoint: (err && err.path) || '', status: err ? err.status : null });
  }

  function renderError(e) {
    return h('div', { class: 'err', role: 'alert' }, [
      h('span', null, t(e.key)),
      e.retry ? h('div', { class: 'chips' }, h('button', {
        class: 'chip', type: 'button', 'data-retry': '', disabled: S.busy,
        onclick: function () { if (S.busy) return; removeEntry(e); e.retry(); }
      }, t('tryAgain'))) : null
    ]);
  }

  // ---------------------------------------------------------------- results
  // variant: '' (64px inline), 'sm' (44px row icon), 'portrait' (full-width product tile, 3:4, object-fit:contain)
  // The family-tinted stage. Product shots arrive on white, so the image multiplies onto the colour field and
  // the white disappears into the tint. The tile shimmers while the photo is still travelling.
  function media(card, variant) {
    var box = h('div', { class: 'media' + (variant ? ' ' + variant : ''), 'data-fam': famAttr(card) });
    var settle = function () { box.classList.remove('ld'); };
    var ph = function () { settle(); return h('div', { class: 'ph', 'aria-hidden': 'true' }, initials(card.name)); };
    var primarySrc = safeUrl(card.image_url);
    var fallbackSrc = card.perfume_id ? API + '/api/image/' + encodeURIComponent(card.perfume_id) : null;
    var src = primarySrc || fallbackSrc;
    if (src) {
      var triedFallback = !primarySrc;
      var img = h('img', { alt: '', loading: 'lazy', decoding: 'async', referrerpolicy: 'no-referrer' });
      img.addEventListener('load', settle);
      img.addEventListener('error', function () {
        if (!triedFallback && fallbackSrc) { triedFallback = true; img.src = fallbackSrc; return; }
        if (img.parentNode) img.parentNode.replaceChild(ph(), img);
      });
      box.classList.add('ld');
      img.src = src;
      if (img.complete && img.naturalWidth) settle();
      box.appendChild(img);
    } else box.appendChild(ph());
    return box;
  }

  function priceNode(card) {
    var label = card.price_label || (card.price_aed != null ? 'AED ' + Math.round(card.price_aed) : '');
    if (!label) return h('span', { class: 'price' }, t('noPrice'));
    if (card.price_source === 'estimated') return h('span', { class: 'price est', title: t('estTooltip'), tabindex: '0', 'aria-label': label + ' (' + t('estTooltip') + ')' }, label);
    return h('span', { class: 'price' }, label);
  }

  function renderPick(card, rank, entry) {
    var pid = card.perfume_id;
    var url = safeUrl(card.product_url);
    var keyNotes = (card.key_notes && card.key_notes.length ? card.key_notes : [].concat(card.notes && card.notes.top || [], card.notes && card.notes.heart || [])).slice(0, 4);
    var expanded = entry.open && entry.open[pid];
    var meta = [priceNode(card)];
    if (card.strength_label) meta.push(h('span', { class: 'dot-sep', 'aria-hidden': 'true' }), h('span', null, card.strength_label));
    meta.push(h('button', {
      class: 'more', type: 'button', 'aria-expanded': String(!!expanded), onclick: function () {
        entry.open = entry.open || {};
        entry.open[pid] = !entry.open[pid];
        if (entry.open[pid]) track('pick_clicked', { perfume_id: pid, rank: rank, action: 'details' });
        var y = R.list.scrollTop; refresh(entry); syncCards(); R.list.scrollTop = y;
      }
    }, expanded ? t('lessDetails') : t('details')));

    var detail = null;
    if (expanded) {
      var n = card.notes || {};
      var row = function (lab, arr) { return arr && arr.length ? h('p', null, [h('b', null, lab + ': '), arr.join(', ')]) : null; };
      detail = h('div', { class: 'detail' }, [
        row(t('notesTop'), n.top), row(t('notesHeart'), n.heart), row(t('notesBase'), n.base),
        card.description ? h('p', null, card.description) : null
      ]);
    }

    var pct = card.match_score != null ? Math.max(0, Math.min(100, Math.round(card.match_score))) : null;
    var scoreRing = null;
    if (pct != null) {
      scoreRing = h('span', {
        class: 'score', role: 'img', 'aria-label': t('matchFmt', { n: pct }), title: t('matchFmt', { n: pct }),
        style: '--m:' + pct
      }, [h('b', { 'aria-hidden': 'true' }, String(pct)), h('i', { 'aria-hidden': 'true' }, '%')]);
    }

    return h('li', { class: 'pick', 'data-pid': pid, 'data-fam': famAttr(card), style: '--i:' + (rank - 1) }, [
      media(card, 'portrait'),
      h('div', { class: 'ptop' }, [
        h('span', { class: 'rank', 'aria-hidden': 'true' }, String(rank)),
        h('div', { class: 'info' }, [
          h('p', { class: 'name' }, card.name),
          h('div', { class: 'brandrow' }, [
            card.brand ? h('p', { class: 'brand' }, card.brand) : null,
            card.family_label ? h('span', { class: 'fampill' }, card.family_label) : null
          ])
        ]),
        scoreRing
      ]),
      card.reason ? h('p', { class: 'reason' }, plain(card.reason)) : null,
      keyNotes.length ? h('ul', { class: 'tags' }, keyNotes.map(function (x) { return h('li', { class: 'tag' }, x); })) : null,
      h('div', { class: 'meta' }, meta),
      detail,
      h('div', { class: 'actions' }, [
        url ? h('a', {
          class: 'btn ghost', href: url, target: '_blank', rel: 'noopener noreferrer', 'data-act': 'view',
          onclick: function () { onView(card, rank, 'view_product'); }
        }, [S.mode === 'page' ? t('viewShort') : t('viewProduct'), h('span', { icon: 'external' })]) : h('span', { style: 'flex:1' }),
        h('button', { class: 'tbtn', type: 'button', 'data-act': 'up', 'aria-label': t('thumbsUp'), title: t('thumbsUp'), 'aria-pressed': 'false', icon: 'up', onclick: function () { onThumb(pid, 1); } }),
        h('button', { class: 'tbtn', type: 'button', 'data-act': 'down', 'aria-label': t('thumbsDown'), title: t('thumbsDown'), 'aria-pressed': 'false', icon: 'down', onclick: function () { onThumb(pid, -1); } }),
        h('button', { class: 'tbtn heart', type: 'button', 'data-act': 'save', 'aria-label': t('save'), title: t('save'), 'aria-pressed': 'false', icon: 'heart', onclick: function () { onHeart(card); } })
      ])
    ]);
  }

  function renderResults(e) {
    var r = e.reply, picks = (r.picks || []).slice(0, 3);
    var kids = [];
    if (r.guided && r.profile_summary && r.profile_summary.length) {
      // Guided match's "what I learned" summary: small labelled tags built from the taste profile the
      // interview collected, shown once above the picks so the shopper sees where they came from.
      kids.push(h('ul', { class: 'tags learned', 'aria-label': t('guidedWhatLearned') }, r.profile_summary.map(function (c) {
        return h('li', { class: 'tag', 'data-k': c.id === 'feel' ? 'feel' : null }, c.label);
      })));
    }
    kids.push(h('div', { class: 'rhead' }, h('h3', null, t('resultsTitle'))));
    if (r.fallback_used) kids.push(fallbackNote());
    kids.push(h('ol', { class: 'picks' }, picks.map(function (p, i) { return renderPick(p, i + 1, e); })));

    var L = r.layering;
    if (L && L.partner) {
      var partner = L.partner, purl = safeUrl(partner.product_url);
      var base = picks.filter(function (p) { return p.perfume_id === L.base_perfume_id; })[0];
      var onLayer = function (how) {
        track('layering_clicked', { base_perfume_id: L.base_perfume_id, partner_id: partner.perfume_id, action: how });
        if (how === 'view_product') postFeedback(partner.perfume_id, S.thumbs[partner.perfume_id] || null, true);
      };
      kids.push(h('div', { class: 'layer', 'data-layer': '', 'data-fam': famAttr(partner) }, [
        h('div', { class: 'lab' }, [h('span', { icon: 'layers' }), t('layerWith')]),
        h('div', { class: 'lrow' }, [
          media(partner, 'sm'),
          h('div', { class: 'info' }, [
            h('p', { class: 'name' }, partner.name),
            h('div', { class: 'brandrow' }, [
              partner.brand ? h('p', { class: 'brand' }, partner.brand) : null,
              base ? h('p', { class: 'brand' }, t('layerOn', { name: base.name }))
                : (partner.family_label ? h('span', { class: 'fampill' }, partner.family_label) : null)
            ])
          ])
        ]),
        L.reason ? h('p', null, plain(L.reason)) : null,
        purl ? h('a', { class: 'link', href: purl, target: '_blank', rel: 'noopener noreferrer', onclick: function () { onLayer('view_product'); } }, [t('viewProduct'), h('span', { icon: 'external' })]) : null
      ]));
      var lrow = kids[kids.length - 1];
      lrow.addEventListener('click', function (ev) { if (!ev.target.closest('a')) onLayer('card'); });
    }

    if (!e.stale) {
      var chips = (r.chips && r.chips.length) ? r.chips : fallbackChips(picks);
      kids.push(h('div', { class: 'refine' }, [
        h('span', { class: 'lab' }, t('refineTitle')),
        h('div', { class: 'chips' }, chips.map(function (c) {
          return h('button', { class: 'chip', type: 'button', 'data-chip': c.id, disabled: S.busy, onclick: function () { refine({ id: c.id, label: c.label || refineLabel(c.id, picks) }); } }, c.label || refineLabel(c.id, picks));
        }))
      ]));
    }
    return h('div', { class: 'results', 'data-results': '' }, kids);
  }

  function refineLabel(id, picks) {
    var m = I18N[S.lang].refine;
    if (id.indexOf('more_like:') === 0) {
      var pid = id.slice(10), n = 1;
      picks.forEach(function (p, i) { if (p.perfume_id === pid) n = i + 1; });
      return m.more_like.replace('{n}', n);
    }
    return m[id] || id;
  }
  function fallbackChips(picks) {
    var ids = ['less_sweet', 'fresher', 'cheaper', 'stronger', 'lighter'];
    picks.forEach(function (p) { ids.push('more_like:' + p.perfume_id); });
    return ids.map(function (id) { return { id: id, label: refineLabel(id, picks) }; });
  }

  // in-place sync of thumbs + hearts on every rendered card
  function syncCards() {
    var nodes = root.querySelectorAll('.pick');
    for (var i = 0; i < nodes.length; i++) {
      var pid = nodes[i].getAttribute('data-pid'), th = S.thumbs[pid] || null;
      var up = nodes[i].querySelector('[data-act=up]'), dn = nodes[i].querySelector('[data-act=down]'), hv = nodes[i].querySelector('[data-act=save]');
      if (up) up.setAttribute('aria-pressed', String(th === 1));
      if (dn) dn.setAttribute('aria-pressed', String(th === -1));
      if (hv) {
        var saved = !!S.saved[pid];
        hv.setAttribute('aria-pressed', String(saved));
        hv.setAttribute('aria-label', saved ? t('saved') : t('save'));
        hv.setAttribute('title', saved ? t('saved') : t('save'));
      }
    }
  }

  function onView(card, rank, action) {
    track('pick_clicked', { perfume_id: card.perfume_id, rank: rank, action: action });
    postFeedback(card.perfume_id, S.thumbs[card.perfume_id] || null, true);
  }

  function onThumb(pid, v) {
    var next = S.thumbs[pid] === v ? null : v;
    S.thumbs[pid] = next;
    syncCards();
    postFeedback(pid, next, false);
    track('feedback_given', { perfume_id: pid, thumbs: next });
  }

  function postFeedback(pid, thumbs, clicked) {
    if (!S.sessionId) return;
    api('POST', '/api/feedback', { session_id: S.sessionId, perfume_id: pid, thumbs: thumbs, clicked: !!clicked }).catch(function (err) {
      if (window.console && console.warn) console.warn('[perfume-widget] feedback', err && err.message);
    });
  }

  // ---------------------------------------------------------------- wishlist
  function onHeart(card) {
    if (S.saved[card.perfume_id]) { setTab('wishlist'); return; }
    if (!S.consent) { S.pendingSave = card; R.consent.hidden = false; R.consentYes.focus(); return; }
    saveWishlist([card.perfume_id]);
  }

  function answerConsent(yes) {
    R.consent.hidden = true;
    var card = S.pendingSave; S.pendingSave = null;
    if (!yes) return;
    S.consent = true;
    store.set('consent', S.sessionId);
    if (card) saveWishlist([card.perfume_id]);
  }

  function saveWishlist(ids) {
    ids.forEach(function (id) { S.saved[id] = true; });
    syncCards();
    api('POST', '/api/wishlist', { session_id: S.sessionId, perfume_ids: ids, consent: true }).then(function (d) {
      setWishlist(d.wishlist || []);
      track('wishlist_saved', { perfume_ids: ids, count: S.wishlist.length });
    }, function (err) {
      ids.forEach(function (id) { delete S.saved[id]; });
      syncCards();
      showError(err, function () { saveWishlist(ids); });
    });
  }

  function loadWishlist() {
    if (!S.sessionId) return Promise.resolve();
    return api('GET', '/api/wishlist?session_id=' + encodeURIComponent(S.sessionId)).then(function (d) {
      setWishlist(d.wishlist || []);
    }, function () {});
  }

  function setWishlist(list) {
    S.wishlist = list;
    S.saved = {};
    list.forEach(function (c) { S.saved[c.perfume_id] = true; });
    renderChrome();
    syncCards();
    if (S.tab === 'wishlist') renderWishlist();
  }

  function renderWishlist() {
    R.wl.textContent = '';
    if (!S.wishlist.length) { R.wl.appendChild(h('p', { class: 'empty' }, t('wishlistEmpty'))); return; }
    R.wl.appendChild(h('h3', null, t('wishlistTitle')));
    S.wishlist.forEach(function (c) {
      var url = safeUrl(c.product_url);
      R.wl.appendChild(h('div', { class: 'wlitem', 'data-pid': c.perfume_id, 'data-fam': famAttr(c) }, [
        media(c, 'sm'),
        h('div', { class: 'info' }, [
          h('p', { class: 'name' }, c.name),
          h('div', { class: 'brandrow' }, [
            c.brand ? h('p', { class: 'brand' }, c.brand) : null,
            c.family_label ? h('span', { class: 'fampill' }, c.family_label) : null
          ]),
          h('div', { class: 'meta' }, [priceNode(c)])
        ]),
        url ? h('a', { class: 'link', href: url, target: '_blank', rel: 'noopener noreferrer', onclick: function () { onView(c, 0, 'wishlist_view_product'); } }, [t('viewProduct'), h('span', { icon: 'external' })]) : null
      ]));
    });
  }

  // ---------------------------------------------------------------- panel, tabs, language
  function setTab(tab) {
    S.tab = tab;
    var wl = tab === 'wishlist';
    R.list.hidden = wl;
    R.wl.hidden = !wl;
    R.composer.hidden = wl;
    renderChrome();
    if (wl) { renderWishlist(); loadWishlist(); }
  }

  function focusInput() { try { R.input.focus({ preventScroll: true }); } catch (e) {} }

  var opened = false;
  function openPanel() {
    if (S.open) return;
    S.open = true;
    R.panel.hidden = false;
    R.launcher.hidden = true;
    track('widget_opened', { first: !opened, page: location.pathname });
    if (!opened) {
      opened = true;
      if (!restoreConversation()) push({ k: 'start' });
      ensureSession().catch(function (err) { showError(err, function () { withSession(function () {}, null); }); });
    }
    if (window.matchMedia && window.matchMedia('(pointer:fine)').matches) focusInput();
    else R.closeBtn.focus({ preventScroll: true });
  }

  function closePanel() {
    if (!S.open) return;
    S.open = false;
    R.panel.hidden = true;
    R.launcher.hidden = false;
    R.launcher.focus({ preventScroll: true });
  }

  function startOver() {
    if (S.busy) return;
    S.entries.slice().forEach(removeEntry);
    R.consent.hidden = true;
    setTab('chat');
    clearPersistedConversation();
    push({ k: 'start' });
    // Fresh start on the server too: the advisor forgets the earlier taste profile; the wishlist stays.
    if (S.sessionId) api('POST', '/api/session/reset', { session_id: S.sessionId, lang: S.lang }).catch(function () {});
  }

  function conversationStarted() {
    return S.entries.some(function (e) { return e.k !== 'start' || e.chosen; });
  }

  function setLang(lang) {
    lang = normLang(lang) || 'en';
    if (lang === S.lang) return;
    S.lang = lang;
    store.set('lang', lang);
    store.set('lang_attr', ATTR_LANG);
    renderChrome();
    rerenderAll();
    if (S.tab === 'wishlist') renderWishlist();
    // Before the conversation starts, fetch a localized greeting and quiz. Afterwards keep the session and send lang per request.
    if (S.session && !conversationStarted() && !S.busy) {
      S.session = null;
      ensureSession().catch(function () {});
    }
  }

  renderChrome();

  function initPage() {
    if (S.open) return;
    S.open = true;
    R.panel.hidden = false;
    opened = true;
    track('widget_opened', { first: true, page: location.pathname });
    if (!restoreConversation()) push({ k: 'start' });
    ensureSession().catch(function (err) { showError(err, function () { withSession(function () {}, null); }); });
  }

  function mount() {
    if (MODE === 'page') {
      var target = null;
      if (MOUNT_SEL) { try { target = document.querySelector(MOUNT_SEL); } catch (e) { target = null; } }
      if (!target) {
        if (window.console && console.warn) console.warn('[perfume-widget] data-mount selector not found, falling back to <body>:', MOUNT_SEL);
        target = document.body;
      }
      if (!host.isConnected || host.parentNode !== target) target.appendChild(host);
      initPage();
      return;
    }
    if (!host.isConnected) document.body.appendChild(host);
    if (/[?&#]psa_open=1\b/.test(location.search + location.hash)) openPanel();
  }
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);

  window.PerfumeWidget = {
    open: function () { if (S.mode !== 'page') openPanel(); },
    close: function () { if (S.mode !== 'page') closePanel(); },
    setLang: setLang,
    get lang() { return S.lang; },
    get sessionId() { return S.sessionId; }
  };
})();
