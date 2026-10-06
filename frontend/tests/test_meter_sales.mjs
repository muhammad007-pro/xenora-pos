/**
 * METR (m/sm) KASRLI SOTUV + SAVAT AVTO-SCROLL.
 *
 * ═══ MUAMMO (jonli, XOZMAG / tenant 28) ═══
 * `m` birligi `isWeightUnit` ro'yxatida YO'Q edi, shuning uchun:
 *   · "necha metr?" oynasi ochilmasdi;
 *   · mato/kabel "dona" sifatida BUTUN songa majburlanardi (3.5 m sotib
 *     bo'lmasdi) — prodda 13 ta metrli sotuvning hammasi butun son;
 *   · "Summa" rejimi ham ishlamasdi ("9500 so'mlik ber" → necha metr?).
 * Prodda 30 ta `m` mahsulot bor (9 tasida pachka narxi — kabel o'rami).
 * Backend buni ALLAQACHON qo'llardi (`quantity: float`), to'siq FAQAT POS'da.
 *
 * ⚠️ GOLDEN — buzilmasligi SHART:
 *   · kg/g/l oqimi avvalgidek (425 qator jonli sotuv);
 *   · `pcs` mahsulot BUTUN son qoladi (og'irlik oynasi ochilmaydi);
 *   · (2026-10-07 yangilandi) metr pachkasi yorlig'i egasi qarori bilan
 *     "O'ram (100 m)" bo'ldi — avval "Pachka (100 dona)" edi. Qarang
 *     `test_meter_label.mjs`.
 *
 * ═══ USLUB ═══
 * Kod fayldan AJRATIB olinadi (nusxa ko'chirilmaydi) — `test_weight_pack_price.mjs`
 * naqshi. Shart yo'qolsa test "topilmadi" deb YIQILADI, jimgina o'tmaydi.
 *
 * Ishga tushirish:  node frontend/tests/test_meter_sales.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';

const POS   = readFileSync(resolve('frontend/js/modules/pos.js'), 'utf8');
const ADMIN = readFileSync(resolve('frontend/js/admin/core.js'), 'utf8');
const RCPT  = readFileSync(resolve('frontend/js/core/receipt-print.js'), 'utf8');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

/** Faylidan funksiya/const ni ajratib, baholab beradi. */
function ajrat(src, pat, nom) {
  const m = src.match(pat);
  if (!m) { fail++; console.log(`[FAIL] ${nom}: manbada TOPILMADI — test eskirgan`); return null; }
  return m[0];
}

// ══════════════════════════════════════════════════════════════════════════
// 1) KASRLI BIRLIKLAR RO'YXATI
// ══════════════════════════════════════════════════════════════════════════
const fracSrc = ajrat(POS, /const FRACTIONAL_UNITS = \[[\s\S]*?\];/, 'FRACTIONAL_UNITS');
const fracFn  = ajrat(POS, /function isFractionalUnit\(u\) \{[^}]*\}/, 'isFractionalUnit');
const lenSrc  = ajrat(POS, /const LENGTH_UNITS = \[[^\]]*\];/, 'LENGTH_UNITS');
const lenFn   = ajrat(POS, /function isLengthUnit\(u\) \{[^}]*\}/, 'isLengthUnit');

const isFractionalUnit = new Function(`${fracSrc}\n${fracFn}\nreturn isFractionalUnit;`)();
const isLengthUnit     = new Function(`${lenSrc}\n${lenFn}\nreturn isLengthUnit;`)();

