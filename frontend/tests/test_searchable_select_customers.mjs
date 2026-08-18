/**
 * dmCustomer testi: nasiya modalida MIJOZ tanlash — qidiruv bilan.
 *
 * NEGA: nasiya endi ishlaydi (v1.9.1) va mijozlar soni tez o'sadi. Ro'yxat
 * `page_size=500` bilan yuklanadi — 500 dan keyingi mijoz dropdownga UMUMAN
 * tushmasdi va uni tanlab bo'lmasdi.
 *
 * GOLDEN QOIDA: `dmCustomer.value` o'qiydigan joy (saveDebt) TEGILMAYDI.
 * Qo'shimcha xavf — "tez mijoz qo'shish": filtr yoqilgan holda yangi mijoz
 * ro'yxatga tushmay, `sel.value` JIMGINA ishlamay qolishi mumkin edi (ensure).
 *
 * Ishga tushirish:  node frontend/tests/test_searchable_select_customers.mjs
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

// 800 mijoz; 777-chi "Dilnoza Karimova" — 500 lik ro'yxatdan TASHQARIDA
const CUSTOMERS = Array.from({ length: 800 }, (_, i) => ({
  id: i + 1, name: `Mijoz ${i + 1}`, phone: `+9989000${String(i + 1).padStart(4, '0')}`,
  total_debt: 0, credit_limit: null,
}));
CUSTOMERS[776].name = 'Dilnoza Karimova';

const jwt = 'x.' + Buffer.from(JSON.stringify({
  sub: 'admin', features: [], business_type: 'store',
})).toString('base64') + '.y';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
await ctx.addInitScript(([t]) => {
  localStorage.setItem('access_token', t);
  localStorage.setItem('business_type', 'store');
  localStorage.setItem('user', JSON.stringify({
    id: 1, username: 'admin', is_superuser: true, role: { name: 'admin' }, tenant_id: 26,
  }));
}, [jwt]);
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));

let created = null;
await page.route('**/api/v1/**', async (route) => {
  const req = route.request();
  const u = new URL(req.url());
  const path = u.pathname.replace('/api/v1', '');
  const q = (u.searchParams.get('search') || '').toLowerCase();
  const size = Number(u.searchParams.get('page_size') || 20);
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) });

  if (req.method() === 'POST' && path === '/customers/') {
    const body = JSON.parse(req.postData() || '{}');
    created = { id: 9001, name: body.name, phone: body.phone, total_debt: 0 };
    CUSTOMERS.push(created);
    return json(created);
  }
  if (path === '/customers/') {
    const rows = (q
      ? CUSTOMERS.filter(c => c.name.toLowerCase().includes(q) || (c.phone || '').includes(q))
      : CUSTOMERS).slice(0, size);
    return json({ items: rows, total: rows.length, page: 1, page_size: size, total_pages: 1 });
  }
  if (path.includes('/features')) return json({ business_type: 'store', enabled_features: [] });
  return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
});

await page.goto(`${BASE}/app/admin.html`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => typeof window.openDebtModal === 'function');
await page.evaluate(() => window.openDebtModal());
await page.waitForTimeout(800);

check('D1_qidiruv_inputi_qoshildi',
      await page.$$eval('#debtModal input[data-ss-input]', e => e.length), 1);
check('D2_boshlangich_500',
      await page.$$eval('#dmCustomer option', o => o.length), 501);   // + "— Tanlang —"

// ── 500 dan TASHQARIDAGI mijoz serverdan topiladi ───────────────────────────
await page.fill('#debtModal input[data-ss-input]', 'Dilnoza');
await page.waitForTimeout(800);
check('D3_serverdan_topildi',
      await page.$$eval('#dmCustomer option', o => o.map(x => x.textContent).filter(t => t.includes('Dilnoza'))),
      ['Dilnoza Karimova · +99890000777']);
check('D4_value_tanlandi', await page.inputValue('#dmCustomer'), '777');

// ── GOLDEN: tez mijoz qo'shish filtr yoqilgan holatda ham ishlaydi ──────────
await page.fill('#debtModal input[data-ss-input]', 'Mijoz 3');   // filtr boshqa natijada
await page.waitForTimeout(700);
await page.evaluate(() => window._dmToggleNewCust ? window._dmToggleNewCust(true) : null);
await page.evaluate(() => {
  document.getElementById('dmNewName').value  = 'Yangi Mijoz';
  document.getElementById('dmNewPhone').value = '+998911234567';
});
await page.click('#dmNewCustSave');
await page.waitForTimeout(700);

check('D5_yangi_mijoz_yaratildi', created && created.name, 'Yangi Mijoz');
check('D6_yangi_mijoz_TANLANDI', await page.inputValue('#dmCustomer'), '9001');
check('D7_js_xato_yoq', errors, []);

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
