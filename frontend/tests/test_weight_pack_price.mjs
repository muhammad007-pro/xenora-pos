/**
 * KG MAHSULOTDA QOP (pachka) NARXI — client oqimi va yorliqlar.
 *
 * ═══ NEGA BU TEST BOR ═══
 *
 * "20 kg qop" ni sotish FRONTENDDA ikki joyda to'silgan edi (backend esa
 * buni allaqachon qo'llardi — `backend/tests/test_weight_pack_price.py`):
 *
 *   1. `pos.js` — pachka tanlov modali sharti `!isFractionalUnit(p.sale_unit)`
 *      bilan kg ni ATAYLAB chetlab o'tardi.
 *   2. `admin/core.js` — `togglePack` kg uchun pachka blokini YASHIRARDI va
 *      maydonlarni tozalardi, ya'ni qop narxini kiritishning yo'li yo'q edi.
 *
 * Ustiga yorliqlar TO'RT joyda "dona" deb QOTIB qolgan edi → kg mahsulotda
 * "Qop (20 dona)" bo'lib chiqardi.
 *
 * ⚠️ GOLDEN — ikkisi ham buzilmasligi SHART:
 *   · OG'IRLIK OQIMI (425 qator jonli sotuv): kg mahsulot kg bo'yicha
 *     sotilishi avvalgidek. Tarozi/skanerdan kelgan og'irlik (`presetWeight`)
 *     pachka modalini OCHMAYDI — ochsa kassir o'lchangan og'irlikni yo'qotadi.
 *   · MAVJUD PACHKALI MAHSULOTLAR (ml 185, pcs 83, m 3): yorliq matni
 *     BIT-BITIGA o'zgarmaydi.
 *
 * ═══ USLUB ═══
 * Kod fayllardan AJRATIB olinadi (nusxa ko'chirilmaydi) — `test_pos_price_edit.js`
 * dagi naqsh. Shunda funksiya o'zgarsa test ham u bilan o'zgaradi va shart
 * yo'qolsa test "topilmadi" deb YIQILADI, jimgina o'tib ketmaydi.
 *
 * ⚠️ 2026-10-06: `isWeightUnit` → `isFractionalUnit` deb NOMI O'ZGARDI
 * (metr qo'shilgach "og'irlik" nomi shartni yashirardi — qarang
 * `test_meter_sales.mjs`). Xulq AYNI; bu yerda faqat nom yangilandi.
 *
 * Ishga tushirish:  node frontend/tests/test_weight_pack_price.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const ROOT = resolve('frontend');
const rd = p => readFileSync(resolve(ROOT, p), 'utf8').replace(/\r\n/g, '\n');

const POS  = rd('js/modules/pos.js');
const RCPT = rd('js/core/receipt-print.js');
const CORE = rd('js/admin/core.js');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

/** Fayldan bo'lak ajratadi; topilmasa test YIQILADI (eskirgan deb). */
function grab(src, re, what) {
  const m = src.match(re);
  if (!m) { console.error(`XATO: "${what}" topilmadi — test eskirgan yoki kod o'zgargan.`); process.exit(2); }
  return m[0];
}

// ══════════════════════════════════════════════════════════════════════════════
// Sandbox: HAQIQIY yorliq funksiyalari (receipt-print.js) + pos.js yordamchilari
// ══════════════════════════════════════════════════════════════════════════════
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext([
  grab(RCPT, /const _PACK_WEIGHT_UNITS = \[[^\]]*\];/,            '_PACK_WEIGHT_UNITS'),
  grab(RCPT, /const _PACK_VOL_UNITS\s*= \[[^\]]*\];/,             '_PACK_VOL_UNITS'),
  grab(RCPT, /export function fmtPackQty\(n\)[\s\S]*?\n}\n/,      'fmtPackQty'),
  grab(RCPT, /export function packKind\(saleUnit\)[\s\S]*?\n}\n/, 'packKind'),
  grab(RCPT, /export function packSizeLabel\(saleUnit, per\)[\s\S]*?\n}\n/, 'packSizeLabel'),
  // ⚠️ `FRACTIONAL_UNITS` ro'yxati HAM ajratilishi shart: funksiya unga
  // tayanadi (metr qo'shilgach ro'yxat alohida const'ga chiqarildi).
  grab(POS,  /const FRACTIONAL_UNITS = \[[\s\S]*?\];/,              'FRACTIONAL_UNITS'),
  grab(POS,  /function isFractionalUnit\(u\) \{[^}]*\}/,              'isFractionalUnit'),
  grab(POS,  /function isPackProduct\(p\) \{[\s\S]*?\n}/,         'isPackProduct'),
].join('\n').replace(/^export /gm, ''), sandbox);

