/* XENORA admin — SALON/FITNES sahifalari moduli (refaktoring 2-bo'lak).
   CLASSIC <script src>, katta scriptdan OLDIN. Global scope saqlanadi. */
// ── Salon/Fitnes sahifalari ───────────────────────────────────────────────────

async function loadSalonSchedule() {
  const inp = document.getElementById('ssWeekStart');
  const today = new Date();
  if (!inp.value) inp.value = today.toISOString().slice(0, 10);
  const start = new Date(inp.value);
  const days = Array.from({length: 7}, (_, i) => {
    const d = new Date(start); d.setDate(start.getDate() + i);
    return d.toISOString().slice(0, 10);
  });
  const DAY_NAMES = ['Yak', 'Du', 'Se', 'Cho', 'Pay', 'Ju', 'Sha'];
  try {
    const results = await Promise.all(days.map(d => apiFetch('/appointments/?date=' + d + '&page_size=100')));
    // Build master→days map
    const masterMap = {};
    results.forEach((res, di) => {
      (res.items || []).forEach(a => {
        const mname = a.employee_name || 'Tayinlanmagan';
        if (!masterMap[mname]) masterMap[mname] = {};
        if (!masterMap[mname][days[di]]) masterMap[mname][days[di]] = [];
        masterMap[mname][days[di]].push(a);
      });
    });
    const masters = Object.keys(masterMap);
    const body = document.getElementById('ssBody');
    if (!masters.length) {
      body.innerHTML = '<div style="text-align:center;padding:3rem;color:var(--text3)">Bu haftada randevu yo\'q</div>';
      return;
    }
    const dayHeaders = days.map((d, i) => {
      const dt = new Date(d);
      return `<th style="min-width:110px;text-align:center">${DAY_NAMES[dt.getDay()]}<br><small style="color:var(--text3);font-weight:400">${d.slice(5)}</small></th>`;
    }).join('');
    const rows = masters.map(mname => {
      const cells = days.map(d => {
        const apts = masterMap[mname][d] || [];
        if (!apts.length) return '<td style="text-align:center;color:var(--text3)">—</td>';
        const items = apts.slice(0, 3).map(a => {
          const cls = a.status === 'completed' ? 'badge-green' : a.status === 'cancelled' ? 'badge-red' : 'badge-blue';
          return `<div style="margin-bottom:2px"><span class="badge ${cls}" style="font-size:.65rem">${a.start_time} ${(a.service_name||'').slice(0,12)}</span></div>`;
        }).join('');
        const more = apts.length > 3 ? `<div style="font-size:.65rem;color:var(--text3)">+${apts.length-3} ta</div>` : '';
        return `<td style="vertical-align:top;padding:.5rem">${items}${more}</td>`;
      }).join('');
      return `<tr><td style="font-weight:700;white-space:nowrap;padding:.5rem .75rem">${mname}</td>${cells}</tr>`;
    }).join('');
    body.innerHTML = `<table style="width:100%;border-collapse:collapse">
      <thead><tr><th style="text-align:left;padding:.5rem .75rem">Usta</th>${dayHeaders}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  } catch(err) { toast(err.message, 'error'); }
}

async function loadSalonServices() {
  const period = document.getElementById('svcPeriod')?.value || 'week';
  try {
    const data = await apiFetch('/analytics/salon-services?period=' + period);
    const items = data.items || [];
    const body = document.getElementById('svcBody');
    if (!items.length) { body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const colors = ['#f59e0b','#3b82f6','#10b981','#ef4444','#8b5cf6'];
    body.innerHTML = items.map((svc, i) => `<tr>
      <td style="font-weight:700;color:${colors[i%colors.length]};text-align:center">${i+1}</td>
      <td class="td-bold">${svc.name}</td>
      <td style="font-weight:700">${svc.count} ta</td>
      <td><span class="badge badge-green">${svc.completed} ta</span></td>
      <td class="td-sub">${svc.avg_duration} daq</td>
      <td class="td-sub">${fmtMoney(svc.avg_price)} UZS</td>
      <td class="td-gold">${fmtMoney(svc.revenue)} UZS</td>
      <td style="font-weight:700;color:${colors[i%colors.length]}">${svc.share_pct}%</td>
    </tr>`).join('');
  } catch(err) { toast(err.message, 'error'); }
}

async function loadSalonPeakHours() {
  const inp = document.getElementById('phDate');
  if (!inp.value) inp.value = new Date().toISOString().slice(0, 10);
  try {
    const data = await apiFetch('/analytics/hourly?date=' + inp.value + 'T12:00:00');
    const hours = Array.isArray(data) ? data : (data.hourly || []);
    const body = document.getElementById('phBody');
    if (!hours.length) { body.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</div>'; return; }
    const maxOrders = Math.max(...hours.map(h => h.orders_count || 0), 1);
    // show only hours 7-22
    const workHours = hours.filter(h => h.hour >= 7 && h.hour <= 22);
    body.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:.75rem">` +
      workHours.map(h => {
        const pct = Math.round((h.orders_count || 0) / maxOrders * 100);
        const isBusy = pct >= 70;
        return `<div style="background:var(--bg3);border:1px solid var(--border);border-radius:.75rem;padding:.75rem;text-align:center">
          <div style="font-weight:700;font-size:1.1rem">${String(h.hour || 0).padStart(2,'0')}:00</div>
          <div style="margin:.5rem 0;height:60px;display:flex;align-items:flex-end;justify-content:center">
            <div style="width:40px;height:${Math.max(pct*0.6,3)}%;background:${isBusy?'var(--danger)':pct>=40?'var(--warning)':'var(--success)'};border-radius:4px 4px 0 0;min-height:3px"></div>
          </div>
          <div style="font-weight:700;color:${isBusy?'var(--danger)':pct>=40?'var(--warning)':'var(--success)'}">${h.orders_count || 0} ta</div>
          <div style="font-size:.7rem;color:var(--text3)">${isBusy?'Band':'Bo\'sh'}</div>
        </div>`;
      }).join('') + '</div>';
  } catch(err) { toast(err.message, 'error'); }
}

