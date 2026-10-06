/**
 * CHEK QOG'OZ KENGLIGI — sozlamaning UZATILISHI va ZAXIRA.
 *
 * ═══ MUAMMO (jonli, 1001 BARAKA) ═══
 * POS sotuv cheki 80mm to'liq chiqardi, admin "Sotuvlar tarixi"dan reprint
 * esa 57mm (tor) — narx ustuni siqilardi. Sababi:
 *   · `admin.html: reprintOrder()` xom `printReceiptHTML(html, {deviceName,
 *     title})` chaqirardi — `paperWidth` (va `fontSize`, `printType`,
 *     `printerIp/Port`) HECH BIRI uzatilmasdi;
 *   · `_rcptCfg` `/receipt-settings/` javobidan `paper_width` ni O'QIMASDI;
 *   · natijada `paperSpec(undefined)` → 58mm zaxira, do'kon 80mm sozlagan
 *     bo'lsa ham.
 *
 * ═══ ZAXIRA QIYMATI — 58, 80 EMAS (qaror) ═══
 * `electron/main.js` PDF SAHIFA o'lchamini ayni shunday hisoblaydi va u yerda
 * zaxira 58 (IKKI joyda). Kontent zaxirasi 80 (=72mm) bo'lsa-yu sahifa 58
 * qolsa — o'ngdagi NARX ustuni KESILADI. Bundan tashqari 57mm rolikdagi jonli
 * do'konlar bor (eco aroma, MANHATTAN): 80mm kontent ularda buzadi, 58mm
 * kontent esa 80mm rolikda tor ko'rinadi, lekin TO'LIQ o'qiladi.
 * Shu sabab "bitta standart" = 58 (zarar yetkazmaydigan yo'nalish), va
 * zaxiraga tushish JIM QOLMAYDI — `console.warn` yoziladi.
 *
 * ⚠️ GOLDEN: 57/58 → 48mm kontent, 80 → 72mm kontent xaritasi o'zgarmaydi.
 *
 * Ishga tushirish:  node frontend/tests/test_receipt_paper_passthrough.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { paperSpec, PAPER_FALLBACK_WIDTH } from '../../frontend/js/core/receipt-print.js';

const ADMIN = readFileSync(resolve('frontend/app/admin.html'), 'utf8');
const POS   = readFileSync(resolve('frontend/js/modules/pos.js'), 'utf8');
const MAIN  = readFileSync(resolve('electron/main.js'), 'utf8');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

// ══════════════════════════════════════════════════════════════════════════
// 1) GOLDEN — kenglik xaritasi o'zgarmagan
// ══════════════════════════════════════════════════════════════════════════
check('1_GOLDEN_57', paperSpec(57), { page: 58, content: 48 });
check('1_GOLDEN_58', paperSpec(58), { page: 58, content: 48 });
check('1_GOLDEN_80', paperSpec(80), { page: 80, content: 72 });
check('1_GOLDEN_satr_80', paperSpec('80'), { page: 80, content: 72 });

// ══════════════════════════════════════════════════════════════════════════
// 2) ZAXIRA — 58 va BALAND (jim emas)
// ══════════════════════════════════════════════════════════════════════════
check('2_zaxira_qiymati', PAPER_FALLBACK_WIDTH, 58);

const ogohlar = [];
const _ow = console.warn;
console.warn = (...a) => ogohlar.push(a.join(' '));
const spec1 = paperSpec(undefined, 'test-chaqiruv');
const spec2 = paperSpec(null);
const spec3 = paperSpec(72);          // ro'yxatda yo'q qiymat
console.warn = _ow;

check('2_undefined_58ga', spec1, { page: 58, content: 48 });
check('2_null_58ga',      spec2, { page: 58, content: 48 });
check('2_notanish_58ga',  spec3, { page: 58, content: 48 });
check('2_uchala_holat_ogohlantirdi', ogohlar.length, 3);
check('2_ogohda_chaqiruv_joyi', /test-chaqiruv/.test(ogohlar[0]), true);
check('2_ogohda_sozlama_nomi', /paper_width/.test(ogohlar[0]), true);

// ══════════════════════════════════════════════════════════════════════════
// 3) ADMIN REPRINT — sozlama UZATILADI (asosiy tuzatish)
// ══════════════════════════════════════════════════════════════════════════
// a) `_rcptCfg` API javobidan `paper_width` o'qiydi
check('3a_rcptCfg_maydoni', /_rcptCfg = \{[\s\S]*?paper_width: null[\s\S]*?\}/.test(ADMIN), true);
check('3a_apidan_oqiladi',  /_rcptCfg\.paper_width\s*=\s*r\.paper_width/.test(ADMIN), true);

// b) `printReceiptDoc` o'rami `paperWidth` ni uzatadi
check('3b_oram_uzatadi', /paperWidth:\s*_rcptCfg\.paper_width/.test(ADMIN), true);

// c) `reprintOrder` XOM `printReceiptHTML` ni ISHLATMAYDI (eski nuqson)
const reprintSrc = (ADMIN.match(/async function reprintOrder\(id\)[\s\S]*?\n\}/) || [''])[0];
check('3c_reprint_topildi', reprintSrc.length > 0, true);
check('3c_printReceiptDoc_orqali', /window\.printReceiptDoc\(html/.test(reprintSrc), true);
// ⚠️ `await` SHART: izohda eski (nuqsonli) chaqiruv nomi atayin eslatilgan,
// regex uni KOD deb o'qimasligi kerak.
check('3c_xom_chaqiruv_yoq',       /await printReceiptHTML\(/.test(reprintSrc), false);

// ══════════════════════════════════════════════════════════════════════════
// 4) POS — chetga chiqqan 80 zaxirasi olib tashlandi
// ══════════════════════════════════════════════════════════════════════════
check('4_pos_80_zaxira_yoq', /paper_width:\s*80\s*,/.test(POS), false);
check('4_pos_null_zaxira',   /paper_width:\s*null\s*,/.test(POS), true);
// POS baribir sozlamani o'qiydi va uzatadi (mavjud xulq)
check('4_pos_apidan_oqiydi', /if \(d\.paper_width\) _receiptCfg\.paper_width = d\.paper_width;/.test(POS), true);
check('4_pos_uzatadi',       /paperWidth:\s*_receiptCfg\.paper_width/.test(POS), true);

// ══════════════════════════════════════════════════════════════════════════
// 5) ELECTRON bilan MOSLIK — kontent sahifadan keng bo'lmasin
// ══════════════════════════════════════════════════════════════════════════
// `electron/main.js` ikki joyda `=== 80 ? 80 : 58` — ya'ni u ham 58 ga tushadi.
// Agar bu yerdagi zaxira 80 qilinsa, CSS kontenti (72mm) 58mm sahifaga
// sig'masdan narx ustuni kesilardi. Shu moslik qulflanadi.
const elektronZaxira = MAIN.match(/Number\((?:opts && opts|o)\.paperWidth\) === 80 \? 80 : (\d+)/g) || [];
check('5_electron_ikki_joyda', elektronZaxira.length, 2);
check('5_electron_zaxirasi_58',
      elektronZaxira.every(m => m.endsWith(': 58')), true);
check('5_ikki_tomon_mos', PAPER_FALLBACK_WIDTH, 58);

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
