/**
 * ADMIN PANEL POLLERLARI va 401 — tuzatish testlari.
 *
 * MUAMMO (jonli, nginx logi, tenant 28 "NICE SHOPPING GROUP", store):
 *   • kunda 697 ta 401 — hammasi badge pollerlaridan. Bir soatda 268 ta 401
 *     va AYNI IP'dan 265 ta 200: sog'lom mijoz (POS, api.js) va eski tokenli
 *     admin oynasi yonma-yon ishlayotgan edi.
 *   • `js/admin/core.js` tokenni BIR MARTA o'qirdi (`let token = ...`), 401
 *     bilan ishlamasdi, `catch {}` xatoni yutardi → `error-handler.js` dagi
 *     "401 → login" hech qachon ishlamasdi, `setInterval` abadiy davom etardi.
 *   • `/kitchen/orders` BARCHA biznes turlarida 15 sekundda bir marta:
 *     oshxonasi yo'q do'konda kuniga ~2 515 keraksiz so'rov (bitta do'kon
 *     badge trafigi 4 274 = serverning butun kunlik trafigining 29%i).
 *
 * GOLDEN QOIDALAR (aynan shu test tekshiradi):
 *   1. Token HAR so'rovda localStorage'dan o'qiladi (eski nusxa ishlatilmaydi)
 *   2. 401 → BIR MARTA `/auth/refresh` → yangi token bilan QAYTA urinish
 *   3. Refresh yiqilsa → tokenlar tozalanadi va login sahifasiga o'tadi
 *   4. `store` turida `/kitchen/orders` UMUMAN pollanmaydi
 *   5. Qaytarilmas 401 da pollerlar TO'XTAYDI (abadiy tsikl yo'q)
 *   6. Badge raqamlari AVVALGIDEK to'g'ri ko'rinadi
 *
 * Ishga tushirish:  node frontend/tests/test_admin_polling.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { resolve, extname, join } from 'path';

const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
               '.css': 'text/css', '.json': 'application/json' };
const server = createServer(async (req, res) => {
  try {
    const p = join(ROOT, decodeURIComponent(req.url.split('?')[0]));
    const body = await readFile(p);
    res.writeHead(200, { 'Content-Type': MIME[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch { res.writeHead(404); res.end('not found'); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${server.address().port}`;

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};
const checkTrue = (name, got) => check(name, !!got, true);

const mkToken = (bizType, mark) => `x.${Buffer.from(JSON.stringify({
  sub: '1', user_id: 1, tenant_id: 28, business_type: bizType,
  features: [], exp: 4102444800, type: 'access', mark,
})).toString('base64')}.y`;

/**
 * Sahifani ochadi.
 *   bizType      — 'store' | 'cafe'
 *   authMode     — 'ok' | 'expired' (birinchi so'rov 401) | 'dead' (refresh ham 401)
 */
async function ochish(browser, { bizType = 'store', authMode = 'ok' } = {}) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  const OLD = mkToken(bizType, 'old');
  const NEW = mkToken(bizType, 'new');
  // ⚠️ `addInitScript` HAR navigatsiyada ishlaydi. Qo'riqchisiz yozilsa
  // login'ga yo'naltirilgandan keyin tokenni QAYTA ekib qo'yadi: login.html
  // (525-qator) `access_token` ni ko'rib admin'ga qaytaradi → cheksiz
  // login↔admin tsikli. Bu TEST artefakti (prodda tokenni hech kim
  // qayta ekmaydi), lekin tekshirmoqchi bo'lgan xulqni butunlay yashiradi.
  // `sessionStorage` qo'riqchisi — bitta tabda faqat BIR MARTA ekiladi.
  await ctx.addInitScript(({ t, b }) => {
    if (sessionStorage.getItem('__seeded')) return;
    sessionStorage.setItem('__seeded', '1');
    localStorage.setItem('access_token', t);
    localStorage.setItem('refresh_token', 'R-TOKEN');
    localStorage.setItem('user', JSON.stringify({ id: 1, business_type: b, role: { name: 'admin' } }));
  }, { t: OLD, b: bizType });

  const calls = [];        // {path, bearer}
  const refreshCalls = [];
  const xatolar = [];
  page.on('pageerror', e => xatolar.push(String(e.message)));

  let refreshed = false;

  await page.route('**/api/v1/**', async (route) => {
    const u = new URL(route.request().url());
    const path = u.pathname.replace('/api/v1', '');
    const bearer = (route.request().headers()['authorization'] || '').replace('Bearer ', '');
    const json = (b, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) });

    // ── Refresh endpointi ────────────────────────────────────────────────
    if (path === '/auth/refresh') {
      refreshCalls.push(JSON.parse(route.request().postData() || '{}'));
      if (authMode === 'dead') return json({ detail: 'Yaroqsiz refresh token' }, 401);
      refreshed = true;
      return json({ access_token: NEW, refresh_token: 'R-TOKEN-2', token_type: 'bearer' });
    }

    calls.push({ path, bearer });

    // ── 401 rejimi: ESKI token bilan kelgan so'rov rad etiladi ───────────
    if (authMode !== 'ok' && bearer === OLD) {
      return json({ detail: 'Autentifikatsiya talab qilinadi' }, 401);
    }

    if (path === '/kitchen/orders')            return json({ pending: [{}, {}], preparing: [{}] });
    if (path === '/inventory/low-stock')       return json([{}, {}, {}, {}]);
    if (path === '/debts/summary')             return json({ total_debtors: 2, total_debt: 500000, total_overdue: 0, open_count: 5, partial_count: 2 });
    if (path === '/analytics/reorder-alerts')  return json({ total: 7, items: [] });
    if (path === '/discounts/active')          return json([]);
    if (path === '/stop-list')                 return json([]);
    return json({ items: [], total: 0, page: 1, page_size: 20, total_pages: 1 });
  });

  await page.goto(`${BASE}/app/admin.html`, { waitUntil: 'domcontentloaded' });
  // Modul blok (`window.__xenoraApi`) va DOMContentLoaded tugashini kutamiz
  await page.waitForFunction(() => typeof window.apiFetch === 'function' && !!window.__xenoraApi,
                             null, { timeout: 10000 }).catch(() => {});
  return { page, ctx, calls, refreshCalls, xatolar, OLD, NEW, refreshed: () => refreshed };
}

