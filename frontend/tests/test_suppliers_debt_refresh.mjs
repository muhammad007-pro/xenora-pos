/**
 * REGRESSIYA QO'RIQCHISI: Firmalar sahifasi — qarz raqamlari eskirmasin.
 *
 * MUAMMO (FAZZA, 13.11): "KKKK" firmasi "Boshlang'ich qarz" 50 000 bilan
 * qo'shildi — Qarzlar tabida KO'RINMADI. Oynani yopib qayta kirsa ko'rinardi,
 * admin "Yangilash" tugmasi esa HECH NARSA qilmasdi. Sabablar:
 *   1. suppliers.html tablari `loaded[...]` bilan BIR MARTA yuklanardi;
 *   2. saveFirm / arxiv / priyomka tasdig'i `loadDebt()` ni chaqirmasdi;
 *   3. core.js `loadPageData('suppliers')` da tarmoq yo'q edi (iframe tegilmasdi).
 * Backend/SW/nginx kesh SABAB EMAS edi (prodda tekshirilgan).
 *
 * Ishga tushirish:  node frontend/tests/test_suppliers_debt_refresh.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { readFileSync } from 'fs';
import { resolve, extname, join } from 'path';
import vm from 'node:vm';

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

// Server holati: AKMALAKA bor; POST kelgach KKKK (opening_debt bilan) qo'shiladi.
const state = {
  suppliers: [{ id: 21, name: 'AKMALAKA', is_active: true, payment_delay_days: 0, opening_debt: 0 }],
  calls: [],
};
const debtRow = s => ({ supplier_id: s.id, supplier_name: s.name, phone: null,
  total_purchases: s.opening_debt || 0, total_paid: 0, total_returned: 0,
  debt: s.opening_debt || 0, advance: 0, balance: s.opening_debt || 0,
  opening_debt: s.opening_debt || 0, overdue_amount: 0, last_purchase: null });

await page.route('**/api/v1/**', async (route) => {
  const req = route.request();
  const path = new URL(req.url()).pathname.replace('/api/v1', '');
  state.calls.push(`${req.method()} ${path}`);
  const json = (b, s = 200) => route.fulfill({ status: s, contentType: 'application/json', body: JSON.stringify(b) });

  if (req.method() === 'POST' && path === '/suppliers-b2b/') {
    const body = JSON.parse(req.postData() || '{}');
    const row = { id: 22, name: body.name, is_active: true, payment_delay_days: 0,
                  opening_debt: body.opening_debt || 0 };
    state.suppliers.push(row);
    return json(row);
  }
  if (path === '/suppliers-b2b/debt-summary') return json(state.suppliers.filter(s => s.is_active).map(debtRow));
  if (path === '/suppliers-b2b/')     return json({ items: state.suppliers, total: state.suppliers.length, page: 1, page_size: 200, total_pages: 1 });
  if (path === '/products/')          return json({ items: [], total: 0, page: 1, page_size: 1000, total_pages: 1 });
  if (path === '/categories/all')     return json([]);
  return json({ items: [], total: 0, page: 1, page_size: 100, total_pages: 1 });
});

const nCalls = (s) => state.calls.filter(c => c === s).length;
const DS = 'GET /suppliers-b2b/debt-summary';
const settle = () => page.waitForTimeout(400);

await page.goto(PAGE, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => typeof window.saveFirm === 'function');
await settle();
// Sahifa QAYTA YUKLANMASLIGINI kuzatish uchun belgi (location.reload bo'lsa yo'qoladi)
await page.evaluate(() => { window.__belgi = 'tirik'; });

// ── 1) Qarzlar tabi HAR ochilganda serverdan ────────────────────────────────
console.log('\n── 1) Tablar orasida o\'tish ──');
await page.evaluate(() => window.supTab('qarzlar')); await settle();
check('1_birinchi_ochilish', nCalls(DS), 1);
await page.evaluate(() => window.supTab('firmalar')); await settle();
await page.evaluate(() => window.supTab('qarzlar')); await settle();
check('1_qayta_ochilganda_yana_soraldi', nCalls(DS), 2);

// ── 2) Firma "Boshlang'ich qarz" bilan saqlangach — Qarzlar yangilanadi ─────
console.log('\n── 2) Boshlang\'ich qarz bilan firma ──');
await page.evaluate(() => window.supTab('firmalar')); await settle();
const oldin = nCalls(DS);
await page.click('#btnAddFirm');
await page.fill('#fName', 'KKKK');
await page.fill('#fOpeningDebt', '50000');
await page.click('#btnSaveFirm');
await page.waitForTimeout(700);
check('2_saqlangach_debt_summary_soraldi', nCalls(DS) - oldin, 1);
// Tabga O'TMASDAN ham Qarzlar kartalari allaqachon yangi (yashirin panelda chizilgan)
check('2_qarzlar_kartasida_KKKK', await page.$eval('#debtGrid', el => el.textContent.includes('KKKK')), true);
check('2_jami_qarz_50000', await page.$eval('#dtDebt', el => el.textContent.replace(/\D/g, '')), '50000');

// ── 3) supRefresh — ochiq tab qayta yuklanadi, sahifa/tab joyida ────────────
console.log('\n── 3) "Yangilash" → supRefresh ──');
check('3_supRefresh_bor', await page.evaluate(() => typeof window.supRefresh), 'function');
await page.evaluate(() => window.supTab('qarzlar')); await settle();
const ds0 = nCalls(DS), sup0 = nCalls('GET /suppliers-b2b/');
await page.evaluate(() => window.supRefresh()); await settle();
check('3_qarzlar_qayta_soraldi', nCalls(DS) - ds0, 1);
check('3_dropdown_firmalari_ham', nCalls('GET /suppliers-b2b/') - sup0, 1);
check('3_tab_joyida_qoldi', await page.$eval('#st-qarzlar', el => el.classList.contains('active')), true);
check('3_sahifa_qayta_yuklanmadi', await page.evaluate(() => window.__belgi), 'tirik');
// Boshqa tablar "yuklanmagan" deb belgilanadi → Priyomka ochilsa serverdan oladi
const rc0 = nCalls('GET /purchase-receipts/');
await page.evaluate(() => window.supTab('priyomka')); await settle();
check('3_boshqa_tab_ochilganda_yangi', nCalls('GET /purchase-receipts/') - rc0 >= 1, true);

await browser.close();
server.close();

// ── 4) core.js — admin "Yangilash" iframe ichidagi supRefresh ni chaqiradi ──
console.log('\n── 4) core.js loadPageData(\'suppliers\') ──');
const CORE = readFileSync(resolve(ROOT, 'js/admin/core.js'), 'utf8').replace(/\r\n/g, '\n');
const m = CORE.match(/function loadPageData\(page\) \{[\s\S]*?\n}/);
if (!m) { console.error('XATO: loadPageData topilmadi — test eskirgan.'); process.exit(2); }
const sb = { chaqirildi: 0, frame: null };
sb.document = { getElementById: id => (id === 'suppliersFrame' ? sb.frame : null) };
vm.createContext(sb);
vm.runInContext(m[0] + '\nglobalThis.loadPageData = loadPageData;', sb);
sb.frame = { contentWindow: { supRefresh: () => { sb.chaqirildi++; } } };
sb.loadPageData('suppliers');
check('4_supRefresh_chaqirildi', sb.chaqirildi, 1);
// Iframe hali yuklanmagan (birinchi kirish) — xato bermaydi
sb.frame = { contentWindow: {} };
let xato = null; try { sb.loadPageData('suppliers'); } catch (e) { xato = e.message; }
check('4_iframe_tayyor_emas_jim', xato, null);
sb.frame = null;
xato = null; try { sb.loadPageData('suppliers'); } catch (e) { xato = e.message; }
check('4_iframe_yoq_jim', xato, null);

console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
