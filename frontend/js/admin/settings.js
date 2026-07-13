/* XENORA admin — SOZLAMALAR (settings) moduli (refaktoring 3-bo'lak).
   Reorder sozlama, Feature Flags UI, Receipt Settings, Departments.
   PRO gate MANTIG'I bu yerda EMAS (settings.html detectPlanAndLock + backend) — tegilmadi.
   hasFeature() core'da qoldi. CLASSIC <script src>, katta scriptdan OLDIN. */
// ── Reorder sozlama modali ─────────────────────────────────────────────────────
let _reorderEditId = null;
let _reorderProducts = [];
async function openReorderModal(settingId, productId) {
  _reorderEditId = settingId;
  if (!_reorderProducts.length) {
    try { const d = await apiFetch('/products/?page_size=500'); _reorderProducts = d.items || []; } catch {}
  }
  const existing = settingId ? null : null;
  const prodSel = `<select id="rmProduct" class="form-control" style="width:100%">
    ${_reorderProducts.map(p => `<option value="${p.id}" ${p.id === productId ? 'selected' : ''}>${p.name}</option>`).join('')}
  </select>`;
  const supSel = `<select id="rmSupplier" class="form-control" style="width:100%">
    <option value="">— Yetkazib beruvchi tanlanmagan —</option>
    ${_reorderSuppliers.map(s => `<option value="${s.id}">${s.name}</option>`).join('')}
  </select>`;

  const box = document.createElement('div');
  box.id = 'reorderModal';
  box.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center';
  box.innerHTML = `<div style="background:var(--bg2);border-radius:12px;width:400px;max-width:96vw;padding:1.5rem;display:flex;flex-direction:column;gap:1rem">
    <h3 style="font-weight:700">${settingId ? 'Sozlamani tahrirlash' : 'Yangi minimal qoldiq'}</h3>
    ${!settingId ? `<div><label style="font-size:.8125rem;color:var(--text2);display:block;margin-bottom:.3rem">Mahsulot</label>${prodSel}</div>` : ''}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem">
      <div><label style="font-size:.8125rem;color:var(--text2);display:block;margin-bottom:.3rem">Minimal qoldiq</label><input id="rmMinQty" type="number" min="0" step="0.1" value="10" class="form-control" style="width:100%"></div>
      <div><label style="font-size:.8125rem;color:var(--text2);display:block;margin-bottom:.3rem">Zakaz miqdori</label><input id="rmReorderQty" type="number" min="0" step="0.1" value="50" class="form-control" style="width:100%"></div>
    </div>
    <div><label style="font-size:.8125rem;color:var(--text2);display:block;margin-bottom:.3rem">Yetkazib beruvchi</label>${supSel}</div>
    <div><label style="font-size:.8125rem;color:var(--text2);display:block;margin-bottom:.3rem">Izoh</label><input id="rmNotes" type="text" placeholder="Ixtiyoriy izoh" class="form-control" style="width:100%"></div>
    <div style="display:flex;gap:.5rem;margin-top:.5rem">
      <button onclick="document.getElementById('reorderModal').remove()" style="flex:1;padding:.5625rem;border-radius:var(--r);background:var(--bg3);border:1px solid var(--border2);color:var(--text2);cursor:pointer">Bekor</button>
      <button onclick="saveReorderSetting(${settingId})" style="flex:2;padding:.5625rem;border-radius:var(--r);background:linear-gradient(135deg,#c9a84c,#e2c97a,#c9a84c);color:#03110c;font-weight:700;cursor:pointer;border:none">Saqlash</button>
    </div>
  </div>`;
  document.body.appendChild(box);
}
async function saveReorderSetting(settingId) {
  const minQty     = parseFloat(document.getElementById('rmMinQty').value) || 10;
  const reorderQty = parseFloat(document.getElementById('rmReorderQty').value) || 50;
  const supplierId = document.getElementById('rmSupplier')?.value || null;
  const notes      = document.getElementById('rmNotes').value;

  try {
    if (settingId) {
      await fetch(API_BASE + `/reorder-settings/${settingId}`, {
        method: 'PATCH',
        headers: {'Authorization':'Bearer '+token, 'Content-Type':'application/json'},
        body: JSON.stringify({ min_qty: minQty, reorder_qty: reorderQty, supplier_id: supplierId || null, notes }),
      });
    } else {
      const productId = parseInt(document.getElementById('rmProduct').value);
      await fetch(API_BASE + '/reorder-settings/', {
        method: 'POST',
        headers: {'Authorization':'Bearer '+token, 'Content-Type':'application/json'},
        body: JSON.stringify({ product_id: productId, min_qty: minQty, reorder_qty: reorderQty, supplier_id: supplierId || null, notes }),
      });
    }
    document.getElementById('reorderModal')?.remove();
    loadReorderAlerts();
    toast('Saqlandi', 'success');
  } catch(e) { toast('Xatolik: ' + e.message, 'error'); }
}
async function deleteReorderSetting(id) {
  if (!confirm('O\'chirishni tasdiqlaysizmi?')) return;
  await fetch(API_BASE + `/reorder-settings/${id}`, { method:'DELETE', headers:{'Authorization':'Bearer '+token} });
  loadReorderAlerts();
  toast("O'chirildi", 'success');
}

