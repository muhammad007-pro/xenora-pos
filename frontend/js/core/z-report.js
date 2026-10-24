/* Z/X-hisobot chek mazmuni — YAGONA MANBA: admin (js/admin/shift.js) va kassa
   (app/shift.html). Classic skript: funksiyalar global. fmtNum — js/core/money.js.
   Ilgari faqat admin shift.js da edi; kassa sahifasi Z-chekni serverga (/print-z)
   yuborardi — server do'kon printeriga yeta olmaydi (MANHATTAN, 2026-10). */

// Z-hisobotning pul qismi — ekran (showShiftReceipt) va 58mm chek (buildZReport58)
// SHU BITTA ro'yxatdan. Backend ESC/POS bilan bir xil tartib (escpos_service._z_money_lines).
//   SAVDO — nima sotildi (nasiya bilan), pul emas
//   PUL   — KASSAGA TUSHGAN: naqd + karta + qarz to'lovi − qaytarish
//   YASHIK — naqd: bo'lishi kerak (sanaldi/farq chaqiruvchida)
// Element: [yorliq, qiymat, qalin]; qiymat null = blok sarlavhasi; '—' = ajratgich.
function zMoneyBlocks(r, fmt) {
  const f = fmt || (n => fmtNum(n || 0) + ' so\'m');
  const g = k => Number(r[k]) || 0;
  const L = [['SAVDO', null]];
  L.push(['Naqd:', f(g('cash_sales'))], ['Karta/Click/Payme:', f(g('card_sales'))]);
  if (g('credit_total') > 0) L.push(['Nasiya:', f(g('credit_total'))]);
  L.push(['JAMI SAVDO:', f(g('total_sales')), true]);
  L.push(['Sotuvlar soni:', (r.sales_count || 0) + ' ta'], ['O\'rtacha chek:', f(g('avg_order'))]);
  if (g('discount_total') > 0) L.push(['Chegirma:', f(g('discount_total'))]);
  L.push(['—'], ['PUL (KASSAGA TUSHGAN)', null]);
  L.push(['Naqd sotuv:', '+' + f(g('cash_sales'))], ['Karta sotuv:', '+' + f(g('card_sales'))]);
  if (g('debt_paid_cash') > 0) L.push(['Qarz to\'lovi (naqd):', '+' + f(g('debt_paid_cash'))]);
  if (g('debt_paid_card') > 0) L.push(['Qarz to\'lovi (karta):', '+' + f(g('debt_paid_card'))]);
  if (g('cash_refunds') > 0)   L.push(['Qaytarish (naqd):', '−' + f(g('cash_refunds'))]);
  if (g('card_refunds') > 0)   L.push(['Qaytarish (karta):', '−' + f(g('card_refunds'))]);
  L.push(['KASSAGA TUSHGAN:', f(g('cash_in_total')), true]);
  L.push(['—'], ['YASHIK (NAQD)', null]);
  L.push(['Boshlang\'ich naqd:', f(g('starting_cash'))], ['Naqd sotuv:', '+' + f(g('cash_sales'))]);
  if (g('cash_refunds') > 0)   L.push(['Naqd qaytarish:', '−' + f(g('cash_refunds'))]);
  if (g('debt_paid_cash') > 0) L.push(['Qarz to\'lovi (naqd):', '+' + f(g('debt_paid_cash'))]);
  if (g('withdrawals') > 0)    L.push(['Olindi (inkassatsiya):', '−' + f(g('withdrawals'))]);
  if (g('deposits') > 0)       L.push(['Qo\'shildi:', '+' + f(g('deposits'))]);
  L.push(['Yashikda bo\'lishi kerak:', f(g('expected_cash')), true]);
  return L;
}

function buildZReport58(r) {
  const esc = (s) => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const m = (n) => fmtNum(n || 0);
  // ISO uchun avvalgi format o'zgarmaydi; tayyor "dd.mm.yyyy" satri o'zi chiqadi
  const dt = (s) => (/^\d{2}\.\d{2}\.\d{4}/.test(String(s || '')) ? String(s)
    : (() => { try { return new Date(s).toLocaleString('uz-UZ'); } catch { return s || '—'; } })());
  const isX = r.is_open === true;
  const sh = r.shortage || 0;
  const shLabel = sh < 0 ? 'KAMOMAD' : (sh > 0 ? 'ORTIQCHA' : 'FARQ');
  const prodRows = (Array.isArray(r.products) ? r.products : []).map(p =>
    `<tr><td>${esc(p.name)}</td><td>${p.quantity}</td><td style="text-align:right">${m(p.revenue)}</td></tr>`
  ).join('') || '<tr><td colspan="3">—</td></tr>';
  return `
    <div class="receipt-center">
      <h4>${esc(r.store_name || 'XENORA')}</h4>
      <p>SMENA HISOB-KITOBI<br>${isX ? 'X-HISOBOT (smena ochiq)' : 'Z-HISOBOT'} #${esc(r.id != null ? r.id : '')}</p>
    </div>
    <div style="font-size:0.85em;margin-bottom:4px">
      Kassir: ${esc(r.cashier || '—')}<br>
      Ochilish: ${esc(dt(r.start_time))}<br>
      ${isX ? 'Hozir: ' + esc(r.datetime || '—') : 'Yopilish: ' + esc(dt(r.end_time))}
    </div>
    <table class="receipt-table">
      <thead><tr><th>Mahsulot</th><th>Soni</th><th>Summa</th></tr></thead>
      <tbody>${prodRows}</tbody>
    </table>
    <div class="receipt-totals">
      ${zMoneyBlocks(r, m).map(([l, v, b]) => l === '—' ? '</div><div class="receipt-totals">'
        : (v === null ? `<div class="rt-row bold"><span>${l}</span><span></span></div>`
                      : `<div class="rt-row${b ? ' bold' : ''}"><span>${l}</span><span>${v}</span></div>`)).join('')}
      ${isX ? '' : `<div class="rt-row"><span>Sanaldi (haqiqiy):</span><span>${m(r.counted_cash)}</span></div>
      <div class="rt-row bold"><span>${shLabel}:</span><span>${sh < 0 ? '-' : ''}${m(Math.abs(sh))}</span></div>`}
    </div>
    ${r.notes ? `<div style="font-size:0.8em;margin-top:4px">Izoh: ${esc(r.notes)}</div>` : ''}
    <div class="receipt-footer">XENORA POS · ${isX ? 'X-hisobot' : 'Z-hisobot'}</div>`;
}
