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
  },
};

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
  return { id: 'guided_q', question: L.gLoved, multi: true, index: 2, max_index: 5, ask_reason: L.gReason,
          options: L.gLovedOpts.map(([id, label]) => ({ id, label })) };
}

function guidedReply(lang, sid, question, extra = {}) {
  return { session_id: sid, language: lang, reply: question.question, picks: [], layering: null, chips: [],
          next_question: question, fallback_used: false, intent: 'chat', profile: {}, guided: true, profile_summary: [], ...extra };
}

function guidedPicksReply(lang, sid, extra = {}) {
  const L = T[lang];
  return picksReply(lang, sid, { reply: L.gReply, guided: true, profile_summary: L.gSummary.map(([id, label]) => ({ id, label })), ...extra });
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
      if (state.guidedStep === 1) { state.guidedStep = 2; return json(200, guidedReply(lang, sid, guidedLovedQuestion(lang))); }
      if (state.guidedStep === 2) { state.guidedStep = 0; return json(200, guidedPicksReply(lang, sid)); }
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

// Answers guided match's instant first question (single tap, sends immediately), then its second, AI-authored
// question (multi-select: two chips + Continue), then waits for the picks. Exercises single-tap-send,
// multi-select + Continue, the progress label, and the "what I learned" summary on the results card.
async function runGuided(page, lang = 'en') {
  const L = T[lang];
  await page.locator('[data-start=guided]').click();
  const q1 = page.locator('.quiz').first();
  await q1.waitFor();
  await q1.locator('.chip').first().click();
  const q2 = page.locator('.quiz').first();
  await q2.waitFor();
  assert.match(await q2.textContent(), lang === 'ar' ? /من 5 كحد أقصى/ : /Question 2 of up to 5/, 'progress label shows question 2 of up to 5');
  assert.ok((await q2.textContent()).includes(L.gReason), 'ask_reason hint renders');
  await q2.locator('.chip').nth(0).click();
  await q2.locator('.chip').nth(1).click();
  await q2.locator('.btn.primary').click();
  await page.locator('[data-results]').first().waitFor();
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
  const q2 = page.locator('.quiz').first();
  await q2.waitFor();
  assert.match(await q2.textContent(), /Which scents do you love\?/, 'skip advances to the next question, not a repeat');
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
  await runGuided(page);
  const startCall = calls(log, '/api/guide/start');
  assert.equal(startCall.length, 1, 'guide/start posted once');
  assert.deepEqual(startCall[0].body, { session_id: 'sess-123', lang: 'en' });
  assert.match(startCall[0].contentType, /application\/json/);
  const guidedChats = calls(log, '/api/chat');
  assert.equal(guidedChats.length, 2, 'one /api/chat per guided answer');
  assert.deepEqual(guidedChats[0].body, { session_id: 'sess-123', message: 'For me', lang: 'en' });
  assert.deepEqual(guidedChats[1].body, { session_id: 'sess-123', message: 'Vanilla, Rose', lang: 'en' });
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
  assert.equal(chats.length, 4, '2 guided answers + 1 failed + 1 retried chat message');
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
  await runGuided(page, 'ar');
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
