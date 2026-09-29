// Smoke test for app/static/widget.js in its default floating (embeddable) mode. Plain node script
// (not the Playwright test runner). Uses app/static/embed-test.html as the floating-mode fixture page
// -- the product homepage at "/" mounts the widget in full-page mode instead (data-mode="page").
//
//   npx http-server app/static -p 8089 -s &
//   node tests/e2e_widget.spec.mjs            # BASE_URL=http://localhost:8089 SHOT_DIR=/tmp by default
//
// Every /api/** call is intercepted with fixture JSON, so no backend is needed.
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import assert from 'node:assert/strict';

let pw;
try { pw = await import('playwright'); } catch {
  const globalRoot = execSync('npm root -g').toString().trim();
  pw = createRequire(globalRoot + '/')('playwright');
}
const { chromium } = pw;

const BASE = process.env.BASE_URL || 'http://localhost:8089';
const SHOT_DIR = process.env.SHOT_DIR || '/tmp';
mkdirSync(SHOT_DIR, { recursive: true });

// ------------------------------------------------------------------ fixtures
const T = {
  en: {
    greeting: "Hi! I'm your scent guide. Let's find something you'll love.",
    q: ['Which notes do you love?', 'Anything you want to avoid?', 'What mood are you after?', 'How strong should it be?', "What's your budget?"],
    reply: 'Here are three picks built around warm vanilla and soft woods.',
    reasons: ['Creamy vanilla with a dry woody finish, close to what you described.', 'Rose and oud for evenings, with a soft amber base.', 'A lighter, fresher take for daytime wear.'],
    layer: 'Citrus on top of woods: bright opening, grounded finish.',
    chips: [['less_sweet', 'Less sweet'], ['fresher', 'Fresher'], ['cheaper', 'Cheaper'], ['stronger', 'Stronger'], ['lighter', 'Lighter'], ['more_like:p1', 'More like pick 1']],
    fam: ['Gourmand', 'Amber or oriental', 'Fresh or citrus', 'Woody'],
    strength: ['Strong', 'Very strong', 'Light', 'Moderate'],
    ask: 'Do you prefer it sweet or fresh?', opts: [['sweet', 'Sweet'], ['fresh', 'Fresh']],
    gFor: 'Who is this perfume for?', gForOpts: [['self', 'For me'], ['gift_her', 'A gift for her'], ['gift_him', 'A gift for him'], ['gift_unsure', 'A gift, unsure of their taste']],
    gLoved: 'Which scents do you love?', gLovedOpts: [['vanilla', 'Vanilla'], ['rose', 'Rose'], ['oud', 'Oud'], ['citrus', 'Citrus']],
    gReason: 'So I can match your taste.',
    gReply: "Here's what I learned about you, and three picks that fit.",
    gSummary: [['for', 'For: me'], ['loves', 'Loves: vanilla, rose']],
    gShowPicksReply: 'Here are three picks from what you told me so far.',
    gScen: 'Pick the moments you want this scent for', gScenHint: 'Choose up to three.',
    gScenOpts: [['beach', 'Barefoot on a beach at sunset', 'Salt air, warm skin, golden light', 'sun_waves', 'aquatic'],
      ['rooftop', 'Walking into a rooftop party', 'City lights and every eye on you', 'sparkle', 'amber'],
      ['fireside', 'Wrapped in cashmere by the fire', 'Soft, warm and close to the skin', 'flame', 'gourmand'],
      ['garden', 'A spring garden in full bloom', 'Fresh petals and dewy green leaves', 'petals', 'floral'],
      ['date', 'A candlelit first date', 'Close, warm and quietly unforgettable', 'candle', 'fruity']],
    gMoment: 'Starting with the beach, which moment feels just right?',
    gMomentOpts: [['beach_sunrise_swim', 'Sunrise swim, salty skin', 'Crisp, airy and barely there', 'sun_waves', 'aquatic'],
      ['beach_golden_hour', 'Golden hour on the sand', 'Juicy fruit on sun-warmed skin', 'sun_waves', 'fruity'],
      ['beach_island', 'A tropical island escape', 'Coconut, white flowers, soft vanilla', 'sun_waves', 'floral']],
    gFeel: ['feel', 'Feel: Sunrise swim, salty skin · Walking into a rooftop party'],
  },
  ar: {
    greeting: 'مرحباً! أنا دليلك إلى العطور. لنجد عطراً تحبه.',
    q: ['ما النفحات التي تحبها؟', 'هل هناك نفحات تريد تجنبها؟', 'ما المزاج الذي تبحث عنه؟', 'ما مدى قوة العطر التي تفضلها؟', 'ما ميزانيتك؟'],
    reply: 'إليك ثلاثة اختيارات مبنية على الفانيليا الدافئة والأخشاب الناعمة.',
    reasons: ['فانيليا كريمية مع لمسة خشبية جافة، قريبة مما وصفته.', 'ورد وعود للمساء مع قاعدة عنبرية ناعمة.', 'خيار أخف وأكثر انتعاشاً للنهار.'],
    layer: 'حمضيات فوق الأخشاب: افتتاحية مشرقة وقاعدة راسخة.',
    chips: [['less_sweet', 'أقل حلاوة'], ['fresher', 'أكثر انتعاشاً'], ['cheaper', 'أرخص'], ['stronger', 'أقوى'], ['lighter', 'أخف'], ['more_like:p1', 'أقرب إلى الاختيار 1']],
    fam: ['حلو (غورماند)', 'عنبري شرقي', 'منعش وحمضي', 'خشبي'],
    strength: ['قوي', 'قوي جداً', 'خفيف', 'متوسط'],
    ask: 'هل تفضله حلواً أم منعشاً؟', opts: [['sweet', 'حلو'], ['fresh', 'منعش']],
    gFor: 'لمن هذا العطر؟', gForOpts: [['self', 'لي أنا'], ['gift_her', 'هدية لها'], ['gift_him', 'هدية له'], ['gift_unsure', 'هدية، ولا أعرف ذوقها بدقة']],
    gLoved: 'ما الروائح التي تحبها؟', gLovedOpts: [['vanilla', 'فانيليا'], ['rose', 'ورد'], ['oud', 'عود'], ['citrus', 'حمضيات']],
    gReason: 'لأتمكن من مطابقة ذوقك.',
    gReply: 'إليك ما تعلمته عنك، وثلاثة اختيارات تناسبك.',
    gSummary: [['for', 'لِـ: لي'], ['loves', 'يحب: فانيليا، ورد']],
    gShowPicksReply: 'إليك ثلاثة اختيارات بناءً على ما أخبرتني به حتى الآن.',
    gScen: 'اختر اللحظات التي تريد أن يرافقك فيها هذا العطر', gScenHint: 'اختر حتى ثلاث لحظات.',
    gScenOpts: [['beach', 'حافي القدمين على شاطئ الغروب', 'نسيم مالح وبشرة دافئة وضوء ذهبي', 'sun_waves', 'aquatic'],
      ['rooftop', 'أدخل حفلة راقية على السطح', 'أضواء المدينة وكل الأنظار نحوك', 'sparkle', 'amber'],
      ['fireside', 'ملتفّ بالكشمير قرب المدفأة', 'ناعم ودافئ وقريب من البشرة', 'flame', 'gourmand'],
      ['garden', 'حديقة ربيعية في أوج تفتّحها', 'بتلات طازجة وأوراق خضراء ندية', 'petals', 'floral'],
      ['date', 'موعد أول على ضوء الشموع', 'قريب ودافئ ولا يُنسى', 'candle', 'fruity']],
    gMoment: 'لنبدأ مع أجواء الشاطئ: أي لحظة تبدو مثالية؟',
    gMomentOpts: [['beach_sunrise_swim', 'سباحة الفجر وملح على البشرة', 'منعش وخفيف كالنسيم', 'sun_waves', 'aquatic'],
      ['beach_golden_hour', 'الساعة الذهبية على الرمال', 'فاكهة عصيرية على بشرة دفّأتها الشمس', 'sun_waves', 'fruity'],
      ['beach_island', 'هروب إلى جزيرة استوائية', 'جوز الهند وزهور بيضاء وفانيليا ناعمة', 'sun_waves', 'floral']],
    gFeel: ['feel', 'الأجواء: سباحة الفجر وملح على البشرة · أدخل حفلة راقية على السطح'],
  },
};

