/**
 * Z-CHEK LOKAL PRINTERGA (fix/z-report-local-print).
 *
 * MUAMMO (jonli, MANHATTAN 2026-10): Z-chek tugmalari `POST /shifts/{id}/print-z`
 * ga borardi — server do'kon printeriga yeta olmaydi, `mock` rejimda faylga
 * yozib `printed: true` qaytarardi → "Z-chek printerga yuborildi", chek yo'q.
 *
 * Qotiriladi:
 *   1) shift.html (kassa): Z-chek → electronAPI.printDocument (lokal), /print-z
 *      CHAQIRILMAYDI; print_type / printer nomi / paper_width 57 /receipt-settings
 *      va /settings/printer/status dan; chek matni z-report.js dan
 *   2) printer javob bermasa (spool-guard ok:false) → aniq xato, "chiqarildi" YO'Q
 *   3) admin printZReport (ro'yxat + yopish oynasi): /x-report → printReceiptDoc,
 *      /print-z yo'q; xato matni o'tadi
 *   4) hech bir UI faylida /print-z va "printerga yuborildi" qolmagan
 *
 * Ishga tushirish:  node frontend/tests/test_z_report_local_print.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { readFileSync } from 'fs';
import { resolve, extname, join } from 'path';
import vm from 'node:vm';

const ROOT = resolve('frontend');
const rd = p => readFileSync(resolve(ROOT, p), 'utf8').replace(/\r\n/g, '\n');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };
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
function grab(src, re, what) {
  const m = src.match(re);
  if (!m) { console.error(`XATO: "${what}" topilmadi — test eskirgan yoki kod o'zgargan.`); process.exit(2); }
  return m[0];
}

const NOT_RESPONDING = "Printer javob bermayapti — qog'ozni tekshiring";
// /x-report (yopilgan smena) — backend `_build_zreport_data` shakli
const Z = {
  store_name: 'MANHATTAN', shift_id: 9, cashier: 'AZIZBEK', start_time: '22.10.2026 23:57',
  end_time: '24.10.2026 00:32', starting_cash: 0, cash_sales: 5210000, card_sales: 1100000,
  credit_total: 2000000, total_sales: 8310000, sales_count: 11, avg_order: 755455,
  discount_total: 1460000, cash_refunds: 0, card_refunds: 0, debt_paid_cash: 0, debt_paid_card: 0,
  cash_in_total: 6310000, withdrawals: 0, deposits: 0, expected_cash: 5210000,
  counted_cash: 5210000, shortage: 0, products: [{ name: 'BLASER 5613', quantity: 1, revenue: 950000 }],
  notes: null, is_open: false,
};
const REPORT = {
  shift_id: 9, cashier: 'AZIZBEK', start_time: '22.10.2026 23:57', end_time: '24.10.2026 00:32', duration_hours: 24.6,
  summary: { total_orders: 11, discount_total: 1460000, avg_order: 755455 },
  by_payment_method: [{ method: 'cash', amount: 5210000 }], top_products: [],
  opening_cash: 0, total_sales: 8310000, cash_sales: 5210000, card_sales: 1100000, credit_total: 2000000,
  cash_in_total: 6310000, expected_cash: 5210000, counted_cash: 5210000, shortage: 0, is_open: false,
};
const calls = [];
const jwt = 'x.' + Buffer.from(JSON.stringify({ sub: 'kassir', exp: 4102444800, features: ['z_report'], business_type: 'store' })).toString('base64') + '.y';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block' });
await ctx.addInitScript(([t]) => {
  localStorage.setItem('access_token', t); localStorage.setItem('business_type', 'store');
  localStorage.setItem('user', JSON.stringify({ id: 28, username: 'kassir', full_name: 'AZIZBEK', role: { name: 'cashier' }, tenant_id: 30 }));
  // Electron preload o'rnida: printDocument payload'ini yozib, belgilangan natijani qaytaradi
  window.__printed = [];
  window.__printResult = { ok: true, engine: 'usb-sumatra' };
  window.electronAPI = {
    isElectron: true,
    printReceipt: async () => ({ ok: false, error: 'eski yo\'l chaqirilmasligi kerak' }),
    printDocument: async (payload) => { window.__printed.push(payload); return window.__printResult; },
  };
}, [jwt]);
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
await page.route(/fonts\.(googleapis|gstatic)\.com/, r => r.fulfill({ status: 200, contentType: 'text/css', body: '' }));
await page.route('**/api/**', r => {
  const u = new URL(r.request().url());
  const p = u.pathname.replace(/.*\/api\/v1/, '');
  const m = r.request().method();
  calls.push({ m, p });
  let body = {};
  if (p === '/shifts/active') body = {};
  else if (p === '/shifts/') body = [];
  else if (p === '/shifts/9/x-report') body = Z;
  else if (p === '/shifts/9/report') body = REPORT;
  else if (p === '/shifts/9/print-z') body = { printed: true, printer: { ok: true, mode: 'mock' } };
  else if (p === '/settings/printer/status') body = { printer_name: 'Xprinter XP-365B', enabled: true };
  else if (p === '/receipt-settings/') body = { print_type: 'usb', printer_ip: '', printer_port: null, paper_width: 57, font_size: 'large' };
  r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
});
await page.goto(`${BASE}/app/shift.html`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => typeof window.showReport === 'function' && typeof window.printReceiptDoc === 'function', null, { timeout: 8000 });
const bodyText = () => page.evaluate(() => document.body.innerText);

console.log('\n── 1) Kassa (shift.html): Z-chek lokal printerga ──');
await page.evaluate(() => window.showReport(9));
await page.waitForSelector('#printZBtn', { timeout: 5000 });
await page.click('#printZBtn');
await page.waitForFunction(() => window.__printed.length === 1, null, { timeout: 5000 });
const pl = await page.evaluate(() => window.__printed[0]);
check('1_print_z_CHAQIRILMADI', calls.some(c => c.p.endsWith('/print-z')), false);
check('1_x_report_olindi', calls.some(c => c.p === '/shifts/9/x-report'), true);
check('1_print_type', pl.printType, 'usb');
check('1_printer_nomi', pl.deviceName, 'Xprinter XP-365B');
check('1_paper_width_57', pl.paperWidth, 57);
check('1_matn_Z_HISOBOT_9', /Z-HISOBOT #9/.test(pl.html), true);
check('1_matn_jami_savdo', /JAMI SAVDO:[\s\S]{0,80}8,310,000/.test(pl.html), true);
check('1_matn_dokon', pl.html.includes('MANHATTAN'), true);
await page.waitForTimeout(100);
check('1_toast_chiqarildi', (await bodyText()).includes('Z-chek chiqarildi'), true);
check('1_yuborildi_YOQ', (await bodyText()).includes('printerga yuborildi'), false);

console.log('\n── 2) Printer javob bermasa ──');
await page.evaluate((e) => { window.__printResult = { ok: false, error: e }; }, NOT_RESPONDING);
await page.click('#printZBtn');
await page.waitForFunction(() => window.__printed.length === 2, null, { timeout: 5000 });
await page.waitForFunction(() => /Z-chek chiqmadi/.test(document.body.innerText), null, { timeout: 5000 });
const t2 = await bodyText();
check('2_aniq_xato', t2.includes('Z-chek chiqmadi: ' + NOT_RESPONDING), true);
await page.evaluate(() => { window.__printResult = { ok: false }; });
await page.click('#printZBtn');
await page.waitForFunction(() => window.__printed.length === 3, null, { timeout: 5000 });
await page.waitForTimeout(100);
check('2_xatosiz_javob_ham_aniq', (await bodyText()).includes('Z-chek chiqmadi: Printer javob bermayapti'), true);
check('2_print_z_hali_ham_yoq', calls.some(c => c.p.endsWith('/print-z')), false);
check('2_sahifa_xatosiz', errors, []);
await browser.close();
server.close();

console.log('\n── 3) Admin printZReport (ro\'yxat + yopish oynasi) ──');
const SHIFT = rd('js/admin/shift.js');
const actx = {
  calls: [], toasts: [], printed: [], result: { ok: true },
  fmtNum: n => Math.round(Number(n) || 0).toLocaleString('en-US'),
};
actx.toast = (m, t) => actx.toasts.push([m, t || 'info']);
actx.apiFetch = async (p) => { actx.calls.push(p); return Z; };
actx.apiFetchPost = async (p) => { actx.calls.push('POST ' + p); return { printed: true }; };
actx.window = { printReceiptDoc: async (html, opts) => { actx.printed.push({ html, opts }); return actx.result; } };
vm.createContext(actx);
vm.runInContext(rd('js/core/z-report.js'), actx);
vm.runInContext(grab(SHIFT, /async function _printZLocal\(r\) \{[\s\S]*?\n}/, '_printZLocal'), actx);
vm.runInContext(grab(SHIFT, /async function printZReport\(shiftId, btn\) \{[\s\S]*?\n}/, 'printZReport'), actx);
await vm.runInContext('printZReport(9, null)', actx);
check('3_x_report', actx.calls, ['/shifts/9/x-report']);
check('3_lokal_chop', actx.printed.length, 1);
check('3_matn_Z_9', /Z-HISOBOT #9/.test(actx.printed[0].html), true);
check('3_toast_ok', actx.toasts, [['Z-hisobot chiqarildi', 'success']]);
actx.result = { ok: false, error: NOT_RESPONDING }; actx.toasts.length = 0;
await vm.runInContext('printZReport(9, null)', actx);
check('3_xato_aniq', actx.toasts, [['Z-hisobot chiqmadi: ' + NOT_RESPONDING, 'error']]);
check('3_print_z_yoq', actx.calls.some(c => c.includes('print-z')), false);

console.log('\n── 4) /print-z UI\'da qolmagan ──');
// Izohlar tarixni tushuntiradi — faqat CHAQIRUV va xabar matni tekshiriladi
for (const f of ['app/shift.html', 'js/admin/shift.js', 'js/admin/core.js', 'app/admin.html'])
  check('4_' + f, /\/shifts\/\$\{[^}]+\}\/print-z|toast\([^)]*printerga yuborildi/.test(rd(f)), false);
const AH = rd('app/admin.html');
const zi = AH.indexOf('<script src="../js/core/z-report.js">'), si = AH.indexOf('<script src="../js/admin/shift.js">');
check('4_admin_z_report_shiftdan_oldin', zi > 0 && zi < si, true);
check('4_sw_keshda', /'\/js\/core\/z-report\.js'/.test(rd('service-worker.js')), true);

console.log(`\n${pass} OK, ${fail} FAIL`);
process.exit(fail ? 1 : 0);