// ── Settings: Feature Flags ───────────────────────────────────────────────────
const FLAG_LABELS = {
  kitchen_display:'Oshxona ekrani (KDS)',table_management:'Stol boshqaruvi',
  waiter:'Ofitsiant rejimi',table_reservation:'Stol bron qilish',recipe:'Retsept (ombor auto-kamaytirish)',
  barcode:'Shtrix-kod skaneri',scale:'Tarozi integratsiyasi',expiry_date:'Yaroqlilik muddati nazorati',
  time_booking:'Vaqt bo\'yicha bron',services:'Xizmatlar ro\'yxati',inventory:'Ombor boshqaruvi',
  loyalty:'Sodiqlik dasturi',delivery:'Yetkazib berish',qr_menu:'QR-menyu',
  modifiers:'Mahsulot modifikatorlari',combo:'Kombo/Set menyu',happy_hour:'Happy Hour (avtomatik chegirma)',
  table_merge:'Stol birlashtirish',courses:'Kursli ovqat',waiter_call:'Ofitsiant chaqirish (QR)',
  tips:'Choy puli (tips)',customer_history:'Mijoz tarixi',voice_order:'Ovozli buyurtma',
  yield_tracking:'Yield/poteriya hisobi',staff_meal:'Xodimlar ovqati',
  returns:'Qaytarish tizimi',quick_sell:'Tez sotuv paneli',multi_barcode:'Ko\'p barcode',
  price_history:'Narx o\'zgarish tarixi',receipt_settings:'Chek sozlamasi',
  cash_register:'Kassa smena',z_report:'Z-hisobot (kun yakuni)',store_dashboard:'Magazin dashboard',
  prescription_archive:'Retsept arxivi',drug_analogs:'Dori analoglari',
  batch_tracking:'Partiya nazorati',dosage_info:'Dozaj ma\'lumoti',rx_required:'Retsept talab nazorati',
  online_booking:'Onlayn bron',staff_schedule:'Usta ish jadvali',before_after_photo:'Oldin/keyin foto',
  salon_client_history:'Salon mijoz tarixi',commission_report:'Komissiya hisoboti',
  credit_sales:'Nasiya/qarz daftar',wholesale_pricing:'Ko\'tara narx',promotions:'Aksiyalar',
  departments:'Bo\'limlar (seksiyalar)',supplier_accounting:'Yetkazib beruvchi hisob-kitob',
  supplier_card:'Yetkazib beruvchi kartochkasi',supplier_debt:'Firmaga qarz',
  supplier_return:'Firmaga vozvrat',purchase_receipt:'Priyomka (qabul akti)',
  write_off:'Utilizatsiya/spisaniye',goods_regrade:'Peresort',markup_policy:'Naценка siyosati',
  bonus_card:'Bonus karta',abc_analysis:'ABC tahlil',auto_reorder:'Avto-zakaz',
  turnover_analysis:'Oborot tahlili',peak_hours:'Peak soatlar',loss_report:'Zarar hisoboti',
  customer_return_ext:'Kengaytirilgan vozvrat',internal_transfer:'Ichki ko\'chirish',markirovka:'Asl belgisi',
};

let _settingsData = null;

