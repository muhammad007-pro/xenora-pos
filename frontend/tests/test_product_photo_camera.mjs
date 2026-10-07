/**
 * MAHSULOT RASMI: "📷 Rasmga olish" + "📁 Fayldan tanlash" + klient siqish.
 *
 * Joylar: admin.html mahsulot formasi (js/admin/core.js), inventory.html,
 * suppliers.html, purchase_receipts.html — hammasida bir xil ikki tugma.
 *
 * Tekshiriladi:
 *   • kamera input'i `capture="environment"` (AI-Ombor bilan bir xil), fayl
 *     input'ida `capture` YO'Q (kompyuterda oddiy fayl tanlash)
 *   • tugma bosilganda AYNAN to'g'ri input'ning fayl oynasi ochiladi
 *   • katta telefon rasmi (>5 MB) yuklashdan oldin 1600px gacha kichrayadi
 *   • kichik fayl O'ZGARMASDAN yuboriladi (mavjud yo'l buzilmagan)
 *   • server rad etsa — "rasm yuklanmadi" xabari (ilgari jim yutilardi)
 *
 * Ishga tushirish:  node frontend/tests/test_product_photo_camera.mjs
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

const CATS = [{ id: 8, name: 'SOVUN', is_active: true, display_order: 0 }];

function fakeToken() {
  const payload = { sub: '1', user_id: 1, tenant_id: 27, business_type: 'store',
                    features: ['inventory', 'barcode'], exp: 4102444800, type: 'access' };
  return `x.${Buffer.from(JSON.stringify(payload)).toString('base64')}.y`;
}

/** Multipart tanasidan birinchi fayl qismini ajratadi: { filename, type, bytes } */
function multipartFile(buf, contentType) {
  const boundary = '--' + /boundary=(.+)$/.exec(contentType)[1];
  const s = buf.toString('latin1');
  const start = s.indexOf(boundary);
  const hdrEnd = s.indexOf('\r\n\r\n', start);
  const end = s.indexOf('\r\n' + boundary, hdrEnd);
  const hdr = s.slice(start, hdrEnd);
  return {
    filename: (/filename="([^"]*)"/.exec(hdr) || [])[1],
    type: (/Content-Type:\s*(\S+)/i.exec(hdr) || [])[1],
    bytes: buf.subarray(hdrEnd + 4, end),
  };
}

/** JPEG o'lchami (SOF marker) — tashqi kutubxonasiz */
function jpegSize(b) {
  let i = 2;
  while (i < b.length) {
    if (b[i] !== 0xFF) return null;
    const m = b[i + 1];
    const len = b.readUInt16BE(i + 2);
    if (m >= 0xC0 && m <= 0xCF && ![0xC4, 0xC8, 0xCC].includes(m)) {
      return [b.readUInt16BE(i + 7), b.readUInt16BE(i + 5)];   // [w, h]
    }
    i += 2 + len;
  }
  return null;
}

/** Sahifani ochadi, API'ni stublaydi. uploads[] — /products/{id}/image so'rovlari */
async function ochish(browser, url, { imageStatus = 200 } = {}) {
  const ctx = await browser.newContext();
  // Tashqi resurslar (Google Fonts, CDN) testni osib qo'yadi — faqat lokal server
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  const page = await ctx.newPage();
  await ctx.addInitScript((t) => {
    localStorage.setItem('access_token', t);
    localStorage.setItem('user', JSON.stringify({ id: 1, business_type: 'store', role: 'admin' }));
  }, fakeToken());
  const uploads = [];
  let nextId = 700;
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.replace('/api/v1', '');
    const json = (b, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) });
    if (/^\/products\/\d+\/image$/.test(path) && req.method() === 'POST') {
      uploads.push(multipartFile(req.postDataBuffer(), req.headers()['content-type']));
      if (imageStatus !== 200) return json({ detail: "Rasm hajmi juda katta (ko'pi bilan 5 MB)" }, imageStatus);
      return json({ message: 'Rasm yuklandi', image_url: '/uploads/products/tenant_27/product_1_ab12cd34.webp' });
    }
    if (path === '/categories/all' || path === '/categories/') return json(CATS);
    if (path === '/products/' && req.method() === 'POST') {
      const body = JSON.parse(req.postData() || '{}');
      return json({ ...body, id: ++nextId });
    }
    if (path === '/stations/' || path === '/departments/') return json([]);
    return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
  });
  await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' });
  return { page, ctx, uploads };
}

