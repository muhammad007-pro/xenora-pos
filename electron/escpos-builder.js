/**
 * ESC/POS yadro — chek baytlarini generatsiya qiladi (LAN transport uchun).
 *
 * NAMUNA: backend/services/escpos_service.py (Python, ISBOTLANGAN — o'sha
 * fayldagi kenglik/sanitizatsiya/pul formatlash mantig'i shu yerga JS'ga
 * ko'chirildi). Bu fayl HECH QAYERGA ULANMAYDI — faqat structured ma'lumotdan
 * bayt yasaydi (sof funksiyalar, Electron/BrowserWindow'ga bog'liq emas —
 * shuning uchun oddiy `node` bilan ham sinash mumkin). Ulanish (TCP socket)
 * electron/main.js da alohida (`_sendRawTcp`).
 *
 * 80mm termal = 48 belgi, 58mm (va UI'dagi "57mm") = 32 belgi bir qatorda.
 */
'use strict';

// Qog'oz kengligi (mm) -> bir qatordagi belgilar soni (Font A, standart ESC/POS).
// 57 ham qo'shilgan: admin.html'dagi "Qog'oz kengligi" tanlovida qiymat 57
// ("57mm (kichik)") ishlatiladi — bu XP-Q80AS kabi 58mm rulon bilan bir xil
// termal klass, shuning uchun 32 belgiga moslanadi (48 emas).
const CHARS_BY_WIDTH = { 57: 32, 58: 32, 80: 48 };

function charsForWidth(widthMm) {
    return CHARS_BY_WIDTH[Number(widthMm)] || 48;
}

// Termal printer kod-sahifasi qo'llab-quvvatlamaydigan belgilarni almashtirish
// (Python escpos_service._sanitize bilan BIR XIL jadval). Bundan keyin qolgan
// matn (o'zbek lotin alifbosi) ASCII/Latin-1 doirasida — kodlash muammosiz.
const SANITIZE_MAP = {
    'ʻ': "'", 'ʼ': "'", '‘': "'", '’': "'",
    '“': '"', '”': '"', '–': '-', '—': '-',
    '…': '...', '•': '*', ' ': ' ',
};

function sanitize(s) {
    if (s === null || s === undefined) return '';
    let out = String(s);
    for (const [a, b] of Object.entries(SANITIZE_MAP)) {
        out = out.split(a).join(b);
    }
    return out;
}

