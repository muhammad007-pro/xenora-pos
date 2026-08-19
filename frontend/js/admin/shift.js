/* XENORA admin — SMENA / KASSA (shift) moduli (refaktoring 3-bo'lak).
   Registers (multi-kassa) + smena ochish/yopish + Z-hisobot cheki. MANTIQ o'zgarmadi
   (savdo bloklovchi smena-majburiyligi pos.js/payment.py da — bu fayl faqat boshqaruv UI).
   CLASSIC <script src>, katta scriptdan OLDIN. Global scope saqlanadi. */
// ═══════════════════════════════════════════════════════
// BOSQICH 30 — Kassalar (multi-register boshqaruvi)
// ═══════════════════════════════════════════════════════
let _editRegisterId = null;
let _branchCache = [];

async function _loadBranchesInto(selectEl, selectedId) {
  try {
    _branchCache = await apiFetch('/branches/');
  } catch { _branchCache = []; }
  selectEl.innerHTML = '<option value="">— Filialsiz —</option>' +
    (_branchCache || []).map(b => `<option value="${b.id}"${b.id===selectedId?' selected':''}>${escH(b.name)}</option>`).join('');
}

async function loadRegisters() {
  const tb = document.getElementById('registersTbody');
  if (!tb) return;
  try {
    const list = await apiFetch('/cash-registers/');
    if (!_branchCache.length) { try { _branchCache = await apiFetch('/branches/'); } catch {} }
    const bName = id => (_branchCache.find(b => b.id === id) || {}).name || '—';
    if (!list.length) { tb.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:1.5rem;color:var(--text3)">Kassa yo\'q. "+ Kassa qo\'shish" tugmasini bosing.</td></tr>'; return; }
    tb.innerHTML = list.map(r => `<tr${r.is_active?'':' style="opacity:.55"'}>
      <td class="td-bold">${escH(r.name)}</td>
      <td>${escH(bName(r.branch_id))}</td>
      <td>${r.is_active?'<span style="color:#22c55e">Faol</span>':'<span style="color:var(--text3)">Nofaol</span>'}</td>
      <td style="display:flex;gap:.4rem">
        <button class="tb-btn" onclick="editRegister(${r.id})">Tahrir</button>
        <button class="tb-btn" onclick="toggleRegister(${r.id},${r.is_active})">${r.is_active?'Nofaol':'Faollashtirish'}</button>
        <button class="tb-btn" style="color:#ef4444;border-color:#ef4444" onclick="deleteRegister(${r.id},'${escH(r.name).replace(/'/g,"\\'")}')">O'chirish</button>
      </td>
    </tr>`).join('');
  } catch (e) {
    tb.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:1.5rem;color:#ef4444">${escH(e.message||'Xato')}</td></tr>`;
  }
}

async function openRegisterModal() {
  _editRegisterId = null;
  document.getElementById('registerModalTitle').textContent = 'Yangi kassa';
  document.getElementById('regName').value = '';
  await _loadBranchesInto(document.getElementById('regBranch'), null);
  openModal('registerModal');
}

async function editRegister(id) {
  const list = await apiFetch('/cash-registers/');
  const r = list.find(x => x.id === id);
  if (!r) return;
  _editRegisterId = id;
  document.getElementById('registerModalTitle').textContent = 'Kassani tahrirlash';
  document.getElementById('regName').value = r.name || '';
  await _loadBranchesInto(document.getElementById('regBranch'), r.branch_id);
  openModal('registerModal');
}

async function saveRegister() {
  const name = document.getElementById('regName').value.trim();
  const branchId = document.getElementById('regBranch').value;
  if (!name) { toast('Kassa nomini kiriting', 'error'); return; }
  const body = { name, branch_id: branchId ? +branchId : null };
  try {
    if (_editRegisterId) {
      await apiFetchPost('/cash-registers/' + _editRegisterId, body, 'PATCH');
    } else {
      await apiFetchPost('/cash-registers/', body, 'POST');
    }
    closeModal('registerModal');
    toast(_editRegisterId ? 'Yangilandi' : 'Kassa qo\'shildi', 'success');
    loadRegisters();
  } catch (e) { toast(e.message || 'Xato', 'error'); }
}

