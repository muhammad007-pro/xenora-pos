/**
 * Code128 — SVG chizg'ich (FAQAT USB/HTML chek yo'li uchun).
 *
 * ═══ NEGA BU MODUL KERAK ═══
 * Tizimda shtrix-kod kodlashning IKKI yo'li bor va ular TUBDAN farq qiladi:
 *
 *   • LAN chek (ESC/POS) — printer O'ZI kodlaydi (`GS k`). Bizda encoder
 *     kerak emas: faqat buyruq va qiymat yuboriladi. Etiketka yo'li ham
 *     shunday ishlaydi (`electron/tspl-builder.js` → TSPL `BARCODE ... "128"`).
 *   • USB chek — HTML → PDF → SumatraPDF, ya'ni printer shtrix-kod BUYRUG'INI
 *     ko'rmaydi, u RASM oladi. Shuning uchun chiziqlarni O'ZIMIZ chizishimiz
 *     kerak. Shu modul aynan shu uchun.
 *
 * ═══ MODUL KENGLIGI — SKANERLANISHNING KALITI ═══
 * Termal printer 203 dpi = 1 nuqta 0.125 mm. Modul kengligi nuqtaning BUTUN
 * karralisi bo'lmasa rasterizator chiziqlarni notekis yaxlitlaydi (biri 2,
 * ikkinchisi 3 nuqta) va skaner nisbatni xato o'qiydi. Shuning uchun kenglik
 * 3 nuqta (0.375 mm) qilib tanlanadi, sig'masa 2 nuqta (0.25 mm).
 *
 * ═══ CODE128 B va C ═══
 * Sof raqamli juft uzunlikdagi qiymat → **C** (2 raqam = 1 belgi, ya'ni ENI
 * IKKI BARAVAR tor). Prod chek raqami 10 xonali ("2610029124") → C.
 * Qolgan hamma holat (harf, chiziqcha, toq uzunlik) → **B**.
 */

// Code128 naqshlari: har biri bar/bo'shliq kengliklari (modul). 0-102 ma'lumot,
// 103=StartA, 104=StartB, 105=StartC, 106=Stop. Ma'lumot naqshlari 11 modul,
// Stop 13 modul (7 element).
const PATTERNS = [
  /*   0 */ '212222', '222122', '222221', '121223', '121322', '131222', '122213',
  /*   7 */ '122312', '132212', '221213', '221312', '231212', '112232', '122132',
  /*  14 */ '122231', '113222', '123122', '123221', '223211', '221132', '221231',
  /*  21 */ '213212', '223112', '312131', '311222', '321122', '321221', '312212',
  /*  28 */ '322112', '322211', '212123', '212321', '232121', '111323', '131123',
  /*  35 */ '131321', '112313', '132113', '132311', '211313', '231113', '231311',
  /*  42 */ '112133', '112331', '132131', '113123', '113321', '133121', '313121',
  /*  49 */ '211331', '231131', '213113', '213311', '213131', '311123', '311321',
  /*  56 */ '331121', '312113', '312311', '332111', '314111', '221411', '431111',
  /*  63 */ '111224', '111422', '121124', '121421', '141122', '141221', '112214',
  /*  70 */ '112412', '122114', '122411', '142112', '142211', '241211', '221114',
  /*  77 */ '413111', '241112', '134111', '111242', '121142', '121241', '114212',
  /*  84 */ '124112', '124211', '411212', '421112', '421211', '212141', '214121',
  /*  91 */ '412121', '111143', '111341', '131141', '114113', '114311', '411113',
  /*  98 */ '411311', '113141', '114131', '311141', '411131',
  /* 103 */ '211412',   // Start A
  /* 104 */ '211214',   // Start B
  /* 105 */ '211232',   // Start C
  /* 106 */ '2331112',  // Stop — 13 modul, 7 element (yagona istisno)
];

const START_B = 104, START_C = 105, STOP = 106;

/** Qiymat Code128C ga mos keladimi (sof raqam + juft uzunlik). */
export function fitsCodeC(value) {
  const s = String(value == null ? '' : value);
  return s.length >= 2 && s.length % 2 === 0 && /^\d+$/.test(s);
}

/**
 * Qiymat → naqsh kengliklari massivi (modul sonlari ketma-ketligi).
 * Birinchi element BAR, keyin navbatma-navbat bo'shliq/bar.
 */
export function code128Widths(value) {
  const s = String(value == null ? '' : value);
  if (!s) return null;

  const codes = [];
  if (fitsCodeC(s)) {
    codes.push(START_C);
    for (let i = 0; i < s.length; i += 2) codes.push(parseInt(s.substr(i, 2), 10));
  } else {
    codes.push(START_B);
    for (const ch of s) {
      const c = ch.charCodeAt(0);
      // Code128B: ASCII 32..126 → qiymat 0..94. Boshqasi QO'LLANMAYDI
      // (chek raqami bunday belgilarni o'z ichiga olmaydi).
      if (c < 32 || c > 126) return null;
      codes.push(c - 32);
    }
  }

  // Nazorat belgisi: (start + Σ i×qiymat) mod 103
  let sum = codes[0];
  for (let i = 1; i < codes.length; i++) sum += i * codes[i];
  codes.push(sum % 103);
  codes.push(STOP);

  const widths = [];
  for (const c of codes) {
    for (const d of PATTERNS[c]) widths.push(parseInt(d, 10));
  }
  return widths;
}

/** Naqshning jami modul soni (sig'ishni hisoblash uchun). */
export function code128Modules(value) {
  const w = code128Widths(value);
  return w ? w.reduce((a, b) => a + b, 0) : 0;
}

/**
 * Code128 SVG qaytaradi (chekka qo'yish uchun).
 *
 * opts:
 *   heightMm   — chiziq balandligi (standart 6 mm — minimal, lekin skaner oladi)
 *   maxWidthMm — sig'adigan eng katta kenglik (chek kontenti, masalan 48 mm)
 *
 * Qiymat kodlanmasa `''` qaytaradi — chek BUZILMAYDI (eski/g'alati chek
 * raqami bo'lsa shtrix-kod shunchaki chiqmaydi).
 */
export function code128Svg(value, opts) {
  const o = opts || {};
  const heightMm = o.heightMm != null ? o.heightMm : 6;
  const maxWidthMm = o.maxWidthMm != null ? o.maxWidthMm : 48;

  const widths = code128Widths(value);
  if (!widths) return '';

  const modules = widths.reduce((a, b) => a + b, 0);
  // 203 dpi nuqtaning butun karralisi: 3 nuqta → 2 nuqta → sig'dirib kesish.
  let mw = 0.375;
  if (modules * mw > maxWidthMm) mw = 0.25;
  if (modules * mw > maxWidthMm) mw = maxWidthMm / modules;

  const totalW = +(modules * mw).toFixed(3);
  let x = 0, bar = true, rects = '';
  for (const w of widths) {
    const wmm = w * mw;
    if (bar) {
      rects += `<rect x="${+x.toFixed(3)}" y="0" width="${+wmm.toFixed(3)}" height="${heightMm}"/>`;
    }
    x += wmm;
    bar = !bar;
  }

  // shape-rendering=crispEdges — chiziq chetlari xiralashmasin (rasterda muhim).
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${totalW}mm" height="${heightMm}mm"`
       + ` viewBox="0 0 ${totalW} ${heightMm}" shape-rendering="crispEdges"`
       + ` style="display:block;margin:0 auto">`
       + `<rect x="0" y="0" width="${totalW}" height="${heightMm}" fill="#fff"/>`
       + `<g fill="#000">${rects}</g></svg>`;
}
