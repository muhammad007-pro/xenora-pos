/* XENORA admin — AQLLI HISOBOT (BOSQICH 27) moduli (refaktoring 3-bo'lak).
   CLASSIC <script src>, katta scriptdan OLDIN. Global scope saqlanadi. */
// ── BOSQICH 27: Aqlli hisobot va nazorat ─────────────────────────────────────

async function loadStoreDashboard() {
  try {
    const d = await apiFetch('/analytics/store-dashboard');
    document.getElementById('sdTodayRevenue').textContent = fmtMoney(d.today_revenue);
    document.getElementById('sdTodayProfit').textContent  = fmtMoney(d.today_profit);
    document.getElementById('sdTodayOrders').textContent  = d.today_orders;
    document.getElementById('sdMonthRevenue').textContent = fmtMoney(d.month_revenue);
    document.getElementById('sdLowStock').textContent     = d.low_stock_count;
    document.getElementById('sdSupplierDebt').textContent = fmtMoney(d.supplier_debt);

    const top5 = document.getElementById('sdTop5Body');
    top5.innerHTML = d.top5_today.length ? d.top5_today.map((p,i) => `
      <tr>
        <td style="color:var(--text3)">${i+1}</td>
        <td style="font-weight:600">${p.product_name}</td>
        <td>${p.qty}</td>
        <td style="color:var(--success)">${fmtMoney(p.revenue)}</td>
      </tr>
    `).join('') : '<tr><td colspan="4" style="text-align:center;padding:1rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>';

    const chart = document.getElementById('sdTrendChart');
    const maxRev = Math.max(...d.daily_trend.map(x => x.revenue), 1);
    chart.innerHTML = d.daily_trend.map(x => {
      const h = Math.max(Math.round((x.revenue / maxRev) * 120), 4);
      return `<div title="${x.date}: ${fmtMoney(x.revenue)}" style="flex:1;background:var(--gold);border-radius:3px 3px 0 0;height:${h}px;opacity:.85;cursor:default"></div>`;
    }).join('');
  } catch(e) { console.error('storeDashboard error', e); }
}

async function loadAbcAnalysis() {
  const period = document.getElementById('abcPeriod')?.value || 'month';
  try {
    const d = await apiFetch(`/analytics/abc-analysis?period=${period}`);
    document.getElementById('abcACount').textContent = d.summary.A.count + ' tovar';
    document.getElementById('abcBCount').textContent = d.summary.B.count + ' tovar';
    document.getElementById('abcCCount').textContent = d.summary.C.count + ' tovar';
    document.getElementById('abcTotal').textContent  = `Jami foyda: ${fmtMoney(d.total_profit)}`;

    const groupColor = {A:'#10b981', B:'#f59e0b', C:'#ef4444'};
    const groupBg    = {A:'rgba(16,185,129,.1)', B:'rgba(245,158,11,.1)', C:'rgba(239,68,68,.1)'};
    document.getElementById('abcBody').innerHTML = d.items.map((item, i) => `
      <tr style="background:${groupBg[item.group]}">
        <td style="color:var(--text3)">${i+1}</td>
        <td><span style="background:${groupColor[item.group]};color:#fff;padding:2px 8px;border-radius:12px;font-weight:700;font-size:.75rem">${item.group}</span></td>
        <td style="font-weight:600">${item.name}</td>
        <td>${item.qty_sold}</td>
        <td>${fmtMoney(item.revenue)}</td>
        <td style="color:${groupColor[item.group]};font-weight:600">${fmtMoney(item.profit)}</td>
        <td>${item.margin_pct}%</td>
        <td>${item.cumulative_pct}%</td>
      </tr>
    `).join('');
  } catch(e) { document.getElementById('abcBody').innerHTML = `<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--red)">Xatolik: ${e.message}</td></tr>`; }
}

let _reorderSuppliers = [];
async function loadReorderSuppliers() {
  try {
    const data = await apiFetch('/suppliers-b2b/');
    _reorderSuppliers = data.items || data || [];
  } catch {}
}

