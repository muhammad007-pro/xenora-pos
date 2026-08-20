/**
 * XENORA — Chek LOKAL chop etish (silent print) qatlami.
 *
 * NEGA: Backend SERVERda ishlaydi (xenora.uz), XP-58 esa DO'KON
 * kompyuteriga USB orqali ulangan. Server do'kondagi USB printerga yeta
 * olmaydi. Shu sabab chek MIJOZ tomonda (Electron) — yashirin oynada
 * yuklanib — LOKAL printerga silent (dialogsiz) yuboriladi.
 *
 *   Electron → window.electronAPI.printReceipt({html, deviceName})  (silent)
 *   Brauzer  → yashirin iframe ichida window.print()                (dialog)
 *
 * Bu modul HECH QANDAY global o'zgaruvchi yaratmaydi — faqat export qiladi.
 */

// Electron server rejimida printReceipt IPC mavjudmi?
export function isElectron() {
  return !!(window.electronAPI && window.electronAPI.isElectron && window.electronAPI.printReceipt);
}

// ── 58mm termal chek uslubi (qora matn, oq fon) ────────────────────────────────
// Ham buildReceipt58() chiqishi, ham POS #receiptBody innerHTML (.receipt-* / .rt-row)
// bir xil renderlansin. CSS o'zgaruvchilari (var(--...)) bu yangi hujjatda
// aniqlanmagan → majburan qora rang.
//
// KENGLIK: kontent 48mm (58mm rolik) — XP-58 termal printerning BOSILADIGAN zonasi
// ~48mm. 54mm qilinsa o'ng chetdagi NARX ustuni bosilmaydigan zonaga tushib KESILADI
// ("505,000"→"505"). Shu sabab 48mm + jadval table-layout:fixed (uzun nom narxni
// o'ngga surib yubormasin, narx ustuni doim to'liq sig'sin).
//
// TAYANCH: konteyner CHAPGA tayanadi (margin:0 — `auto`/markaz EMAS). `margin:0 auto`
// bo'lsa 48mm kontent 58mm qog'oz o'rtasiga markazlashib, chapda ~5mm bo'sh joy
// qoladi, o'ng cheti esa printerning chapdan boshlanuvchi 48mm bosiladigan zonasidan
// chiqib KESILADI ("UZS"→"U2", "CASH"→"CAS"). Chapga tayansa — matn 0mm dan boshlanib
// butun 48mm ishlatiladi, narx o'ngda to'liq sig'adi. Chap/o'ng padding minimal (0.5mm).
//
// SHRIFT: bola elementlar `em` (base'ga nisbatan) — "Shrift o'lchami" sozlamasi
// (Kichik/Normal/Katta → 11/13/15px) butun chekni proporsional kattalashtiradi.
const FONT_PX = { small: 11, normal: 13, large: 15 };
function _fontPx(size) {
  if (typeof size === 'number' && size > 0) return size;
  return FONT_PX[size] || FONT_PX.normal;
}

