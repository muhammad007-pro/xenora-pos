/* XENORA admin — RESTORAN/KAFE (food) moduli (refaktoring 3-bo'lak).
   Kunlik maxsus, ofitsiant reyting, bron, sodiqlik, top taomlar, smena hisoboti,
   oshxona stat, stop-list, xodimlar ovqati. Products/customers/orders CORE'da qoldi.
   CLASSIC <script src>, katta scriptdan OLDIN. Global scope saqlanadi. */
// ── Kunlik maxsus (Specials) ──────────────────────────────────────────────────
let editingSpecialId = null;

async function loadSpecials() {
  const dateEl = document.getElementById('specialsDate');
  if (!dateEl.value) dateEl.value = new Date().toISOString().slice(0,10);
  const d = dateEl.value;
  try {
    const specials = await apiFetch('/daily-specials/?target_date=' + d);
    const body = document.getElementById('specialsBody');
    if (!specials.length) {
      body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Bugungi maxsus taom yo\'q</td></tr>';
      return;
    }
    body.innerHTML = specials.map(s => `<tr>
      <td>
        <div class="td-bold">${s.product_name}</div>
        ${s.category_name ? `<div class="td-sub">${s.category_name}</div>` : ''}
      </td>
      <td class="td-sub">${fmtMoney(s.original_price)} UZS</td>
      <td class="td-gold">${fmtMoney(s.display_price)} UZS${s.special_price&&s.special_price!==s.original_price?'<span class="badge badge-green" style="margin-left:.375rem">Chegirma</span>':''}</td>
      <td class="td-sub" style="max-width:200px">${s.special_description||'—'}</td>
      <td><span class="badge ${s.is_active?'badge-green':'badge-gray'}">${s.is_active?'Faol':'Nofaol'}</span></td>
      <td class="td-actions">
        <button class="act-btn" onclick='openSpecialModal(${JSON.stringify(s)})' title="Tahrirlash"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="1.8"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="1.8"/></svg></button>
        <button class="act-btn danger" onclick="deleteSpecial(${s.id},'${s.product_name.replace(/'/g,"\\'")}')"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" stroke="currentColor" stroke-width="1.8"/></svg></button>
      </td>
    </tr>`).join('');
  } catch (err) { toast(err.message,'error'); }
}
document.addEventListener('DOMContentLoaded', () => {
  const sd = document.getElementById('specialsDate');
  if (sd) sd.addEventListener('change', loadSpecials);
});

function openSpecialModal(special = null) {
  editingSpecialId = special?.id || null;
  document.getElementById('smTitle').textContent = special ? 'Maxsus taom tahrirlash' : "Maxsus taom qo'shish";
  document.getElementById('smDate').value        = special?.date || new Date().toISOString().slice(0,10);
  document.getElementById('smSpecialPrice').value= special?.special_price || '';
  document.getElementById('smDescription').value = special?.special_description || '';
  document.getElementById('smActive').checked    = special ? special.is_active !== false : true;
  _loadCats().then(async cats => {
    const prods = await apiFetch('/products/?limit=100').catch(()=>({items:[]}));
    const list  = prods.items||prods||[];
    const sel = document.getElementById('smProduct');
    sel.innerHTML = '<option value="">— mahsulot tanlang —</option>' +
      list.map(p=>`<option value="${p.id}"${special?.product_id===p.id?' selected':''}>${p.name} — ${fmtMoney(p.price)} UZS</option>`).join('');
  });
  document.getElementById('specialModal').classList.add('open');
  setTimeout(()=>document.getElementById('smProduct')?.focus(),100);
}

function closeSpecialModal() { document.getElementById('specialModal').classList.remove('open'); }

