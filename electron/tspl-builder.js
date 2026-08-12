/**
 * TSPL yadro — ETIKETKA baytlarini generatsiya qiladi (LAN transport uchun).
 *
 * NAMUNA: electron/escpos-builder.js (chek, ESC/POS) — tuzilishi, sanitizatsiya
 * va pul formatlash naqshi shu yerga ko'chirildi. Lekin bu MUTLAQO ALOHIDA yo'l:
 * chek printeri (ESC/POS) kodiga tegilmaydi. Etiketka printeri boshqa tilda
 * (TSPL) gaplashadi va boshqa qurilma (Xprinter XP-350B).
 *
 * Bu fayl HECH QAYERGA ULANMAYDI — faqat structured ma'lumotdan bayt yasaydi
 * (sof funksiyalar, Electron/BrowserWindow'ga bog'liq emas — shuning uchun
 * oddiy `node` bilan ham sinash mumkin). Ulanish (TCP socket) alohida:
 * electron/lan-socket.js `sendRawTcp` (u protokolga bog'liq emas — ESC/POS
 * baytini ham, TSPL baytini ham bir xil yuboradi).
 *
 * ── O'LCHAM HISOBI ──────────────────────────────────────────────────────────
 * XP-350B = 203 dpi → 8 nuqta/mm. Standart etiketka 40x30 mm = 320x240 nuqta.
 * Barcha joylashuv NUQTADA hisoblanadi (TSPL koordinatalari nuqtada).
 *
 * ── TSPL vs ESC/POS farqi (muhim) ───────────────────────────────────────────
 * ESC/POS — oqim (matn qatorma-qator ketadi). TSPL — KOORDINATALI: har element
 * (TEXT/BARCODE) x,y bilan qo'yiladi, keyin PRINT butun etiketkani bosadi.
 * Shuning uchun wrapText emas, "nuqta kengligiga sig'dirish" kerak va
 * markazlashtirish qo'lda hisoblanadi (TSPL'da avto-markaz YO'Q).
 */
'use strict';

// 203 dpi printer — 1 mm = 8 nuqta. Boshqa dpi kerak bo'lsa opts.dpi orqali.
const DOTS_PER_MM_203 = 8;

function dotsPerMm(dpi) {
    const d = Number(dpi) || 203;
    return d / 25.4;
}

function mmToDots(mm, dpi) {
    return Math.round((Number(mm) || 0) * dotsPerMm(dpi));
}

// TSPL ichki shriftlar (203 dpi da bir belgining nuqta o'lchami).
// Markazlashtirish va sig'dirish shu jadval asosida hisoblanadi.
const FONT_METRICS = {
    '1': { w: 8,  h: 12 },
    '2': { w: 12, h: 20 },
    '3': { w: 16, h: 24 },
    '4': { w: 24, h: 32 },
    '5': { w: 32, h: 48 },
};

function fontMetrics(font) {
    return FONT_METRICS[String(font)] || FONT_METRICS['2'];
}

// Belgining haqiqiy kengligi = shrift kengligi × x-multiplikator.
function charWidth(font, xMul) {
    return fontMetrics(font).w * (Number(xMul) || 1);
}

function charHeight(font, yMul) {
    return fontMetrics(font).h * (Number(yMul) || 1);
}

// ── Sanitizatsiya ────────────────────────────────────────────────────────────
// TSPL ichki shriftlari faqat ASCII/Latin — kirill YOKI maxsus tipografik
// belgilar chop etilmaydi (bo'sh joy yoki axlat chiqadi). Ikki bosqich:
//   1) tipografik belgilar → ASCII (escpos-builder.js SANITIZE_MAP bilan bir xil)
//   2) o'zbek kirilli → lotin translitiratsiya (mahsulot nomlari aralash keladi)
const SANITIZE_MAP = {
    'ʻ': "'", 'ʼ': "'", '‘': "'", '’': "'",
    '“': '"', '”': '"', '–': '-', '—': '-',
    '…': '...', '•': '*', ' ': ' ',
};