// A hostile option: every field must render as plain text, the motif and colour keys are whitelisted.
const HOSTILE_OPT = { id: 'x', label: '<b>Night</b> swim', caption: '<img src=x onerror="window.__pwned=1">',
  motif: '<svg onload="window.__pwned=1">', family: 'javascript:alert(1)' };

function quiz(lang) {
  const q = T[lang].q;
  const ar = lang === 'ar';
  return [
    { id: 'liked_notes', question: q[0], multi: true, options: [['vanilla', ar ? 'فانيليا' : 'Vanilla'], ['rose', ar ? 'ورد' : 'Rose'], ['oud', ar ? 'عود' : 'Oud'], ['bergamot', ar ? 'برغموت' : 'Bergamot'], ['skip', ar ? 'تخطَّ' : 'Skip']].map(([id, label]) => ({ id, label })) },
    { id: 'disliked_notes', question: q[1], multi: true, options: [['patchouli', ar ? 'باتشولي' : 'Patchouli'], ['sea notes', ar ? 'نفحات بحرية' : 'Sea notes'], ['skip', ar ? 'لا شيء' : 'Nothing']].map(([id, label]) => ({ id, label })) },
    { id: 'mood', question: q[2], multi: true, options: [['cozy', ar ? 'دافئ ومريح' : 'Warm and cozy'], ['elegant', ar ? 'أنيق' : 'Elegant'], ['energetic', ar ? 'منعش ونشيط' : 'Fresh and energetic']].map(([id, label]) => ({ id, label })) },
    { id: 'strength', question: q[3], multi: false, options: [['2', ar ? 'خفيف' : 'Light'], ['3', ar ? 'متوسط' : 'Moderate'], ['4', ar ? 'قوي' : 'Strong']].map(([id, label]) => ({ id, label })) },
    { id: 'budget', question: q[4], multi: false, options: [['300', ar ? 'حتى 300 درهم' : 'Up to AED 300'], ['600', ar ? 'حتى 600 درهم' : 'Up to AED 600'], ['0', ar ? 'بدون ميزانية' : 'No budget']].map(([id, label]) => ({ id, label })) },
  ];
}

