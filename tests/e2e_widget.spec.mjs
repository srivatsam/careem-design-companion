// Smoke test for app/static/widget.js. Plain node script (not the Playwright test runner).
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
    ...extra,
  };
}

// ------------------------------------------------------------------ mock backend
function mockApi(page, log) {
  const state = { failNextChat: false, wishlist: [] };
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
    if (path === '/api/chat') {
      if (state.failNextChat) { state.failNextChat = false; return json(500, { error: 'boom' }); }
      if (/ask me/i.test(body.message)) {
        return json(200, { session_id: sid, language: lang, reply: 'Happy to help.', picks: [], layering: null, chips: [], next_question: { id: 'q', question: T[lang].ask, multi: false, options: T[lang].opts.map(([id, label]) => ({ id, label })) }, fallback_used: false, intent: 'chat', profile: {} });
      }
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

async function runQuiz(page) {
  await page.locator('[data-start=quiz]').click();
  for (let i = 0; i < 5; i++) {
    const q = page.locator('.quiz');
    await q.waitFor();
    await q.locator('.chip').first().click();
    if (i === 0) await q.locator('.chip').nth(1).click(); // multi-select: two liked notes
    await q.locator('[data-quiz-next]').click();
  }
  await page.locator('[data-results]').first().waitFor();
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

  await page.goto(BASE + '/');
  const launcher = page.locator('.launcher');
  await launcher.waitFor();
  assert.equal((await launcher.textContent()).trim(), 'Find your scent');
  await launcher.click();
  await page.locator('[data-start=quiz]').waitFor();
  assert.equal(calls(log, '/api/session').length, 1, 'session created on open');
  assert.deepEqual(calls(log, '/api/session')[0].body, { lang: 'en' });

  // quiz -> results
  await runQuiz(page);
  const quizCall = calls(log, '/api/quiz');
  assert.equal(quizCall.length, 1, 'quiz posted once');
  assert.deepEqual(quizCall[0].body, {
    session_id: 'sess-123',
    answers: { liked_notes: ['vanilla', 'rose'], disliked_notes: ['patchouli'], moods: ['cozy'], strength: 2, budget_aed: 300 },
    lang: 'en',
  });
  assert.match(quizCall[0].contentType, /application\/json/);
  assert.equal(await page.locator('[data-results]').first().locator('.pick').count(), 3);
  assert.equal(await page.locator('[data-layer]').count(), 1);
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
  assert.equal(chats.length, 2);
  assert.deepEqual(chats[1].body, { session_id: 'sess-123', message: 'Something warm for winter evenings', lang: 'en' });
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
  for (const n of ['widget_opened', 'quiz_started', 'quiz_completed', 'chat_message_sent', 'results_shown', 'pick_clicked', 'refine_used', 'wishlist_saved', 'feedback_given', 'error_shown', 'fallback_used']) {
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
  await page.goto(BASE + '/?lang=ar');
  const launcher = page.locator('.launcher');
  await launcher.waitFor();
  assert.equal((await launcher.textContent()).trim(), 'اعثر على عطرك');
  assert.equal(await page.locator('.psa').getAttribute('dir'), 'rtl');
  await launcher.click();
  await page.locator('[data-start=quiz]').waitFor();
  assert.equal(calls(log, '/api/session')[0].body.lang, 'ar');
  await runQuiz(page);
  assert.equal(calls(log, '/api/quiz')[0].body.lang, 'ar');
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
  await page.goto(BASE + '/');
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

const browser = await launch();
try {
  const res = await mobileFlow(browser);
  await arabicFlow(browser, { width: 390, height: 844 }, 'widget-ar.png');
  await arabicFlow(browser, { width: 1280, height: 800 }, 'widget-ar-desktop.png');
  await desktopFlow(browser);
  console.log('OK: widget smoke test passed');
  console.log('events seen:', res.events.sort().join(', '));
  console.log('screenshots in', SHOT_DIR);
} catch (e) {
  console.error('FAILED:', e);
  process.exitCode = 1;
} finally {
  await browser.close();
}