function buildCss(fontPx) {
  return `
  *{margin:0;padding:0;box-sizing:border-box}
  @page{margin:0}
  html,body{background:#fff;margin:0;padding:0;text-align:left}
  /* CHAPGA tayanadi: margin:0 (auto EMAS) → chapda bo'sh joy yo'q, narx o'ngda kesilmaydi.
     padding chap/o'ng 0.5mm → butun 48mm bosiladigan zona matn uchun ishlatiladi. */
  /* font-weight:600 — termal printer ingichka shriftni XIRA bosadi; butun chek
     to'qroq (bold) → mahsulot nomi/narx aniq chiqadi. Shrift o'lchami saqlanadi. */
  .r58{width:48mm;max-width:48mm;margin:0;padding:2mm 0.5mm;
       font-family:'Courier New',monospace;font-size:${fontPx}px;font-weight:600;line-height:1.35;color:#000}
  .r58, .r58 *{color:#000 !important;background:transparent !important;border-color:#000 !important}
  .r58 h4{font-size:1.2em;font-weight:700;margin-bottom:2px}
  .r58 small{font-size:0.8em}
  .r58 img{max-width:100%;display:block;margin:3px auto}
  .receipt-center{text-align:center;margin-bottom:6px;padding-bottom:6px;border-bottom:1px dashed #000}
  .receipt-center p{font-size:0.85em;line-height:1.5}
  /* table-layout:fixed → nom uzun bo'lsa keyingi qatorga o'tadi (narxni surmaydi) */
  .receipt-table{width:100%;border-collapse:collapse;margin:4px 0;table-layout:fixed}
  .receipt-table th,.receipt-table td{padding:1px 2px;vertical-align:top;overflow:hidden}
  .receipt-table th{text-align:left;font-size:0.85em;font-weight:700;border-bottom:1px solid #000}
  /* mahsulot nomi + soni + narx — BOLD (termal aniq, xira emas) */
  .receipt-table td{font-size:0.85em;font-weight:700;word-break:break-word;overflow-wrap:anywhere}
  /* ── MAHSULOT BLOKI (v1.8.7) — ESC/POS bilan BIR XIL joylashuv ──────────────
     1-qator: nom (to'liq kenglik, uzun bo'lsa o'raladi)
     2-qator: "11 x 5 000" chapda,  summa o'ngda
     NEGA JADVAL EMAS, GRID: 48mm ga uchala ustunni BIR qatorga tiqish uchun
     narx ustuni torayadi va katta summa KESILADI (o'lchovda tasdiqlangan:
     29% da "1 500 000" klip bo'ldi). "1fr auto" da narx ustuni O'ZI kerakli
     kenglikni oladi — hech qachon kesilmaydi, nom esa qolganini oladi.
     Grid yana bo'shliqqa (HTML'dagi satr ko'chirish) SEZGIR EMAS — pos.js va
     receipt-print.js turlicha yozilgan, inline-block bo'lsa buzilardi.
     ⚠️ 3 ta <td> SAQLANADI: LAN yo'li DOM'dan tds[1]/tds[2] ni o'qiydi
     (main.js _RECEIPT_EXTRACT_JS) — tuzilma o'zgarsa eski .exe buziladi.
     ⚠️ Bu izoh JS template literal ICHIDA — backtick YOZMANG (literalni uzadi). */
  .receipt-table,.receipt-table thead,.receipt-table tbody{display:block;width:100%}
  .receipt-table thead tr,.receipt-table tbody tr{display:grid;grid-template-columns:1fr auto;column-gap:4px}
  .receipt-table thead th:nth-child(2){display:none}         /* "Soni" sarlavhasi keraksiz */
  .receipt-table thead th:nth-child(1){grid-column:1}
  .receipt-table thead th:nth-child(3){grid-column:2;text-align:right}
  /* min-width:0 — GRID TUZOG'I: "1fr" ustunining standart eng kichik kengligi
     "auto" (min-content), shuning uchun uzun "1000 x 1 500 000" qisqarmay,
     narx ustunini siqib KESIB qo'yardi (o'lchovda ko'rindi). 0 bo'lsa — narx
     kerakli joyni to'liq oladi, miqdor esa qolganiga o'raladi. */
  .receipt-table tbody td{min-width:0}
  /* ⚠️ :has(td:nth-child(3)) — 2 USTUNLI jadvallarni BUZMASLIK uchun.
     report.html (kunlik hisobot) qatorlari 2 katakli: "nom | qiymat".
     Ular uchun standart "1fr auto" AYNAN kerakli natija (chapda nom, o'ngda
     qiymat). Faqat 3 katakli MAHSULOT qatorlari 2 qatorli blokka aylanadi. */
  .receipt-table tbody tr:has(td:nth-child(3)) td:nth-child(1){grid-column:1/-1}
  .receipt-table tbody tr:has(td:nth-child(3)) td:nth-child(2){grid-column:1;text-align:left;padding-left:8px}
  .receipt-table tbody td:nth-child(3){grid-column:2;text-align:right;white-space:nowrap}
  .receipt-table tbody td:last-child{text-align:right}
  /* MAHSULOTLAR ORASIDA AJRATUVCHI (mijoz talabi): ilgari qatorlar bir-biriga
     yopishib ketardi. Sarlavha chizig'i SOLID, mahsulot orasidagi DASHED —
     jadval tugagandek ko'rinmasin. Oxirgisidan keyin yo'q (pastda totals bor). */
  .receipt-table tbody tr:not(:last-child){border-bottom:1px dashed #000;padding-bottom:3px;margin-bottom:3px}
  .receipt-totals{border-top:1px dashed #000;padding-top:4px;margin-top:4px}
  .rt-row{display:flex;justify-content:space-between;gap:6px;font-size:1em;padding:1px 0}
  .rt-row span:last-child{text-align:right}
  .rt-row.bold{font-weight:700;font-size:1.1em;border-top:1px solid #000;margin-top:3px;padding-top:3px}
  .receipt-footer{text-align:center;border-top:1px dashed #000;margin-top:5px;padding-top:5px;font-size:0.85em;line-height:1.6}
`;
}

