/* XENORA admin — OMBOR (inventory) moduli (refaktoring 3-bo'lak).
   Ombor sahifasi, kirim/chiqim, inventarizatsiya, hisobot, restock/writeoff/threshold.
   CLASSIC <script src>, katta scriptdan OLDIN (markupdan KEYIN — DOM elementlar mavjud).
   Global scope saqlanadi; mantiq o'zgarmaydi, faqat kod joyi. */
// ── Inventory (Ombor) page ────────────────────────────────────────────────────
let invCurrentPage = 1;
let invLowOnly     = false;

async function loadInventory() {
  const search = document.getElementById('invSearch')?.value || '';
  const params = new URLSearchParams({ page: invCurrentPage, page_size: 20 });
  if (invLowOnly) params.set('low_stock_only', 'true');
  if (search)     params.set('search', search);
  try {
    const data  = await apiFetch('/inventory/?' + params);
    const items = data.items || [];
    const total = data.total || 0;
    let lowCnt = 0;
    document.getElementById('invTotal').textContent = total;
    document.getElementById('invPagInfo').textContent = `${items.length} / ${total} ta`;
    const body = document.getElementById('invBody');
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Mahsulot topilmadi</td></tr>';
      document.getElementById('invLow').textContent = 0;
      document.getElementById('invOk').textContent  = 0;
      return;
    }
    body.innerHTML = items.map(inv => {
      const p    = inv.product || {};
      const isLow = inv.quantity <= inv.min_threshold;
      if (isLow) lowCnt++;
      const pct  = inv.max_threshold > 0 ? Math.min(100, Math.round(inv.quantity / inv.max_threshold * 100)) : 0;
      const barColor = isLow ? 'var(--danger)' : inv.quantity <= inv.min_threshold * 2 ? 'var(--warning)' : 'var(--success)';
      const lastR = inv.last_restock ? fmtDate(inv.last_restock) : '—';
      const nameEsc = (p.name||'').replace(/'/g,"\\'").replace(/"/g,'&quot;');
      return `<tr${isLow?' style="background:rgba(239,68,68,.04)"':''}>
        <td class="td-bold">${p.name||'—'}</td>
        <td><code style="font-size:.8125rem;color:var(--text2);font-family:monospace">${p.barcode||'—'}</code></td>
        <td>
          <div style="display:flex;align-items:center;gap:.625rem">
            <div style="flex:1;height:6px;background:var(--bg4);border-radius:3px;min-width:60px;overflow:hidden">
              <div style="width:${pct}%;height:100%;background:${barColor};border-radius:3px"></div>
            </div>
            <span style="font-size:.875rem;font-weight:700;${isLow?'color:var(--danger)':''};min-width:50px;white-space:nowrap">${inv.quantity} ${inv.unit}</span>
            ${isLow?'<span class="badge badge-red">Kam</span>':''}
          </div>
        </td>
        <td class="td-sub">${inv.min_threshold} / ${inv.max_threshold} ${inv.unit}</td>
        <td class="td-sub">${lastR}</td>
        <td class="td-actions">
          <button class="act-btn" title="Kirim qilish" onclick="openRestockModal(${inv.id},'${nameEsc}','${inv.unit}',${inv.quantity})">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          </button>
          <button class="act-btn act-danger" title="Hisobdan o'chirish" onclick="openWriteoffModal(${inv.id},'${nameEsc}','${inv.unit}',${inv.quantity})">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          </button>
          <button class="act-btn" title="Chegara sozlash" onclick="openThresholdModal(${inv.id},${inv.min_threshold},${inv.max_threshold},'${inv.unit}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8"/><path d="M12 2v2m0 16v2M4.22 4.22l1.42 1.42m12.72 12.72 1.42 1.42M2 12h2m16 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          </button>
        </td>
      </tr>`;
    }).join('');
    document.getElementById('invLow').textContent = lowCnt;
    document.getElementById('invOk').textContent  = items.length - lowCnt;
    document.getElementById('invPrevBtn').disabled = invCurrentPage <= 1;
    document.getElementById('invNextBtn').disabled = items.length < 20;
    const badge = document.getElementById('lowStockBadge');
    if (badge) { badge.textContent = lowCnt; badge.style.display = lowCnt > 0 ? '' : 'none'; }
  } catch (err) { toast(err.message, 'error'); }
}

