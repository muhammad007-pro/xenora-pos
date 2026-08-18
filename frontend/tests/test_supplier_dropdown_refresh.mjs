/**
 * REGRESSIYA QO'RIQCHISI: suppliers.html — firma dropdownlari eskirmasin.
 *
 * MUAMMO (mijozda, Fazza Parfum): KERASYS firmasi qo'shildi, jadvalda va Qarzlar
 * kartalarida KO'RINDI, lekin "+ To'lov" / "Vozvrat" / "Priyomka" dropdownlarida
 * YO'Q edi. Sabab: `suppliers` massivi FAQAT `masterInit()` da (sahifa yuklanganda)
 * to'ldirilardi; `loadFirms()` jadvalni yangi so'rovdan chizardi, massivga esa
 * tegmasdi. Admin panelida "Firmalar" iframe bir marta yuklanadi va qayta
 * yuklanmaydi -> firma sessiya oxirigacha dropdownlarda paydo bo'lmasdi (F5 shart).
 *
 * Ishga tushirish:  node frontend/tests/test_supplier_dropdown_refresh.mjs
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

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
const page = await ctx.newPage();
await ctx.addInitScript(() => localStorage.setItem('access_token', 'test.token.x'));

// Server holati: boshida faqat TEST; POST kelgach KERASYS qo'shiladi.
const state = { suppliers: [{ id: 1, name: 'TEST', is_active: true, payment_delay_days: 0 }] };

await page.route('**/api/v1/**', async (route) => {
  const req = route.request();
  const path = new URL(req.url()).pathname.replace('/api/v1', '');
  const json = (b, s = 200) => route.fulfill({ status: s, contentType: 'application/json', body: JSON.stringify(b) });

  if (req.method() === 'POST' && path === '/suppliers-b2b/') {
    const body = JSON.parse(req.postData() || '{}');
    const row = { id: 2, name: body.name, is_active: true, payment_delay_days: 0,
                  tenant_id: 26, created_at: '2026-08-18T15:02:30Z' };
    state.suppliers.push(row);
    return json(row);
  }
  if (path === '/suppliers-b2b/')     return json({ items: state.suppliers, total: state.suppliers.length, page: 1, page_size: 200, total_pages: 1 });
  if (path === '/products/')          return json({ items: [{ id: 1, name: 'Ayva', price: 5500 }], total: 1, page: 1, page_size: 500, total_pages: 1 });
  if (path === '/categories/all')     return json([]);
  if (path === '/suppliers-b2b/debt-summary') return json([]);
  return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
});

const opts = (sel) => page.$$eval(`${sel} option`, els => els.map(o => o.textContent.trim()).filter(Boolean));

await page.goto(PAGE, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => typeof window.saveFirm === 'function');
await page.waitForTimeout(400);

check('T0_boshida_faqat_TEST', await opts('#paySupplier'), ['TEST']);

// ── Yangi firma qo'shamiz (KERASYS) ─────────────────────────────────────────
await page.click('#btnAddFirm');
await page.fill('#fName', 'KERASYS');
await page.click('#btnSaveFirm');
await page.waitForTimeout(600);

// SAHIFA QAYTA YUKLANMAYDI — aynan mijozdagi holat (iframe bir marta yuklanadi)
check('T1_tolov_dropdownida_KERASYS', await opts('#paySupplier'), ['TEST', 'KERASYS']);
check('T2_vozvrat_dropdownida',       await opts('#retSupplier'), ['TEST', 'KERASYS']);
check('T3_priyomka_dropdownida',      await opts('#nSupplier'),   ['TEST', 'KERASYS']);

// ── Qidiruv filtri dropdownni QISQARTIRMASIN ────────────────────────────────
await page.fill('#firmSearch', 'KER');
await page.waitForTimeout(700);   // firmDelayLoad debounce (350ms)
check('T4_qidiruv_dropdownni_buzmadi', await opts('#paySupplier'), ['TEST', 'KERASYS']);

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