// O'zbek kirill → lotin. Uzun birikmalar (ch/sh/yo...) BIRINCHI almashtiriladi,
// aks holda 'ч' → 'c'+'h' emas, alohida harflar buzib chiqadi.
const CYRILLIC_MAP = {
    'Ў': "O'", 'ў': "o'", 'Қ': 'Q', 'қ': 'q', 'Ғ': "G'", 'ғ': "g'", 'Ҳ': 'H', 'ҳ': 'h',
    'Ё': 'Yo', 'ё': 'yo', 'Ж': 'J', 'ж': 'j', 'Ч': 'Ch', 'ч': 'ch', 'Ш': 'Sh', 'ш': 'sh',
    'Щ': 'Sh', 'щ': 'sh', 'Ю': 'Yu', 'ю': 'yu', 'Я': 'Ya', 'я': 'ya', 'Ц': 'Ts', 'ц': 'ts',
    'А': 'A', 'а': 'a', 'Б': 'B', 'б': 'b', 'В': 'V', 'в': 'v', 'Г': 'G', 'г': 'g',
    'Д': 'D', 'д': 'd', 'Е': 'E', 'е': 'e', 'З': 'Z', 'з': 'z', 'И': 'I', 'и': 'i',
    'Й': 'Y', 'й': 'y', 'К': 'K', 'к': 'k', 'Л': 'L', 'л': 'l', 'М': 'M', 'м': 'm',
    'Н': 'N', 'н': 'n', 'О': 'O', 'о': 'o', 'П': 'P', 'п': 'p', 'Р': 'R', 'р': 'r',
    'С': 'S', 'с': 's', 'Т': 'T', 'т': 't', 'У': 'U', 'у': 'u', 'Ф': 'F', 'ф': 'f',
    'Х': 'X', 'х': 'x', 'Ъ': "'", 'ъ': "'", 'Ь': '', 'ь': '', 'Ы': 'i', 'ы': 'i',
    'Э': 'E', 'э': 'e',
};

function sanitize(s) {
    if (s === null || s === undefined) return '';
    let out = String(s);
    for (const [a, b] of Object.entries(SANITIZE_MAP)) {
        out = out.split(a).join(b);
    }
    for (const [a, b] of Object.entries(CYRILLIC_MAP)) {
        if (out.indexOf(a) !== -1) out = out.split(a).join(b);
    }
    // Qolgan ASCII bo'lmagan belgilar (emoji, xitoy, hali qolgan kirill) — olib
    // tashlanadi. Printer ularni baribir chiza olmaydi, axlat chiqargandan ko'ra
    // yo'q bo'lgani yaxshi.
    return out.replace(/[^\x20-\x7E]/g, '');
}