async function toggleRegister(id, isActive) {
  try {
    await apiFetchPost('/cash-registers/' + id, { is_active: !isActive }, 'PATCH');
    loadRegisters();
  } catch (e) { toast(e.message || 'Xato', 'error'); }
}

async function deleteRegister(id, name) {
  if (!confirm(`"${name}" kassasini o'chirmoqchimisiz?`)) return;
  try {
    await apiFetchPost('/cash-registers/' + id, {}, 'DELETE');
    toast('O\'chirildi', 'success');
    loadRegisters();
  } catch (e) { toast(e.message || 'Xato', 'error'); }
}

// ═══════════════════════════════════════════════════════
// BOSQICH 20 — Cash Register (Kassa Smena)
// ═══════════════════════════════════════════════════════
let _activeShiftId = null;
let _shiftsCache = [];
let _registerNameMap = {};
let _lastZReport = null;   // oxirgi Z-hisobot ma'lumoti (chop etish uchun)
async function loadShiftsPage() {
  const data = await apiFetch('/shifts/');
  _shiftsCache = Array.isArray(data) ? data : (data.items || []);
  // Kassa nomlari xaritasi (register_id → nom)
  _registerNameMap = {};
  try {
    const regs = await apiFetch('/cash-registers/');
    (Array.isArray(regs) ? regs : []).forEach(r => { _registerNameMap[r.id] = r.name; });
  } catch {}
  // Faol smena holati
  const active = _shiftsCache.find(s => !s.end_time);
  _activeShiftId = active ? active.id : null;
  const badge = document.getElementById('activeShiftBadge');
  if (badge) badge.style.display = active ? '' : 'none';
  // Filtr dropdownlarini to'ldirish
  const cashierSel = document.getElementById('shiftFilterCashier');
  const regSel = document.getElementById('shiftFilterRegister');
  if (cashierSel) {
    const names = [...new Set(_shiftsCache.map(s => (s.user && s.user.full_name) || s.user_name || s.cashier).filter(Boolean))];
    cashierSel.innerHTML = '<option value="">Barcha kassirlar</option>' + names.map(n => `<option value="${escH(n)}">${escH(n)}</option>`).join('');
  }
  if (regSel) {
    const regIds = [...new Set(_shiftsCache.map(s => s.register_id).filter(v => v != null))];
    regSel.innerHTML = '<option value="">Barcha kassalar</option>' + regIds.map(id => `<option value="${id}">${escH(_registerNameMap[id] || ('Kassa #' + id))}</option>`).join('');
  }
  renderShifts();
}
function renderShifts() {
  const tb = document.getElementById('shiftsTbody');
  if (!tb) return;
  const fCashier = (document.getElementById('shiftFilterCashier') || {}).value || '';
  const fRegister = (document.getElementById('shiftFilterRegister') || {}).value || '';
  const fDate = (document.getElementById('shiftFilterDate') || {}).value || '';
  const shifts = (_shiftsCache || []).filter(s => {
    const name = (s.user && s.user.full_name) || s.user_name || s.cashier || '';
    if (fCashier && name !== fCashier) return false;
    if (fRegister && String(s.register_id) !== String(fRegister)) return false;
    if (fDate && (s.start_time || '').slice(0, 10) !== fDate) return false;
    return true;
  });
  if (!shifts.length) { tb.innerHTML = '<tr><td colspan="11" style="text-align:center;color:#888">Smena topilmadi</td></tr>'; return; }
  tb.innerHTML = shifts.map(s => {
    const open = !s.end_time;
    const shortage = s.shortage || 0;
    const cashier = (s.user && s.user.full_name) || s.user_name || s.cashier || '—';
    const regName = s.register_id != null ? (_registerNameMap[s.register_id] || ('Kassa #' + s.register_id)) : '—';
    return `<tr style="${open?'background:#f0fdf4':''}">
      <td>${escH(cashier)}</td>
      <td style="font-size:.82rem">${escH(regName)}</td>
      <td style="font-size:.82rem">${(s.start_time||'').slice(0,16).replace('T',' ')}</td>
      <td style="font-size:.82rem">${s.end_time?(s.end_time.slice(0,16).replace('T',' ')):'<span style="color:#22c55e">Faol</span>'}</td>
      <td>${fmtNum(s.starting_cash||0)}</td>
      <td>${fmtNum(s.cash_sales||0)}</td>
      <td>${fmtNum(s.card_sales||0)}</td>
      <td>${fmtNum(s.credit_total||0)}</td>
      <td style="color:${shortage<0?'#ef4444':shortage>0?'#22c55e':'#888'}">${shortage?fmtNum(shortage):0}</td>
      <td>${open?'<span style="color:#22c55e">Faol</span>':'Yopiq'}</td>
      <td>${open
        ? `<button class="tb-btn" style="color:#ef4444;border-color:#ef4444" onclick="openCloseShiftModal(${s.id},${s.starting_cash||0})">Yopish</button>`
        : (hasFeature('z_report') ? `<button class="tb-btn" onclick="printZReport(${s.id},this)">🖨 Z-chek</button>` : '—')}</td>
    </tr>`;
  }).join('');
}
async function openShiftModal() {
  const users = await apiFetch('/users/?page_size=100');
  const sel = document.getElementById('shiftUser');
  sel.innerHTML = (users.items||users||[]).map(u=>`<option value="${u.id}">${escH(u.full_name||u.username)}</option>`).join('');
  document.getElementById('shiftStartCash').value = '0';

  // Kassa tanlash — faqat cash_register flagi yoqilgan bo'lsa (faol kassalar mavjud)
  const regGroup = document.getElementById('shiftRegisterGroup');
  const regSel = document.getElementById('shiftRegister');
  try {
    const regs = (await apiFetch('/cash-registers/')).filter(r => r.is_active);
    if (regs.length && hasFeature('cash_register')) {
      if (!_branchCache.length) { try { _branchCache = await apiFetch('/branches/'); } catch {} }
      const bName = id => (_branchCache.find(b => b.id === id) || {}).name;
      regSel.innerHTML = regs.map(r => `<option value="${r.id}">${escH(r.name)}${bName(r.branch_id)?' — '+escH(bName(r.branch_id)):''}</option>`).join('');
      regGroup.style.display = '';
    } else {
      regGroup.style.display = 'none';
      regSel.innerHTML = '';
    }
  } catch { regGroup.style.display = 'none'; regSel.innerHTML = ''; }

  openModal('shiftOpenModal');
}
async function openShift() {
  const userId = +document.getElementById('shiftUser').value;
  const startCash = +document.getElementById('shiftStartCash').value || 0;
  const body = { user_id: userId, starting_cash: startCash };
  const regGroup = document.getElementById('shiftRegisterGroup');
  if (regGroup && regGroup.style.display !== 'none') {
    const regId = document.getElementById('shiftRegister').value;
    if (regId) body.register_id = +regId;
  }
  try {
    await apiFetchPost('/shifts/', body, 'POST');
    closeModal('shiftOpenModal');
    loadShiftsPage();
    toast('Smena ochildi!');
  } catch (e) { toast(e.message || 'Xato', 'error'); }
}
async function openCloseShiftModal(shiftId, startingCash) {
  _activeShiftId = shiftId;
  document.getElementById('shiftCountedCash').value = '';
  document.getElementById('shiftCloseNotes').value = '';
  document.getElementById('shiftClosePreview').style.display = 'none';
  document.getElementById('scStartCash').textContent = fmtNum(startingCash);
  openModal('shiftCloseModal');
  // Live preview when typing
  document.getElementById('shiftCountedCash').oninput = function() {
    const counted = +this.value || 0;
    const preview = document.getElementById('shiftClosePreview');
    preview.style.display = '';
    document.getElementById('scExpected').textContent = '...';
    document.getElementById('scCashSales').textContent = '...';
    document.getElementById('scShortage').textContent = fmtNum(counted - startingCash) + ' so\'m';
  };
}
async function closeShift() {
  const counted = +document.getElementById('shiftCountedCash').value || 0;
  const notes = document.getElementById('shiftCloseNotes').value.trim();
  const _sid = _activeShiftId;
  const result = await apiFetchPost(`/shifts/${_sid}/close?counted_cash=${counted}&notes=${encodeURIComponent(notes)}`, {}, 'POST');
  closeModal('shiftCloseModal');
  if (result && (result.id || result.shortage !== undefined)) {
    const shortage = result.shortage || 0;
    toast(`Smena yopildi. ${shortage < 0 ? '⚠️ Kamomad: ' + fmtNum(Math.abs(shortage)) + ' so\'m' : shortage > 0 ? 'Ortiqcha: ' + fmtNum(shortage) + ' so\'m' : 'Hisob mos!'}`, shortage ? 'warning' : 'success');
    // Yopilgach — to'liq hisob-kitob cheki ko'rsatiladi (professional Z-hisobot).
    showShiftReceipt(result, _sid);
  } else {
    toast((result && result.detail) || 'Smena yopilmadi', 'error');
  }
  loadShiftsPage();
}

