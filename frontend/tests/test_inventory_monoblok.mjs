/**
 * OMBOR JADVALI — sensor monoblokda +/− tugmalari ko'rinsin (fix/inventory-precision).
 *
 * MUAMMO (jonli, 1001 BARAKA, 2026-10-14, ~1024px YesPOS monoblok):
 *   `.data-table-wrap{overflow:hidden}` keng ombor jadvalining o'ng tomonini —
 *   "Amallar" ustunidagi + (kirim) / − (hisobdan o'chirish) tugmalarini —
 *   kesib tashlardi, skroll ham yo'q edi. mobile.css faqat ≤768px ni ushlardi.
 *
 * Qotiriladi (1024 / 1280 / 1366 / 1920 px):
 *   1) + va − tugmalari ko'rinadi VA bosiladi (elementFromPoint markazda — tugmaning o'zi)
 *   2) jadval o'z o'ramida suriladi, sahifa gorizontal surilmaydi
 *   3) "+" bosilsa kirim oynasi ochiladi (amal haqiqatan ishlaydi)
 *   4) qoldiq 3 xonagacha: 8.665000000000001 → "8.665"
 *   5) fmtQty birlik testlari
 *
 * Ishga tushirish:  node frontend/tests/test_inventory_monoblok.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { readFileSync } from 'fs';
import { resolve, extname, join } from 'path';
import vm from 'node:vm';

const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };
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

// ── 5) fmtQty ──────────────────────────────────────────────────────────────
console.log('\n── 5) fmtQty ──');
const mctx = { window: {} };
vm.createContext(mctx);
vm.runInContext(readFileSync(resolve(ROOT, 'js/core/money.js'), 'utf8'), mctx);
const fq = mctx.window.fmtQty;
check('5_float_xato', fq(0.265 + 8.4), '8.665');
check('5_butun', fq(3), '3');
check('5_nol_kasr', fq(2.5), '2.5');
check('5_mayda_qoldiq', fq(9e-15), '0');
check('5_manfiy', fq(-0.0005), '0');
check('5_manfiy_kasr', fq(-1.2345), '-1.234');

// BARAKA'ga o'xshash ma'lumot: uzun nom, 13 raqamli barkod, kg kasr
const ITEMS = Array.from({ length: 12 }, (_, i) => ({
  id: 100 + i, quantity: i === 0 ? 0.265 + 8.4 : (i % 3 ? 182 : 0), unit: i % 2 ? 'dona' : 'kg',
  min_threshold: 5, max_threshold: 100, last_restock: '2026-10-14T06:00:00Z',
  product: { id: 2000 + i, name: i === 0 ? 'DOKTORSKAYA VARENAYA KOLBASA PREMIUM' : `MAHSULOT NOMI UZUNROQ ${i}`,
             barcode: '4780069000' + String(100 + i), price: 125000, cost_price: 100000, pack_size: 0, pack_price: 0 },
}));
const tok = `x.${Buffer.from(JSON.stringify({ sub: '1', user_id: 1, tenant_id: 27, business_type: 'supermarket', features: [], exp: 4102444800 })).toString('base64')}.y`;

const browser = await chromium.launch({ headless: true });
for (const [w, h] of [[1024, 768], [1280, 800], [1366, 768], [1920, 1080]]) {
  console.log(`\n── ${w}x${h} ──`);
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, serviceWorkers: 'block', hasTouch: w === 1024 });
  await ctx.addInitScript(([t]) => {
    if (sessionStorage.getItem('__s')) return; sessionStorage.setItem('__s', '1');
    localStorage.setItem('access_token', t); localStorage.setItem('business_type', 'supermarket');
    localStorage.setItem('user', JSON.stringify({ id: 1, role: { name: 'admin' }, business_type: 'supermarket' }));
  }, [tok]);
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  await ctx.route('**/api/**', r => {
    const p = new URL(r.request().url()).pathname.replace(/.*\/api\/v1/, '');
    const body = p === '/inventory/' ? { items: ITEMS, total: ITEMS.length } : { items: [], total: 0 };
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`${BASE}/app/admin.html`, { waitUntil: 'domcontentloaded', timeout: 40000 });
  await page.waitForFunction(() => typeof window.switchPage === 'function', null, { timeout: 15000 });
  await page.evaluate(() => window.switchPage('inventory'));
  await page.waitForFunction(() => document.querySelectorAll('#invBody tr').length === 12, null, { timeout: 8000 });
  await page.waitForTimeout(500);   // kirish animatsiyasi

  const r = await page.evaluate(() => {
    const row = document.querySelector('#invBody tr');
    const res = {};
    // TO'LIQ ko'rinish: tugma butunlay o'ramning KO'RINADIGAN qismi ichida bo'lsin.
    // (Markaz nuqtasi yetarli emas: main'da "−" o'ng cheti 16px kesilgan, markazi esa
    // chegaradan 1px ichkarida edi — kesilish tekshiruvdan o'tib ketardi.)
    const wrap = row.closest('.data-table-wrap');
    const btns = row.querySelectorAll('td.td-actions .act-btn');
    for (const [k, b] of [['plus', btns[0]], ['minus', btns[1]], ['chegara', btns[2]]]) {
      b.scrollIntoView({ block: 'center' });
      // ⚠️ scrollIntoView overflow:hidden o'ramni ham DASTUR orqali gorizontal suradi —
      // foydalanuvchi buni qila olmaydi. Haqiqiy holat: o'ram boshida (scrollLeft 0).
      wrap.scrollLeft = 0;
      const rc = b.getBoundingClientRect(), wr = wrap.getBoundingClientRect();
      const hit = document.elementFromPoint(rc.left + rc.width / 2, rc.top + rc.height / 2);
      res[k] = { toliqKorinadi: rc.left >= wr.left - 0.5 && rc.right <= wr.right + 0.5 && rc.right <= innerWidth,
                 clickable: !!hit && (hit === b || b.contains(hit)) };
    }
    res.pageHScroll = document.documentElement.scrollWidth > innerWidth + 1;
    res.qty = row.querySelector('td:nth-child(3) span').textContent.trim();
    return res;
  });
  check(`1_${w}_plus_korinadi_bosiladi`, r.plus, { toliqKorinadi: true, clickable: true });
  check(`1_${w}_minus_korinadi_bosiladi`, r.minus, { toliqKorinadi: true, clickable: true });
  check(`1_${w}_chegara_korinadi_bosiladi`, r.chegara, { toliqKorinadi: true, clickable: true });
  check(`2_${w}_sahifa_gorizontal_surilmaydi`, r.pageHScroll, false);
  check(`4_${w}_qoldiq_3_xona`, r.qty, '8.665 kg');
  if (w === 1024) {
    // bosishdan OLDIN — haqiqiy ko'rinish (Playwright click yashirin o'ramni ham surib yuboradi)
    await page.screenshot({ path: `${process.env.TEMP || '.'}/inv_monoblok_1024.png` });
    await page.click('#invBody tr:first-child .act-btn:not(.act-danger)');
    const opened = await page.waitForFunction(() => document.getElementById('restockModal')?.classList.contains('open'),
      null, { timeout: 3000 }).then(() => true).catch(() => false);
    check('3_plus_kirim_oynasini_ochadi', opened, true);
  }
  check(`${w}_xatosiz`, errors, []);
  await ctx.close();
}
await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
