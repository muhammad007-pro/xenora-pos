/**
 * PACHKA TANLOV OYNASI — birlik yorliqlari (metr "Dona bo'yicha" xatosi).
 *
 * ═══ MUAMMO (v1.13.0, jonli) ═══
 * Metr mahsulotida (kabel o'rami) tanlov oynasi:
 *   · birlik tugmasi " Dona bo'yicha" (metr EMAS);
 *   · pachka tomoni "📦 Pachka" / "100 dona" (100 METR emas).
 * Sabab: `packKind('m')` metrni DONA deb bilardi (`perUnit:false`), modal esa
 * `isFractionalUnit('m') === true` shoxiga kirib `unitWord` ("Dona") dan
 * "… bo'yicha" yasardi. Yorliq POS'da inline yasalgani uchun test qilinmagan.
 *
 * ═══ TUZATISH ═══
 *   · `packKind` ga uzunlik: m/sm → "🧵 O'ram", birlik so'zi "m"/"sm"
 *   · `unitChoiceLabel(saleUnit)` — tugma yorlig'i YAGONA joyda (receipt-print.js)
 *   · backend `pack_word` ham "o'ram" (ESC/POS cheki) — test_pack_label.py
 *
 * ⚠️ GOLDEN:
 *   · kg: "⚖️ Kg bo'yicha" / "Qop (20 kg)" — bit-bitiga avvalgidek
 *   · dona/pcs: "Dona" / "Pachka (10 dona)" — avvalgidek
 *   · ml: "ml" / "Butun (150 ml)" — avvalgidek
 *   · qaytarishda summa rejimi metr uchun YO'Q bo'lib qoladi
 *
 * Ishga tushirish:  node frontend/tests/test_meter_label.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const rd = p => readFileSync(resolve('frontend', p), 'utf8').replace(/\r\n/g, '\n');
const RCPT = rd('js/core/receipt-print.js');
const POS  = rd('js/modules/pos.js');
const RET  = rd('app/returns.html');

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

// ── Sandbox: HAQIQIY funksiyalar ──────────────────────────────────────────
const sb = {};
vm.createContext(sb);
vm.runInContext([
  grab(RCPT, /const _PACK_WEIGHT_UNITS = \[[^\]]*\];/,  '_PACK_WEIGHT_UNITS'),
  grab(RCPT, /const _PACK_VOL_UNITS\s*= \[[^\]]*\];/,   '_PACK_VOL_UNITS'),
  grab(RCPT, /const _PACK_LENGTH_UNITS = \[[^\]]*\];/,  '_PACK_LENGTH_UNITS'),
  grab(RCPT, /const _UNIT_NAMES = \{[\s\S]*?\};/,        '_UNIT_NAMES'),
  grab(RCPT, /export function fmtPackQty\(n\)[\s\S]*?\n}\n/,      'fmtPackQty'),
  grab(RCPT, /export function packKind\(saleUnit\)[\s\S]*?\n}\n/, 'packKind'),
  grab(RCPT, /export function packSizeLabel\(saleUnit, per\)[\s\S]*?\n}\n/, 'packSizeLabel'),
  grab(RCPT, /export function unitChoiceLabel\(saleUnit\)[\s\S]*?\n}\n/, 'unitChoiceLabel'),
  grab(RET,  /function _sumModeAvailable\(saleUnit\) \{[\s\S]*?\n}/, '_sumModeAvailable'),
].join('\n').replace(/^export /gm, ''), sb);

// ── showPackChoiceModal — HAQIQIY funksiya, soxta DOM bilan ─────────────────
const modalSrc = grab(POS, /function showPackChoiceModal\(product\) \{[\s\S]*?\n}/, 'showPackChoiceModal');
function modal(product) {
  const nodes = {};
  const ctx = Object.assign(Object.create(null), {
    packKind: sb.packKind, fmtPackQty: sb.fmtPackQty, unitChoiceLabel: sb.unitChoiceLabel,
    fmtNum: n => String(n),
    openModal: () => {},
    _packChoiceProduct: null,
    document: { getElementById: id => (nodes[id] ||= { textContent: '' }) },
  });
  vm.createContext(ctx);
  vm.runInContext(`${modalSrc}\nshowPackChoiceModal(${JSON.stringify(product)});`, ctx);
  const t = id => nodes[id].textContent;
  return { pack: t('packChoicePackLbl'), hint: t('packChoicePackHint'),
           unit: t('packChoiceDonaLbl'), price: t('packChoiceDonaPrice') };
}
const P = (sale_unit, pack_size) => ({ name: 'X', sale_unit, pack_size, pack_price: 1000, price: 10 });

// ══════════════════════════════════════════════════════════════════════════
console.log('\n── 1) Metr — asosiy xato ──');
const m = modal(P('m', 100));
check('1_m_birlik_tugmasi', m.unit,  "📏 Metr bo'yicha");
check('1_m_pachka_tugmasi', m.pack,  "🧵 O'ram");
check('1_m_hint',           m.hint,  '100 m');
check('1_m_narx_birligi',   m.price, '10 UZS / m');
check('1_m_dona_YOQ',       /dona/i.test(m.unit + m.hint), false);
check('1_M_katta_harf',     modal(P('M', 50)).unit, "📏 Metr bo'yicha");

const sm = modal(P('sm', 500));
check('1_sm_birlik', sm.unit, "📏 Santimetr bo'yicha");
check('1_sm_hint',   sm.hint, '500 sm');

// ══════════════════════════════════════════════════════════════════════════
console.log('\n── 2) Og\'irlik/suyuqlik ──');
const kg = modal(P('kg', 20));
check('2_GOLDEN_kg_birlik', kg.unit, "⚖️ Kg bo'yicha");
check('2_GOLDEN_kg_pachka', kg.pack, '📦 Qop');
check('2_GOLDEN_kg_hint',   kg.hint, '20 kg');
check('2_g_birlik',    modal(P('g', 500)).unit,  "⚖️ Gramm bo'yicha");
check('2_g_hint',      modal(P('g', 500)).hint,  '500 g');
check('2_l_birlik',    modal(P('l', 5)).unit,    "⚖️ Litr bo'yicha");
check('2_l_hint',      modal(P('l', 5)).hint,    '5 l');
check('2_litr_birlik', modal(P('litr', 5)).unit, "⚖️ Litr bo'yicha");
check('2_litr_hint',   modal(P('litr', 5)).hint, '5 litr');

// ══════════════════════════════════════════════════════════════════════════
console.log('\n── 3) GOLDEN: dona va ml avvalgidek ──');
for (const u of ['pcs', 'dona', null, 'quti']) {
  const d = modal(P(u, 10));
  check(`3_GOLDEN_${u}_birlik`, d.unit, 'Dona');
  check(`3_GOLDEN_${u}_pachka`, d.pack, '📦 Pachka');
  check(`3_GOLDEN_${u}_hint`,   d.hint, '10 dona');
  check(`3_GOLDEN_${u}_narx`,   d.price, '10 UZS');
}
const ml = modal(P('ml', 150));
check('3_GOLDEN_ml_birlik', ml.unit, 'ml');
check('3_GOLDEN_ml_pachka', ml.pack, '🧴 Butun');
check('3_GOLDEN_ml_hint',   ml.hint, '150 ml');

// ══════════════════════════════════════════════════════════════════════════
console.log('\n── 4) Chek / savat yorlig\'i (packSizeLabel) ──');
check('4_m_chek',   sb.packSizeLabel('m', 150),   "O'ram (150 m)");
check('4_sm_chek',  sb.packSizeLabel('sm', 50),   "O'ram (50 sm)");
check('4_GOLDEN_kg',  sb.packSizeLabel('kg', 20),  'Qop (20 kg)');
check('4_GOLDEN_pcs', sb.packSizeLabel('pcs', 10), 'Pachka (10 dona)');
check('4_GOLDEN_ml',  sb.packSizeLabel('ml', 150), 'Butun (150 ml)');

// ══════════════════════════════════════════════════════════════════════════
console.log('\n── 5) Qaytarish summa rejimi O\'ZGARMADI ──');
check('5_m_YOQ',   sb._sumModeAvailable('m'),  false);
check('5_sm_YOQ',  sb._sumModeAvailable('sm'), false);
check('5_GOLDEN_kg_bor', sb._sumModeAvailable('kg'), true);
check('5_GOLDEN_ml_bor', sb._sumModeAvailable('ml'), true);
check('5_GOLDEN_pcs_YOQ', sb._sumModeAvailable('pcs'), false);

// Inline yorliq qaytib kelmasin (eski xato manbasi)
check('6_modal_yagona_manbadan', /unitChoiceLabel\(product\.sale_unit\)/.test(modalSrc), true);
check('6_inline_bo_yicha_YOQ',   /bo'yicha`/.test(modalSrc), false);

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
