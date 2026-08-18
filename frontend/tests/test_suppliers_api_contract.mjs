/**
 * REGRESSIYA QO'RIQCHISI: suppliers.html — API javob shartnomasi.
 *
 * MUAMMO (mijozda, Fazza Parfum): "Firma qo'shish" da qizil "Xatolik" chiqardi.
 * `js/core/api.js` HAR DOIM O'RALGAN javob qaytaradi:
 *     { success:true, data:<javob>, status }   |   { success:false, error:'...', status }
 * suppliers.html esa XOM javob kutardi (`res.id`, `res.items`, `res.detail`):
 *   • muvaffaqiyatli qo'shilganda ham `res.id` undefined  -> qizil "Xatolik"
 *   • serverning HAQIQIY xato matni (`res.error`) hech qachon ko'rsatilmasdi
 *   • `masterInit` da `supRes.items` -> firmalar/mahsulotlar ro'yxati BO'SH
 *
 * Bu test HAQIQIY sahifani brauzerda ochadi (Playwright), tarmoqni mock qiladi
 * va firma qo'shish oqimini boshidan oxirigacha bosib ko'radi.
 *
 * Ishga tushirish:  node frontend/tests/test_suppliers_api_contract.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { resolve, extname, join } from 'path';

// ES modul importlari `file://` da CORS sabab BLOKLANADI — kichik statik server
// ko'taramiz (port dev-server ro'yxatida EMAS, shuning uchun api.js nisbiy
// `/api/v1` ni tanlaydi va route mock'i uni ushlaydi).
const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
               '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = createServer(async (req, res) => {
  try {
    const p = join(ROOT, decodeURIComponent(req.url.split('?')[0]));
    const body = await readFile(p);
    res.writeHead(200, { 'Content-Type': MIME[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404); res.end('not found');
  }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const PORT = server.address().port;
const PAGE = `http://127.0.0.1:${PORT}/app/suppliers.html`;

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

// Serverni taqlid qilamiz: api.js file:// da http://localhost:8000/api/v1 ga boradi
function makeRoutes(page, state) {
  return page.route('**/api/v1/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace('/api/v1', '');
    const json = (body, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (req.method() === 'POST' && path === '/suppliers-b2b/') {
      state.posts.push(JSON.parse(req.postData() || '{}'));
      if (state.failNext) {
        return json({ detail: "Bu INN allaqachon ro'yxatda bor" }, 400);
      }
      return json({ id: 77, name: 'TEST', tax_id: '302831456', is_active: true,
                    tenant_id: 26, created_at: '2026-08-18T00:00:00Z' });
    }
    if (path === '/suppliers-b2b/' )    return json({ items: state.suppliers, total: state.suppliers.length, page: 1, page_size: 200, total_pages: 1 });
    if (path === '/products/')          return json({ items: [{ id: 1, name: 'Ayva', price: 5500 }], total: 1, page: 1, page_size: 500, total_pages: 1 });
    if (path === '/categories/all')     return json([{ id: 1, name: 'Parfum' }]);
    if (path === '/suppliers-b2b/debt-summary') return json([]);
    if (path === '/purchase-receipts/') return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
    if (path === '/supplier-returns/')  return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
    if (path === '/supplier-payments/') return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
    return json({});
  });
}

const browser = await chromium.launch({ headless: true });

// ── 1. Firma qo'shish — MUVAFFAQIYAT ────────────────────────────────────────
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const state = { posts: [], suppliers: [], failNext: false };
  await ctx.addInitScript(() => localStorage.setItem('access_token', 'test.token.x'));
  await makeRoutes(page, state);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));

  await page.goto(PAGE);
  await page.waitForFunction(() => typeof window.saveFirm === 'function');

  await page.click('#btnAddFirm');
  await page.fill('#fName', 'TEST');
  await page.fill('#fInn', '302831456');
  await page.fill('#fPhone', '+998 71 200 20 20');
  await page.fill('#fAddress', 'Toshkent');
  await page.fill('#fContract', 'SH-12');
  await page.fill('#fContact', 'Alisher');
  await page.fill('#fDelay', '0');
  await page.click('#btnSaveFirm');
  await page.waitForTimeout(400);

  const toast = await page.evaluate(() => document.body.innerText.match(/Qo'shildi|Xatolik|Firma saqlanmadi/)?.[0] || '(toast yo\'q)');
  check('T1_POST_yuborildi', state.posts.length, 1);
  check('T1_payload_nom', state.posts[0]?.name, 'TEST');
  check('T1_payload_inn', state.posts[0]?.tax_id, '302831456');
  check('T1_otsrochka_nol_qabul', state.posts[0]?.payment_delay_days, 0);
  check('T1_muvaffaqiyat_toast', toast, "Qo'shildi");
  check('T1_modal_yopildi', await page.locator('#firmModal.active').count(), 0);
  check('T1_js_xato_yoq', errors, []);
  await ctx.close();
}

// ── 2. Server XATOSI — matn TO'LIQ ko'rinsin ("Xatolik" emas) ───────────────
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const state = { posts: [], suppliers: [], failNext: true };
  await ctx.addInitScript(() => localStorage.setItem('access_token', 'test.token.x'));
  await makeRoutes(page, state);
  await page.goto(PAGE);
  await page.waitForFunction(() => typeof window.saveFirm === 'function');

  await page.click('#btnAddFirm');
  await page.fill('#fName', 'TEST');
  await page.click('#btnSaveFirm');
  await page.waitForTimeout(400);

  const txt = await page.evaluate(() => document.body.innerText);
  check('T2_server_matni_korinadi', txt.includes("Bu INN allaqachon ro'yxatda bor"), true);
  check('T2_qisqartirilgan_Xatolik_yoq', /(^|\s)Xatolik(\s|$)/.test(txt), false);
  check('T2_modal_ochiq_qoldi', await page.locator('#firmModal.active').count(), 1);
  await ctx.close();
}

// ── 3. Ro'yxat (GET) — o'ralgan javobdan o'qilsin ───────────────────────────
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const state = {
    posts: [], failNext: false,
    suppliers: [{ id: 1, name: 'ECO AROMA', tax_id: '123', phone: '+998', is_active: true, payment_delay_days: 5 }],
  };
  await ctx.addInitScript(() => localStorage.setItem('access_token', 'test.token.x'));
  await makeRoutes(page, state);
  await page.goto(PAGE);
  await page.waitForFunction(() => typeof window.loadFirms === 'function');
  await page.waitForTimeout(500);

  const bodyTxt = await page.locator('#firmTableBody').innerText();
  check('T3_royxat_korinadi', bodyTxt.includes('ECO AROMA'), true);
  check('T3_bosh_deb_kormaydi', bodyTxt.includes('Firmalar topilmadi'), false);
  // dropdownlar ham to'ldirilishi kerak (masterInit `suppliers` massivi)
  const optCount = await page.locator('#retSupplier option').count();
  check('T3_dropdown_toldirildi', optCount > 0, true);
  await ctx.close();
}

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
