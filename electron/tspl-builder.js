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

// ── Kenglik xavfsizlik koeffitsienti ─────────────────────────────────────────
// JONLI SINOVDA (XP-365B, 40x30mm) aniqlandi: nominal hisob bo'yicha 252 nuqta
// (304 dan kichik) bo'lgan matn O'NGDAN KESILDI — x=286 da tugardi, printer
// esa undan oldinroq to'xtagan. Sabab ikkitasidan biri (tashqaridan farqlab
// bo'lmaydi): firmware shrift kengligi nominal jadvaldan katta, YOKI bosiladigan
// maydon 40mm dan tor (kalla siljishi / o'ng chekka).
// Ikkalasida ham yechim bir xil: SIG'DIRISH hisobida belgini kengroq deb olamiz.
// DIQQAT: bu faqat "sig'adimi / nechta belgi" QARORI uchun. Markazlashtirish
// HAQIQIY kenglik bilan hisoblanadi — aks holda matn chapga qiyshayardi.
const FIT_SAFETY = 1.2;

function fitWidth(font, xMul) {
    return charWidth(font, xMul) * FIT_SAFETY;
}

function maxCharsFor(maxDots, font, xMul) {
    return Math.max(1, Math.floor(maxDots / fitWidth(font, xMul)));
}

// ── Balandlik ham nominal jadvaldan KATTA ────────────────────────────────────
// JONLI SINOV 3: hisobda tepa/past 14/14 chiqardi, amalda esa mazmun yuqoriga
// siljib, barcode ostidagi raqam etiketka chekkasiga TEGDI. Formula to'g'ri edi
// (oxirgi element balandligi, barcode balandligi va uchala bo'shliq hisobga
// olingan) — muammo kenglikdagi bilan AYNI: nominal shrift o'lchami haqiqiydan
// kichik. 1.2 koeffitsient bilan blok 212 emas, ~229 bo'ladi va past chekka
// 243 ga chiqadi (limit 240) — kuzatilgan holat aynan shu.
//
// Bu yerda koeffitsient BLOK HISOBIGA ham, y SILJISHIGA ham qo'llanadi:
// aks holda nom qatorlari bir-biriga kirib ketadi.
// Barcode balandligiga TEGMAYDI — uni printer aniq chizadi.
const V_SAFETY = 1.2;

function vHeight(font, yMul) {
    return Math.ceil(charHeight(font, yMul) * V_SAFETY);
}

// Matnni berilgan NUQTA kengligiga sig'dirish (belgi soniga aylantirib qirqadi).
function fitText(text, maxDots, font, xMul) {
    const s = sanitize(text);
    const maxChars = maxCharsFor(maxDots, font, xMul);
    if (s.length <= maxChars) return s;
    if (maxChars <= 3) return s.slice(0, maxChars);
    return s.slice(0, maxChars - 3) + '...';
}

// Uzun nomni 2 qatorga bo'lish (so'z butunligicha ko'chadi; oxirgi qator
// sig'masa "..." bilan qirqiladi). Etiketka kichik — 2 qatordan ko'pi sig'maydi.
function splitName(text, maxDots, font, xMul, maxLines) {
    const s = sanitize(text);
    const maxChars = maxCharsFor(maxDots, font, xMul);
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
        if (len <= maxCharsFor(maxDots, f.font, f.mul)) return f;
    }
    return PRICE_FONT_LADDER[PRICE_FONT_LADDER.length - 1];
}

// ── Mahsulot nomi — HECH QACHON KESILMASIN ───────────────────────────────────
// Etiketkada nom eng muhim ma'lumot: kesilgan nom yaroqsiz. Shuning uchun
// ketma-ket urinamiz: katta shrift 1 qator → katta shrift 2 qator →
// kichik shrift 1 qator → kichik shrift 2 qator. Faqat shundan keyin "..."
// (bu holat 2 qator × ~34 belgidan uzun nomda bo'ladi).
const NAME_FONT_LADDER = [
    { font: '2', mul: 1 },   // 12x20 — asosiy, o'qish qulay
    { font: '1', mul: 1 },   // 8x12  — juda uzun nomlar uchun
];