function toggleInvLow() {
  invLowOnly = !invLowOnly;
  invCurrentPage = 1;
  document.getElementById('invLowBtn').classList.toggle('primary', invLowOnly);
  loadInventory();
}

function invPage(dir) {
  invCurrentPage = Math.max(1, invCurrentPage + dir);
  loadInventory();
}

// ── Restock modal (BOSQICH 16: kengaytirilgan) ───────────────────────────────
let _restockInvId = null;
let _suppliersList = [];

async function _loadSuppliersForModal() {
  if (_suppliersList.length) return;
  try {
    const data = await apiFetch('/suppliers-b2b/?page_size=200');
    _suppliersList = data.items || [];
    const sel = document.getElementById('rmSupplierId');
    if (sel) {
      _suppliersList.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id; opt.textContent = s.name;
        sel.appendChild(opt);
      });
    }
  } catch {}
}

function openRestockModal(invId, productName, unit, currentQty) {
  _restockInvId = invId;
  document.getElementById('rmProductName').textContent = productName;
  document.getElementById('rmUnit').textContent        = unit;
  document.getElementById('rmCurrentQty').textContent  = currentQty + ' ' + unit;
  document.getElementById('rmQty').value       = '';
  document.getElementById('rmUnitPrice').value  = '';
  document.getElementById('rmSupplierId').value = '';
  document.getElementById('rmBatch').value      = '';
  document.getElementById('rmExpiry').value     = '';
  document.getElementById('rmNote').value       = '';
  document.getElementById('rmTotalCostBox').style.display = 'none';
  document.getElementById('restockModal').classList.add('open');
  _loadSuppliersForModal();
  setTimeout(() => document.getElementById('rmQty').focus(), 100);

  const calcTotal = () => {
    const q = parseFloat(document.getElementById('rmQty').value)||0;
    const p = parseFloat(document.getElementById('rmUnitPrice').value)||0;
    const box = document.getElementById('rmTotalCostBox');
    if (q > 0 && p > 0) {
      document.getElementById('rmTotalCost').textContent = fmtMoney(q * p);
      box.style.display = '';
    } else { box.style.display = 'none'; }
  };
  document.getElementById('rmQty').oninput = calcTotal;
  document.getElementById('rmUnitPrice').oninput = calcTotal;
}

function closeRestockModal() { document.getElementById('restockModal').classList.remove('open'); }

