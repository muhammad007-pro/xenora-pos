/**
 * POS savatda NARX KELISHUVI — pos.js dagi HAQIQIY kod ustida sinov.
 *
 * Funksiyalar pos.js FAYLIDAN ajratib olinadi (nusxa ko'chirilmaydi) — shunda
 * kod o'zgarsa test ham u bilan birga o'zgaradi, ya'ni test eskirmaydi.
 *
 * ENG MUHIM TEKSHIRUV (S-guruh): CLIENT ekranda ko'rsatgan jami SERVER hisoblagan
 * jamiga TENG bo'lishi. Server mantig'i (order_service.create_order) shu faylda
 * qayta yozilgan — ikkalasi ajralib ketsa test yiqiladi. Narx/chegirma nozik
 * hudud: bu yerdagi nomuvofiqlik jimgina pul xatosi bo'ladi.
 *
 * Ishga tushirish:  node frontend/tests/test_pos_price_edit.js
 */
'use strict';
const fs   = require('fs');
const path = require('path');
const vm   = require('vm');

// CRLF -> LF: Windows'da fayl CRLF bilan saqlanadi, regexdagi \n mos kelmay qolmasin.
const SRC = fs.readFileSync(
  path.join(__dirname, '..', 'js', 'modules', 'pos.js'), 'utf8').replace(/\r\n/g, '\n');

// ─── pos.js dan kerakli bo'laklarni AJRATIB OLISH ────────────────────────────
function grab(re, what) {
  const m = SRC.match(re);
  if (!m) { console.error(`XATO: pos.js dan "${what}" topilmadi — test eskirgan.`); process.exit(2); }
  return m[0];
}

const src = [
  grab(/const PRICE_MAX = \d+;/,                                   'PRICE_MAX'),
  grab(/function effPrice\(item\)[\s\S]*?\n}\n/,                   'effPrice'),
  grab(/function priceEditDiscount\(cart\)[\s\S]*?\n}\n/,          'priceEditDiscount'),
  grab(/function _activeDiscountsNow\(\)[\s\S]*?\n}\n/,            '_activeDiscountsNow'),
  grab(/function _discAmount\(d, base\)[\s\S]*?\n}\n/,             '_discAmount'),
  grab(/function computeAutoDiscounts\(\)[\s\S]*?\n}\n/,           'computeAutoDiscounts'),
  grab(/function computeTotals\(\)[\s\S]*?\n}\n/,                  'computeTotals'),
].join('\n');

// pos.js payload'idagi chegirma kanali mantig'i — AYNAN fayldan olinadi.
const payloadSrc = grab(
  /discount_type   : t\.editDisc > 0[\s\S]*?discount_amount : t\.disc \+ t\.editDisc,/,
  'payload chegirma kanali');

