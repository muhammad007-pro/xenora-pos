/**
 * MOLIYA SANA FILTRI + ADMIN SMENALAR + "CHEKLAR" ATAMASI + POS QAMALISH
 * (feature/dashboard-sales-breakdown).
 *
 * Qotiriladi:
 *   1) profit.html: sana o'zgarsa AVTOMATIK yuklanadi; "Ko'rsatish" tugmasi
 *      majburan yuklaydi; tanlangan oraliq yozuvi; eski davr javobi yangisini
 *      ustidan YOZMAYDI; Chart.js yuklanmasa ham sahifa ishlaydi
 *   2) admin Smenalar: ochiq smena → X-hisobot / Kassa / Yopish, yopilgan →
 *      Z-hisobot; X oynasida "X-HISOBOT", sanalgan/farq yo'q; Z da bor;
 *      o'z smenasi ochiq bo'lsa "+ Smena ochish" yashirin
 *   3) Atama: store → "Cheklar", cafe → "Buyurtmalar"
 *   4) POS "Smena oching" oynasi: Admin panel (admin/menejer), Smenalar, Chiqish
 *   5) shift.html: smena yopilgach ← tugmasi tarixga emas, rolga mos sahifaga
 *
 * Ishga tushirish:  node frontend/tests/test_finance_shift_ui.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { readFileSync } from 'fs';
import { resolve, extname, join } from 'path';

const ROOT = resolve('frontend');
const rd = p => readFileSync(resolve(ROOT, p), 'utf8').replace(/\r\n/g, '\n');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
               '.css': 'text/css', '.svg': 'image/svg+xml', '.json': 'application/json' };
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
const kut = ms => new Promise(r => setTimeout(r, ms));
const mkToken = (biz, features = []) => `x.${Buffer.from(JSON.stringify({
  sub: '1', user_id: 1, tenant_id: 28, business_type: biz, features, exp: 4102444800, type: 'access',
})).toString('base64')}.y`;

const CHART_STUB = 'window.Chart=function(){return{destroy(){},update(){}}};Chart.defaults={font:{}};';

async function ochish(browser, url, { biz = 'store', chart = true, api, user } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block' });
  await ctx.addInitScript(({ t, b, u }) => {
    if (sessionStorage.getItem('__seeded')) return;
    sessionStorage.setItem('__seeded', '1');
    localStorage.setItem('access_token', t);
    localStorage.setItem('business_type', b);
    localStorage.setItem('user', JSON.stringify(u));
  }, { t: mkToken(biz, ['z_report']), b: biz, u: user || { id: 1, full_name: 'ADMIN', business_type: biz, role: { name: 'admin' } } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  // Tashqi hostlar: Chart.js — stub (yoki "yuklanmadi"), qolgani bo'sh
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => {
    const u = r.request().url();
    if (u.includes('chart')) return chart ? r.fulfill({ status: 200, contentType: 'text/javascript', body: CHART_STUB })
                                          : r.abort();
    return r.fulfill({ status: 200, contentType: 'text/css', body: '' });
  });
  const calls = [];
  await page.route('**/api/v1/**', async r => {
    const u = new URL(r.request().url());
    const path = u.pathname.replace(/.*\/api\/v1/, '');
    calls.push({ m: r.request().method(), path, q: u.search });
    const out = await api(path, u, r.request());
    if (out && out.__delay) await kut(out.__delay);
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(out && out.__delay ? out.body : (out ?? {})) });
  });
  await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' });
  return { page, ctx, calls, errors };
}

const browser = await chromium.launch({ headless: true });

// ═══ 1) MOLIYA — sana oralig'i ═════════════════════════════════════════════════
console.log('\n── 1) Moliya sana filtri ──');
{
  const summary = (q) => ({ business_type: 'store', revenue: q.get('date_from') ? 5000 : 1000, cost: 0,
                           gross_profit: 0, expenses: 0, net_profit: 0, orders_count: 1 });
  let slowFirst = true;
  const t = await ochish(browser, '/app/profit.html', { api: (path, u) => {
    if (path === '/profit/summary') {
      // Birinchi oraliq so'rovi (faqat "dan") SEKIN — ikkinchisidan keyin keladi
      if (u.searchParams.get('date_from') === '2026-10-01' && !u.searchParams.get('date_to') && slowFirst) {
        slowFirst = false;
        return { __delay: 1500, body: { ...summary(u.searchParams), revenue: 999999 } };
      }
      return summary(u.searchParams);
    }
    if (path === '/profit/timeline') return { points: [] };
    return [];
  } });
  await t.page.waitForFunction(() => /Jami savdo/.test(document.getElementById('sg').textContent), null, { timeout: 8000 });
  check('1_tugma_bor', await t.page.isVisible('#pApply'), true);
  t.calls.length = 0;
  await t.page.fill('#pFrom', '2026-10-01');
  await kut(800);
  check('1_dan_avtomatik', t.calls.filter(c => c.path === '/profit/summary').map(c => c.q),
        ['?period=today&date_from=2026-10-01']);
  await t.page.fill('#pTo', '2026-10-05');
  await kut(800);
  check('1_gacha_avtomatik', t.calls.some(c => c.path === '/profit/summary' && c.q.includes('date_to=2026-10-05')), true);
  check('1_oraliq_yozuvi', await t.page.textContent('#pNow'), "Ko'rsatilmoqda: 01.10.2026 — 05.10.2026");
  await kut(1200);   // sekin (eski) javob endi keldi — ekranni buzmasligi kerak
  const sg = (await t.page.textContent('#sg')).replace(/\s/g, '');
  check('1_eski_javob_tashlandi', /999[^0-9]?999/.test(sg), false);
  check('1_yangi_raqam', /5[^0-9]?000/.test(sg), true);
  t.calls.length = 0;
  await t.page.click('#pApply');
  await kut(300);
  check('1_korsatish_majburan', t.calls.filter(c => c.path === '/profit/summary').length, 1);
  t.calls.length = 0;
  await t.page.dispatchEvent('#pTo', 'change');
  await kut(700);
  check('1_ozgarmasa_qayta_yuklamaydi', t.calls.length, 0);
  check('1_xatosiz', t.errors, []);
  await t.ctx.close();
}
{
  const t = await ochish(browser, '/app/profit.html', { chart: false, api: (path) =>
    path === '/profit/summary' ? { business_type: 'store', revenue: 1000, cost: 0, gross_profit: 0, expenses: 0, net_profit: 0 }
      : path === '/profit/timeline' ? { points: [] } : [] });
  await t.page.waitForFunction(() => /Jami savdo/.test(document.getElementById('sg').textContent), null, { timeout: 8000 }).catch(() => {});
  check('1_chartsiz_raqamlar_chiqadi', /Jami savdo/.test(await t.page.textContent('#sg')), true);
  t.calls.length = 0;
  await t.page.fill('#pFrom', '2026-10-02');
  await t.page.click('#pApply');
  await kut(400);
  check('1_chartsiz_filtr_ishlaydi', t.calls.some(c => c.q.includes('date_from=2026-10-02')), true);
  await t.ctx.close();
}

// ═══ 2–3) ADMIN — Smenalar va atama ════════════════════════════════════════════
const SHIFTS = [
  { id: 11, user_id: 1, user: { full_name: 'ADMIN' }, start_time: '2026-10-14T04:00:00Z', end_time: null,
    starting_cash: 100000, total_sales: 0, cash_sales: 0, card_sales: 0, credit_total: 0, shortage: 0 },
  { id: 10, user_id: 2, user: { full_name: 'KASSIR' }, start_time: '2026-10-13T04:00:00Z', end_time: '2026-10-13T15:00:00Z',
    starting_cash: 0, total_sales: 500000, cash_sales: 400000, card_sales: 100000, credit_total: 0, shortage: -5000 },
];
const XREP = (id, open) => ({ shift_id: id, is_open: open, store_name: 'DOKON', cashier: 'ADMIN',
  start_time: '14.10.2026 09:00', end_time: open ? null : '13.10.2026 20:00', datetime: '14.10.2026 12:00',
  cash_sales: 300000, card_sales: 0, credit_total: 0, total_sales: 300000, sales_count: 3, avg_order: 100000,
  expected_cash: 400000, counted_cash: open ? 0 : 395000, shortage: open ? 0 : -5000, starting_cash: 100000,
  cash_in_total: 300000, products: [] });
const adminApi = (path) => {
  if (path === '/shifts/') return SHIFTS;
  if (path === '/shifts/11/x-report') return XREP(11, true);
  if (path === '/shifts/10/x-report') return XREP(10, false);
  if (path === '/analytics/summary') return { total_revenue: 0, total_orders: 0, by_payment_method: [], daily_revenue: [] };
  return { items: [], total: 0 };
};
for (const biz of ['store', 'cafe']) {
  console.log(`\n── 2/3) Admin (${biz}) ──`);
  const t = await ochish(browser, '/app/admin.html', { biz, api: adminApi });
  await t.page.waitForFunction(() => typeof window.switchPage === 'function', null, { timeout: 15000 }).catch(() => {});
  const kpiLbl = await t.page.$eval('#kpiOrders', el => el.parentElement.querySelector('.kpi-label').textContent.trim());
  check(`3_${biz}_kpi_yorligi`, kpiLbl, biz === 'store' ? 'Cheklar' : 'Buyurtmalar');
  if (biz === 'cafe') { await t.ctx.close(); continue; }
  await t.page.evaluate(() => switchPage('shifts'));
  await t.page.waitForFunction(() => document.querySelectorAll('#shiftsBody tr').length === 2, null, { timeout: 5000 });
  const rows = await t.page.$$eval('#shiftsBody tr', trs => trs.map(tr => [...tr.querySelectorAll('td:last-child button')].map(b => b.textContent.trim())));
  check('2_ochiq_amallar', rows[0], ['X-hisobot', '💵 Kassa', 'Yopish']);
  check('2_yopiq_amallar', rows[1], ['Z-hisobot', '🖨 Z-chek']);
  check('2_ochish_yashirin_ozi_ochiq', await t.page.isVisible('#shiftsOpenBtn'), false);
  check('2_ishora', await t.page.textContent('#myShiftHint'), 'Sizning smenangiz ochiq (#11)');
  check('2_smena_yorligi_store', await t.page.textContent('[data-store-label="Bugungi cheklar"]'), 'Bugungi cheklar');
  await t.page.click('#shiftsBody tr:nth-child(1) button:has-text("X-hisobot")');
  await t.page.waitForFunction(() => document.getElementById('shiftReceiptModal').classList.contains('open'), null, { timeout: 5000 });
  const x = await t.page.textContent('#shiftReceiptArea');
  check('2_X_sarlavha', x.includes('X-HISOBOT (smena ochiq)'), true);
  check('2_X_sanaldi_yoq', x.includes('Sanaldi'), false);
  check('2_X_vaqt_satri', x.includes('14.10.2026 09:00') && !x.includes('Invalid'), true);
  check('2_X_zchek_tugmasi_yoq', await t.page.isVisible('#shiftReceiptPrintZBtn'), false);
  await t.page.evaluate(() => closeModal('shiftReceiptModal'));
  await t.page.click('#shiftsBody tr:nth-child(2) button:has-text("Z-hisobot")');
  await t.page.waitForFunction(() => /Z-HISOBOT/.test(document.getElementById('shiftReceiptArea').textContent), null, { timeout: 5000 });
  const z = await t.page.textContent('#shiftReceiptArea');
  check('2_Z_sanaldi_bor', z.includes('Sanaldi') && z.includes('Kamomad'), true);
  await t.page.evaluate(() => closeModal('shiftReceiptModal'));
  await t.page.click('#shiftsBody tr:nth-child(1) button:has-text("Yopish")');
  await t.page.waitForFunction(() => document.getElementById('shiftCloseModal').classList.contains('open'), null, { timeout: 5000 });
  check('2_yopish_xreport', t.calls.filter(c => c.path === '/shifts/11/x-report').length >= 2, true);
  check('2_xatosiz', t.errors, []);
  await t.ctx.close();
}

// ═══ 4) POS "Smena oching" — chiqish yo'llari (statik + mantiq) ════════════════
console.log('\n── 4) POS gate ──');
const PHTML = rd('app/pos.html');
const POS = rd('js/modules/pos.js');
const gate = PHTML.slice(PHTML.indexOf('id="openShiftGate"'), PHTML.indexOf('Sotuvchi almashtirish / qulf'));
check('4_admin_tugma', /id="gateAdminBtn"[^>]*href="admin\.html"|href="admin\.html"[^>]*id="gateAdminBtn"/.test(gate), true);
check('4_smena_tugma', gate.includes('id="gateShiftBtn"'), true);
check('4_chiqish_tugma', gate.includes('id="gateLogoutBtn"'), true);
check('4_admin_rol_boyicha', /gateAdminBtn[\s\S]{0,200}display = \(_adminLink && _adminLink\.style\.display !== 'none'\)/.test(POS), true);
check('4_chiqish_logout', /gateLogoutBtn[\s\S]{0,120}logoutBtn'\)\?\.click\(\)/.test(POS), true);
// Haqiqiy brauzer: smenasiz POS → gate ochiladi; admin panel tugmasi faqat adminga
for (const [role, want] of [['admin', true], ['cashier', false]]) {
  const t = await ochish(browser, '/app/pos.html', {
    user: { id: 1, full_name: role.toUpperCase(), business_type: 'store', role: { name: role } },
    api: (path) => path === '/shifts/active' ? null : (path === '/cash-registers/' ? [] : []),
  });
  const shown = await t.page.waitForFunction(() => document.getElementById('openShiftGate')?.classList.contains('open'),
    null, { timeout: 15000 }).then(() => true).catch(() => false);
  check(`4_${role}_gate_ochildi`, shown, true);
  check(`4_${role}_admin_tugma`, await t.page.isVisible('#gateAdminBtn'), want);
  check(`4_${role}_chiqish_korinadi`, await t.page.isVisible('#gateLogoutBtn'), true);
  if (role === 'cashier') {
    await t.page.click('#gateLogoutBtn');
    await t.page.waitForURL(/login\.html/, { timeout: 5000 }).catch(() => {});
    check('4_chiqish_loginga', /shared\/login\.html/.test(t.page.url()), true);
  }
  await t.ctx.close();
}

// ═══ 5) shift.html — yopilgach ← tugmasi ══════════════════════════════════════
console.log('\n── 5) shift.html ──');
const SH = rd('app/shift.html');
check('5_bayroq_yopilganda', /if \(res\.id\) \{\n\s*window\._shiftJustClosed = true;/.test(SH), true);
check('5_orqaga_replace', /if \(window\._shiftJustClosed\) \{ e\.preventDefault\(\); location\.replace\(uy\); return; \}/.test(SH), true);
check('5_admin_hisobotdan_keyin', /_shiftJustClosed && window\._shiftHome\?\.admin\) location\.replace/.test(SH), true);

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
