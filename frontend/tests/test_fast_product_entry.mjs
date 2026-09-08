/**
 * TEZ KIRITISH testi: "saqlash va yana qo'shish" + klaviatura.
 *
 * MUAMMO (mijozda, 1001 BARAKA): har mahsulotdan keyin modal YOPILARDI —
 * 62 mahsulot = 62 marta oyna ochish va 62 marta kategoriya tanlash.
 * Enter saqlamasdi, Escape esa umuman ishlamasdi (umumiy ishlovchi
 * `.modal-overlay.open` ni qidiradi, `#productModal` da bu klass yo'q).
 *
 * GOLDEN QOIDA: TAHRIRLASH rejimi tegilmasin — mavjud mahsulotni saqlagach
 * oyna avvalgidek YOPILISHI kerak. Test aynan shuni ham tekshiradi.
 *
 * Ishga tushirish:  node frontend/tests/test_fast_product_entry.mjs
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
  { id: 8, name: 'SOVUN',       is_active: true, display_order: 0 },
];

function fakeToken(bizType) {
  const payload = {
    sub: '1', user_id: 1, tenant_id: 27, business_type: bizType,
    features: ['inventory', 'barcode', 'scale'], exp: 4102444800, type: 'access',
  };
  const b64 = Buffer.from(JSON.stringify(payload)).toString('base64');
  return `x.${b64}.y`;
}

/** Sahifani ochadi, API'ni stublaydi. Qaytaradi: {page, posts, ctx} */
async function ochish(browser, bizType) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const tkn = fakeToken(bizType);
  await ctx.addInitScript((t) => {
    localStorage.setItem('access_token', t);
    localStorage.setItem('user', JSON.stringify({ id: 1, business_type: 'store' }));
  }, tkn);

  const posts = [];       // yozilgan mahsulotlar
  let nextId = 500;

  await page.route('**/api/v1/**', async (route) => {
    const req = route.request();
    const u = new URL(req.url());
    const path = u.pathname.replace('/api/v1', '');
    const json = (b, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) });

    if (path === '/categories/all') return json(CATS);

    if (path === '/products/' && req.method() === 'POST') {
      const body = JSON.parse(req.postData() || '{}');
      // Band barkodni taqlid qilamiz — xato yo'li ham tekshirilsin
      if (body.barcode === '9999999999999') {
        return json({ detail: 'Bu barcode band' }, 400);
      }
      posts.push(body);
      return json({ ...body, id: ++nextId });
    }
    if (/^\/products\/\d+$/.test(path) && req.method() === 'PATCH') {
      posts.push({ _patch: true, ...JSON.parse(req.postData() || '{}') });
      return json({ id: 1, name: 'tahrirlangan' });
    }
    // Shtrix-kod lookup — katalogdan nom keladi
    if (path.startsWith('/products/lookup/')) {
      const code = path.split('/').pop();
      if (code === '4780023325484') {
        return json({ barcode: code, found: true, source: 'catalog',
                      name: 'ECLAIR SOVUN', category: 'SOVUN', unit: 'dona', votes: 3 });
      }
      return json({ barcode: code, found: false });
    }
    if (path === '/products/') {
      return json({ items: [], total: 0, page: 1, page_size: 500, total_pages: 1 });
    }
    if (path.startsWith('/barcodes/product/')) return json([]);
    if (path === '/stations/' || path === '/departments/') return json([]);
    return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
  });

  await page.goto(`${BASE}/app/admin.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.openProductModal === 'function');
  await page.waitForTimeout(300);
  return { page, posts, ctx };
}

const ochiqmi = (page) =>
  page.$eval('#productModal', el => el.classList.contains('open'));

/** Formani to'ldiradi (kategoriya/birlik faqat berilsa). */
async function toldir(page, { nom, narx, tan, kat, birlik, barkod }) {
  if (nom    !== undefined) await page.fill('#pmf_name', nom);
  if (narx   !== undefined) await page.fill('#pmf_price', String(narx));
  if (tan    !== undefined) await page.fill('#pmf_cost_price', String(tan));
  if (barkod !== undefined) await page.fill('#pmf_barcode', barkod);
  if (kat    !== undefined) await page.selectOption('#pmf_category', String(kat));
  if (birlik !== undefined) await page.selectOption('#pmf_sale_unit', birlik);
}

const browser = await chromium.launch({ headless: true });

// ══════════════════════════════════════════════════════════════════════════════
// A) STORE — ketma-ket kiritish
// ══════════════════════════════════════════════════════════════════════════════
{
  const { page, posts } = await ochish(browser, 'store');

  await page.evaluate(() => window.openProductModal());
  await page.waitForTimeout(250);
  check('A0_oyna_ochildi', await ochiqmi(page), true);

  // ── 1-mahsulot: kategoriya + birlik + pachka to'ldiramiz ──
  await toldir(page, { nom: 'DURU SOVUN', narx: 12000, tan: 9000, kat: 8, birlik: 'pcs' });
  await page.fill('#pmf_pack_price', '96000');
  await page.fill('#pmf_pack_size', '8');
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(600);

  check('A1_oyna_OCHIQ_qoldi',   await ochiqmi(page), true);
  check('A1_nom_tozalandi',      await page.inputValue('#pmf_name'), '');
  check('A1_narx_tozalandi',     await page.inputValue('#pmf_price'), '');
  check('A1_tannarx_tozalandi',  await page.inputValue('#pmf_cost_price'), '');
  check('A1_barkod_tozalandi',   await page.inputValue('#pmf_barcode'), '');
  check('A1_KATEGORIYA_saqlandi', await page.inputValue('#pmf_category'), '8');
  check('A1_BIRLIK_saqlandi',     await page.inputValue('#pmf_sale_unit'), 'pcs');
  check('A1_kursor_nomda',
        await page.evaluate(() => document.activeElement?.id), 'pmf_name');
  check('A1_boshlangich_qoldiq_tozalandi', await page.inputValue('#pmf_stock'), '');
  // Pachka MAHSULOTGA XOS — keyingi mahsulotga o'tmasligi kerak
  check('A1_PACHKA_narxi_tozalandi', await page.inputValue('#pmf_pack_price'), '');
  check('A1_PACHKA_donasi_tozalandi', await page.inputValue('#pmf_pack_size'), '');

  // ── 2 va 3-mahsulot: kategoriya QAYTA tanlanmaydi ──
  await toldir(page, { nom: 'ECLAIR SOVUN', narx: 8000 });
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(600);
  await toldir(page, { nom: 'JASMINE SOVUN', narx: 9500 });
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(600);

  check('A2_uchtasi_ham_saqlandi', posts.length, 3);
  check('A2_nomlar', posts.map(p => p.name), ['DURU SOVUN', 'ECLAIR SOVUN', 'JASMINE SOVUN']);
  check('A2_KATEGORIYA_adashmadi', posts.map(p => p.category_id), [8, 8, 8]);
  check('A2_birlik_adashmadi',     posts.map(p => p.sale_unit), ['pcs', 'pcs', 'pcs']);
  check('A2_narxlar',              posts.map(p => p.price), [12000, 8000, 9500]);
  // Birinchisida pachka bor edi — keyingilariga O'TMAGAN bo'lishi shart
  check('A2_PACHKA_otmadi', posts.map(p => p.pack_price), [96000, null, null]);
  check('A2_PACHKA_dona_otmadi', posts.map(p => p.pack_size), [8, null, null]);
  check('A2_oyna_hamon_ochiq',     await ochiqmi(page), true);

  // ── X tugmasi ishlashda davom etadi ──
  await page.evaluate(() => window.closeProductModal());
  await page.waitForTimeout(200);
  check('A3_qolda_yopish_ishlaydi', await ochiqmi(page), false);

  await page.context().close();
}

// ══════════════════════════════════════════════════════════════════════════════
// B) TAHRIRLASH — eski xulq: saqlagach oyna YOPILADI
// ══════════════════════════════════════════════════════════════════════════════
{
  const { page, posts } = await ochish(browser, 'store');
  await page.evaluate(() => window.openProductModal({
    id: 1, name: 'ESKI NOM', price: 5000, cost_price: 3000, category_id: 7,
    sale_unit: 'pcs', is_available: true,
  }));
  await page.waitForTimeout(250);
  check('B0_tahrir_oynasi_ochildi', await ochiqmi(page), true);
  check('B0_nom_toldirilgan', await page.inputValue('#pmf_name'), 'ESKI NOM');

  await page.fill('#pmf_name', 'YANGI NOM');
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(600);

  check('B1_TAHRIRDA_oyna_YOPILDI', await ochiqmi(page), false);
  check('B1_patch_yuborildi', posts.filter(p => p._patch).length, 1);
  await page.context().close();
}

// ══════════════════════════════════════════════════════════════════════════════
// C) KLAVIATURA — Enter saqlaydi, Escape yopadi
// ══════════════════════════════════════════════════════════════════════════════
{
  const { page, posts } = await ochish(browser, 'store');

  await page.evaluate(() => window.openProductModal());
  await page.waitForTimeout(250);
  await toldir(page, { nom: 'ENTER TEST', narx: 7000, kat: 7 });
  await page.focus('#pmf_price');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(700);

  check('C1_Enter_saqladi',      posts.length, 1);
  check('C1_Enter_nomi',         posts[0]?.name, 'ENTER TEST');
  check('C1_Enter_oyna_ochiq',   await ochiqmi(page), true);

  // Escape — ilgari UMUMAN ishlamasdi
  await page.keyboard.press('Escape');
  await page.waitForTimeout(250);
  check('C2_Escape_yopdi', await ochiqmi(page), false);

  // Listener oqmaydi: oyna yopilgach Escape/Enter hech narsa qilmaydi
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  check('C3_yopilgach_Enter_saqlamaydi', posts.length, 1);

  // Select ichida Enter saqlamaydi (ro'yxatni yopishi kerak)
  await page.evaluate(() => window.openProductModal());
  await page.waitForTimeout(250);
  await toldir(page, { nom: 'SELECT TEST', narx: 100 });
  await page.focus('#pmf_category');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  check('C4_select_ichida_Enter_saqlamaydi', posts.length, 1);

  await page.context().close();
}

// ══════════════════════════════════════════════════════════════════════════════
// D) XATO holati — forma ochiq qoladi, kiritilgan ma'lumot yo'qolmaydi
// ══════════════════════════════════════════════════════════════════════════════
{
  const { page, posts } = await ochish(browser, 'store');
  await page.evaluate(() => window.openProductModal());
  await page.waitForTimeout(250);

  // narx bo'sh → frontend validatsiyasi
  await toldir(page, { nom: 'NARXSIZ', kat: 7 });
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(400);
  check('D1_narxsiz_saqlanmadi',  posts.length, 0);
  check('D1_oyna_ochiq',          await ochiqmi(page), true);
  check('D1_nom_yoqolmadi',       await page.inputValue('#pmf_name'), 'NARXSIZ');

  // band barkod → server 400
  await toldir(page, { narx: 5000, barkod: '9999999999999' });
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(600);
  check('D2_band_barkod_saqlanmadi', posts.length, 0);
  check('D2_oyna_ochiq',             await ochiqmi(page), true);
  check('D2_nom_yoqolmadi',          await page.inputValue('#pmf_name'), 'NARXSIZ');
  check('D2_barkod_qizardi',
        await page.$eval('#pmf_barcode', el => el.style.borderColor), 'rgb(239, 68, 68)');

  await page.context().close();
}

// ══════════════════════════════════════════════════════════════════════════════
// E) SHTRIX-KOD avtomatik to'ldirish hali ham ishlaydi
// ══════════════════════════════════════════════════════════════════════════════
{
  const { page } = await ochish(browser, 'store');
  await page.evaluate(() => window.openProductModal());
  await page.waitForTimeout(250);

  await page.fill('#pmf_barcode', '4780023325484');
  await page.waitForTimeout(900);                 // 400ms debounce + so'rov

  check('E1_nom_toldirildi',       await page.inputValue('#pmf_name'), 'ECLAIR SOVUN');
  check('E1_kategoriya_mos_keldi', await page.inputValue('#pmf_category'), '8');
  check('E1_hint_korindi',
        await page.$eval('#pmBcHint', el => el.style.display !== 'none'), true);

  // Skaner Enter yuboradi — bu SAQLAMASLIGI kerak (narx hali yo'q)
  await page.fill('#pmf_barcode', '4780023325484');
  await page.focus('#pmf_barcode');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(700);
  check('E2_barkod_maydonida_Enter_saqlamaydi', await ochiqmi(page), true);

  await page.context().close();
}

// ══════════════════════════════════════════════════════════════════════════════
// F) BOSHQA BIZNES TURLARI — forma buzilmasin (FORM_CONFIGS boshqacha)
// ══════════════════════════════════════════════════════════════════════════════
for (const [biz, kutilgan] of [
  ['restaurant', ['pmf_name', 'pmf_price', 'pmf_sale_unit', 'pmf_category', 'pmf_station', 'pmf_description']],
  ['pharmacy',   ['pmf_name', 'pmf_price', 'pmf_sale_unit', 'pmf_category', 'pmf_barcode', 'pmf_active_ingredient']],
]) {
  const { page, posts } = await ochish(browser, biz);
  await page.evaluate(() => window.openProductModal());
  await page.waitForTimeout(300);

  const bor = await page.evaluate((ids) => ids.every(i => !!document.getElementById(i)), kutilgan);
  check(`F_${biz}_maydonlar_joyida`, bor, true);
  check(`F_${biz}_barkod_yoq_bolsa_xato_bermaydi`,
        await page.evaluate(() => !!document.getElementById('pmf_name')), true);

  // Ketma-ket saqlash bu turlarda ham ishlaydi (barkod maydoni yo'q bo'lsa ham)
  await page.fill('#pmf_name', `${biz} mahsuloti`);
  await page.fill('#pmf_price', '15000');
  await page.selectOption('#pmf_category', '7');
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(700);

  check(`F_${biz}_saqlandi`, posts.length, 1);
  check(`F_${biz}_oyna_ochiq_qoldi`, await ochiqmi(page), true);
  check(`F_${biz}_kategoriya_saqlandi`, await page.inputValue('#pmf_category'), '7');
  check(`F_${biz}_nom_tozalandi`, await page.inputValue('#pmf_name'), '');

  await page.context().close();
}

await browser.close();
server.close();
console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