function card(lang, i, over = {}) {
  const L = T[lang];
  const base = [
    { perfume_id: 'p1', name: 'Vanilla Dune', brand: 'Maison Sable', family: 'gourmand', price_aed: 350, price_source: 'catalogue', price_label: lang === 'ar' ? '350 درهم' : 'AED 350', image_url: null, match_score: 92, key_notes: ['vanilla', 'tonka bean', 'sandalwood'] },
    { perfume_id: 'p2', name: 'Rose Oud Nuit', brand: 'Atelier Noor', family: 'amber', price_aed: 520, price_source: 'estimated', price_label: lang === 'ar' ? '~520 درهم (تقديري)' : '~AED 520 (est.)', image_url: '/missing-image.jpg', match_score: 87, key_notes: ['rose', 'oud', 'amber'] },
    { perfume_id: 'p3', name: 'Bergamot Morning', brand: 'Citrine', family: 'fresh', price_aed: null, price_source: 'none', price_label: '', image_url: null, match_score: 74, key_notes: ['bergamot', 'neroli', 'white musk'] },
    { perfume_id: 'p4', name: 'Cedar Veil', brand: 'Northwood', family: 'woody', price_aed: 280, price_source: 'catalogue', price_label: lang === 'ar' ? '280 درهم' : 'AED 280', image_url: null, match_score: null, key_notes: ['cedar', 'vetiver'] },
  ][i];
  return {
    ...base,
    family_label: L.fam[i],
    notes: { top: ['bergamot', 'pink pepper'], heart: base.key_notes.slice(0, 2), base: ['musk', 'amber'] },
    accords: ['sweet', 'woody'],
    strength: [4, 5, 2, 3][i],
    strength_label: L.strength[i],
    product_url: `https://example.com/p/${base.perfume_id}`,
    description: 'A seed-catalogue description used for the prototype.',
    reason: L.reasons[i] || null,
    rating: 4.2, rating_count: 120,
    ...over,
  };
}

function picksReply(lang, sid, extra = {}) {
  const L = T[lang];
  return {
    session_id: sid, language: lang, reply: L.reply,
    picks: [card(lang, 0), card(lang, 1), card(lang, 2)],
    layering: { base_perfume_id: 'p1', partner: card(lang, 3), reason: L.layer },
    chips: L.chips.map(([id, label]) => ({ id, label })),
    next_question: null, fallback_used: false, intent: 'recommend', profile: {},
    guided: false, profile_summary: [],
    ...extra,
  };
}

// ------------------------------------------------------------------ guided match fixtures
function guidedForQuestion(lang) {
  const L = T[lang];
  return { id: 'guided_for', question: L.gFor, multi: false, index: 1, max_index: 5,
          options: L.gForOpts.map(([id, label]) => ({ id, label })) };
}

function guidedLovedQuestion(lang) {
  const L = T[lang];
  return { id: 'guided_q', question: L.gLoved, multi: true, index: 3, max_index: 5, ask_reason: L.gReason,
          options: L.gLovedOpts.map(([id, label]) => ({ id, label })) };
}

const cardOpts = (list) => list.map(([id, label, caption, motif, family]) => ({ id, label, caption, motif, family }));

function guidedScenarioQuestion(lang) {
  const L = T[lang];
  return { id: 'scenario', topic: 'scenario', question: L.gScen, multi: true, index: 2, max_index: 5, ask_reason: L.gScenHint,
          options: [...cardOpts(L.gScenOpts), HOSTILE_OPT] };
}

function guidedMomentQuestion(lang) {
  const L = T[lang];
  return { id: 'scenario_moment', topic: 'scenario_moment', question: L.gMoment, multi: false, index: 3, max_index: 5,
          options: cardOpts(L.gMomentOpts) };
}

function guidedReply(lang, sid, question, extra = {}) {
  return { session_id: sid, language: lang, reply: question.question, picks: [], layering: null, chips: [],
          next_question: question, fallback_used: false, intent: 'chat', profile: {}, guided: true, profile_summary: [], ...extra };
}

function guidedPicksReply(lang, sid, extra = {}) {
  const L = T[lang];
  const summary = [L.gSummary[0], L.gFeel, ...L.gSummary.slice(1)];
  return picksReply(lang, sid, { reply: L.gReply, guided: true, profile_summary: summary.map(([id, label]) => ({ id, label })), ...extra });
}