function wrapDoc(innerHTML, title, opts) {
  const css = buildCss(_fontPx((opts || {}).fontSize));
  return `<!DOCTYPE html><html lang="uz"><head><meta charset="UTF-8">`
    + `<title>${title || 'Chek'}</title><style>${css}</style></head>`
    + `<body><div class="r58">${innerHTML}</div></body></html>`;
}

// Brauzer (PWA) fallback — yashirin iframe ichida chop etish (butun sahifa emas).
function _printViaIframe(html) {
  return new Promise((resolve) => {
    const ifr = document.createElement('iframe');
    Object.assign(ifr.style, {
      position: 'fixed', right: '0', bottom: '0', width: '0', height: '0',
      border: '0', visibility: 'hidden',
    });
    let done = false;
    const finish = (res) => { if (done) return; done = true; try { ifr.remove(); } catch {} resolve(res); };
    ifr.onload = () => {
      try {
        ifr.contentWindow.focus();
        ifr.contentWindow.print();
      } catch (e) { finish({ ok: false, error: e.message, browser: true }); return; }
      setTimeout(() => finish({ ok: true, browser: true }), 1200);
    };
    document.body.appendChild(ifr);
    try {
      const doc = ifr.contentWindow.document;
      doc.open(); doc.write(html); doc.close();
    } catch (e) { finish({ ok: false, error: e.message, browser: true }); }
  });
}

/**
 * Chek innerHTML (58mm) ni LOKAL printerga chiqarish.
 * @returns {Promise<{ok:boolean, error?:string, browser?:boolean}>}
 *   ok:true  — chiqarildi. browser:true bo'lsa brauzer dialogi ishlatildi.
 *   ok:false — HAQIQIY xato (jimgina "yuborildi" demaymiz).
 */
export async function printReceiptHTML(innerHTML, opts = {}) {
  if (!innerHTML || !String(innerHTML).trim()) return { ok: false, error: 'Chek bo\'sh' };
  // opts.fontSize: 'small'|'normal'|'large' (yoki px) — "Shrift o'lchami" sozlamasi
  const html = wrapDoc(innerHTML, opts.title, { fontSize: opts.fontSize });
  if (isElectron()) {
    try {
      const api = window.electronAPI;
      // Markaziy print servis (B1): printType (usb/lan/qr) transportni tanlaydi.
      // deviceName bo'sh bo'lsa main.js OS default printerni ishlatadi.
      // printType bo'sh → main.js 'usb' (SumatraPDF) → chek natijasi o'zgarmaydi.
      const payload = {
        html,
        deviceName: (opts.deviceName || '').trim(),
        printType: opts.printType || 'usb',
        printerIp: opts.printerIp || null,
        printerPort: opts.printerPort || null,
        // LAN 2-bosqich: qog'oz kengligi (58/80mm — ESC/POS qator belgilar soni
        // uchun) va pul qutisi (cash drawer) signali. USB (SumatraPDF) yo'liga
        // ta'sir qilmaydi — faqat lanTransport shu ikkalasini o'qiydi.
        paperWidth: opts.paperWidth || null,
        openDrawer: !!opts.openDrawer,
      };
      // printDocument mavjud bo'lsa markaziy yo'l; bo'lmasa (eski preload) — printReceipt.
      const res = api.printDocument
        ? await api.printDocument(payload)
        : await api.printReceipt(payload);
      return res && typeof res === 'object' ? res : { ok: false, error: 'Printerdan javob yo\'q' };
    } catch (e) {
      return { ok: false, error: e.message || 'Electron print xato' };
    }
  }
  return _printViaIframe(html);
}

// ── Yordamchi: pul + HTML-escape ───────────────────────────────────────────────
function _money(n) {
  const v = Math.round(Number(n) || 0);
  return String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}
function _esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const _PAY = { cash: 'Naqd', card: 'Karta', click: 'Click', payme: 'Payme', credit: 'Nasiya', transfer: "O'tkazma", room_charge: 'Xona hisobi' };

