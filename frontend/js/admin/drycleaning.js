/* XENORA admin — KIMYOVIY TOZALASH (dry_cleaning) sahifalari moduli (refaktoring 2-bo'lak).
   CLASSIC <script src>, katta scriptdan OLDIN. Global scope saqlanadi. */
// ── Kimyoviy tozalash sahifalari ─────────────────────────────────────────────

async function loadDryStats() {
  const period = document.getElementById('dsPeriod')?.value || 'month';
  try {
    const data = await apiFetch('/analytics/dry-stats?period=' + period);
    document.getElementById('dsTotal').textContent   = data.total || 0;
    document.getElementById('dsRevenue').textContent = fmtMoney(data.total_revenue||0) + ' UZS';
    document.getElementById('dsAvg').textContent     = fmtMoney(data.avg_check||0) + ' UZS';
    const sc = data.status_counts || {};
    document.getElementById('dsStatPending').textContent   = sc.pending    || 0;
    document.getElementById('dsStatPreparing').textContent = sc.preparing  || 0;
    document.getElementById('dsStatReady').textContent     = sc.ready      || 0;
    document.getElementById('dsStatCompleted').textContent = sc.completed  || 0;
    document.getElementById('dsStatCancelled').textContent = sc.cancelled  || 0;
    const daily  = data.daily || [];
    const maxRev = Math.max(...daily.map(d => d.revenue||0), 1);
    document.getElementById('dsChartBody').innerHTML = daily.length
      ? `<div style="display:flex;align-items:flex-end;gap:3px;height:70px;padding:0 .5rem">` +
        daily.map(d => {
          const pct = Math.round((d.revenue||0)/maxRev*100);
          return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px" title="${d.date}: ${d.count} ta, ${fmtMoney(d.revenue)} UZS">
            <div style="width:100%;height:${Math.max(pct*0.65,2)}px;background:var(--gold);border-radius:2px 2px 0 0"></div>
            <div style="font-size:.6rem;color:var(--text3)">${d.date.slice(5)}</div>
          </div>`;
        }).join('') + '</div>'
      : '';
  } catch(err) { toast(err.message,'error'); }
}

let drCurrentPage = 1;
function drPage(dir) { drCurrentPage = Math.max(1, drCurrentPage+dir); loadDryReady(); }

async function loadDryReady() {
  const search = document.getElementById('drSearch')?.value || '';
  try {
    const data  = await apiFetch('/orders/?has_cleaning=true&status=ready&page_size=30&page=' + drCurrentPage);
    let items   = data.items || [];
    const total = data.total || 0;
    if (search) {
      const sl = search.toLowerCase();
      items = items.filter(o => (o.order_number||'').toLowerCase().includes(sl) || JSON.stringify(o.biz_meta||{}).toLowerCase().includes(sl));
    }
    const badge = document.getElementById('dryReadyBadge');
    if (badge) { badge.textContent = total; badge.style.display = total>0?'':'none'; }
    document.getElementById('drPagInfo').textContent = `${items.length} / ${total} ta`;
    const body = document.getElementById('drBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Tayyor buyurtma yo\'q</td></tr>'; return; }
    body.innerHTML = items.map(o => {
      const meta = o.biz_meta || {};
      const itemList = (o.items||[]).map(i=>i.product_name||i.name||'').filter(Boolean).join(', ');
      return `<tr>
        <td style="font-weight:700;color:var(--gold)">#${o.order_number}</td>
        <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${meta.cleaning_items||itemList||'—'}</td>
        <td class="td-sub" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${meta.cleaning_notes||'—'}</td>
        <td style="font-weight:700">${fmtMoney(o.final_amount||0)} UZS</td>
        <td class="td-sub">${(o.updated_at||o.created_at||'').slice(0,10)}</td>
        <td class="td-actions">
          <button class="act-btn" title="Topshirildi" onclick="clNextStatus(${o.id},'completed')">✓</button>
        </td>
      </tr>`;
    }).join('');
    document.getElementById('drPrevBtn').disabled = drCurrentPage <= 1;
    document.getElementById('drNextBtn').disabled = items.length < 30;
  } catch(err) { toast(err.message,'error'); }
}

async function loadDryServices() {
  const period = document.getElementById('dsvPeriod')?.value || 'month';
  const now    = new Date();
  const start  = period === 'week' ? new Date(now - 7*86400000) : new Date(now - 30*86400000);
  try {
    const data   = await apiFetch('/orders/?has_cleaning=true&page_size=500');
    const orders = (data.items||[]).filter(o => new Date(o.created_at) >= start);
    const svcMap = {};
    orders.forEach(o => {
      (o.items||[]).forEach(item => {
        const name = item.product_name || item.name || '—';
        if (!svcMap[name]) svcMap[name] = { count: 0, revenue: 0 };
        svcMap[name].count++;
        svcMap[name].revenue += item.total_price || 0;
      });
    });
    const items    = Object.entries(svcMap).sort((a,b)=>b[1].revenue-a[1].revenue);
    const totalRev = items.reduce((s,[,v])=>s+v.revenue,0) || 1;
    const body     = document.getElementById('dsvBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const colors = ['#f59e0b','#3b82f6','#10b981','#ef4444','#8b5cf6'];
    body.innerHTML = items.map(([name,s],i) => `<tr>
      <td style="font-weight:700;color:${colors[i%colors.length]};text-align:center">${i+1}</td>
      <td class="td-bold">${name}</td>
      <td style="font-weight:700">${s.count} ta</td>
      <td class="td-gold">${fmtMoney(s.revenue)} UZS</td>
      <td style="font-weight:700;color:${colors[i%colors.length]}">${Math.round(s.revenue/totalRev*100)}%</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadDryClients() {
  const search = document.getElementById('dcSearch')?.value || '';
  try {
    const data   = await apiFetch('/orders/?has_cleaning=true&page_size=500');
    const orders = data.items || [];
    const clientMap = {};
    orders.forEach(o => {
      const cname  = o.customer?.name || o.customer_name || 'Noma\'lum';
      const cphone = o.customer?.phone || '—';
      const key    = cname.toLowerCase();
      if (!clientMap[key]) clientMap[key] = { name: cname, phone: cphone, count: 0, total: 0, last: null };
      clientMap[key].count++;
      clientMap[key].total += o.final_amount || 0;
      const d = (o.created_at||'').slice(0,10);
      if (!clientMap[key].last || d > clientMap[key].last) clientMap[key].last = d;
    });
    let items = Object.values(clientMap).sort((a,b)=>b.total-a.total);
    if (search) { const sl=search.toLowerCase(); items=items.filter(c=>c.name.toLowerCase().includes(sl)||c.phone.includes(sl)); }
    const body = document.getElementById('dcBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Mijoz topilmadi</td></tr>'; return; }
    body.innerHTML = items.slice(0,50).map((c,i) => `<tr>
      <td style="font-weight:700;color:var(--text2)">${i+1}</td>
      <td class="td-bold">${c.name}</td>
      <td class="td-sub">${c.phone}</td>
      <td style="font-weight:700">${c.count} ta</td>
      <td class="td-gold">${fmtMoney(c.total)} UZS</td>
      <td class="td-sub">${fmtMoney(c.count?c.total/c.count:0)} UZS</td>
      <td class="td-sub">${c.last||'—'}</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadDryWorkload() {
  try {
    const data   = await apiFetch('/analytics/dry-stats?period=month');
    const daily  = data.daily || [];
    const maxCnt = Math.max(...daily.map(d=>d.count||0), 1);
    const avgCnt = daily.length ? Math.round(daily.reduce((s,d)=>s+(d.count||0),0)/daily.length*10)/10 : 0;
    document.getElementById('dwChartBody').innerHTML = daily.length
      ? `<div style="display:flex;align-items:flex-end;gap:3px;height:70px;padding:0 .5rem">` +
        daily.map(d => {
          const pct    = Math.round((d.count||0)/maxCnt*100);
          const isBusy = d.count > avgCnt * 1.5;
          return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px" title="${d.date}: ${d.count} ta">
            <div style="width:100%;height:${Math.max(pct*0.65,2)}px;background:${isBusy?'var(--danger)':'var(--gold)'};border-radius:2px 2px 0 0"></div>
            <div style="font-size:.6rem;color:var(--text3)">${d.date.slice(5)}</div>
          </div>`;
        }).join('') + '</div>'
      : '';
    const body = document.getElementById('dwBody');
    if (!daily.length) { body.innerHTML='<tr><td colspan="4" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    body.innerHTML = daily.slice().reverse().map(d => {
      const load = d.count > avgCnt*1.5 ? '<span class="badge badge-red">Yuqori</span>' : d.count > avgCnt*0.7 ? '<span class="badge badge-blue">O\'rta</span>' : '<span class="badge badge-gray">Past</span>';
      return `<tr>
        <td class="td-sub">${d.date}</td>
        <td style="font-weight:700">${d.count} ta</td>
        <td class="td-gold">${fmtMoney(d.revenue)} UZS</td>
        <td>${load}</td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadDryPayments() {
  const period = document.getElementById('dpPeriod')?.value || 'month';
  try {
    const data = await apiFetch('/analytics/cashier-report?period=' + period);
    const methodTotals = { cash:0, card:0, click:0, payme:0, qr:0 };
    const methodCounts = { cash:0, card:0, click:0, payme:0, qr:0 };
    (data||[]).forEach(c => {
      Object.keys(methodTotals).forEach(m => {
        if (c[m] > 0) { methodTotals[m] += c[m]; methodCounts[m]++; }
      });
    });
    const totalRev = Object.values(methodTotals).reduce((s,v)=>s+v,0) || 1;
    const LABELS = { cash:'Naqd', card:'Karta', click:'Click', payme:'Payme', qr:'QR' };
    const COLORS = { cash:'#10b981', card:'#3b82f6', click:'#f59e0b', payme:'#8b5cf6', qr:'#ec4899' };
    const methods = Object.entries(methodTotals).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]);
    document.getElementById('dpBarsBody').innerHTML = methods.length
      ? `<div style="display:flex;gap:.75rem;flex-wrap:wrap;margin-bottom:1rem">` +
        methods.map(([m,v]) => {
          const pct = Math.round(v/totalRev*100);
          return `<div style="flex:1;min-width:80px;background:var(--bg3);border:1px solid var(--border);border-radius:.75rem;padding:.75rem;text-align:center">
            <div style="font-size:.75rem;color:var(--text3);margin-bottom:.25rem">${LABELS[m]||m}</div>
            <div style="font-weight:700;color:${COLORS[m]||'var(--gold)'};font-size:1.1rem">${pct}%</div>
            <div style="font-size:.75rem;color:var(--text2)">${fmtMoney(v)} UZS</div>
          </div>`;
        }).join('') + '</div>'
      : '';
    const body = document.getElementById('dpBody');
    if (!methods.length) { body.innerHTML='<tr><td colspan="4" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    body.innerHTML = methods.map(([m,v]) => `<tr>
      <td><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${COLORS[m]||'#666'};margin-right:.5rem"></span><b>${LABELS[m]||m}</b></td>
      <td style="font-weight:700">${methodCounts[m]} ta</td>
      <td class="td-gold">${fmtMoney(v)} UZS</td>
      <td style="font-weight:700;color:${COLORS[m]||'var(--gold)'}">${Math.round(v/totalRev*100)}%</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}



/* ── Tozalash jurnali (jurnal klasteri, refaktoring 3-bo'lak) ── */
// ── Cleaning journal (dry_cleaning) ──────────────────────────────────────────
let clCurrentPage = 1, clStatusVal = '';

const CL_STATUS = {
  pending:   { lbl:'Qabul qilindi', cls:'badge-amber' },
  preparing: { lbl:'Tozalanmoqda', cls:'badge-blue'  },
  ready:     { lbl:'Tayyor',        cls:'badge-green'  },
  completed: { lbl:'Topshirildi',   cls:'badge-gray'   },
  cancelled: { lbl:'Bekor',         cls:'badge-red'    },
};
const CL_NEXT = { pending:'preparing', preparing:'ready', ready:'completed' };
const CL_NEXT_LBL = { pending:'Tozalashga olib ketildi', preparing:'Tayyor', ready:'Topshirildi' };

async function loadCleaning() {
  const search = document.getElementById('clSearch')?.value || '';
  const params = new URLSearchParams({ page: clCurrentPage, page_size: 20, has_cleaning: 'true' });
  if (clStatusVal) params.set('status', clStatusVal);
  if (search)      params.set('search', search);
  try {
    const data  = await apiFetch('/orders/?' + params);
    const items = data.items || [];
    const total = data.total || 0;
    document.getElementById('clTotal').textContent    = total;
    document.getElementById('clPending').textContent  = items.filter(o => o.status === 'pending').length;
    document.getElementById('clPreparing').textContent = items.filter(o => o.status === 'preparing').length;
    document.getElementById('clReady').textContent    = items.filter(o => o.status === 'ready').length;
    document.getElementById('clPagInfo').textContent  = `${items.length} / ${total} ta`;
    const body = document.getElementById('clBody');
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Buyurtma topilmadi</td></tr>';
    } else {
      body.innerHTML = items.map(o => {
        const meta   = o.biz_meta || {};
        const date   = new Date(o.created_at).toLocaleDateString('uz-UZ', { day:'2-digit', month:'2-digit', year:'numeric' });
        const st     = CL_STATUS[o.status] || { lbl: o.status, cls: '' };
        const nextSt = CL_NEXT[o.status];
        const items_list = (o.items || []).map(i => i.product_name || i.name || '').filter(Boolean).join(', ');
        return `<tr>
          <td style="font-size:.75rem;color:var(--text2);white-space:nowrap">${date}</td>
          <td style="font-weight:700;color:var(--gold)">#${o.order_number}</td>
          <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${meta.cleaning_items || items_list}">${meta.cleaning_items || items_list || '—'}</td>
          <td style="font-size:.8125rem;color:var(--text2);max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${meta.cleaning_notes || '—'}</td>
          <td style="font-weight:600;white-space:nowrap">${fmtMoney(o.final_amount)} UZS</td>
          <td><span class="badge ${st.cls}">${st.lbl}</span></td>
          <td class="td-actions">
            ${nextSt ? `<button class="act-btn" title="${CL_NEXT_LBL[o.status]}" onclick="clNextStatus(${o.id},'${nextSt}')">›</button>` : ''}
          </td>
        </tr>`;
      }).join('');
    }
    document.getElementById('clPrevBtn').disabled = clCurrentPage <= 1;
    document.getElementById('clNextBtn').disabled = items.length < 20;
    const activeCnt = items.filter(o => o.status === 'pending' || o.status === 'preparing').length;
    const badge = document.getElementById('cleaningBadge');
    if (badge) { badge.textContent = activeCnt; badge.style.display = activeCnt > 0 ? '' : 'none'; }
  } catch(err) { toast(err.message, 'error'); }
}

function clApplyFilter() { clStatusVal = document.getElementById('clFilter')?.value || ''; clCurrentPage = 1; loadCleaning(); }
function clPage(dir)     { clCurrentPage = Math.max(1, clCurrentPage + dir); loadCleaning(); }

async function clNextStatus(id, newStatus) {
  try {
    const res = await fetch(`${API_BASE}/orders/${id}`, {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Xatolik'); }
    toast(CL_STATUS[newStatus]?.lbl + ' holatiga o\'tkazildi', 'success');
    loadCleaning();
    updateCleaningBadge();
  } catch(err) { toast(err.message, 'error'); }
}

async function updateCleaningBadge() {
  try {
    const [p, pr] = await Promise.all([
      apiFetch('/orders/?has_cleaning=true&status=pending&page_size=1'),
      apiFetch('/orders/?has_cleaning=true&status=preparing&page_size=1'),
    ]);
    const cnt = (p.total || 0) + (pr.total || 0);
    const badge = document.getElementById('cleaningBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt > 0 ? '' : 'none'; }
  } catch {}
}

