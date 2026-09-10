/**
 * MAHSULOTLAR RO'YXATI — "Qoldiq" ustuni testi.
 *
 * MUAMMO (mijozda, 1001 BARAKA): Mahsulotlar ro'yxatida qoldiq va o'lchov
 * birligi ko'rinmasdi — do'konchi har safar Ombor bo'limiga o'tishga majbur edi.
 *
 * GOLDEN QOIDALAR (aynan shu test tekshiradi):
 *  1. Qoldiq `/inventory/pos-stock` dan PARALLEL keladi. O'sha so'rov YIQILSA
 *     ham mahsulotlar ro'yxati BARIBIR ko'rinishi shart (ustun "—" bo'ladi).
 *  2. Ombor qatori yo'q mahsulot "—" ko'rsatadi (0 EMAS — qoldiq noma'lum).
 *  3. Kasrli qoldiq (0.5 kg, 1.3 kg) buzilmasdan chiqadi.
 *  4. Boshqa biznes turlari tegilmaydi — `_extraHeader/_extraCell` mantiqi
 *     saqlanadi (apteka → "Dozaj", restoran → "Shtrix-kod").
 *  5. Saralash faqat KLIENTDA — qo'shimcha so'rov yubormaydi va qidiruv/
 *     kategoriya filtrini buzmaydi.
 *
 * Ishga tushirish:  node frontend/tests/test_product_list_stock.mjs
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

const CATS = [
  { id: 7, name: 'ICHIMLIKLAR', is_active: true, display_order: 0 },
  { id: 8, name: 'ATIR',        is_active: true, display_order: 0 },
];

// `/products/` javobi — backend `category` OBYEKTINI qaytaradi (`category_name` EMAS).
const PRODUCTS = [
  { id: 101, name: 'COCA COLA 1L', price: 12000, sale_unit: 'pcs', barcode: '4780001', is_available: true,  category: { id: 7, name: 'ICHIMLIKLAR' }, dosage: '500mg' },
  { id: 102, name: 'SHAKAR',       price: 14000, sale_unit: 'kg',  barcode: '4780002', is_available: true,  category: { id: 8, name: 'ATIR' } },
  { id: 103, name: 'ATIR ml',      price: 90000, sale_unit: 'ml',  barcode: '4780003', is_available: false, category: { id: 8, name: 'ATIR' } },
  { id: 104, name: 'YANGI TOVAR',  price: 5000,  sale_unit: 'pcs', barcode: '4780004', is_available: true,  category: null },
];

// `/inventory/pos-stock` — 104 ATAYIN YO'Q (ombor qatorisiz mahsulot → "—")
const STOCK = [
  { product_id: 101, name: 'COCA COLA 1L', quantity: 12,  unit: 'dona' },
  { product_id: 102, name: 'SHAKAR',       quantity: 0.5, unit: 'kg'   },
  { product_id: 103, name: 'ATIR ml',      quantity: 1.3000000000000003, unit: 'kg' },
];

/** Sahifani ochadi, API'ni stublaydi. opts: {bizType, stockFails} */
async function ochish(browser, { bizType = 'store', stockFails = false } = {}) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const payload = {
    sub: '1', user_id: 1, tenant_id: 27, business_type: bizType,
    features: ['inventory', 'barcode'], exp: 4102444800, type: 'access',
  };
  const tkn = `x.${Buffer.from(JSON.stringify(payload)).toString('base64')}.y`;
  await ctx.addInitScript((t) => {
    localStorage.setItem('access_token', t);
    localStorage.setItem('user', JSON.stringify({ id: 1, business_type: 'store' }));
  }, tkn);

  const calls = [];        // yuborilgan so'rovlar (nechta va qaysi endpoint)
  const saqlanganlar = []; // POST /products/ tanalari
  const xatolar = [];      // sahifadagi JS xatolari
  page.on('pageerror', e => xatolar.push(String(e.message)));

  await page.route('**/api/v1/**', async (route) => {
    const u = new URL(route.request().url());
    const path = u.pathname.replace('/api/v1', '');
    calls.push(path + (u.search || ''));
    const json = (b, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) });

    if (path === '/categories/all') return json(CATS);
    if (path === '/inventory/pos-stock') {
      if (stockFails) return json({ detail: 'Ombor yiqildi' }, 500);
      return json({ items: STOCK, can_cost: false, block_oversell: false });
    }
    if (path === '/products/' && route.request().method() === 'POST') {
      saqlanganlar.push(JSON.parse(route.request().postData() || '{}'));
      return json({ id: 999, name: 'YANGI', price: 1000, sale_unit: 'pcs', category: null });
    }
    if (path === '/stations/' || path === '/departments/') return json([]);
    if (path.startsWith('/barcodes/product/')) return json([]);
    if (path === '/products/') {
      // qidiruv / kategoriya filtri — backend qiladi, biz taqlid qilamiz
      let items = PRODUCTS;
      const q = u.searchParams.get('search');
      const cat = u.searchParams.get('category_id');
      if (q)   items = items.filter(p => p.name.toLowerCase().includes(q.toLowerCase()));
      if (cat) items = items.filter(p => p.category && String(p.category.id) === cat);
      return json({ items, total: items.length, page: 1, page_size: 500, total_pages: 1 });
    }
    return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
  });

  await page.goto(`${BASE}/app/admin.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.loadProducts === 'function');
  return { page, ctx, calls, saqlanganlar, xatolar };
}

/** `calls` ichida shu prefiks bilan boshlanuvchi so'rovlar soni. */
const nechta = (calls, prefiks) => calls.filter(c => c.startsWith(prefiks)).length;

/** Jadval qatorlarini o'qiydi: har qator — katakchalar matni massivi. */
const qatorlar = (page) => page.$$eval('#productsBody tr', trs =>
  trs.map(tr => [...tr.children].map(td => td.textContent.trim())));

const nomlar = async (page) => (await qatorlar(page)).map(r => r[1]);
/** Qoldiq — 5-ustun (0:checkbox, 1:Nomi, 2:Kategoriya, 3:Narxi, 4:Qoldiq) */
const qoldiqlar = async (page) => (await qatorlar(page)).map(r => r[4]);

/** Mahsulotlar sahifasiga o'tadi (sarlavha bosilishi uchun u KO'RINISHI shart). */
const yukla = async (page) => {
  await page.evaluate(() => window.switchPage('products'));
  await page.waitForFunction(() => document.querySelectorAll('#productsBody tr').length > 0
                                && !document.querySelector('#productsBody td[colspan]'));
};

const browser = await chromium.launch();

// ── 1. Asosiy holat: qoldiq, birlik, kategoriya ──────────────────────────────
{
  const { page, ctx, xatolar } = await ochish(browser);
  await yukla(page);

  check('1_ustunlar_soni', (await qatorlar(page))[0].length, 8);
  check('1_sarlavhalar', await page.$$eval('#productsThead th', ths => ths.map(t => t.textContent.trim())),
        ['', 'Nomi', 'Kategoriya', 'Narxi', 'Qoldiq', 'Shtrix-kod', 'Status', 'Amallar']);
  check('1_qoldiq_butun',  (await qoldiqlar(page))[0], '12 dona');
  check('1_qoldiq_kasrli', (await qoldiqlar(page))[1], '0.5 kg');
  // float artefakti (1.3000000000000003) 3 xonaga yaxlitlanadi
  check('1_qoldiq_float_artefakt', (await qoldiqlar(page))[2], '1.3 kg');
  // ombor qatori YO'Q → "—" (0 emas)
  check('1_ombor_qatorisiz', (await qoldiqlar(page))[3], '—');

  // Kategoriya endi NOM ko'rsatadi (ilgari `category_name` o'qilardi → doim "—")
  check('1_kategoriya_nomi', (await qatorlar(page)).map(r => r[2]),
        ['ICHIMLIKLAR', 'ATIR', 'ATIR', '—']);

  // ID ustuni ko'rinmaydi, LEKIN checkbox value va onclick dagi p.id joyida
  check('1_id_ustuni_yoq', (await qatorlar(page)).some(r => r.includes('101')), false);
  check('1_checkbox_value', await page.$$eval('#productsBody .prod-cb', cbs => cbs.map(c => c.value)),
        ['101', '102', '103', '104']);
  check('1_ochirish_onclick_id',
        await page.$eval('#productsBody tr td.td-actions .danger', b => /deleteProduct\(101,/.test(b.getAttribute('onclick'))),
        true);
  check('1_js_xato_yoq', xatolar, []);

  await ctx.close();
}

// ── 2. pos-stock YIQILSA — ro'yxat baribir ko'rinadi ─────────────────────────
{
  const { page, ctx } = await ochish(browser, { stockFails: true });
  await yukla(page);

  check('2_royxat_koringan', (await nomlar(page)).length, 4);
  check('2_nomlar_joyida', await nomlar(page), ['COCA COLA 1L', 'SHAKAR', 'ATIR ml', 'YANGI TOVAR']);
  check('2_qoldiq_bosh', await qoldiqlar(page), ['—', '—', '—', '—']);
  check('2_kategoriya_ishlaydi', (await qatorlar(page))[0][2], 'ICHIMLIKLAR');

  await ctx.close();
}

// ── 3. Qoldiq bo'yicha saralash (klientda) ───────────────────────────────────
{
  const { page, ctx, calls } = await ochish(browser);
  await yukla(page);
  check('3_boshlangich_tartib', await nomlar(page), ['COCA COLA 1L', 'SHAKAR', 'ATIR ml', 'YANGI TOVAR']);

  // ⚠️ FAQAT ro'yxatga aloqador endpointlar sanaladi. `calls.length` ni butunlay
  // sanash FLAKY: admin.html da badge pollerlari bor (updatePendingBadge 15 s,
  // low-stock/reorder/debt 60–120 s) — ular tasodifan shu oynada tushib qolardi.
  const oldin = nechta(calls, '/products/') + nechta(calls, '/inventory/pos-stock');
  await page.click('#thStock');
  // kam → ko'p; ombori yo'q ("—") HAR DOIM oxirida
  check('3_kam_kop', await nomlar(page), ['SHAKAR', 'ATIR ml', 'COCA COLA 1L', 'YANGI TOVAR']);
  check('3_strelka_yuqoriga', await page.$eval('#thStock', t => t.textContent.trim()), 'Qoldiq ↑');

  await page.click('#thStock');
  check('3_kop_kam', await nomlar(page), ['COCA COLA 1L', 'ATIR ml', 'SHAKAR', 'YANGI TOVAR']);
  check('3_strelka_pastga', await page.$eval('#thStock', t => t.textContent.trim()), 'Qoldiq ↓');
  check('3_qoshimcha_sorov_yoq',
        (nechta(calls, '/products/') + nechta(calls, '/inventory/pos-stock')) - oldin, 0);

  // Qidiruv saralashni tiklaydi (server tartibi — nom bo'yicha)
  await page.fill('#productsSearch', 'ar');
  await page.waitForTimeout(650);
  check('3_qidiruv_ishlaydi', await nomlar(page), ['SHAKAR', 'YANGI TOVAR']);
  check('3_saralash_tiklandi', await page.$eval('#thStock', t => t.textContent.trim()), 'Qoldiq');
  check('3_qidiruvda_qoldiq_bor', await qoldiqlar(page), ['0.5 kg', '—']);

  // Kategoriya filtri
  await page.fill('#productsSearch', '');
  await page.waitForTimeout(650);
  await page.selectOption('#productsCatFilter', '8');
  await page.waitForTimeout(650);
  check('3_kategoriya_filtri', await nomlar(page), ['SHAKAR', 'ATIR ml']);
  check('3_filtrda_qoldiq_bor', await qoldiqlar(page), ['0.5 kg', '1.3 kg']);

  // Filtrlangan ro'yxat ichida ham saralash ishlaydi
  await page.click('#thStock');
  check('3_filtrda_saralash', await nomlar(page), ['SHAKAR', 'ATIR ml']);

  await ctx.close();
}

// ── 4. Boshqa biznes turlari buzilmasin (_extraHeader/_extraCell) ────────────
for (const [biz, sarlavha, katak] of [
  ['pharmacy',   'Dozaj',        '500mg'],
  ['restaurant', 'Shtrix-kod',   '4780001'],
  ['hotel',      "Sig'im",       '—'],
  ['salon',      'Davomiylik',   '—'],
]) {
  const { page, ctx } = await ochish(browser, { bizType: biz });
  await yukla(page);
  check(`4_${biz}_extra_sarlavha`, await page.$eval('#thExtra', t => t.textContent.trim()), sarlavha);
  check(`4_${biz}_extra_katak`,   (await qatorlar(page))[0][5], katak);
  // Qoldiq ustuni hamma turda joyida
  check(`4_${biz}_qoldiq`,        (await qatorlar(page))[0][4], '12 dona');
  await ctx.close();
}

// ── 6. Qoldiq xaritasi KESHLANADI (v1.12.7 regressiyasi tuzatildi) ──────────
// Ilgari har qidiruv/filtr `/inventory/pos-stock` ni qayta tortardi — jonli
// serverda 442–909 ms. Endi sahifaga kirganda BIR MARTA olinadi.
{
  const { page, ctx, calls } = await ochish(browser);
  await yukla(page);
  check('6_sahifa_ochilganda_bir_marta', nechta(calls, '/inventory/pos-stock'), 1);

  // qidiruv → pos-stock QAYTA CHAQIRILMAYDI (products esa chaqiriladi)
  const prodOldin = nechta(calls, '/products/');
  await page.fill('#productsSearch', 'ar');
  await page.waitForTimeout(600);
  check('6_qidiruvda_posstock_qayta_yoq', nechta(calls, '/inventory/pos-stock'), 1);
  check('6_qidiruvda_products_chaqirildi', nechta(calls, '/products/') - prodOldin, 1);
  check('6_qidiruvda_qoldiq_saqlandi', await qoldiqlar(page), ['0.5 kg', '—']);

  // kategoriya filtri → ham qayta tortmaydi
  await page.fill('#productsSearch', '');
  await page.waitForTimeout(600);
  await page.selectOption('#productsCatFilter', '8');
  await page.waitForTimeout(650);
  check('6_filtrda_posstock_qayta_yoq', nechta(calls, '/inventory/pos-stock'), 1);

  // saralash → umuman so'rov yubormaydi
  // (badge pollerlari sanalmasin — yuqoridagi izohga qara)
  const jamiOldin = nechta(calls, '/products/') + nechta(calls, '/inventory/pos-stock');
  await page.click('#thStock');
  check('6_saralashda_sorov_yoq',
        (nechta(calls, '/products/') + nechta(calls, '/inventory/pos-stock')) - jamiOldin, 0);

  // "Yangilash" tugmasi → QAYTA tortiladi
  // (`page.click` emas: offline-banner overlay bosishni to'sadi — to'g'ridan chaqiramiz)
  await page.evaluate(() => document.getElementById('refreshBtn').click());
  await page.waitForTimeout(700);
  check('6_yangilash_qayta_tortdi', nechta(calls, '/inventory/pos-stock'), 2);

  await ctx.close();
}

// ── 6b. DEBOUNCE: tez yozishda bitta so'rov ─────────────────────────────────
{
  const { page, ctx, calls } = await ochish(browser);
  await yukla(page);
  const oldin = nechta(calls, '/products/');

  await page.type('#productsSearch', 'coca', { delay: 40 });   // 4 harf, 40ms oraliq
  await page.waitForTimeout(700);
  check('6b_debounce_bitta_sorov', nechta(calls, '/products/') - oldin, 1);
  check('6b_natija_togri', await nomlar(page), ['COCA COLA 1L']);

  await ctx.close();
}

// ── 6c. Mahsulot saqlangach xarita YANGILANADI ──────────────────────────────
{
  const { page, ctx, calls, saqlanganlar } = await ochish(browser);
  await yukla(page);
  check('6c_boshlangich', nechta(calls, '/inventory/pos-stock'), 1);

  await page.evaluate(() => window.openProductModal());
  await page.fill('#pmf_name', 'TEST MAHSULOT');
  await page.fill('#pmf_price', '9000');
  await page.selectOption('#pmf_category', '7');
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(900);

  check('6c_saqlandi', saqlanganlar.length, 1);
  check('6c_saqlagach_xarita_yangilandi', nechta(calls, '/inventory/pos-stock'), 2);

  await ctx.close();
}

// ── 5. Mobil: jadval gorizontal suriladi (sahifa emas) ───────────────────────
{
  const ctx = await browser.newContext({ viewport: { width: 375, height: 720 } });
  const page = await ctx.newPage();
  await ctx.close();
  // markup emas, CSS qoidasi tekshiriladi — .data-table-wrap ≤768px da overflow-x:auto
  const css = await readFile(join(ROOT, 'styles', 'admin.css'), 'utf8');
  const mobil = /@media\s*\(max-width:768px\)\s*\{[^}]*\.data-table-wrap\{[^}]*overflow-x:auto/.test(css);
  check('5_mobil_gorizontal_skroll', mobil, true);
}

await browser.close();
server.close();
console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
