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
      <td style="white-space:nowrap">${open
        ? `<button class="tb-btn" title="Kassadan pul olish / qo'shish" onclick="openCashMoveModal(${s.id})">💵</button>
           <button class="tb-btn" style="color:#ef4444;border-color:#ef4444" onclick="openCloseShiftModal(${s.id},${s.starting_cash||0})">Yopish</button>`
        : (hasFeature('z_report') ? `<button class="tb-btn" onclick="printZReport(${s.id},this)">🖨 Z-chek</button>` : '—')}</td>
    </tr>`;
  }).join('');
}
async function openShiftModal() {
  // Xodim TANLANMAYDI — smena har doim joriy foydalanuvchiga ochiladi
  // (backend `create_shift` klient bergan `user_id` ni qabul qilmaydi, 403).
  // Ilgari bu yerda `/users/` ro'yxati bor edi; boshqa xodim tanlansa server
  // rad etardi — ya'ni ro'yxat bajarib bo'lmaydigan va'da berardi.
  const me = getUser();
  document.getElementById('shiftUser').textContent = me.full_name || me.username || '—';
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
  // `user_id` — sxema uni MAJBURIY deb biladi (aks holda 422), lekin server
  // baribir joriy foydalanuvchini qo'yadi. Shuning uchun o'z id'imizni yuboramiz.
  const startCash = +document.getElementById('shiftStartCash').value || 0;
  const body = { user_id: getUser().id, starting_cash: startCash };
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
// Yopish oynasi: "kutilgan naqd" SERVERDAN (X-hisobot — Z bilan aynan bir xil
// hisob). Ilgari u "..." bo'lib turardi va "kamomad" = sanalgan − boshlang'ich
// deb ko'rsatilardi (sotuv, qaytarish, qarz to'lovi umuman hisobga olinmasdi).
let _closeExpected = null;
async function openCloseShiftModal(shiftId, startingCash) {
  _activeShiftId = shiftId;
  _closeExpected = null;
  const inp = document.getElementById('shiftCountedCash');
  inp.value = '';                     // ⛔ sukut 0 EMAS — sanab kiritilsin
  document.getElementById('shiftCloseNotes').value = '';
  document.getElementById('scStartCash').textContent = fmtNum(startingCash) + ' so\'m';
  ['scCashSales', 'scExpected', 'scShortage'].forEach(id => { document.getElementById(id).textContent = '...'; });
  document.getElementById('scExtra').innerHTML = '';
  openModal('shiftCloseModal');
  inp.oninput = _renderCloseDiff;
  try {
    const x = await apiFetch(`/shifts/${shiftId}/x-report`);
    if (_activeShiftId !== shiftId) return;          // boshqa smena oynasi ochilgan
    _closeExpected = Number(x.expected_cash) || 0;
    const row = (l, v) => `<div style="display:flex;justify-content:space-between"><span>${l}</span><span>${v}</span></div>`;
    document.getElementById('scCashSales').textContent = '+' + fmtNum(x.cash_sales) + ' so\'m';
    document.getElementById('scExtra').innerHTML =
        (x.cash_refunds   > 0 ? row('Naqd qaytarish:', '−' + fmtNum(x.cash_refunds) + ' so\'m') : '')
      + (x.debt_paid_cash > 0 ? row('Qarz to\'lovi (naqd):', '+' + fmtNum(x.debt_paid_cash) + ' so\'m') : '')
      + (x.withdrawals    > 0 ? row('Olindi (inkassatsiya):', '−' + fmtNum(x.withdrawals) + ' so\'m') : '')
      + (x.deposits       > 0 ? row('Qo\'shildi:', '+' + fmtNum(x.deposits) + ' so\'m') : '');
    document.getElementById('scExpected').textContent = fmtNum(_closeExpected) + ' so\'m';
  } catch (e) {
    document.getElementById('scExpected').textContent = 'yuklanmadi';
    toast('Kutilgan naqd yuklanmadi: ' + (e.message || ''), 'error');
  }
  _renderCloseDiff();
}
function _renderCloseDiff() {
  const el = document.getElementById('scShortage');
  const raw = document.getElementById('shiftCountedCash').value;
  if (raw === '' || _closeExpected === null) { el.textContent = '—'; el.style.color = ''; return; }
  const d = (+raw || 0) - _closeExpected;
  el.textContent = d < 0 ? `Kamomad: ${fmtNum(-d)} so'm` : d > 0 ? `Ortiqcha: ${fmtNum(d)} so'm` : 'Mos ✓';
  el.style.color = d < 0 ? '#ef4444' : d > 0 ? '#16a34a' : '#16a34a';
}
async function closeShift() {
  const inp = document.getElementById('shiftCountedCash');
  // ⛔ Bo'sh bilan yopilmaydi (server ham 400 qaytaradi). Yashik bo'sh — 0 yozilsin.
  if (inp.value.trim() === '' || !(+inp.value >= 0)) {
    toast('Yashikdagi naqd pulni sanab kiriting (bo\'sh bo\'lsa — 0)', 'error');
    inp.focus();
    return;
  }
  const counted = +inp.value;
  const notes = document.getElementById('shiftCloseNotes').value.trim();
  const _sid = _activeShiftId;
  let result;
  try {
    result = await apiFetchPost(`/shifts/${_sid}/close?counted_cash=${counted}&notes=${encodeURIComponent(notes)}`, {}, 'POST');
  } catch (e) {
    toast(e.message || 'Smena yopilmadi', 'error');
    return;                                           // oyna ochiq qoladi — tuzatib qayta urinsin
  }
  closeModal('shiftCloseModal');
  const shortage = result.shortage || 0;
  toast(`Smena yopildi. ${shortage < 0 ? '⚠️ Kamomad: ' + fmtNum(Math.abs(shortage)) + ' so\'m' : shortage > 0 ? 'Ortiqcha: ' + fmtNum(shortage) + ' so\'m' : 'Hisob mos!'}`, shortage ? 'warning' : 'success');
  // Yopilgach — to'liq hisob-kitob cheki ko'rsatiladi (professional Z-hisobot).
  showShiftReceipt(result, _sid);
  loadShiftsPage();
}

// ── Inkassatsiya / razmen ────────────────────────────────────────────────────
// Xarajat EMAS (foydaga tegmaydi) — faqat "yashikda bo'lishi kerak" ni tuzatadi.
// Ilgari egasi yashikdan pul olsa smena yopilganda u KAMOMAD bo'lib ko'rinardi.
let _cmShiftId = null;
async function openCashMoveModal(shiftId) {
  _cmShiftId = shiftId;
  document.getElementById('cmKind').value = 'withdrawal';
  document.getElementById('cmAmount').value = '';
  document.getElementById('cmReason').value = '';
  openModal('cashMoveModal');
  _loadCashMoves(shiftId);
}
async function _loadCashMoves(shiftId) {
  const el = document.getElementById('cmList');
  el.innerHTML = '';
  try {
    const rows = await apiFetch(`/shifts/${shiftId}/cash-movements`);
    if (!rows.length) return;
    el.innerHTML = '<div style="font-weight:600;margin-bottom:.25rem">Shu smenada:</div>' + rows.map(m =>
      `<div style="display:flex;justify-content:space-between;gap:.5rem"><span>${escH(m.reason || '')}</span>`
      + `<span style="white-space:nowrap;color:${m.kind === 'withdrawal' ? '#ef4444' : '#16a34a'}">${m.kind === 'withdrawal' ? '−' : '+'}${fmtNum(m.amount)}</span></div>`
    ).join('');
  } catch { /* ro'yxat yordamchi — xato bo'lsa jim */ }
}
async function saveCashMove() {
  const amount = +document.getElementById('cmAmount').value;
  const reason = document.getElementById('cmReason').value.trim();
  if (!(amount > 0)) { toast('Summani kiriting', 'error'); return; }
  if (reason.length < 2) { toast('Sababini yozing', 'error'); return; }
  const btn = document.getElementById('cmSaveBtn');
  btn.disabled = true;
  try {
    await apiFetchPost(`/shifts/${_cmShiftId}/cash-movements`,
      { kind: document.getElementById('cmKind').value, amount, reason });
    toast('Kassa harakati yozildi', 'success');
    closeModal('cashMoveModal');
  } catch (e) {
    toast(e.message || 'Saqlanmadi', 'error');
  } finally {
    btn.disabled = false;
  }
}

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
    ${zMoneyBlocks(r).map(([l, v, b]) => l === '—' ? line : (v === null ? `<div style="font-weight:700;font-size:.78rem">${l}</div>` : row(l, v, b))).join('')}
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
      ${zMoneyBlocks(r, m).map(([l, v, b]) => l === '—' ? '</div><div class="receipt-totals">'
        : (v === null ? `<div class="rt-row bold"><span>${l}</span><span></span></div>`
                      : `<div class="rt-row${b ? ' bold' : ''}"><span>${l}</span><span>${v}</span></div>`)).join('')}
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