const sandbox = {
  state: null,
  MODE: { taxRate: 0, serviceRate: 0 },
  _activeDiscounts: [],
  fmtNum: n => String(Math.round(Number(n) || 0)),
  console,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
// Payload chegirma bo'lagini chaqiriladigan funksiyaga o'raymiz.
vm.runInContext(
  `function buildDiscountFields(t) { return { ${payloadSrc} }; }`, sandbox);

const { effPrice, priceEditDiscount, computeTotals, buildDiscountFields } = sandbox;

// ─── SERVER mantig'i (order_service.create_order) — mustaqil qayta yozilgan ───
// Client bilan bir manbadan EMAS: ikkalasi ajralib ketsa test buni ko'rsatsin.
function serverTotals(cart, payload, taxRate = 0, svcRate = 0) {
  let subtotal = 0;
  for (const i of cart) {
    // unit_price = product.price (katalog). Override FAQAT kattaroq bo'lsa.
    const catalog = i.catalogUnit;
    const ov = payload.items.find(x => x.ref === i.ref).unit_price_override;
    const unit = (ov != null && ov > catalog) ? ov : catalog;
    subtotal += unit * i.serverQty;
  }
  const dv = payload.discount_value || 0;
  let manual = 0;
  if (dv > 0) {
    manual = payload.discount_type === 'pct'
      ? subtotal * Math.min(dv, 100) / 100
      : Math.min(dv, subtotal);
  }
  const auto = payload.autoDisc || 0;
  const totalDisc = Math.min(Math.round((manual + auto) * 100) / 100, subtotal);
  const after = subtotal - totalDisc;
  return { subtotal, totalDisc, final: after + after * taxRate + after * svcRate };
}

function clientPayload(t, cart) {
  const d = buildDiscountFields(t);
  d.items = cart.map(i => ({
    ref: i.ref,
    unit_price_override: (i._priceNew != null && i._priceNew > i.price)
      ? (i._weight != null && i._weight > 0 ? i._priceNew / i._weight : i._priceNew)
      : null,
  }));
  return d;
}

// ─── Sinov ramkasi ────────────────────────────────────────────────────────────
let pass = 0; const fails = [];
function check(name, got, want, tol = 0.01) {
  const ok = (typeof want === 'number')
    ? Math.abs(Number(got) - want) <= tol
    : JSON.stringify(got) === JSON.stringify(want);
  if (ok) { pass++; console.log(`[OK  ] ${name}`); }
  else    { fails.push(name); console.log(`[FAIL] ${name}: ${JSON.stringify(got)} != ${JSON.stringify(want)}`); }
}

function setCart(cart, discount = { type: 'pct', value: 0 }, active = []) {
  sandbox.state = { cart, discount, discountSource: null, products: [] };
  sandbox._activeDiscounts = active;
  return computeTotals();
}

const item = (o) => Object.assign(
  { ref: o.ref || 'r', id: 1, name: 'X', price: 0, qty: 1, _priceNew: null,
    catalogUnit: o.price, serverQty: o.qty || 1 }, o);

// ══ E: effPrice / priceEditDiscount ══════════════════════════════════════════
check('E1_tegilmagan_katalog',  effPrice({ price: 145000, _priceNew: null }), 145000);
check('E2_tushirilgan_katalog', effPrice({ price: 145000, _priceNew: 140000 }), 145000);
check('E3_oshirilgan_yangi',    effPrice({ price: 145000, _priceNew: 160000 }), 160000);
check('E4_kelishuv_summa',      priceEditDiscount([
  item({ price: 145000, _priceNew: 140000 }),
  item({ price: 12000,  _priceNew: 10000  }),
  item({ price: 400000, _priceNew: 390000 }),
]), 5000 + 2000 + 10000);
check('E5_oshirish_chegirma_emas', priceEditDiscount([
  item({ price: 145000, _priceNew: 160000 }),
]), 0);
check('E6_miqdorga_kopaytiriladi', priceEditDiscount([
  item({ price: 145000, _priceNew: 140000, qty: 3 }),
]), 15000);

// ══ R: REGRESSIYA — kelishuvsiz savat AYNAN avvalgidek ═══════════════════════
{
  const cart = [item({ ref: 'a', price: 145000, qty: 2 }), item({ ref: 'b', price: 12000 })];
  const t = setCart(cart);
  check('R1_sub',       t.sub, 302000);
  check('R2_editDisc',  t.editDisc, 0);
  check('R3_total',     t.total, 302000);
  const d = buildDiscountFields(t);
  check('R4_payload_type_null',  d.discount_type, null);
  check('R5_payload_value_null', d.discount_value, null);
  check('R6_payload_amount_0',   d.discount_amount, 0);
}
{ // foiz chegirma + kelishuv YO'Q -> foiz bo'lib ketadi (avvalgidek)
  const t = setCart([item({ price: 100000 })], { type: 'pct', value: 10 });
  const d = buildDiscountFields(t);
  check('R7_foiz_saqlanadi', [d.discount_type, d.discount_value], ['pct', 10]);
}

// ══ M: Marg'ilon stsenariysi — uch mahsulot kelishildi ═══════════════════════
{
  const cart = [
    item({ ref: 'a', price: 145000, _priceNew: 140000 }),
    item({ ref: 'b', price: 12000,  _priceNew: 10000  }),
    item({ ref: 'c', price: 400000, _priceNew: 390000 }),
  ];
  const t = setCart(cart);
  check('M1_sub_katalog',  t.sub, 557000);          // katalog narxida qoladi
  check('M2_kelishuv',     t.editDisc, 17000);
  check('M3_jami_chegirma', t.totalDisc, 17000);
  check('M4_total',        t.total, 540000);        // 140k + 10k + 390k
  const p = clientPayload(t, cart);
  check('M5_kanal_fixed',  p.discount_type, 'fixed');
  check('M6_qiymat',       p.discount_value, 17000);
  check('M7_override_yoq', p.items.every(i => i.unit_price_override === null), true);
  const s = serverTotals(cart, p);
  check('M8_SERVER_MOS',   s.final, t.total);       // ⚠️ ekran == kassa
}

// ══ U: Narx OSHIRISH — chegirma EMAS ════════════════════════════════════════
{
  const cart = [item({ ref: 'a', price: 100000, _priceNew: 130000 })];
  const t = setCart(cart);
  check('U1_sub_oshdi',    t.sub, 130000);
  check('U2_chegirma_0',   t.editDisc, 0);
  check('U3_total',        t.total, 130000);
  const p = clientPayload(t, cart);
  check('U4_kanal_tegmadi', p.discount_type, null);
  check('U5_override',      p.items[0].unit_price_override, 130000);
  const s = serverTotals(cart, p);
  check('U6_SERVER_MOS',    s.final, t.total);
  check('U7_server_chegirma_0', s.totalDisc, 0);
}
{ // og'irlik qatori: _priceNew = QATOR JAMI, serverga BIRLIK narx ketadi
  const cart = [item({ ref: 'w', price: 300000, qty: 1, _weight: 30, _unit: 'ml',
                       _priceNew: 360000, catalogUnit: 10000, serverQty: 30 })];
  const t = setCart(cart);
  check('U8_ogirlik_sub', t.sub, 360000);
  const p = clientPayload(t, cart);
  check('U9_ogirlik_birlik_narx', p.items[0].unit_price_override, 12000);   // 360000/30
  check('U10_ogirlik_SERVER_MOS', serverTotals(cart, p).final, t.total);
}

// ══ X: ARALASH — tushirish + oshirish + qo'lda foiz chegirma ════════════════
{
  const cart = [
    item({ ref: 'a', price: 145000, _priceNew: 140000 }),   // -5 000
    item({ ref: 'b', price: 100000, _priceNew: 130000 }),   // +30 000 (chegirma emas)
  ];
  const t = setCart(cart, { type: 'pct', value: 10 });
  check('X1_sub', t.sub, 145000 + 130000);                  // 275 000
  check('X2_edit', t.editDisc, 5000);
  check('X3_foiz', t.disc, 27500);                          // 10% x 275 000
  check('X4_jami_chegirma', t.totalDisc, 32500);
  check('X5_total', t.total, 242500);
  const p = clientPayload(t, cart);
  check('X6_fixed_yigindi', [p.discount_type, p.discount_value], ['fixed', 32500]);
  check('X7_SERVER_MOS', serverTotals(cart, p).final, t.total);
}

// ══ A: AKSIYA bilan birga — pricing-resolver buzilmasin ═════════════════════
{
  // 10% mahsulot aksiyasi + narx kelishuvi bir qatorda
  const active = [{ id: 7, is_active: true, type: 'percentage', value: 10, product_id: 1 }];
  const cart = [item({ ref: 'a', id: 1, price: 100000, _priceNew: 90000 })];
  const t = setCart(cart, { type: 'pct', value: 0 }, active);
  check('A1_aksiya_KATALOGDAN', t.autoDisc, 10000);   // 10% x 100 000 — server ham shunday
  check('A2_kelishuv',          t.editDisc, 10000);
  check('A3_ikkalasi',          t.totalDisc, 20000);
  check('A4_total',             t.total, 80000);
  const p = clientPayload(t, cart);
  p.autoDisc = t.autoDisc;   // server aksiyani o'zi qayta hisoblaydi
  check('A5_SERVER_MOS', serverTotals(cart, p).final, t.total);
}
{
  // Aksiya + narx OSHIRILGAN: aksiya OSHIRILGAN narxdan hisoblanadi (server ham)
  const active = [{ id: 7, is_active: true, type: 'percentage', value: 10, product_id: 1 }];
  const cart = [item({ ref: 'a', id: 1, price: 100000, _priceNew: 200000 })];
  const t = setCart(cart, { type: 'pct', value: 0 }, active);
  check('A6_aksiya_OSHGAN_NARXDAN', t.autoDisc, 20000);   // 10% x 200 000
  const p = clientPayload(t, cart);
  p.autoDisc = t.autoDisc;
  check('A7_SERVER_MOS', serverTotals(cart, p).final, t.total);
}

// ══ C: CHEGARA holatlari ════════════════════════════════════════════════════
{ // 0 ga tushirish — chegirma subtotaldan oshmaydi
  const cart = [item({ ref: 'a', price: 50000, _priceNew: 0 })];
  const t = setCart(cart);
  check('C1_bepul_total',     t.total, 0);
  check('C2_chegirma_cheklandi', t.totalDisc, 50000);
  const p = clientPayload(t, cart);
  check('C3_SERVER_MOS', serverTotals(cart, p).final, 0);
}
{ // foiz + kelishuv birgalikda subtotaldan oshsa — qisiladi, manfiy chiqmaydi
  const cart = [item({ ref: 'a', price: 100000, _priceNew: 20000 })];
  const t = setCart(cart, { type: 'pct', value: 90 });
  check('C4_manfiy_emas', t.total >= 0, true);
  const p = clientPayload(t, cart);
  check('C5_qiymat_sub_bilan_cheklangan', p.discount_value <= t.sub, true);
  check('C6_SERVER_MOS', serverTotals(cart, p).final, t.total);
}
{ // soliq/xizmat bor rejim (restoran) — kelishuv soliqdan OLDIN ayiriladi
  sandbox.MODE = { taxRate: 0.12, serviceRate: 0.10 };
  const cart = [item({ ref: 'a', price: 100000, _priceNew: 90000 })];
  const t = setCart(cart);
  check('C7_soliq_kelishuvdan_keyin', t.tax, 90000 * 0.12);
  const p = clientPayload(t, cart);
  check('C8_SERVER_MOS', serverTotals(cart, p, 0.12, 0.10).final, t.total);
  sandbox.MODE = { taxRate: 0, serviceRate: 0 };
}

console.log();
const total = pass + fails.length;
if (fails.length) { console.log(`${pass}/${total} PASS — XATO: ${fails.join(', ')}`); process.exit(1); }
console.log(`${total}/${total} PASS`);
