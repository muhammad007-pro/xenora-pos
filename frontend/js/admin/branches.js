/* XENORA admin — FILIALLAR (branches) moduli (refaktoring 3-bo'lak).
   CLASSIC <script src>, katta scriptdan OLDIN. Global scope saqlanadi. */
// ═══════════════════════════════════════════════════════════════════
// FILIAL TIZIMI (BOSQICH 15)
// ═══════════════════════════════════════════════════════════════════

let _branches = [];      // keshlanган filiallar
let _activeBranchId = null;  // 0 = hamma, N = specific

// ── Branch Switcher ─────────────────────────────────────────────

function toggleBranchDD() {
  document.getElementById('branchDropdown').classList.toggle('open');
}
document.addEventListener('click', (e) => {
  if (!document.getElementById('branchSwitcher')?.contains(e.target)) {
    document.getElementById('branchDropdown')?.classList.remove('open');
  }
});

async function loadBranchesSwitcher() {
  try {
    const data = await apiFetch('/branches/');
    _branches = Array.isArray(data) ? data : [];
    if (_branches.length <= 1) {
      // 1 ta filial varsa — switcher kerak emas
      document.getElementById('branchSwitcher').style.display = 'none';
      return;
    }
    document.getElementById('branchSwitcher').style.display = '';
    const list = document.getElementById('branchDDList');
    list.innerHTML = _branches.filter(b=>b.is_active).map(b => `
      <div class="branch-dd-item${_activeBranchId===b.id?' selected':''}" onclick="switchBranch(${b.id})">
        <span class="bd-dot"></span>
        <span>${b.name}</span>
        ${b.is_default?'<span style="font-size:.625rem;color:var(--text3);margin-left:auto">Asosiy</span>':''}
      </div>`).join('');

    // Badge
    const badge = document.getElementById('branchCountBadge');
    if (badge) { badge.textContent = _branches.length; badge.style.display = ''; }

    _updateBranchBtnLabel();
  } catch {}
}

function _updateBranchBtnLabel() {
  const lbl = document.getElementById('branchBtnLabel');
  const allEl = document.getElementById('branchAll');
  if (!lbl) return;
  if (!_activeBranchId) {
    lbl.textContent = 'Hamma filiallar';
    allEl?.classList.add('selected');
  } else {
    const br = _branches.find(b=>b.id===_activeBranchId);
    lbl.textContent = br ? br.name : 'Filial';
    allEl?.classList.remove('selected');
  }
  // Re-render list
  const list = document.getElementById('branchDDList');
  if (list) {
    list.querySelectorAll('.branch-dd-item').forEach(el => {
      const onclick = el.getAttribute('onclick')||'';
      const id = parseInt(onclick.replace('switchBranch(','').replace(')',''))||0;
      el.classList.toggle('selected', id === _activeBranchId);
    });
  }
}

async function switchBranch(branchId) {
  document.getElementById('branchDropdown').classList.remove('open');
  try {
    const res = await fetch(`${API_BASE}/auth/switch-branch/${branchId}`, {
      method:'POST', headers:{'Authorization':'Bearer '+token}
    });
    if (!res.ok) throw new Error('Xatolik');
    const data = await res.json();
    localStorage.setItem('access_token', data.access_token);
    token = data.access_token;
    _activeBranchId = branchId || null;
    _updateBranchBtnLabel();
    // Joriy sahifani qayta yuklash
    loadPageData(currentPage);
    toast(branchId ? `${_branches.find(b=>b.id===branchId)?.name || 'Filial'} tanlandi` : 'Hamma filiallar', 'success');
  } catch { toast('Filial almashtirishda xatolik','error'); }
}

// ── Branch Management Page ──────────────────────────────────────

let _editBranchId = null;

