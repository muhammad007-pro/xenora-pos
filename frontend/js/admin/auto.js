/* XENORA admin — AUTO SERVIS sahifalari moduli (refaktoring 2-bo'lak).
   CLASSIC <script src>, katta scriptdan OLDIN. Global scope saqlanadi. */
// ── Auto servis sahifalari ────────────────────────────────────────────────────

async function loadAutoStats() {
  const period = document.getElementById('asPeriod')?.value || 'week';
  try {
    const data = await apiFetch('/analytics/auto-stats?period=' + period);
    document.getElementById('asTotal').textContent    = data.total || 0;
    document.getElementById('asRevenue').textContent  = fmtMoney(data.total_revenue||0) + ' UZS';
    document.getElementById('asPaid').textContent     = fmtMoney(data.total_paid||0) + ' UZS';
    document.getElementById('asDebt').textContent     = fmtMoney(data.debt_total||0) + ' UZS';
    document.getElementById('asAvgHours').textContent = (data.avg_hours||0) + ' soat';
    const sc = data.status_counts || {};
    document.getElementById('asPending').textContent    = sc.pending    || 0;
    document.getElementById('asInProgress').textContent = sc.in_progress || 0;
    document.getElementById('asDone').textContent       = sc.done       || 0;
    document.getElementById('asDelivered').textContent  = sc.delivered  || 0;
    // Daily bar chart
    const daily = data.daily || [];
    const maxRev = Math.max(...daily.map(d => d.revenue||0), 1);
    const chartBody = document.getElementById('asChartBody');
    if (!daily.length) { chartBody.innerHTML = ''; return; }
    chartBody.innerHTML = `<div style="display:flex;align-items:flex-end;gap:4px;height:80px;padding:0 .5rem">` +
      daily.map(d => {
        const pct = Math.round((d.revenue||0)/maxRev*100);
        return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px" title="${d.date}: ${fmtMoney(d.revenue)} UZS">
          <div style="width:100%;height:${Math.max(pct*0.7,2)}px;background:var(--gold);border-radius:2px 2px 0 0;min-height:2px"></div>
          <div style="font-size:.6rem;color:var(--text3);white-space:nowrap">${d.date.slice(5)}</div>
        </div>`;
      }).join('') + '</div>';
  } catch(err) { toast(err.message,'error'); }
}

let arCurrentPage = 1;
function arPage(dir) { arCurrentPage = Math.max(1, arCurrentPage+dir); loadAutoReady(); }

async function loadAutoReady() {
  const search = document.getElementById('arSearch')?.value || '';
  try {
    const data  = await apiFetch('/vehicles/orders/?status=done&page_size=50&page=' + arCurrentPage);
    let items = data.items || [];
    if (search) {
      const sl = search.toLowerCase();
      items = items.filter(o =>
        (o.order_number||'').toLowerCase().includes(sl) ||
        (o.vehicle?.plate_number||'').toLowerCase().includes(sl) ||
        (o.description||'').toLowerCase().includes(sl)
      );
    }
    const total = data.total || 0;
    document.getElementById('arPagInfo').textContent = `${items.length} / ${total} ta`;
    const badge = document.getElementById('autoReadyBadge');
    if (badge) { badge.textContent = total; badge.style.display = total>0?'':'none'; }
    const body = document.getElementById('arBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Olib ketilmagan buyurtma yo\'q</td></tr>'; return; }
    body.innerHTML = items.map(o => `<tr>
      <td style="font-weight:700;color:var(--gold)">${o.order_number||'#'+o.id}</td>
      <td style="font-size:.8125rem">${o.vehicle?.plate_number?`<b>${o.vehicle.plate_number}</b> <span style="color:var(--text2)">${[o.vehicle.brand,o.vehicle.model].filter(Boolean).join(' ')}</span>`:'—'}</td>
      <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${o.description||'—'}</td>
      <td style="font-weight:700">${fmtMoney(o.total_amount||0)} UZS</td>
      <td style="color:${(o.paid_amount||0)>=(o.total_amount||0)?'var(--success)':'var(--warning)'}">${fmtMoney(o.paid_amount||0)} UZS</td>
      <td class="td-sub">${(o.completion_date||o.updated_at||'').slice(0,10)}</td>
      <td class="td-actions">
        <button class="act-btn" title="Topshirildi" onclick="soNextStatus(${o.id},'delivered')">✓</button>
      </td>
    </tr>`).join('');
    document.getElementById('arPrevBtn').disabled = arCurrentPage <= 1;
    document.getElementById('arNextBtn').disabled = items.length < 50;
  } catch(err) { toast(err.message,'error'); }
}

async function loadAutoDebt() {
  try {
    const data  = await apiFetch('/vehicles/orders/?page_size=200');
    const items = (data.items || []).filter(o => (o.total_amount||0) > (o.paid_amount||0));
    const totalDebt = items.reduce((s, o) => s + ((o.total_amount||0)-(o.paid_amount||0)), 0);
    const badge = document.getElementById('autoDebtBadge');
    if (badge) { badge.textContent = items.length; badge.style.display = items.length>0?'':'none'; }
    document.getElementById('adTotalDebt').textContent = `Jami qarz: ${fmtMoney(totalDebt)} UZS`;
    const body = document.getElementById('adBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Qarzli buyurtma yo\'q</td></tr>'; return; }
    const SO_ST = { pending:'badge-amber', in_progress:'badge-blue', done:'badge-green', delivered:'badge-gray' };
    const SO_LBL = { pending:'Kutilmoqda', in_progress:'Jarayonda', done:'Tayyor', delivered:'Topshirildi' };
    body.innerHTML = items.sort((a,b)=>((b.total_amount||0)-(b.paid_amount||0))-((a.total_amount||0)-(a.paid_amount||0))).map(o => {
      const debt = (o.total_amount||0)-(o.paid_amount||0);
      return `<tr>
        <td style="font-weight:700;color:var(--gold)">${o.order_number||'#'+o.id}</td>
        <td style="font-size:.8125rem">${o.vehicle?.plate_number?`<b>${o.vehicle.plate_number}</b>`:'—'}</td>
        <td class="td-sub">${o.customer?.name||'—'}</td>
        <td style="font-weight:700">${fmtMoney(o.total_amount||0)} UZS</td>
        <td style="color:var(--success)">${fmtMoney(o.paid_amount||0)} UZS</td>
        <td style="font-weight:700;color:var(--danger)">${fmtMoney(debt)} UZS</td>
        <td><span class="badge ${SO_ST[o.status]||''}">${SO_LBL[o.status]||o.status}</span></td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadAutoDuration() {
  const period = document.getElementById('adurPeriod')?.value || 'week';
  try {
    const data = await apiFetch('/analytics/auto-stats?period=' + period);
    document.getElementById('adurAvg').textContent = (data.avg_hours||0) + ' soat';
    // Get detailed orders for duration table
    const oData = await apiFetch('/vehicles/orders/?page_size=200');
    const orders = (oData.items||[]).filter(o => o.completion_date && o.intake_date && ['done','delivered'].includes(o.status));
    if (!orders.length) {
      document.getElementById('adurMin').textContent = '—';
      document.getElementById('adurMax').textContent = '—';
      document.getElementById('adurBody').innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>';
      return;
    }
    const withDur = orders.map(o => {
      const hrs = Math.round(((new Date(o.completion_date) - new Date(o.intake_date)) / 3600000) * 10) / 10;
      return { ...o, hrs };
    }).filter(o => o.hrs > 0).sort((a,b) => b.hrs - a.hrs);
    document.getElementById('adurMin').textContent = (withDur.at(-1)?.hrs||0) + ' soat';
    document.getElementById('adurMax').textContent = (withDur[0]?.hrs||0) + ' soat';
    const SO_LBL = { pending:'Kutilmoqda', in_progress:'Jarayonda', done:'Tayyor', delivered:'Topshirildi' };
    const SO_CLS = { pending:'badge-amber', in_progress:'badge-blue', done:'badge-green', delivered:'badge-gray' };
    document.getElementById('adurBody').innerHTML = withDur.map(o => `<tr>
      <td style="font-weight:700;color:var(--gold)">${o.order_number||'#'+o.id}</td>
      <td>${o.vehicle?.plate_number?`<b>${o.vehicle.plate_number}</b> <span style="color:var(--text2)">${[o.vehicle.brand,o.vehicle.model].filter(Boolean).join(' ')}</span>`:'—'}</td>
      <td class="td-sub">${(o.intake_date||'').slice(0,10)}</td>
      <td class="td-sub">${(o.completion_date||'').slice(0,10)}</td>
      <td style="font-weight:700;color:${o.hrs>24?'var(--danger)':o.hrs>8?'var(--warning)':'var(--success)'}">${o.hrs} soat</td>
      <td><span class="badge ${SO_CLS[o.status]||''}">${SO_LBL[o.status]||o.status}</span></td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadAutoBrands() {
  try {
    const [vData, oData] = await Promise.all([
      apiFetch('/vehicles/?page_size=200'),
      apiFetch('/vehicles/orders/?page_size=500'),
    ]);
    const vehicles   = vData.items || [];
    const orders     = oData.items || [];
    const vMap = {};
    vehicles.forEach(v => { vMap[v.id] = v; });
    const brandMap = {};
    vehicles.forEach(v => {
      const brand = v.brand || 'Boshqa';
      if (!brandMap[brand]) brandMap[brand] = { count: 0, orders: 0, revenue: 0 };
      brandMap[brand].count++;
    });
    orders.forEach(o => {
      if (!o.vehicle_id) return;
      const v = vMap[o.vehicle_id];
      const brand = v?.brand || 'Boshqa';
      if (!brandMap[brand]) brandMap[brand] = { count: 0, orders: 0, revenue: 0 };
      brandMap[brand].orders++;
      brandMap[brand].revenue += o.total_amount || 0;
    });
    const totalVeh = vehicles.length || 1;
    const items = Object.entries(brandMap).sort((a,b) => b[1].count - a[1].count);
    const body = document.getElementById('abBody');
    if (!items.length) { body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Avtomobil topilmadi</td></tr>'; return; }
    const colors = ['#f59e0b','#3b82f6','#10b981','#ef4444','#8b5cf6'];
    body.innerHTML = items.map(([brand, s], i) => `<tr>
      <td style="font-weight:700;color:${colors[i%colors.length]};text-align:center">${i+1}</td>
      <td class="td-bold" style="color:${colors[i%colors.length]}">${brand}</td>
      <td style="font-weight:700">${s.count} ta</td>
      <td>${s.orders} ta</td>
      <td class="td-gold">${fmtMoney(s.revenue)} UZS</td>
      <td style="font-weight:700;color:${colors[i%colors.length]}">${Math.round(s.count/totalVeh*100)}%</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadAutoClients() {
  const search = document.getElementById('acSearch')?.value || '';
  try {
    const data   = await apiFetch('/vehicles/orders/?page_size=500');
    const orders = data.items || [];
    const clientMap = {};
    orders.forEach(o => {
      const cname = o.customer?.name || 'Noma\'lum';
      const cphone = o.customer?.phone || '—';
      const key = cname.toLowerCase();
      if (!clientMap[key]) clientMap[key] = { name: cname, phone: cphone, orders: 0, total: 0, paid: 0, plates: new Set(), last: null };
      clientMap[key].orders++;
      clientMap[key].total += o.total_amount || 0;
      clientMap[key].paid  += o.paid_amount  || 0;
      if (o.vehicle?.plate_number) clientMap[key].plates.add(o.vehicle.plate_number);
      const d = (o.created_at||'').slice(0,10);
      if (!clientMap[key].last || d > clientMap[key].last) clientMap[key].last = d;
    });
    let items = Object.values(clientMap).sort((a,b) => b.total - a.total);
    if (search) {
      const sl = search.toLowerCase();
      items = items.filter(c => c.name.toLowerCase().includes(sl) || [...c.plates].some(p => p.toLowerCase().includes(sl)));
    }
    const body = document.getElementById('acBody');
    if (!items.length) { body.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Mijoz topilmadi</td></tr>'; return; }
    body.innerHTML = items.slice(0,50).map((c, i) => `<tr>
      <td style="font-weight:700;color:var(--text2)">${i+1}</td>
      <td class="td-bold">${c.name}</td>
      <td class="td-sub" style="font-size:.75rem">${[...c.plates].join(', ')||'—'}</td>
      <td style="font-weight:700">${c.orders} ta</td>
      <td class="td-gold">${fmtMoney(c.total)} UZS</td>
      <td style="color:${c.paid>=c.total?'var(--success)':'var(--warning)'}">${fmtMoney(c.paid)} UZS</td>
      <td class="td-sub">${c.last||'—'}</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function updateAutoReadyBadge() {
  try {
    const data = await apiFetch('/vehicles/orders/?status=done&page_size=1');
    const cnt  = data.total || 0;
    const badge = document.getElementById('autoReadyBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt>0?'':'none'; }
  } catch {}
}

async function updateAutoDebtBadge() {
  try {
    const data  = await apiFetch('/vehicles/orders/?page_size=100');
    const cnt   = (data.items||[]).filter(o => (o.total_amount||0) > (o.paid_amount||0)).length;
    const badge = document.getElementById('autoDebtBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt>0?'':'none'; }
  } catch {}
}

