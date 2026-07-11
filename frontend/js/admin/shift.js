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
  const fdt = (s) => { try { return new Date(s).toLocaleString('uz-UZ',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}); } catch { return s || '—'; } };
  const row = (l, v, bold) => `<div style="display:flex;justify-content:space-between;${bold?'font-weight:700;':''}"><span>${l}</span><span>${v}</span></div>`;
  const line = '<div style="border-top:1px dashed #999;margin:.4rem 0"></div>';
  const money = (n) => fmtNum(n || 0) + ' so\'m';
  const shortage = r.shortage || 0;
  const shTxt = shortage < 0 ? `⚠️ Kamomad: ${money(Math.abs(shortage))}` : (shortage > 0 ? `Ortiqcha: ${money(shortage)}` : 'Mos ✓');
  document.getElementById('shiftReceiptArea').innerHTML = `
    <div style="text-align:center;font-weight:700;margin-bottom:.3rem">SMENA HISOB-KITOBI</div>
    <div style="text-align:center;font-size:.72rem;color:#555;margin-bottom:.6rem">Z-HISOBOT · #${r.id ?? shiftId ?? ''}</div>
    ${row('Kassir:', r.cashier || '—')}
    ${row('Ochilish:', fdt(r.start_time))}
    ${row('Yopilish:', fdt(r.end_time))}
    ${line}
    ${row('Sotuvlar soni:', (r.sales_count ?? 0) + ' ta')}
    ${row('Naqd sotuv:', money(r.cash_sales))}
    ${row('Karta/Click/Payme:', money(r.card_sales))}
    ${row('Nasiya:', money(r.credit_total))}
    ${row('Chegirma:', money(r.discount_total))}
    ${row('Qaytarish:', money(r.returns_total))}
    ${line}
    ${row('JAMI SAVDO:', money(r.total_sales), true)}
    ${line}
    ${row('Boshlang\'ich naqd:', money(r.starting_cash))}
    ${row('Kutilgan naqd:', money(r.expected_cash))}
    ${row('Sanaldi (haqiqiy):', money(r.counted_cash))}
    ${row(shortage < 0 ? 'Kamomad:' : (shortage > 0 ? 'Ortiqcha:' : 'Farq:'), shTxt, true)}
    ${r.notes ? line + `<div style="font-size:.75rem;color:#555">Izoh: ${(r.notes+'').replace(/</g,'&lt;')}</div>` : ''}
  `;
  const zbtn = document.getElementById('shiftReceiptPrintZBtn');
  if (zbtn) {
    if (hasFeature('z_report')) { zbtn.style.display=''; zbtn.onclick = () => printZReport(r.id ?? shiftId, zbtn); }
    else zbtn.style.display = 'none';
  }
  openModal('shiftReceiptModal');
}

// Ekrandagi chekni brauzer/printer orqali chop etish (fizik Z-printer'siz ham).
function printShiftReceipt() {
  const html = document.getElementById('shiftReceiptArea').innerHTML;
  const w = window.open('', '_blank', 'width=380,height=640');
  if (!w) { toast('Chop oynasi bloklandi', 'error'); return; }
  w.document.write(`<html><head><title>Smena cheki</title></head><body style="font-family:'Courier New',monospace;font-size:12px;padding:10px">${html}</body></html>`);
  w.document.close(); w.focus(); w.print();
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