async function saveRestock() {
  const qty = parseFloat(document.getElementById('rmQty').value);
  if (!qty || qty <= 0) { toast("Miqdorni kiriting", 'error'); return; }
  const btn = document.getElementById('rmSaveBtn');
  btn.disabled = true; btn.textContent = 'Saqlanmoqda...';
  try {
    const body = {
      quantity: qty,
      unit_cost: parseFloat(document.getElementById('rmUnitPrice').value) || 0,
      notes: document.getElementById('rmNote').value.trim() || null,
    };
    const suppId = parseInt(document.getElementById('rmSupplierId').value);
    if (suppId) body.supplier_id = suppId;
    const batch = document.getElementById('rmBatch').value.trim();
    if (batch) body.batch_number = batch;
    const expiry = document.getElementById('rmExpiry').value;
    if (expiry) body.expiry_date = expiry;

    const res = await fetch(`${API_BASE}/inventory/${_restockInvId}/add-stock`, {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    closeRestockModal();
    toast(`${qty} kiritildi`, 'success');
    loadInventory();
    updateLowStockBadge();
  } catch (err) { toast(err.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Kirim qilish'; }
}

// ── Writeoff modal ─────────────────────────────────────────────────────────────
let _woInvId = null;

function openWriteoffModal(invId, productName, unit, currentQty) {
  _woInvId = invId;
  document.getElementById('woProductName').textContent = productName;
  document.getElementById('woUnit').textContent        = unit;
  document.getElementById('woCurrentQty').textContent  = currentQty + ' ' + unit;
  document.getElementById('woQty').value    = '';
  document.getElementById('woReason').value = 'spoiled';
  document.getElementById('woBatch').value  = '';
  document.getElementById('woNote').value   = '';
  document.getElementById('writeoffModal').classList.add('open');
  setTimeout(() => document.getElementById('woQty').focus(), 100);
}

function closeWriteoffModal() { document.getElementById('writeoffModal').classList.remove('open'); }

async function saveWriteoff() {
  const qty = parseFloat(document.getElementById('woQty').value);
  if (!qty || qty <= 0) { toast("Miqdorni kiriting", 'error'); return; }
  const btn = document.getElementById('woSaveBtn');
  btn.disabled = true; btn.textContent = "O'chirilmoqda...";
  try {
    const body = {
      inventory_id: _woInvId,
      quantity: qty,
      reason: document.getElementById('woReason').value,
      batch_number: document.getElementById('woBatch').value.trim() || null,
      notes: document.getElementById('woNote').value.trim() || null,
    };
    const res = await fetch(`${API_BASE}/inventory/writeoff`, {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    closeWriteoffModal();
    toast(`${qty} hisobdan o'chirildi`, 'success');
    if (currentPage === 'stockOut') { loadStockOut(); }
    else { loadInventory(); }
    updateLowStockBadge();
  } catch (err) { toast(err.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = "Hisobdan o'chirish"; }
}

// ── Threshold modal ───────────────────────────────────────────────────────────
let _threshInvId = null;

function openThresholdModal(invId, minT, maxT, unit) {
  _threshInvId = invId;
  document.getElementById('tmMin').value       = minT;
  document.getElementById('tmMax').value       = maxT;
  document.getElementById('tmUnit').textContent = unit;
  document.getElementById('thresholdModal').classList.add('open');
  setTimeout(() => document.getElementById('tmMin').focus(), 100);
}

function closeThresholdModal() { document.getElementById('thresholdModal').classList.remove('open'); }

async function saveThreshold() {
  const minT = parseFloat(document.getElementById('tmMin').value);
  const maxT = parseFloat(document.getElementById('tmMax').value);
  if (isNaN(minT) || isNaN(maxT)) { toast("Qiymatlarni kiriting", 'error'); return; }
  const btn = document.getElementById('tmSaveBtn');
  btn.disabled = true; btn.textContent = 'Saqlanmoqda...';
  try {
    const res = await fetch(`${API_BASE}/inventory/${_threshInvId}`, {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ min_threshold: minT, max_threshold: maxT })
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    closeThresholdModal();
    toast("Chegara yangilandi", 'success');
    loadInventory();
  } catch (err) { toast(err.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Saqlash'; }
}

// ── Kirim tarixi (pageStockIn) — BOSQICH 16 ──────────────────────────────────
let siCurrentPage = 1;
let _siStats = { count: 0, qty: 0, cost: 0 };

function siApplyFilter() { siCurrentPage = 1; loadStockIn(); }
function siPage(d) { siCurrentPage = Math.max(1, siCurrentPage + d); loadStockIn(); }

async function loadStockIn() {
  const type    = document.getElementById('siTypeFilter')?.value || '';
  const from    = document.getElementById('siDateFrom')?.value || '';
  const to      = document.getElementById('siDateTo')?.value || '';
  const params  = new URLSearchParams({ page: siCurrentPage, page_size: 30 });
  if (type) params.set('movement_type', type);
  if (from) params.set('date_from', from);
  if (to)   params.set('date_to', to);
  try {
    const data  = await apiFetch('/inventory/movements?' + params);
    const items = data.items || [];
    const total = data.total || 0;

    document.getElementById('siPagInfo').textContent = `${items.length} / ${total} ta`;
    document.getElementById('siPrevBtn').disabled = siCurrentPage <= 1;
    document.getElementById('siNextBtn').disabled = items.length < 30;

    // stats faqat 'in' uchun
    const inItems = items.filter(i => i.movement_type === 'in');
    document.getElementById('siCount').textContent = total;
    document.getElementById('siQty').textContent   = inItems.reduce((s,i)=>s+i.quantity,0).toFixed(2);
    document.getElementById('siCost').textContent  = fmtMoney(inItems.reduce((s,i)=>s+(i.total_cost||0),0));

    const typeLabels = { in:'Kirim', out:'Chiqim', writeoff:"O'chirish", adjustment:'Inventar', sale:'Sotuv', return:'Qaytish' };
    const typeColors = { in:'var(--success)', out:'var(--warning)', writeoff:'var(--danger)', adjustment:'#8b5cf6', sale:'var(--text2)' };

    const body = document.getElementById('siBody');
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:2rem;color:var(--text3)">Hech narsa topilmadi</td></tr>';
      return;
    }
    body.innerHTML = items.map(mv => `<tr>
      <td class="td-sub">${mv.created_at ? mv.created_at.slice(0,16).replace('T',' ') : '—'}</td>
      <td class="td-bold">${mv.product_name || '—'}</td>
      <td><span style="color:${typeColors[mv.movement_type]||'var(--text2)'};font-weight:600;font-size:.8125rem">${typeLabels[mv.movement_type]||mv.movement_type}</span></td>
      <td>${mv.quantity} ${mv.unit}</td>
      <td class="td-sub">${mv.unit_cost > 0 ? fmtMoney(mv.unit_cost) : '—'}</td>
      <td class="td-sub">${mv.total_cost > 0 ? fmtMoney(mv.total_cost) : '—'}</td>
      <td class="td-sub">${mv.supplier_name || '—'}</td>
      <td class="td-sub">${mv.batch_number || '—'}</td>
      <td class="td-sub" style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${mv.notes||''}">${mv.notes || '—'}</td>
    </tr>`).join('');
  } catch (err) { toast(err.message, 'error'); }
}


// ── Chiqim / Hisobdan o'chirish (pageStockOut) — BOSQICH 16 ──────────────────
let soCurrentPage = 1;

function soPage(d) { soCurrentPage = Math.max(1, soCurrentPage + d); loadStockOut(); }

async function loadStockOut() {
  const search = document.getElementById('soSearch')?.value || '';
  const params = new URLSearchParams({ page: soCurrentPage, page_size: 20 });
  if (search) params.set('search', search);
  try {
    const [invData, woData] = await Promise.all([
      apiFetch('/inventory/?' + params),
      apiFetch('/inventory/movements?movement_type=writeoff&page=1&page_size=20'),
    ]);
    const items = invData.items || [];
    const total = invData.total || 0;
    const woItems = woData.items || [];

    document.getElementById('soInvCount').textContent = total;
    document.getElementById('soPagInfo').textContent  = `${items.length} / ${total} ta`;
    document.getElementById('soPrevBtn').disabled = soCurrentPage <= 1;
    document.getElementById('soNextBtn').disabled = items.length < 20;

    document.getElementById('soCount').textContent = woData.total || 0;
    document.getElementById('soQty').textContent   = woItems.reduce((s,i)=>s+i.quantity,0).toFixed(2);

    const body = document.getElementById('soBody');
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text3)">Mahsulot topilmadi</td></tr>';
    } else {
      const nameEsc = s => (s||'').replace(/'/g,"\\'").replace(/"/g,'&quot;');
      body.innerHTML = items.map(inv => {
        const p    = inv.product || {};
        const isLow = inv.quantity <= inv.min_threshold;
        return `<tr${isLow?' style="background:rgba(239,68,68,.04)"':''}>
          <td class="td-bold">${p.name || '—'}</td>
          <td><span style="font-weight:700;${isLow?'color:var(--danger)':''}">${inv.quantity}</span>${isLow?' <span class="badge badge-red">Kam</span>':''}</td>
          <td class="td-sub">${inv.unit}</td>
          <td class="td-sub">${inv.min_threshold}</td>
          <td class="td-actions">
            <button class="act-btn act-danger" title="Hisobdan o'chirish"
              onclick="openWriteoffModal(${inv.id},'${nameEsc(p.name)}','${inv.unit}',${inv.quantity})">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
            </button>
          </td>
        </tr>`;
      }).join('');
    }

    const reasonLabels = { spoiled:"Buzilgan", lost:"Yo'qolgan", internal_use:"Ichki ishlatish", expired:"Muddati o'tgan", other:"Boshqa", inventory_adjustment:"Inventar" };
    const hBody = document.getElementById('soHistoryBody');
    if (!woItems.length) {
      hBody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:1.5rem;color:var(--text3)">Hech narsa topilmadi</td></tr>';
    } else {
      hBody.innerHTML = woItems.map(mv => `<tr>
        <td class="td-sub">${mv.created_at ? mv.created_at.slice(0,16).replace('T',' ') : '—'}</td>
        <td class="td-bold">${mv.product_name || '—'}</td>
        <td style="color:var(--danger);font-weight:600">−${mv.quantity} ${mv.unit}</td>
        <td><span class="badge badge-red">${reasonLabels[mv.reason]||mv.reason||'—'}</span></td>
        <td class="td-sub">${mv.notes || '—'}</td>
        <td class="td-sub">${mv.user_name || '—'}</td>
      </tr>`).join('');
    }
  } catch (err) { toast(err.message, 'error'); }
}

if (document.getElementById('soSearch')) {
  let _soT;
  document.getElementById('soSearch').addEventListener('input', () => {
    clearTimeout(_soT); _soT = setTimeout(() => { soCurrentPage=1; loadStockOut(); }, 300);
  });
}


// ── Inventarizatsiya (pageInvCount) — BOSQICH 16 ─────────────────────────────
let _icCurrentCountId = null;
let _icItems = [];

async function loadInvCountList() {
  document.getElementById('icListBox').style.display = '';
  document.getElementById('icDetailBox').style.display = 'none';
  try {
    const data  = await apiFetch('/inventory/count/list');
    const items = data.items || [];
    const body  = document.getElementById('icListBody');
    const statusMap = { draft:'Tahrirda', confirmed:'Tasdiqlangan', cancelled:'Bekor' };
    const statusColor = { draft:'badge-amber', confirmed:'badge-green', cancelled:'badge-red' };
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Inventarizatsiya yo\'q</td></tr>';
      return;
    }
    body.innerHTML = items.map(c => `<tr>
      <td class="td-bold">#${c.id}</td>
      <td class="td-sub">${c.created_at ? c.created_at.slice(0,16).replace('T',' ') : '—'}</td>
      <td><span class="badge ${statusColor[c.status]||''}">${statusMap[c.status]||c.status}</span></td>
      <td>${c.total_items}</td>
      <td style="color:${c.filled_items===c.total_items?'var(--success)':'var(--warning)'}">${c.filled_items}/${c.total_items}</td>
      <td class="td-sub">${c.confirmed_at ? c.confirmed_at.slice(0,10) : '—'}</td>
      <td class="td-actions">
        <button class="act-btn" onclick="openInvCountDetail(${c.id},'${c.status}')">Ko'rish</button>
        ${c.status==='draft'?`<button class="act-btn act-danger" onclick="deleteInvCount(${c.id})">O'ch</button>`:''}
      </td>
    </tr>`).join('');
  } catch (err) { toast(err.message, 'error'); }
}

async function startInvCount() {
  if (!confirm("Yangi inventarizatsiya boshlash. Hozirgi qoldiqlar snapshotga olinadi. Davom etasizmi?")) return;
  try {
    const res = await fetch(`${API_BASE}/inventory/count/start`, {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: null })
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    const data = await res.json();
    toast(`Inventarizatsiya boshlandi. ${data.item_count} ta mahsulot`, 'success');
    await loadInvCountList();
    openInvCountDetail(data.id, 'draft');
  } catch (err) { toast(err.message, 'error'); }
}

async function openInvCountDetail(countId, status) {
  _icCurrentCountId = countId;
  document.getElementById('icListBox').style.display = 'none';
  document.getElementById('icDetailBox').style.display = '';
  document.getElementById('icDetailTitle').textContent = `Inventarizatsiya #${countId}`;
  const statusMap = { draft:'Tahrirda', confirmed:'Tasdiqlangan' };
  const statusColor = { draft:'badge-amber', confirmed:'badge-green' };
  document.getElementById('icStatusBadge').className = `badge ${statusColor[status]||''}`;
  document.getElementById('icStatusBadge').textContent = statusMap[status]||status;
  document.getElementById('icConfirmBtn').style.display = status === 'draft' ? '' : 'none';
  document.getElementById('icSearch').value = '';
  await _renderInvCountItems(countId, status);
}

async function _renderInvCountItems(countId, status) {
  try {
    const data = await apiFetch(`/inventory/count/${countId}`);
    _icItems = data.items || [];
    _icRenderItems(_icItems, status || data.status);

    const filled = _icItems.filter(i => i.actual_qty !== null);
    const short  = filled.filter(i => (i.difference||0) < 0).length;
    const over   = filled.filter(i => (i.difference||0) > 0).length;
    document.getElementById('icSumTotal').textContent = _icItems.length;
    document.getElementById('icSumShort').textContent = short;
    document.getElementById('icSumOver').textContent  = over;
    document.getElementById('icSummary').style.display = filled.length > 0 ? '' : 'none';
  } catch (err) { toast(err.message, 'error'); }
}

function _icRenderItems(items, status) {
  const searchVal = (document.getElementById('icSearch')?.value || '').toLowerCase();
  const filtered  = searchVal ? items.filter(i => (i.product_name||'').toLowerCase().includes(searchVal)) : items;
  const body = document.getElementById('icDetailBody');
  const isDraft = status === 'draft';
  body.innerHTML = filtered.map(it => {
    const diff = it.difference;
    const diffColor = diff === null ? 'var(--text3)' : diff < 0 ? 'var(--danger)' : diff > 0 ? 'var(--success)' : 'var(--text2)';
    const diffTxt   = diff === null ? '—' : `${diff > 0 ? '+' : ''}${diff.toFixed(2)}`;
    return `<tr id="icRow_${it.id}">
      <td class="td-bold">${it.product_name || '—'}</td>
      <td class="td-sub">${it.unit}</td>
      <td style="color:var(--text2)">${it.system_qty}</td>
      <td>${isDraft
        ? `<input type="number" min="0" step="0.001" value="${it.actual_qty !== null ? it.actual_qty : ''}" placeholder="0"
             style="width:90px;padding:.375rem .5rem;background:var(--bg3);border:1px solid var(--border2);border-radius:6px;color:var(--text);font-family:inherit"
             onchange="icUpdateItem(${it.id},this.value,'${it.unit}')">`
        : `<span style="font-weight:600">${it.actual_qty !== null ? it.actual_qty : '—'}</span>`
      }</td>
      <td><span style="color:${diffColor};font-weight:600">${diffTxt}</span></td>
      <td class="td-sub">${it.notes || '—'}</td>
    </tr>`;
  }).join('');
}

function icFilterItems() {
  const data = apiFetch(`/inventory/count/${_icCurrentCountId}`).then(d => {
    _icItems = d.items || [];
    _icRenderItems(_icItems, d.status);
  }).catch(()=>{});
}

async function icUpdateItem(itemId, actualQtyStr, unit) {
  const actualQty = parseFloat(actualQtyStr);
  if (isNaN(actualQty) || actualQty < 0) return;
  try {
    const res = await fetch(`${API_BASE}/inventory/count/${_icCurrentCountId}/items/${itemId}`, {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ actual_qty: actualQty })
    });
    if (!res.ok) return;
    const upd = await res.json();
    // In-place update
    const it = _icItems.find(i => i.id === itemId);
    if (it) { it.actual_qty = actualQty; it.difference = upd.difference; }
    const diff = upd.difference;
    const row  = document.getElementById(`icRow_${itemId}`);
    if (row) {
      const diffCell = row.cells[4];
      const diffColor = diff < 0 ? 'var(--danger)' : diff > 0 ? 'var(--success)' : 'var(--text2)';
      diffCell.innerHTML = `<span style="color:${diffColor};font-weight:600">${diff > 0 ? '+' : ''}${diff.toFixed(2)}</span>`;
    }
    const short = _icItems.filter(i => (i.difference||0) < 0).length;
    const over  = _icItems.filter(i => (i.difference||0) > 0).length;
    document.getElementById('icSumShort').textContent = short;
    document.getElementById('icSumOver').textContent  = over;
    document.getElementById('icSummary').style.display = '';
  } catch {}
}

async function confirmInvCount() {
  const unfilled = _icItems.filter(i => i.actual_qty === null).length;
  if (unfilled > 0 && !confirm(`${unfilled} ta mahsulot sanalmagan. Davom etasizmi?`)) return;
  if (!confirm("Inventarizatsiyani tasdiqlash. Farqlar omborga yoziladi. Davom etasizmi?")) return;
  try {
    const res = await fetch(`${API_BASE}/inventory/count/${_icCurrentCountId}/confirm`, {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    const data = await res.json();
    toast(data.message, 'success');
    closeInvCountDetail();
    loadInventory();
    updateLowStockBadge();
  } catch (err) { toast(err.message, 'error'); }
}

async function deleteInvCount(countId) {
  if (!confirm("Inventarizatsiyani o'chirish?")) return;
  try {
    const res = await fetch(`${API_BASE}/inventory/count/${countId}`, {
      method: 'DELETE',
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast("O'chirildi", 'success');
    loadInvCountList();
  } catch (err) { toast(err.message, 'error'); }
}

function closeInvCountDetail() {
  _icCurrentCountId = null;
  document.getElementById('icListBox').style.display = '';
  document.getElementById('icDetailBox').style.display = 'none';
  loadInvCountList();
}


// ── Ombor hisoboti (pageInvReport) — BOSQICH 16 ──────────────────────────────
async function loadInvReport() {
  const days = document.getElementById('irPeriod')?.value || 30;
  document.getElementById('irLastUpdated').textContent = `Yuklanmoqda...`;
  try {
    const [report, value] = await Promise.all([
      apiFetch(`/inventory/report/summary?days=${days}`),
      apiFetch('/inventory/value'),
    ]);

    document.getElementById('irLastUpdated').textContent = `Oxirgi yangilash: ${new Date().toLocaleTimeString('uz')}`;
    document.getElementById('irInCount').textContent  = report.incoming?.count || 0;
    document.getElementById('irInCost').textContent   = fmtMoney(report.incoming?.total_cost || 0);
    document.getElementById('irOutCount').textContent = report.outgoing?.count || 0;
    document.getElementById('irDeadCount').textContent= report.dead_stock_count || 0;

    // Ombor qiymati
    document.getElementById('irValCost').textContent   = fmtMoney(value.total_cost || 0);
    document.getElementById('irValRetail').textContent = fmtMoney(value.total_retail || 0);
    document.getElementById('irValProfit').textContent = fmtMoney(value.potential_profit || 0);

    // Top kelim mahsulotlar
    const topBody = document.getElementById('irTopBody');
    const top = report.top_incoming || [];
    if (!top.length) {
      topBody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:1.5rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>';
    } else {
      topBody.innerHTML = top.map((r,i) => `<tr>
        <td class="td-sub">${i+1}</td>
        <td class="td-bold">${r.product_name}</td>
        <td class="td-sub">${r.total_qty.toFixed(2)}</td>
        <td class="td-sub">${fmtMoney(r.total_cost)}</td>
      </tr>`).join('');
    }

    // O'lik tovar
    const deadBody = document.getElementById('irDeadBody');
    const dead = report.dead_stock || [];
    if (!dead.length) {
      deadBody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:1.5rem;color:var(--success)">O\'lik tovar yo\'q!</td></tr>';
    } else {
      deadBody.innerHTML = dead.map(r => `<tr>
        <td class="td-bold" style="color:var(--warning)">${r.product_name}</td>
        <td class="td-sub">${r.quantity}</td>
        <td class="td-sub">${r.last_restock ? r.last_restock.slice(0,10) : '—'}</td>
      </tr>`).join('');
    }
  } catch (err) { toast(err.message, 'error'); }
}