let seDaysFilter = 7;
function seSetDays(days) {
  seDaysFilter = days;
  ['7','30'].forEach(v => {
    const b = document.getElementById('seDays'+v);
    if (b) b.style.cssText = '';
  });
  const ab = document.getElementById('seDays' + days);
  if (ab) ab.style.cssText = 'background:var(--gold);color:#000';
  loadSalonExpiring();
}

async function loadSalonExpiring() {
  const today = new Date(); today.setHours(0,0,0,0);
  try {
    const data = await apiFetch('/memberships/?status=active&page_size=200');
    const items = (data.items || []);
    const cutoff = new Date(today); cutoff.setDate(today.getDate() + seDaysFilter);
    const expiring = items.filter(m => {
      const end = new Date(m.end_date); end.setHours(0,0,0,0);
      return end <= cutoff;
    }).sort((a, b) => a.end_date.localeCompare(b.end_date));
    const todayStr = today.toISOString().slice(0, 10);
    const todayCount = expiring.filter(m => m.end_date <= todayStr).length;
    document.getElementById('seTotal').textContent    = expiring.length;
    document.getElementById('seToday').textContent    = todayCount;
    document.getElementById('seNeedCall').textContent = expiring.length;
    const badge = document.getElementById('salonExpiryBadge');
    if (badge) { badge.textContent = expiring.length; badge.style.display = expiring.length > 0 ? '' : 'none'; }
    const body = document.getElementById('seBody');
    if (!expiring.length) { body.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Tugayotgan abonement yo\'q</td></tr>'; return; }
    body.innerHTML = expiring.map(m => {
      const end = new Date(m.end_date); end.setHours(0,0,0,0);
      const daysLeft = Math.ceil((end - today) / 86400000);
      const cls = daysLeft <= 0 ? 'badge-red' : daysLeft <= 3 ? 'badge-amber' : 'badge-blue';
      const lbl = daysLeft <= 0 ? 'Tugadi' : daysLeft + ' kun';
      const cname = m.customer?.name || m.customer_name || '—';
      const cphone = m.customer?.phone || '—';
      return `<tr${daysLeft <= 0 ? ' style="background:rgba(239,68,68,.04)"' : ''}>
        <td class="td-bold">${cname}</td>
        <td class="td-sub"><a href="tel:${cphone}" style="color:var(--info)">${cphone}</a></td>
        <td><span class="badge badge-blue">${m.plan_name}</span></td>
        <td>${m.end_date}</td>
        <td><span class="badge ${cls}">${lbl}</span></td>
        <td>${m.visits_used || 0}/${m.visits_total || '∞'}</td>
        <td class="td-gold">${fmtMoney(m.price)} UZS</td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message, 'error'); }
}

async function loadSalonClients() {
  const period = document.getElementById('sclientPeriod')?.value || 'week';
  const now = new Date();
  const start = period === 'week' ? new Date(now - 7*86400000) : new Date(now - 30*86400000);
  try {
    const [aptData, allAptData] = await Promise.all([
      apiFetch('/appointments/?page_size=500'),
      apiFetch('/appointments/?page_size=500'),
    ]);
    const allApts = aptData.items || [];
    const recentApts = allApts.filter(a => new Date(a.created_at || a.date) >= start);
    // Group by customer name
    const clientMap = {};
    allApts.forEach(a => {
      const key = (a.customer_name || '').toLowerCase().trim();
      if (!key) return;
      if (!clientMap[key]) clientMap[key] = { name: a.customer_name, phone: a.customer_phone || '—', count: 0, revenue: 0, last: null, inPeriod: false };
      clientMap[key].count++;
      clientMap[key].revenue += a.price || 0;
      if (!clientMap[key].last || a.date > clientMap[key].last) clientMap[key].last = a.date;
    });
    recentApts.forEach(a => {
      const key = (a.customer_name || '').toLowerCase().trim();
      if (clientMap[key]) clientMap[key].inPeriod = true;
    });
    const clients = Object.values(clientMap).sort((a, b) => b.revenue - a.revenue);
    const returning = clients.filter(c => c.count > 1);
    const newClients = clients.filter(c => c.count === 1);
    document.getElementById('scTotal').textContent  = clients.length;
    document.getElementById('scNew').textContent    = newClients.length;
    document.getElementById('scReturn').textContent = returning.length;
    document.getElementById('scRate').textContent   = clients.length ? Math.round(returning.length / clients.length * 100) + '%' : '0%';
    const body = document.getElementById('scBody');
    if (!clients.length) { body.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    body.innerHTML = clients.slice(0, 50).map(c => {
      const isNew = c.count === 1;
      return `<tr>
        <td class="td-bold">${c.name}</td>
        <td class="td-sub">${c.phone}</td>
        <td style="font-weight:700">${c.count} ta</td>
        <td class="td-gold">${fmtMoney(c.revenue)} UZS</td>
        <td class="td-sub">${fmtMoney(c.count ? c.revenue/c.count : 0)} UZS</td>
        <td class="td-sub">${c.last || '—'}</td>
        <td><span class="badge ${isNew ? 'badge-blue' : 'badge-green'}">${isNew ? 'Yangi' : 'Doimiy'}</span></td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message, 'error'); }
}

async function loadSalonMasterReport() {
  const period = document.getElementById('mrPeriod')?.value || 'week';
  try {
    const data = await apiFetch('/analytics/master-report?period=' + period);
    const body = document.getElementById('mrBody');
    if (!data.length) { body.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const maxRev = Math.max(...data.map(m => m.revenue || 0), 1);
    const colors = ['#f59e0b','#94a3b8','#c27c1e'];
    body.innerHTML = data.map((m, i) => {
      const pct = Math.round((m.revenue || 0) / maxRev * 100);
      const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : '';
      return `<tr>
        <td style="text-align:center;font-size:1.1rem">${medal || i+1}</td>
        <td class="td-bold">${m.name}</td>
        <td style="font-weight:700">${m.count} ta</td>
        <td><span class="badge badge-green">${m.completed} ta</span></td>
        <td class="td-sub" style="font-size:.75rem">${(m.services||[]).join(', ') || '—'}</td>
        <td class="td-sub">${fmtMoney(m.avg_check)} UZS</td>
        <td>
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden;min-width:60px"><div style="width:${pct}%;height:100%;background:${colors[i]||'var(--info)'};border-radius:3px"></div></div>
            <span class="td-gold" style="white-space:nowrap">${fmtMoney(m.revenue)} UZS</span>
          </div>
        </td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message, 'error'); }
}


/* ── Abonementlar + Ustalar (jurnal klasteri, refaktoring 3-bo'lak) ── */
async function loadMemberships() {
  const flt = document.getElementById('mbFilter')?.value || '';
  const params = new URLSearchParams({ page: mbCurrentPage, page_size: 20 });
  if (flt === 'expiring') params.set('expiring', 'true');
  else if (flt)           params.set('status', flt);
  try {
    const data  = await apiFetch('/memberships/?' + params);
    const items = data.items || [];
    const total = data.total || 0;
    const today = new Date(); today.setHours(0,0,0,0);
    document.getElementById('mbTotal').textContent    = total;
    document.getElementById('mbActive').textContent   = items.filter(m => m.status==='active' && new Date(m.end_date)>=today).length;
    document.getElementById('mbExpiring').textContent = items.filter(m => {
      if (m.status !== 'active') return false;
      const d = Math.ceil((new Date(m.end_date) - new Date()) / 86400000);
      return d >= 0 && d <= 7;
    }).length;
    document.getElementById('mbPagInfo').textContent = `${items.length} / ${total} ta`;
    const body = document.getElementById('mbBody');
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Abonement topilmadi</td></tr>';
      return;
    }
    body.innerHTML = items.map(m => {
      const cust = m.customer || {};
      const end  = new Date(m.end_date);
      const dl   = Math.ceil((end - new Date()) / 86400000);
      let badgeCls, badgeLbl;
      if (m.status === 'cancelled')               { badgeCls='badge-red';   badgeLbl='Bekor'; }
      else if (m.status === 'expired' || end < today) { badgeCls='badge-gray';  badgeLbl="Muddati o'tgan"; }
      else if (dl <= 7)                           { badgeCls='badge-amber'; badgeLbl=`${dl} kun qoldi`; }
      else                                         { badgeCls='badge-green'; badgeLbl='Faol'; }
      const vt = m.visits_total || 0, vu = m.visits_used || 0;
      const vPct  = vt > 0 ? Math.min(100, Math.round(vu / vt * 100)) : 100;
      const vColor = vt > 0 && vu >= vt ? 'var(--danger)' : vPct > 75 ? 'var(--warning)' : 'var(--gold)';
      return `<tr>
        <td><div style="font-weight:600">${cust.full_name||'—'}</div><div style="font-size:.75rem;color:var(--text2)">${cust.phone||''}</div></td>
        <td><div style="font-weight:600">${m.plan_name||'—'}</div><div style="font-size:.75rem;color:var(--gold)">${fmtMoney(m.price)} UZS</div></td>
        <td><div style="font-size:.75rem;color:var(--text2)">${(m.start_date||'').slice(0,10)}</div><div style="font-weight:600">${(m.end_date||'').slice(0,10)}</div></td>
        <td>
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden;min-width:50px"><div style="width:${vPct}%;height:100%;background:${vColor};border-radius:3px"></div></div>
            <span style="font-size:.75rem;color:var(--text2)">${vt > 0 ? vu+'/'+vt : vu+'(∞)'}</span>
          </div>
        </td>
        <td><span class="badge ${badgeCls}">${badgeLbl}</span></td>
        <td class="td-actions">
          ${m.status==='active' ? `<button class="act-btn" title="Tashrif" onclick="mbAddVisit(${m.id})"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M9 11l3 3L22 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>` : ''}
        </td>
      </tr>`;
    }).join('');
    document.getElementById('mbPrevBtn').disabled = mbCurrentPage <= 1;
    document.getElementById('mbNextBtn').disabled = items.length < 20;
    const expCnt = items.filter(m => {
      if (m.status !== 'active') return false;
      const d = Math.ceil((new Date(m.end_date) - new Date()) / 86400000);
      return d >= 0 && d <= 7;
    }).length;
    const badge = document.getElementById('expiringBadge');
    if (badge) { badge.textContent = expCnt; badge.style.display = expCnt > 0 ? '' : 'none'; }
  } catch(err) { toast(err.message, 'error'); }
}

function mbApplyFilter() { mbCurrentPage = 1; loadMemberships(); }
function mbPage(dir)     { mbCurrentPage = Math.max(1, mbCurrentPage + dir); loadMemberships(); }

async function mbAddVisit(id) {
  try {
    const res = await fetch(`${API_BASE}/memberships/${id}/visit`, {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Xatolik'); }
    toast("Tashrif qo'shildi", 'success');
    loadMemberships();
  } catch(err) { toast(err.message, 'error'); }
}

async function updateExpiringBadge() {
  try {
    const data = await apiFetch('/memberships/?expiring=true&page_size=1');
    const cnt  = data.total || 0;
    const badge = document.getElementById('expiringBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt > 0 ? '' : 'none'; }
  } catch {}
}

// ── Masters reytingi (salon/fitness) ─────────────────────────────────────────
async function loadMasters() {
  const days = parseInt(document.getElementById('mastersPeriod')?.value || '30');
  const from = new Date(Date.now() - days * 86400000).toISOString();
  try {
    const data = await apiFetch(`/analytics/employees?date_from=${from}`);
    const emps = Array.isArray(data) ? data : (data.employees || []);
    const body = document.getElementById('mastersBody');
    if (!emps.length) {
      body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>';
      return;
    }
    const maxSales = Math.max(...emps.map(e => e.total_sales || 0), 1);
    body.innerHTML = emps.map((e, i) => {
      const pct   = Math.round((e.total_sales || 0) / maxSales * 100);
      const medal = i===0 ? '🥇' : i===1 ? '🥈' : i===2 ? '🥉' : '';
      const barColor = i===0 ? 'var(--gold)' : i===1 ? '#aaa' : i===2 ? '#cd7f32' : 'var(--info)';
      return `<tr>
        <td style="font-size:1.25rem;text-align:center">${medal || i+1}</td>
        <td style="font-weight:600">${e.name||'—'}</td>
        <td>${e.orders_count||0} ta</td>
        <td style="color:var(--gold);font-weight:700">${fmtMoney(e.total_sales||0)} UZS</td>
        <td>${fmtMoney(e.avg_check||0)} UZS</td>
        <td style="min-width:120px">
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:6px;background:var(--bg4);border-radius:3px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${barColor};border-radius:3px"></div></div>
            <span style="font-size:.75rem;color:var(--text2);flex-shrink:0">${pct}%</span>
          </div>
        </td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message, 'error'); }
}