// Smena yopilish chekini (Z-hisobot) chiroyli ko'rsatadi — jami savdo, naqd, karta,
// Click/Payme (card ichida), nasiya, qaytarish, sotuvlar soni, vaqt, kamomad.
function showShiftReceipt(r, shiftId) {
  _lastZReport = r;   // chop etish uchun saqlaymiz (buildZReport58)
  const fdt = (s) => { try { return new Date(s).toLocaleString('uz-UZ',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}); } catch { return s || '—'; } };
  const esc = (s) => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const row = (l, v, bold) => `<div style="display:flex;justify-content:space-between;${bold?'font-weight:700;':''}"><span>${l}</span><span>${v}</span></div>`;
  const line = '<div style="border-top:1px dashed #999;margin:.4rem 0"></div>';
  const money = (n) => fmtNum(n || 0) + ' so\'m';
  const shortage = r.shortage || 0;
  const shTxt = shortage < 0 ? `⚠️ Kamomad: ${money(Math.abs(shortage))}` : (shortage > 0 ? `Ortiqcha: ${money(shortage)}` : 'Mos ✓');
  // SOTILGAN MAHSULOTLAR — nima nechta sotildi (summa bo'yicha)
  const prods = Array.isArray(r.products) ? r.products : [];
  const prodHtml = prods.length
    ? prods.map(p => `<div style="display:flex;justify-content:space-between;font-size:.78rem"><span>${esc(p.name)} ×${p.quantity}</span><span>${money(p.revenue)}</span></div>`).join('')
    : '<div style="font-size:.75rem;color:#888">— sotuv yo\'q —</div>';
  document.getElementById('shiftReceiptArea').innerHTML = `
    <div style="text-align:center;font-weight:700;margin-bottom:.3rem">${esc(r.store_name || 'XENORA')}</div>
    <div style="text-align:center;font-weight:700">SMENA HISOB-KITOBI</div>
    <div style="text-align:center;font-size:.72rem;color:#555;margin-bottom:.6rem">Z-HISOBOT · #${r.id ?? shiftId ?? ''}</div>
    ${row('Kassir:', esc(r.cashier || '—'))}
    ${row('Ochilish:', fdt(r.start_time))}
    ${row('Yopilish:', fdt(r.end_time))}
    ${line}
    <div style="font-weight:700;font-size:.78rem;margin-bottom:.2rem">SOTILGAN MAHSULOTLAR</div>
    ${prodHtml}
    ${line}
    ${row('Sotuvlar soni:', (r.sales_count ?? 0) + ' ta')}
    ${row('O\'rtacha chek:', money(r.avg_order))}
    ${row('Naqd sotuv:', money(r.cash_sales))}
    ${row('Karta/Click/Payme:', money(r.card_sales))}
    ${row('Nasiya:', money(r.credit_total))}
    ${row('Chegirma:', money(r.discount_total))}
    ${row('Qaytarish:', money(r.returns_total))}
    ${line}
    ${row('JAMI SAVDO:', money(r.total_sales), true)}
    ${line}
    ${row('Boshlang\'ich naqd:', money(r.starting_cash))}
    ${/* Nasiya to'lovi — kassaga tushgan pul, LEKIN sotuv emas: shu sabab
          "JAMI SAVDO" dan yuqorida emas, kassa blokida turadi. */''}
    ${(r.debt_paid_cash > 0) ? row('Nasiya to\'lovi (naqd):', money(r.debt_paid_cash)) : ''}
    ${(r.debt_paid_card > 0) ? row('Nasiya to\'lovi (karta):', money(r.debt_paid_card)) : ''}
    ${row('Kutilgan naqd:', money(r.expected_cash))}
    ${row('Sanaldi (haqiqiy):', money(r.counted_cash))}
    ${row(shortage < 0 ? 'Kamomad:' : (shortage > 0 ? 'Ortiqcha:' : 'Farq:'), shTxt, true)}
    ${r.notes ? line + `<div style="font-size:.75rem;color:#555">Izoh: ${esc(r.notes)}</div>` : ''}
  `;
  const zbtn = document.getElementById('shiftReceiptPrintZBtn');
  if (zbtn) {
    if (hasFeature('z_report')) { zbtn.style.display=''; zbtn.onclick = () => printZReport(r.id ?? shiftId, zbtn); }
    else zbtn.style.display = 'none';
  }
  openModal('shiftReceiptModal');
}

