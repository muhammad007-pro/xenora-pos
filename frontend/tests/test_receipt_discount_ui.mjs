/**
 * CHEK CHEGIRMASI — jonli POS cheki (fix/receipt-discount).
 *
 * NICE SHOPPING (28) shikoyati: kassada "Kelishuv −3 000" ko'rinadi, chop
 * etilgan chekda esa chegirma yo'q edi (kelishuvli chekda "Chegirmasiz" =
 * qatorlar yig'indisi, chegirma qatori chiqmasdi). Aksiya chegirmasi esa
 * kelishuvsiz chekda umuman chiqmasdi (_discAll da autoDisc yo'q edi).
 *
 * Qotiriladi (HAQIQIY pos.js funksiyalari + haqiqiy receipt-print.js, vm):
 *   1) #6972: 6 × 18 000 → 17 500 — qator 105 000, Chegirmasiz 108 000,
 *      Chegirma (kelishuv) −3 000, UMUMIY 105 000
 *   2) kelishuv + qo'lda 10% — kelishuv va qolgan chegirma alohida qatorda
 *   3) aksiya (autoDisc) kelishuvsiz chekda "Chegirma" qatorida
 *   4) GOLDEN: kelishuvsiz/chegirmasiz va qo'lda-foizli chek o'zgarmagan
 *   5) arifmetika: Chegirmasiz − chegirmalar = UMUMIY
 *
 * Ishga tushirish:  node frontend/tests/test_receipt_discount_ui.mjs
 * Eski kodda:       node frontend/tests/test_receipt_discount_ui.mjs --ref main
 *                   (pos.js va receipt-print.js `main` dagidan — 1-3 YIQILADI)
 */
import { readFileSync, writeFileSync, unlinkSync } from 'fs';
import { resolve } from 'path';
import { execSync } from 'child_process';
import { pathToFileURL } from 'url';
import vm from 'node:vm';

const REF = process.argv.includes('--ref') ? process.argv[process.argv.indexOf('--ref') + 1] : null;
const show = p => execSync(`git show ${REF}:${p}`, { encoding: 'utf8', maxBuffer: 1 << 24 });

const POS = (REF ? show('frontend/js/modules/pos.js') : readFileSync(resolve('frontend/js/modules/pos.js'), 'utf8'))
  .replace(/\r\n/g, '\n');
let RP_FILE = resolve('frontend/js/core/receipt-print.js'), TMP = null;
if (REF) {   // o'sha papkaga — nisbiy importlar (code128.js) ishlasin
  TMP = RP_FILE = resolve('frontend/js/core/_receipt_print_ref_tmp.js');
  writeFileSync(TMP, show('frontend/js/core/receipt-print.js'));
}

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
const fn = name => grab(new RegExp(`\\nfunction ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`), name);

