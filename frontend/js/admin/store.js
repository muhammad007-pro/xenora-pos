/* XENORA admin — MAGAZIN/SUPERMARKET + NASIYA moduli (refaktoring 3-bo'lak).
   CLASSIC <script src>, katta scriptdan OLDIN. Global scope saqlanadi. */
// ── Magazin/Supermarket sahifalari ────────────────────────────────────────────

async function loadStoreTop() {
  const period = document.getElementById('stTopPeriod')?.value || 'week';
  const sortBy = document.getElementById('stTopSort')?.value || 'quantity';
  const now = new Date();
  let dateFrom;
  if (period==='today') dateFrom = new Date(now.getFullYear(),now.getMonth(),now.getDate());
  else if (period==='week') dateFrom = new Date(now - 7*86400000);
  else dateFrom = new Date(now - 30*86400000);
  const params = new URLSearchParams({ date_from: dateFrom.toISOString(), limit: 20 });
  try {
    const data = await apiFetch('/analytics/products?' + params);
    let items = data.products || data || [];
    if (sortBy === 'quantity') items = items.sort((a,b) => (b.quantity||0)-(a.quantity||0));
    else items = items.sort((a,b) => (b.revenue||0)-(a.revenue||0));
    const body = document.getElementById('stTopBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const maxQ = Math.max(...items.map(i=>i.quantity||0), 1);
    body.innerHTML = items.map((it, idx) => {
      const pct   = Math.round((it.quantity||0)/maxQ*100);
      const medal = idx===0?'🥇':idx===1?'🥈':idx===2?'🥉':'';
      return `<tr>
        <td style="font-size:1.1rem;text-align:center">${medal||idx+1}</td>
        <td class="td-bold">${it.name||'—'}</td>
        <td><span class="badge badge-blue">${it.category||'—'}</span></td>
        <td>
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden;min-width:60px"><div style="width:${pct}%;height:100%;background:var(--gold);border-radius:3px"></div></div>
            <span style="font-weight:700;min-width:40px">${it.quantity||0}</span>
          </div>
        </td>
        <td class="td-gold">${fmtMoney(it.revenue||0)} UZS</td>
        <td class="td-sub">${it.orders_count||0} ta</td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadStoreMargin() {
  const period = document.getElementById('smPeriod')?.value || 'week';
  try {
    const data = await apiFetch('/analytics/store-margin?period=' + period);
    document.getElementById('smRevenue').textContent = fmtMoney(data.total_revenue||0) + ' UZS';
    document.getElementById('smProfit').textContent  = fmtMoney(data.total_profit||0) + ' UZS';
    document.getElementById('smMargin').textContent  = (data.overall_margin_pct||0) + '%';
    const body  = document.getElementById('smBody');
    const items = data.items || [];
    if (!items.length) { body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    body.innerHTML = items.map(it => {
      const marColor = it.margin_pct >= 30 ? 'var(--success)' : it.margin_pct >= 10 ? 'var(--warning)' : 'var(--danger)';
      return `<tr>
        <td class="td-bold">${it.name||'—'}</td>
        <td>${fmtMoney(it.sell_price||0)} UZS</td>
        <td class="td-sub">${it.cost_price>0 ? fmtMoney(it.cost_price)+' UZS' : '—'}</td>
        <td>${it.qty_sold||0} ta</td>
        <td style="color:var(--success);font-weight:700">${fmtMoney(it.profit||0)} UZS</td>
        <td><span class="badge ${it.margin_pct>=30?'badge-green':it.margin_pct>=10?'badge-amber':'badge-red'}">${it.margin_pct}%</span></td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadStoreCats() {
  const period = document.getElementById('scPeriod')?.value || 'week';
  const now = new Date();
  let dateFrom;
  if (period==='today') dateFrom = new Date(now.getFullYear(),now.getMonth(),now.getDate());
  else if (period==='week') dateFrom = new Date(now - 7*86400000);
  else dateFrom = new Date(now - 30*86400000);
  try {
    const data = await apiFetch('/analytics/categories?date_from=' + dateFrom.toISOString());
    const cats = data.categories || data || [];
    const body = document.getElementById('scBody');
    if (!cats.length) { body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const totalRev = cats.reduce((s,c) => s+(c.revenue||0), 0) || 1;
    const maxRev   = Math.max(...cats.map(c=>c.revenue||0), 1);
    const colors   = ['#3b82f6','#f59e0b','#10b981','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316'];
    body.innerHTML = cats.map((cat, i) => {
      const pct  = Math.round((cat.revenue||0)/maxRev*100);
      const share = ((cat.revenue||0)/totalRev*100).toFixed(1);
      return `<tr>
        <td style="text-align:center;font-weight:700;color:${colors[i%colors.length]}">${i+1}</td>
        <td class="td-bold" style="color:${colors[i%colors.length]}">${cat.name||'—'}</td>
        <td class="td-sub">${cat.products_count||'—'} ta</td>
        <td>${cat.quantity||0} ta</td>
        <td>
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:6px;background:var(--bg4);border-radius:3px;overflow:hidden;min-width:80px"><div style="width:${pct}%;height:100%;background:${colors[i%colors.length]};border-radius:3px"></div></div>
            <span class="td-gold" style="white-space:nowrap">${fmtMoney(cat.revenue||0)}</span>
          </div>
        </td>
        <td style="font-weight:700;color:${colors[i%colors.length]}">${share}%</td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadStoreCashier() {
  const period = document.getElementById('caPeriod')?.value || 'week';
  try {
    const data = await apiFetch('/analytics/cashier-report?period=' + period);
    const body = document.getElementById('caBody');
    if (!data.length) { body.innerHTML='<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const maxTotal = Math.max(...data.map(c=>c.total||0), 1);
    body.innerHTML = data.map((c, i) => {
      const pct = Math.round((c.total||0)/maxTotal*100);
      return `<tr>
        <td class="td-bold">${c.name||'—'}</td>
        <td>${c.transactions||0} ta</td>
        <td>
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden;min-width:60px"><div style="width:${pct}%;height:100%;background:${i===0?'var(--gold)':'var(--info)'};border-radius:3px"></div></div>
            <span class="td-gold" style="white-space:nowrap">${fmtMoney(c.total||0)}</span>
          </div>
        </td>
        <td>${fmtMoney(c.cash||0)}</td>
        <td>${fmtMoney(c.card||0)}</td>
        <td>${fmtMoney((c.click||0)+(c.payme||0)+(c.qr||0))}</td>
        <td style="color:var(--success)">${c.tips>0?'+'+fmtMoney(c.tips):'—'}</td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

let plCurrentPage = 1;
function plPage(dir) { plCurrentPage = Math.max(1, plCurrentPage + dir); loadStorePriceList(); }

async function loadStorePriceList() {
  const search = document.getElementById('plSearch')?.value || '';
  const params = new URLSearchParams({ page: plCurrentPage, page_size: 20, is_active: 'true' });
  if (search) params.set('search', search);
  try {
    const data  = await apiFetch('/products/?' + params);
    const items = data.items || [];
    const total = data.total || 0;
    document.getElementById('plPagInfo').textContent = `${items.length} / ${total} ta`;
    const body = document.getElementById('plBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Mahsulot topilmadi</td></tr>'; return; }
    body.innerHTML = items.map(p => {
      const sell = p.price || 0, cost = p.cost_price || 0;
      const margin = sell - cost;
      const marPct = sell > 0 && cost > 0 ? ((margin/sell)*100).toFixed(1) : '—';
      const marColor = parseFloat(marPct) >= 30 ? 'var(--success)' : parseFloat(marPct) >= 10 ? 'var(--warning)' : cost > 0 ? 'var(--danger)' : 'var(--text2)';
      return `<tr>
        <td class="td-bold">${p.name||'—'}</td>
        <td><span class="badge badge-blue">${p.category?.name||'—'}</span></td>
        <td class="td-sub">${cost>0?fmtMoney(cost)+' UZS':'—'}</td>
        <td class="td-gold" style="font-weight:700">${fmtMoney(sell)} UZS</td>
        <td style="color:var(--success)">${cost>0?fmtMoney(margin)+' UZS':'—'}</td>
        <td style="color:${marColor};font-weight:700">${marPct !== '—' ? marPct+'%' : '—'}</td>
      </tr>`;
    }).join('');
    document.getElementById('plPrevBtn').disabled = plCurrentPage <= 1;
    document.getElementById('plNextBtn').disabled = items.length < 20;
  } catch(err) { toast(err.message,'error'); }
}

let discCurrentPage = 1, discFilter = null;
function discSetFilter(f) {
  discFilter = f;
  discCurrentPage = 1;
  document.getElementById('discShowAll').style.cssText      = f===null ? 'background:var(--gold);color:#000' : '';
  document.getElementById('discShowActive').style.cssText   = f===true  ? 'background:var(--gold);color:#000' : '';
  document.getElementById('discShowInactive').style.cssText = f===false ? 'background:var(--gold);color:#000' : '';
  loadStoreDiscounts();
}
function discPage(dir) { discCurrentPage = Math.max(1, discCurrentPage+dir); loadStoreDiscounts(); }

async function loadStoreDiscounts() {
  const params = new URLSearchParams({ page: discCurrentPage, page_size: 20 });
  if (discFilter !== null) params.set('is_active', discFilter);
  try {
    const data  = await apiFetch('/discounts/?' + params);
    const items = data.items || [];
    _discItems = items;   // #34: tahrir uchun cache
    const total = data.total || 0;
    document.getElementById('discTotal').textContent  = total;
    document.getElementById('discActive').textContent = items.filter(d=>d.is_active).length;
    document.getElementById('discPagInfo').textContent = `${items.length} / ${total} ta`;
    const badge = document.getElementById('activeDiscountsBadge');
    if (badge) { const ac = items.filter(d=>d.is_active).length; badge.textContent=ac; badge.style.display=ac>0?'':'none'; }
    const body = document.getElementById('discBody');
    // FAZA 4: bo'sh bo'lsa ham aksiyalar (promotions) qo'shiladi — bitta birlashgan ro'yxat.
    let _rows = items.map(d => {
      const typeMap = { percentage:'%', fixed:"so'm" };
      const val = d.type==='percentage' ? d.value+'%' : fmtMoney(d.value)+' UZS';
      const from = d.valid_from ? d.valid_from.slice(0,10) : '∞';
      const to   = d.valid_to   ? d.valid_to.slice(0,10)   : '∞';
      return `<tr>
        <td class="td-bold">${d.name||'—'}</td>
        <td><span class="badge badge-blue">${d.type==='percentage'?'Foiz':'Belgilangan'}</span></td>
        <td style="font-weight:700;color:var(--gold)">${val}</td>
        <td class="td-sub">${from} → ${to}</td>
        <td class="td-sub">${d.used_count||0} / ${d.usage_limit||'∞'}</td>
        <td>${d.is_active?'<span class="badge badge-green">Faol</span>':'<span class="badge badge-gray">Nofaol</span>'}</td>
        <td class="td-actions">
          <button class="act-btn" title="Tahrirlash" onclick="editDiscount(${d.id})" style="margin-right:.25rem">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7M18.5 2.5a2.12 2.12 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button class="act-btn" title="${d.is_active?'O\'chirish (nofaol)':'Yoqish'}" onclick="discToggle(${d.id},${!d.is_active})">
            ${d.is_active
              ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
              : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M9 11l3 3L22 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'}
          </button>
          <button class="act-btn" title="Butunlay o'chirish" onclick="discDelete(${d.id})" style="color:var(--danger);margin-left:.25rem">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2m2 0v14a1 1 0 01-1 1H6a1 1 0 01-1-1V6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          </button>
        </td>
      </tr>`;
    }).join('');
    // FAZA 4: aksiyalarni (flash/happy-hour/2 ol 1 ol/miqdor/summa) shu ro'yxatga qo'shamiz.
    _rows += await _promotionRows();
    body.innerHTML = _rows || '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Chegirma/aksiya topilmadi</td></tr>';
    document.getElementById('discPrevBtn').disabled = discCurrentPage <= 1;
    document.getElementById('discNextBtn').disabled = items.length < 20;
  } catch(err) { toast(err.message,'error'); }
}

// FAZA 4: aksiyalar (Promotion) — birlashgan hub ro'yxati uchun qatorlar. Tur belgisi + CRUD /promotions/.
const _PROMO_LABEL = { flash_price:'⚡ Flash', min_amount:'💰 Summa', min_qty_discount:'📦 Miqdor', buy_x_get_y:'🎁 2 ol 1 ol' };
async function _promotionRows() {
  try {
    const data = await apiFetch('/promotions/?page_size=200');
    const promos = (data && data.items) || (Array.isArray(data) ? data : []);
    if (!promos.length) return '';
    return promos.map(p => {
      let val = '—';
      if (p.promo_type === 'flash_price') val = fmtMoney(p.flash_price||0) + ' UZS';
      else if (p.promo_type === 'buy_x_get_y') val = `${p.buy_qty} ol ${p.free_product_id ? ((p.free_qty_per_set||1)+'× '+(p.free_product_name||'boshqa')) : (p.get_qty||1)+' bepul'}`;
      else val = (p.discount_type==='percentage' ? (p.discount_value||0)+'%' : fmtMoney(p.discount_value||0)+' UZS')
               + (p.promo_type==='min_amount' ? ` (≥${fmtMoney(p.min_purchase_amount||0)})` : p.promo_type==='min_qty_discount' ? ` (≥${p.min_purchase_qty||0} dona)` : '');
      const from = p.start_date ? p.start_date.slice(0,10) : '∞';
      const to   = p.end_date   ? p.end_date.slice(0,10)   : '∞';
      const hh   = (p.time_from && p.time_to) ? ` ${p.time_from}-${p.time_to}` : '';
      return `<tr>
        <td class="td-bold">${p.name||'—'}</td>
        <td><span class="badge badge-gold">${_PROMO_LABEL[p.promo_type]||p.promo_type}</span></td>
        <td style="font-weight:700;color:var(--gold)">${val}</td>
        <td class="td-sub">${from} → ${to}${hh}</td>
        <td class="td-sub">${p.used_count||0} / ${p.usage_limit||'∞'}</td>
        <td>${p.is_active?'<span class="badge badge-green">Faol</span>':'<span class="badge badge-gray">Nofaol</span>'}</td>
        <td class="td-actions">
          <button class="act-btn" title="Tahrirlash (aksiya)" onclick="location.href='promotions.html?edit=${p.id}'" style="margin-right:.25rem">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7M18.5 2.5a2.12 2.12 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button class="act-btn" title="${p.is_active?'O\'chirish (nofaol)':'Yoqish'}" onclick="promoToggle(${p.id},${!p.is_active})">
            ${p.is_active
              ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
              : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M9 11l3 3L22 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'}
          </button>
          <button class="act-btn" title="Butunlay o'chirish" onclick="promoDelete(${p.id})" style="color:var(--danger);margin-left:.25rem">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2m2 0v14a1 1 0 01-1 1H6a1 1 0 01-1-1V6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          </button>
        </td>
      </tr>`;
    }).join('');
  } catch(e) { return ''; }
}

async function promoToggle(id, newActive) {
  try {
    const res = await fetch(`${API_BASE}/promotions/${id}`, {
      method: 'PUT',
      headers: { 'Authorization': 'Bearer '+token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: newActive }),
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast(newActive ? 'Aksiya yoqildi' : "Aksiya o'chirildi", 'success');
    loadStoreDiscounts();
  } catch(err) { toast(err.message,'error'); }
}

async function promoDelete(id) {
  if (!confirm("Aksiya butunlay o'chirilsinmi?")) return;
  try {
    const res = await fetch(`${API_BASE}/promotions/${id}`, {
      method: 'DELETE', headers: { 'Authorization': 'Bearer '+token },
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast("Aksiya o'chirildi", 'success');
    loadStoreDiscounts();
  } catch(err) { toast(err.message,'error'); }
}
window.promoToggle = promoToggle;
window.promoDelete = promoDelete;

async function discToggle(discId, newActive) {
  try {
    const res = await fetch(`${API_BASE}/discounts/${discId}/toggle`, {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer '+token }
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast(newActive ? 'Chegirma yoqildi' : "Chegirma o'chirildi", 'success');
    loadStoreDiscounts();
    updateActiveDiscountsBadge();
  } catch(err) { toast(err.message,'error'); }
}

async function updateActiveDiscountsBadge() {
  try {
    const data = await apiFetch('/discounts/active');
    const cnt  = Array.isArray(data) ? data.length : 0;
    const badge = document.getElementById('activeDiscountsBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt > 0 ? '' : 'none'; }
  } catch {}
}

// ══ #34: Chegirma yaratish/tahrirlash (POST + PUT /discounts/) ══════════════════
let _dscProducts = [];       // datalist uchun mahsulotlar (nom → id)
let _discItems = [];         // joriy ro'yxat (tahrir uchun cache)
let _editDiscountId = null;  // tahrir rejimi: id yoki null (yaratish)
let _editDiscount = null;    // tahrirlanayotgan chegirma (is_active taqqoslash uchun)

async function openDiscountModal(edit) {
  _editDiscountId = edit ? edit.id : null;
  _editDiscount   = edit || null;
  ['dscName','dscValue','dscMinAmount','dscFrom','dscTo','dscProductSearch'].forEach(id => { const el=document.getElementById(id); if (el) el.value=''; });
  document.getElementById('dscTarget').value = 'all';
  document.getElementById('dscCategory').value = '';
  document.getElementById('dscType').value = 'percentage';
  document.getElementById('dscActive').checked = true;
  document.getElementById('dscModalTitle').textContent = edit ? 'Chegirmani tahrirlash' : 'Yangi chegirma';
  await _loadDiscountPickers();   // pickerlar tayyor bo'lgach prefill
  if (edit) {
    document.getElementById('dscName').value      = edit.name || '';
    document.getElementById('dscType').value      = edit.type || 'percentage';
    document.getElementById('dscValue').value     = edit.value ?? '';
    document.getElementById('dscMinAmount').value = edit.min_order_amount || '';
    document.getElementById('dscFrom').value      = edit.valid_from ? edit.valid_from.slice(0,10) : '';
    document.getElementById('dscTo').value        = edit.valid_to   ? edit.valid_to.slice(0,10)   : '';
    document.getElementById('dscActive').checked  = edit.is_active !== false;
    if (edit.product_id) {
      document.getElementById('dscTarget').value = 'product';
      const p = _dscProducts.find(x => x.id === edit.product_id);
      document.getElementById('dscProductSearch').value = p ? p.name : '';
    } else if (edit.category_id) {
      document.getElementById('dscTarget').value = 'category';
      document.getElementById('dscCategory').value = edit.category_id;
    } else {
      document.getElementById('dscTarget').value = 'all';
    }
  }
  discTargetChange();
  openModal('discountModal');
}

function editDiscount(id) {
  const d = _discItems.find(x => x.id === id);
  if (d) openDiscountModal(d);
  else toast('Chegirma topilmadi', 'error');
}

function discTargetChange() {
  const t = document.getElementById('dscTarget').value;
  document.getElementById('dscCategoryGroup').style.display = t === 'category' ? '' : 'none';
  document.getElementById('dscProductGroup').style.display  = t === 'product'  ? '' : 'none';
}

async function _loadDiscountPickers() {
  try {
    const cats = await apiFetch('/categories/all') || [];
    const sel = document.getElementById('dscCategory');
    sel.innerHTML = '<option value="">— Tanlang —</option>' +
      cats.map(c => `<option value="${c.id}">${(c.name||'').replace(/"/g,'&quot;')}</option>`).join('');
  } catch { /* kategoriya olinmasa bo'sh */ }
  try {
    _dscProducts = await apiFetch('/products/all') || [];
    const dl = document.getElementById('dscProductList');
    if (dl) dl.innerHTML = _dscProducts.map(p => `<option value="${(p.name||'').replace(/"/g,'&quot;')}">`).join('');
  } catch { _dscProducts = []; }
}

async function saveDiscount() {
  const name  = document.getElementById('dscName').value.trim();
  const target= document.getElementById('dscTarget').value;
  const type  = document.getElementById('dscType').value;
  const value = parseFloat(document.getElementById('dscValue').value);
  if (!name)          { toast('Chegirma nomini kiriting', 'error'); return; }
  if (!(value > 0))   { toast("Qiymat musbat bo'lsin", 'error'); return; }
  if (type === 'percentage' && value > 100) { toast('Foiz 0–100 orasida bo\'lsin', 'error'); return; }

  let product_id = null, category_id = null;
  if (target === 'category') {
    category_id = parseInt(document.getElementById('dscCategory').value) || null;
    if (!category_id) { toast('Kategoriyani tanlang', 'error'); return; }
  } else if (target === 'product') {
    const nm = document.getElementById('dscProductSearch').value.trim();
    const p  = _dscProducts.find(x => (x.name || '').trim() === nm);
    if (!p) { toast("Mahsulotni ro'yxatdan tanlang", 'error'); return; }
    product_id = p.id;
  }

  const minAmount = parseFloat(document.getElementById('dscMinAmount').value) || 0;
  const fromV = document.getElementById('dscFrom').value;
  const toV   = document.getElementById('dscTo').value;
  if (fromV && toV && fromV > toV) { toast("Muddat noto'g'ri (boshlanish > tugash)", 'error'); return; }

  const payload = {
    name, type, value, product_id, category_id,
    min_order_amount: minAmount,
    valid_from: fromV ? new Date(fromV + 'T00:00:00').toISOString() : null,
    valid_to:   toV   ? new Date(toV   + 'T23:59:59').toISOString() : null,
  };

  const isEdit   = _editDiscountId != null;
  const wantActive = document.getElementById('dscActive').checked;
  try {
    const saved = isEdit
      ? await apiFetchPost(`/discounts/${_editDiscountId}`, payload, 'PUT')
      : await apiFetchPost('/discounts/', payload, 'POST');
    // is_active: PUT/POST uni o'zgartirmaydi (default faol) — kerak bo'lsa toggle.
    const curActive = isEdit ? (_editDiscount && _editDiscount.is_active !== false) : true;
    const targetId  = isEdit ? _editDiscountId : (saved && saved.id);
    if (curActive !== wantActive && targetId) {
      try { await fetch(`${API_BASE}/discounts/${targetId}/toggle`, { method: 'PATCH', headers: { Authorization: 'Bearer ' + token } }); } catch {}
    }
    closeModal('discountModal');
    toast(isEdit ? 'Chegirma yangilandi' : 'Chegirma yaratildi', 'success');
    _editDiscountId = null; _editDiscount = null;
    loadStoreDiscounts();
    updateActiveDiscountsBadge();
  } catch (e) { toast(e.message || 'Chegirma saqlanmadi', 'error'); }
}

async function discDelete(id) {
  if (!confirm("Chegirma o'chirilsinmi?")) return;
  try {
    const res = await fetch(`${API_BASE}/discounts/${id}`, { method: 'DELETE', headers: { Authorization: 'Bearer ' + token } });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Xato'); }
    toast("Chegirma o'chirildi", 'success');
    loadStoreDiscounts();
    updateActiveDiscountsBadge();
  } catch (e) { toast(e.message || "O'chirilmadi", 'error'); }
}

// ══ BOSQICH 19: NASIYA / QARZ DAFTAR ══════════════════════════════════════════
//
// TUZATISH (mijozda topildi — Fazza Parfum): bu blokda 12 marta `showAlert(...)`
// chaqirilardi, lekin bunday funksiya butun frontendda YO'Q (admin panelining
// xabar funksiyasi — `toast()`, core.js:10). Har chaqiruv ReferenceError berardi:
//   - validatsiya shoxida (try'dan TASHQARIDA) tugma butunlay "o'lik" bo'lardi —
//     na xabar, na so'rov. Serverда 7 kun ichida BITTA ham POST /debts/ yo'q edi.
//   - muvaffaqiyat shoxida esa xato `catch` ga tushib, catch ichidagi showAlert
//     YANA yiqilardi -> ro'yxat yangilanmasdi.
// Endi hamma joyda `toast()` (imzosi bir xil: msg, type).
let debtCurrentPage = 1;
let currentDebtId = null;
let _debtCustomers = [];   // BOSQICH 13: yuklangan mijozlar (mahalliy dublikat tekshiruvi uchun)

async function updateDebtBadge() {
  try {
    const data = await apiFetch('/debts/summary');
    const badge = document.getElementById('debtBadge');
    const n = (data.open_count || 0) + (data.partial_count || 0);
    if (badge) { badge.textContent = n; badge.style.display = n > 0 ? '' : 'none'; }
  } catch {}
}

async function loadDebtSummary() {
  try {
    const d = await apiFetch('/debts/summary');
    document.getElementById('dTotalDebtors').textContent = d.total_debtors || 0;
    document.getElementById('dTotalDebt').textContent = fmtMoney(d.total_debt||0) + ' UZS';
    document.getElementById('dOverdue').textContent = fmtMoney(d.total_overdue||0) + ' UZS';
    document.getElementById('dPartial').textContent = d.partial_count || 0;
  } catch {}
}

async function loadDebts() {
  const status = document.getElementById('dFilterStatus')?.value || '';
  const overdueOnly = document.getElementById('dOverdueOnly')?.checked ? '&overdue_only=true' : '';
  const url = `/debts/?page=${debtCurrentPage}&page_size=50${status ? '&status='+status : ''}${overdueOnly}`;
  const body = document.getElementById('debtBody');
  body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Yuklanmoqda...</td></tr>';
  try {
    const data = await apiFetch(url);
    const list = Array.isArray(data) ? data : [];
    if (!list.length) {
      body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Qarz yo\'q</td></tr>';
      return;
    }
    const today = new Date().toISOString().slice(0,10);
    body.innerHTML = list.map(d => {
      const overdue = d.due_date && d.due_date < today && d.status !== 'paid';
      const statusBadge = d.status === 'paid'
        ? '<span style="color:var(--success);font-size:.75rem">✓ To\'langan</span>'
        : d.status === 'partial'
        ? '<span style="color:var(--warning);font-size:.75rem">⏳ Qisman</span>'
        : '<span style="color:var(--red);font-size:.75rem">● Ochiq</span>';
      return `<tr>
        <td style="font-size:.75rem;color:var(--text3)">${fmtDate2(d.created_at)}</td>
        <td>${d.customer ? escH(d.customer.name) : '—'}<br><span style="font-size:.7rem;color:var(--text3)">${d.customer?.phone||''}</span></td>
        <td style="color:var(--text2)">${fmtMoney(d.amount)} UZS</td>
        <td style="color:var(--success)">${fmtMoney(d.paid_amount)} UZS</td>
        <td style="color:var(--red);font-weight:600">${fmtMoney(d.remaining)} UZS</td>
        <td>${d.due_date ? '<span style="color:'+(overdue?'var(--red)':'var(--text2)')+'">'+d.due_date+'</span>' : '—'}</td>
        <td>${statusBadge}</td>
        <td style="display:flex;gap:.375rem;flex-wrap:wrap">
          ${d.status !== 'paid' ? `<button class="tb-btn tb-btn-sm" onclick="openPayDebt(${d.id},${d.remaining})">To'lash</button>` : ''}
        </td>
      </tr>`;
    }).join('');
    document.getElementById('debtPagInfo').textContent = `${list.length} ta yozuv`;
  } catch (e) {
    body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--red)">Yuklab bo\'lmadi</td></tr>';
  }
}

function debtPageNav(dir) { debtCurrentPage = Math.max(1, debtCurrentPage + dir); loadDebts(); }

async function openDebtModal() {
  // Mijozlar ro'yxatini to'ldirish
  const sel = document.getElementById('dmCustomer');
  if (sel.options.length <= 1) {
    try {
      const custs = await apiFetch('/customers/?page_size=500');
      const list = Array.isArray(custs) ? custs : (custs.items || []);
      _debtCustomers = list;   // BOSQICH 13: mahalliy dublikat tekshiruvi uchun saqlash
      list.forEach(c => {
        const o = document.createElement('option');
        o.value = c.id;
        o.textContent = `${c.name}${c.phone ? ' · ' + c.phone : ''}`;
        sel.appendChild(o);
      });
    } catch {}
  }
  // QIDIRUV: mijozlar soni tez o'sadi (nasiya endi ishlaydi) — 500 talik
  // ro'yxatdan sichqoncha bilan topish real emas. Server qidiruvi
  // (`/customers/?search=`) bilan istalgan mijoz topiladi.
  // `dmCustomer.value` o'qiydigan joy (saveDebt) TEGILMAYDI.
  if (typeof window.searchableSelect === 'function' && !sel._ss) {
    window.searchableSelect(sel, {
      placeholder: 'Ism yoki telefon bilan qidirish...',
      initial: _debtCustomers,
      render: (c) => ({ value: c.id, label: `${c.name}${c.phone ? ' · ' + c.phone : ''}` }),
      search: async (q) => {
        const r = await apiFetch(`/customers/?search=${encodeURIComponent(q)}&page_size=50`);
        const list = Array.isArray(r) ? r : (r.items || []);
        list.forEach(c => { if (!_debtCustomers.some(x => x.id === c.id)) _debtCustomers.push(c); });
        return list;
      },
    });
  }
  if (sel._ss) { sel._ss.setInitial(_debtCustomers); sel._ss.reset(); }

  document.getElementById('dmAmount').value = '';
  document.getElementById('dmDueDate').value = '';
  document.getElementById('dmNotes').value = '';
  _dmToggleNewCust(false);   // BOSQICH 13: yangi mijoz bloki yopiq holatda
  openModal('debtModal');
}

// ── BOSQICH 13: nasiyada tez yangi mijoz qo'shish ──────────────────────────────
function _dmToggleNewCust(show) {
  const box = document.getElementById('dmNewCustBox');
  if (!box) return;
  const on = (show === undefined) ? (box.style.display === 'none') : show;
  box.style.display = on ? '' : 'none';
  if (on) {
    document.getElementById('dmNewName').value = '';
    document.getElementById('dmNewPhone').value = '';
    const d = document.getElementById('dmNewDiscount'); if (d) d.value = '';
    setTimeout(() => document.getElementById('dmNewName').focus(), 50);
  }
}

async function dmAddNewCustomer() {
  const name  = document.getElementById('dmNewName').value.trim();
  const phone = document.getElementById('dmNewPhone').value.trim();
  if (!name)  { toast('Ism kiriting', 'error'); return; }
  if (!phone) { toast('Telefon kiriting', 'error'); return; }   // do'kon nasiyasi — telefon majburiy
  // BOSQICH S1: chegirma % (ixtiyoriy, 0-100)
  const discRaw = document.getElementById('dmNewDiscount')?.value;
  const disc = discRaw !== '' && discRaw != null ? parseFloat(discRaw) : 0;
  if (!(disc >= 0 && disc <= 100)) { toast("Chegirma 0-100 oralig'ida bo'lsin", 'error'); return; }
  const sel = document.getElementById('dmCustomer');

  // Mahalliy dublikat: shu do'kon ro'yxatida telefon bo'lsa — mavjudni tanla (yangi yaratma)
  const existing = _debtCustomers.find(c => (c.phone || '') === phone);
  if (existing) {
    if (sel._ss) sel._ss.ensure(existing); else sel.value = String(existing.id);
    _dmToggleNewCust(false);
    toast('Mavjud mijoz tanlandi', 'info');
    return;
  }

  const btn = document.getElementById('dmNewCustSave');
  btn.disabled = true; btn.textContent = '...';
  try {
    const c = await apiFetchPost('/customers/', { name, phone, discount_percent: disc }, 'POST');
    _debtCustomers.push(c);
    // Qidiruv filtri yoqilgan bo'lsa yangi option ro'yxatga tushmasligi mumkin —
    // `ensure` uni kafolatli qo'shib tanlaydi (aks holda mijoz "tanlanmagan"
    // bo'lib qolardi va qarz saqlanmasdi).
    if (sel._ss) {
      sel._ss.setInitial(_debtCustomers);
      sel._ss.ensure(c);
    } else {
      const o = document.createElement('option');
      o.value = String(c.id);
      o.textContent = `${c.name}${c.phone ? ' · ' + c.phone : ''}`;
      sel.appendChild(o);
      sel.value = String(c.id);
    }
    _dmToggleNewCust(false);
    toast("Mijoz qo'shildi va tanlandi", 'success');
  } catch (e) {
    toast(e.message || 'Xato', 'error');   // backend 400 "Bu telefon raqam band" (global unique)
  } finally {
    btn.disabled = false; btn.textContent = 'Qo\'shish va tanlash';
  }
}

document.getElementById('dmNewCustBtn')?.addEventListener('click', () => _dmToggleNewCust());
document.getElementById('dmNewCustSave')?.addEventListener('click', dmAddNewCustomer);

async function saveDebt() {
  const custId = document.getElementById('dmCustomer').value;
  const amount = parseFloat(document.getElementById('dmAmount').value);
  if (!custId || !amount || amount <= 0) {
    toast('Mijoz va miqdor kiritilishi shart', 'error'); return;
  }
  const payload = {
    customer_id: parseInt(custId),
    amount,
    due_date: document.getElementById('dmDueDate').value || null,
    notes: document.getElementById('dmNotes').value || null,
  };
  try {
    await apiFetchPost('/debts/', payload, 'POST');   // apiFetch faqat GET — POST uchun apiFetchPost
    closeModal('debtModal');
    toast('Qarz yozildi', 'success');
    loadDebtSummary(); loadDebts(); updateDebtBadge();
  } catch (e) {
    toast(e.message || 'Xato', 'error');
  }
}

function openPayDebt(id, remaining) {
  currentDebtId = id;
  document.getElementById('payDebtInfo').innerHTML =
    `<b>Qolgan qarz:</b> <span style="color:var(--red)">${fmtMoney(remaining)} UZS</span>`;
  document.getElementById('pdAmount').value = remaining;
  document.getElementById('pdNotes').value = '';
  openModal('payDebtModal');
}

async function submitDebtPayment() {
  const amount = parseFloat(document.getElementById('pdAmount').value);
  if (!amount || amount <= 0) { toast('Miqdor kiriting', 'error'); return; }
  const payload = {
    amount,
    payment_method: document.getElementById('pdMethod').value,
    notes: document.getElementById('pdNotes').value || null,
  };
  try {
    await apiFetchPost(`/debts/${currentDebtId}/pay`, payload, 'POST');   // apiFetch faqat GET
    closeModal('payDebtModal');
    toast('To\'lov qabul qilindi', 'success');
    loadDebtSummary(); loadDebts(); updateDebtBadge();
  } catch (e) {
    toast(e.message || 'Xato', 'error');
  }
}

function fmtDate2(s) {
  if (!s) return '—';
  const d = new Date(s);
  return `${d.getDate().toString().padStart(2,'0')}.${(d.getMonth()+1).toString().padStart(2,'0')}.${d.getFullYear()}`;
}
function escH(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

async function updateSalonExpiryBadge() {
  try {
    const data = await apiFetch('/memberships/?status=active&expiring=true&page_size=100');
    const cnt = data.total || 0;
    const badge = document.getElementById('salonExpiryBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt > 0 ? '' : 'none'; }
  } catch {}
}

async function updateExpiryBadge() {
  try {
    const data = await apiFetch('/products/?has_expiry=true&expiry_days=30&page_size=200');
    const items = data.items || [];
    const today = new Date(); today.setHours(0,0,0,0);
    let cnt = 0;
    items.forEach(p => {
      if (!p.expiry_date) return;
      const exp = new Date(p.expiry_date); exp.setHours(0,0,0,0);
      const days = Math.ceil((exp - today) / 86400000);
      if (days <= 30) cnt++;
    });
    const badge = document.getElementById('expiryBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt > 0 ? '' : 'none'; }
  } catch {}
}

async function loadWaiters() {
  const period = document.getElementById('waitersPeriod')?.value || 'week';
  const now = new Date();
  let dateFrom;
  if (period==='today') { dateFrom = new Date(now.getFullYear(),now.getMonth(),now.getDate()); }
  else if (period==='week') { dateFrom = new Date(now - 7*86400000); }
  else { dateFrom = new Date(now - 30*86400000); }
  const params = new URLSearchParams({
    date_from: dateFrom.toISOString(),
    date_to:   now.toISOString(),
  });
  try {
    const data = await apiFetch('/analytics/employees?' + params);
    const waiters = data.employees || data || [];
    const body = document.getElementById('waitersBody');
    if (!waiters.length) {
      body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Hali buyurtma yo\'q</td></tr>';
      return;
    }
    const maxSales = Math.max(...waiters.map(w=>w.total_sales||0), 1);
    body.innerHTML = waiters.map((w, i) => {
      const pct = Math.round((w.total_sales||0)/maxSales*100);
      const medal = i===0?'🥇':i===1?'🥈':i===2?'🥉':'';
      return `<tr>
        <td style="font-size:1.25rem;text-align:center">${medal||i+1}</td>
        <td class="td-bold">${w.name||'—'}</td>
        <td>${w.orders_count||0} ta</td>
        <td class="td-gold">${fmtMoney(w.total_sales||0)} UZS</td>
        <td>${fmtMoney(w.avg_check||0)} UZS</td>
        <td style="min-width:120px">
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:6px;background:var(--bg4);border-radius:3px;overflow:hidden">
              <div style="width:${pct}%;height:100%;background:${i===0?'var(--gold)':i===1?'#aaa':i===2?'#cd7f32':'var(--info)'};border-radius:3px"></div>
            </div>
            <span style="font-size:.75rem;color:var(--text2);flex-shrink:0">${pct}%</span>
          </div>
        </td>
      </tr>`;
    }).join('');
  } catch (err) { toast(err.message,'error'); }
}
document.addEventListener('DOMContentLoaded', () => {
  const rcDate = document.getElementById('rcDate');
  if (rcDate) rcDate.addEventListener('change', loadReservCalendar);
  const tdPer  = document.getElementById('tdPeriod');
  if (tdPer) tdPer.addEventListener('change', loadTopDishes);
  const tdSrt  = document.getElementById('tdSort');
  if (tdSrt) tdSrt.addEventListener('change', loadTopDishes);
  const wsPer  = document.getElementById('wsPeriod');
  if (wsPer) wsPer.addEventListener('change', loadWaiterShift);
  const ksDy   = document.getElementById('ksDays');
  if (ksDy) ksDy.addEventListener('change', loadKitchenStats);
  const slSrch = document.getElementById('slSearch');
  if (slSrch) { let _slT; slSrch.addEventListener('input', () => { clearTimeout(_slT); _slT = setTimeout(() => { slCurrentPage=1; loadStopList(); }, 300); }); }
  const stTopP = document.getElementById('stTopPeriod');
  if (stTopP) stTopP.addEventListener('change', loadStoreTop);
  const stTopS = document.getElementById('stTopSort');
  if (stTopS) stTopS.addEventListener('change', loadStoreTop);
  const smP = document.getElementById('smPeriod');
  if (smP) smP.addEventListener('change', loadStoreMargin);
  const scP = document.getElementById('scPeriod');
  if (scP) scP.addEventListener('change', loadStoreCats);
  const caP = document.getElementById('caPeriod');
  if (caP) caP.addEventListener('change', loadStoreCashier);
  const plSrch = document.getElementById('plSearch');
  if (plSrch) { let _plT; plSrch.addEventListener('input', () => { clearTimeout(_plT); _plT = setTimeout(() => { plCurrentPage=1; loadStorePriceList(); }, 300); }); }
  const wp = document.getElementById('waitersPeriod');
  if (wp) wp.addEventListener('change', loadWaiters);
  const invSrch = document.getElementById('invSearch');
  if (invSrch) {
    let _t;
    invSrch.addEventListener('input', () => { clearTimeout(_t); _t = setTimeout(() => { invCurrentPage=1; loadInventory(); }, 300); });
  }
  const siSrch = document.getElementById('siSearch');
  if (siSrch) {
    let _sit;
    siSrch.addEventListener('input', () => { clearTimeout(_sit); _sit = setTimeout(() => { siCurrentPage=1; loadStockIn(); }, 300); });
  }
  const rxSrch = document.getElementById('rxSearch');
  if (rxSrch) {
    let _rt;
    rxSrch.addEventListener('input', () => { clearTimeout(_rt); _rt = setTimeout(() => { rxCurrentPage=1; loadPrescriptions(); }, 350); });
  }
  const mp = document.getElementById('mastersPeriod');
  if (mp) mp.addEventListener('change', loadMasters);
  const soSrch = document.getElementById('soSearch');
  if (soSrch) {
    let _st;
    soSrch.addEventListener('input', () => { clearTimeout(_st); _st = setTimeout(() => { svcOrderPage=1; loadServiceOrders(); }, 350); });
  }
  const stSrch = document.getElementById('stSearch');
  if (stSrch) {
    let _stT;
    stSrch.addEventListener('input', () => { clearTimeout(_stT); _stT = setTimeout(() => { stCurrentPage=1; loadStudents(); }, 350); });
  }
  const grP = document.getElementById('grPeriod');
  if (grP) grP.addEventListener('change', loadGroups);
  const clSrch = document.getElementById('clSearch');
  if (clSrch) {
    let _clT;
    clSrch.addEventListener('input', () => { clearTimeout(_clT); _clT = setTimeout(() => { clCurrentPage=1; loadCleaning(); }, 350); });
  }
  const hbSrch = document.getElementById('hbSearch');
  if (hbSrch) {
    let _hbT;
    hbSrch.addEventListener('input', () => { clearTimeout(_hbT); _hbT = setTimeout(() => { hbCurrentPage=1; loadHotelBookings(); }, 350); });
  }
  // Kimyoviy tozalash event listeners
  const dsPer = document.getElementById('dsPeriod');
  if (dsPer) dsPer.addEventListener('change', loadDryStats);
  const drSrch = document.getElementById('drSearch');
  if (drSrch) { let _drT; drSrch.addEventListener('input', () => { clearTimeout(_drT); _drT = setTimeout(() => { drCurrentPage=1; loadDryReady(); }, 350); }); }
  const dsvPer = document.getElementById('dsvPeriod');
  if (dsvPer) dsvPer.addEventListener('change', loadDryServices);
  const dcSrch = document.getElementById('dcSearch');
  if (dcSrch) { let _dcT; dcSrch.addEventListener('input', () => { clearTimeout(_dcT); _dcT = setTimeout(loadDryClients, 350); }); }
  const dpPer = document.getElementById('dpPeriod');
  if (dpPer) dpPer.addEventListener('change', loadDryPayments);
  // Maktab event listeners
  const ssPer  = document.getElementById('ssPeriod');
  if (ssPer)  ssPer.addEventListener('change', loadSchoolStats);
  const tsSrch = document.getElementById('tsSearch');
  if (tsSrch) { let _tsT; tsSrch.addEventListener('input', () => { clearTimeout(_tsT); _tsT = setTimeout(loadSchoolTopStudents, 350); }); }
  const sgdGrp = document.getElementById('sgdGroup');
  if (sgdGrp) sgdGrp.addEventListener('change', loadSchoolGroupDetail);
  const spPer  = document.getElementById('spPeriod');
  if (spPer)  spPer.addEventListener('change', loadSchoolPayments);
  const stcPer = document.getElementById('stcPeriod');
  if (stcPer) stcPer.addEventListener('change', loadSchoolTopCourses);
  // Auto servis event listeners
  const asPer = document.getElementById('asPeriod');
  if (asPer) asPer.addEventListener('change', loadAutoStats);
  const arSrch = document.getElementById('arSearch');
  if (arSrch) { let _arT; arSrch.addEventListener('input', () => { clearTimeout(_arT); _arT = setTimeout(() => { arCurrentPage=1; loadAutoReady(); }, 350); }); }
  const adurPer = document.getElementById('adurPeriod');
  if (adurPer) adurPer.addEventListener('change', loadAutoDuration);
  const acSrch = document.getElementById('acSearch');
  if (acSrch) { let _acT; acSrch.addEventListener('input', () => { clearTimeout(_acT); _acT = setTimeout(loadAutoClients, 350); }); }
  // Salon event listeners
  const ssWS = document.getElementById('ssWeekStart');
  if (ssWS) ssWS.addEventListener('change', loadSalonSchedule);
  const svcPer = document.getElementById('svcPeriod');
  if (svcPer) svcPer.addEventListener('change', loadSalonServices);
  const phDt = document.getElementById('phDate');
  if (phDt) phDt.addEventListener('change', loadSalonPeakHours);
  const sclientPer = document.getElementById('sclientPeriod');
  if (sclientPer) sclientPer.addEventListener('change', loadSalonClients);
  const mrPer = document.getElementById('mrPeriod');
  if (mrPer) mrPer.addEventListener('change', loadSalonMasterReport);
  // Dorixona event listeners
  const psPer = document.getElementById('psPeriod');
  if (psPer) psPer.addEventListener('change', loadPharmStats);
  const ppSrch = document.getElementById('ppSearch');
  if (ppSrch) {
    let _ppT;
    ppSrch.addEventListener('input', () => { clearTimeout(_ppT); _ppT = setTimeout(() => { ppCurrentPage=1; loadPharmPatients(); }, 350); });
  }
  const ptmPer = document.getElementById('ptmPeriod');
  if (ptmPer) ptmPer.addEventListener('change', loadPharmTopMeds);
  const pcPer = document.getElementById('pcPeriod');
  if (pcPer) pcPer.addEventListener('change', loadPharmCats);
  const pharmCaPer = document.getElementById('pharmCaPeriod');
  if (pharmCaPer) pharmCaPer.addEventListener('change', loadPharmCashier);
  // Mehmonxona event listeners
  const htPer = document.getElementById('htPeriod');
  if (htPer) htPer.addEventListener('change', loadHotelStats);
  const hoPer = document.getElementById('hoPeriod');
  if (hoPer) hoPer.addEventListener('change', loadHotelOccupancy);
  const hgSrch = document.getElementById('hgSearch');
  if (hgSrch) { let _hgT; hgSrch.addEventListener('input', () => { clearTimeout(_hgT); _hgT = setTimeout(loadHotelGuests, 350); }); }
  const hrrPer = document.getElementById('hrrPeriod');
  if (hrrPer) hrrPer.addEventListener('change', loadHotelRoomRevenue);
});

