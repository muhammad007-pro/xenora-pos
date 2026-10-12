/**
 * PACHKA TANLOV OYNASI — XAVFSIZ TARTIB va QOLDIQ OGOHLANTIRISHI (fix/pack-choice-ui).
 *
 * ═══ MUAMMO (jonli, FAZZA) ═══
 * "📦 Pachka" tugmasi birinchi va oltin rangda edi. Kassir shoshilib bosgan:
 * "3 talik" tish cho'tkasida 1 dona o'rniga ombordan 3 dona ayrilgan, qoldiq
 * (3 dona) tugagan. Kod to'g'ri ishlagan (base_qty = pack_size × soni) —
 * muammo ko'rinishda edi.
 *
 * ═══ QOTIRILADI ═══
 *   1) Tartib: birlik (Dona/Kg/Metr) BIRINCHI, pachka IKKINCHI; ikkalasi bir xil
 *      klass va o'lchamda; oltin (btn-gold) yo'q; autofocus yo'q
 *   2) Aniqlik: "1 pachka = 3 dona", "Ombordan 3 dona ayriladi", dona → "1 dona"
 *   3) Qoldiq < pack_size → oyna ichida ogohlantirish; savatdagi miqdor hisobga
 *      olinadi; qoldiq noma'lum → ogohlantirish YO'Q
 *   4) Ogohlantirish sotuvni TO'SMAYDI — pachka baribir savatga qo'shiladi
 *   5) GOLDEN: savat qatorining ombor miqdori (_lineBaseQty) o'zgarmagan
 *
 * Ishga tushirish:  node frontend/tests/test_pack_choice_ui.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const rd = p => readFileSync(resolve('frontend', p), 'utf8').replace(/\r\n/g, '\n');
const RCPT = rd('js/core/receipt-print.js');
const POS  = rd('js/modules/pos.js');
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

// ══════════════════════════════════════════════════════════════════════════
console.log('\n── 1) Tugmalar tartibi va ko\'rinishi (pos.html) ──');
const modalHtml = grab(HTML, /<div class="modal-wrap" id="packChoiceModal">[\s\S]*?<!-- #21\/#22/, 'packChoiceModal');
const iDona = modalHtml.indexOf('id="packChoiceDonaBtn"');
const iPack = modalHtml.indexOf('id="packChoicePackBtn"');
check('1_dona_birinchi', iDona >= 0 && iPack >= 0 && iDona < iPack, true);
const btnTag = id => grab(modalHtml, new RegExp(`<button[^>]*id="${id}"[^>]*>`), id);
const cls   = t => (t.match(/class="([^"]*)"/) || [])[1];
const style = t => (t.match(/style="([^"]*)"/) || [])[1];
check('1_bir_xil_klass',  cls(btnTag('packChoiceDonaBtn')), cls(btnTag('packChoicePackBtn')));
check('1_oddiy_rang',     cls(btnTag('packChoicePackBtn')), 'btn btn-outline');
check('1_bir_xil_olcham', style(btnTag('packChoiceDonaBtn')), style(btnTag('packChoicePackBtn')));
check('1_oltin_yoq',      /btn-gold/.test(modalHtml), false);
check('1_autofocus_yoq',  /autofocus/i.test(modalHtml), false);
check('1_ogohlantirish_joyi', /id="packChoiceWarn"[^>]*display:none/.test(modalHtml), true);

// ══════════════════════════════════════════════════════════════════════════
// Sandbox: HAQIQIY funksiyalar (pos.js + receipt-print.js), soxta DOM
const sb = { state: { cart: [] }, _stockMap: new Map(), _guardOn: false };
const nodes = {};
sb.document = { getElementById: id => (nodes[id] ||= { textContent: '', style: { display: 'none' } }) };
sb.toasts = [];
sb.toast = (msg, type) => sb.toasts.push([type, msg]);
sb.added = [];
sb.addToCart = (id, w, mode) => sb.added.push([id, w, mode]);
sb.closeModal = () => {};
sb._packChoiceProduct = null;
vm.createContext(sb);
vm.runInContext([
  grab(RCPT, /const _PACK_WEIGHT_UNITS = \[[^\]]*\];/,  '_PACK_WEIGHT_UNITS'),
  grab(RCPT, /const _PACK_VOL_UNITS\s*= \[[^\]]*\];/,   '_PACK_VOL_UNITS'),
  grab(RCPT, /const _PACK_LENGTH_UNITS = \[[^\]]*\];/,  '_PACK_LENGTH_UNITS'),
  grab(RCPT, /export function fmtPackQty\(n\)[\s\S]*?\n}\n/,      'fmtPackQty'),
  grab(RCPT, /export function packKind\(saleUnit\)[\s\S]*?\n}\n/, 'packKind'),
  grab(POS,  /function _stockNum\(n\) \{[\s\S]*?\n}/,             '_stockNum'),
  grab(POS,  /function _lineBaseQty\(line, product\) \{[\s\S]*?\n}/, '_lineBaseQty'),
  grab(POS,  /function _renderPackChoiceInfo\(product, k\) \{[\s\S]*?\n}/, '_renderPackChoiceInfo'),
  grab(POS,  /function _packStockShort\(product\) \{[\s\S]*?\n}/, '_packStockShort'),
].join('\n').replace(/^export /gm, ''), sb);

const packClick = grab(POS,
  /document\.getElementById\('packChoicePackBtn'\)\?\.addEventListener\('click', \(\) => \{[\s\S]*?\n\}\);/,
  'packChoicePackBtn handler');
vm.runInContext(packClick.replace(
  "document.getElementById('packChoicePackBtn')?.addEventListener('click', ",
  'globalThis.__packClick = (').replace(/\);$/, ');'), sb);

const T = id => nodes[id]?.textContent;
const shown = () => nodes.packChoiceWarn?.style.display !== 'none';
function render(product, stock, cart = []) {
  sb._stockMap = new Map(stock == null ? [] : [[product.id, { quantity: stock, unit: 'dona' }]]);
  sb.state.cart = cart;
  vm.runInContext(`_renderPackChoiceInfo(${JSON.stringify(product)}, packKind(${JSON.stringify(product.sale_unit)}))`, sb);
}
const TISH = { id: 715, name: 'BIOMED ZUB SHOTKA 3 TALIK', sale_unit: 'pcs', pack_size: 3, pack_price: 30000, price: 10000 };

// ══════════════════════════════════════════════════════════════════════════
console.log('\n── 2) Aniqlik qatorlari ──');
render(TISH, 10);
check('2_pachka_qoidasi', `${T('packChoicePackRule')} 3 dona`, '1 pachka = 3 dona');
check('2_ombordan',       T('packChoicePackDeduct'), 'Ombordan 3 dona ayriladi');
check('2_dona_tugmasi',   T('packChoiceDonaRule'), '1 dona');
const QOP = { id: 9, name: 'UN', sale_unit: 'kg', pack_size: 20, pack_price: 200000, price: 11000 };
render(QOP, 100);
check('2_qop_qoidasi', T('packChoicePackRule'), '1 qop =');
check('2_qop_ombordan', T('packChoicePackDeduct'), 'Ombordan 20 kg ayriladi');
check('2_kg_birlik',    T('packChoiceDonaRule'), "Miqdorni o'zingiz kiritasiz");

// ══════════════════════════════════════════════════════════════════════════
console.log('\n── 3) Qoldiq ogohlantirishi ──');
render(TISH, 2);
check('3_qoldiq_kam_korinadi', shown(), true);
check('3_matn', T('packChoiceWarn'), '⚠️ Omborda 2 dona, 1 pachka = 3 dona');
render(TISH, 3);
check('3_aynan_teng_ogohlantirish_yoq', shown(), false);
render(TISH, 10);
check('3_yetarli_ogohlantirish_yoq', shown(), false);
render(TISH, 5, [{ id: 715, qty: 1, _unitSold: 'pachka' }]);   // savatda 3 dona band
check('3_savat_hisobga_olinadi', T('packChoiceWarn'), '⚠️ Omborda 2 dona, 1 pachka = 3 dona');
render(TISH, null);
check('3_qoldiq_nomalum_jim', shown(), false);
render(QOP, 15);
check('3_qop_matni', T('packChoiceWarn'), '⚠️ Omborda 15 kg, 1 qop = 20 kg');

// ══════════════════════════════════════════════════════════════════════════
console.log('\n── 4) Ogohlantirish sotuvni TO\'SMAYDI ──');
sb._stockMap = new Map([[715, { quantity: 2, unit: 'dona' }]]);
sb.state.cart = []; sb.added = []; sb.toasts = []; sb._guardOn = false;
sb._packChoiceProduct = TISH;
vm.runInContext('__packClick()', sb);
check('4_savatga_qoshildi', sb.added, [[715, null, 'pachka']]);
check('4_ogohlantirish_toast', sb.toasts.length === 1 && sb.toasts[0][0] === 'warning', true);
sb.added = []; sb.toasts = []; sb._guardOn = true;
vm.runInContext('__packClick()', sb);
check('4_qoriqchi_yoqiq_ikki_marta_emas', [sb.added.length, sb.toasts.length], [1, 0]);
sb._stockMap = new Map([[715, { quantity: 30, unit: 'dona' }]]);
sb.added = []; sb.toasts = []; sb._guardOn = false;
vm.runInContext('__packClick()', sb);
check('4_yetarli_jim', [sb.added.length, sb.toasts.length], [1, 0]);

// ══════════════════════════════════════════════════════════════════════════
console.log('\n── 5) GOLDEN: ombor miqdori hisobi o\'zgarmagan ──');
const lb = (line, p) => vm.runInContext(`_lineBaseQty(${JSON.stringify(line)}, ${JSON.stringify(p)})`, sb);
check('5_pachka_2ta',  lb({ qty: 2, _unitSold: 'pachka' }, TISH), 6);
check('5_dona_2ta',    lb({ qty: 2, _unitSold: 'dona' }, TISH), 2);
check('5_oddiy_1ta',   lb({ qty: 1 }, TISH), 1);
check('5_kg_0.75',     lb({ qty: 1, _weight: 0.75 }, QOP), 0.75);

console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
