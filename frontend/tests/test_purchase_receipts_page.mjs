/**
 * PRIYOMKA SAHIFASI (purchase_receipts.html) — o'ralgan API javobi.
 *
 * api.js javobi {success,data,error}; sahifa ilgari uni xom o'qirdi →
 * firmalar/mahsulotlar/kirimlar bo'sh, "Yangi tovar" serverda yaratilsa ham
 * "Mahsulot yaratilmadi" (qayta bosish → dublikat), tasdiqlash "Xatolik".
 *
 * Stub SERVER shaklini qaytaradi (xom JSON) — o'rashni api.js o'zi qiladi.
 *
 * Ishga tushirish (D:\cafe dan):  node frontend/tests/test_purchase_receipts_page.mjs
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

function fakeToken() {
  const payload = { sub: '1', user_id: 1, tenant_id: 27, business_type: 'store',
                    features: ['inventory', 'barcode'], exp: 4102444800, type: 'access' };
  return `x.${Buffer.from(JSON.stringify(payload)).toString('base64')}.y`;
}
const page_ = (items) => ({ items, total: items.length, page: 1, page_size: 100, total_pages: 1 });

const SUPPLIERS = [{ id: 3, name: 'Ta\'minot MChJ' }, { id: 4, name: 'Kerasys' }];
const PRODUCTS  = [{ id: 11, name: 'VERITA', price: 10000, cost_price: 7000, barcode: '111' }];
const RECEIPT   = { id: 1, receipt_date: '2026-10-13', supplier_id: 3, supplier_name: 'Ta\'minot MChJ',
                    invoice_number: 'NL-1', total_amount: 75000, net_amount: 75000, status: 'draft',
                    notes: null, items: [{ id: 1, product_id: 11, product_name: 'VERITA', quantity: 10,
                    unit_price: 7500, total_price: 75000, brak_qty: 0 }] };

/** opts.productPost: 'ok' | 'band' ; opts.confirmStatus: 'confirmed' | 'paid' */
async function ochish(browser, opts = {}) {
  const ctx = await browser.newContext();
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  const page = await ctx.newPage();
  await ctx.addInitScript((t) => {
    localStorage.setItem('access_token', t);
    localStorage.setItem('user', JSON.stringify({ id: 1, business_type: 'store', role: 'admin' }));
  }, fakeToken());
  const log = { productPosts: [], receiptPosts: [], confirms: 0 };
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace('/api/v1', '');
    const m = req.method();
    const json = (b, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) });
    if (path === '/suppliers-b2b/') return json(page_(SUPPLIERS));
    if (path === '/products/' && m === 'GET') return json(page_(PRODUCTS));
    if (path === '/categories/all') return json([{ id: 8, name: 'SOVUN' }]);
    if (path === '/products/' && m === 'POST') {
      const body = JSON.parse(req.postData() || '{}');
      log.productPosts.push(body);
      if (opts.productPost === 'band') return json({ detail: 'Bu barcode band' }, 400);
      return json({ ...body, id: 500 });
    }
    if (path.startsWith('/barcodes/lookup/')) {
      const code = decodeURIComponent(path.split('/').pop());
      if (opts.productPost === 'band' && code === '4780000000017')
        return json({ id: 77, name: 'OLDINGI SOVUN', price: 15000, cost_price: 9000, barcode: code });
      return json({ detail: 'Barcode topilmadi' }, 404);
    }
    if (path === '/purchase-receipts/' && m === 'GET') return json(page_([RECEIPT]));
    if (path === '/purchase-receipts/' && m === 'POST') {
      log.receiptPosts.push(JSON.parse(req.postData() || '{}'));
      return json({ ...RECEIPT, id: 2 });
    }
    if (path === '/purchase-receipts/1' && m === 'GET') return json(RECEIPT);
    if (path === '/purchase-receipts/1/confirm') {
      log.confirms++;
      return json({ ...RECEIPT, status: opts.confirmStatus || 'confirmed' });
    }
    return json(page_([]));
  });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.accept());
  await page.goto(`${BASE}/app/purchase_receipts.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#nSupplier option').length > 0, null, { timeout: 8000 })
    .catch(() => {});
  await page.waitForTimeout(400);
  return { page, ctx, log, errors };
}

const bodyHas = (page, s) => page.evaluate((s) => document.body.innerText.includes(s), s);

const browser = await chromium.launch();

// ── A) Ro'yxatlar to'ladi ───────────────────────────────────────────────────
{
  const { page, ctx, errors } = await ochish(browser);
  check('A_filtr_firmalar', await page.$$eval('#filterSupplier option', os => os.map(o => o.textContent)),
        ['Barcha firmalar', "Ta'minot MChJ", 'Kerasys']);
  check('A_yangi_kirim_firmalar', await page.$$eval('#nSupplier option', os => os.map(o => o.value)), ['3', '4']);
  check('A_mahsulot_qatori', await page.$$eval('#itemsBody tr:first-child select option', os => os.map(o => o.value)), ['11']);
  check('A_kirimlar_jadvali', await page.$$eval('#tableBody tr', trs => trs.map(t => t.cells[2]?.textContent.trim())),
        ["Ta'minot MChJ"]);
  check('A_JS_xatosi_yoq', errors, []);
  await ctx.close();
}

// ── B) Kirim yaratish + tasdiqlash ──────────────────────────────────────────
for (const st of ['confirmed', 'paid']) {
  const { page, ctx, log, errors } = await ochish(browser, { confirmStatus: st });
  if (st === 'confirmed') {
    await page.evaluate(() => {
      document.getElementById('newModal').classList.add('active');
      const row = document.querySelector('#itemsBody tr');
      row.cells[1].querySelector('input').value = '10';
      row.cells[2].querySelector('input').value = '7500';
    });
    await page.evaluate(() => window.createReceipt());
    await page.waitForTimeout(500);
    check('B_kirim_POST', log.receiptPosts.map(b => [b.supplier_id, b.items.map(i => [i.product_id, i.quantity, i.unit_price])]),
          [[3, [[11, 10, 7500]]]]);
    check('B_saqlandi_xabari', await bodyHas(page, 'Priyomka saqlandi'), true);
    check('B_modal_yopildi', await page.$eval('#newModal', el => el.classList.contains('active')), false);
  }
  await page.evaluate(() => window.openDetail(1));
  await page.waitForTimeout(300);
  check(`B_${st}_detal_ochildi`, await page.$eval('#detailModal', el => el.classList.contains('active')), true);
  check(`B_${st}_tasdiq_tugmasi`, await page.$eval('#btnConfirm', el => el.style.display), '');
  await page.evaluate(() => window.confirmReceipt());
  await page.waitForTimeout(500);
  check(`B_${st}_tasdiqlandi`, [log.confirms, await bodyHas(page, 'Priyomka tasdiqlandi')], [1, true]);
  check(`B_${st}_JS_xatosi_yoq`, errors, []);
  await ctx.close();
}

// ── C) Yangi tovar: bir marta yaratiladi, xato ko'rsatilmaydi ───────────────
async function yangiTovar(page) {
  await page.evaluate(() => {
    window.onReceiptProductNotFound('4780000000017');
    document.getElementById('npName').value = 'YANGI SOVUN';
    document.getElementById('npPrice').value = '15000';
    document.getElementById('npCat').value = '8';
  });
  await page.evaluate(() => window.saveNewProduct());
  await page.waitForTimeout(500);
}
{
  const { page, ctx, log, errors } = await ochish(browser);
  await yangiTovar(page);
  check('C_POST_bir_marta', log.productPosts.length, 1);
  check('C_muvaffaqiyat_xabari', await bodyHas(page, "Tovar qo'shildi"), true);
  check('C_xato_xabari_YOQ', await bodyHas(page, 'yaratilmadi'), false);
  check('C_modal_yopildi', await page.$eval('#npModal', el => el.classList.contains('active')), false);
  check('C_kirim_qatorida', await page.$eval('#itemsBody tr:first-child select', s => s.value), '500');
  check('C_JS_xatosi_yoq', errors, []);
  await ctx.close();
}

// ── D) Barkod band (oldingi urinish yaratib bo'lgan) → mavjudi ishlatiladi ──
{
  const { page, ctx, log, errors } = await ochish(browser, { productPost: 'band' });
  await yangiTovar(page);
  check('D_POST_bir_marta', log.productPosts.length, 1);
  check('D_xato_xabari_YOQ', await bodyHas(page, 'yaratilmadi'), false);
  check('D_mavjud_haqida_xabar', await bodyHas(page, 'allaqachon bor: OLDINGI SOVUN'), true);
  check('D_kirim_qatorida_mavjud', await page.$eval('#itemsBody tr:first-child select', s => s.value), '77');
  check('D_tan_narx_qoyildi', await page.$eval('#itemsBody tr:first-child td:nth-child(3) input', i => i.value), '9000');
  check('D_JS_xatosi_yoq', errors, []);
  await ctx.close();
}

// ── E) "Hozir to'landi" — qarzga qoladi ko'rinadi va paid_now serverga ketadi ─
{
  const { page, ctx, log, errors } = await ochish(browser);
  await page.evaluate(() => document.getElementById('newModal').classList.add('active'));
  const row = '#itemsBody tr:first-child';
  await page.fill(`${row} td:nth-child(2) input`, '10');
  await page.fill(`${row} td:nth-child(3) input`, '7500');      // jami 75 000
  await page.fill('#nDiscount', '5000');                           // net 70 000
  check('E_bosh_maydon_quti_yashirin', await page.$eval('#debtAfterBox', el => el.style.display), 'none');
  await page.fill('#nPaidNow', '30000');
  check('E_quti_korindi', await page.$eval('#debtAfterBox', el => el.style.display), '');
  check('E_qarzga_qoladi', await page.$eval('#debtAfterLabel', el => el.textContent),
        await page.evaluate(() => (40000).toLocaleString('uz-UZ')));
  await page.fill('#nDiscount', '0');                              // net o'zgarsa qayta hisob
  check('E_chegirma_ozgarsa_qayta', await page.$eval('#debtAfterLabel', el => el.textContent),
        await page.evaluate(() => (45000).toLocaleString('uz-UZ')));
  await page.fill('#nPaidNow', '90000');                           // ortiqcha → 0, manfiy emas
  check('E_ortiqcha_tolov_0', await page.$eval('#debtAfterLabel', el => el.textContent), '0');
  await page.fill('#nPaidNow', '30000');
  await page.evaluate(() => window.createReceipt());
  await page.waitForTimeout(500);
  check('E_POST_paid_now', log.receiptPosts.map(b => b.paid_now), [30000]);
  check('E_yopilgach_tozalandi', [await page.$eval('#nPaidNow', i => i.value),
        await page.$eval('#debtAfterBox', el => el.style.display)], ['', 'none']);

  // Bo'sh qoldirilsa — 0 yuboriladi (avvalgi xulq)
  await page.evaluate(() => document.getElementById('newModal').classList.add('active'));
  await page.fill(`${row} td:nth-child(3) input`, '7500');
  await page.evaluate(() => window.createReceipt());
  await page.waitForTimeout(500);
  check('E_bosh_paid_now_0', log.receiptPosts.map(b => b.paid_now), [30000, 0]);
  check('E_JS_xatosi_yoq', errors, []);
  await ctx.close();
}

await browser.close();
server.close();
console.log(`\n${pass} OK, ${fail} FAIL`);
process.exit(fail ? 1 : 0);