// ── "Soni" ustuni: miqdor × BIRLIK narx ──────────────────────────────────────
// v1.8.7, mijoz talabi: chekda "11 dona ... 55 000" edi — xaridor qaysi tovar
// QANCHADAN olinganini bilmasdi. Endi "11 x 5 000 ... 55 000".
//
// ⚠️ BU YAGONA MANBA: uchala renderer (POS jonli chek, reprint/admin, Z-hisobot)
// shu funksiyani chaqiradi. LAN (ESC/POS) yo'li esa chek HTML'ini DOM'dan o'qiydi
// (main.js `_RECEIPT_EXTRACT_JS` → tds[1] = "Soni" katakchasi), ya'ni shu yerdagi
// matn O'ZGARISHSIZ termal printerga ham boradi — ikkala yo'l bir xil ko'rinadi.
// Shu sabab format ASCII 'x' bilan: '×' (U+00D7) termal kod-sahifada (CP437)
// boshqa belgiga aylanadi.
//
// moneyFn — har fayl O'Z pul formatini beradi (reprint: "5 000", POS: "5,000").
function _qtyNum(q) {
  // 11 → "11", 1.5 → "1.5" (ortiqcha nol yo'q — 58mm da har belgi qimmat)
  const n = Number(q);
  if (!isFinite(n)) return String(q == null ? '' : q);
  return String(Math.round(n * 1000) / 1000);
}

/**
 * Birlik narx: avval haqiqiy `price` (aniq), bo'lmasa jami/miqdor.
 * `price` afzal — bo'linmada yaxlitlash xatosi bo'lishi mumkin
 * (3 dona / 10 000 → 3 333.33), haqiqiy narx esa aniq.
 */
export function unitPriceOf(it, lineTotal, qty) {
  const p = Number(it && it.price);
  if (isFinite(p) && p > 0) return p;
  const q = Number(qty), t = Number(lineTotal);
  if (isFinite(q) && q > 0 && isFinite(t) && t > 0) return t / q;
  return 0;
}

/**
 * "11 x 5 000" yorlig'i. Birlik narx noma'lum yoki 0 bo'lsa (bepul aksiya,
 * buzuq ma'lumot) — ESKI ko'rinish (faqat miqdor), ya'ni hech qachon
 * "11 x 0" kabi chalg'ituvchi matn chiqmaydi.
 */
export function qtyPriceLabel(qty, unitPrice, moneyFn) {
  const m = typeof moneyFn === 'function' ? moneyFn : _money;
  const u = Number(unitPrice);
  const q = Number(qty);
  if (!isFinite(u) || u <= 0 || !isFinite(q) || q <= 0) {
    return String(qty == null ? '' : qty);
  }
  return `${_qtyNum(q)} x ${m(u)}`;
}

/**
 * `/orders/{id}/receipt` server ma'lumotidan 58mm chek innerHTML yasash (REPRINT uchun).
 * Chek mazmuni POS chekiga mos: pachka yorlig'i, chegirma, jami, to'lov, fiskal QR.
 */
/**
 * Sodiqlik (loyalty) chek qatorlari — UMUMIY manba (buildReceipt58 + pos.js renderReceiptData).
 * rec.loyalty {earned, redeemed, redeemed_amount, balance} bo'lsa qatorlar; aks holda ''.
 * Walk-in / ballsiz sotuvда rec.loyalty=null → hech narsa chiqmaydi. 58mm'ga mos (qisqa yorliq).
 */
export function loyaltyRows(rec) {
  const L = rec && rec.loyalty;
  if (!L) return '';
  let h = '';
  if (L.redeemed)          h += `<div class="rt-row"><span>Ball chegirma:</span><span>-${_money(L.redeemed_amount)} (${L.redeemed} ball)</span></div>`;
  if (L.earned)            h += `<div class="rt-row"><span>Yig'ilgan ball:</span><span>+${L.earned}</span></div>`;
  if (L.balance != null)   h += `<div class="rt-row"><span>Ballar balansi:</span><span>${L.balance}</span></div>`;
  return h;
}

// FAZA 3b: bepul aksiya mahsuloti (narx=0 + "Aksiya (bepul)" belgisi). 3 renderer BIR XIL ishlatadi.
export function isGiftItem(it) {
  if (!it) return false;
  if (typeof it.notes === 'string' && it.notes.indexOf('Aksiya (bepul)') === 0) return true;
  const q = it.quantity != null ? it.quantity : (it.qty || 0);
  const line = it.total != null ? it.total
             : (it.total_price != null ? it.total_price
             : (it.price != null && q ? it.price * q : null));
  return q > 0 && line === 0;
}

// Bepul Y qatori — 58mm sig'adi (yorliq nom ostида, narx ustuni "BEPUL").
export function giftRow(name, qty) {
  return `<tr><td>${_esc(name)}<br><small style="font-size:.62rem;color:#16a34a">🎁 BEPUL (aksiya)</small></td>`
       + `<td>${_esc(qty)}</td><td style="text-align:right">BEPUL</td></tr>`;
}

