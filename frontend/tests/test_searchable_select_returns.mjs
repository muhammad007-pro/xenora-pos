/**
 * BOSQICH C testi: returns.html (mijoz VOZVRATI) — mahsulot va mijoz qidiruvi.
 *
 * NEGA: A bosqichida `suppliers.html` dagi vozvrat/priyomka tuzatilgan edi,
 * ammo `app/returns.html` (Qaytarish jurnali) chetda qolgan — bu yerda ham
 * mahsulot ham mijoz `page_size=500` bilan yuklanardi va yozib qidirish YO'Q
 * edi. 794 mahsulotli do'konda 294 tasi dropdownga UMUMAN tushmasdi.
 *
 * GOLDEN QOIDA: `sel.value` va `opt.dataset.price` o'qiydigan joylar
 * (submitReturn, ip${idx} onchange, calcTotal) TEGILMAYDI.
 *
 * Ishga tushirish:  node frontend/tests/test_searchable_select_returns.mjs
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

// 1200 mahsulot; 1151-chi "KERASYS shampun" — boshlang'ich 1000 talikdan TASHQARIDA
const PRODUCTS = Array.from({ length: 1200 }, (_, i) => ({
  id: i + 1, name: `Mahsulot ${i + 1}`, price: (i + 1) * 100,
}));
PRODUCTS[1150].name = 'KERASYS shampun';        // id 1151, narx 115100

// 1200 mijoz; 1112-chi "Dilnoza Karimova" — 1000 talikdan TASHQARIDA
const CUSTOMERS = Array.from({ length: 1200 }, (_, i) => ({
  id: i + 1, name: `Mijoz ${i + 1}`, phone: `+9989000${String(i + 1).padStart(4, '0')}`,
  total_debt: 0,
}));
CUSTOMERS[1111].name = 'Dilnoza Karimova';      // id 1112

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

// Boshlang'ich (filtrsiz) so'rovdagi page_size — 500 kesilishi qaytmasin
const initialSize = { products: null, customers: null };
let searchCalls = 0;

await page.route('**/api/v1/**', async (route) => {
  const u = new URL(route.request().url());
  const path = u.pathname.replace('/api/v1', '');
  const q = (u.searchParams.get('search') || '').toLowerCase();
  const size = Number(u.searchParams.get('page_size') || 20);
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) });

  if (path === '/products/') {
    if (q) searchCalls++; else initialSize.products = size;
    const rows = (q ? PRODUCTS.filter(p => p.name.toLowerCase().includes(q)) : PRODUCTS).slice(0, size);
    return json({ items: rows, total: rows.length, page: 1, page_size: size, total_pages: 1 });
  }
  if (path === '/customers/') {
    if (q) searchCalls++; else initialSize.customers = size;
    const rows = (q
      ? CUSTOMERS.filter(c => c.name.toLowerCase().includes(q) || (c.phone || '').includes(q))
      : CUSTOMERS).slice(0, size);
    return json({ items: rows, total: rows.length, page: 1, page_size: size, total_pages: 1 });
  }
  if (path === '/returns/')      return json([]);
  if (path.includes('/features')) return json({ business_type: 'store', enabled_features: [] });
  return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
});

// 'commit' (stage_c naqshi): sahifadagi ba'zi resurslar 'domcontentloaded' ni
// kechiktiradi — biz select to'lishini alohida kutamiz.
await page.goto(`${BASE}/app/returns.html`, { waitUntil: 'commit' });
await page.waitForFunction(() => document.querySelectorAll('#cCustomerId option').length > 1);
await page.waitForTimeout(400);

// ── R1: page_size 500 -> 1000 (ikkala ro'yxat ham) ──────────────────────────
check('R1_page_size_1000', initialSize, { products: 1000, customers: 1000 });

// ── R2: MIJOZ — boshlang'ich ro'yxat va qidiruv inputi ──────────────────────
check('R2_mijoz_boshlangich_1000',
      await page.$$eval('#cCustomerId option', o => o.length), 1001);   // + "— Tanlang —"
check('R2_mijoz_qidiruv_inputi',
      await page.$eval('#cCustomerId', s => !!(s._ss && s._ss.input)), true);

// Modal ochilmasa maydonlar KO'RINMAYDI — Playwright fill qilmaydi
await page.evaluate(() => window.openCreateModal());
await page.waitForTimeout(300);

// Qidiruv inputlariga test uchun id beramiz (komponent ularni idsiz yaratadi)
await page.evaluate(() => {
  document.getElementById('cCustomerId')._ss.input.id = 'ssCust';
  document.getElementById('ip0')._ss.input.id = 'ssRow0';
});

// ── R3: MAHSULOT qatori — boshlang'ich 1000 va qidiruv inputi ───────────────
check('R3_mahsulot_boshlangich_1000',
      await page.$$eval('#ip0 option', o => o.length), 1001);           // + "— Mahsulot —"
check('R3_qator_grid_4_ustun',
      await page.$eval('#cItems .item-row', r => r.children.length), 4);

// ── R4: 1000 dan TASHQARIDAGI mahsulot SERVERDAN topiladi ──────────────────
await page.fill('#ssRow0', 'KERASYS');
await page.waitForTimeout(800);                                        // debounce 300ms + so'rov
check('R4_serverdan_topildi',
      await page.$$eval('#ip0 option', o => o.map(x => x.textContent).filter(t => t.includes('KERASYS'))),
      ['KERASYS shampun']);
check('R4_server_soroviga_bordi', searchCalls > 0, true);

// ── R5: GOLDEN — sel.value, dataset.price va mavjud onchange ishlayveradi ───
check('R5_value_ozgardi',    await page.inputValue('#ip0'), '1151');
check('R5_dataset_price',    await page.$eval('#ip0', s => s.options[s.selectedIndex].dataset.price), '115100');
check('R5_onchange_narx',    await page.inputValue('#ipr0'), '115100');
// (aniq format Node va brauzer ICU'sida farq qilishi mumkin — mazmuni tekshiriladi)
check('R5_jami_hisoblandi',  (await page.textContent('#cTotal')).startsWith('Jami:'), true);

// ── R6: MIJOZ — 1000 dan tashqaridagi mijoz topiladi va tanlanadi ──────────
await page.fill('#ssCust', 'Dilnoza');
await page.waitForTimeout(800);
check('R6_mijoz_serverdan_topildi',
      await page.$$eval('#cCustomerId option', o => o.map(x => x.textContent).filter(t => t.includes('Dilnoza'))),
      ['Dilnoza Karimova · +99890001112']);
check('R6_mijoz_tanlandi', await page.inputValue('#cCustomerId'), '1112');

// ── R7: DINAMIK qo'shilgan qator ham qidiruvli ─────────────────────────────
await page.evaluate(() => window.addItemRow());
await page.waitForTimeout(200);
check('R7_qator_qoshildi', await page.$$eval('#cItems .item-row', r => r.length), 2);
check('R7_har_qatorda_qidiruv',
      await page.$$eval('#cItems .item-row', rows => rows.every(r => !!r.querySelector('input[data-ss-input]'))), true);

await page.evaluate(() => { document.getElementById('ip1')._ss.input.id = 'ssRow1'; });
await page.fill('#ssRow1', 'KERASYS');
await page.waitForTimeout(800);
check('R7_qatorda_value', await page.inputValue('#ip1'), '1151');

// ── R8: modal QAYTA ochilganda mijoz filtri tozalanadi ─────────────────────
await page.evaluate(() => window.closeModal('createModal'));
await page.evaluate(() => window.openCreateModal());
await page.waitForTimeout(400);
check('R8_filtr_tozalandi', await page.$eval('#cCustomerId', s => s._ss.input.value), '');
// 1002 = 1000 boshlang'ich + serverdan topilgan Dilnoza (mahalliy ro'yxatga
// qo'shilgan, ya'ni filtr olib tashlangach ham tanlash mumkin) + "— Tanlang —"
check('R8_royxat_tiklandi', await page.$$eval('#cCustomerId option', o => o.length), 1002);
check('R8_mijoz_bosh',      await page.inputValue('#cCustomerId'), '');

check('R9_js_xato_yoq', errors, []);

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
