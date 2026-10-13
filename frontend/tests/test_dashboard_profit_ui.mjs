/**
 * DASHBOARD: "Bugungi foyda" bloki (feature/dashboard-net-profit).
 *
 * Qotiriladi:
 *   1) Qatorlar tartibi: savdo, tan narx (−), yalpi, xarajat ulushi (−), keyin sof foyda
 *   2) Xarajat 0 bo'lsa ham qator KO'RINADI
 *   3) Taqsimlangan xarajat — "jami X dan" izohi; taqsimlanmagan — izohsiz
 *   4) Sof foyda manfiy bo'lsa qizil
 *   5) Belgilash: blok ID'lari joyida (view_finance bo'lmasa yashirin)
 *   6) Qaytarish qatori: bugungi savdo − qaytarish = sof savdo (0 bo'lsa ham), izoh
 *
 * Raqamlar serverdan tayyor keladi — bu yerda faqat ko'rsatish sinaladi.
 * Ishga tushirish:  node frontend/tests/test_dashboard_profit_ui.mjs
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
vm.runInContext(grab(CORE, /function renderProfitBreakdown\(pb\) \{[\s\S]*?\n}/, 'renderProfitBreakdown'), ctx);
const render = pb => vm.runInContext(`renderProfitBreakdown(${JSON.stringify(pb)})`, ctx);
const rows = () => [...nodes.kpiProfitRows.innerHTML.matchAll(/<span>([^<]+)<\/span><span>([^<]+)<\/span>/g)]
  .map(m => [m[1], m[2]]);

console.log('\n── 1) Qatorlar (eski server — sales_gross yo\'q) ──');
render({ revenue: 10000, cost: 6000, gross_profit: 4000, expenses: 1500, net_profit: 2500,
         expense_info: { is_split: false, raw: 1500 } });
// revenue serverda qaytarishdan KEYIN → "Sof savdo" (chap kartadagi "Bugungi savdo" bilan adashmasin)
check('1_tartib', rows(), [['Sof savdo', '10000'], ['Tan narx', '−6000'],
                          ['Yalpi foyda', '4000'], ['Xarajat ulushi', '−1500']]);
check('1_ikki_chiziq', (nodes.kpiProfitRows.innerHTML.match(/border-top/g) || []).length, 2);
check('1_sof_foyda', nodes.kpiNetProfit.textContent, '2500');
check('1_yorliq', nodes.kpiNetProfitLabel.textContent, 'sof foyda');
check('1_izohsiz', /taqsimlangan/.test(nodes.kpiProfitRows.innerHTML), false);

console.log('\n── 2) Xarajat 0 ──');
render({ revenue: 10000, cost: 6000, gross_profit: 4000, expenses: 0, net_profit: 4000, expense_info: {} });
check('2_qator_bor_0_deb', rows().find(r => r[0] === 'Xarajat ulushi'), ['Xarajat ulushi', '0']);
check('2_sof_teng_yalpi', nodes.kpiNetProfit.textContent, '4000');

console.log('\n── 3) Taqsimlangan izoh ──');
render({ revenue: 0, cost: 0, gross_profit: 0, expenses: 96774, net_profit: -96774,
         expense_info: { is_split: true, raw: 3000000 } });
check('3_izoh', /kunlarga taqsimlangan \(jami 3000000 dan\)/.test(nodes.kpiProfitRows.innerHTML), true);

console.log('\n── 4) Manfiy — qizil ──');
check('4_qizil', nodes.kpiNetProfit.style.color, 'var(--red)');
render({ revenue: 1, cost: 0, gross_profit: 1, expenses: 0, net_profit: 1, expense_info: {} });
check('4_musbat_oddiy', nodes.kpiNetProfit.style.color, '');

console.log('\n── 5) Belgilash ──');
for (const id of ['kpiNetProfitCard', 'kpiProfitRows', 'kpiNetProfit', 'kpiNetProfitLabel', 'kpiProfitTrend']) {
  check(`5_${id}`, HTML.includes(`id="${id}"`), true);
}
check('5_default_yashirin', /id="kpiNetProfitCard" style="display:none"/.test(HTML), true);
check('5_eski_server_zaxira', /trends\.net_profit != null/.test(CORE), true);

console.log('\n── 6) Qaytarish qatori (feature/dashboard-returns-row) ──');
render({ sales_gross: 4605000, returns: 515000, returns_count: 2, revenue: 4090000,
         cost: 2500000, gross_profit: 1590000, expenses: 100000, net_profit: 1490000, expense_info: {} });
check('6_tartib', rows(), [['Bugungi savdo', '4605000'], ['Qaytarish', '−515000'], ['Sof savdo', '4090000'],
                          ['Tan narx', '−2500000'], ['Yalpi foyda', '1590000'], ['Xarajat ulushi', '−100000']]);
check('6_uch_chiziq', (nodes.kpiProfitRows.innerHTML.match(/border-top/g) || []).length, 3);
check('6_izoh', /kecha sotilgan tovar ham bo'lishi mumkin/.test(nodes.kpiProfitRows.innerHTML), true);
check('6_nomlar_ikki_xil', rows().filter(r => r[0] === 'Bugungi savdo').length, 1);
const r6 = Object.fromEntries(rows());
check('6_zanjir', [4605000 - 515000 === +r6['Sof savdo'], +r6['Sof savdo'] - 2500000 === +r6['Yalpi foyda']], [true, true]);
check('6_sof_foyda', nodes.kpiNetProfit.textContent, '1490000');
render({ sales_gross: 10000, returns: 0, returns_count: 0, revenue: 10000, cost: 6000,
         gross_profit: 4000, expenses: 0, net_profit: 4000, expense_info: {} });
check('6_qaytarish_0_korinadi', rows().find(r => r[0] === 'Qaytarish'), ['Qaytarish', '0']);

console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