// Z-hisobot 58mm innerHTML (chek idiomida: .receipt-* / .rt-row → margin:0, 48mm,
// chapga, monospace, shrift sozlama). Markaziy printDocument shu HTML'ni bosadi.
function buildZReport58(r) {
  const esc = (s) => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const m = (n) => fmtNum(n || 0);
  const dt = (s) => { try { return new Date(s).toLocaleString('uz-UZ'); } catch { return s || '—'; } };
  const sh = r.shortage || 0;
  const shLabel = sh < 0 ? 'KAMOMAD' : (sh > 0 ? 'ORTIQCHA' : 'FARQ');
  const prodRows = (Array.isArray(r.products) ? r.products : []).map(p =>
    `<tr><td>${esc(p.name)}</td><td>${p.quantity}</td><td style="text-align:right">${m(p.revenue)}</td></tr>`
  ).join('') || '<tr><td colspan="3">—</td></tr>';
  return `
    <div class="receipt-center">
      <h4>${esc(r.store_name || 'XENORA')}</h4>
      <p>SMENA HISOB-KITOBI<br>Z-HISOBOT #${esc(r.id != null ? r.id : '')}</p>
    </div>
    <div style="font-size:0.85em;margin-bottom:4px">
      Kassir: ${esc(r.cashier || '—')}<br>
      Ochilish: ${esc(dt(r.start_time))}<br>
      Yopilish: ${esc(dt(r.end_time))}
    </div>
    <table class="receipt-table">
      <thead><tr><th>Mahsulot</th><th>Soni</th><th>Summa</th></tr></thead>
      <tbody>${prodRows}</tbody>
    </table>
    <div class="receipt-totals">
      <div class="rt-row"><span>Sotuvlar soni:</span><span>${r.sales_count || 0} ta</span></div>
      <div class="rt-row"><span>O'rtacha chek:</span><span>${m(r.avg_order)}</span></div>
      <div class="rt-row bold"><span>JAMI SAVDO:</span><span>${m(r.total_sales)}</span></div>
    </div>
    <div class="receipt-totals">
      <div class="rt-row"><span>Naqd:</span><span>${m(r.cash_sales)}</span></div>
      <div class="rt-row"><span>Karta/Click/Payme:</span><span>${m(r.card_sales)}</span></div>
      <div class="rt-row"><span>Nasiya:</span><span>${m(r.credit_total)}</span></div>
      ${(r.discount_total > 0) ? `<div class="rt-row"><span>Chegirma:</span><span>-${m(r.discount_total)}</span></div>` : ''}
      ${(r.returns_total > 0) ? `<div class="rt-row"><span>Qaytarish:</span><span>-${m(r.returns_total)}</span></div>` : ''}
    </div>
    <div class="receipt-totals">
      <div class="rt-row"><span>Boshlang'ich naqd:</span><span>${m(r.starting_cash)}</span></div>
      ${(r.debt_paid_cash > 0) ? `<div class="rt-row"><span>Nasiya to'lovi (naqd):</span><span>+${m(r.debt_paid_cash)}</span></div>` : ''}
      ${(r.debt_paid_card > 0) ? `<div class="rt-row"><span>Nasiya to'lovi (karta):</span><span>${m(r.debt_paid_card)}</span></div>` : ''}
      <div class="rt-row"><span>Kutilgan naqd:</span><span>${m(r.expected_cash)}</span></div>
      <div class="rt-row"><span>Sanaldi (haqiqiy):</span><span>${m(r.counted_cash)}</span></div>
      <div class="rt-row bold"><span>${shLabel}:</span><span>${sh < 0 ? '-' : ''}${m(Math.abs(sh))}</span></div>
    </div>
    ${r.notes ? `<div style="font-size:0.8em;margin-top:4px">Izoh: ${esc(r.notes)}</div>` : ''}
    <div class="receipt-footer">XENORA POS · Z-hisobot</div>`;
}

// Z-hisobotni MARKAZIY print servisga (B1: printDocument) yuboradi — 58mm, silent,
// Windows oyna YO'Q. window.printReceiptDoc admin.html modulida (deviceName +
// print_type/ip/port + shrift avtomatik qo'shiladi).
function printShiftReceipt() {
  if (!_lastZReport) { toast('Z-hisobot ma\'lumoti yo\'q', 'error'); return; }
  if (!window.printReceiptDoc) { toast('Print servis topilmadi', 'error'); return; }
  const html = buildZReport58(_lastZReport);
  window.printReceiptDoc(html, { title: 'Z-hisobot #' + (_lastZReport.id || '') })
    .then((res) => {
      if (res && res.ok) { if (!res.browser) toast('Z-hisobot chiqarildi', 'success'); }
      else toast('Z-hisobot chiqmadi: ' + ((res && res.error) || 'noma\'lum xato'), 'error');
    })
    .catch((e) => toast('Z-hisobot xato: ' + (e.message || e), 'error'));
}
async function printZReport(shiftId, btn) {
  if (btn) { btn.disabled = true; btn.textContent = '...'; }
  try {
    const res = await apiFetchPost(`/shifts/${shiftId}/print-z`, {}, 'POST');
    if (res.printed) toast('Z-chek printerga yuborildi');
    else if (res.printer?.reason === 'disabled') toast('Printer o\'chiq (sozlamadan yoqing)', 'error');
    else toast(res.detail || 'Z-chek chiqmadi', 'error');
  } catch (e) { toast(e.message || 'Z-chek chiqmadi', 'error'); }
  finally { if (btn) { btn.disabled = false; btn.textContent = '🖨 Z-chek'; } }
}