/** Brauzerda rasm yaratadi (shovqin — telefon fotosiga o'xshab yomon siqiladi) */
async function makeImage(page, w, h, type, quality = 0.95, alpha = false) {
  const b64 = await page.evaluate(async ({ w, h, type, quality, alpha }) => {
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    const ctx = c.getContext('2d');
    const img = ctx.createImageData(w, h);
    for (let i = 0; i < img.data.length; i += 4) {
      img.data[i] = Math.random() * 255; img.data[i + 1] = Math.random() * 255;
      img.data[i + 2] = Math.random() * 255; img.data[i + 3] = alpha ? (i % 8 ? 0 : 255) : 255;
    }
    ctx.putImageData(img, 0, 0);
    const blob = await new Promise(r => c.toBlob(r, type, quality));
    const u8 = new Uint8Array(await blob.arrayBuffer());
    let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode(...u8.subarray(i, i + 0x8000));
    return btoa(s);
  }, { w, h, type, quality, alpha });
  return Buffer.from(b64, 'base64');
}

/** Tugmani bosib, ochilgan fayl oynasining input id'si va capture'ini qaytaradi */
async function chooser(page, btnSel, file) {
  const [fc] = await Promise.all([page.waitForEvent('filechooser'), page.click(btnSel)]);
  const info = await fc.element().evaluate(el => ({ id: el.id, capture: el.getAttribute('capture') }));
  if (file) await fc.setFiles(file);
  return info;
}

const browser = await chromium.launch({ headless: true });