// ------------------------------------------------------------------ mock backend
function mockApi(page, log) {
  const state = { failNextChat: false, wishlist: [], guidedStep: 0 };
  page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    let body = null;
    try { body = req.postDataJSON(); } catch { body = null; }
    log.push({ method: req.method(), path, body, query: Object.fromEntries(url.searchParams), contentType: req.headers()['content-type'] || '' });
    const lang = (body && body.lang) || 'en';
    const sid = 'sess-123';
    const json = (status, data) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });

    if (path === '/api/session') return json(200, { session_id: sid, language: lang, greeting: T[lang].greeting, quiz: quiz(lang), brand_filter: '' });
    if (path === '/api/quiz') return json(200, picksReply(lang, sid));
    if (path === '/api/guide/start') {
      state.guidedStep = 1;
      return json(200, guidedReply(lang, sid, guidedForQuestion(lang)));
    }
    if (path === '/api/guide/finish') {
      state.guidedStep = 0;
      return json(200, guidedPicksReply(lang, sid, { reply: T[lang].gShowPicksReply }));
    }
    if (path === '/api/chat') {
      if (state.failNextChat) { state.failNextChat = false; return json(500, { error: 'boom' }); }
      if (/ask me/i.test(body.message)) {
        return json(200, { session_id: sid, language: lang, reply: 'Happy to help.', picks: [], layering: null, chips: [], next_question: { id: 'q', question: T[lang].ask, multi: false, options: T[lang].opts.map(([id, label]) => ({ id, label })) }, fallback_used: false, intent: 'chat', profile: {}, guided: false, profile_summary: [] });
      }
      // guided match: Q1 -> scenario cards -> moment cards -> picks; skipping the scenario grid falls back to an
      // ordinary AI-written question (plain chips), as the server does
      const skipped = /^(Skip|تخطي)$/.test(body.message);
      if (state.guidedStep === 1) { state.guidedStep = 2; return json(200, guidedReply(lang, sid, guidedScenarioQuestion(lang))); }
      if (state.guidedStep === 2 && skipped) { state.guidedStep = 4; return json(200, guidedReply(lang, sid, guidedLovedQuestion(lang))); }
      if (state.guidedStep === 2) { state.guidedStep = 3; return json(200, guidedReply(lang, sid, guidedMomentQuestion(lang))); }
      if (state.guidedStep === 3 || state.guidedStep === 4) { state.guidedStep = 0; return json(200, guidedPicksReply(lang, sid)); }
      return json(200, picksReply(lang, sid));
    }
    if (path === '/api/refine') return json(200, picksReply(lang, sid, { fallback_used: true, reply: lang === 'ar' ? 'أقل حلاوة، كما طلبت.' : 'Less sweet, as requested.' }));
    if (path === '/api/wishlist' && req.method() === 'POST') {
      for (const id of body.perfume_ids) if (!state.wishlist.some((c) => c.perfume_id === id)) state.wishlist.push(card(lang, ['p1', 'p2', 'p3', 'p4'].indexOf(id)));
      return json(200, { wishlist: state.wishlist });
    }
    if (path === '/api/wishlist') return json(200, { wishlist: state.wishlist });
    if (path === '/api/feedback' || path === '/api/events') return json(200, { ok: true });
    return json(404, { error: 'not found' });
  });
  return state;
}

// ------------------------------------------------------------------ helpers
const launch = () => chromium.launch(existsSync('/opt/pw-browsers/chromium') ? { executablePath: '/opt/pw-browsers/chromium' } : {}).catch(() => chromium.launch());
const calls = (log, path, method = 'POST') => log.filter((c) => c.path === path && c.method === method);
const eventNames = (log) => calls(log, '/api/events').map((c) => c.body.name);