const nechta = (calls, path) => calls.filter(c => c.path === path).length;
const kut = (ms) => new Promise(r => setTimeout(r, ms));

const browser = await chromium.launch();

// ══════════════════════════════════════════════════════════════════════════
// 1) MODUL ULANISHI — refresh mexanizmi `window` da bormi
// ══════════════════════════════════════════════════════════════════════════
{
  const t = await ochish(browser, { bizType: 'store' });
  const bor = await t.page.evaluate(() =>
    !!(window.__xenoraApi && typeof window.__xenoraApi.refreshAccessToken === 'function'));
  checkTrue('api.js refresh mexanizmi window.__xenoraApi da', bor);
  check('sahifada JS xatosi yo\'q', t.xatolar, []);
  await t.ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════
// 2) TOKEN JONLI O'QILADI — eski nusxa ishlatilmaydi
// ══════════════════════════════════════════════════════════════════════════
{
  const t = await ochish(browser, { bizType: 'store' });
  // Boshqa oyna tokenni yangiladi (api.js refresh localStorage'ga yozadi)
  await t.page.evaluate((nt) => localStorage.setItem('access_token', nt), t.NEW);
  const sent = await t.page.evaluate(async () => {
    const r = await window.apiFetch('/debts/summary');
    return r.open_count;
  });
  check('yangi token bilan so\'rov ketdi (javob keldi)', sent, 5);
  const oxirgi = t.calls.filter(c => c.path === '/debts/summary').pop();
  check('so\'rovda localStorage dagi YANGI token', oxirgi.bearer === t.NEW, true);
  await t.ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════
// 3) 401 → REFRESH → QAYTA URINISH
// ══════════════════════════════════════════════════════════════════════════
{
  const t = await ochish(browser, { bizType: 'store', authMode: 'expired' });
  const natija = await t.page.evaluate(async () => {
    try { return { ok: true, d: await window.apiFetch('/debts/summary') }; }
    catch (e) { return { ok: false, err: e.message }; }
  });
  checkTrue('401 dan keyin so\'rov MUVAFFAQIYATLI tugadi', natija.ok);
  check('javob to\'g\'ri keldi', natija.d?.open_count, 5);
  checkTrue('/auth/refresh chaqirildi', t.refreshCalls.length >= 1);
  check('refresh tanasida refresh_token bor', t.refreshCalls[0]?.refresh_token, 'R-TOKEN');
  const ds = t.calls.filter(c => c.path === '/debts/summary');
  check('qayta urinish YANGI token bilan', ds[ds.length - 1].bearer === t.NEW, true);
  await t.ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════
// 4) REFRESH BIR MARTA (single-flight) — parallel 401 lar bitta refresh kutadi
// ══════════════════════════════════════════════════════════════════════════
{
  const t = await ochish(browser, { bizType: 'store', authMode: 'expired' });
  const n = await t.page.evaluate(async () => {
    const r = await Promise.all([
      window.apiFetch('/debts/summary').catch(() => null),
      window.apiFetch('/analytics/reorder-alerts').catch(() => null),
      window.apiFetch('/inventory/low-stock').catch(() => null),
    ]);
    return r.filter(Boolean).length;
  });
  check('uchala parallel so\'rov tiklandi', n, 3);
  check('refresh BIR MARTA bajarildi (stampede yo\'q)', t.refreshCalls.length, 1);
  await t.ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════
// 5) REFRESH YIQILSA → login ga + tokenlar tozalanadi
// ══════════════════════════════════════════════════════════════════════════
{
  const t = await ochish(browser, { bizType: 'store', authMode: 'dead' });
  // ⚠️ `evaluate` NAVIGATSIYA bilan poyga qiladi: so'rovni uzatib, keyin
  // yo'naltirishni KUTAMIZ (aks holda "Execution context was destroyed").
  t.page.evaluate(() => { window.apiFetch('/debts/summary').catch(() => {}); }).catch(() => {});
  let yonaltirildi = true;
  try {
    await t.page.waitForURL(/login\.html/, { timeout: 15000 });
    await t.page.waitForLoadState('domcontentloaded');
  } catch { yonaltirildi = false; }
  checkTrue('login sahifasiga yo\'naltirildi', yonaltirildi && /login\.html/.test(t.page.url()));
  checkTrue('/auth/refresh urinib ko\'rildi', t.refreshCalls.length >= 1);
  // Navigatsiyadan KEYIN o'qiymiz — origin bir xil, localStorage ko'rinadi.
  const tok = await t.page.evaluate(() => [
    localStorage.getItem('access_token'), localStorage.getItem('refresh_token')]).catch(() => ['?', '?']);
  check('tokenlar tozalandi', tok, [null, null]);
  await t.ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════
// 6) store TURIDA /kitchen/orders POLLANMAYDI (eng katta foyda)
// ══════════════════════════════════════════════════════════════════════════
{
  const t = await ochish(browser, { bizType: 'store' });
  await kut(1500);
  check('store: /kitchen/orders so\'rovi YO\'Q', nechta(t.calls, '/kitchen/orders'), 0);
  checkTrue('store: /inventory/low-stock BOR', nechta(t.calls, '/inventory/low-stock') >= 1);
  checkTrue('store: /debts/summary BOR', nechta(t.calls, '/debts/summary') >= 1);
  checkTrue('store: /analytics/reorder-alerts BOR', nechta(t.calls, '/analytics/reorder-alerts') >= 1);
  await t.ctx.close();
}

{
  const t = await ochish(browser, { bizType: 'cafe' });
  await kut(1500);
  checkTrue('cafe: /kitchen/orders BOR (oshxona bor)', nechta(t.calls, '/kitchen/orders') >= 1);
  check('cafe: /debts/summary YO\'Q (store badge\'i)', nechta(t.calls, '/debts/summary'), 0);
  await t.ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════
// 7) BADGE RAQAMLARI TO'G'RI (GOLDEN — ko'rinish buzilmadi)
// ══════════════════════════════════════════════════════════════════════════
{
  const t = await ochish(browser, { bizType: 'store' });
  await t.page.waitForFunction(() =>
    document.getElementById('debtBadge')?.textContent === '7', null, { timeout: 8000 }).catch(() => {});
  const badges = await t.page.evaluate(() => ({
    debt:    document.getElementById('debtBadge')?.textContent,
    low:     document.getElementById('lowStockBadge')?.textContent,
    reorder: document.getElementById('reorderBadge')?.textContent,
  }));
  check('debtBadge = open+partial (5+2)', badges.debt, '7');
  check('lowStockBadge = 4', badges.low, '4');
  check('reorderBadge = 7', badges.reorder, '7');
  await t.ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════
// 8) POLLER TO'XTAYDI — abadiy tsikl yo'q
// ══════════════════════════════════════════════════════════════════════════
{
  const t = await ochish(browser, { bizType: 'store' });
  // Pollerlar ro'yxatga olinganmi
  const royxat = await t.page.evaluate(() => typeof window.registerPoller === 'function');
  checkTrue('registerPoller mavjud', royxat);

  // Qaytarilmas 401 ni majburlab chaqiramiz (refresh mexanizmini olib tashlaymiz)
  const toxtadi = await t.page.evaluate(async () => {
    window.__xenoraApi = null;              // refresh yo'q → qaytarilmas
    const oldFetch = window.fetch;
    window.fetch = async () => new Response('{"detail":"401"}', { status: 401 });
    try { await window.apiFetch('/debts/summary').catch(() => {}); } finally { window.fetch = oldFetch; }
    return window.__pollersStopped === true;
  });
  checkTrue('qaytarilmas 401 da pollerlar to\'xtadi', toxtadi);

  // To'xtagandan keyin YANGI so'rov ketmasligi kerak
  const oldin = t.calls.length;
  await kut(1200);
  check('to\'xtagandan keyin yangi poller so\'rovi yo\'q', t.calls.length, oldin);

  const toast = await t.page.evaluate(() =>
    [...document.querySelectorAll('.toast')].map(e => e.textContent).join('|'));
  checkTrue('foydalanuvchiga ogohlantirish ko\'rsatildi', /Sessiya tugadi/.test(toast));
  await t.ctx.close();
}

await browser.close();
server.close();
console.log(`\n${pass} OK, ${fail} FAIL`);
process.exit(fail ? 1 : 0);
