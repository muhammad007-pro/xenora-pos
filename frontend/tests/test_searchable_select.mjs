/**
 * BOSQICH A testi: mahsulot select'larida NOM BO'YICHA qidiruv.
 *
 * MUAMMO (mijozda, Fazza Parfum): Vozvrat va Priyomka oynalarida mahsulot
 * oddiy `<select>` dan tanlanardi — 794 faol mahsulot ichidan yozib qidirish
 * YO'Q edi. Ustiga-ustak ro'yxat `page_size=500` bilan yuklanardi, ya'ni
 * 294 mahsulot dropdownga UMUMAN tushmasdi.
 *
 * GOLDEN QOIDA: `sel.value` va `opt.dataset.price` o'qiydigan joylar
 * TEGILMASIN — komponent faqat select USTIGA qidiruv qatlami qo'shadi.
 * Shu sabab test ayni shu ikkisini ham tekshiradi.
 *
 * Ishga tushirish:  node frontend/tests/test_searchable_select.mjs
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
const PAGE = `http://127.0.0.1:${server.address().port}/app/suppliers.html`;

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

// 1200 mahsulot: birinchi 1000 boshlang'ich ro'yxatga tushadi,
// 1001-1200 FAQAT server qidiruvi bilan topiladi (aynan mijozdagi holat).
const ALL = Array.from({ length: 1200 }, (_, i) => ({
  id: i + 1, name: `Mahsulot ${i + 1}`, price: (i + 1) * 100, cost_price: (i + 1) * 60,
}));
ALL[1150].name = 'KERASYS shampun';     // id 1151 — ro'yxatdan TASHQARIDA
ALL[1150].price = 45000;

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
const page = await ctx.newPage();
await ctx.addInitScript(() => localStorage.setItem('access_token', 'test.token.x'));

let searchCalls = 0;
await page.route('**/api/v1/**', async (route) => {
  const u = new URL(route.request().url());
  const path = u.pathname.replace('/api/v1', '');
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) });

  if (path === '/products/') {
    const q = (u.searchParams.get('search') || '').toLowerCase();
    const size = Number(u.searchParams.get('page_size') || 20);
    if (q) searchCalls++;
    const rows = (q ? ALL.filter(p => p.name.toLowerCase().includes(q)) : ALL).slice(0, size);
    return json({ items: rows, total: rows.length, page: 1, page_size: size, total_pages: 1 });
  }
  if (path === '/suppliers-b2b/') return json({ items: [{ id: 1, name: 'TEST', is_active: true, payment_delay_days: 0 }], total: 1, page: 1, page_size: 200, total_pages: 1 });
  if (path === '/categories/all') return json([]);
  return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
});

await page.goto(PAGE, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => typeof window.debtSaveRet === 'function');
await page.waitForTimeout(500);

// ── T1: boshlang'ich ro'yxat 1000 ta (500 kesilishi tuzatilgan) ─────────────
check('T1_boshlangich_1000', await page.$$eval('#retProduct option', o => o.length), 1000);

// ── T2: Vozvrat — qidiruv inputi bor va 1000 dan TASHQARIDAGI mahsulotni topadi ──
const retSearch = '#retProduct';
check('T2_qidiruv_inputi_bor', await page.$$eval('input[data-ss-input]', els => els.length > 0), true);

// Vozvrat modalini ochamiz — aks holda input KO'RINMAYDI (Playwright fill qilmaydi)
await page.evaluate(() => window.debtOpenRet(1));
await page.waitForTimeout(200);
await page.fill('#returnModal input[data-ss-input]', 'KERASYS');
await page.waitForTimeout(700);   // debounce 300ms + so'rov
const retOpts = await page.$$eval(`${retSearch} option`, o => o.map(x => x.textContent));
check('T2_server_qidiruvi_topdi', retOpts, ['KERASYS shampun']);
check('T2_server_soroviga_bordi', searchCalls > 0, true);

// ── T3: GOLDEN — sel.value va dataset.price O'QILISHI ishlayveradi ──────────
// Bitta natija qolganda komponent uni tanlaydi va `change` yuboradi ->
// mavjud onchange `retPrice` ni dataset.price dan to'ldirishi kerak.
check('T3_value_ozgardi',   await page.inputValue(retSearch), '1151');
check('T3_dataset_price',   await page.$eval(`${retSearch}`, s => s.options[s.selectedIndex].dataset.price), '45000');
check('T3_onchange_ishladi', await page.inputValue('#retPrice'), '45000');

// ── T4: Priyomka — DINAMIK qator ham qidiruvli bo'lsin ──────────────────────
await page.evaluate(() => window.debtCloseRet());   // modal yopilmasa tab bosilmaydi
await page.waitForTimeout(200);
await page.click('#st-priyomka');
await page.waitForTimeout(300);
await page.click('#btnNewReceipt');
await page.waitForTimeout(200);
const before = await page.$$eval('#itemsBody tr', r => r.length);
await page.click('button:has-text("+ Tovar")');
await page.waitForTimeout(200);
const after = await page.$$eval('#itemsBody tr', r => r.length);
check('T4_qator_qoshildi', after > before, true);
check('T4_har_qatorda_qidiruv',
      await page.$$eval('#itemsBody tr', rows => rows.every(r => !!r.querySelector('input[data-ss-input]'))), true);

// Qator ichida qidiruv ishlaydi va tanlov `recCalcRow` ni chaqiradi (narx ustuni)
const rowSearch = '#itemsBody tr:last-child input[data-ss-input]';
await page.fill(rowSearch, 'KERASYS');
await page.waitForTimeout(700);
check('T4_qatorda_topildi',
      await page.$$eval('#itemsBody tr:last-child select option', o => o.map(x => x.textContent)),
      ['KERASYS shampun']);
check('T4_qatorda_value', await page.inputValue('#itemsBody tr:last-child select'), '1151');

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
