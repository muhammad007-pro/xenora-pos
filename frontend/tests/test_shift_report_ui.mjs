/**
 * Z-HISOBOT VA KASSA NAZORATI — UI (fix/shift-report).
 *
 * Qotiriladi:
 *   1) shift.html (kassir): yopish oynasida sanalgan naqd BO'SH; bo'sh bilan
 *      yopish so'rovi YUBORILMAYDI; "yashikda bo'lishi kerak" SERVERDAN
 *      (x-report); farq = sanalgan − kutilgan; counted_cash query'da ketadi
 *   2) shift.html hisobot: SAVDO / PUL (kassaga tushgan) / YASHIK bloklari,
 *      kamomad ko'rinadi; "Jami tushum" (ikki marta chegirma) yo'q
 *   3) shift.html inkassatsiya: POST /cash-movements {kind, amount, reason}
 *   4) tarixdagi 📊 — window.showReport (modul ichida global emas edi)
 *   5) admin: zMoneyBlocks tartibi; yopish maydoni sukut 0 emas;
 *      "Bugungi daromad" x-report'dan; waiter.js counted_cash query'da
 *
 * Ishga tushirish:  node frontend/tests/test_shift_report_ui.mjs
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

// ── Soxta server javoblari ───────────────────────────────────────────────────
const X = { expected_cash: 410000, starting_cash: 100000, cash_sales: 300000, cash_refunds: 10000,
            debt_paid_cash: 20000, withdrawals: 0, deposits: 0, total_sales: 390000 };
const REPORT = {
  shift_id: 9, cashier: 'Kassir', start_time: '13.10.2026 09:00', end_time: '13.10.2026 18:00', duration_hours: 9,
  summary: { total_orders: 2, discount_total: 10000, avg_order: 195000, net_revenue: 390000 },
  by_payment_method: [{ method: 'cash', amount: 300000 }, { method: 'card', amount: 90000 }],
  top_products: [], opening_cash: 100000, closing_cash: 410000,
  total_sales: 390000, cash_sales: 300000, card_sales: 90000, credit_total: 0,
  cash_refunds: 10000, card_refunds: 15000, debt_paid_cash: 20000, debt_paid_card: 5000,
  cash_in_total: 390000, withdrawals: 0, deposits: 0, expected_cash: 410000,
  counted_cash: 400000, shortage: -10000, is_open: false,
};
const calls = [];
const jwt = 'x.' + Buffer.from(JSON.stringify({ sub: 'kassir', exp: 4102444800, features: [], business_type: 'store' })).toString('base64') + '.y';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block' });
await ctx.addInitScript(([t]) => {
  localStorage.setItem('access_token', t); localStorage.setItem('business_type', 'store');
  localStorage.setItem('user', JSON.stringify({ id: 5, username: 'kassir', full_name: 'Kassir', role: { name: 'cashier' }, tenant_id: 27 }));
}, [jwt]);
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
await page.route(/fonts\.(googleapis|gstatic)\.com/, r => r.fulfill({ status: 200, contentType: 'text/css', body: '' }));
await page.route('**/api/**', r => {
  const u = new URL(r.request().url());
  const p = u.pathname.replace(/.*\/api\/v1/, '');
  const m = r.request().method();
  calls.push({ m, p, q: u.search, body: r.request().postData() });
  let body = {};
  if (p === '/shifts/active') body = { id: 9, start_time: '2026-10-13T04:00:00Z', starting_cash: 100000 };
  else if (p === '/shifts/') body = [];
  else if (p === '/shifts/9/x-report') body = X;
  else if (p === '/shifts/9/close') body = { id: 9 };
  else if (p === '/shifts/9/report') body = REPORT;
  else if (p === '/shifts/9/cash-movements') body = m === 'POST' ? { id: 1 } : [];
  r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
});
await page.goto(`${BASE}/app/shift.html`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#closeShiftBtn', { timeout: 8000 });

console.log('\n── 1) Yopish oynasi ──');
await page.click('#closeShiftBtn');
await page.waitForFunction(() => /bo'lishi kerak/i.test(document.getElementById('closePreview').textContent), null, { timeout: 5000 });
check('1_maydon_bosh', await page.inputValue('#endingCash'), '');
check('1_xreport_chaqirildi', calls.some(c => c.p === '/shifts/9/x-report'), true);
const pv = (await page.textContent('#closePreview')).replace(/\s/g, '');
check('1_kutilgan_serverdan', /410[^0-9]?000/.test(pv), true);
await page.click('#confirmCloseBtn');
await page.waitForTimeout(200);
check('1_boshi_bilan_yopilmaydi', calls.some(c => c.p === '/shifts/9/close'), false);
await page.fill('#endingCash', '400000');
check('1_farq_kamomad', (await page.textContent('#closeDiff')).startsWith('Kamomad'), true);
await page.click('#confirmCloseBtn');
await page.waitForFunction(() => document.getElementById('reportModal').classList.contains('open'), null, { timeout: 5000 });
const close = calls.find(c => c.p === '/shifts/9/close');
check('1_counted_query', new URLSearchParams(close?.q || '').get('counted_cash'), '400000');

console.log('\n── 2) Kassir hisoboti ──');
await page.waitForFunction(() => /Kassaga tushgan/.test(document.getElementById('reportBody').textContent), null, { timeout: 5000 });
const rep = await page.textContent('#reportBody');
for (const frag of ['Jami savdo', 'Kassaga tushgan', "Yashikda bo'lishi kerak", 'Kamomad', "Qarz to'lovi (karta)", 'Qaytarish (karta)'])
  check('2_' + frag, rep.includes(frag), true);
check('2_jami_tushum_YOQ', rep.includes('Jami tushum'), false);
await page.click('#repClose');

console.log('\n── 3) Inkassatsiya ──');
await page.waitForSelector('#cashMoveBtn');
await page.click('#cashMoveBtn');
await page.fill('#cmAmount', '200000');
await page.fill('#cmReason', 'egasiga topshirildi');
await page.click('#cmSave');
await page.waitForTimeout(300);
const mv = calls.find(c => c.p === '/shifts/9/cash-movements' && c.m === 'POST');
check('3_post_body', mv ? JSON.parse(mv.body) : null, { kind: 'withdrawal', amount: 200000, reason: 'egasiga topshirildi' });

console.log('\n── 4) Tarix 📊 ──');
check('4_window_showReport', await page.evaluate(() => typeof window.showReport), 'function');
check('4_sahifa_xatosiz', errors, []);
await browser.close();
server.close();

console.log('\n── 5) Admin ──');
const SHIFT = rd('js/core/z-report.js');   // zMoneyBlocks shu yerga ko'chdi (kassa bilan umumiy)
const zctx = { fmtNum: n => String(Math.round(n)) };
vm.createContext(zctx);
vm.runInContext(grab(SHIFT, /function zMoneyBlocks\(r, fmt\) \{[\s\S]*?\n}/, 'zMoneyBlocks'), zctx);
zctx.r = { ...REPORT, starting_cash: 100000, withdrawals: 50000, sales_count: 2 };
const blocks = vm.runInContext('zMoneyBlocks(r, n => String(n))', zctx).map(([l, v]) => [l, v ?? null]);
const labels = blocks.map(b => b[0]);
check('5_blok_tartibi', labels.filter(l => /^(SAVDO|PUL|YASHIK)/.test(l)), ['SAVDO', 'PUL (KASSAGA TUSHGAN)', 'YASHIK (NAQD)']);
check('5_jami_savdo', blocks.find(b => b[0] === 'JAMI SAVDO:')[1], '390000');
check('5_kassaga_tushgan', blocks.find(b => b[0] === 'KASSAGA TUSHGAN:')[1], '390000');
check('5_inkassatsiya', blocks.find(b => b[0] === 'Olindi (inkassatsiya):')[1], '−50000');
check('5_yashik', blocks.find(b => b[0] === "Yashikda bo'lishi kerak:")[1], '410000');

const AHTML = rd('app/admin.html');
check('5_admin_maydon_sukut_0_emas', /id="shiftCountedCash" value=""/.test(AHTML), true);
check('5_admin_smena_karta_yorligi', /id="shiftRevTotal">[^<]*<\/div><div class="ms-lbl">Ochiq smenalar savdosi/.test(AHTML), true);
const CORE = rd('js/admin/core.js');
check('5_ochiq_smena_xreport', /shiftRevTotal[\s\S]{0,900}x-report/.test(CORE), true);
check('5_waiter_query', /close\?counted_cash=/.test(rd('js/waiter.js')), true);
check('5_waiter_ending_cash_yoq', /ending_cash:/.test(rd('js/waiter.js')), false);

console.log(`\n${pass} OK, ${fail} FAIL`);
process.exit(fail ? 1 : 0);