async function loadSettings() {
  document.getElementById('settingsLoading').style.display = '';
  document.getElementById('settingsContent').style.display = 'none';
  try {
    const data = await apiFetch('/cafes/my/features');
    _settingsData = data;
    const plan = data.subscription_plan || 'free';
    // "free" kaliti o'zgarmaydi — faqat ko'rinadigan nom "LITE".
    const planLabel = plan === 'free' ? 'LITE' : plan.toUpperCase();
    const isProPlan = plan !== 'free';   // Lite'dan boshqasi (pro) — PRO ochiq
    document.getElementById('settingsPlanBadge').textContent = planLabel + ' tarif';

    // Backend endi FAQAT shu biznesga tegishli funksiyalarni qaytaradi (begona kelmaydi).
    const freeFlags = [], proFlags = [];
    (data.features || []).forEach(f => {
      if (f.is_pro) proFlags.push(f); else freeFlags.push(f);
    });

    // FREE section — biznes turiga tegishli BO'LMAGAN flaglar kulrang/disabled
    document.getElementById('settingsFreeSection').innerHTML = freeFlags.map(f => {
      const label = FLAG_LABELS[f.flag] || f.flag;
      const foreign = f.in_business === false;   // begona biznes funksiyasi
      const note = foreign
        ? `<div style="font-size:.7rem;color:#f59e0b;margin-top:.15rem">Bu funksiya sizning biznes turingizga tegishli emas</div>`
        : '';
      return `<div class="toggle-row" style="padding:.5rem 0;border-bottom:1px solid var(--border2)${foreign ? ';opacity:.55' : ''}">
        <div>
          <div class="toggle-label" style="font-size:.875rem">${foreign ? '🚫 ' : ''}${label}</div>
          <div style="font-size:.75rem;color:var(--text3)">${f.flag}</div>
          ${note}
        </div>
        <label class="toggle-switch"${foreign ? ' style="pointer-events:none"' : ''}>
          <input type="checkbox" data-flag="${f.flag}" ${f.is_enabled ? 'checked' : ''} ${foreign ? 'disabled' : ''} onchange="_settingsFlagChanged(this)">
          <span class="slider"${foreign ? ' style="opacity:.5"' : ''}></span>
        </label>
      </div>`;
    }).join('');

    // PRO section — PRO tarifda TOGGLE (o'zi yoqadi/o'chiradi); Lite tarifda qulflangan.
    const proNote = document.getElementById('settingsProNote');
    if (proNote) proNote.textContent = isProPlan
      ? 'PRO tarif — bu funksiyalarni o\'zingiz yoqib/o\'chirasiz.'
      : 'Bu funksiyalar PRO tarifda. Ochish uchun tarifni PRO ga o\'tkazing (Super Admin).';
    document.getElementById('settingsProSection').innerHTML = proFlags.map(f => {
      const label = FLAG_LABELS[f.flag] || f.flag;
      if (isProPlan) {
        // PRO tarif → oddiy toggle (FREE kabi), saqlanadi.
        return `<div class="toggle-row" style="padding:.5rem 0;border-bottom:1px solid var(--border2)">
          <div>
            <div class="toggle-label" style="font-size:.875rem">${label}</div>
            <div style="font-size:.75rem;color:var(--text3)">${f.flag}</div>
          </div>
          <label class="toggle-switch">
            <input type="checkbox" data-flag="${f.flag}" data-pro="1" ${f.is_enabled ? 'checked' : ''} onchange="_settingsFlagChanged(this)">
            <span class="slider"></span>
          </label>
        </div>`;
      }
      // Lite tarif → qulflangan (avvalgi ko'rinish).
      return `<div class="toggle-row" style="padding:.5rem 0;border-bottom:1px solid var(--border2);opacity:.65" onclick="toast('Bu funksiya PRO tarifda. Tarifni PRO ga o\\'tkazing','warning')">
        <div>
          <div class="toggle-label" style="font-size:.875rem">🔒 ${label}</div>
          <div style="font-size:.75rem;color:var(--text3)">${f.flag}</div>
        </div>
        <label class="toggle-switch" style="pointer-events:none">
          <input type="checkbox" disabled ${f.is_enabled ? 'checked' : ''}>
          <span class="slider" style="opacity:.5"></span>
        </label>
      </div>`;
    }).join('');

    document.getElementById('settingsLoading').style.display = 'none';
    document.getElementById('settingsContent').style.display = '';
  } catch(e) {
    document.getElementById('settingsLoading').textContent = 'Xatolik: ' + e.message;
  }
}