// Answers guided match's instant first question (single tap, sends immediately), then the scenario card grid
// (multi-select up to 3, "Continue with n"), then the moment cards (single tap), then waits for the picks.
// Exercises single-tap-send, multi-select + the cap, the progress label, the motif whitelist, text-only
// rendering of server strings, "Something else", and the "what I learned" summary on the results card.
async function runGuided(page, lang = 'en', shotPrefix = null) {
  const L = T[lang];
  const ar = lang === 'ar';
  await page.locator('[data-start=guided]').click();
  const q1 = page.locator('.quiz').first();
  await q1.waitFor();
  await q1.locator('.chip').first().click();

  // Q2: scenario cards
  const q2 = page.locator('.quiz.scn-q').first();
  await q2.waitFor();
  assert.match(await q2.textContent(), ar ? /السؤال 2 من 5 كحد أقصى/ : /Question 2 of up to 5/, 'progress label shows question 2 of up to 5');
  assert.ok((await q2.textContent()).includes(L.gScenHint), 'the "up to three" hint renders');
  const cards = q2.locator('.scard');
  assert.equal(await cards.count(), L.gScenOpts.length + 1, 'one card per option');
  assert.equal(await q2.locator('.chip').count(), 0, 'scenario options render as cards, not chips');
  assert.equal(await cards.first().locator('.scard-art svg').count(), 1, 'a known motif draws its SVG');
  assert.equal(await cards.first().getAttribute('data-fam'), 'aquatic', 'the card wears its family colour');
  assert.ok((await cards.first().textContent()).includes(L.gScenOpts[0][2]), 'the sub-caption renders');
  const hostile = q2.locator('.scard[data-id=x]');
  assert.equal(await hostile.locator('.scard-art svg').count(), 0, 'an unknown motif draws nothing');
  assert.equal(await hostile.getAttribute('data-fam'), null, 'an unknown family key is ignored');
  assert.equal(await hostile.locator('b').textContent(), HOSTILE_OPT.label, 'labels are text, never markup');
  assert.equal(await hostile.locator('img').count(), 0);
  const cont = q2.locator('[data-continue]');
  assert.equal(await cont.isDisabled(), true, 'Continue waits for a pick');
  if (shotPrefix) {
    await page.waitForTimeout(450);
    await q2.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOT_DIR}/${shotPrefix}-q2.png` });
  }
  await cards.nth(0).click();
  await q2.locator('.scard').nth(1).click();
  assert.equal(await page.locator('.quiz.scn-q .scard').nth(0).getAttribute('aria-pressed'), 'true');
  assert.equal((await page.locator('.quiz.scn-q [data-continue]').textContent()).trim(), ar ? 'متابعة (2)' : 'Continue with 2');
  // the cap: a third pick is fine, a fourth is refused until one is released
  await page.locator('.quiz.scn-q .scard').nth(2).click();
  assert.equal(await page.locator('.quiz.scn-q .scard').nth(3).getAttribute('aria-disabled'), 'true', 'a fourth card is disabled at 3');
  await page.locator('.quiz.scn-q .scard').nth(3).click({ force: true });
  assert.equal(await page.locator('.quiz.scn-q .scard[aria-pressed=true]').count(), 3, 'never more than 3 chosen');
  await page.locator('.quiz.scn-q .scard').nth(2).click();
  assert.equal(await page.locator('.quiz.scn-q .scard[aria-pressed=true]').count(), 2);
  if (shotPrefix) await page.screenshot({ path: `${SHOT_DIR}/${shotPrefix}-q2-selected.png` });
  await page.locator('.quiz.scn-q [data-continue]').click();

  // Q3: moment cards, one tap sends
  const q3 = page.locator('.quiz.scn-q').first();
  await q3.waitFor();
  assert.ok((await q3.textContent()).includes(L.gMoment));
  assert.equal(await q3.locator('.scn.big .scard:not(.other)').count(), 3);
  assert.equal(await q3.locator('.scard[aria-pressed]').count(), 0, 'single-select moments carry no pressed state');
  await q3.locator('[data-other]').click();
  assert.equal(await page.locator('.input').getAttribute('placeholder'), ar ? 'صف لحظتك…' : 'Describe your moment…', '"Something else" hands over to the composer');
  if (shotPrefix) {
    await page.waitForTimeout(450);
    await page.screenshot({ path: `${SHOT_DIR}/${shotPrefix}-q3.png` });
  }
  await q3.locator('.scard').first().click();
  await page.locator('[data-results]').first().waitFor();
  const feel = page.locator('[data-results]').first().locator('.tags.learned .tag[data-k=feel]');
  assert.equal((await feel.textContent()).trim(), L.gFeel[1], 'the Feel tag leads the summary');
}

// Skip (never repeats a question) and "Show my picks now" (available from question 2 onward).
async function guidedControlsFlow(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const log = [];
  mockApi(page, log);
  await page.goto(BASE + '/');
  await page.locator('[data-start=guided]').click();
  const q1 = page.locator('.quiz').first();
  await q1.waitFor();
  assert.equal(await page.locator('.quiz .btn', { hasText: 'Show my picks now' }).count(), 0, 'no show-picks-now on question 1');
  await q1.locator('.btn', { hasText: 'Skip' }).click();
  const q2 = page.locator('.quiz.scn-q').first();
  await q2.waitFor();
  assert.match(await q2.textContent(), /Pick the moments you want this scent for/, 'skip advances to the scenario cards');
  // keyboard: Space toggles a card and focus stays on it through the re-render
  await page.locator('.quiz.scn-q .scard').nth(1).focus();
  await page.keyboard.press('Space');
  assert.equal(await page.locator('.quiz.scn-q .scard').nth(1).getAttribute('aria-pressed'), 'true');
  assert.equal(await page.evaluate(() => document.querySelector('#psa-widget-host').shadowRoot.activeElement.getAttribute('data-id')), 'rooftop', 'focus survives the toggle');
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('.quiz.scn-q .scard').nth(1).getAttribute('aria-pressed'), 'false');
  // desktop page mode: five across
  const tops = await page.locator('.quiz.scn-q .scard').evaluateAll((els) => els.slice(0, 5).map((el) => Math.round(el.getBoundingClientRect().top)));
  assert.equal(new Set(tops).size, 1, 'the first five cards share one row on desktop');
  await page.locator('.quiz.scn-q .btn', { hasText: 'Skip' }).click();
  const q3 = page.locator('.quiz:not(.scn-q)').first();
  await q3.waitFor();
  assert.match(await q3.textContent(), /Which scents do you love\?/, 'skipping the cards falls back to an ordinary question');
  await page.locator('.quiz .btn', { hasText: 'Show my picks now' }).click();
  await page.locator('[data-results]').first().waitFor();
  assert.equal(calls(log, '/api/guide/finish').length, 1, 'show-picks-now posts to /api/guide/finish');
  assert.deepEqual(calls(log, '/api/guide/finish')[0].body, { session_id: 'sess-123', lang: 'en' });
  assert.match(await page.locator('.msg.bot').last().textContent(), /Here are three picks from what you told me so far\./);
  assert.deepEqual(errors, []);
  await ctx.close();
}

// ------------------------------------------------------------------ mobile flow (full)
async function mobileFlow(browser) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/missing-image|404|500/.test(m.text())) errors.push(m.text()); });
  const log = [];
  const state = mockApi(page, log);

  await page.goto(BASE + '/embed-test.html');
  const launcher = page.locator('.launcher');
  await launcher.waitFor();
  assert.equal((await launcher.textContent()).trim(), 'Find your scent');
  await launcher.click();
  await page.locator('[data-start=guided]').waitFor();
  assert.equal(calls(log, '/api/session').length, 1, 'session created on open');
  assert.deepEqual(calls(log, '/api/session')[0].body, { lang: 'en' });

  // guided match -> results
  await runGuided(page, 'en', 's-mobile-en');
  const startCall = calls(log, '/api/guide/start');
  assert.equal(startCall.length, 1, 'guide/start posted once');
  assert.deepEqual(startCall[0].body, { session_id: 'sess-123', lang: 'en' });
  assert.match(startCall[0].contentType, /application\/json/);
  const guidedChats = calls(log, '/api/chat');
  assert.equal(guidedChats.length, 3, 'one /api/chat per guided answer');
  assert.deepEqual(guidedChats[0].body, { session_id: 'sess-123', message: 'For me', lang: 'en' });
  assert.deepEqual(guidedChats[1].body, { session_id: 'sess-123', message: 'Barefoot on a beach at sunset, Walking into a rooftop party', lang: 'en' });
  assert.deepEqual(guidedChats[2].body, { session_id: 'sess-123', message: 'Sunrise swim, salty skin', lang: 'en' });
  assert.equal(await page.locator('[data-results]').first().locator('.pick').count(), 3);
  assert.equal(await page.locator('[data-layer]').count(), 1);
  // "what I learned" summary tags above the picks
  assert.match(await page.locator('[data-results]').first().locator('.tags.learned').textContent(), /For: me/);
  assert.match(await page.locator('[data-results]').first().locator('.tags.learned').textContent(), /Loves: vanilla, rose/);
  // estimated price tooltip + placeholder + image error fallback
  assert.equal(await page.locator('.price.est').first().getAttribute('title'), 'Estimated price for the prototype');
  await page.waitForFunction(() => document.querySelector('#psa-widget-host').shadowRoot.querySelectorAll('.pick img').length === 0);

  // thumbs + view product
  await page.locator('.pick').first().locator('[data-act=up]').click();
  assert.equal(await page.locator('.pick').first().locator('[data-act=up]').getAttribute('aria-pressed'), 'true');
  const [popup] = await Promise.all([
    ctx.waitForEvent('page'),
    page.locator('.pick').first().locator('[data-act=view]').click(),
  ]);
  await popup.close();

  // chat with a server error first -> Try again
  state.failNextChat = true;
  await page.locator('.input').fill('Something warm for winter evenings');
  await page.locator('.input').press('Enter');
  await page.locator('[data-retry]').waitFor();
  assert.match(await page.locator('.err').textContent(), /something went wrong/i);
  await page.locator('[data-retry]').click();
  await page.waitForFunction(() => document.querySelector('#psa-widget-host').shadowRoot.querySelectorAll('[data-results]').length === 2);
  const chats = calls(log, '/api/chat');
  assert.equal(chats.length, 5, '3 guided answers + 1 failed + 1 retried chat message');
  assert.deepEqual(chats.at(-1).body, { session_id: 'sess-123', message: 'Something warm for winter evenings', lang: 'en' });
  assert.equal(await page.locator('.send').isDisabled(), true, 'send disabled with empty input');

  // next_question quick replies
  await page.locator('.input').fill('ask me something');
  await page.locator('.input').press('Enter');
  const quick = page.locator('.wrap .chips .chip', { hasText: 'Sweet' });
  await quick.waitFor();
  await quick.click();
  await page.waitForFunction(() => document.querySelector('#psa-widget-host').shadowRoot.querySelectorAll('[data-results]').length === 3);
  assert.equal(calls(log, '/api/chat').at(-1).body.message, 'Sweet');

  // refine
  await page.locator('[data-results]').last().locator('[data-chip=less_sweet]').click();
  await page.waitForFunction(() => document.querySelector('#psa-widget-host').shadowRoot.querySelectorAll('[data-results]').length === 4);
  assert.deepEqual(calls(log, '/api/refine')[0].body, { session_id: 'sess-123', chip: 'less_sweet', lang: 'en' });
  assert.match(await page.locator('[data-results]').last().textContent(), /AI is resting; showing rule-based picks/);
  assert.equal(await page.locator('[data-results]').first().locator('[data-chip]').count(), 0, 'old refine chips removed');

  // wishlist with consent
  await page.locator('[data-results]').last().locator('.pick').first().locator('[data-act=save]').click();
  await page.locator('.consent').waitFor();
  assert.match(await page.locator('.consent').textContent(), /Save picks to a wishlist for this session\?/);
  assert.equal(calls(log, '/api/wishlist').length, 0, 'nothing saved before consent');
  await page.locator('.consent .btn.primary').click();
  await page.waitForFunction(() => /Wishlist \(1\)/.test(document.querySelector('#psa-widget-host').shadowRoot.querySelectorAll('.tab')[1].textContent));
  assert.deepEqual(calls(log, '/api/wishlist')[0].body, { session_id: 'sess-123', perfume_ids: ['p1'], consent: true });
  // second save: no prompt again
  await page.locator('[data-results]').last().locator('.pick').nth(1).locator('[data-act=save]').click();
  await page.waitForFunction(() => /Wishlist \(2\)/.test(document.querySelector('#psa-widget-host').shadowRoot.querySelectorAll('.tab')[1].textContent));
  assert.equal(await page.locator('.consent').isVisible(), false);

  await page.locator('.tab').nth(1).click();
  await page.locator('.wlitem').first().waitFor();
  assert.equal(await page.locator('.wlitem').count(), 2);
  assert.ok(calls(log, '/api/wishlist', 'GET').some((c) => c.query.session_id === 'sess-123'));
  await page.screenshot({ path: `${SHOT_DIR}/widget-en-wishlist.png` });
  await page.locator('.tab').nth(0).click();

  // screenshot: scroll to first results card so picks are visible
  await page.evaluate(() => {
    const r = document.querySelector('#psa-widget-host').shadowRoot;
    const res = r.querySelectorAll('[data-results]')[3];
    r.querySelector('.list').scrollTop = res.offsetTop - 12;
  });
  await page.screenshot({ path: `${SHOT_DIR}/widget-en.png` });
  await page.locator('[data-results]').nth(3).locator('[data-layer]').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOT_DIR}/widget-en-layering.png` });

  // feedback + events
  const fb = calls(log, '/api/feedback');
  assert.deepEqual(fb[0].body, { session_id: 'sess-123', perfume_id: 'p1', thumbs: 1, clicked: false });
  assert.deepEqual(fb[1].body, { session_id: 'sess-123', perfume_id: 'p1', thumbs: 1, clicked: true });
  const names = new Set(eventNames(log));
  for (const n of ['widget_opened', 'guided_started', 'guided_question_shown', 'guided_answer', 'chat_message_sent', 'results_shown', 'pick_clicked', 'refine_used', 'wishlist_saved', 'feedback_given', 'error_shown', 'fallback_used']) {
    assert.ok(names.has(n), `event ${n} fired`);
  }
  assert.ok(calls(log, '/api/events').every((c) => c.body.session_id === 'sess-123'));

  // storage
  const stored = await page.evaluate(() => ({ sid: localStorage.getItem('psa_session_id') }));
  assert.equal(stored.sid, 'sess-123');

  // switch to Arabic in the header
  await page.locator('.langbtn').click();
  const app = page.locator('.psa');
  assert.equal(await app.getAttribute('dir'), 'rtl');
  assert.equal(await app.getAttribute('lang'), 'ar');
  assert.equal((await page.locator('.launcher').textContent()).trim(), 'اعثر على عطرك');
  assert.equal((await page.locator('.title').textContent()).trim(), 'اعثر على عطرك');
  assert.equal(await page.evaluate(() => localStorage.getItem('psa_lang')), 'ar');
  // subsequent requests carry lang=ar
  await page.locator('[data-results]').last().locator('[data-chip=cheaper]').click();
  await page.waitForFunction(() => document.querySelector('#psa-widget-host').shadowRoot.querySelectorAll('[data-results]').length === 5);
  assert.equal(calls(log, '/api/refine').at(-1).body.lang, 'ar');

  // close + launcher label in Arabic
  await page.locator('.iconbtn').last().click();
  assert.equal((await page.locator('.launcher').textContent()).trim(), 'اعثر على عطرك');

  assert.deepEqual(errors, [], 'no page errors');
  await ctx.close();
  return { log, events: [...names] };
}