// YANGI — asosiy tuzatish
check('1_m_kasrli',        isFractionalUnit('m'),    true);
check('1_sm_kasrli',       isFractionalUnit('sm'),   true);
check('1_M_katta_harf',    isFractionalUnit('M'),    true);
// GOLDEN — mavjud og'irlik oqimi
check('1_GOLDEN_kg',       isFractionalUnit('kg'),   true);
check('1_GOLDEN_g',        isFractionalUnit('g'),    true);
check('1_GOLDEN_l',        isFractionalUnit('l'),    true);
check('1_GOLDEN_litr',     isFractionalUnit('litr'), true);
// GOLDEN — butun qolishi kerak bo'lganlar
check('1_GOLDEN_pcs_butun',     isFractionalUnit('pcs'),     false);
check('1_GOLDEN_box_butun',     isFractionalUnit('box'),     false);
check('1_GOLDEN_pack_butun',    isFractionalUnit('pack'),    false);
check('1_GOLDEN_portion_butun', isFractionalUnit('portion'), false);
// `ml` ATAYIN ro'yxatda YO'Q — alohida yo'ldan ketadi (#20 atir)
check('1_ml_royxatda_yoq', isFractionalUnit('ml'), false);
check('1_ml_doAddToCart_da_qoshiladi',
      /isFractionalUnit\(product\.sale_unit\) \|\| product\.sale_unit === 'ml'/.test(POS), true);

// Uzunlik aniqlash (sarlavha/yorliq uchun)
check('1_uzunlik_m',    isLengthUnit('m'),  true);
check('1_uzunlik_sm',   isLengthUnit('sm'), true);
check('1_uzunlik_kg_yoq', isLengthUnit('kg'), false);

// ══════════════════════════════════════════════════════════════════════════
// 2) OG'IRLIK OYNASI METR UCHUN OCHILADI
// ══════════════════════════════════════════════════════════════════════════
// `addToCart` da og'irlik oynasiga yo'naltirish sharti
check('2_addToCart_kasrli_shoxi',
      /if \(isFractionalUnit\(p\.sale_unit\) && unitMode !== 'pachka'\)/.test(POS), true);
// Pachka/dona tanlovida ham (kabel o'rami: "Metr bo'yicha" tomoni)
check('2_packChoice_kasrli_shoxi',
      /p\.sale_unit === 'ml' \|\| isFractionalUnit\(p\.sale_unit\)/.test(POS), true);

// ══════════════════════════════════════════════════════════════════════════
// 3) PRESET TUGMALARI — metr uchun mos
// ══════════════════════════════════════════════════════════════════════════
const presetSrc = ajrat(POS, /const _su = String\(product\.sale_unit[\s\S]*?\];/, 'presetlar');
const presetlar = new Function('product', `${presetSrc}\nreturn presets;`);

check('3_metr_presetlari', presetlar({ sale_unit: 'm' }).map(([v]) => v),
      ['0.5', '1', '2', '3', '5', '10']);
check('3_metr_yorliqlari', presetlar({ sale_unit: 'm' }).map(([, l]) => l),
      ['0.5 m', '1 m', '2 m', '3 m', '5 m', '10 m']);
check('3_sm_presetlari', presetlar({ sale_unit: 'sm' }).map(([v]) => v),
      ['10', '20', '50', '100', '150', '200']);
// GOLDEN — mavjud presetlar tegilmagan
check('3_GOLDEN_kg_presetlari', presetlar({ sale_unit: 'kg' }).map(([v]) => v),
      ['0.1', '0.25', '0.5', '1', '1.5', '2']);
check('3_GOLDEN_g_presetlari', presetlar({ sale_unit: 'g' }).map(([v]) => v),
      ['100', '200', '300', '500', '750', '1000']);
check('3_GOLDEN_ml_presetlari', presetlar({ sale_unit: 'ml' }).map(([v]) => v),
      ['10', '20', '30', '50', '100', '150']);

// ══════════════════════════════════════════════════════════════════════════
// 4) "SUMMA" REJIMI METR UCHUN
// ══════════════════════════════════════════════════════════════════════════
// `_weightFromSum` birlikka BOG'LIQ EMAS (narxdan hisoblaydi) — metr uchun
// avtomatik ishlaydi. Formula: summa / narx, 3 xona.
const sumSrc = ajrat(POS, /function _weightFromSum\(sum\) \{[\s\S]*?\n\}/, '_weightFromSum');
const weightFromSum = new Function('_weightProduct', `${sumSrc}\nreturn _weightFromSum;`);