function _settingsFlagChanged(chk) { /* visual only, saved on button click */ }

async function saveSettingsFlags() {
  const btn = document.getElementById('settingsSaveBtn');
  btn.disabled = true; btn.textContent = 'Saqlanmoqda...';
  const enabled = [], disabled = [];
  // FREE section + PRO section (PRO tarifda toggle ochiq). Lite tarifda PRO input
  // `disabled` bo'ladi → o'tkazib yuboriladi (tarif chegarasi saqlanadi).
  document.querySelectorAll('#settingsFreeSection input[data-flag], #settingsProSection input[data-flag]').forEach(chk => {
    if (chk.disabled) return;   // begona/qulflangan flaglar saqlanmaydi
    if (chk.checked) enabled.push(chk.dataset.flag);
    else disabled.push(chk.dataset.flag);
  });
  try {
    const res = await fetch(`${API_BASE}/cafes/my/features`, {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled, disabled }),
    });
    const data = await res.json();
    if (res.ok && data.ok) toast('Funksiyalar saqlandi. Sahifani yangilang (F5) — yangi flaglar kuchga kiradi.', 'success', 5000);
    else toast(data.detail || 'Xatolik', 'error');
  } catch(e) { toast('Xatolik: ' + e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Saqlash'; }
}


// ═══════════════════════════════════════════════════════
// BOSQICH 20 — Receipt Settings (Chek Sozlamasi)
// ═══════════════════════════════════════════════════════
async function loadReceiptSettings() {
  const s = await apiFetch(`${getApiBase()}/receipt-settings/`);
  if (!s) return;
  document.getElementById('rsStoreName').value = s.store_name || '';
  document.getElementById('rsAddress').value = s.address || '';
  document.getElementById('rsPhone').value = s.phone || '';
  document.getElementById('rsTaxId').value = s.tax_id || '';
  document.getElementById('rsHeader').value = s.header_text || '';
  document.getElementById('rsFooter').value = s.footer_text || '';
  document.getElementById('rsPaper').value = s.paper_width || '80';
  document.getElementById('rsFontSize').value = s.font_size || 'normal';
  document.getElementById('rsQrEnabled').checked = !!s.qr_enabled;
  document.getElementById('rsQrUrlGroup').style.display = s.qr_enabled ? '' : 'none';
  document.getElementById('rsQrUrl').value = s.qr_url || '';
}
async function saveReceiptSettings() {
  const body = {
    store_name: document.getElementById('rsStoreName').value.trim(),
    address: document.getElementById('rsAddress').value.trim(),
    phone: document.getElementById('rsPhone').value.trim(),
    tax_id: document.getElementById('rsTaxId').value.trim(),
    header_text: document.getElementById('rsHeader').value.trim(),
    footer_text: document.getElementById('rsFooter').value.trim(),
    paper_width: +document.getElementById('rsPaper').value,
    font_size: document.getElementById('rsFontSize').value,
    qr_enabled: document.getElementById('rsQrEnabled').checked,
    qr_url: document.getElementById('rsQrUrl').value.trim(),
  };
  await apiFetch(`${getApiBase()}/receipt-settings/`, { method:'PUT', body: JSON.stringify(body) });
  toast('Chek sozlamalari saqlandi!');
  previewReceipt();
}
async function previewReceipt() {
  const data = await apiFetch(`${getApiBase()}/receipt-settings/preview`);
  const box = document.getElementById('receiptPreviewBox');
  if (box && data.html) box.innerHTML = data.html;
}

// ═══════════════════════════════════════════════════════
// BOSQICH 21 — Departments (Bo'limlar tizimi)
// ═══════════════════════════════════════════════════════
const _DEPT_PRESETS = ['#1fb084','#ec4899','#f59e0b','#10b981','#3b82f6','#ef4444','#8b5cf6','#06b6d4','#84cc16','#f97316'];
let _editingDeptId = null;
let drCurrentTab = 'sales';

async function loadDepartments() {
  const grid = document.getElementById('deptsGrid');
  if (!grid) return;
  grid.innerHTML = '<div style="color:var(--text3);padding:2rem;text-align:center">Yuklanmoqda...</div>';
  try {
    const depts = await apiFetch('/departments/');
    if (!depts.length) {
      grid.innerHTML = '<div style="color:var(--text3);padding:2rem;text-align:center;grid-column:1/-1">Hali bo\'lim yo\'q. "Bo\'lim qo\'shish" tugmasi bilan boshlang.</div>';
      return;
    }
    grid.innerHTML = depts.map(d => `
      <div style="background:var(--bg2);border:1px solid var(--border);border-radius:1rem;overflow:hidden">
        <div style="height:8px;background:${d.color||'#1fb084'}"></div>
        <div style="padding:1rem">
          <div style="display:flex;align-items:center;gap:.625rem;margin-bottom:.5rem">
            <span style="font-size:1.5rem">${d.icon||'📦'}</span>
            <div>
              <div style="font-weight:700;font-size:.9375rem">${d.name}</div>
              <div style="font-size:.75rem;color:var(--text3)">${d.description||''}</div>
            </div>
          </div>
          <div style="display:flex;gap:.75rem;font-size:.75rem;color:var(--text2);margin-bottom:.875rem">
            <span>📦 ${d.products_count} mahsulot</span>
            <span>🏷️ ${d.categories_count} kategoriya</span>
            ${!d.is_active?'<span style="color:#ef4444">Nofaol</span>':''}
          </div>
          <div style="display:flex;gap:.5rem">
            <button class="tb-btn" onclick="openDeptModal(${JSON.stringify(d).replace(/"/g,'&quot;')})" style="flex:1">Tahrirlash</button>
            <button class="tb-btn" onclick="deleteDept(${d.id},'${d.name}')" style="color:#ef4444">🗑</button>
          </div>
        </div>
      </div>
    `).join('');
  } catch(e) {
    grid.innerHTML = `<div style="color:#ef4444;padding:2rem;text-align:center;grid-column:1/-1">Xato: ${e.message}</div>`;
  }
}

function openDeptModal(dept = null) {
  _editingDeptId = dept ? dept.id : null;
  document.getElementById('deptModalTitle').textContent = dept ? "Bo'limni tahrirlash" : "Yangi bo'lim";
  document.getElementById('deptName').value  = dept?.name || '';
  document.getElementById('deptDesc').value  = dept?.description || '';
  const color = dept?.color || '#1fb084';
  document.getElementById('deptColor').value    = color;
  document.getElementById('deptColorHex').value = color;
  document.getElementById('deptIcon').value  = dept?.icon || '';
  document.getElementById('deptOrder').value = dept?.display_order ?? 0;
  document.getElementById('deptActive').checked = dept ? dept.is_active : true;
  // Rang presets
  const presetsEl = document.getElementById('deptColorPresets');
  presetsEl.innerHTML = '<span style="font-size:.75rem;color:var(--text3);width:100%;display:block">Tez ranglar:</span>' +
    _DEPT_PRESETS.map(c => `<span onclick="setDeptColor('${c}')" style="width:24px;height:24px;border-radius:50%;background:${c};cursor:pointer;display:inline-block;border:2px solid ${c===color?'#fff':'transparent'}"></span>`).join('');
  // Color picker sync
  document.getElementById('deptColor').oninput = e => {
    document.getElementById('deptColorHex').value = e.target.value;
  };
  document.getElementById('deptColorHex').oninput = e => {
    const v = e.target.value;
    if (/^#[0-9a-fA-F]{6}$/.test(v)) document.getElementById('deptColor').value = v;
  };
  document.getElementById('deptModal').classList.add('open');
  setTimeout(() => document.getElementById('deptName').focus(), 120);
}

function setDeptColor(c) {
  document.getElementById('deptColor').value = c;
  document.getElementById('deptColorHex').value = c;
}

function closeDeptModal() { document.getElementById('deptModal').classList.remove('open'); }

async function saveDept() {
  const name = document.getElementById('deptName').value.trim();
  if (!name) { toast("Nomi kiritilmagan", 'error'); return; }
  const color = document.getElementById('deptColorHex').value || document.getElementById('deptColor').value || '#1fb084';
  const body = {
    name,
    description: document.getElementById('deptDesc').value.trim() || null,
    color,
    icon:          document.getElementById('deptIcon').value.trim() || null,
    display_order: parseInt(document.getElementById('deptOrder').value) || 0,
    is_active:     document.getElementById('deptActive').checked,
  };
  try {
    if (_editingDeptId) {
      await apiFetchPost(`/departments/${_editingDeptId}`, body, 'PUT');
      toast("Bo'lim yangilandi");
    } else {
      await apiFetchPost(`/departments/`, body, 'POST');
      toast("Bo'lim qo'shildi");
    }
    _clearDeptsCache();
    closeDeptModal();
    loadDepartments();
  } catch(e) { toast(e.message, 'error'); }
}

async function deleteDept(id, name) {
  if (!confirm(`"${name}" bo'limini o'chirishni tasdiqlaysizmi?`)) return;
  try {
    const r = await apiFetchPost(`/departments/${id}`, {}, 'DELETE');
    toast(r.message || "O'chirildi");
    _clearDeptsCache();
    loadDepartments();
  } catch(e) { toast(e.message, 'error'); }
}

function openDeptsReportModal() {
  document.getElementById('deptReportModal').style.display = 'flex';
  loadDeptReport('sales');
}
function closeDeptReportModal() {
  document.getElementById('deptReportModal').style.display = 'none';
}

async function loadDeptReport(tab) {
  drCurrentTab = tab;
  document.getElementById('drBtnSales').className     = 'tb-btn' + (tab==='sales'    ?'tb-btn-primary':'');
  document.getElementById('drBtnInventory').className = 'tb-btn' + (tab==='inventory'?'tb-btn-primary':'');
  const body = document.getElementById('deptReportBody');
  body.innerHTML = '<div style="text-align:center;color:var(--text3);padding:2rem">Yuklanmoqda...</div>';
  try {
    if (tab === 'sales') {
      const period = document.getElementById('drPeriod').value;
      const d = await apiFetch(`/departments/report/sales?period=${period}`);
      if (!d.departments?.length) { body.innerHTML = '<p style="color:var(--text3);text-align:center;padding:2rem">Ma\'lumot yo\'q</p>'; return; }
      body.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:.8125rem">
        <thead><tr style="border-bottom:1px solid var(--border2)">
          <th style="text-align:left;padding:.5rem">Bo'lim</th>
          <th style="text-align:right;padding:.5rem">Sotuv</th>
          <th style="text-align:right;padding:.5rem">Foyda</th>
          <th style="text-align:right;padding:.5rem">Marja</th>
        </tr></thead>
        <tbody>
          ${d.departments.map(r=>`<tr style="border-bottom:1px solid var(--border2)">
            <td style="padding:.5rem;display:flex;align-items:center;gap:.5rem">
              <span style="width:12px;height:12px;border-radius:3px;background:${r.color};display:inline-block"></span>
              ${r.icon||'📦'} ${r.name}
            </td>
            <td style="padding:.5rem;text-align:right">${fmtMoney(r.revenue)}</td>
            <td style="padding:.5rem;text-align:right;color:${r.profit>=0?'#10b981':'#ef4444'}">${fmtMoney(r.profit)}</td>
            <td style="padding:.5rem;text-align:right">${r.margin}%</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
    } else {
      const d = await apiFetch('/departments/report/inventory');
      if (!d.length) { body.innerHTML = '<p style="color:var(--text3);text-align:center;padding:2rem">Ma\'lumot yo\'q</p>'; return; }
      body.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:.8125rem">
        <thead><tr style="border-bottom:1px solid var(--border2)">
          <th style="text-align:left;padding:.5rem">Bo'lim</th>
          <th style="text-align:right;padding:.5rem">Mahsulot</th>
          <th style="text-align:right;padding:.5rem">Ombor qiymati</th>
          <th style="text-align:right;padding:.5rem">Kam qoldiq</th>
        </tr></thead>
        <tbody>
          ${d.map(r=>`<tr style="border-bottom:1px solid var(--border2)">
            <td style="padding:.5rem;display:flex;align-items:center;gap:.5rem">
              <span style="width:12px;height:12px;border-radius:3px;background:${r.color};display:inline-block"></span>
              ${r.icon||'📦'} ${r.name}
            </td>
            <td style="padding:.5rem;text-align:right">${r.products}</td>
            <td style="padding:.5rem;text-align:right">${fmtMoney(r.total_value)}</td>
            <td style="padding:.5rem;text-align:right;color:${r.low_stock>0?'#ef4444':'#10b981'}">${r.low_stock}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
    }
  } catch(e) { body.innerHTML = `<p style="color:#ef4444;padding:2rem">${e.message}</p>`; }
}