// ══════════════════════════════════════════════════════════════════════════════
// A) XenoraPhoto.shrink — birlik darajasida (admin.html konteksti)
// ══════════════════════════════════════════════════════════════════════════════
{
  const { page, ctx } = await ochish(browser, '/app/admin.html');
  await page.waitForFunction(() => !!window.XenoraPhoto);
  const r = await page.evaluate(async () => {
    const mk = async (w, h, type, q, alpha) => {
      const c = document.createElement('canvas'); c.width = w; c.height = h;
      const x = c.getContext('2d'); const d = x.createImageData(w, h);
      for (let i = 0; i < d.data.length; i += 4) {
        d.data[i] = Math.random() * 255; d.data[i + 1] = Math.random() * 255;
        d.data[i + 2] = Math.random() * 255; d.data[i + 3] = alpha ? 0 : 255;
      }
      x.putImageData(d, 0, 0);
      const b = await new Promise(res => c.toBlob(res, type, q));
      return new File([b], 'IMG_2026.' + (type === 'image/png' ? 'png' : 'jpg'), { type });
    };
    const dims = async (f) => { const bm = await createImageBitmap(f); return [bm.width, bm.height]; };
    const out = {};
    const big = await mk(4000, 3000, 'image/jpeg', 0.95);
    const s1 = await XenoraPhoto.shrink(big);
    out.big = { inMB: +(big.size / 1048576).toFixed(1), outKB: Math.round(s1.size / 1024),
                type: s1.type, name: s1.name, dims: await dims(s1) };
    const tall = await mk(1200, 2400, 'image/jpeg', 0.95);
    out.tall = await dims(await XenoraPhoto.shrink(tall));
    const small = await mk(300, 200, 'image/jpeg', 0.8);
    out.smallSame = (await XenoraPhoto.shrink(small)) === small;
    const png = await mk(2400, 2400, 'image/png', undefined, true);
    const s2 = await XenoraPhoto.shrink(png);
    const bm = await createImageBitmap(s2);
    const cc = document.createElement('canvas'); cc.width = 4; cc.height = 4;
    const cx = cc.getContext('2d'); cx.drawImage(bm, 0, 0);
    out.png = { type: s2.type, dims: [bm.width, bm.height], alpha: cx.getImageData(1, 1, 1, 1).data[3] };
    const txt = new File(['salom'], 'a.txt', { type: 'text/plain' });
    out.txtSame = (await XenoraPhoto.shrink(txt)) === txt;
    const fake = new File(['<svg/>'], 'x.jpg', { type: 'image/jpeg' });
    out.brokenSame = (await XenoraPhoto.shrink(fake)) === fake;
    return out;
  });
  console.log('    katta rasm:', r.big.inMB, 'MB ->', r.big.outKB, 'KB');
  check('A1_katta_rasm_5MB_dan_katta_edi', r.big.inMB > 5, true);
  check('A1_1600px_gacha_kichraydi', r.big.dims, [1600, 1200]);
  check('A1_hajm_1MB_dan_kichik', r.big.outKB < 1024, true);
  check('A1_JPEG_qoladi', [r.big.type, r.big.name], ['image/jpeg', 'IMG_2026.jpg']);
  check('A2_tik_rasm_nisbat_saqlanadi', r.tall, [800, 1600]);
  check('A3_kichik_fayl_TEGILMAYDI', r.smallSame, true);
  check('A4_png_webp_ga_alfa_saqlanadi', [r.png.type, r.png.dims, r.png.alpha], ['image/webp', [1600, 1600], 0]);
  check('A5_rasm_emas_TEGILMAYDI', r.txtSame, true);
  check('A6_buzuq_rasm_asl_holida_qaytadi', r.brokenSame, true);
  await ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════════
// B) admin.html — mahsulot formasi (core.js)
// ══════════════════════════════════════════════════════════════════════════════
{
  const { page, ctx, uploads } = await ochish(browser, '/app/admin.html');
  await page.waitForFunction(() => typeof window.openProductModal === 'function');
  await page.waitForTimeout(300);
  await page.evaluate(() => window.openProductModal());
  await page.waitForTimeout(250);

  check('B0_tugmalar', await page.$$eval('#pmBody .xp-picker button', bs => bs.map(b => b.textContent.trim())),
        ['📷 Rasmga olish', '📁 Fayldan tanlash']);
  check('B0_kamera_capture', await page.getAttribute('#pmf_image_cam', 'capture'), 'environment');
  check('B0_fayl_capture_YOQ', await page.getAttribute('#pmf_image', 'capture'), null);
  check('B0_accept', [await page.getAttribute('#pmf_image_cam', 'accept'), await page.getAttribute('#pmf_image', 'accept')],
        ['image/*', 'image/*']);

  // 1) Kamera → katta telefon rasmi → kichrayib yuklanadi
  const big = await makeImage(page, 4000, 3000, 'image/jpeg');
  const c1 = await chooser(page, '#pmf_image_cam_btn', { name: 'IMG_20261007.jpg', mimeType: 'image/jpeg', buffer: big });
  check('B1_kamera_tugmasi_kamera_inputini_ochadi', c1, { id: 'pmf_image_cam', capture: 'environment' });
  check('B1_preview_korinadi', await page.$eval('#pmImgPrev', el => el.style.display !== 'none' && !!el.src), true);
  await page.fill('#pmf_name', 'KAMERA SOVUN');
  await page.fill('#pmf_price', '12000');
  await page.selectOption('#pmf_category', '8');
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(1500);
  check('B1_rasm_yuklandi', uploads.length, 1);
  const u1 = uploads[0];
  check('B1_yuborilgan_JPEG_1600px', jpegSize(u1.bytes), [1600, 1200]);
  check('B1_yuborilgan_5MB_dan_ancha_kichik', u1.bytes.length < 1024 * 1024 && big.length > 5 * 1024 * 1024, true);

  // 2) Fayldan tanlash → kichik rasm O'ZGARMASDAN ketadi (mavjud yo'l)
  const small = await makeImage(page, 320, 240, 'image/jpeg', 0.8);
  const c2 = await chooser(page, '#pmf_image_btn', { name: 'logo.jpg', mimeType: 'image/jpeg', buffer: small });
  check('B2_fayl_tugmasi_fayl_inputini_ochadi', c2, { id: 'pmf_image', capture: null });
  await page.fill('#pmf_name', 'FAYL SOVUN');
  await page.fill('#pmf_price', '9000');
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(1200);
  check('B2_ikkinchi_yuklash', uploads.length, 2);
  check('B2_kichik_fayl_bayt_bayt_bir_xil', Buffer.compare(uploads[1].bytes, small) === 0, true);
  check('B2_fayl_nomi_saqlandi', uploads[1].filename, 'logo.jpg');

  // 3) Ketma-ket kiritish: oldingi rasm keyingi mahsulotga O'TMAYDI
  await page.fill('#pmf_name', 'RASMSIZ SOVUN');
  await page.fill('#pmf_price', '7000');
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(900);
  check('B3_rasmsiz_mahsulotda_yuklash_YOQ', uploads.length, 2);
  await ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════════
// C) admin.html — server rasmni rad etsa xabar chiqadi (ilgari jim edi)
// ══════════════════════════════════════════════════════════════════════════════
{
  const { page, ctx, uploads } = await ochish(browser, '/app/admin.html', { imageStatus: 400 });
  await page.waitForFunction(() => typeof window.openProductModal === 'function');
  await page.waitForTimeout(300);
  await page.evaluate(() => window.openProductModal());
  await page.waitForTimeout(250);
  const small = await makeImage(page, 320, 240, 'image/jpeg', 0.8);
  await chooser(page, '#pmf_image_btn', { name: 'a.jpg', mimeType: 'image/jpeg', buffer: small });
  await page.fill('#pmf_name', 'XATO SOVUN');
  await page.fill('#pmf_price', '5000');
  await page.selectOption('#pmf_category', '8');
  await page.evaluate(() => window.saveProduct());
  await page.waitForTimeout(1200);
  const toasts = await page.$$eval('#toasts .toast', ts => ts.map(t => t.textContent));
  check('C1_yuklash_urinildi', uploads.length, 1);
  check('C1_rasm_xatosi_korsatildi', toasts.some(t => t.includes('rasm yuklanmadi') && t.includes('5 MB')), true);
  await ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════════
// D) inventory / suppliers / purchase_receipts — bir xil ikki tugma + yuklash
// ══════════════════════════════════════════════════════════════════════════════
// ⚠️ purchase_receipts.html: "Yangi tovar" saqlash OLDINDAN buzuq (2026-10-07
// aniqlandi, bu branchda tuzatilmagan) — sahifa api.js ning O'RALGAN javobini
// ({success,data}) xom deb o'qiydi → `prod.id` undefined → "Mahsulot
// yaratilmadi" (server esa mahsulotni yaratib bo'lgan). Shu sabab u yerda
// faqat tugma/kamera/preview tekshiriladi, yuklash emas.
for (const [url, openCls, saveFn, uploadWorks] of [
  ['/app/inventory.html', 'open', 'saveNewProduct', true],
  ['/app/suppliers.html', 'active', 'recSaveNewProduct', true],
  ['/app/purchase_receipts.html', 'active', 'saveNewProduct', false],
]) {
  const tag = url.split('/').pop().replace('.html', '');
  for (const imageStatus of (uploadWorks ? [200, 400] : [200])) {
    const { page, ctx, uploads } = await ochish(browser, url, { imageStatus });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.waitForSelector('#npImageCamBtn', { state: 'attached' });
    await page.waitForFunction(() => !!window.XenoraPhoto);
    await page.waitForTimeout(500);
    await page.evaluate((c) => document.getElementById('npModal').classList.add(c), openCls);

    if (imageStatus === 200) {
      check(`D_${tag}_tugmalar`, await page.$$eval('#npModal .xp-picker button', bs => bs.map(b => b.textContent.trim())),
            ['📷 Rasmga olish', '📁 Fayldan tanlash']);
      check(`D_${tag}_kamera_capture`, await page.getAttribute('#npImageCam', 'capture'), 'environment');
      check(`D_${tag}_fayl_capture_YOQ`, await page.getAttribute('#npImage', 'capture'), null);
      const cf = await chooser(page, '#npImageBtn', null);
      check(`D_${tag}_fayl_tugmasi`, cf, { id: 'npImage', capture: null });
    }

    const big = await makeImage(page, 4000, 3000, 'image/jpeg');
    const cc = await chooser(page, '#npImageCamBtn', { name: 'IMG_1.jpg', mimeType: 'image/jpeg', buffer: big });
    check(`D_${tag}_${imageStatus}_kamera_tugmasi`, cc, { id: 'npImageCam', capture: 'environment' });
    check(`D_${tag}_${imageStatus}_preview`,
          await page.$eval('#npImagePreview', el => el.style.display !== 'none' && !!el.src), true);

    if (!uploadWorks) {
      check(`D_${tag}_JS_xatosi_yoq`, errors, []);
      await ctx.close();
      continue;
    }

    await page.fill('#npName', 'TEST TOVAR');
    await page.fill('#npPrice', '15000');
    await page.evaluate(() => {
      const s = document.getElementById('npCat');
      if (![...s.options].some(o => o.value === '8')) s.add(new Option('SOVUN', '8'));
      s.value = '8';
    });
    await page.evaluate((fn) => window[fn] ? window[fn]() : null, saveFn);
    await page.waitForTimeout(1500);

    check(`D_${tag}_${imageStatus}_yuklandi`, uploads.length, 1);
    if (uploads[0]) check(`D_${tag}_${imageStatus}_1600px`, jpegSize(uploads[0].bytes), [1600, 1200]);
    if (imageStatus === 400) {
      const shown = await page.evaluate(() => document.body.innerText.includes('rasm yuklanmadi'));
      check(`D_${tag}_400_xabar_korsatildi`, shown, true);
    }
    check(`D_${tag}_${imageStatus}_JS_xatosi_yoq`, errors, []);
    await ctx.close();
  }
}

await browser.close();
server.close();
console.log(`\n${pass} OK, ${fail} FAIL`);
process.exit(fail ? 1 : 0);