function fitName(text, maxDots, maxLines) {
    const s = sanitize(text);
    const limit = Math.max(1, Number(maxLines) || 2);

    for (const f of NAME_FONT_LADDER) {
        const maxChars = maxCharsFor(maxDots, f.font, f.mul);
        if (s.length <= maxChars) {
            return { font: f.font, mul: f.mul, lines: [s] };
        }
        const lines = splitName(s, maxDots, f.font, f.mul, limit);
        // splitName sig'magan qoldiqni "..." bilan belgilaydi — "..." bo'lmasa
        // demak nom TO'LIQ sig'di, shu shriftni olamiz.
        if (!lines.some((l) => l.endsWith('...'))) {
            return { font: f.font, mul: f.mul, lines };
        }
    }
    // Oxirgi chora: eng kichik shrift, 2 qator, qoldiq "..." bilan.
    const last = NAME_FONT_LADDER[NAME_FONT_LADDER.length - 1];
    return {
        font: last.font, mul: last.mul,
        lines: splitName(s, maxDots, last.font, last.mul, limit),
    };
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
    // Chetki bo'sh joy: 8 → 16 nuqta (2mm). Jonli sinovda o'ng chekka
    // kesgani uchun oshirildi (FIT_SAFETY bilan birga ishlaydi).
    const M = 16;
    const usable = W - M * 2;             // 40mm da 288 nuqta

    // ── Vertikal joylashuv — MAZMUN ETIKETKA O'RTASIDA ───────────────────────
    // Ilgari y=4 dan boshlanardi va pastda ~46 nuqta bo'sh qolardi (yorliq
    // "yuqoriga yopishgan" ko'rinardi). Endi butun blok balandligi hisoblanib,
    // (H - blok) / 2 dan boshlanadi — tepa va past teng.
    //
    // Blok: nom → narx → barcode → raqam. Har elementning balandligi TANLANGAN
    // shriftga bog'liq (nom 1 yoki 2 qator, narx avto-shrift), shuning uchun
    // qattiq y qiymatlari emas, YIG'INDI hisoblanadi.
    const CODE_FONT = '2', CODE_MUL = 1;  // shrift 1 → 2: raqam o'qish uchun juda kichik edi
    // Bo'shliqlar qisqartirildi (8/10/4 → 6/8/4): V_SAFETY bilan blok kattaroq
    // hisoblanadi, ko'rinadigan chetki joy qolishi uchun o'rin kerak.
    const GAP_NAME_PRICE = 6;
    const GAP_PRICE_BARCODE = 8;
    const GAP_BARCODE_CODE = 4;
    const MIN_V_MARGIN = 12;              // tepa/pastdagi eng kam bo'sh joy (~1.5mm)
    // 104 → 88 (~11mm): 104 bilan V_SAFETY hisobida blok etiketkadan chiqib
    // ketardi. Kenglikni oshira olmaganimiz uchun balandlik muhim, lekin
    // chetga tegib turgan yorliqdan ko'ra biroz pastroq barcode afzal.
    const BARCODE_H_TARGET = 88;
    const BARCODE_H_MIN = 56;

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

        // ── 1-BOSQICH: elementlarni TAYYORLAB, balandliklarini hisoblaymiz ──
        // (hali chizmaymiz — avval blok balandligi kerak, markazlashtirish uchun)

        // Nom — shrift/qator soni AVTOMATIK, kesilmasin (fitName)
        const nf = fitName(it.name || '', usable, 2);
        const nameLineH = vHeight(nf.font, nf.mul);
        const nameStep  = nameLineH + 2;
        const nameH = nf.lines.length * nameLineH + (nf.lines.length - 1) * 2;

        // Narx — son bo'lsa money(), matn bo'lsa o'zi. Valyuta FAQAT songa
        // qo'shiladi ("Aksiya so'm" ma'nosiz bo'lardi). Qirqish emas —
        // sig'adigan eng katta shrift tanlanadi.
        const rawPrice = it.price;
        const isNumeric = typeof rawPrice === 'number' || /^\d+(\.\d+)?$/.test(String(rawPrice || ''));
        let priceTxt = isNumeric ? money(rawPrice) : sanitize(rawPrice || '');
        if (priceTxt && isNumeric && currency) priceTxt += ' ' + currency;
        let pf = null, priceH = 0;
        if (priceTxt) {
            pf = pickPriceFont(priceTxt, usable);
            priceTxt = fitText(priceTxt, usable, pf.font, pf.mul);
            priceH = vHeight(pf.font, pf.mul);
        }

        // Barcode — printer o'zi chizadi (rasm yubormaymiz).
        // ⚠️ KENGLIK O'ZGARTIRILMAYDI: EAN-13 = 95 modul × narrow, oraliq qiymat
        // YO'Q. narrow=2 → 190 nuqta (x=65..255, JONLI SINOVDA toza chiqqan).
        // narrow=3 → 285 nuqta (x=18..303) — jonli sinovda x=286 KESILGAN,
        // ya'ni 303 kafolatli kesiladi. Shu sabab kenglik o'rniga BALANDLIK
        // oshiriladi (skaner uchun balandlik ham muhim: ko'proq skan chizig'i).
        const code = sanitize(it.barcode || '');
        let type = null, narrow = 2, bw = 0, codeTxt = '', codeH = 0;
        let barcodeH = 0;
        if (code) {
            type = barcodeType(code);
            if (barcodeWidthDots(code, type, narrow) > usable) narrow = 1;
            bw = barcodeWidthDots(code, type, narrow);
            codeTxt = fitText(code, usable, CODE_FONT, CODE_MUL);
            codeH = vHeight(CODE_FONT, CODE_MUL);
            barcodeH = BARCODE_H_TARGET;
        }

        // ── 2-BOSQICH: blok balandligi va markazlashtirish ──
        const gaps = (priceTxt ? GAP_NAME_PRICE : 0)
                   + (code ? GAP_PRICE_BARCODE + GAP_BARCODE_CODE : 0);
        const fixedH = nameH + priceH + codeH + gaps;
        // Balandlik sig'masa barcode'ni qisqartiramiz (matn hech qachon kesilmaydi).
        const maxBarcodeH = H - 2 * MIN_V_MARGIN - fixedH;
        if (code && barcodeH > maxBarcodeH) {
            barcodeH = Math.max(BARCODE_H_MIN, maxBarcodeH);
        }
        const blockH = fixedH + barcodeH;
        let y = Math.max(MIN_V_MARGIN, Math.round((H - blockH) / 2));

        // ── 3-BOSQICH: chizish (hamma element BIR XIL markaz o'qida) ──
        nf.lines.forEach((ln, i) => {
            const x = centerX(ln.length, W, nf.font, nf.mul);
            parts.push(cmd(`TEXT ${x},${y + i * nameStep},"${nf.font}",0,${nf.mul},${nf.mul},"${escapeTspl(ln)}"`));
        });
        y += nameH;

        if (priceTxt) {
            y += GAP_NAME_PRICE;
            const px = centerX(priceTxt.length, W, pf.font, pf.mul);
            parts.push(cmd(`TEXT ${px},${y},"${pf.font}",0,${pf.mul},${pf.mul},"${escapeTspl(priceTxt)}"`));
            y += priceH;
        }

        if (code) {
            y += GAP_PRICE_BARCODE;
            const bx = Math.max(M, Math.round((W - bw) / 2));
            // BARCODE x,y,"tur",balandlik,human_readable,burilish,narrow,wide,"kod"
            // human_readable=0 — raqamni O'ZIMIZ pastda chizamiz (shrift nazorati uchun).
            parts.push(cmd(`BARCODE ${bx},${y},"${type}",${barcodeH},0,0,${narrow},${narrow * 2},"${escapeTspl(code)}"`));
            y += barcodeH + GAP_BARCODE_CODE;

            const cx = centerX(codeTxt.length, W, CODE_FONT, CODE_MUL);
            parts.push(cmd(`TEXT ${cx},${y},"${CODE_FONT}",0,${CODE_MUL},${CODE_MUL},"${escapeTspl(codeTxt)}"`));
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
    FIT_SAFETY, V_SAFETY, fitWidth, vHeight, maxCharsFor, fitName, pickPriceFont,
    buildLabelBytes, buildTestLabelBytes, TEST_ITEMS,
};
