/**
 * BOSQICH B testi: qidiruvli select CLASSIC kontekstda.
 *
 * Bosqich A modul kontekstida edi (suppliers.html). Bu yerda asosiy texnik
 * xavf tekshiriladi: `js/admin/inventory.js` — CLASSIC skript, `window.
 * searchableSelect` unga to'g'ri yetib boradimi va skript TARTIBI to'g'rimi
 * (komponent js/admin/* dan OLDIN yuklanishi shart).
 *
 * Qamrov:
 *   1) admin.html — "Kirim qilish" (rmProdSel). Bu yerda value = INVENTORY id
 *      (product id EMAS) va dataset unit/packSize/packPrice — hammasi saqlanishi shart.
 *   2) inventory.html — prodSel. Bu ro'yxat "omborda HALI YO'Q" mahsulotlar;
 *      server qidiruvi butun katalogni qaytaradi, natija FILTRLANISHI kerak.
 *
 * Ishga tushirish:  node frontend/tests/test_searchable_select_stage_b.mjs
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

// 1200 mahsulot; 1151-chi "KERASYS shampun" — 1000 lik boshlang'ich ro'yxatdan TASHQARIDA
const PRODUCTS = Array.from({ length: 1200 }, (_, i) => ({
  id: i + 1, name: `Mahsulot ${i + 1}`, price: (i + 1) * 100,
  pack_size: 0, pack_price: 0,
}));
PRODUCTS[1150].name = 'KERASYS shampun';
PRODUCTS[1150].pack_size = 12;
PRODUCTS[1150].pack_price = 480000;

// Ombor: FAQAT dastlabki 500 mahsulot uchun qator bor (id = product_id + 5000).
// Ya'ni 501+ mahsulotlar "omborda HALI YO'Q" — inventory.html shularni taklif qiladi.
// KERASYS (1151) omborda YO'Q -> prodSel qidiruvida CHIQISHI kerak.
const INV = PRODUCTS.slice(0, 500).map(p => ({
  id: p.id + 5000, product_id: p.id, quantity: 7, unit: 'dona',
  min_threshold: 2, max_threshold: 50, product: p,
}));
// Ombor qidiruvi (admin "Kirim qilish") uchun KERASYS ham kerak — alohida qator
INV.push({ id: 1151 + 5000, product_id: 1151, quantity: 7, unit: 'dona',
           min_threshold: 2, max_threshold: 50, product: PRODUCTS[1150] });

// JWT: admin.html `features` claim'ini o'qiydi
const jwt = 'x.' + Buffer.from(JSON.stringify({
  sub: 'admin', features: [], business_type: 'store', role: 'admin',
})).toString('base64') + '.y';

async function routeAll(page, opts = {}) {
  await page.route('**/api/v1/**', async (route) => {
    const u = new URL(route.request().url());
    const path = u.pathname.replace('/api/v1', '');
    const q = (u.searchParams.get('search') || '').toLowerCase();
    const size = Number(u.searchParams.get('page_size') || u.searchParams.get('limit') || 20);
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) });

    if (path === '/inventory/') {
      const rows = (q ? INV.filter(i => i.product.name.toLowerCase().includes(q)) : INV).slice(0, size);
      return json({ items: rows, total: rows.length, page: 1, page_size: size, total_pages: 1 });
    }
    if (path === '/products/') {
      const rows = (q ? PRODUCTS.filter(p => p.name.toLowerCase().includes(q)) : PRODUCTS).slice(0, size);
      return json({ items: rows, total: rows.length, page: 1, page_size: size, total_pages: 1 });
    }
    if (path === '/products/all')   return json(PRODUCTS.slice(0, size));
    if (path === '/categories/all') return json([]);
    if (path.includes('/features'))  return json({ business_type: 'store', enabled_features: [] });
    if (path === '/suppliers-b2b/') return json({ items: [], total: 0, page: 1, page_size: 200, total_pages: 1 });
    return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
  });
}

const browser = await chromium.launch({ headless: true });

// ══════════ 1) admin.html — "Kirim qilish" (CLASSIC kontekst) ══════════
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  // AuthGuard `user` ni ham talab qiladi (faqat token yetmaydi) — aks holda
  // sahifa login.html ga yo'naltiriladi va test goto'da osilib qoladi.
  await ctx.addInitScript(([t]) => {
    localStorage.setItem('access_token', t);
    localStorage.setItem('business_type', 'store');
    localStorage.setItem('user', JSON.stringify({
      id: 1, username: 'admin', full_name: 'Admin', is_superuser: true,
      role: { name: 'admin' }, tenant_id: 26,
    }));
  }, [jwt]);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await routeAll(page);

  await page.goto(`${BASE}/app/admin.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.searchableSelect === 'function');
  check('B1_classic_kontekstda_komponent_bor', true, true);

  await page.waitForFunction(() => typeof window.openRestockPicker === 'function');
  await page.evaluate(() => window.openRestockPicker());
  await page.waitForTimeout(800);

  check('B2_qidiruv_inputi_qoshildi',
        await page.$$eval('#rmProdRow input[data-ss-input]', e => e.length), 1);
  check('B3_boshlangich_royxat_toliq',
        await page.$$eval('#rmProdSel option', o => o.length), 502);   // 501 ombor qatori + "Mahsulot tanlang..."

  // 1000 dan tashqaridagi mahsulot — SERVERDAN
  await page.fill('#rmProdRow input[data-ss-input]', 'KERASYS');
  await page.waitForTimeout(800);
  check('B4_serverdan_topildi',
        await page.$$eval('#rmProdSel option', o => o.map(x => x.textContent).filter(t => t.includes('KERASYS'))),
        ['KERASYS shampun — 7 dona']);

  // GOLDEN: value = INVENTORY id, dataset saqlangan, onchange ishlagan
  check('B5_value_inventory_id', await page.inputValue('#rmProdSel'), String(1151 + 5000));
  check('B5_dataset_unit',
        await page.$eval('#rmProdSel', s => s.options[s.selectedIndex].dataset.unit), 'dona');
  check('B5_dataset_packSize',
        await page.$eval('#rmProdSel', s => s.options[s.selectedIndex].dataset.packSize), '12');
  check('B6_js_xato_yoq', errors, []);
  await ctx.close();
}

// ══════════ 2) inventory.html — prodSel ("omborda YO'Q" semantikasi) ══════════
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await ctx.addInitScript(([t]) => {
    localStorage.setItem('access_token', t);
    localStorage.setItem('user', JSON.stringify({
      id: 1, username: 'admin', full_name: 'Admin', is_superuser: true,
      role: { name: 'admin' }, tenant_id: 26,
    }));
  }, [jwt]);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await routeAll(page);

  await page.goto(`${BASE}/app/inventory.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !!document.querySelector('#prodSel option'));
  await page.waitForTimeout(600);

  check('B7_qidiruv_inputi_qoshildi',
        await page.$$eval('#prodSelectRow input[data-ss-input]', e => e.length), 1);

  // "Qo'shish" modalini ochamiz — aks holda input KO'RINMAYDI (fill ishlamaydi)
  await page.evaluate(() => window.openAdd());
  await page.waitForTimeout(300);

  // (a) omborda YO'Q mahsulot (KERASYS, id 1151) — qidiruvda CHIQISHI kerak
  await page.fill('#prodSelectRow input[data-ss-input]', 'KERASYS');
  await page.waitForTimeout(800);
  check('B8a_omborda_yoqi_chiqadi',
        await page.$$eval('#prodSel option', o => o.map(x => x.textContent).filter(t => t.includes('KERASYS'))),
        ['KERASYS shampun']);

  // (b) omborda BOR mahsulot (Mahsulot 42) — semantika saqlanib, CHIQMASLIGI kerak
  await page.fill('#prodSelectRow input[data-ss-input]', 'Mahsulot 42');
  await page.waitForTimeout(800);
  check('B8b_omborda_bori_chiqmaydi',
        await page.$$eval('#prodSel option', o => o.map(x => x.textContent).filter(t => t === 'Mahsulot 42')),
        []);
  check('B9_js_xato_yoq', errors, []);
  await ctx.close();
}

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