async function loadReorderAlerts() {
  try {
    const [alertsD, settingsD] = await Promise.all([
      apiFetch('/analytics/reorder-alerts'),
      apiFetch('/reorder-settings/'),
    ]);
    const alerts   = alertsD.alerts || [];
    const settings = settingsD || [];

    document.getElementById('raAlertCount').textContent    = alertsD.total || 0;
    document.getElementById('raSettingsCount').textContent = settings.length;
    if (reorderBadgeEl) { reorderBadgeEl.textContent = alertsD.total; reorderBadgeEl.style.display = alertsD.total > 0 ? '' : 'none'; }

    document.getElementById('raAlertsBody').innerHTML = alerts.length ? alerts.map(a => `
      <tr style="background:rgba(239,68,68,.06)">
        <td style="font-weight:600">${a.product_name}</td>
        <td style="color:var(--red);font-weight:600">${a.current_qty}</td>
        <td>${a.min_qty}</td>
        <td style="color:var(--red)">${a.deficit}</td>
        <td style="color:var(--success);font-weight:600">${a.reorder_qty}</td>
        <td>${a.supplier_name ? `<span style="color:var(--gold)">${a.supplier_name}</span>${a.supplier_phone ? '<br><small style="color:var(--text3)">'+a.supplier_phone+'</small>' : ''}` : '<span style="color:var(--text3)">—</span>'}</td>
        <td><button class="tb-btn" style="font-size:.75rem" onclick="openReorderModal(${a.setting_id}, ${a.product_id})">O'zgartirish</button></td>
      </tr>
    `).join('') : '<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:var(--success)">Barcha tovarlar yetarli!</td></tr>';

    document.getElementById('raSettingsBody').innerHTML = settings.length ? settings.map(s => `
      <tr>
        <td style="font-weight:600">${s.product_name}</td>
        <td>${s.min_qty}</td>
        <td>${s.reorder_qty}</td>
        <td>${s.supplier_name || '<span style="color:var(--text3)">—</span>'}</td>
        <td style="color:var(--text3);font-size:.8125rem">${s.notes || ''}</td>
        <td style="display:flex;gap:.375rem">
          <button class="tb-btn" style="font-size:.75rem" onclick="openReorderModal(${s.id}, ${s.product_id})">Tahrir</button>
          <button class="tb-btn" style="font-size:.75rem;background:var(--red);color:#fff" onclick="deleteReorderSetting(${s.id})">O'chir</button>
        </td>
      </tr>
    `).join('') : '<tr><td colspan="6" style="text-align:center;padding:1.5rem;color:var(--text3)">Sozlamalar yo\'q</td></tr>';
  } catch(e) { console.error('reorderAlerts error', e); }
}

const reorderBadgeEl = document.getElementById('reorderBadge');

let _tvAllItems = [], _tvFilter = '';
function tvSetFilter(cat) {
  _tvFilter = cat;
  renderTurnover();
}
function renderTurnover() {
  const filtered = _tvFilter ? _tvAllItems.filter(i => i.category === _tvFilter) : _tvAllItems;
  const catLabel = {fast:'Tez ketadi', normal:'Normal', slow:'Sekin', dead:"O'lik tovar"};
  const catColor = {fast:'#10b981', normal:'#3b82f6', slow:'#f59e0b', dead:'#ef4444'};
  document.getElementById('tvBody').innerHTML = filtered.length ? filtered.map(item => `
    <tr>
      <td style="font-weight:600">${item.product_name}</td>
      <td>${item.current_qty}</td>
      <td>${item.qty_sold}</td>
      <td style="color:var(--text2)">${item.avg_daily}</td>
      <td>${item.days_of_stock !== null ? item.days_of_stock + ' kun' : '<span style="color:var(--text3)">∞</span>'}</td>
      <td><span style="background:${catColor[item.category]};color:#fff;padding:2px 10px;border-radius:12px;font-size:.75rem">${catLabel[item.category]}</span></td>
    </tr>
  `).join('') : `<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma'lumot yo'q</td></tr>`;
}
async function loadTurnoverAnalysis() {
  const period = document.getElementById('tvPeriod')?.value || 'month';
  try {
    const d = await apiFetch(`/analytics/turnover?period=${period}`);
    _tvAllItems = d.items || [];
    document.getElementById('tvFastCount').textContent   = d.counts.fast   || 0;
    document.getElementById('tvNormalCount').textContent = d.counts.normal || 0;
    document.getElementById('tvSlowCount').textContent   = d.counts.slow   || 0;
    document.getElementById('tvDeadCount').textContent   = d.counts.dead   || 0;
    renderTurnover();
  } catch(e) { document.getElementById('tvBody').innerHTML = `<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--red)">Xatolik</td></tr>`; }
}