// ------------------------------------------------------------------ Arabic page (data-lang="ar"), mobile + desktop
async function arabicFlow(browser, viewport, shot) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const log = [];
  mockApi(page, log);
  await page.goto(BASE + '/embed-test.html?lang=ar');
  const launcher = page.locator('.launcher');
  await launcher.waitFor();
  assert.equal((await launcher.textContent()).trim(), 'اعثر على عطرك');
  assert.equal(await page.locator('.psa').getAttribute('dir'), 'rtl');
  await launcher.click();
  await page.locator('[data-start=guided]').waitFor();
  assert.equal(calls(log, '/api/session')[0].body.lang, 'ar');
  await runGuided(page, 'ar', viewport.width < 500 ? 's-mobile-ar' : null);
  assert.equal(calls(log, '/api/guide/start')[0].body.lang, 'ar');
  assert.equal(calls(log, '/api/chat')[0].body.lang, 'ar');
  assert.match(await page.locator('[data-results]').first().locator('.tags.learned').textContent(), /لِـ: لي/);
  await page.evaluate(() => {
    const r = document.querySelector('#psa-widget-host').shadowRoot;
    const res = r.querySelector('[data-results]');
    r.querySelector('.list').scrollTop = res.offsetTop - 60;
  });
  await page.screenshot({ path: `${SHOT_DIR}/${shot}` });
  assert.deepEqual(errors, []);
  await ctx.close();
}

