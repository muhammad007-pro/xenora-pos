/**
 * CHEKDAGI SHTRIX-KOD — chek buzilmasligi va balandlik o'smasligi.
 *
 * Nimani qulflaydi:
 *   1. `buildReceipt58()` chiqishida `.receipt-barcode[data-barcode]` bor
 *      (LAN/ESC-POS yo'li AYNAN shu atributni o'qiydi — `electron/main.js`)
 *   2. SVG 58mm va 80mm kontentiga SIG'ADI (chetdan chiqib ketmaydi)
 *   3. Chek balandligi KESKIN oshmaydi (~8mm dan ko'p emas)
 *   4. `order_number` yo'q bo'lsa chek AVVALGIDEK chiqadi (blok qo'shilmaydi)
 *   5. Mavjud bloklar (jami, footer, fiskal QR) joyida qoladi
 *
 * ⚠️ BU TEST FIZIK SKANERLASHNI ALMASHTIRMAYDI. USB yo'lida chiziqlarni biz
 * chizamiz; bir marta chek bosib, skaner o'qishini tasdiqlash SHART.
 * Shu skript namuna chekni `screenshots/` ga saqlaydi — telefon skaneri
 * bilan ham sinab ko'rish mumkin.
 *
 * Ishga tushirish:  node frontend/tests/test_receipt_barcode.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile, writeFile, mkdir } from 'fs/promises';
import { resolve, extname, join } from 'path';

const ROOT = resolve('frontend');
const OUT = resolve('screenshots');
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

const REC = {
  cafe_name: 'NICE SHOPPING GROUP',
  cafe_address: "Marg'ilon sh.",
  order_number: '2610029124',
  date: '02.10.2026 10:02',
  items: [
    { name: 'HOFF Q38-E-004', quantity: 1, unit_price: 250000, total: 250000 },
    { name: 'POLWON PW199-300 METR', quantity: 2, unit_price: 25000, total: 50000 },
  ],
  subtotal: 300000, discount_amount: 10000, final_amount: 290000,
  payment_methods: [{ method: 'cash', amount: 290000 }],
};

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto(`${BASE}/shared/login.html`, { waitUntil: 'domcontentloaded' });
await page.addScriptTag({ type: 'module', content: `
  import { buildReceipt58, wrapDoc, paperSpec } from '${BASE}/js/core/receipt-print.js';
  window.__build = buildReceipt58;
  window.__wrap = wrapDoc;
  window.__spec = paperSpec;
  window.__ready = true;
`});
await page.waitForFunction(() => window.__ready === true);

// ── 1) data-barcode atributi (LAN yo'li shuni o'qiydi) ───────────────────────
const bc = await page.evaluate(rec => {
  const el = document.createElement('div');
  el.innerHTML = window.__build(rec);
  const b = el.querySelector('.receipt-barcode[data-barcode]');
  return {
    bor: !!b,
    qiymat: b ? b.getAttribute('data-barcode') : null,
    svg: b ? !!b.querySelector('svg') : false,
    // Jamidan KEYIN, footer'dan OLDIN turishi kerak
    totalsdanKeyin: b ? !!(el.querySelector('.receipt-totals').compareDocumentPosition(b) & 4) : false,
    footerdanOldin: b ? !!(b.compareDocumentPosition(el.querySelector('.receipt-footer')) & 4) : false,
  };
}, REC);
check('1_data_barcode_bor', bc.bor, true);
check('1_qiymat_order_number', bc.qiymat, '2610029124');
check('1_svg_chizildi', bc.svg, true);
check('1_jamidan_keyin', bc.totalsdanKeyin, true);
check('1_footerdan_oldin', bc.footerdanOldin, true);

// ── 2) order_number yo'q → blok QO'SHILMAYDI (eski chek buzilmaydi) ─────────
const yoq = await page.evaluate(rec => {
  const r = Object.assign({}, rec); delete r.order_number; delete r.order_id;
  const el = document.createElement('div');
  el.innerHTML = window.__build(r);
  return {
    barcode: !!el.querySelector('.receipt-barcode'),
    totals: !!el.querySelector('.receipt-totals'),
    footer: !!el.querySelector('.receipt-footer'),
  };
}, REC);
check('2_kodsiz_barcode_yoq', yoq.barcode, false);
check('2_kodsiz_jami_joyida', yoq.totals, true);
check('2_kodsiz_footer_joyida', yoq.footer, true);

// ── 3) 58mm va 80mm: SVG kontentga SIG'ADI ──────────────────────────────────
for (const [paper, contentMm] of [[58, 48], [80, 72]]) {
  const o = await page.evaluate(({ rec, paper }) => {
    const r = Object.assign({}, rec, { paper_width: paper });
    document.body.innerHTML = window.__wrap(window.__build(r), 'chek', { paperWidth: paper });
    const box = document.querySelector('.r58');
    const svg = document.querySelector('.receipt-barcode svg');
    return {
      kontentPx: box ? box.getBoundingClientRect().width : 0,
      svgPx: svg ? svg.getBoundingClientRect().width : 0,
      balandlikPx: box ? box.getBoundingClientRect().height : 0,
    };
  }, { rec: REC, paper });
  check(`3_${paper}mm_svg_sigdi`, o.svgPx > 0 && o.svgPx <= o.kontentPx, true);
  console.log(`       ${paper}mm: kontent ${o.kontentPx.toFixed(1)}px, svg ${o.svgPx.toFixed(1)}px`);
}

// ── 4) BALANDLIK: shtrix-kod bilan va busiz farqi ───────────────────────────
const h = await page.evaluate(rec => {
  const olch = (r) => {
    document.body.innerHTML = window.__wrap(window.__build(r), 'chek', { paperWidth: 58 });
    return document.querySelector('.r58').getBoundingClientRect().height;
  };
  const bilan = olch(rec);
  const r2 = Object.assign({}, rec); delete r2.order_number; delete r2.order_id;
  const busiz = olch(r2);
  return { bilan, busiz, farqPx: bilan - busiz };
}, REC);
// 96 dpi da 1mm ≈ 3.78px. 6mm kod + ~2mm bo'shliq ≈ 30px. 45px dan oshmasin.
check('4_balandlik_farqi_kichik', h.farqPx > 0 && h.farqPx < 45, true);
console.log(`       balandlik: ${h.busiz.toFixed(1)}px → ${h.bilan.toFixed(1)}px `
          + `(+${h.farqPx.toFixed(1)}px ≈ ${(h.farqPx / 3.7795).toFixed(1)}mm)`);

// ── 5) Fiskal QR bilan birga — chalkashmaslik (kod tepada, QR pastda) ───────
const fisk = await page.evaluate(rec => {
  const r = Object.assign({}, rec, { fiscal_qr_url: 'https://consumer.invoice.uz/x', fiscal_number: 12345 });
  const el = document.createElement('div');
  el.innerHTML = window.__build(r);
  const b = el.querySelector('.receipt-barcode');
  const qr = el.querySelector('img[alt="Fiskal QR"]');
  return { ikkisiBor: !!b && !!qr, kodQRdanOldin: !!(b && qr && (b.compareDocumentPosition(qr) & 4)) };
}, REC);
check('5_kod_va_QR_birga', fisk.ikkisiBor, true);
check('5_kod_QRdan_oldin', fisk.kodQRdanOldin, true);

// ── 6) LAN YO'LI: electron/main.js DOM-o'quvchisi chekdan nimani oladi ──────
// Bu eng muhim tekshiruv: printerga AYNAN shu qiymat `GS k` bilan ketadi.
// `_RECEIPT_EXTRACT_JS` ni main.js dan O'QIB, chek DOM'ida bajaramiz.
{
  const src = await readFile(resolve('electron/main.js'), 'utf8');
  const m = src.match(/const _RECEIPT_EXTRACT_JS = `([\s\S]*?)`;/);
  check('6_extract_js_topildi', !!m, true);
  if (m) {
    // main.js da JS satr ichida `\\s` kabi ikkilangan qochishlar bor —
    // template literalda qanday bo'lsa, shunday bajaramiz.
    const extractJs = m[1].replace(/\\\\/g, '\\');
    const got = await page.evaluate(({ rec, js }) => {
      document.body.innerHTML = window.__wrap(window.__build(rec), 'chek', { paperWidth: 58 });
      // eslint-disable-next-line no-eval
      const r = eval(js);
      return { barcode: r.barcode, meta: r.meta, totals: (r.totals || []).length };
    }, { rec: REC, js: extractJs });
    check('6_LAN_barcode_qiymati', got.barcode, '2610029124');
    check('6_LAN_meta_joyida', /2610029124/.test(got.meta || ''), true);
    check('6_LAN_jami_joyida', got.totals > 0, true);

    // order_number yo'q → barcode null (GS k yuborilmaydi)
    const yoq2 = await page.evaluate(({ rec, js }) => {
      const r2 = Object.assign({}, rec); delete r2.order_number; delete r2.order_id;
      document.body.innerHTML = window.__wrap(window.__build(r2), 'chek', { paperWidth: 58 });
      // eslint-disable-next-line no-eval
      return eval(js).barcode;
    }, { rec: REC, js: extractJs });
    check('6_LAN_kodsiz_null', yoq2, null);
  }
}

// ── NAMUNA CHEK — foydalanuvchi bosib/skanerlab ko'rishi uchun ──────────────
await mkdir(OUT, { recursive: true });
for (const paper of [58, 80]) {
  const html = await page.evaluate(({ rec, paper }) => {
    const r = Object.assign({}, rec, { paper_width: paper });
    return window.__wrap(window.__build(r), 'XENORA namuna chek', { paperWidth: paper });
  }, { rec: REC, paper });
  const f = join(OUT, `namuna_chek_${paper}mm.html`);
  await writeFile(f, html, 'utf8');
  console.log(`       namuna saqlandi: ${f}`);
}

await browser.close();
server.close();
console.log('');
console.log(`${pass} o'tdi, ${fail} yiqildi`);
if (fail) process.exit(1);