const { fmtPackQty, packKind, packSizeLabel, isFractionalUnit, isPackProduct } = sandbox;

// ══════════════════════════════════════════════════════════════════════════════
// 1) YORLIQLAR — sale_unit ga qarab ("dona" qotib qolmasin)
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 1) Yorliqlar ──');

check('1_kg_qop',        packSizeLabel('kg', 20),   'Qop (20 kg)');
check('1_g_qop',         packSizeLabel('g', 500),   'Qop (500 g)');
check('1_litr_qop',      packSizeLabel('litr', 5),  'Qop (5 litr)');
check('1_l_qop',         packSizeLabel('l', 5),     'Qop (5 l)');
check('1_kg_pack_nomi',  packKind('kg').pack,       'Qop');
check('1_kg_ikonka',     packKind('kg').packIcon,   '📦');
check('1_kg_birlik_ikonka', packKind('kg').unitIcon, '⚖️');

// ── GOLDEN: mavjud mahsulotlar matni BIT-BITIGA o'zgarmaydi ──
check('1_GOLDEN_ml_185',   packSizeLabel('ml', 150),   'Butun (150 ml)');
check('1_GOLDEN_ml_nomi',  packKind('ml').pack,        'Butun');
check('1_GOLDEN_ml_ikonka', packKind('ml').packIcon,   '🧴');
check('1_GOLDEN_pcs_83',   packSizeLabel('pcs', 10),   'Pachka (10 dona)');
check('1_GOLDEN_dona',     packSizeLabel('dona', 12),  'Pachka (12 dona)');
check('1_GOLDEN_m_3',      packSizeLabel('m', 100),    'Pachka (100 dona)');
check('1_GOLDEN_bosh_birlik', packSizeLabel(null, 6),  'Pachka (6 dona)');
check('1_GOLDEN_notogri_birlik', packSizeLabel('qop', 4), 'Pachka (4 dona)');

// Katta-kichik harf
check('1_KG_katta_harf',  packSizeLabel('KG', 20),  'Qop (20 kg)');

// ══════════════════════════════════════════════════════════════════════════════
// 2) YAXLITLASH — Math.round emas, 3 xona (base_qty/qty kasrli chiqishi mumkin)
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 2) 3 xonali yaxlitlash ──');

check('2_butun_nol_qoldirmaydi', fmtPackQty(20),      '20');     // "20.000" EMAS
check('2_yarim_saqlanadi',       fmtPackQty(0.5),     '0.5');    // Math.round -> 1 (xato)
check('2_uch_xona',              fmtPackQty(0.7405882), '0.741');
check('2_uzun_kasr_qisqaradi',   fmtPackQty(1 / 3),   '0.333');
check('2_null_nol',              fmtPackQty(null),    '0');
check('2_undefined_nol',         fmtPackQty(undefined), '0');
check('2_matn_nol',              fmtPackQty('x'),     '0');
// Kasrli qop yorlig'i butunlab yo'qolmaydi
check('2_yarim_kg_qop_yorligi',  packSizeLabel('kg', 0.5), 'Qop (0.5 kg)');

// ══════════════════════════════════════════════════════════════════════════════
// 3) OQIM — pos.js dagi HAQIQIY shartlar ustida qaror jadvali
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 3) Oqim (qaror jadvali) ──');

