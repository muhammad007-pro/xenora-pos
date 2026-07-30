/**
 * XENORA — Chek LOKAL chop etish (silent print) qatlami.
 *
 * NEGA: Backend SERVERda ishlaydi (146.190.225.168), XP-58 esa DO'KON
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
  .receipt-table th:nth-child(1),.receipt-table td:nth-child(1){width:50%}
  .receipt-table th:nth-child(2),.receipt-table td:nth-child(2){width:14%;text-align:center}
  /* narx ustuni: o'ngga tayanadi, bir qatorda (nowrap) va to'liq sig'adi */
  .receipt-table th:nth-child(3),.receipt-table td:nth-child(3){width:36%;text-align:right;white-space:nowrap}
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
    return `<tr><td>${name}${sub2}</td><td>${_esc(qty)}</td>`
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