export function buildReceipt58(rec) {
  rec = rec || {};
  const items = rec.items || [];
  const sub = rec.subtotal != null ? rec.subtotal : rec.total_amount;
  const disc = rec.discount_amount != null ? rec.discount_amount : (rec.discount || 0);
  const tax = rec.tax_amount != null ? rec.tax_amount : (rec.tax || 0);
  const service = rec.service_amount || 0;
  const total = rec.final_amount != null ? rec.final_amount : rec.total;
  const pays = rec.payment_methods || [];
  const payTxt = pays.length
    ? pays.map(p => _PAY[p.method] || p.method).join(', ')
    : '—';

  const rowsHtml = items.map(it => {
    const qty = it.quantity != null ? it.quantity : (it.qty || 1);
    if (isGiftItem(it)) return giftRow(it.name || it.product_name || '', qty);   // FAZA 3b
    const name = _esc(it.name || it.product_name || '');
    const line = it.total != null ? it.total : (it.total_price || 0);
    // Pachka yorlig'i (1 pachka = base_qty/quantity dona) — POS bilan bir xil
    let sub2 = '';
    if (it.unit_sold === 'pachka' && it.base_qty && qty) {
      sub2 = `<br><small>📦 Pachka (${Math.round(it.base_qty / qty)} dona)</small>`;
    }
    // "11 x 5 000" — miqdor × birlik narx (v1.8.7). LAN yo'li shu katakchani
    // DOM'dan o'qiydi, shuning uchun USB va LAN bir xil ko'rinadi.
    const qtyTxt = qtyPriceLabel(qty, unitPriceOf(it, line, qty), _money);
    return `<tr><td>${name}${sub2}</td><td>${_esc(qtyTxt)}</td>`
      + `<td style="text-align:right">${_money(line)}</td></tr>`;
  }).join('');

  const dateTxt = _esc(rec.date || new Date().toLocaleString('uz-UZ'));
  const num = _esc(rec.order_number != null ? rec.order_number : (rec.order_id || ''));

  let html = `
    <div class="receipt-center">
      <h4>${_esc(rec.cafe_name || 'XENORA')}</h4>
      <p>${_esc(rec.cafe_address || '')}${rec.cafe_address ? '<br>' : ''}${dateTxt}</p>
    </div>
    <div style="font-size:10px;margin-bottom:4px">Chek #${num}${rec.table ? ' | Stol: #' + _esc(rec.table) : ''}</div>
    <table class="receipt-table">
      <thead><tr><th>Mahsulot</th><th>Soni</th><th>Narxi</th></tr></thead>
      <tbody>${rowsHtml || '<tr><td colspan="3">—</td></tr>'}</tbody>
    </table>
    <div class="receipt-totals">
      <div class="rt-row"><span>Jami:</span><span>${_money(sub)}</span></div>
      ${(disc > 0) ? `<div class="rt-row"><span>Chegirma:</span><span>-${_money(disc)}</span></div>` : ''}
      ${(tax > 0) ? `<div class="rt-row"><span>Soliq (12%):</span><span>${_money(tax)}</span></div>` : ''}
      ${(service > 0) ? `<div class="rt-row"><span>Xizmat (10%):</span><span>${_money(service)}</span></div>` : ''}
      <div class="rt-row bold"><span>UMUMIY:</span><span>${_money(total)} UZS</span></div>
      <div class="rt-row"><span>To'lov:</span><span>${_esc(payTxt)}</span></div>
      ${loyaltyRows(rec)}
    </div>
    <div class="receipt-footer">Xarid uchun rahmat!</div>`;

  if (rec.fiscal_qr_url) {
    html += `
    <div style="text-align:center;margin-top:5px;padding-top:5px;border-top:1px dashed #000">
      <div style="font-size:10px;font-weight:700">🧾 FISKAL CHEK</div>
      ${rec.fiscal_number ? `<div style="font-size:9px">№ ${_esc(rec.fiscal_number)}</div>` : ''}
      <img src="https://api.qrserver.com/v1/create-qr-code/?size=120x120&data=${encodeURIComponent(rec.fiscal_qr_url)}"
           width="110" height="110" alt="Fiskal QR" onerror="this.style.display='none'">
      <div style="font-size:9px">Soliq ilovasida skanerlang</div>
    </div>`;
  }
  return html;
}
