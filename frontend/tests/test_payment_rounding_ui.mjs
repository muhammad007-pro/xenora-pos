/**
 * KG SOTUVDAGI TIYIN NUQSONI — POS tomoni (fix/payment-rounding).
 *
 * Qotiriladi (HAQIQIY funksiyalar, soxta DOM bilan):
 *   1) og'irlik qatori = round(narx × og'irlik, 2): 0.566 × 26500 → 14999 (dumsiz)
 *   2) summa rejimi: 15 000 terilsa qator 15 000, og'irlik 0.566; payload'da
 *      `line_total: 15000`; oddiy qatorlarda bu kalit UMUMAN yo'q (GOLDEN)
 *   3) split jami 2 xona (kasrli chek butun songa tushib qolmaydi)
 *   4) "kutilayotgan": to'langan chekda belgi + o'chirishda ogohlantirish
 *
 * Ishga tushirish:  node frontend/tests/test_payment_rounding_ui.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const POS = readFileSync(resolve('frontend', 'js/modules/pos.js'), 'utf8').replace(/\r\n/g, '\n');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};
function grab(re, what) {
  const m = POS.match(re);
  if (!m) { console.error(`XATO: "${what}" topilmadi — test eskirgan yoki kod o'zgargan.`); process.exit(2); }
  return m[0];
}

const ctx = {
  state: { cart: [], staffMember: null, cleaningInfo: null, customer: null, discount: { value: 0 } },
  MODE: { isService: false, isDryCleaning: false, taxRate: 0, serviceRate: 0 },
  isFractionalUnit: u => ['kg', 'g', 'l', 'm', 'sm'].includes(String(u).toLowerCase()),
  isPackProduct: () => false,
  packSizeLabel: () => '',
  _warnIfShort: () => {},
  _membershipDates: null, _cartScrollToEnd: false,
  beep: () => {}, renderCart: () => {},
  fmt: n => Math.round(Number(n) || 0).toLocaleString('en-US') + ' UZS',
  parseMoney: s => parseFloat(String(s ?? '').replace(/[^\d.]/g, '')) || 0,
  document: { getElementById: () => null },
};
vm.createContext(ctx);
vm.runInContext([
  grab(/function roundMoney\(n\) \{[\s\S]*?\n}/, 'roundMoney'),
  grab(/function effPrice\(item\) \{[\s\S]*?\n}/, 'effPrice'),
  grab(/function priceEditDiscount\(cart\) \{[\s\S]*?\n}/, 'priceEditDiscount'),
  'function computeAutoDiscounts(){ return { perItem: [], labels: [], cartDisc: 0, total: 0, ids: [] }; }',
  grab(/function computeTotals\(\) \{[\s\S]*?\n}/, 'computeTotals'),
  grab(/function doAddToCart\(product, modifiers, weight = null, unitMode = null, lineTotal = null\) \{[\s\S]*?\n}\n/, 'doAddToCart'),
  grab(/function _weightFromSum\(sum\) \{[\s\S]*?\n}/, '_weightFromSum'),
  'let _weightProduct = null;',
  grab(/function _heldDeleteMessage\(order\) \{[\s\S]*?\n}/, '_heldDeleteMessage'),
].join('\n'), ctx);

const KG = { id: 1, name: 'QORA SHRUP 4', price: 26500, sale_unit: 'kg' };

console.log('\n── 1) Og\'irlik qatori ──');
check('1_float_dumi', 0.566 * 26500, 14998.999999999998);
vm.runInContext('state.cart = []', ctx);
ctx.doAddToCart(KG, [], 0.566);
check('1_qator_14999', ctx.state.cart[0].price, 14999);
check('1_jami_dumsiz', ctx.computeTotals().total, 14999);
check('1_lineTotal_yoq', ctx.state.cart[0]._lineTotal, null);
ctx.doAddToCart(KG, [], 0.74);
check('1_GOLDEN_0.74', ctx.state.cart[1].price, 19610);

console.log('\n── 2) Summa rejimi ──');
vm.runInContext('_weightProduct = ' + JSON.stringify(KG), ctx);
const w = vm.runInContext('_weightFromSum(15000)', ctx);
check('2_ogirlik_3_xona', w, 0.566);
vm.runInContext('state.cart = []', ctx);
ctx.doAddToCart(KG, [], w, null, 15000);
check('2_qator_15000', [ctx.state.cart[0].price, ctx.state.cart[0]._weight, ctx.state.cart[0]._lineTotal], [15000, 0.566, 15000]);
check('2_jami_15000', ctx.computeTotals().total, 15000);

// payload: HAQIQIY buildOrderPayload ichidagi qator xaritasi
const itemMap = grab(/items          : state\.cart\.map\(i => \(\{[\s\S]*?\n    \}\)\),/, 'payload items');
check('2_payload_line_total_shartli', /\.\.\.\(i\._lineTotal != null && i\._priceNew == null \? \{ line_total: i\._lineTotal \} : \{\}\)/.test(itemMap), true);
const mapper = vm.runInContext(
  `(i) => (${itemMap.match(/state\.cart\.map\(i => \((\{[\s\S]*?\n    \})\)\),/)[1]})`,
  Object.assign(ctx, { MODE: { ...ctx.MODE, hasCourses: false } }));
const p1 = mapper({ id: 1, _weight: 0.566, _unitPrice: 26500, price: 15000, _lineTotal: 15000, _priceNew: null });
const p2 = mapper({ id: 2, price: 5000, qty: 2 });
const p3 = mapper({ id: 1, _weight: 0.566, _unitPrice: 26500, price: 14999, _lineTotal: null });
check('2_summa_qatorida_line_total', p1.line_total, 15000);
check('2_GOLDEN_dona_qatorida_kalit_yoq', 'line_total' in p2, false);
check('2_GOLDEN_ogirlik_rejimida_kalit_yoq', 'line_total' in p3, false);
const p4 = mapper({ id: 1, _weight: 0.566, _unitPrice: 26500, price: 15000, _lineTotal: 15000, _priceNew: 16000 });
check('2_narx_kelishuvida_line_total_yoq', 'line_total' in p4, false);

console.log('\n── 3) To\'lov va split ──');
check('3_doPayment_roundMoney', /const due   = roundMoney\(payableTotal\(\)\);/.test(POS), true);
check('3_split_total_roundMoney', /const total     = roundMoney\(computeTotals\(\)\.total\);/.test(POS), true);
check('3_split_Math_round_yoq', /const total     = Math\.round\(computeTotals\(\)\.total\);/.test(POS), false);
check('3_roundMoney_chegara', [ctx.roundMoney(14998.999999999998), ctx.roundMoney(14999.4), ctx.roundMoney(10000)], [14999, 14999.4, 10000]);

console.log('\n── 4) Kutilayotgan ──');
const msgPaid = ctx._heldDeleteMessage({ id: 9, paid_amount: 14999 });
check('4_ogohlantirish_summa', /Bu chekda 14,999 UZS to'lov bor/.test(msgPaid), true);
check('4_ogohlantirish_qayta_tolov_olmang', /qayta to'lov olmang/.test(msgPaid), true);
check('4_GOLDEN_tolovsiz_oddiy_savol', ctx._heldDeleteMessage({ id: 9, paid_amount: 0 }), "Bu kutilayotgan buyurtma o'chirilsinmi?");
check('4_GOLDEN_eski_server_maydonsiz', ctx._heldDeleteMessage({ id: 9 }), "Bu kutilayotgan buyurtma o'chirilsinmi?");
const held = grab(/function openHeldModal\(\) \{[\s\S]*?\n}/, 'openHeldModal');
check('4_royxatda_tolangan_belgisi', /held-paid[\s\S]*to'langan/.test(held), true);
check('4_ochirish_yangi_xabar', /confirm\(_heldDeleteMessage\(/.test(held), true);

// ── 5) Vozvrat oldindan ko'rish (returns.html) — server qoidasi bilan bir xil ──
console.log('\n── 5) Vozvrat oldindan ko\'rish ──');
const RET = readFileSync(resolve('frontend', 'app/returns.html'), 'utf8').replace(/\r\n/g, '\n');
const rowAmountSrc = (RET.match(/function _rowAmount\(oiEl, q, pr\) \{[\s\S]*?\n}/) || [])[0];
if (!rowAmountSrc) { console.error('XATO: _rowAmount topilmadi'); process.exit(2); }
const rctx = {};
vm.createContext(rctx);
vm.runInContext(rowAmountSrc, rctx);
const el = (soldQty, soldTotal) => ({ dataset: { soldQty: String(soldQty), soldTotal: String(soldTotal) } });
check('5_summa_rejimi_toliq', rctx._rowAmount(el(0.566, 15000), 0.566, 26500), 15000);
check('5_qisman_proporsional', rctx._rowAmount(el(0.566, 15000), 0.3, 26500), 7950.53);
check('5_GOLDEN_butun_son', rctx._rowAmount(el(3, 15000), 1, 5000), 5000);
check('5_GOLDEN_boglanmagan', rctx._rowAmount(null, 2, 5000), 10000);
check('5_GOLDEN_eski_server_sold_total_yoq', rctx._rowAmount({ dataset: { soldQty: '3', soldTotal: '' } }, 1, 5000), 5000);
check('5_calcTotal_rowAmount', /total \+= _rowAmount\(document\.getElementById\(`ioi\$\{id\}`\), q, pr\);/.test(RET), true);

console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