async function loadPeakHours() {
  const period = document.getElementById('phPeriod')?.value || 'month';
  try {
    const d = await apiFetch(`/analytics/peak-hours?period=${period}`);
    if (d.peak_hour && d.peak_day) {
      document.getElementById('phPeakInfo').textContent =
        `Peak soat: ${d.peak_hour.label} (${d.peak_hour.count} buyurtma) | Peak kun: ${d.peak_day.label}`;
    }

    const maxH = Math.max(...d.hours.map(x => x.count), 1);
    const maxD = Math.max(...d.days.map(x => x.count), 1);

    const hChart = document.getElementById('phHoursChart');
    hChart.innerHTML = d.hours.map(h => {
      const ht = Math.max(Math.round((h.count / maxH) * 150), 4);
      const isPeak = d.peak_hour && h.hour === d.peak_hour.hour;
      return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px">
        <div title="${h.label}: ${h.count} ta" style="width:100%;background:${isPeak ? 'var(--gold)' : 'var(--bg3)'};border-radius:3px 3px 0 0;height:${ht}px;border:1px solid ${isPeak ? 'var(--gold)' : 'var(--border2)'}"></div>
        <span style="font-size:9px;color:var(--text3);writing-mode:vertical-lr;transform:rotate(180deg)">${h.hour}</span>
      </div>`;
    }).join('');

    const dChart = document.getElementById('phDaysChart');
    dChart.innerHTML = d.days.map(day => {
      const ht = Math.max(Math.round((day.count / maxD) * 150), 4);
      const isPeak = d.peak_day && day.day === d.peak_day.day;
      return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px">
        <span style="font-size:.7rem;color:var(--text2)">${day.count}</span>
        <div title="${day.label}: ${day.count} ta" style="width:100%;background:${isPeak ? 'var(--gold)' : '#3b82f6'};opacity:${isPeak ? 1 : .6};border-radius:3px 3px 0 0;height:${ht}px"></div>
        <span style="font-size:.7rem;color:var(--text2)">${day.label.slice(0,3)}</span>
      </div>`;
    }).join('');

    const maxCount = Math.max(...d.hours.map(x => x.count), 1);
    document.getElementById('phBody').innerHTML = d.hours.filter(h => h.count > 0).sort((a,b) => b.count - a.count).map(h => {
      const w = Math.round((h.count / maxCount) * 100);
      const isPeak = d.peak_hour && h.hour === d.peak_hour.hour;
      return `<tr ${isPeak ? 'style="background:rgba(201,168,76,.08)"' : ''}>
        <td style="font-weight:${isPeak ? 700 : 400}">${h.label}${isPeak ? ' ⭐' : ''}</td>
        <td>${h.count}</td>
        <td>${fmtMoney(h.revenue)}</td>
        <td><div style="background:var(--bg3);border-radius:4px;height:8px;width:120px"><div style="background:${isPeak ? 'var(--gold)' : '#3b82f6'};width:${w}%;height:100%;border-radius:4px"></div></div></td>
      </tr>`;
    }).join('');
  } catch(e) { console.error('peakHours error', e); }
}

