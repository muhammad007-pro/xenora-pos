/* Modifikator admin UI — guruh (single/multiple, majburiy, min/max) → variantlar (price_delta, default).
   Backend /modifiers CRUD to'liq tayyor; bu — FAQAT admin UI. Restoran/kafe (MODIFIERS feature).
   Globallar core.js'дан: apiFetch, apiFetchPost, token, API_BASE, toast, fmtMoney, openModal, closeModal. */

let _modGroupsCache = [];
let _modProducts = {};   // nom(lower) → id

function _modEsc(s){ return String(s==null?'':s).replace(/[<>"'&]/g,c=>({'<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','&':'&amp;'}[c])); }

async function _modLoadProducts() {
  try {
    const data = await apiFetch('/products/?page_size=1000&is_active=true');
    const items = data.items || data || [];
    _modProducts = {};
    let opts = '';
    (items||[]).forEach(p => { if (p && p.name) { _modProducts[p.name.trim().toLowerCase()] = p.id; opts += `<option value="${_modEsc(p.name)}"></option>`; } });
    const dl = document.getElementById('mgProductList'); if (dl) dl.innerHTML = opts;
  } catch (e) { /* jim */ }
}

function _modProductName(pid) {
  if (!pid) return 'Barcha mahsulotlar';
  for (const [nm, id] of Object.entries(_modProducts)) if (id === pid) return nm;
  return 'Mahsulot #' + pid;
}

async function loadModifiers() {
  _modLoadProducts();
  const body = document.getElementById('modifiersBody');
  if (!body) return;
  try {
    const g = await apiFetch('/modifiers/groups');
    _modGroupsCache = Array.isArray(g) ? g : (g.items || []);
    if (!_modGroupsCache.length) { body.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text3)">Guruh yo\'q. "+ Yangi guruh" bilan boshlang.</div>'; return; }
    body.innerHTML = _modGroupsCache.map(_modGroupCard).join('');
  } catch (e) { toast(e.message, 'error'); }
}

function _modGroupCard(g) {
  const typeLbl = g.type === 'multiple' ? "Ko'p tanlash" : 'Bitta tanlash';
  const req = g.is_required ? '<span class="badge badge-gold">Majburiy</span>' : '<span class="badge badge-gray">Ixtiyoriy</span>';
  const rows = (g.modifiers || []).map(m => `
    <tr>
      <td>${_modEsc(m.name)}${m.is_default?' <span class="badge badge-green">default</span>':''}</td>
      <td style="text-align:right;color:var(--gold)">${(m.price_delta||0)>0?'+':''}${fmtMoney(m.price_delta||0)}</td>
      <td class="td-actions" style="text-align:right;white-space:nowrap">
        <button class="act-btn" onclick="openModifierModal(${g.id},${m.id})" title="Tahrir">&#9998;</button>
        <button class="act-btn" style="color:var(--danger)" onclick="deleteModifier(${m.id})" title="O'chirish">&#128465;</button>
      </td>
    </tr>`).join('') || '<tr><td colspan="3" style="color:var(--text3);padding:.5rem">Variant yo\'q</td></tr>';
  return `
  <div style="background:var(--bg2);border:1px solid var(--border2);border-radius:12px;padding:1rem;margin-bottom:1rem">
    <div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
      <strong style="font-size:1rem">${_modEsc(g.name)}</strong> ${req}
      <span class="badge badge-blue">${typeLbl}</span>
      <span style="color:var(--text3);font-size:.8rem">${_modEsc(_modProductName(g.product_id))} · min ${g.min_select}/max ${g.max_select}</span>
      <span style="margin-left:auto;display:flex;gap:.35rem">
        <button class="tb-btn" onclick="openModifierModal(${g.id})">+ Variant</button>
        <button class="tb-btn" onclick="openGroupModal(${g.id})">Tahrir</button>
        <button class="tb-btn" style="color:var(--danger)" onclick="deleteGroup(${g.id})">O'chirish</button>
      </span>
    </div>
    <table style="width:100%;margin-top:.6rem;border-collapse:collapse"><tbody>${rows}</tbody></table>
  </div>`;
}

// ── Guruh CRUD ──
function openGroupModal(id) {
  const g = id ? _modGroupsCache.find(x=>x.id===id) : null;
  document.getElementById('modGroupTitle').textContent = g ? 'Guruhni tahrirlash' : 'Yangi guruh';
  document.getElementById('mgId').value = g ? g.id : '';
  document.getElementById('mgName').value = g ? g.name : '';
  document.getElementById('mgProduct').value = (g && g.product_id) ? _modProductName(g.product_id) : '';
  document.getElementById('mgType').value = g ? g.type : 'single';
  document.getElementById('mgRequired').checked = g ? !!g.is_required : false;
  document.getElementById('mgMin').value = g ? g.min_select : 0;
  document.getElementById('mgMax').value = g ? g.max_select : 1;
  openModal('modGroupModal');
}

async function saveGroup() {
  const id = document.getElementById('mgId').value;
  const name = document.getElementById('mgName').value.trim();
  const type = document.getElementById('mgType').value;
  const isReq = document.getElementById('mgRequired').checked;
  const min = parseInt(document.getElementById('mgMin').value, 10) || 0;
  const max = parseInt(document.getElementById('mgMax').value, 10) || 1;
  const prodName = document.getElementById('mgProduct').value.trim().toLowerCase();
  const pid = prodName ? (_modProducts[prodName] || null) : null;
  if (!name) { toast('Guruh nomini kiriting', 'error'); return; }
  if (min > max) { toast("Min tanlash Max'dan katta bo'lmasin", 'error'); return; }
  if (isReq && min < 1) { toast('Majburiy guruhда Min tanlash kamida 1 bo\'lsin', 'error'); return; }
  if (prodName && !pid) { toast("Mahsulot topilmadi — ro'yxatdan tanlang yoki bo'sh qoldiring", 'error'); return; }
  const body = { name, product_id: pid, type, is_required: isReq, min_select: min, max_select: max };
  try {
    if (id) await apiFetchPost(`/modifiers/groups/${id}`, body, 'PATCH');
    else    await apiFetchPost('/modifiers/groups', { ...body, modifiers: [] });
    toast('Saqlandi', 'success'); closeModal('modGroupModal'); loadModifiers();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteGroup(id) {
  if (!confirm("Guruh (va variantlari) o'chirilsinmi?")) return;
  try { await apiFetchPost(`/modifiers/groups/${id}`, {}, 'DELETE'); toast("O'chirildi", 'success'); loadModifiers(); }
  catch (e) { toast(e.message, 'error'); }
}

// ── Variant CRUD ──
function openModifierModal(groupId, id) {
  const g = _modGroupsCache.find(x=>x.id===groupId);
  const m = (id && g) ? (g.modifiers||[]).find(x=>x.id===id) : null;
  document.getElementById('modItemTitle').textContent = m ? 'Variantni tahrirlash' : 'Yangi variant';
  document.getElementById('miId').value = m ? m.id : '';
  document.getElementById('miGroupId').value = groupId;
  document.getElementById('miName').value = m ? m.name : '';
  document.getElementById('miDelta').value = m ? m.price_delta : 0;
  document.getElementById('miDefault').checked = m ? !!m.is_default : false;
  openModal('modItemModal');
}

async function saveModifier() {
  const id = document.getElementById('miId').value;
  const gid = document.getElementById('miGroupId').value;
  const name = document.getElementById('miName').value.trim();
  const delta = parseFloat(document.getElementById('miDelta').value) || 0;   // manfiy ham mumkin (chegirmali variant)
  const isDef = document.getElementById('miDefault').checked;
  if (!name) { toast('Variant nomini kiriting', 'error'); return; }
  // "Bitta tanlash" guruhда default faqat bitta bo'lsin — ogohlantirish
  const g = _modGroupsCache.find(x=>x.id===Number(gid));
  if (isDef && g && g.type === 'single') {
    const others = (g.modifiers||[]).filter(x=>x.is_default && x.id!==Number(id));
    if (others.length && !confirm('Bu guruh "bitta tanlash". Allaqachon default variant bor — eskisini qo\'lда oling. Davom etilsinmi?')) return;
  }
  const body = { name, price_delta: delta, is_default: isDef };
  try {
    if (id) await apiFetchPost(`/modifiers/modifiers/${id}`, body, 'PATCH');
    else    await apiFetchPost(`/modifiers/groups/${gid}/modifiers`, body);
    toast('Saqlandi', 'success'); closeModal('modItemModal'); loadModifiers();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteModifier(id) {
  if (!confirm("Variant o'chirilsinmi?")) return;
  try { await apiFetchPost(`/modifiers/modifiers/${id}`, {}, 'DELETE'); toast("O'chirildi", 'success'); loadModifiers(); }
  catch (e) { toast(e.message, 'error'); }
}

// Global (onclick + core.js sahifa dispatch)
window.loadModifiers = loadModifiers;
window.openGroupModal = openGroupModal;
window.saveGroup = saveGroup;
window.deleteGroup = deleteGroup;
window.openModifierModal = openModifierModal;
window.saveModifier = saveModifier;
window.deleteModifier = deleteModifier;