async function loadBranches() {
  try {
    const data = await apiFetch('/branches/');
    _branches = Array.isArray(data) ? data : [];
    const total = _branches.length;
    const active = _branches.filter(b=>b.is_active).length;
    const def = _branches.find(b=>b.is_default);
    document.getElementById('brTotalCount').textContent = total;
    document.getElementById('brActiveCount').textContent = active;
    document.getElementById('brDefaultName').textContent = def ? def.name : '—';

    const tbody = document.getElementById('branchTbody');
    if (!tbody) return;
    if (!total) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text3);padding:2rem">Hali filial yo\'q</td></tr>';
      return;
    }
    tbody.innerHTML = _branches.map(b=>`
      <tr>
        <td>
          <span style="font-weight:600">${b.name}</span>
          ${b.is_default?'<span style="margin-left:.375rem;font-size:.625rem;background:var(--gold-dim);color:var(--gold);padding:2px 6px;border-radius:4px">Asosiy</span>':''}
        </td>
        <td>${b.address||'—'}</td>
        <td>${b.phone||'—'}</td>
        <td>
          <span style="font-size:.75rem;padding:3px 8px;border-radius:4px;background:${b.is_active?'rgba(16,185,129,.12)':'rgba(239,68,68,.12)'};color:${b.is_active?'var(--success)':'var(--danger)'}">
            ${b.is_active?'Faol':'Nofaol'}
          </span>
        </td>
        <td>
          <button class="tb-btn" style="padding:.3rem .6rem;font-size:.75rem" onclick='openBranchModal(${JSON.stringify(b)})'>Tahrirlash</button>
          ${!b.is_default?`<button class="tb-btn" style="padding:.3rem .6rem;font-size:.75rem;margin-left:.25rem;color:var(--danger)" onclick="deactivateBranch(${b.id},'${b.name}')">${b.is_active?'O\'chirish':''}</button>`:''}
        </td>
      </tr>`).join('');
  } catch (e) { toast('Filiallar yuklanmadi','error'); }
}

function openBranchModal(branch=null) {
  _editBranchId = branch?.id || null;
  document.getElementById('branchModalTitle').textContent = branch ? 'Filial tahrirlash' : 'Yangi filial';
  document.getElementById('branchNameInput').value = branch?.name || '';
  document.getElementById('branchAddressInput').value = branch?.address || '';
  document.getElementById('branchPhoneInput').value = branch?.phone || '';
  document.getElementById('branchDefaultCheck').checked = branch?.is_default || false;
  // Tahrirlashda default checkboxni ko'rsat, yangi qo'shishda yashir
  document.getElementById('branchDefaultRow').style.display = branch ? '' : 'none';
  const ov = document.getElementById('branchModalOverlay');
  ov.style.display = 'flex';
  setTimeout(()=>document.getElementById('branchNameInput').focus(),100);
}

function closeBranchModal(e) {
  if (e && e.currentTarget !== e.target) return;
  document.getElementById('branchModalOverlay').style.display = 'none';
  _editBranchId = null;
}

async function saveBranch() {
  const name = document.getElementById('branchNameInput').value.trim();
  if (!name) { toast('Filial nomi kiritilmagan','error'); return; }
  const payload = {
    name,
    address: document.getElementById('branchAddressInput').value.trim()||null,
    phone: document.getElementById('branchPhoneInput').value.trim()||null,
  };
  if (_editBranchId) payload.is_default = document.getElementById('branchDefaultCheck').checked;
  try {
    const method = _editBranchId ? 'PATCH' : 'POST';
    const url = _editBranchId ? `${API_BASE}/branches/${_editBranchId}` : `${API_BASE}/branches/`;
    const res = await fetch(url, {method, headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!res.ok) { const e=await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    document.getElementById('branchModalOverlay').style.display = 'none';
    toast(_editBranchId?'Yangilandi':"Qo'shildi",'success');
    await loadBranches();
    await loadBranchesSwitcher();
  } catch(e) { toast(e.message,'error'); }
}

async function deactivateBranch(id, name) {
  if (!confirm(`"${name}" filialini o'chirmoqchimisiz? Ma'lumotlar saqlanib qoladi.`)) return;
  try {
    const res = await fetch(`${API_BASE}/branches/${id}`, {method:'DELETE', headers:{'Authorization':'Bearer '+token}});
    if (!res.ok) { const e=await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast("O'chirildi",'success'); await loadBranches(); await loadBranchesSwitcher();
  } catch(e) { toast(e.message,'error'); }
}

// Init: filialllarni yuklash (faqat admin/ega uchun)
if (!token) {} else { loadBranchesSwitcher(); }

