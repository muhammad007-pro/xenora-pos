/**
 * SOTUVLAR TARIXI — sana oralig'i va kunlar bo'yicha guruhlash (feature/sales-history-filter).
 *
 * Qotiriladi:
 *   1) Tayyor davrlar (Bugun/Kecha/7 kun/30 kun) — oy chegarasidan o'tishda ham to'g'ri
 *   2) Kunlarga guruhlash KELGAN TARTIBDA; sarlavha va kunlik jami serverdagi `days`
 *      dan (sahifadan mustaqil)
 *   3) POS: kun sarlavhalari, "Ko'proq yuklash", qayta chop etish tugmasi saqlangan
 *   4) Admin: sana tanlanmasa — AVVALGI `/orders/` yo'li (GOLDEN); tanlansa —
 *      `/orders/history`, kun sarlavhasi qatorlari va davr jami
 *
 * Ishga tushirish:  node frontend/tests/test_sales_history_ui.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const rd = p => readFileSync(resolve('frontend', p), 'utf8').replace(/\r\n/g, '\n');
const HELP = rd('js/core/sales-history.js');
const POS  = rd('js/modules/pos.js');
const CORE = rd('js/admin/core.js');
const PHTML = rd('app/pos.html');
const AHTML = rd('app/admin.html');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};
function grab(src, re, what) {
  const m = src.match(re);
  if (!m) { console.error(`XATO: "${what}" topilmadi — test eskirgan yoki kod o'zgargan.`); process.exit(2); }
  return m[0];
}

// ── yordamchi (classic skript → window.XenoraSalesHistory) ─────────────────
const hctx = { window: {} };
vm.createContext(hctx);
vm.runInContext(HELP, hctx);
const SH = hctx.window.XenoraSalesHistory;

console.log('\n── 1) Tayyor davrlar ──');
check('1_bugun',   { ...SH.presetRange('today', '2026-10-12') },     { from: '2026-10-12', to: '2026-10-12' });
check('1_kecha',   { ...SH.presetRange('yesterday', '2026-10-01') }, { from: '2026-09-30', to: '2026-09-30' });
check('1_7kun',    { ...SH.presetRange('week', '2026-10-03') },      { from: '2026-09-27', to: '2026-10-03' });
check('1_30kun',   { ...SH.presetRange('month', '2026-03-01') },     { from: '2026-01-31', to: '2026-03-01' });
check('1_yil_chegarasi', SH.addDays('2026-01-01', -1), '2025-12-31');
check('1_localToday', SH.localToday(new Date(2026, 9, 8, 23, 59)), '2026-10-08');
check('1_dayLabel',  SH.dayLabel('2026-10-10'), '10.10.2026, shanba');
check('1_rangeLabel', SH.rangeLabel('2026-10-08', '2026-10-12'), '08.10.2026 — 12.10.2026');
check('1_rangeLabel_bir_kun', SH.rangeLabel('2026-10-12', '2026-10-12'), '12.10.2026');

console.log('\n── 2) Guruhlash ──');
const items = [
  { id: 5, business_date: '2026-10-12' }, { id: 4, business_date: '2026-10-12' },
  { id: 3, business_date: '2026-10-11' }, { id: 1, business_date: '2026-10-08' },
];
check('2_guruhlar', SH.groupByDay(items).map(g => [g.date, g.items.map(i => i.id)]),
  [['2026-10-12', [5, 4]], ['2026-10-11', [3]], ['2026-10-08', [1]]]);

// ── 3) POS ko'rinishi ───────────────────────────────────────────────────────
console.log('\n── 3) POS ──');
check('3_skript_posdan_oldin', PHTML.indexOf('js/core/sales-history.js') < PHTML.indexOf('js/modules/pos.js'), true);
check('3_tayyor_tugmalar', ['today', 'yesterday', 'week', 'month'].every(k => PHTML.includes(`data-sh-preset="${k}"`)), true);
const pctx = {
  window: { XenoraSalesHistory: SH },
  _sh: { items: [], days: {} },
  _shPay: { cash: 'Naqd', credit: 'Nasiya' },
  _shEsc: s => String(s ?? ''),
  fmtNum: n => String(n),
  document: { getElementById: id => (pctx.__nodes[id] ||= { innerHTML: '' }) },
  __nodes: {},
};
vm.createContext(pctx);
vm.runInContext([
  grab(POS, /function _shRowHtml\(o, mgr\) \{[\s\S]*?\n}/, '_shRowHtml'),
  grab(POS, /function _shRender\(d, mgr\) \{[\s\S]*?\n}/, '_shRender'),
].join('\n'), pctx);
pctx._sh.items = [
  { id: 5, business_date: '2026-10-12', final_amount: 100, status: 'completed', payment_method: 'cash', daily_number: 7 },
  { id: 4, business_date: '2026-10-12', final_amount: 999, status: 'cancelled', payment_method: 'cash', daily_number: 6 },
  { id: 3, business_date: '2026-10-11', final_amount: 40,  status: 'completed', payment_method: 'credit', daily_number: 2 },
];
// Kun jami SERVERDAN — sahifada yo'q cheklar ham ichida (masalan 10.11 da 3 ta chek)
pctx._sh.days = { '2026-10-12': { count: 1, total: 100 }, '2026-10-11': { count: 3, total: 540 } };
vm.runInContext('_shRender({ has_more: true, total: 9 }, true)', pctx);
const html = pctx.__nodes.salesHistoryList.innerHTML;
const heads = [...html.matchAll(/class="sh-day"><span>📅 ([^<]+)<\/span><span>([^<]+)<\/span>/g)].map(m => [m[1], m[2]]);
check('3_kun_sarlavhalari', heads, [['12.10.2026, dushanba', '1 ta · 100'], ['11.10.2026, yakshanba', '3 ta · 540']]);
check('3_reprint_tugmasi_saqlangan', (html.match(/data-sh-print="\d+"/g) || []).length, 3);
check('3_tafsilot_saqlangan', (html.match(/data-sh-detail="\d+"/g) || []).length, 3);
check('3_bekor_belgisi', /bekor/.test(html), true);
check('3_kop_yuklash', /data-sh-more="1"[^>]*>Ko'proq yuklash \(yana 6 ta\)/.test(html), true);
vm.runInContext('_sh.items = []; _shRender({ has_more: false, total: 0 }, true)', pctx);
check('3_bosh_davr', /Bu davrda sotuv yo/.test(pctx.__nodes.salesHistoryList.innerHTML), true);

// ── 4) Admin ────────────────────────────────────────────────────────────────
console.log('\n── 4) Admin ──');
check('4_tayyor_tugmalar', ['today', 'yesterday', 'week', 'month'].every(k => AHTML.includes(`data-sh-preset="${k}"`)), true);
check('4_skript_ulangan', AHTML.includes('<script src="../js/core/sales-history.js"></script>'), true);
const nodes = {};
const actx = {
  window: { XenoraSalesHistory: SH },
  URLSearchParams,
  salesPage: 1,
  _statusSales: { completed: ['Yakunlangan', 'badge-green'] },
  _payLabel: { cash: 'Naqd' },
  fmtDate: s => s, fmtMoney: n => String(n), escH: s => String(s ?? ''),
  toast: () => {},
  _initSalesFilters: async () => {},
  calls: [],
  document: { getElementById: id => (nodes[id] ||= { value: '', innerHTML: '', textContent: '', style: {} }) },
};
actx.apiFetch = async (url) => {
  actx.calls.push(url);
  if (url.startsWith('/orders/history')) {
    return { date_from: '2026-10-08', date_to: '2026-10-12', today: '2026-10-12',
             summary: { count: 4, total: 150, orders: 5 },
             days: [{ date: '2026-10-12', count: 1, total: 100 }, { date: '2026-10-08', count: 3, total: 50 }],
             items: [{ id: 2, business_date: '2026-10-12', final_amount: 100, status: 'completed', daily_number: 1 },
                     { id: 1, business_date: '2026-10-08', final_amount: 20, status: 'completed', daily_number: 1 }],
             total: 5, page: 1, page_size: 50, has_more: false };
  }
  return { items: [{ id: 9, final_amount: 1, status: 'completed' }], total: 1, total_pages: 1 };
};
vm.createContext(actx);
vm.runInContext([
  grab(CORE, /function _salesRowHtml\(o\) \{[\s\S]*?\n}/, '_salesRowHtml'),
  grab(CORE, /let _shAdminToday = null;.*\n/, '_shAdminToday'),
  grab(CORE, /const _SH_ADMIN_PAGE = \d+;\n/, '_SH_ADMIN_PAGE'),
  grab(CORE, /async function _loadSalesGrouped\(from, to, cid, rid\) \{[\s\S]*?\n}/, '_loadSalesGrouped'),
  grab(CORE, /async function loadSalesHistory\(\) \{[\s\S]*?\n}/, 'loadSalesHistory'),
].join('\n'), actx);

await vm.runInContext('loadSalesHistory()', actx);
check('4_GOLDEN_sanasiz_eski_yol', actx.calls.at(-1), '/orders/?page=1&page_size=20');
check('4_GOLDEN_eski_qator', /onclick="openSaleDetail\(9\)"/.test(nodes.salesBody.innerHTML), true);
check('4_GOLDEN_summary_yashirin', nodes.shAdminSummary.style.display, 'none');

nodes.shFrom.value = '2026-10-08'; nodes.shTo.value = '2026-10-12';
await vm.runInContext('loadSalesHistory()', actx);
check('4_sana_bilan_history', actx.calls.at(-1), '/orders/history?page=1&page_size=50&date_from=2026-10-08&date_to=2026-10-12');
const ab = nodes.salesBody.innerHTML;
check('4_kun_qatorlari', (ab.match(/class="sh-day-row"/g) || []).length, 2);
check('4_kun_jami_serverdan', /08\.10\.2026, payshanba <span style="float:right">3 ta · <span class="td-gold">50</.test(ab), true);
check('4_reprint_saqlangan', (ab.match(/data-reprint="\d+"/g) || []).length, 2);
check('4_davr_jami', /08\.10\.2026 — 12\.10\.2026<\/b> · 4 ta chek · <b class="td-gold">150<\/b>/.test(nodes.shAdminSummary.innerHTML), true);
check('4_bekor_eslatma', /\+1 bekor\/kutilgan/.test(nodes.shAdminSummary.innerHTML), true);

console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