// ------------------------------------------------------------------ desktop English: panel + start screen + results
async function desktopFlow(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const log = [];
  mockApi(page, log);
  await page.goto(BASE + '/embed-test.html');
  await page.screenshot({ path: `${SHOT_DIR}/widget-en-desktop-closed.png` });
  await page.locator('.launcher').click();
  await page.locator('[data-start=chat]').waitFor();
  const box = await page.locator('.panel').boundingBox();
  assert.equal(Math.round(box.width), 420, 'desktop panel is 420px wide');
  assert.ok(box.x + box.width > 1240, 'panel sits bottom-right');
  await page.waitForTimeout(300); // let the open animation finish
  await page.screenshot({ path: `${SHOT_DIR}/widget-en-desktop-start.png` });
  await page.locator('[data-start=chat]').click();
  await page.locator('.input').fill('A fresh citrus scent for the office under 300 AED');
  await page.locator('.send').click();
  await page.locator('[data-results]').waitFor();
  await page.screenshot({ path: `${SHOT_DIR}/widget-en-desktop.png` });
  await ctx.close();
}

// ------------------------------------------------------------------ page mode: hero, starters, start over, reload-restore
async function pageModeFlow(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/missing-image|404|500/.test(m.text())) errors.push(m.text()); });
  const log = [];
  mockApi(page, log);

  await page.goto(BASE + '/');
  await page.locator('.hero-title').waitFor();
  assert.equal(await page.locator('.launcher').isVisible(), false, 'page mode has no visible launcher');
  assert.ok((await page.locator('.starter').count()) >= 4, 'starter prompts render');

  // clicking a starter sends it as a chat message and renders 3 picks
  const starterText = (await page.locator('.starter').first().textContent()).trim();
  await page.locator('.starter').first().click();
  await page.locator('[data-results]').waitFor();
  assert.equal(await page.locator('[data-results]').first().locator('.pick').count(), 3, 'starter click produces 3 picks');
  const firstChat = calls(log, '/api/chat');
  assert.equal(firstChat.length, 1, 'starter click posts one /api/chat');
  assert.equal(firstChat[0].body.message, starterText);

  // Start over returns to the hero
  await page.locator('.restart-link').click();
  await page.locator('.hero-title').waitFor();
  assert.equal(await page.locator('[data-results]').count(), 0, 'results cleared by start over');
  assert.ok((await page.locator('.starter').count()) >= 4, 'starters render again after start over');

  // produce a fresh conversation, then reload: it should restore from sessionStorage, not refetch
  await page.locator('.starter').nth(2).click();
  await page.locator('[data-results]').waitFor();
  assert.equal(await page.locator('[data-results]').first().locator('.pick').count(), 3);
  const chatCountBeforeReload = calls(log, '/api/chat').length;

  await page.reload();
  await page.locator('[data-results]').waitFor({ timeout: 5000 });
  assert.equal(await page.locator('[data-results]').first().locator('.pick').count(), 3, 'picks restored after reload');
  assert.equal(await page.locator('.hero-title').count(), 0, 'hero does not reappear when a conversation is restored');
  assert.equal(calls(log, '/api/chat').length, chatCountBeforeReload, 'no extra /api/chat call after reload -- restored, not refetched');
  // a refine chip on a restored pick still works (event handlers survive the restore)
  await page.locator('[data-results]').last().locator('[data-chip=less_sweet]').click();
  await page.waitForFunction(() => document.querySelector('#psa-widget-host').shadowRoot.querySelectorAll('[data-results]').length >= 2);
  assert.ok(calls(log, '/api/refine').length >= 1, 'refine on a restored card still posts');

  assert.deepEqual(errors, [], 'no page errors');
  await ctx.close();
}

const browser = await launch();
try {
  const res = await mobileFlow(browser);
  await arabicFlow(browser, { width: 390, height: 844 }, 'widget-ar.png');
  await arabicFlow(browser, { width: 1280, height: 800 }, 'widget-ar-desktop.png');
  await desktopFlow(browser);
  await pageModeFlow(browser);
  await guidedControlsFlow(browser);
  console.log('OK: widget smoke test passed');
  console.log('events seen:', res.events.sort().join(', '));
  console.log('screenshots in', SHOT_DIR);
} catch (e) {
  console.error('FAILED:', e);
  process.exitCode = 1;
} finally {
  await browser.close();
}
