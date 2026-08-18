/**
 * BOSQICH C testi: markup_policy.html (`fProduct`) — qidiruvli select.
 *
 * A/B bilan bir xil naqsh. Bu yerdagi qo'shimcha xavf — TAHRIRLASH oqimi:
 * mavjud qoidani ochganda `fProduct.value = p.product_id` qilinardi; qidiruv
 * filtri o'sha option'ni ro'yxatdan chiqarib yuborgan bo'lsa, maydon JIMGINA
 * BO'SH ko'rinardi. Endi `ensure()` ishlatiladi.
 *
 * Ishga tushirish:  node frontend/tests/test_searchable_select_stage_c.mjs
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

const PRODUCTS = Array.from({ length: 1200 }, (_, i) => ({
  id: i + 1, name: `Mahsulot ${i + 1}`, price: (i + 1) * 100,
}));
PRODUCTS[1150].name = 'KERASYS shampun';       // id 1151 — 1000 lik ro'yxatdan tashqarida

const jwt = 'x.' + Buffer.from(JSON.stringify({ sub: 'admin', features: [] })).toString('base64') + '.y';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
await ctx.addInitScript(([t]) => {
  localStorage.setItem('access_token', t);
  localStorage.setItem('user', JSON.stringify({
    id: 1, username: 'admin', is_superuser: true, role: { name: 'admin' }, tenant_id: 26,
  }));
}, [jwt]);
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));

await page.route('**/api/v1/**', async (route) => {
  const u = new URL(route.request().url());
  const path = u.pathname.replace('/api/v1', '');
  const q = (u.searchParams.get('search') || '').toLowerCase();
  const size = Number(u.searchParams.get('page_size') || 20);
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) });

  if (path === '/products/') {
    const rows = (q ? PRODUCTS.filter(p => p.name.toLowerCase().includes(q)) : PRODUCTS).slice(0, size);
    return json({ items: rows, total: rows.length, page: 1, page_size: size, total_pages: 1 });
  }
  if (path === '/categories/')     return json({ items: [], total: 0, page: 1, page_size: 200, total_pages: 1 });
  if (path.includes('/features'))  return json({ business_type: 'store', enabled_features: [] });
  return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
});

// Modul skript deferred: Sidebar.init() kutilsa DOMContentLoaded ham kechikadi ->
// 'commit' bilan boramiz va keyin selectning to'lishini kutamiz.
await page.goto(`${BASE}/app/markup_policy.html`, { waitUntil: 'commit' });
await page.waitForFunction(() => document.querySelectorAll('#fProduct option').length > 1);
await page.waitForTimeout(400);

check('C1_boshlangich_1000', await page.$$eval('#fProduct option', o => o.length), 1001);  // + "— tanlang —"
check('C2_qidiruv_inputi_bor', await page.$$eval('#productRow input[data-ss-input]', e => e.length), 1);

// Forma modalini ochamiz — aks holda maydonlar KO'RINMAYDI
await page.evaluate(() => document.getElementById('modalCreate').classList.add('active'));
await page.waitForTimeout(200);
// Qidiruv maydoni faqat "product" rejimida ko'rinadi
await page.selectOption('#fScope', 'product');
await page.waitForTimeout(200);

await page.fill('#productRow input[data-ss-input]', 'KERASYS');
await page.waitForTimeout(800);
check('C3_serverdan_topildi',
      await page.$$eval('#fProduct option', o => o.map(x => x.textContent).filter(t => t.includes('KERASYS'))),
      ['KERASYS shampun']);
check('C4_value_ozgardi', await page.inputValue('#fProduct'), '1151');

// TAHRIRLASH: filtr boshqa mahsulotni ko'rsatib turganda ham mavjud qoida
// mahsuloti tanlanishi kerak (ensure)
await page.fill('#productRow input[data-ss-input]', 'Mahsulot 7');
await page.waitForTimeout(800);
const ensured = await page.evaluate(() => {
  const sel = document.getElementById('fProduct');
  sel._ss.ensure({ id: 999, name: 'Eski qoida mahsuloti' });
  return { value: sel.value, label: sel.options[sel.selectedIndex].textContent };
});
check('C5_ensure_tanladi', ensured, { value: '999', label: 'Eski qoida mahsuloti' });
check('C6_js_xato_yoq', errors, []);

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