// XOZMAG: "JILVIR 400 METRAJ" 4000 so'm/m, mijoz 9500 so'mlik so'radi
check('4_summa_9500_4000som',  weightFromSum({ price: 4000 })(9500),  2.375);
check('4_summa_10000_2500som', weightFromSum({ price: 2500 })(10000), 4);
check('4_summa_aniq_bolmasa',  weightFromSum({ price: 3500 })(10000), 2.857);
check('4_summa_narx_0',        weightFromSum({ price: 0 })(9500),     0);
check('4_summa_0',             weightFromSum({ price: 4000 })(0),     0);

// Rejim tugmasi yorlig'i uzunlikda "Uzunlik" bo'ladi
check('4_rejim_yorligi_moslanadi',
      /_qtyBtn\.textContent = _len \? 'Uzunlik' : "Og'irlik"/.test(POS), true);
check('4_sarlavha_moslanadi',
      /_ttl\.textContent = _len \? "Uzunlik kiriting" : "Og'irlik kiriting"/.test(POS), true);

// ══════════════════════════════════════════════════════════════════════════
// 5) ADMIN FORMASI — POS bilan AYNI ro'yxat
// ══════════════════════════════════════════════════════════════════════════
const wUnits = ajrat(ADMIN, /const _wUnits = \[[^\]]*\];/, '_wUnits');
const adminUnits = new Function(`${wUnits}\nreturn _wUnits;`)();
check('5_admin_m_bor',  adminUnits.includes('m'),  true);
check('5_admin_sm_bor', adminUnits.includes('sm'), true);
// Ikki ro'yxat mos bo'lishi SHART: admin bloklasa POS'da kasr kiritilmaydi
const posUnits = new Function(`${fracSrc}\nreturn FRACTIONAL_UNITS;`)();
check('5_admin_POS_royxati_mos', [...adminUnits].sort(), [...posUnits].sort());

// ══════════════════════════════════════════════════════════════════════════
// 6) GOLDEN — PACHKA YORLIG'I O'ZGARMAGAN
// ══════════════════════════════════════════════════════════════════════════
// Metr uchun "Bobina" yorlig'i ATAYLAB qilinmadi (fayl boshidagi izoh).
check('6_GOLDEN_len_royxati_qoshilmagan', /_PACK_LEN_UNITS/.test(RCPT), false);
check('6_GOLDEN_bobina_yoq',              /[Bb]obina/.test(RCPT),       false);
check('6_GOLDEN_pack_weight_tegilmagan',
      /const _PACK_WEIGHT_UNITS = \['kg', 'g', 'l', 'litr'\];/.test(RCPT), true);

// ══════════════════════════════════════════════════════════════════════════
// 7) SAVAT AVTO-SCROLL
// ══════════════════════════════════════════════════════════════════════════
check('7_belgi_bor',        /let _cartScrollToEnd = false;/.test(POS), true);
check('7_qoshilganda_qoyiladi',
      /_cartScrollToEnd = true;\s*\/\/ yangi qator qo'shildi/.test(POS), true);
check('7_silliq_scroll',
      /list\.scrollTo\(\{ top: list\.scrollHeight, behavior: 'smooth' \}\)/.test(POS), true);
check('7_eski_webview_zaxira', /list\.scrollTop = list\.scrollHeight;/.test(POS), true);
check('7_renderCart_oxirida_rAF', /requestAnimationFrame\(\(\) => \{/.test(POS), true);
// ⚠️ Belgi FAQAT `doAddToCart` da qo'yiladi — o'chirish/miqdor o'zgarishida
// kassirning scroll holati tegilmaydi.
check('7_faqat_bir_joyda_qoyiladi',
      (POS.match(/_cartScrollToEnd = true/g) || []).length, 1);
// Belgi iste'mol qilinadi (bir martalik) — aks holda har renderda sakrardi
check('7_belgi_tozalanadi', /_cartScrollToEnd = false;\s*\n\s*\/\/ `requestAnimationFrame`/.test(POS), true);

// ══════════════════════════════════════════════════════════════════════════
// 8) GOLDEN — ESKI NOM QOLMAGAN
// ══════════════════════════════════════════════════════════════════════════
check('8_isWeightUnit_qolmagan', /isWeightUnit/.test(POS), false);

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