// Shartlarni fayldan AYNAN olamiz — o'zgarsa yoki yo'qolsa test yiqiladi.
const packGuardSrc = grab(POS,
  /if \(unitMode == null && presetWeight == null && isPackProduct\(p\)\) \{/,
  'pachka tanlov sharti');
const weightGuardSrc = grab(POS,
  /if \(isFractionalUnit\(p\.sale_unit\) && unitMode !== 'pachka'\) \{/,
  "og'irlik modali sharti");

// To'siq OLINGANINI tasdiqlaymiz: eski `!isFractionalUnit(...)` qaytib kelmasin
check('3_eski_tosiq_olindi', /!isFractionalUnit/.test(packGuardSrc), false);
// ⚠️ GOLDEN sharti SAQLANGANINI tasdiqlaymiz
check('3_presetWeight_sharti_bor', /presetWeight == null/.test(packGuardSrc), true);
check('3_unitMode_pachka_istisnosi', /unitMode !== 'pachka'/.test(weightGuardSrc), true);

// Shartlarni BAHOLAYMIZ (matn tekshiruvi yetarli emas — mantiq ham to'g'ri bo'lsin)
const cond = (src) => {
  const body = src.replace(/^if \(/, '').replace(/\) \{$/, '');
  return vm.runInContext(
    `(function(unitMode, presetWeight, p){ return !!(${body}); })`, sandbox);
};
const packModalOchiladi = cond(packGuardSrc);
const ogirlikModaliga   = cond(weightGuardSrc);

const KG_QOP  = { sale_unit: 'kg',  pack_size: 20, pack_price: 450000 };
const KG_SOF  = { sale_unit: 'kg',  pack_size: null, pack_price: null };
const PCS_PK  = { sale_unit: 'pcs', pack_size: 10, pack_price: 30000 };
const ML_PK   = { sale_unit: 'ml',  pack_size: 150, pack_price: 250000 };

// a) Kartaga bosildi (unitMode=null, presetWeight=null)
check('3a_kg_qop_tanlov_modali',  packModalOchiladi(null, null, KG_QOP), true);
check('3a_kg_qopsiz_modal_YOQ',   packModalOchiladi(null, null, KG_SOF), false);
check('3a_pcs_pachka_modal',      packModalOchiladi(null, null, PCS_PK), true);
check('3a_ml_butun_modal',        packModalOchiladi(null, null, ML_PK),  true);

// b) ⚠️ GOLDEN — SKANER/TAROZIDAN kelgan og'irlik pachka modalini OCHMAYDI
check('3b_GOLDEN_skaner_ogirligi_modal_ochmaydi',
      packModalOchiladi(null, 0.740, KG_QOP), false);
check('3b_GOLDEN_skaner_ogirligi_qopsiz_ham',
      packModalOchiladi(null, 1.5, KG_SOF), false);

// c) Tanlov qilingandan keyin modal QAYTA ochilmaydi
check('3c_qop_tanlandi_modal_qayta_ochmaydi', packModalOchiladi('pachka', null, KG_QOP), false);
check('3c_dona_tanlandi_modal_qayta_ochmaydi', packModalOchiladi('dona', null, PCS_PK), false);

// d) Og'irlik modaliga yo'naltirish
check('3d_kg_qop_tanlansa_ogirlikka_TUSHMAYDI',
      ogirlikModaliga('pachka', null, KG_QOP), false);   // qop oqimi savatga boradi
check('3d_kg_ogirlik_boyicha_ogirlikka',
      ogirlikModaliga(null, null, KG_QOP), true);
check('3d_kg_qopsiz_ogirlikka', ogirlikModaliga(null, null, KG_SOF), true);
check('3d_GOLDEN_skaner_ogirligi_ham_shu_shoxda',
      ogirlikModaliga(null, 0.740, KG_QOP), true);       // presetWeight bilan savatga
check('3d_pcs_ogirlikka_tushmaydi', ogirlikModaliga(null, null, PCS_PK), false);
check('3d_ml_ogirlikka_tushmaydi',  ogirlikModaliga(null, null, ML_PK),  false);

// e) "Birlik bo'yicha" tugmasi kg ni og'irlik oynasiga yuboradi
const donaBtnSrc = grab(POS,
  /if \(p\.sale_unit === 'ml' \|\| isFractionalUnit\(p\.sale_unit\)\) showWeightModal\(p\);/,
  "birlik tugmasi yo'naltirishi");
check('3e_kg_tugmasi_ogirlik_oynasi', /isFractionalUnit\(p\.sale_unit\)/.test(donaBtnSrc), true);
check('3e_ml_avvalgidek', /p\.sale_unit === 'ml'/.test(donaBtnSrc), true);

// ══════════════════════════════════════════════════════════════════════════════
// 4) SAVAT yorlig'i — doAddToCart pachka shoxi yagona manbadan
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 4) Savat yorlig\'i ──');

const cartLbl = grab(POS, /_packLabel: packSizeLabel\(product\.sale_unit, product\.pack_size\),/,
                     'savat _packLabel');
check('4_savat_yagona_manbadan', cartLbl.includes('packSizeLabel'), true);
// Eski qotib qolgan matn qaytib kelmasin
check('4_eski_qotgan_dona_yoq', /Pachka \(\$\{product\.pack_size\} dona\)/.test(POS), false);

// POS cheki yorlig'i
const rcptLbl = grab(POS, /return packSizeLabel\(i\.sale_unit, i\.base_qty \/ q\);/, 'POS chek yorlig\'i');
check('4_pos_chekida_sale_unit', rcptLbl.includes('i.sale_unit'), true);
check('4_pos_chekida_Math_round_yoq', /Math\.round\(i\.base_qty/.test(POS), false);

// Bosiladigan chek (receipt-print.js)
check('4_bosma_chek_Math_round_yoq', /Math\.round\(it\.base_qty/.test(RCPT), false);
check('4_bosma_chek_yagona_manbadan',
      /packSizeLabel\(it\.sale_unit, it\.base_qty \/ qty\)/.test(RCPT), true);

// ══════════════════════════════════════════════════════════════════════════════
// 5) MAHSULOT FORMASI (admin/core.js)
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 5) Mahsulot formasi ──');

const toggleSrc = grab(CORE, /const togglePack = \(\) => \{[\s\S]*?\n      \};/, 'togglePack');
// Blok endi YASHIRILMAYDI va maydonlar TOZALANMAYDI
check('5_blok_hamisha_korinadi', /packBlock\.style\.display = '';/.test(toggleSrc), true);
check('5_yashirish_olindi', /display = isW \? 'none'/.test(toggleSrc), false);
check('5_tozalash_olindi', /pmf_pack_price'\)\.value = ''/.test(toggleSrc), false);

// Qop yorliqlari bor va `_wUnits` shoxi `_volUnits` DAN OLDIN
const labelsSrc = grab(CORE, /const updatePackLabels = \(\) => \{[\s\S]*?\n      \};/, 'updatePackLabels');
check('5_qop_sarlavhasi', /Qop bilan sotish/.test(labelsSrc), true);
check('5_qop_narxi_placeholder', /Qop narxi/.test(labelsSrc), true);
check('5_qopdagi_kg_placeholder', /Qopdagi \$\{u\}/.test(labelsSrc), true);
check('5_wUnits_shoxi_oldin',
      labelsSrc.indexOf('_wUnits.includes(u)') < labelsSrc.indexOf('_volUnits.includes(u)'), true);
// GOLDEN: flakon (ml) shoxi joyida
check('5_GOLDEN_flakon_shoxi_bor', /Butun \(flakon\) bilan sotish/.test(labelsSrc), true);
check('5_GOLDEN_pachka_shoxi_bor', /Pachka bilan sotish/.test(labelsSrc), true);

// Pachka marjasi: tannarx × pack_size (server bilan BIR XIL formula)
check('5_pachka_marjasi_bor', /const packCost = c \* ps;/.test(CORE), true);
check('5_marja_qop_sozi', /_mW\.includes\(u\) \? 'Qop'/.test(CORE), true);

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
