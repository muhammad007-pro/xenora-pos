/**
 * Code128 encoder tekshiruvi (`frontend/js/core/code128.js`).
 *
 * ⚠️ NEGA BU TEST MUHIM: shtrix-kod JIMGINA buziladi. Naqsh jadvalidagi bitta
 * xato chekda "to'g'ri ko'rinadigan" lekin SKANER O'QIMAYDIGAN chiziq beradi.
 * Shuning uchun spetsifikatsiya invariantlari qotirib qo'yiladi.
 *
 * DIQQAT: bu test FIZIK skanerlashni ALMASHTIRMAYDI. USB yo'lida chiziqlarni
 * biz chizamiz, LAN yo'lida esa printer o'zi kodlaydi (`GS k`) — ikkisini
 * bitta chekda solishtirib bir marta skanerlab ko'rish SHART.
 *
 * Ishga tushirish:  node frontend/tests/test_code128.mjs
 */
import { code128Widths, code128Modules, code128Svg, fitsCodeC } from '../js/core/code128.js';

let fail = 0;
function check(nom, bor, kutilgan) {
  const a = JSON.stringify(bor), b = JSON.stringify(kutilgan);
  if (a === b) { console.log(`[OK  ] ${nom}: ${a}`); }
  else { console.log(`[FAIL] ${nom}: ${a} (kutilgan ${b})`); fail++; }
}

// ── 1) JADVAL INVARIANTLARI (spetsifikatsiya) ────────────────────────────────
// Jadvalni to'g'ridan o'qiy olmaymiz (eksport qilinmagan), shuning uchun
// kodlangan natija orqali tekshiramiz.

// Code128C: start + 5 ma'lumot + check = 7 naqsh × 11 + stop 13 = 90 modul
check('C_10_raqam_modul', code128Modules('2610029124'), 90);
// Code128B: start + 10 ma'lumot + check = 12 × 11 + 13 = 145 modul
check('B_10_belgi_modul', code128Modules('A610029124'), 145);
// Toq uzunlikdagi raqam → B (C juft talab qiladi): 1+9+1=11 × 11 + 13 = 134
check('B_toq_raqam_modul', code128Modules('261002912'), 134);

check('fitsCodeC_juft_raqam', fitsCodeC('2610029124'), true);
check('fitsCodeC_toq_raqam', fitsCodeC('261002912'), false);
check('fitsCodeC_harfli', fitsCodeC('A-1001'), false);

// Har naqsh 11 modul (stop 13) — jami 6 elementli guruhlarga bo'linishi kerak
const w = code128Widths('2610029124');
// StartC + 5 ma'lumot + nazorat = 7 naqsh × 6 element, + stop 7 element
check('element_soni', w.length, 7 * 6 + 7);
const stopWidths = w.slice(-7);
check('stop_naqshi', stopWidths, [2, 3, 3, 1, 1, 1, 2]);
check('stop_moduli', stopWidths.reduce((a, b) => a + b, 0), 13);

// Ma'lumot naqshlarining HAR BIRI 11 modul
let hammasi11 = true;
for (let i = 0; i + 6 <= w.length - 7; i += 6) {
  const s = w.slice(i, i + 6).reduce((a, b) => a + b, 0);
  if (s !== 11) hammasi11 = false;
}
check('har_naqsh_11_modul', hammasi11, true);

// ── 2) START NAQSHLARI (standart qiymatlar) ──────────────────────────────────
// Start C = 211232, Start B = 211214. Birinchi 6 element shuni berishi kerak.
check('startC_naqshi', code128Widths('2610029124').slice(0, 6), [2, 1, 1, 2, 3, 2]);
check('startB_naqshi', code128Widths('A-1001').slice(0, 6), [2, 1, 1, 2, 1, 4]);

// ── 3) NAZORAT BELGISI (qo'lda hisoblangan) ──────────────────────────────────
// "2610029124" → StartC(105) + [26,10,02,91,24]
//   sum = 105 + 1*26 + 2*10 + 3*2 + 4*91 + 5*24 = 105+26+20+6+364+120 = 641
//   641 mod 103 = 641 - 6*103(618) = 23  → nazorat belgisi 23 → naqsh '312131'
check('nazorat_belgisi_naqshi', code128Widths('2610029124').slice(36, 42), [3, 1, 2, 1, 3, 1]);

// "A-1001" → StartB(104) + ['A'=33, '-'=13, '1'=17, '0'=16, '0'=16, '1'=17]
//   sum = 104 + 1*33 + 2*13 + 3*17 + 4*16 + 5*16 + 6*17 = 104+33+26+51+64+80+102 = 460
//   460 mod 103 = 460 - 4*103(412) = 48 → naqsh '313121'
check('nazorat_belgisi_B', code128Widths('A-1001').slice(42, 48), [3, 1, 3, 1, 2, 1]);

// ── 4) SVG GEOMETRIYASI ──────────────────────────────────────────────────────
const svg = code128Svg('2610029124', { heightMm: 6, maxWidthMm: 48 });
check('svg_yaratildi', svg.startsWith('<svg'), true);
// 90 modul × 0.375 mm = 33.75 mm (203 dpi da 3 nuqta — butun karrali)
check('svg_kengligi_33.75mm', /width="33\.75mm"/.test(svg), true);
check('svg_balandligi_6mm', /height="6mm"/.test(svg), true);
check('svg_crispEdges', svg.includes('shape-rendering="crispEdges"'), true);
// Bar soni: 7 naqsh × 3 bar = 21, + stop 4 bar (2331112) = 25, + 1 oq fon
check('bar_soni', (svg.match(/<rect /g) || []).length, 1 + 25);

// Uzun qiymat 48 mm ga sig'sin (modul 0.25 mm ga tushadi)
const uzun = code128Svg('A610029124', { heightMm: 6, maxWidthMm: 48 });
check('uzun_svg_sigdi', /width="36\.25mm"/.test(uzun), true);   // 145 × 0.25

// ── 5) XATOGA CHIDAMLILIK — chek BUZILMASIN ──────────────────────────────────
check('bosh_qiymat', code128Svg('', {}), '');
check('null_qiymat', code128Svg(null, {}), '');
check('kirill_qiymat', code128Svg('ЧЕК-1', {}), '');   // ASCII emas → chizmaydi

console.log('');
if (fail) { console.log(`${fail} ta TEKSHIRUV YIQILDI`); process.exit(1); }
console.log('HAMMASI PASS');