async function saveSpecial() {
  const product_id = parseInt(document.getElementById('smProduct').value);
  if (!product_id) { toast('Mahsulot tanlanmagan','error'); return; }
  const payload = {
    product_id,
    date: document.getElementById('smDate').value,
    special_price: parseFloat(document.getElementById('smSpecialPrice').value)||null,
    special_description: document.getElementById('smDescription').value.trim()||null,
    is_active: document.getElementById('smActive').checked,
  };
  const btn = document.getElementById('smSaveBtn');
  btn.disabled=true; btn.textContent='Saqlanmoqda...';
  try {
    const method = editingSpecialId ? 'PATCH' : 'POST';
    const url    = editingSpecialId ? `${API_BASE}/daily-specials/${editingSpecialId}` : `${API_BASE}/daily-specials/`;
    const res    = await fetch(url, { method, headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    closeSpecialModal();
    toast(editingSpecialId ? 'Yangilandi' : "Qo'shildi",'success');
    loadSpecials();
  } catch (err) { toast(err.message,'error'); }
  finally { btn.disabled=false; btn.textContent='Saqlash'; }
}

async function deleteSpecial(id, name) {
  if (!confirm(`"${name}" ni maxsus ro'yxatdan o'chirmoqchimisiz?`)) return;
  try {
    const res = await fetch(`${API_BASE}/daily-specials/${id}`, { method:'DELETE', headers:{'Authorization':'Bearer '+token} });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast("O'chirildi",'success'); loadSpecials();
  } catch (err) { toast(err.message,'error'); }
}

// ── Ofitsiant reytingi ────────────────────────────────────────────────────────
// ── Bron Kalendar ─────────────────────────────────────────────────────────────
let rcView = 'day';
function rcSetView(v) {
  rcView = v;
  document.getElementById('rcViewDay').style.cssText  = v==='day'  ? 'background:var(--gold);color:#000' : '';
  document.getElementById('rcViewWeek').style.cssText = v==='week' ? 'background:var(--gold);color:#000' : '';
  loadReservCalendar();
}
async function loadReservCalendar() {
  const el = document.getElementById('rcCalendar');
  const dateVal = document.getElementById('rcDate').value || new Date().toISOString().slice(0,10);
  el.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text3)">Yuklanmoqda...</div>';
  try {
    const STATUS = { pending:'Kutmoqda', confirmed:'Tasdiqlangan', cancelled:'Bekor', completed:'Bajarildi' };
    const CLS    = { pending:'badge-amber', confirmed:'badge-green', cancelled:'badge-red', completed:'badge-gray' };
    if (rcView === 'day') {
      const data = await apiFetch('/reservations/?date=' + dateVal + '&page_size=50');
      const items = data.items || [];
      if (!items.length) { el.innerHTML = '<div style="padding:3rem;text-align:center;color:var(--text3)">Bu kunda bron yo\'q</div>'; return; }
      el.innerHTML = `<div class="data-table-wrap"><table>
        <thead><tr><th>Vaqt</th><th>Mijoz</th><th>Stol</th><th>Kishi</th><th>Davomiyligi</th><th>Izoh</th><th>Holat</th></tr></thead>
        <tbody>${items.map(r => `<tr>
          <td class="td-bold">${new Date(r.reservation_time).toLocaleTimeString('uz',{hour:'2-digit',minute:'2-digit'})}</td>
          <td>${r.customer?.name||'—'}</td>
          <td>Stol ${r.table?.number||r.table_id||'—'}</td>
          <td>${r.guests_count||'—'}</td>
          <td>${r.duration_minutes||60} daqiqa</td>
          <td class="td-sub">${r.notes||'—'}</td>
          <td><span class="badge ${CLS[r.status]||'badge-gray'}">${STATUS[r.status]||r.status}</span></td>
        </tr>`).join('')}</tbody>
      </table></div>`;
    } else {
      // Hafta ko'rinishi: 7 kun, paralel so'rovlar
      const base = new Date(dateVal); base.setHours(0,0,0,0);
      const days = Array.from({length:7}, (_,i) => { const d=new Date(base); d.setDate(d.getDate()+i); return d.toISOString().slice(0,10); });
      const results = await Promise.all(days.map(d => apiFetch('/reservations/?date='+d+'&page_size=50').catch(()=>({items:[]}))));
      const weekDays = ['Dushanba','Seshanba','Chorshanba','Payshanba','Juma','Shanba','Yakshanba'];
      el.innerHTML = `<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:.5rem">
        ${days.map((d,i) => {
          const items = results[i].items||[];
          const dt = new Date(d);
          const dayName = weekDays[dt.getDay()===0?6:dt.getDay()-1];
          return `<div style="border:1px solid var(--border);border-radius:.5rem;padding:.5rem;min-height:80px">
            <div style="font-size:.75rem;font-weight:700;color:var(--text2);margin-bottom:.5rem">${dayName}<br><span style="color:var(--text3)">${d.slice(5)}</span></div>
            ${items.length===0 ? '<div style="font-size:.75rem;color:var(--text3)">Bron yo\'q</div>' :
              items.map(r=>`<div style="font-size:.7rem;padding:.2rem .4rem;margin:.2rem 0;border-radius:.25rem;background:${r.status==='confirmed'?'#dcfce7':r.status==='cancelled'?'#fee2e2':'#fef9c3'}">
                ${new Date(r.reservation_time).toLocaleTimeString('uz',{hour:'2-digit',minute:'2-digit'})} ${r.customer?.name||''}
              </div>`).join('')}
          </div>`;
        }).join('')}
      </div>`;
    }
  } catch(err) { el.innerHTML = `<div style="padding:2rem;color:var(--danger)">${err.message}</div>`; }
}
document.addEventListener('DOMContentLoaded', () => {
  const rcDate = document.getElementById('rcDate');
  if (rcDate) rcDate.value = new Date().toISOString().slice(0,10);
});

// ── Sodiqlik darajalari ────────────────────────────────────────────────────────
async function loadLoyaltyTiers() {
  try {
    const tiers = await apiFetch('/analytics/loyalty-tiers');
    const map = { Platinum: 'ltPlatinum', Gold: 'ltGold', Silver: 'ltSilver', Bronze: 'ltBronze' };
    tiers.forEach(t => {
      const el = document.getElementById(map[t.tier]);
      if (el) el.textContent = t.count + ' ta';
    });
    const body = document.getElementById('ltBody');
    const tierColor = { Platinum: '#a855f7', Gold: '#f59e0b', Silver: '#3b82f6', Bronze: '#888' };
    body.innerHTML = tiers.map(t => `<tr>
      <td><span style="font-weight:700;color:${tierColor[t.tier]||'inherit'}">${t.tier}</span></td>
      <td><span class="badge badge-green">${t.discount_pct}% chegirma</span></td>
      <td class="td-sub">${t.threshold > 0 ? fmtMoney(t.threshold)+' UZS dan' : 'Barcha mijozlar'}</td>
      <td style="font-weight:700">${t.count} ta</td>
      <td class="td-gold">${fmtMoney(t.total_spent)} UZS</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

// ── Top taomlar ───────────────────────────────────────────────────────────────
async function loadTopDishes() {
  const period = document.getElementById('tdPeriod')?.value || 'week';
  const sortBy = document.getElementById('tdSort')?.value || 'quantity';
  const now = new Date();
  let dateFrom;
  if (period==='today') dateFrom = new Date(now.getFullYear(),now.getMonth(),now.getDate());
  else if (period==='week') dateFrom = new Date(now - 7*86400000);
  else dateFrom = new Date(now - 30*86400000);
  const params = new URLSearchParams({ date_from: dateFrom.toISOString(), limit: 20 });
  try {
    const data = await apiFetch('/analytics/products?' + params);
    let items = data.products || data || [];
    if (sortBy === 'quantity') items = items.sort((a,b) => (b.quantity||0) - (a.quantity||0));
    else items = items.sort((a,b) => (b.revenue||0) - (a.revenue||0));
    const body = document.getElementById('tdBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const maxQty = Math.max(...items.map(i=>i.quantity||0), 1);
    body.innerHTML = items.map((item, idx) => {
      const pct = Math.round((item.quantity||0)/maxQty*100);
      const medal = idx===0?'🥇':idx===1?'🥈':idx===2?'🥉':'';
      return `<tr>
        <td style="font-size:1.1rem;text-align:center">${medal||idx+1}</td>
        <td class="td-bold">${item.name||'—'}</td>
        <td><span class="badge badge-blue">${item.category||'—'}</span></td>
        <td>
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden;min-width:60px"><div style="width:${pct}%;height:100%;background:var(--gold);border-radius:3px"></div></div>
            <span style="font-weight:700;min-width:40px">${item.quantity||0}</span>
          </div>
        </td>
        <td class="td-gold">${fmtMoney(item.revenue||0)} UZS</td>
        <td class="td-sub">${item.orders_count||0} ta buyurtma</td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

// ── Smena hisoboti (tips + stollar) ──────────────────────────────────────────
async function loadWaiterShift() {
  const period = document.getElementById('wsPeriod')?.value || 'week';
  try {
    const data = await apiFetch('/analytics/waiter-report?period=' + period);
    const body = document.getElementById('wsBody');
    if (!data.length) { body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const maxRev = Math.max(...data.map(w=>w.total_revenue||0), 1);
    body.innerHTML = data.map((w, i) => {
      const pct   = Math.round((w.total_revenue||0)/maxRev*100);
      const medal = i===0?'🥇':i===1?'🥈':i===2?'🥉':'';
      return `<tr>
        <td style="font-size:1.1rem;text-align:center">${medal||i+1}</td>
        <td class="td-bold">${w.name||'—'}</td>
        <td><span style="font-weight:700">${w.tables_count}</span> <span style="color:var(--text2);font-size:.8rem">stol</span></td>
        <td>${w.orders_count||0} ta</td>
        <td>
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden;min-width:60px"><div style="width:${pct}%;height:100%;background:${i===0?'var(--gold)':i===1?'#aaa':i===2?'#cd7f32':'var(--info)'};border-radius:3px"></div></div>
            <span class="td-gold" style="white-space:nowrap">${fmtMoney(w.total_revenue||0)}</span>
          </div>
        </td>
        <td style="color:var(--success);font-weight:600">${w.tips_total>0?'+'+fmtMoney(w.tips_total)+' UZS':'—'}</td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

// ── Kitchen stats ─────────────────────────────────────────────────────────────
async function loadKitchenStats() {
  const days = document.getElementById('ksDays')?.value || '7';
  try {
    const data = await apiFetch('/analytics/kitchen-stats?days=' + days);
    document.getElementById('ksAvg').textContent   = data.overall_avg_minutes ? data.overall_avg_minutes + ' min' : '—';
    document.getElementById('ksTotal').textContent = data.total_orders || 0;
    const body = document.getElementById('ksBody');
    const daily = data.daily_stats || [];
    if (!daily.length) { body.innerHTML='<tr><td colspan="4" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q (buyurtmalarda timer ishlatilmagan)</td></tr>'; return; }
    const maxMin = Math.max(...daily.map(d=>d.avg_minutes||0), 1);
    body.innerHTML = daily.map(d => {
      const pct = Math.round((d.avg_minutes||0)/maxMin*100);
      const color = d.avg_minutes <= 10 ? 'var(--success)' : d.avg_minutes <= 20 ? 'var(--warning)' : 'var(--danger)';
      return `<tr>
        <td class="td-bold">${d.date||'—'}</td>
        <td>${d.count} ta</td>
        <td>
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden;min-width:80px"><div style="width:${pct}%;height:100%;background:${color};border-radius:3px"></div></div>
            <span style="font-weight:700;color:${color};min-width:60px">${d.avg_minutes} min</span>
          </div>
        </td>
        <td><span class="badge ${d.avg_minutes<=10?'badge-green':d.avg_minutes<=20?'badge-amber':'badge-red'}">${d.avg_minutes<=10?'Tez':d.avg_minutes<=20?'Normal':'Sekin'}</span></td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

// ── Stop-list ─────────────────────────────────────────────────────────────────
let slCurrentPage = 1, slFilterAvail = 'all';
function slSetFilter(f) {
  slFilterAvail = f;
  slCurrentPage = 1;
  document.getElementById('slShowAll').style.cssText    = f==='all'     ? 'background:var(--gold);color:#000' : '';
  document.getElementById('slShowUnavail').style.cssText = f==='unavail' ? 'background:var(--gold);color:#000' : '';
  loadStopList();
}
function slPage(dir) { slCurrentPage = Math.max(1, slCurrentPage + dir); loadStopList(); }

async function loadStopList() {
  const search = document.getElementById('slSearch')?.value || '';
  const params = new URLSearchParams({ page: slCurrentPage, page_size: 20, is_active: 'true' });
  if (slFilterAvail === 'unavail') params.set('is_available', 'false');
  if (search) params.set('search', search);
  try {
    const data  = await apiFetch('/products/?' + params);
    const items = data.items || [];
    const total = data.total || 0;
    const unavailCount = items.filter(p => !p.is_available).length;
    document.getElementById('slAvail').textContent   = items.filter(p => p.is_available).length;
    document.getElementById('slUnavail').textContent = unavailCount;
    document.getElementById('slPagInfo').textContent = `${items.length} / ${total} ta`;
    const badge = document.getElementById('stopListBadge');
    if (badge) { badge.textContent = unavailCount; badge.style.display = unavailCount > 0 ? '' : 'none'; }
    const body = document.getElementById('slBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text3)">Mahsulot topilmadi</td></tr>'; return; }
    body.innerHTML = items.map(p => `<tr${!p.is_available?' style="background:rgba(239,68,68,.04)"':''}>
      <td class="td-bold">${p.name||'—'}</td>
      <td><span class="badge badge-blue">${p.category?.name||'—'}</span></td>
      <td class="td-gold">${fmtMoney(p.price||0)} UZS</td>
      <td>${p.is_available
        ? '<span class="badge badge-green">Mavjud</span>'
        : '<span class="badge badge-red">To\'xtatilgan</span>'}</td>
      <td class="td-actions">
        <button class="act-btn ${!p.is_available?'':'btn-danger'}" title="${p.is_available?'Stop-listga qo\'shish':'Sotuvga qaytarish'}" onclick="slToggle(${p.id},${!p.is_available})">
          ${p.is_available
            ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
            : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M9 11l3 3L22 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'}
        </button>
      </td>
    </tr>`).join('');
    document.getElementById('slPrevBtn').disabled = slCurrentPage <= 1;
    document.getElementById('slNextBtn').disabled = items.length < 20;
  } catch(err) { toast(err.message,'error'); }
}

async function slToggle(productId, newAvail) {
  try {
    const res = await fetch(`${API_BASE}/products/${productId}/availability?is_available=${newAvail}`, {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    const data = await res.json();
    toast(newAvail ? `"${data.name}" sotuvga qaytarildi` : `"${data.name}" stop-listga qo'shildi`, 'success');
    loadStopList();
    updateStopListBadge();
  } catch(err) { toast(err.message,'error'); }
}

async function updateStopListBadge() {
  try {
    const data = await apiFetch('/products/?is_available=false&page_size=1');
    const cnt  = data.total || 0;
    const badge = document.getElementById('stopListBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt > 0 ? '' : 'none'; }
  } catch {}
}

// ── Xodimlar ovqati (Staff Meal) ──────────────────────────────────────────────

let smPage = 1;

async function smLoadSelects() {
  try {
    const [empData, prodData] = await Promise.all([
      apiFetch('/employees/list?is_active=true&page_size=100'),
      apiFetch('/products/?is_active=true&page_size=200'),
    ]);
    const employees = empData.items || [];
    const products  = prodData.items || [];

    const empOpts = employees.map(e =>
      `<option value="${e.id}">${e.full_name}${e.position ? ' ('+e.position+')' : ''}</option>`
    ).join('');
    document.getElementById('smEmployee').innerHTML    = '<option value="">— Xodimni tanlang —</option>' + empOpts;
    document.getElementById('smFilterEmp').innerHTML   = '<option value="">Barcha xodimlar</option>' + empOpts;

    const prodOpts = products.map(p =>
      `<option value="${p.id}">${p.name}</option>`
    ).join('');
    document.getElementById('smProduct').innerHTML = '<option value="">— Taomni tanlang —</option>' + prodOpts;
  } catch(err) { console.error('smLoadSelects:', err); }
}

async function smCreate() {
  const employee_id = parseInt(document.getElementById('smEmployee').value);
  const product_id  = parseInt(document.getElementById('smProduct').value);
  const quantity    = parseFloat(document.getElementById('smQty').value) || 1;
  const notes       = document.getElementById('smNotes').value.trim();

  if (!employee_id) { toast('Xodimni tanlang', 'error'); return; }
  if (!product_id)  { toast('Taomni tanlang', 'error'); return; }
  if (quantity <= 0) { toast('Porsiya 0 dan katta bo\'lsin', 'error'); return; }

  try {
    await apiFetch('/staff-meals/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ employee_id, product_id, quantity, notes: notes || null }),
    });
    toast('Xodim ovqati qayd etildi', 'success');
    document.getElementById('smEmployee').value = '';
    document.getElementById('smProduct').value  = '';
    document.getElementById('smQty').value      = '1';
    document.getElementById('smNotes').value    = '';
    smPage = 1;
    loadStaffMeals();
  } catch(err) { toast(err.message, 'error'); }
}

function smClearFilter() {
  document.getElementById('smFilterEmp').value = '';
  document.getElementById('smDateFrom').value  = '';
  document.getElementById('smDateTo').value    = '';
  smPage = 1;
  loadStaffMeals();
}

function smChangePage(dir) { smPage = Math.max(1, smPage + dir); loadStaffMeals(); }

async function loadStaffMeals() {
  const empId    = document.getElementById('smFilterEmp')?.value || '';
  const dateFrom = document.getElementById('smDateFrom')?.value || '';
  const dateTo   = document.getElementById('smDateTo')?.value   || '';

  const params = new URLSearchParams({ page: smPage, page_size: 20 });
  if (empId)    params.set('employee_id', empId);
  if (dateFrom) params.set('date_from', dateFrom);
  if (dateTo)   params.set('date_to', dateTo);

  // Oylik umumiy stats (joriy oy)
  const now = new Date();
  const firstDay = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0,10);
  const lastDay  = new Date(now.getFullYear(), now.getMonth()+1, 0).toISOString().slice(0,10);
  const repParams = new URLSearchParams({ date_from: firstDay, date_to: lastDay });
  if (empId) repParams.set('employee_id', empId);

  try {
    const [data, report] = await Promise.all([
      apiFetch('/staff-meals/?' + params),
      apiFetch('/staff-meals/report?' + repParams),
    ]);

    document.getElementById('smTotalCount').textContent = report.total_count ?? '—';
    document.getElementById('smTotalCost').textContent  = fmtMoney(report.total_cost || 0) + ' UZS';
    document.getElementById('smFilterCount').textContent = data.total ?? '—';

    const body = document.getElementById('smBody');
    const items = data.items || [];
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Qaydlar topilmadi</td></tr>';
    } else {
      body.innerHTML = items.map(m => `<tr>
        <td>${m.created_at ? new Date(m.created_at).toLocaleString('uz-UZ',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '—'}</td>
        <td class="td-bold">${m.employee_name||'—'}</td>
        <td><span class="badge badge-blue">${m.employee_position||'—'}</span></td>
        <td>${m.product_name||'—'}</td>
        <td>${m.quantity}</td>
        <td>${fmtMoney(m.cost_price||0)} UZS</td>
        <td class="td-gold">${fmtMoney(m.total_cost||0)} UZS</td>
        <td class="td-actions">
          <button class="act-btn btn-danger" title="O'chirish" onclick="smDelete(${m.id})">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><polyline points="3 6 5 6 21 6" stroke="currentColor" stroke-width="2"/><path d="M19 6l-1 14H6L5 6" stroke="currentColor" stroke-width="2"/><path d="M10 11v6M14 11v6M9 6V4h6v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          </button>
        </td>
      </tr>`).join('');
    }
    document.getElementById('smPagInfo').textContent = `${items.length} / ${data.total} ta`;
    document.getElementById('smPrevBtn').disabled = smPage <= 1;
    document.getElementById('smNextBtn').disabled = items.length < 20;

    // Xodim bo'yicha hisobot
    const repBody = document.getElementById('smReportBody');
    const byEmp = report.by_employee || [];
    if (!byEmp.length) {
      repBody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:1.5rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>';
    } else {
      repBody.innerHTML = byEmp.map((e, i) => `<tr>
        <td>${i+1}</td>
        <td class="td-bold">${e.employee_name}</td>
        <td><span class="badge badge-blue">${e.employee_position||'—'}</span></td>
        <td>${e.count}</td>
        <td class="td-gold">${fmtMoney(e.total_cost)} UZS</td>
      </tr>`).join('');
    }
  } catch(err) { toast(err.message, 'error'); }
}

async function smDelete(id) {
  if (!confirm('Yozuvni o\'chirishni tasdiqlaysizmi? Ombor qaytarilmaydi.')) return;
  try {
    await apiFetch(`/staff-meals/${id}`, { method: 'DELETE' });
    toast('Yozuv o\'chirildi', 'success');
    loadStaffMeals();
  } catch(err) { toast(err.message, 'error'); }
}