try {
  const R = await import(pathToFileURL(RP_FILE).href);
  const body = { innerHTML: '' };
  const ctx = {
    ...R,
    state: { cart: [], discount: { value: 0, type: 'pct' }, discountSource: null, products: [], table: null },
    MODE: { taxRate: 0, serviceRate: 0 },
    _activeDiscounts: [],
    payMethod: 'cash',
    _shPay: { cash: 'Naqd' },
    fmtNum: n => Math.round(Number(n) || 0).toLocaleString('en-US'),
    fmtDuration: () => '',
    document: { getElementById: id => (id === 'receiptBody' ? body : null) },
    Date, Math, Number, JSON, Set, Array, Object, String, isFinite,
  };
  vm.createContext(ctx);
  for (const n of ['effPrice', 'priceEditDiscount', '_activeDiscountsNow', '_discAmount',
                   'computeAutoDiscounts', 'computeTotals', '_rcptPackLabel', '_rcptDiscountLabel',
                   'renderReceiptData']) {
    vm.runInContext(fn(n).replace(/^\n/, ''), ctx);
  }

  const render = (cart, { discount = { value: 0, type: 'pct' }, source = null, auto = [] } = {}) => {
    ctx.state.cart = cart;
    ctx.state.discount = discount;
    ctx.state.discountSource = source;
    ctx._activeDiscounts = auto;
    vm.runInContext('renderReceiptData({ cafe_name: "MEBEL FURNITURA", order_id: 1 })', ctx);
    const h = body.innerHTML;
    const rows = [...h.matchAll(/<tr><td>([^<]*)[\s\S]*?<\/td><td>([^<]*)<\/td>\s*<td style="text-align:right">([^<]*)<\/td><\/tr>/g)]
      .map(m => [m[2], m[3]]);
    const totals = [...h.matchAll(/<div class="rt-row[^"]*"><span>([^<]*)<\/span><span>([^<]*)<\/span><\/div>/g)]
      .map(m => [m[1], m[2]]).filter(([l]) => l !== "To'lov:");
    return { rows, totals };
  };
  const it = (id, price, qty, n = null) => ({ id, name: `M${id}`, price, qty, _priceNew: n });

  // ── 1) #6972 ────────────────────────────────────────────────────────────
  console.log('\n── 1) #6972 kelishuv ──');
  let r = render([it(1, 18000, 6, 17500)]);
  check('1_qator_kelishilgan_summada', r.rows, [['6 x 18,000', '105,000']]);
  check('1_jami_qatorlari', r.totals, [['Chegirmasiz:', '108,000'], ['Chegirma (kelishuv):', '-3,000'], ['UMUMIY:', '105,000 UZS']]);

  // #7014 — bir nechta qator, ikkitasida kelishuv (prod: 1 510 000 / 24 000)
  r = render([it(1, 132500, 1), it(2, 142500, 1), it(3, 500000, 1), it(4, 5000, 6, 3000),
              it(5, 180000, 2), it(6, 45000, 5), it(7, 2000, 60, 1800)]);
  check('1_7014', r.totals, [['Chegirmasiz:', '1,510,000'], ['Chegirma (kelishuv):', '-24,000'], ['UMUMIY:', '1,486,000 UZS']]);

  // ── 2) kelishuv + qo'lda 10% ────────────────────────────────────────────
  console.log("\n── 2) kelishuv + qo'lda ──");
  // 245 000 → 220 000 va 100 000; 10% × 345 000 = 34 500; jami 59 500
  r = render([it(1, 245000, 1, 220000), it(2, 100000, 1)], { discount: { value: 10, type: 'pct' }, source: 'manual' });
  check('2_qatorlar', r.rows, [['1 x 245,000', '220,000'], ['1 x 100,000', '100,000']]);
  check('2_jami_qatorlari', r.totals, [['Chegirmasiz:', '345,000'], ['Chegirma (kelishuv):', '-25,000'],
                                       ["Chegirma -10% (qo'lda):", '-34,500'], ['UMUMIY:', '285,500 UZS']]);

  // ── 3) aksiya (autoDisc), kelishuvsiz ────────────────────────────────────
  console.log('\n── 3) aksiya ──');
  const AKS = [{ id: 9, product_id: 1, type: 'percentage', value: 10, is_active: true }];
  r = render([it(1, 50000, 2), it(2, 30000, 1)], { auto: AKS });
  check('3_aksiya_chekda', r.totals, [['Chegirmasiz:', '130,000'], ['Chegirma:', '-10,000'], ['UMUMIY:', '120,000 UZS']]);
  // aksiya + qo'lda 5%: yorliq foizsiz (summa foizga mos emas)
  r = render([it(1, 50000, 2), it(2, 30000, 1)], { auto: AKS, discount: { value: 5, type: 'pct' }, source: 'manual' });
  check('3_aksiya_va_qolda', r.totals, [['Chegirmasiz:', '130,000'], ['Chegirma:', '-16,500'], ['UMUMIY:', '113,500 UZS']]);

  // ── 4) GOLDEN ───────────────────────────────────────────────────────────
  console.log('\n── 4) GOLDEN ──');
  r = render([it(1, 5000, 2), it(2, 7000, 1)]);
  check('4_chegirmasiz', r.totals, [['Jami:', '17,000'], ['UMUMIY:', '17,000 UZS']]);
  r = render([it(1, 5000, 2), it(2, 7000, 1)], { discount: { value: 10, type: 'pct' }, source: 'customer' });
  check('4_qolda_foiz', r.totals, [['Chegirmasiz:', '17,000'], ['Chegirma -10% (mijoz):', '-1,700'], ['UMUMIY:', '15,300 UZS']]);
  r = render([it(1, 245000, 1, 260000)]);   // narx OSHIRILGAN — chegirma emas
  check('4_oshirilgan', [r.rows, r.totals], [[['1 x 260,000', '260,000']], [['Jami:', '260,000'], ['UMUMIY:', '260,000 UZS']]]);

  // ── 5) arifmetika ───────────────────────────────────────────────────────
  console.log('\n── 5) arifmetika ──');
  const num = s => Number(String(s).replace(/[^\d.-]/g, ''));
  for (const [nom, cart, opt] of [
    ['6972', [it(1, 18000, 6, 17500)], {}],
    ['kasr', [it(1, 40000, 3, 33333.4)], {}],
    ['qolda', [it(1, 245000, 1, 220000), it(2, 100000, 1)], { discount: { value: 10, type: 'pct' }, source: 'manual' }],
  ]) {
    const t = render(cart, opt).totals;
    const sub = num(t[0][1]), um = num(t[t.length - 1][1]);
    const disc = t.slice(1, -1).reduce((a, [, v]) => a + num(v), 0);
    check(`5_${nom}_Chegirmasiz-chegirma=UMUMIY`, Math.abs(sub + disc - um) <= 1, true);
  }
} finally {
  if (TMP) try { unlinkSync(TMP); } catch { /* yo'q */ }
}
console.log(`\n${pass}/${pass + fail} PASS${REF ? `  (ref: ${REF})` : ''}`);
process.exit(fail ? 1 : 0);