// TSPL'da matn qo'shtirnoq ichida: `TEXT x,y,"2",0,1,1,"MATN"`. Matn ichidagi
// qo'shtirnoq va teskari slesh buyruqni BUZADI — ekranlash SHART.
function escapeTspl(s) {
    return sanitize(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

// escpos-builder.js money() bilan AYNI naqsh — 150000 → "150 000".
function money(n) {
    const v = Math.round(Number(n) || 0);
    return String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

// Matnni berilgan NUQTA kengligiga sig'dirish (belgi soniga aylantirib qirqadi).
function fitText(text, maxDots, font, xMul) {
    const s = sanitize(text);
    const cw = charWidth(font, xMul);
    const maxChars = Math.max(1, Math.floor(maxDots / cw));
    if (s.length <= maxChars) return s;
    if (maxChars <= 3) return s.slice(0, maxChars);
    return s.slice(0, maxChars - 3) + '...';
}

// Uzun nomni 2 qatorga bo'lish (so'z butunligicha ko'chadi; oxirgi qator
// sig'masa "..." bilan qirqiladi). Etiketka kichik — 2 qatordan ko'pi sig'maydi.
function splitName(text, maxDots, font, xMul, maxLines) {
    const s = sanitize(text);
    const cw = charWidth(font, xMul);
    const maxChars = Math.max(1, Math.floor(maxDots / cw));
    const limit = Math.max(1, Number(maxLines) || 2);

    const words = s.split(/\s+/).filter(Boolean);
    const lines = [];
    let cur = '';
    for (const w of words) {
        const next = cur ? cur + ' ' + w : w;
        if (next.length <= maxChars) {
            cur = next;
        } else {
            if (cur) lines.push(cur);
            cur = w.length > maxChars ? w.slice(0, maxChars) : w;
        }
        if (lines.length >= limit) break;
    }
    if (cur && lines.length < limit) lines.push(cur);
    if (!lines.length) return [''];

    // Sig'magan qoldiq bo'lsa — oxirgi qatorni "..." bilan belgilaymiz.
    const used = lines.join(' ');
    if (used.length < s.length) {
        const last = lines[lines.length - 1];
        lines[lines.length - 1] = last.length > maxChars - 3
            ? last.slice(0, Math.max(1, maxChars - 3)) + '...'
            : last + '...';
    }
    return lines;
}

// Markazlashtirish uchun x koordinatasi (TSPL'da avto-markaz yo'q).
function centerX(textLen, labelDots, font, xMul) {
    const w = textLen * charWidth(font, xMul);
    return Math.max(0, Math.round((labelDots - w) / 2));
}

// Narx uchun eng KATTA sig'adigan shriftni tanlaydi. Narx — etiketkadagi eng
// muhim element, uni "150 00..." qilib qirqish YARAMAYDI; o'rniga shriftni
// kichraytiramiz. Ro'yxat kattadan kichikka: 32 → 24 → 16 → 12 nuqta kenglik.
const PRICE_FONT_LADDER = [
    { font: '3', mul: 2 },
    { font: '4', mul: 1 },
    { font: '3', mul: 1 },
    { font: '2', mul: 1 },
];

function pickPriceFont(text, maxDots) {
    const len = String(text || '').length;
    for (const f of PRICE_FONT_LADDER) {
        if (len * charWidth(f.font, f.mul) <= maxDots) return f;
    }
    return PRICE_FONT_LADDER[PRICE_FONT_LADDER.length - 1];
}

// ── Barcode ──────────────────────────────────────────────────────────────────
// 13 xonali sof raqam → EAN13 (printer nazorat raqamini o'zi tekshiradi),
// aks holda → CODE128 (universal: harf+raqam).
function barcodeType(code) {
    return /^\d{13}$/.test(String(code || '')) ? 'EAN13' : '128';
}

// Barcode kengligini NUQTADA taxminlash — markazlashtirish uchun kerak.
// EAN-13 doim 95 modul. CODE128: start(11) + har belgi 11 + checksum(11) +
// stop(13) = 11*n + 35 modul. Modul kengligi = narrow.
function barcodeWidthDots(code, type, narrow) {
    const n = Math.max(1, Number(narrow) || 2);
    const s = String(code || '');
    const modules = type === 'EAN13' ? 95 : (11 * s.length + 35);
    return modules * n;
}

// ── TSPL buyruq qatori ───────────────────────────────────────────────────────
// TSPL har buyruqni CRLF bilan tugatishni kutadi (LF yolg'iz — ba'zi firmware
// buyruqni qabul qilmaydi).
function cmd(s) {
    return s + '\r\n';
}

/**
 * Etiketka(lar) uchun TSPL bayt yasaydi.
 *
 * items: [{ name, price, barcode, qty }]
 *   name    — mahsulot nomi (2 qatorgacha sig'diriladi)
 *   price   — son yoki tayyor matn; son bo'lsa money() bilan formatlanadi
 *   barcode — EAN-13 (13 raqam) yoki ixtiyoriy kod (CODE128)
 *   qty     — SHU etiketkadan nechta nusxa (yo'q bo'lsa opts.copies)
 *
 * opts: {
 *   widthMm=40, heightMm=30, gapMm=2,   // etiketka o'lchami va oraliq
 *   density=8, speed=4,                  // qoralik (0-15) va tezlik (dyuym/s)
 *   copies=1, dpi=203,
 *   currency='' // narx yoniga qo'shiladigan matn, masalan "so'm"
 * }
 */
function buildLabelBytes(items, opts) {
    const list = Array.isArray(items) ? items : [items];
    const o = opts || {};

    const widthMm  = Number(o.widthMm)  || 40;
    const heightMm = Number(o.heightMm) || 30;
    const gapMm    = o.gapMm != null ? Number(o.gapMm) : 2;
    const density  = o.density != null ? Number(o.density) : 8;
    const speed    = o.speed   != null ? Number(o.speed)   : 4;
    const dpi      = Number(o.dpi) || 203;
    const currency = o.currency ? sanitize(o.currency) : '';

    const W = mmToDots(widthMm, dpi);    // 40mm @203dpi = 320
    const H = mmToDots(heightMm, dpi);   // 30mm @203dpi = 240
    const M = 8;                          // chetki bo'sh joy (nuqta)
    const usable = W - M * 2;             // 304 nuqta

    // ── Vertikal joylashuv (40x30mm = 320x240 uchun hisoblangan) ──
    //   y=6    nom 1-qator   (shrift 2, 12x20)
    //   y=28   nom 2-qator
    //   y=52   narx          (shrift 3, x2/y2 → 32x48)
    //   y=106  barcode       (balandlik 62)
    //   y=172  barcode raqami(shrift 1, 8x12)
    // Jami ~184 < 240 — pastda zaxira bor (etiketka biroz siljisa ham kesilmaydi).
    const NAME_FONT = '2', NAME_MUL = 1;
    const CODE_FONT = '1', CODE_MUL = 1;
    const Y_NAME = 6;
    const Y_NAME_STEP = charHeight(NAME_FONT, NAME_MUL) + 2;
    const Y_PRICE = 52;
    const Y_BARCODE = 106;
    const BARCODE_H = 62;
    const Y_CODE_TEXT = Y_BARCODE + BARCODE_H + 4;

    const parts = [];

    // ── Printer sozlamasi — bir marta, hamma etiketkaga amal qiladi ──
    parts.push(cmd(`SIZE ${widthMm} mm, ${heightMm} mm`));
    parts.push(cmd(`GAP ${gapMm} mm, 0 mm`));
    parts.push(cmd(`DENSITY ${density}`));
    parts.push(cmd(`SPEED ${speed}`));
    parts.push(cmd('DIRECTION 1'));       // 1 = qog'oz chiqish yo'nalishi (matn to'g'ri o'qiladi)
    parts.push(cmd('REFERENCE 0,0'));

    for (const raw of list) {
        const it = raw || {};
        const copies = Math.max(1, Number(it.qty) || Number(o.copies) || 1);

        parts.push(cmd('CLS'));

        // ── Nom (2 qatorgacha) ──
        const nameLines = splitName(it.name || '', usable, NAME_FONT, NAME_MUL, 2);
        nameLines.forEach((ln, i) => {
            const x = centerX(ln.length, W, NAME_FONT, NAME_MUL);
            const y = Y_NAME + i * Y_NAME_STEP;
            parts.push(cmd(`TEXT ${x},${y},"${NAME_FONT}",0,${NAME_MUL},${NAME_MUL},"${escapeTspl(ln)}"`));
        });

        // ── Narx (katta, markazda) — son bo'lsa money(), matn bo'lsa o'zi ──
        // Valyuta FAQAT songa qo'shiladi ("Aksiya so'm" ma'nosiz bo'lardi).
        const rawPrice = it.price;
        const isNumeric = typeof rawPrice === 'number' || /^\d+(\.\d+)?$/.test(String(rawPrice || ''));
        let priceTxt = isNumeric ? money(rawPrice) : sanitize(rawPrice || '');
        if (priceTxt && isNumeric && currency) priceTxt += ' ' + currency;
        if (priceTxt) {
            // Qirqish emas — sig'adigan eng katta shriftni tanlaymiz.
            const pf = pickPriceFont(priceTxt, usable);
            priceTxt = fitText(priceTxt, usable, pf.font, pf.mul);
            const px = centerX(priceTxt.length, W, pf.font, pf.mul);
            parts.push(cmd(`TEXT ${px},${Y_PRICE},"${pf.font}",0,${pf.mul},${pf.mul},"${escapeTspl(priceTxt)}"`));
        }

        // ── Barcode — printer o'zi chizadi (rasm yubormaymiz) ──
        const code = sanitize(it.barcode || '');
        if (code) {
            const type = barcodeType(code);
            // narrow=2 → EAN-13 kengligi 190 nuqta (304 ga bemalol sig'adi).
            // CODE128 uzun bo'lsa narrow=1 ga tushiramiz, aks holda chetdan chiqadi.
            let narrow = 2;
            if (barcodeWidthDots(code, type, narrow) > usable) narrow = 1;
            const bw = barcodeWidthDots(code, type, narrow);
            const bx = Math.max(M, Math.round((W - bw) / 2));
            // BARCODE x,y,"tur",balandlik,human_readable,burilish,narrow,wide,"kod"
            // human_readable=0 — raqamni O'ZIMIZ pastda chizamiz (shrift nazorati uchun).
            parts.push(cmd(`BARCODE ${bx},${Y_BARCODE},"${type}",${BARCODE_H},0,0,${narrow},${narrow * 2},"${escapeTspl(code)}"`));

            const codeTxt = fitText(code, usable, CODE_FONT, CODE_MUL);
            const cx = centerX(codeTxt.length, W, CODE_FONT, CODE_MUL);
            parts.push(cmd(`TEXT ${cx},${Y_CODE_TEXT},"${CODE_FONT}",0,${CODE_MUL},${CODE_MUL},"${escapeTspl(codeTxt)}"`));
        }

        // PRINT m,n → m ta to'plam, har biri n nusxa. Bizda 1 to'plam × copies.
        parts.push(cmd(`PRINT 1,${copies}`));
    }

    // TSPL ASCII — latin1 kodlash (sanitize'dan keyin baribir ASCII qolgan).
    return Buffer.from(parts.join(''), 'latin1');
}

// Sozlama sahifasidagi "Test etiketka" uchun namuna (escpos-builder.js
// TEST_STRUCTURED bilan bir xil maqsad — printer ulanishini tekshirish).
const TEST_ITEMS = [
    { name: 'XENORA TEST ETIKETKA', price: 150000, barcode: '2012345678909', qty: 1 },
];

function buildTestLabelBytes(opts) {
    return buildLabelBytes(TEST_ITEMS, opts);
}

module.exports = {
    DOTS_PER_MM_203, FONT_METRICS,
    dotsPerMm, mmToDots, fontMetrics, charWidth, charHeight,
    sanitize, escapeTspl, money, fitText, splitName, centerX,
    barcodeType, barcodeWidthDots,
    buildLabelBytes, buildTestLabelBytes, TEST_ITEMS,
};