function money(n) {
    const v = Math.round(Number(n) || 0);
    return String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

// Uzun matnni kenglik bo'yicha qatorlarga bo'lish (so'z butunligicha ko'chadi).
function wrapText(text, width) {
    const s = sanitize(text);
    const words = s.split(/\s+/).filter(Boolean);
    const lines = [];
    let cur = '';
    for (const w of words) {
        const next = cur ? cur + ' ' + w : w;
        if (next.length <= width) {
            cur = next;
        } else {
            if (cur) lines.push(cur);
            cur = w.slice(0, width);
        }
    }
    if (cur) lines.push(cur);
    return lines.length ? lines : [''];
}

// Chap va o'ng ustun — bitta qatorda, kenglik bo'yicha tekislangan.
function row(left, right, width) {
    let l = sanitize(left);
    let r = sanitize(right);
    let space = width - l.length - r.length;
    if (space < 1) {
        l = l.slice(0, Math.max(0, width - r.length - 1));
        space = Math.max(1, width - l.length - r.length);
    }
    return l + ' '.repeat(space) + r;
}

// ── ESC/POS buyruq baytlari ──────────────────────────────────────────────────
const ESC = 0x1b, GS = 0x1d;
const CMD = {
    INIT:        Buffer.from([ESC, 0x40]),                    // ESC @  — boshlang'ich holat
    ALIGN_LEFT:  Buffer.from([ESC, 0x61, 0x00]),
    ALIGN_CENTER: Buffer.from([ESC, 0x61, 0x01]),
    BOLD_ON:     Buffer.from([ESC, 0x45, 0x01]),
    BOLD_OFF:    Buffer.from([ESC, 0x45, 0x00]),
    DOUBLE_ON:   Buffer.from([GS, 0x21, 0x11]),                // GS ! 0x11 — 2x kenglik+balandlik
    DOUBLE_OFF:  Buffer.from([GS, 0x21, 0x00]),
    CUT:         Buffer.from([GS, 0x56, 0x00]),                // GS V 0 — to'liq kesish
    FEED:        Buffer.from([0x0a, 0x0a, 0x0a]),
};
// ESC p m t1 t2 — pul qutisi (cash drawer) "kick" signali. m=0 → pin 2 (eng keng
// tarqalgan drawer ulanishi). t1/t2 — signal davomiyligi (~impuls uzunligi).
const DRAWER_KICK = Buffer.from([ESC, 0x70, 0x00, 25, 250]);

function textLine(s) {
    return Buffer.concat([Buffer.from(sanitize(s) + '\n', 'latin1')]);
}
function line(width, ch) {
    return textLine(ch.repeat(width));
}

/**
 * Structured chek ma'lumotidan ESC/POS bayt yasaydi.
 *
 * structured: {
 *   storeName, addressLines: string[], meta (masalan "Chek #17 | Stol: #3"),
 *   rows: [{name, qty, price}], totals: [{label, value, bold}],
 *   footer, fiscalNumber?
 * }
 * opts: { openDrawer?: bool }
 */
function buildReceiptBytes(structured, widthMm, opts) {
    const s = structured || {};
    const o = opts || {};
    const w = charsForWidth(widthMm);
    const parts = [CMD.INIT];

    // ── Sarlavha: do'kon nomi (markaz, katta+qalin) ──
    parts.push(CMD.ALIGN_CENTER, CMD.BOLD_ON, CMD.DOUBLE_ON);
    parts.push(textLine(s.storeName || "Do'kon"));
    parts.push(CMD.DOUBLE_OFF, CMD.BOLD_OFF);
    for (const addr of (s.addressLines || [])) {
        for (const ln of wrapText(addr, w)) parts.push(textLine(ln));
    }
    parts.push(line(w, '='));

    // ── Meta: "Chek #.. | Stol: #.." ──
    parts.push(CMD.ALIGN_LEFT);
    if (s.meta) {
        for (const ln of wrapText(s.meta, w)) parts.push(textLine(ln));
    }
    parts.push(line(w, '-'));

    // ── Mahsulotlar ──
    parts.push(textLine(row('Mahsulot', 'Summa', w)));
    parts.push(line(w, '-'));
    for (const it of (s.rows || [])) {
        for (const ln of wrapText(it.name || '', w)) parts.push(textLine(ln));
        const qty = it.qty != null && it.qty !== '' ? it.qty : '1';
        parts.push(textLine(row(`  ${qty} dona`, it.price || '', w)));
    }
    parts.push(line(w, '-'));

    // ── Jami / soliq / chegirma / umumiy ──
    for (const t of (s.totals || [])) {
        if (t.bold) {
            parts.push(CMD.BOLD_ON);
            parts.push(textLine(row(t.label, t.value, w)));
            parts.push(CMD.BOLD_OFF);
        } else {
            parts.push(textLine(row(t.label, t.value, w)));
        }
    }
    parts.push(line(w, '='));

    // ── Fiskal (bor bo'lsa — faqat matn, QR bosqichi keyinroq) ──
    if (s.fiscalNumber) {
        parts.push(CMD.ALIGN_CENTER, CMD.BOLD_ON);
        parts.push(textLine('FISKAL CHEK'));
        parts.push(CMD.BOLD_OFF, CMD.ALIGN_LEFT);
        parts.push(textLine(row('Fiskal No:', String(s.fiscalNumber), w)));
        parts.push(line(w, '='));
    }

    // ── Footer ──
    parts.push(CMD.ALIGN_CENTER);
    for (const ln of wrapText(s.footer || 'Xarid uchun rahmat!', w)) parts.push(textLine(ln));
    parts.push(CMD.ALIGN_LEFT, CMD.FEED);

    // Pul qutisi — kesishdan OLDIN (chek uzilib chiqqach, tortma ochiladi).
    if (o.openDrawer) parts.push(DRAWER_KICK);

    parts.push(CMD.CUT);
    return Buffer.concat(parts);
}

// Sozlama sahifasidagi "Test chek" uchun namuna (Python TEST_DATA bilan mos).
const TEST_STRUCTURED = {
    storeName: 'XENORA TEST',
    addressLines: ["Toshkent sh., Test ko'chasi 1"],
    meta: 'Chek #TEST-001',
    rows: [
        { name: 'Kofe Amerikano', qty: '2', price: money(30000) },
        { name: 'Sendvich (uzun nom misoli uchun tekshirish)', qty: '1', price: money(25000) },
    ],
    totals: [
        { label: 'Jami:', value: money(55000), bold: false },
        { label: 'Chegirma:', value: '-' + money(5000), bold: false },
        { label: 'UMUMIY:', value: money(50000) + ' UZS', bold: true },
        { label: "To'lov:", value: 'Naqd', bold: false },
    ],
    footer: 'Bu TEST CHEK — LAN printer tekshiruvi',
};

function buildTestReceiptBytes(widthMm, opts) {
    return buildReceiptBytes(TEST_STRUCTURED, widthMm, opts);
}

module.exports = {
    charsForWidth, sanitize, wrapText, row, money,
    CMD, DRAWER_KICK,
    buildReceiptBytes, buildTestReceiptBytes, TEST_STRUCTURED,
};
