/*
 * Perfume selection agent: embeddable chat widget.
 * Vanilla JS, one file, no build step, no external fonts or CDNs. Everything renders inside a Shadow DOM.
 *
 * Embed:  <script src="/widget.js" data-lang="en" data-brand=""></script>
 *   data-lang   "en" | "ar"          initial language (the in-widget toggle overrides it until the page's data-lang changes)
 *   data-brand  optional brand name  sent to POST /api/session as "brand"
 *   data-api    optional API origin  defaults to the origin that served widget.js
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
      greeting: "Hi! I'll help you find a perfume you'll love. How would you like to start?",
      startQuiz: 'Answer 5 quick questions',
      startQuizSub: 'Tap to choose. Takes about 30 seconds.',
      startChat: 'Tell me what you want',
      startChatSub: 'Describe a mood, a note, or a perfume you love.',
      chatPrompt: "Tell me what you're looking for: a mood, an occasion, notes you love, or a perfume you already wear.",
      placeholder: 'Describe your ideal scent…',
      send: 'Send',
      quizProgress: 'Question {i} of {n}',
      next: 'Next',
      seePicks: 'See my picks',
      noPreference: 'No preference',
      typing: 'Finding scents for you…',
      resultsTitle: 'Your top picks',
      match: 'match',
      matchFmt: '{n}% match',
      estTooltip: 'Estimated price for the prototype',
      noPrice: 'Price not available',
      viewProduct: 'View product',
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
      wishlistEmpty: 'Nothing saved yet. Tap the heart on a pick to save it here.',
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
      greeting: 'مرحباً! سأساعدك في العثور على عطر تحبه. كيف تفضّل أن نبدأ؟',
      startQuiz: 'أجب عن 5 أسئلة سريعة',
      startQuizSub: 'اختر بلمسة، في نحو 30 ثانية.',
      startChat: 'أخبرني بما تريد',
      startChatSub: 'صف مزاجاً أو نفحة أو عطراً تحبه.',
      chatPrompt: 'أخبرني بما تبحث عنه: مزاج، أو مناسبة، أو نفحات تحبها، أو عطر تستخدمه حالياً.',
      placeholder: 'صف العطر الذي تتخيله…',
      send: 'إرسال',
      quizProgress: 'السؤال {i} من {n}',
      next: 'التالي',
      seePicks: 'اعرض اختياراتي',
      noPreference: 'لا تفضيل',
      typing: 'نبحث عن عطور تناسبك…',
      resultsTitle: 'أفضل اختياراتك',
      match: 'تطابق',
      matchFmt: 'تطابق {n}%',
      estTooltip: 'سعر تقديري للنموذج الأولي',
      noPrice: 'السعر غير متوفر',
      viewProduct: 'عرض المنتج',
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
      wishlistEmpty: 'لا يوجد شيء محفوظ بعد. اضغط على القلب في أي اختيار لحفظه هنا.',
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
    layers: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l8 4-8 4-8-4zM4 12l8 4 8-4M4 16l8 4 8-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>'
  };

  var FAMILY_COLORS = {
    floral: '#e2b4bf', fresh: '#e6d584', aquatic: '#a9c9d6', green: '#b3c79f',
    fruity: '#eeb095', gourmand: '#d8b48c', woody: '#b39a82', amber: '#d29a5f'
  };
  var FALLBACK_COLORS = ['#e2b4bf', '#e6d584', '#a9c9d6', '#b3c79f', '#eeb095', '#d8b48c', '#b39a82', '#d29a5f'];
  var REFINE_RE = /^(less_sweet|fresher|cheaper|stronger|lighter|more_like:.+)$/;
  var EMPTY_CHOICE = { skip: 1, none: 1, any: 1, no_preference: 1 };

  // ---------------------------------------------------------------- state
  var S = {
    lang: initialLang(),
    sessionId: store.get('session_id'),
    session: null,
    ready: false,
    busy: false,
    open: false,
    tab: 'chat',
    entries: [],
    quiz: null,          // {questions, i, sel: {qid: [ids]}}
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
  function familyColor(card) {
    var c = FAMILY_COLORS[String(card.family || '').toLowerCase()];
    if (c) return c;
    var s = String(card.name || card.perfume_id || ''), n = 0;
    for (var i = 0; i < s.length; i++) n = (n * 31 + s.charCodeAt(i)) >>> 0;
    return FALLBACK_COLORS[n % FALLBACK_COLORS.length];
  }

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
  var CSS = [
    ':host{all:initial}',
    '.psa{--bg:#faf7f2;--surface:#ffffff;--surface-2:#f2ede5;--ink:#1f1a15;--ink-2:#5c5349;--ink-3:#8b8177;--border:#e8e1d6;--border-2:#d9cfc1;',
    '--accent:#8a5a2b;--accent-hover:#754a22;--accent-ink:#ffffff;--accent-soft:#f4e9dc;--danger:#a23b2a;--danger-soft:#f8e6e1;--good:#3f6b47;',
    '--shadow:0 18px 50px rgba(48,30,12,.18),0 2px 8px rgba(48,30,12,.08);--ph-ink:rgba(31,26,21,.62);--tap:36px;',
    'font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans","Noto Sans Arabic",sans-serif;',
    'font-size:15px;line-height:1.45;color:var(--ink);-webkit-font-smoothing:antialiased;text-align:start}',
    '.psa:lang(ar){font-family:"SF Arabic","Geeza Pro","Noto Sans Arabic","Noto Naskh Arabic","Segoe UI",Tahoma,system-ui,sans-serif;line-height:1.6}',
    '@media (prefers-color-scheme:dark){.psa{--bg:#171411;--surface:#211d19;--surface-2:#2b2621;--ink:#f3ede5;--ink-2:#c6bbae;--ink-3:#948a7e;--border:#362f28;--border-2:#4a4037;',
    '--accent:#d49a5c;--accent-hover:#e0ab71;--accent-ink:#1b130b;--accent-soft:#3a2b1d;--danger:#e58b77;--danger-soft:#3a211b;--good:#8fc198;--shadow:0 18px 50px rgba(0,0,0,.5);--ph-ink:rgba(20,15,10,.7)}}',
    '@media (pointer:coarse){.psa{--tap:44px}}',
    '*,*::before,*::after{box-sizing:border-box}',
    'button,input{font:inherit;color:inherit;margin:0}',
    'button{cursor:pointer;-webkit-tap-highlight-color:transparent}',
    'button:disabled{cursor:default}',
    ':focus-visible{outline:2px solid var(--accent);outline-offset:2px}',
    'svg{width:20px;height:20px;display:block;flex:none}',
    '[dir=rtl] svg.flip{transform:scaleX(-1)}',
    '.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}',
    // launcher
    '.launcher{position:fixed;z-index:2147483000;bottom:20px;inset-inline-end:20px;display:flex;align-items:center;gap:8px;height:52px;padding:0 20px 0 16px;padding-inline:16px 20px;',
    'border:0;border-radius:999px;background:var(--accent);color:var(--accent-ink);font-weight:600;font-size:15px;box-shadow:0 8px 24px rgba(60,36,12,.28);transition:transform .15s ease,background .15s ease}',
    '.launcher:hover{background:var(--accent-hover);transform:translateY(-1px)}',
    '.launcher[hidden]{display:none}',
    // panel
    '.panel{position:fixed;z-index:2147483001;bottom:20px;inset-inline-end:20px;width:420px;height:min(720px,calc(100vh - 40px));display:flex;flex-direction:column;',
    'background:var(--bg);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);overflow:hidden;animation:psa-in .18s ease-out}',
    '.panel[hidden]{display:none}',
    '@keyframes psa-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}',
    '@media (prefers-reduced-motion:reduce){.panel,.dot{animation:none!important}.launcher{transition:none}}',
    '@media (min-width:640px) and (max-width:1024px){.panel{width:440px;height:min(780px,calc(100vh - 40px))}}',
    '@media (max-width:419px){.head .mark{display:none}.psa .head{gap:6px;padding-inline:14px 6px}}',
    '@media (max-width:639px){.panel{inset:0;width:100%;height:100%;height:100dvh;border:0;border-radius:0}.launcher{bottom:16px;inset-inline-end:16px}}',
    // header
    '.head{display:flex;align-items:center;gap:10px;padding:14px 12px 10px 16px;padding-inline:16px 10px}',
    '.mark{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent);flex:none}',
    '.titles{flex:1;min-width:0}',
    '.title{margin:0;font-size:16px;font-weight:650;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.subtitle{margin:0;font-size:12.5px;color:var(--ink-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.iconbtn{width:var(--tap);height:var(--tap);display:grid;place-items:center;border:0;border-radius:10px;background:transparent;color:var(--ink-2)}',
    '.iconbtn:hover{background:var(--surface-2);color:var(--ink)}',
    '.langbtn{flex:none;height:32px;padding:0 12px;border:1px solid var(--border-2);border-radius:999px;background:var(--surface);font-size:13px;font-weight:600;color:var(--ink-2)}',
    '@media (pointer:coarse){.langbtn{height:40px}}',
    '.langbtn:hover{border-color:var(--accent);color:var(--accent)}',
    '.langbtn:lang(ar),.langbtn[lang=ar]{font-family:"SF Arabic","Geeza Pro","Noto Sans Arabic",Tahoma,system-ui,sans-serif}',
    '.tabs{display:flex;gap:4px;padding:0 12px;border-bottom:1px solid var(--border)}',
    '.tab{position:relative;border:0;background:none;padding:8px 10px 10px;min-height:var(--tap);font-size:14px;font-weight:550;color:var(--ink-3)}',
    '.tab[aria-selected=true]{color:var(--ink)}',
    '.tab[aria-selected=true]::after{content:"";position:absolute;inset-inline:10px;bottom:-1px;height:2px;border-radius:2px;background:var(--accent)}',
    // body
    '.body{flex:1;min-height:0;display:flex;flex-direction:column}',
    '.list{position:relative;flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:16px;display:flex;flex-direction:column;gap:10px}',
    '.list[hidden]{display:none}',
    '.msg{max-width:86%;padding:10px 14px;border-radius:16px;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}',
    '.bot{align-self:flex-start;background:var(--surface-2);border-end-start-radius:6px}',
    '.user{align-self:flex-end;background:var(--accent);color:var(--accent-ink);border-end-end-radius:6px}',
    '.wrap{display:flex;flex-direction:column;gap:8px;align-self:stretch}',
    '.note{display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-3);margin:0}',
    '.note svg{width:15px;height:15px}',
    '.err{align-self:flex-start;max-width:86%;display:flex;flex-direction:column;gap:8px;padding:10px 14px;border-radius:16px;border-end-start-radius:6px;background:var(--danger-soft);color:var(--ink)}',
    '.chips{display:flex;flex-wrap:wrap;gap:8px}',
    '.chip{min-height:var(--tap);padding:6px 14px;border:1px solid var(--border-2);border-radius:999px;background:var(--surface);font-size:14px;line-height:1.2;color:var(--ink);text-align:center}',
    '@media (hover:hover){.chip:hover:not(:disabled):not([aria-pressed=true]){border-color:var(--accent);color:var(--accent)}}',
    '.chip[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}',
    '.chip:disabled{opacity:.55}',
    '.starts{display:grid;gap:8px;align-self:stretch}',
    '.start{display:flex;align-items:center;gap:12px;width:100%;padding:14px;border:1px solid var(--border);border-radius:14px;background:var(--surface);text-align:start;transition:border-color .15s ease}',
    '.start:hover{border-color:var(--accent)}',
    '.start .ic{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent);flex:none}',
    '.start b{display:block;font-size:15px;font-weight:600}',
    '.start small{display:block;font-size:13px;color:var(--ink-3)}',
    '.card{align-self:stretch;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px}',
    '.quiz{display:flex;flex-direction:column;gap:12px}',
    '.progress{display:flex;align-items:center;gap:10px;font-size:12.5px;color:var(--ink-3)}',
    '.bar{flex:1;height:4px;border-radius:4px;background:var(--surface-2);overflow:hidden}',
    '.bar i{display:block;height:100%;background:var(--accent);border-radius:4px}',
    '.q{margin:0;font-size:16px;font-weight:600}',
    '.row-end{display:flex;justify-content:flex-end;gap:8px}',
    '.btn{min-height:var(--tap);padding:8px 18px;border-radius:999px;border:1px solid transparent;font-size:14px;font-weight:600;display:inline-flex;align-items:center;justify-content:center;gap:6px;text-decoration:none}',
    '.primary{background:var(--accent);color:var(--accent-ink)}',
    '.primary:hover:not(:disabled){background:var(--accent-hover)}',
    '.ghost{background:transparent;border-color:var(--border-2);color:var(--ink)}',
    '.ghost:hover{border-color:var(--accent);color:var(--accent)}',
    '.btn:disabled{opacity:.5}',
    '.btn svg{width:16px;height:16px}',
    // results
    '.results{display:flex;flex-direction:column;gap:10px;align-self:stretch}',
    '.rhead{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin:4px 2px 0}',
    '.rhead h3{margin:0;font-size:13px;font-weight:650;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-2)}',
    '.rhead:lang(ar) h3{letter-spacing:0}',
    '.pick{display:flex;flex-direction:column;gap:10px;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:12px}',
    '.ptop{display:flex;gap:12px;align-items:flex-start}',
    '.media{position:relative;width:64px;height:64px;flex:none;border-radius:12px;overflow:hidden;background:var(--fam,#d8b48c)}',
    '.media.sm{width:44px;height:44px;border-radius:10px}',
    '.media img{width:100%;height:100%;object-fit:cover;display:block;background:var(--surface)}',
    '.ph{width:100%;height:100%;display:grid;place-items:center;font-weight:700;font-size:19px;letter-spacing:.02em;color:var(--ph-ink)}',
    '.media.sm .ph{font-size:14px}',
    '.rank{position:absolute;top:4px;inset-inline-start:4px;min-width:18px;height:18px;padding:0 5px;border-radius:9px;background:rgba(255,255,255,.88);color:#1f1a15;font-size:11px;font-weight:700;display:grid;place-items:center}',
    '.info{flex:1;min-width:0}',
    '.name{margin:0;font-size:15.5px;font-weight:650;line-height:1.3}',
    '.brand{margin:2px 0 0;font-size:13px;color:var(--ink-2)}',
    '.score{flex:none;align-self:flex-start;padding:3px 9px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-size:12px;font-weight:700;white-space:nowrap}',
    '.reason{margin:0;font-size:14px;color:var(--ink)}',
    '.tags{display:flex;flex-wrap:wrap;gap:6px;margin:0;padding:0;list-style:none}',
    '.tag{padding:2px 9px;border-radius:999px;background:var(--surface-2);color:var(--ink-2);font-size:12.5px}',
    '.meta{display:flex;align-items:center;flex-wrap:wrap;gap:4px 10px;font-size:13px;color:var(--ink-2)}',
    '.price{font-weight:650;color:var(--ink)}',
    '.price.est{text-decoration:underline dotted var(--ink-3);text-underline-offset:3px;cursor:help}',
    '.dot-sep{width:3px;height:3px;border-radius:50%;background:var(--ink-3)}',
    '.more{margin-inline-start:auto;border:0;background:none;padding:4px 2px;font-size:13px;font-weight:600;color:var(--accent)}',
    '.detail{display:grid;gap:4px;font-size:13px;color:var(--ink-2);padding:10px 12px;border-radius:10px;background:var(--surface-2)}',
    '.detail b{color:var(--ink);font-weight:600}',
    '.detail p{margin:0}',
    '.actions{display:flex;align-items:center;gap:4px}',
    '.actions .btn{flex:1;min-width:0}',
    '.tbtn{width:var(--tap);height:var(--tap);display:grid;place-items:center;border:1px solid transparent;border-radius:10px;background:transparent;color:var(--ink-3)}',
    '.tbtn:hover{background:var(--surface-2);color:var(--ink)}',
    '.tbtn[aria-pressed=true]{color:var(--accent);--thumb-fill:var(--accent-soft);--heart-fill:var(--accent)}',
    '.tbtn.heart[aria-pressed=true]{--heart-fill:#c2452d;color:#c2452d}',
    '.layer{display:flex;flex-direction:column;gap:8px;padding:12px;border-radius:14px;border:1px dashed var(--border-2);background:var(--accent-soft)}',
    '.layer .lab{display:flex;align-items:center;gap:6px;font-size:12.5px;font-weight:650;color:var(--accent);text-transform:uppercase;letter-spacing:.04em}',
    '.layer .lab:lang(ar){letter-spacing:0}',
    '.layer .lab svg{width:16px;height:16px}',
    '.lrow{display:flex;align-items:center;gap:10px;width:100%;padding:0;border:0;background:none;text-align:start}',
    '.lrow .info .name{font-size:14.5px}',
    '.layer p{margin:0;font-size:13.5px;color:var(--ink-2)}',
    '.link{display:inline-flex;align-items:center;gap:4px;font-size:13px;font-weight:600;color:var(--accent);text-decoration:none}',
    '.link:hover{text-decoration:underline}',
    '.link svg{width:14px;height:14px}',
    '.refine{display:flex;flex-direction:column;gap:8px;margin-top:2px}',
    '.refine .lab{font-size:12.5px;font-weight:600;color:var(--ink-3)}',
    // typing
    '.typing{align-self:flex-start;display:flex;align-items:center;gap:4px;padding:12px 14px;border-radius:16px;border-end-start-radius:6px;background:var(--surface-2)}',
    '.dot{width:7px;height:7px;border-radius:50%;background:var(--ink-3);animation:psa-dot 1.1s infinite ease-in-out}',
    '.dot:nth-child(2){animation-delay:.15s}.dot:nth-child(3){animation-delay:.3s}',
    '@keyframes psa-dot{0%,80%,100%{opacity:.3;transform:translateY(0)}40%{opacity:1;transform:translateY(-3px)}}',
    // consent + composer
    '.consent{display:flex;align-items:center;flex-wrap:wrap;gap:8px 10px;margin:0 12px 8px;padding:10px 12px;border-radius:14px;background:var(--accent-soft);font-size:14px}',
    '.consent[hidden]{display:none}',
    '.consent span{flex:1 1 180px}',
    '.consent .btn{min-height:32px;padding:4px 14px}',
    '@media (pointer:coarse){.consent .btn{min-height:40px}}',
    '.composer{display:flex;align-items:center;gap:8px;padding:10px 12px;padding-bottom:calc(10px + env(safe-area-inset-bottom,0px));border-top:1px solid var(--border);background:var(--bg)}',
    '.composer[hidden]{display:none}',
    '.input{flex:1;min-width:0;height:44px;padding:0 16px;border:1px solid var(--border-2);border-radius:999px;background:var(--surface);color:var(--ink);font-size:16px;outline:none}',
    '.input::placeholder{color:var(--ink-3)}',
    '.input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}',
    '.send{width:44px;height:44px;flex:none;display:grid;place-items:center;border:0;border-radius:50%;background:var(--accent);color:var(--accent-ink)}',
    '.send:disabled{opacity:.4}',
    // wishlist
    '.wl{flex:1;min-height:0;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}',
    '.wl[hidden]{display:none}',
    '.wl h3{margin:0 2px;font-size:13px;font-weight:650;color:var(--ink-2)}',
    '.wlitem{display:flex;align-items:center;gap:12px;padding:10px;background:var(--surface);border:1px solid var(--border);border-radius:14px}',
    '.wlitem .info{display:flex;flex-direction:column;gap:2px}',
    '.empty{margin:24px 8px;text-align:center;color:var(--ink-3);font-size:14px}'
  ].join('\n');

  // ---------------------------------------------------------------- shell
  var host = document.createElement('div');
  host.id = 'psa-widget-host';
  var root = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host;
  var styleEl = document.createElement('style');
  styleEl.textContent = CSS;
  root.appendChild(styleEl);

  var R = {}; // refs
  R.app = h('div', { class: 'psa' });
  R.launcher = h('button', { class: 'launcher', type: 'button', onclick: function () { openPanel(); } }, [
    h('span', { icon: 'bottle' }), R.launcherLabel = h('span')
  ]);
  R.title = h('h2', { class: 'title', id: 'psa-title' });
  R.subtitle = h('p', { class: 'subtitle' });
  R.langBtn = h('button', { class: 'langbtn', type: 'button', onclick: function () { setLang(S.lang === 'ar' ? 'en' : 'ar'); } });
  R.restartBtn = h('button', { class: 'iconbtn', type: 'button', icon: 'restart', onclick: startOver });
  R.closeBtn = h('button', { class: 'iconbtn', type: 'button', icon: 'close', onclick: function () { closePanel(); } });
  R.tabChat = h('button', { class: 'tab', type: 'button', role: 'tab', onclick: function () { setTab('chat'); } });
  R.tabWish = h('button', { class: 'tab', type: 'button', role: 'tab', onclick: function () { setTab('wishlist'); } });
  R.list = h('div', { class: 'list', role: 'log', 'aria-live': 'polite' });
  R.wl = h('div', { class: 'wl', hidden: true });
  R.consentText = h('span');
  R.consentYes = h('button', { class: 'btn primary', type: 'button', onclick: function () { answerConsent(true); } });
  R.consentNo = h('button', { class: 'btn ghost', type: 'button', onclick: function () { answerConsent(false); } });
  R.consent = h('div', { class: 'consent', role: 'alertdialog', hidden: true }, [R.consentText, R.consentYes, R.consentNo]);
  R.input = h('input', { class: 'input', type: 'text', autocomplete: 'off', enterkeyhint: 'send', maxlength: '500' });
  R.send = h('button', { class: 'send', type: 'submit', icon: 'send' });
  R.composer = h('form', { class: 'composer', onsubmit: function (ev) { ev.preventDefault(); sendTyped(); } }, [R.input, R.send]);
  R.panel = h('section', { class: 'panel', role: 'dialog', 'aria-labelledby': 'psa-title', hidden: true }, [
    h('header', { class: 'head' }, [
      h('div', { class: 'mark', icon: 'bottle' }),
      h('div', { class: 'titles' }, [R.title, R.subtitle]),
      R.langBtn, R.restartBtn, R.closeBtn
    ]),
    h('div', { class: 'tabs', role: 'tablist' }, [R.tabChat, R.tabWish]),
    h('div', { class: 'body' }, [R.list, R.wl, R.consent, R.composer])
  ]);
  add(R.app, [R.launcher, R.panel]);
  root.appendChild(R.app);

  R.input.addEventListener('input', syncSend);
  R.panel.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closePanel(); });

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
    R.closeBtn.setAttribute('aria-label', t('close'));
    R.tabChat.textContent = t('tabChat');
    R.tabWish.textContent = t('tabWishlist', { n: S.wishlist.length });
    R.tabChat.setAttribute('aria-selected', String(S.tab === 'chat'));
    R.tabWish.setAttribute('aria-selected', String(S.tab === 'wishlist'));
    R.consentText.textContent = t('consent');
    R.consentYes.textContent = t('yes');
    R.consentNo.textContent = t('no');
    R.input.setAttribute('placeholder', t('placeholder'));
    R.input.setAttribute('aria-label', t('placeholder'));
    R.send.setAttribute('aria-label', t('send'));
    syncSend();
  }

  function syncSend() { R.send.disabled = S.busy || !R.input.value.trim(); }

  // ---------------------------------------------------------------- transcript
  function push(e) {
    e.id = ++S.seq;
    S.entries.push(e);
    e.el = renderEntry(e);
    R.list.appendChild(e.el);
    scrollTo(e.el);
    return e;
  }
  function refresh(e) {
    if (!e.el || !e.el.parentNode) return;
    var n = renderEntry(e);
    e.el.parentNode.replaceChild(n, e.el);
    e.el = n;
  }
  function removeEntry(e) {
    var i = S.entries.indexOf(e);
    if (i >= 0) S.entries.splice(i, 1);
    if (e.el && e.el.parentNode) e.el.parentNode.removeChild(e.el);
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
      case 'quiz': return renderQuiz(e);
      case 'results': return renderResults(e);
      case 'error': return renderError(e);
      case 'typing': return h('div', { class: 'typing', role: 'status' }, [
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

  function renderStart(e) {
    var greeting = (S.session && S.session.greeting) || t('greeting');
    var kids = [h('p', { class: 'msg bot' }, greeting)];
    if (!e.chosen) {
      kids.push(h('div', { class: 'starts' }, [
        h('button', { class: 'start', type: 'button', 'data-start': 'quiz', onclick: startQuiz }, [
          h('span', { class: 'ic', icon: 'quiz' }), h('span', null, [h('b', null, t('startQuiz')), h('small', null, t('startQuizSub'))])
        ]),
        h('button', { class: 'start', type: 'button', 'data-start': 'chat', onclick: startChat }, [
          h('span', { class: 'ic', icon: 'chat' }), h('span', null, [h('b', null, t('startChat')), h('small', null, t('startChatSub'))])
        ])
      ]));
    }
    return h('div', { class: 'wrap' }, kids);
  }

  // ---------------------------------------------------------------- quiz
  function startQuiz() {
    if (S.busy) return;
    markStart('quiz');
    withSession(function () {
      var qs = (S.session && S.session.quiz) || [];
      if (!qs.length) { push({ k: 'bot', i18n: 'chatPrompt' }); focusInput(); return; }
      S.quiz = { questions: qs, i: 0, sel: {} };
      track('quiz_started', { questions: qs.length });
      S.quiz.entry = push({ k: 'quiz' });
    }, startQuiz);
  }

  function renderQuiz(e) {
    var Q = S.quiz;
    if (!Q) return h('div');
    var q = Q.questions[Q.i], n = Q.questions.length, sel = Q.sel[q.id] || [];
    var last = Q.i === n - 1;
    return h('div', { class: 'card quiz', 'data-qid': q.id }, [
      h('div', { class: 'progress' }, [
        h('span', null, t('quizProgress', { i: Q.i + 1, n: n })),
        h('span', { class: 'bar' }, h('i', { style: 'width:' + Math.round((Q.i + 1) / n * 100) + '%' }))
      ]),
      h('p', { class: 'q' }, q.question),
      h('div', { class: 'chips', role: 'group', 'aria-label': q.question }, (q.options || []).map(function (c) {
        return h('button', {
          class: 'chip', type: 'button', 'data-id': c.id, 'aria-pressed': String(sel.indexOf(c.id) >= 0),
          onclick: function () { toggleQuizChip(q, c.id); }
        }, c.label || c.id);
      })),
      h('div', { class: 'row-end' }, h('button', {
        class: 'btn primary', type: 'button', 'data-quiz-next': '', disabled: S.busy, onclick: quizNext
      }, last ? t('seePicks') : t('next')))
    ]);
  }

  function toggleQuizChip(q, id) {
    var Q = S.quiz, sel = (Q.sel[q.id] || []).slice(), at = sel.indexOf(id);
    if (at >= 0) sel.splice(at, 1);
    else if (!q.multi || EMPTY_CHOICE[id]) sel = [id];
    else sel = sel.filter(function (x) { return !EMPTY_CHOICE[x]; }).concat(id);
    Q.sel[q.id] = sel;
    refresh(Q.entry);
  }

  function quizNext() {
    var Q = S.quiz;
    if (!Q || S.busy) return;
    var q = Q.questions[Q.i], sel = Q.sel[q.id] || [];
    var labels = (q.options || []).filter(function (c) { return sel.indexOf(c.id) >= 0; }).map(function (c) { return c.label || c.id; });
    var qEntry = Q.entry;
    removeEntry(qEntry);
    push({ k: 'bot', text: q.question });
    push({ k: 'user', text: labels.length ? labels.join(', ') : t('noPreference') });
    if (Q.i < Q.questions.length - 1) {
      Q.i++;
      Q.entry = push({ k: 'quiz' });
    } else {
      var answers = buildAnswers(Q);
      S.quiz = null;
      track('quiz_completed', { answered: Object.keys(Q.sel).filter(function (k) { return Q.sel[k].length; }).length });
      request('/api/quiz', function () { return { session_id: S.sessionId, answers: answers, lang: S.lang }; });
    }
  }

  function buildAnswers(Q) {
    var a = { liked_notes: [], disliked_notes: [], moods: [], strength: null, budget_aed: null };
    Q.questions.forEach(function (q) {
      var sel = (Q.sel[q.id] || []).filter(function (id) { return !EMPTY_CHOICE[id]; });
      var num = sel.length ? parseFloat(sel[0]) : NaN;
      if (q.id === 'liked_notes') a.liked_notes = sel;
      else if (q.id === 'disliked_notes') a.disliked_notes = sel;
      else if (q.id === 'mood' || q.id === 'moods') a.moods = sel;
      else if (q.id === 'strength') a.strength = isNaN(num) ? null : num;
      else if (q.id === 'budget') a.budget_aed = isNaN(num) || num <= 0 ? null : num;
    });
    return a;
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
    S.entries.forEach(function (e) { if (e.k === 'start' && !e.chosen) { e.chosen = how; refresh(e); } });
  }

  function abandonQuiz() {
    if (S.quiz) { removeEntry(S.quiz.entry); S.quiz = null; }
  }

  function sendTyped() {
    var text = R.input.value.trim();
    if (!text || S.busy) return;
    R.input.value = '';
    syncSend();
    sendChat(text, 'typed');
  }

  function sendChat(text, source) {
    markStart('chat');
    abandonQuiz();
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
  function setBusy(b) {
    S.busy = b;
    syncSend();
    var nodes = R.list.querySelectorAll('.chip,[data-quiz-next],.start');
    for (var i = 0; i < nodes.length; i++) nodes[i].disabled = b;
    if (b && !typingEntry) typingEntry = push({ k: 'typing' });
    if (!b && typingEntry) { removeEntry(typingEntry); typingEntry = null; }
  }

  function withSession(fn, retry) {
    if (S.session) { fn(); return; }
    setBusy(true);
    ensureSession().then(function () { setBusy(false); fn(); }, function (err) { setBusy(false); showError(err, retry); });
  }

  function request(path, bodyFn) {
    if (S.busy) return;
    setBusy(true);
    ensureSession()
      .then(function () { return api('POST', path, bodyFn()); })
      .then(function (reply) { setBusy(false); handleReply(reply, path); },
        function (err) { setBusy(false); showError(err, function () { request(path, bodyFn); }); });
  }

  function handleReply(r, path) {
    var picks = (r && r.picks) || [];
    var hasPicks = picks.length > 0;
    var bot = { k: 'bot', text: plain(r.reply), fallback: !!r.fallback_used && !hasPicks };
    if (r.next_question && r.next_question.options && r.next_question.options.length) {
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
  function media(card, small, rank) {
    var box = h('div', { class: 'media' + (small ? ' sm' : '') });
    box.style.setProperty('--fam', familyColor(card));
    var ph = function () { return h('div', { class: 'ph', 'aria-hidden': 'true' }, initials(card.name)); };
    var src = safeUrl(card.image_url);
    if (src) {
      var img = h('img', { alt: '', loading: 'lazy', decoding: 'async' });
      img.addEventListener('error', function () { if (img.parentNode) img.parentNode.replaceChild(ph(), img); });
      img.src = src;
      box.appendChild(img);
    } else box.appendChild(ph());
    if (rank) box.appendChild(h('span', { class: 'rank', 'aria-hidden': 'true' }, String(rank)));
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

    return h('li', { class: 'pick', 'data-pid': pid }, [
      h('div', { class: 'ptop' }, [
        media(card, false, rank),
        h('div', { class: 'info' }, [
          h('p', { class: 'name' }, card.name),
          h('p', { class: 'brand' }, [card.brand, card.family_label ? ' · ' + card.family_label : ''].join(''))
        ]),
        card.match_score != null ? h('span', { class: 'score', title: t('match') }, t('matchFmt', { n: Math.round(card.match_score) })) : null
      ]),
      card.reason ? h('p', { class: 'reason' }, plain(card.reason)) : null,
      keyNotes.length ? h('ul', { class: 'tags' }, keyNotes.map(function (x) { return h('li', { class: 'tag' }, x); })) : null,
      h('div', { class: 'meta' }, meta),
      detail,
      h('div', { class: 'actions' }, [
        url ? h('a', {
          class: 'btn ghost', href: url, target: '_blank', rel: 'noopener noreferrer', 'data-act': 'view',
          onclick: function () { onView(card, rank, 'view_product'); }
        }, [t('viewProduct'), h('span', { icon: 'external' })]) : h('span', { style: 'flex:1' }),
        h('button', { class: 'tbtn', type: 'button', 'data-act': 'up', 'aria-label': t('thumbsUp'), title: t('thumbsUp'), 'aria-pressed': 'false', icon: 'up', onclick: function () { onThumb(pid, 1); } }),
        h('button', { class: 'tbtn', type: 'button', 'data-act': 'down', 'aria-label': t('thumbsDown'), title: t('thumbsDown'), 'aria-pressed': 'false', icon: 'down', onclick: function () { onThumb(pid, -1); } }),
        h('button', { class: 'tbtn heart', type: 'button', 'data-act': 'save', 'aria-label': t('save'), title: t('save'), 'aria-pressed': 'false', icon: 'heart', onclick: function () { onHeart(card); } })
      ])
    ]);
  }

  function renderResults(e) {
    var r = e.reply, picks = (r.picks || []).slice(0, 3);
    var kids = [h('div', { class: 'rhead' }, h('h3', null, t('resultsTitle')))];
    if (r.fallback_used) kids.push(fallbackNote());
    kids.push(h('ol', { class: 'wrap', style: 'margin:0;padding:0;list-style:none;gap:10px' }, picks.map(function (p, i) { return renderPick(p, i + 1, e); })));

    var L = r.layering;
    if (L && L.partner) {
      var partner = L.partner, purl = safeUrl(partner.product_url);
      var base = picks.filter(function (p) { return p.perfume_id === L.base_perfume_id; })[0];
      var onLayer = function (how) {
        track('layering_clicked', { base_perfume_id: L.base_perfume_id, partner_id: partner.perfume_id, action: how });
        if (how === 'view_product') postFeedback(partner.perfume_id, S.thumbs[partner.perfume_id] || null, true);
      };
      kids.push(h('div', { class: 'layer', 'data-layer': '' }, [
        h('div', { class: 'lab' }, [h('span', { icon: 'layers' }), t('layerWith')]),
        h('div', { class: 'lrow' }, [
          media(partner, true),
          h('div', { class: 'info' }, [
            h('p', { class: 'name' }, partner.name),
            h('p', { class: 'brand' }, [partner.brand, base ? t('layerOn', { name: base.name }) : partner.family_label].filter(Boolean).join(' · '))
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
      R.wl.appendChild(h('div', { class: 'wlitem', 'data-pid': c.perfume_id }, [
        media(c, true),
        h('div', { class: 'info' }, [
          h('p', { class: 'name' }, c.name),
          h('p', { class: 'brand' }, c.brand + (c.family_label ? ' · ' + c.family_label : '')),
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
      push({ k: 'start' });
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
    S.quiz = null;
    S.entries.slice().forEach(removeEntry);
    R.consent.hidden = true;
    setTab('chat');
    push({ k: 'start' });
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

  function mount() {
    if (!host.isConnected) document.body.appendChild(host);
    if (/[?&#]psa_open=1\b/.test(location.search + location.hash)) openPanel();
  }
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);

  window.PerfumeWidget = {
    open: openPanel,
    close: closePanel,
    setLang: setLang,
    get lang() { return S.lang; },
    get sessionId() { return S.sessionId; }
  };
})();
