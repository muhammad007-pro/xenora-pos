/**
 * ETIKETKA — "Hammasini belgilash" (feature/labels-select-all, XOZMAG so'rovi).
 *
 * Qotiriladi:
 *   1) Sarlavha katakchasi: bosish → ko'rinayotgan, barcode'i bor hammasi
 *      belgilanadi; qayta bosish → belgi olinadi; qisman → indeterminate
 *   2) Filtr (qidiruv / kategoriya): faqat ko'rinayotganlar belgilanadi;
 *      filtr o'zgarsa belgilar SAQLANADI va "filtrda ko'rinmayapti" soni chiqadi;
 *      filtrlangan holda belgi olish yashirinlarga tegmaydi
 *   3) "N ta mahsulot tanlandi" + "Belgilarni tozalash"
 *   4) Chegara: 1000 ta mahsulot — preview 60 namuna; >300 etiketka tasdiq;
 *      A4 da >2000 etiketka to'siladi; bekor qilinsa chop etilmaydi
 *   5) GOLDEN: bittalab belgilash, son maydoni, kichik to'plam tasdiqsiz chop
 *
 * Ishga tushirish:  node frontend/tests/test_labels_select_all.mjs
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

const ATIR = { id: 1, name: 'ATIR' }, SOVUN = { id: 2, name: 'SOVUN' };
const mk = (id, name, cat, barcode = `47800000${String(id).padStart(5, '0')}`) =>
  ({ id, name, price: 1000 * id, barcode, category_id: cat.id, category: cat });
const SMALL = [
  mk(1, 'Atir Gucci', ATIR), mk(2, 'Atir Dior', ATIR), mk(3, 'Atir Chanel', ATIR),
  mk(4, 'Sovun Dove', SOVUN), mk(5, 'Sovun Lux', SOVUN),
  mk(6, 'Sovun kodsiz', SOVUN, null),          // barcode yo'q — tanlab bo'lmaydi
];
const BIG = Array.from({ length: 1000 }, (_, i) => mk(i + 1, `Tovar ${i + 1}`, i % 2 ? ATIR : SOVUN));

async function ochish(browser, products) {
  const ctx = await browser.newContext();
  // JsBarcode CDN'dan — stub (tarmoqsiz); boshqa tashqi so'rovlar to'xtatiladi
  await ctx.route(/cdn\.jsdelivr\.net/, r => r.fulfill({
    contentType: 'text/javascript', body: 'window.JsBarcode = function(){};' }));
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1|cdn\.jsdelivr)/, r => r.abort());
  await ctx.addInitScript(() => {
    localStorage.setItem('access_token', 'x.e30.y');
    window.__confirms = [];
    window.__confirmAnswer = true;
    window.confirm = (m) => { window.__confirms.push(m); return window.__confirmAnswer; };
    window.__printed = 0;
    window.print = () => { window.__printed++; };
  });
  const page = await ctx.newPage();
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '');
    const json = b => route.fulfill({ contentType: 'application/json', body: JSON.stringify(b) });
    if (path === '/products/all') return json(products);
    if (path === '/settings/label-printer') return json({ enabled: false });
    return json({});
  });
  await page.goto(`${BASE}/app/labels.html`);
  await page.waitForSelector('.product-item');
  return { page, ctx };
}

const st = page => page.evaluate(() => {
  const cb = document.getElementById('selectAll');
  return {
    checked: cb.checked, ind: cb.indeterminate, dis: cb.disabled,
    lbl: document.getElementById('selectAllLbl').textContent,
    count: document.getElementById('selectedCount').textContent,
    clearBtn: document.getElementById('clearSelBtn').style.display !== 'none',
    rows: [...document.querySelectorAll('.product-item.selected')].map(e => +e.dataset.id),
    total: document.getElementById('totalCount').textContent,
  };
});
const search = (page, v) => page.fill('#searchInput', v);   // fill → input hodisasi
const cat = (page, v) => page.selectOption('#catFilter', String(v));
const clickAll = page => page.click('.list-head');

const browser = await chromium.launch();
try {
  // ════════════════════════════════════════════════════════════════════════
  console.log('\n── 1) Hammasini belgilash / olish / qisman ──');
  let { page, ctx } = await ochish(browser, SMALL);
  let s = await st(page);
  check('1_boshlang_ich', [s.checked, s.ind, s.lbl], [false, false, "Hammasini belgilash (5 ta ko'rinayotgan)"]);
  check('1_tozalash_tugmasi_yashirin', s.clearBtn, false);

  await clickAll(page);
  s = await st(page);
  check('1_hammasi_belgilandi', s.rows, [1, 2, 3, 4, 5]);
  check('1_kodsiz_tanlanmadi', s.rows.includes(6), false);
  check('1_katakcha_checked', [s.checked, s.ind], [true, false]);
  check('1_soni', s.count, '5 ta mahsulot tanlandi · 5 etiketka');
  check('1_preview_jami', s.total, 'Jami: 5 mahsulot, 5 etiketka');

  await clickAll(page);
  s = await st(page);
  check('1_qayta_bosish_olindi', [s.rows, s.checked, s.ind], [[], false, false]);
  check('1_soni_nol', s.count, '0 ta tanlangan');

  await page.click('.product-item[data-id="2"]');               // GOLDEN: bittalab
  s = await st(page);
  check('1_qisman_indeterminate', [s.checked, s.ind], [false, true]);
  await clickAll(page);                                           // qisman → hammasi
  s = await st(page);
  check('1_qismandan_hammasi', [s.rows, s.checked, s.ind], [[1, 2, 3, 4, 5], true, false]);

  // ════════════════════════════════════════════════════════════════════════
  console.log('\n── 2) Filtr bilan ──');
  await page.click('#clearSelBtn');
  await cat(page, 2);                                              // SOVUN
  s = await st(page);
  check('2_kategoriya_yorliq', s.lbl, "Hammasini belgilash (2 ta ko'rinayotgan)");
  await clickAll(page);
  s = await st(page);
  check('2_faqat_sovun', s.rows, [4, 5]);

  await cat(page, '');                                             // filtr olindi
  s = await st(page);
  check('2_filtr_ozgarsa_belgilar_saqlanadi', s.rows, [4, 5]);
  check('2_endi_qisman', s.ind, true);

  await cat(page, 1);                                              // ATIR — sovunlar yashirin
  s = await st(page);
  check('2_yashirin_soni', s.count, "2 ta mahsulot tanlandi · 2 etiketka (2 tasi filtrda ko'rinmayapti)");
  check('2_atir_bosh_holat', [s.checked, s.ind], [false, false]);
  await clickAll(page);
  await cat(page, '');
  s = await st(page);
  check('2_ikki_kategoriya_yigildi', s.rows, [1, 2, 3, 4, 5]);

  await search(page, 'dior');                                      // qidiruv
  s = await st(page);
  check('2_qidiruv_checked', [s.checked, s.lbl], [true, "Hammasini belgilash (1 ta ko'rinayotgan)"]);
  await clickAll(page);                                            // faqat Dior olinadi
  await search(page, '');
  s = await st(page);
  check('2_filtrda_olish_yashiringa_tegmaydi', s.rows, [1, 3, 4, 5]);

  await search(page, 'yo\'q-narsa');
  s = await st(page);
  check('2_bosh_natija_disabled', [s.dis, s.lbl], [true, 'Hammasini belgilash']);
  await search(page, 'kodsiz');                                    // faqat barcode'siz
  s = await st(page);
  check('2_faqat_kodsiz_disabled', s.dis, true);

  // ════════════════════════════════════════════════════════════════════════
  console.log('\n── 3) Tozalash ──');
  await search(page, '');
  await page.click('#clearSelBtn');
  s = await st(page);
  check('3_tozalandi', [s.rows, s.count, s.clearBtn, s.checked, s.ind], [[], '0 ta tanlangan', false, false, false]);
  check('3_preview_bosh', s.total, 'Jami: 0 mahsulot, 0 etiketka');

  // ════════════════════════════════════════════════════════════════════════
  console.log('\n── 5) GOLDEN: mavjud oqim ──');
  await page.click('.product-item[data-id="3"]');
  await page.fill('.product-item[data-id="3"] .pi-qty', '4');
  await page.fill('.product-item[data-id="5"] .pi-qty', '2');     // son kiritish avto-tanlaydi
  s = await st(page);
  check('5_bittalab_va_son', [s.rows, s.count], [[3, 5], '2 ta mahsulot tanlandi · 6 etiketka']);
  await clickAll(page);                                            // qolganlari globalQty=1 bilan
  const qtys = await page.evaluate(() =>
    [...document.querySelectorAll('.product-item.selected .pi-qty')].map(i => +i.value));
  check('5_hammasi_mavjud_sonni_buzmaydi', qtys, [1, 1, 4, 1, 2]);
  await page.click('#clearSelBtn');
  await page.click('.product-item[data-id="1"]');
  await page.click('#printBtn');
  await page.waitForTimeout(400);
  const g = await page.evaluate(() => ({ c: window.__confirms.length, p: window.__printed,
    labels: document.querySelectorAll('#printArea .label-card').length }));
  check('5_kichik_tasdiqsiz_chop', [g.c, g.p, g.labels], [0, 1, 1]);
  await ctx.close();

  // ════════════════════════════════════════════════════════════════════════
  console.log('\n── 4) Chegara: 1000 ta mahsulot ──');
  ({ page, ctx } = await ochish(browser, BIG));
  const t0 = Date.now();
  await clickAll(page);
  const dt = Date.now() - t0;
  s = await st(page);
  check('4_1000_belgilandi', s.count, '1000 ta mahsulot tanlandi · 1000 etiketka');
  check('4_belgilash_tez_(<3s)', dt < 3000, true);
  const prev = await page.evaluate(() => ({
    cards: document.querySelectorAll('#previewGrid .label-card').length,
    more: document.querySelector('#previewGrid .preview-more')?.textContent || '' }));
  check('4_preview_60_namuna', prev.cards, 60);
  check('4_preview_qolgani_yozilgan', /yana 940 ta mahsulot/.test(prev.more), true);

  await page.evaluate(() => { window.__confirmAnswer = false; });
  await page.click('#printBtn');
  await page.waitForTimeout(400);
  let r = await page.evaluate(() => ({ c: window.__confirms.slice(-1)[0] || '', p: window.__printed }));
  check('4_tasdiq_soraldi', /1000 ta mahsulot, jami 1000 ta etiketka/.test(r.c), true);
  check('4_bekor_qilinsa_chop_yoq', r.p, 0);

  await page.evaluate(() => { window.__confirmAnswer = true; });
  await page.click('#printBtn');
  await page.waitForTimeout(800);
  r = await page.evaluate(() => ({ p: window.__printed,
    labels: document.querySelectorAll('#printArea .label-card').length }));
  check('4_tasdiqlansa_hammasi_chop', [r.p, r.labels], [1, 1000]);

  await page.fill('#globalQty', '3');
  await page.click('text=Barchasiga');                             // 3000 etiketka
  const before = await page.evaluate(() => window.__confirms.length);
  await page.click('#printBtn');
  await page.waitForTimeout(400);
  r = await page.evaluate(() => ({ p: window.__printed, c: window.__confirms.length,
    toast: document.getElementById('toastBox').textContent }));
  check('4_A4_2000dan_kop_tosildi', [r.p, r.c - before], [1, 0]);
  check('4_A4_toast', /3000 ta etiketka .*ko'pi bilan 2000/.test(r.toast), true);

  // TSPL rejimida 2000 to'sig'i yo'q — faqat tasdiq (baytlar kichik: PRINT 1,qty)
  await page.evaluate(() => { window.setMode('tspl'); window.__confirmAnswer = false; });
  const b2 = await page.evaluate(() => window.__confirms.length);
  await page.click('#printBtn');
  await page.waitForTimeout(300);
  r = await page.evaluate(() => window.__confirms.length);
  check('4_TSPL_tosilmaydi_faqat_tasdiq', r - b2, 1);
  await ctx.close();
} finally {
  await browser.close();
  server.close();
}

console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
