/**
 * ARALASH TO'LOVDA NASIYA — POS split + chek (feature/split-credit).
 *
 * Qotiriladi (HAQIQIY funksiyalar, soxta DOM bilan):
 *   1) buildSplitPayments: nasiya ulushi BIRINCHI; naqd qolganini yopadi;
 *      nasiyada mijoz yo'q → valid=false + needCustomer
 *   2) GOLDEN: nasiya 0 bo'lsa naqd+karta ro'yxati bit-bitiga avvalgidek;
 *      yashirin nasiya qatoridagi eski qiymat hisobga KIRMAYDI
 *   3) Chek (58/80mm — bitta builder): 2+ usul → "Naqd: 170 000" / "Nasiya: 130 000";
 *      bitta usul → avvalgidek "To'lov: Naqd"
 *   4) POS yagona nasiyada endi alohida POST /debts/ YO'Q, customer_id yuboriladi
 *
 * Ishga tushirish:  node frontend/tests/test_split_credit_ui.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const rd = p => readFileSync(resolve('frontend', p), 'utf8').replace(/\r\n/g, '\n');
const POS  = rd('js/modules/pos.js');
const RCPT = rd('js/core/receipt-print.js');
const HTML = rd('app/pos.html');

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

// ── 1-2) buildSplitPayments ─────────────────────────────────────────────────
const nodes = {};
const ctx = {
  state: { customer: null },
  computeTotals: () => ({ total: 300000 }),
  parseMoney: s => parseFloat(String(s ?? '').replace(/[^\d.]/g, '')) || 0,
  document: { getElementById: id => nodes[id] || null },
};
vm.createContext(ctx);
vm.runInContext([
  grab(POS, /const _SPLIT_METHODS = \[[^\]]*\];/, '_SPLIT_METHODS'),
  grab(POS, /function _splitInput\(m\) \{[^\n]*\}/, '_splitInput'),
  grab(POS, /function _splitVal\(m\) \{[\s\S]*?\n}/, '_splitVal'),
  grab(POS, /function buildSplitPayments\(\) \{[\s\S]*?\n}/, 'buildSplitPayments'),
].join('\n'), ctx);

function setSplit(vals, { creditRow = 'flex' } = {}) {
  for (const k of Object.keys(nodes)) delete nodes[k];
  for (const m of ['cash', 'card', 'click', 'payme', 'credit']) nodes['split_' + m] = { value: String(vals[m] ?? '') };
  nodes.splitRow_credit = { style: { display: creditRow } };
  nodes.splitRow_click  = { style: { display: '' } };
  nodes.splitRow_payme  = { style: { display: '' } };
  return vm.runInContext('buildSplitPayments()', ctx);
}
const brief = s => s.payments.map(p => [p.method, p.amount]);

console.log('\n── 1) Naqd + nasiya ──');
ctx.state.customer = { id: 7 };
let s = setSplit({ credit: '130 000', cash: '170 000' });
check('1_nasiya_birinchi', brief(s), [['credit', 130000], ['cash', 170000]]);
check('1_valid', s.valid, true);
s = setSplit({ credit: '130 000', cash: '200 000' });
check('1_naqd_qaytim', [s.payments[1].amount, s.payments[1].change], [170000, 30000]);
s = setSplit({ credit: '100 000', card: '50 000', cash: '150 000' });
check('1_uch_usul_tartib', brief(s), [['credit', 100000], ['card', 50000], ['cash', 150000]]);
s = setSplit({ credit: '300 000' });
check('1_toliq_nasiya_split', [brief(s), s.valid], [[['credit', 300000]], true]);
s = setSplit({ credit: '350 000' });
check('1_nasiya_ortiqcha_invalid', s.valid, false);

ctx.state.customer = null;
s = setSplit({ credit: '130 000', cash: '170 000' });
check('1_mijozsiz_invalid', [s.valid, s.needCustomer], [false, true]);

console.log('\n── 2) GOLDEN: naqd + karta ──');
s = setSplit({ card: '100 000', cash: '200 000' });
check('2_GOLDEN_naqd_karta', [brief(s), s.valid, s.needCustomer], [[['card', 100000], ['cash', 200000]], true, false]);
check('2_GOLDEN_maydonlar', Object.keys(s.payments[0]), ['method', 'amount', 'given_amount', 'change']);
s = setSplit({ credit: '130 000', card: '100 000', cash: '200 000' }, { creditRow: 'none' });
check('2_yashirin_nasiya_kirmaydi', [brief(s), s.valid], [[['card', 100000], ['cash', 200000]], true]);

// ── 3) Chek ─────────────────────────────────────────────────────────────────
console.log('\n── 3) Chek ──');
const rctx = {};
vm.createContext(rctx);
vm.runInContext([
  grab(RCPT, /const _PAY = \{[^\n]*\};/, '_PAY'),
  grab(RCPT, /function _money\(n\) \{[\s\S]*?\n}/, '_money'),
  grab(RCPT, /function _esc\(s\) \{[\s\S]*?\n}/, '_esc'),
  grab(RCPT, /export function payRowsHtml\(pays, payTxt\) \{[\s\S]*?\n}/, 'payRowsHtml'),
].join('\n').replace(/^export /gm, ''), rctx);
const rows = html => [...html.matchAll(/<span>([^<]*)<\/span><span>([^<]*)<\/span>/g)].map(m => [m[1], m[2]]);
rctx.P = [{ method: 'cash', amount: 170000 }, { method: 'credit', amount: 130000 }];
check('3_aralash_summalar', rows(vm.runInContext('payRowsHtml(P, "")', rctx)),
  [['Naqd:', '170 000'], ['Nasiya:', '130 000']]);
rctx.P1 = [{ method: 'cash', amount: 300000 }];
check('3_GOLDEN_bitta_usul', rows(vm.runInContext('payRowsHtml(P1, "Naqd")', rctx)), [["To'lov:", 'Naqd']]);
check('3_GOLDEN_bosh', rows(vm.runInContext('payRowsHtml([], "—")', rctx)), [["To'lov:", '—']]);
check('3_builder_ishlatadi', /\$\{payRowsHtml\(pays, payTxt\)\}/.test(RCPT), true);
check('3_jonli_chek_split_summa', /payment_methods \|\| \[\]\)\.length > 1\)[\s\S]{0,200}fmtNum\(p\.amount\)/.test(POS), true);

// ── 4) POS oqimi ────────────────────────────────────────────────────────────
console.log('\n── 4) POS oqimi ──');
const doPay = grab(POS, /async function doPayment\(\) \{[\s\S]*?\n}/, 'doPayment');
const doSplit = grab(POS, /async function doSplitPayment\(\) \{[\s\S]*?\n}/, 'doSplitPayment');
check('4_yagona_nasiya_debts_POST_yoq', /api\.post\('\/debts\/'/.test(doPay), false);
check('4_yagona_nasiya_customer_id', /customer_id : payMethod === 'credit'/.test(doPay), true);
check('4_split_nasiya_customer_id', /p\.method === 'credit' \? \{ customer_id/.test(doSplit), true);
check('4_split_mijoz_tekshiruvi', /if \(s\.needCustomer\)/.test(doSplit), true);
check('4_html_split_credit_qatori', /id="splitRow_credit" style="display:none/.test(HTML) && /id="split_credit"/.test(HTML), true);
check('4_qator_nasiya_tugmasi_bilan_ochiladi', /splitRow_credit'\);\s*\n\s*if \(splitCredit\) splitCredit\.style\.display = 'flex'/.test(POS), true);

console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
