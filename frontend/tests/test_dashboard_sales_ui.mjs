/**
 * DASHBOARD: "Bugungi savdo" kartasi qatorlari (feature/dashboard-sales-breakdown).
 *
 * Qotiriladi:
 *   1) Tartib: naqd, karta, nasiya, qaytarish (−), sof savdo, kassadan olingan
 *   2) "Boshqa" faqat ≠0 bo'lsa; qatorlar yig'indisi savdoga teng
 *   3) Eski server (sales_breakdown yo'q) — bo'sh, xato yo'q
 *   4) Belgilash: #kpiSalesRows savdo kartasida, loadDashboard chaqiradi
 *
 * Ishga tushirish:  node frontend/tests/test_dashboard_sales_ui.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const rd = p => readFileSync(resolve('frontend', p), 'utf8').replace(/\r\n/g, '\n');
const CORE = rd('js/admin/core.js');
const HTML = rd('app/admin.html');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};
function grab(src, re, what) {
  const m = src.match(re);
  if (!m) { console.error(`XATO: "${what}" topilmadi.`); process.exit(2); }
  return m[0];
}

const nodes = {};
const ctx = {
  fmtMoney: n => String(Math.round(n)),
  document: { getElementById: id => (nodes[id] ||= { innerHTML: '', textContent: '', style: {} }) },
};
vm.createContext(ctx);
vm.runInContext(grab(CORE, /function renderSalesBreakdown\(b\) \{[\s\S]*?\n}/, 'renderSalesBreakdown'), ctx);
const render = b => vm.runInContext(`renderSalesBreakdown(${JSON.stringify(b)})`, ctx);
const rows = () => [...nodes.kpiSalesRows.innerHTML.matchAll(/<span>([^<]+)<\/span><span>([^<]+)<\/span>/g)]
  .map(m => [m[1], m[2]]);

console.log('\n── 1) Tartib (egasining namunasi) ──');
render({ sales: 8265000, cash: 6085000, card: 2180000, credit: 0, other: 0, returns: 515000,
         returns_count: 1, net_sales: 7750000, cash_withdrawn: 300000, cash_withdrawn_count: 1 });
check('1_tartib', rows(), [['Naqd', '6085000'], ['Karta', '2180000'], ['Nasiya', '0'],
                          ['Qaytarish', '−515000'], ['Sof savdo', '7750000'], ['Kassadan olingan', '300000']]);
check('1_bir_chiziq', (nodes.kpiSalesRows.innerHTML.match(/border-top/g) || []).length, 1);
check('1_sof_qalin', /font-weight:700"[^>]*data-row="net-sales"/.test(nodes.kpiSalesRows.innerHTML), true);

console.log('\n── 2) Boshqa ──');
render({ sales: 25000, cash: 12000, card: 5000, credit: 3000, other: 5000, returns: 0,
         returns_count: 0, net_sales: 25000, cash_withdrawn: 0, cash_withdrawn_count: 0 });
const r2 = Object.fromEntries(rows());
check('2_boshqa_bor', r2['Boshqa'], '5000');
check('2_yigindi', +r2['Naqd'] + +r2['Karta'] + +r2['Nasiya'] + +r2['Boshqa'], 25000);
check('2_olingan_0_korinadi', r2['Kassadan olingan'], '0');
render({ sales: 1, cash: 1, card: 0, credit: 0, other: 0, returns: 0, net_sales: 1, cash_withdrawn: 0 });
check('2_boshqa_0_yoq', rows().some(r => r[0] === 'Boshqa'), false);

console.log('\n── 3) Eski server ──');
render(null);
check('3_bosh', nodes.kpiSalesRows.innerHTML, '');

console.log('\n── 4) Belgilash ──');
check('4_id_bor', HTML.includes('id="kpiSalesRows"'), true);
check('4_savdo_kartasida', HTML.indexOf('id="kpiSalesRows"') > HTML.indexOf('id="kpiRevenue"')
  && HTML.indexOf('id="kpiSalesRows"') < HTML.indexOf('id="kpiOrders"'), true);
check('4_chaqiriladi', /renderSalesBreakdown\(analytics\.sales_breakdown\)/.test(CORE), true);

console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
