/* XENORA admin — MAKTAB/KURS (school) sahifalari moduli (refaktoring 2-bo'lak).
   CLASSIC <script src>, katta scriptdan OLDIN. Global scope saqlanadi. */
// ── Maktab/Kurs sahifalari ────────────────────────────────────────────────────

async function loadSchoolStats() {
  const period = document.getElementById('ssPeriod')?.value || 'month';
  try {
    const data = await apiFetch('/analytics/school-stats?period=' + period);
    document.getElementById('ssTotal').textContent    = data.total_orders    || 0;
    document.getElementById('ssRevenue').textContent  = fmtMoney(data.total_revenue||0) + ' UZS';
    document.getElementById('ssStudents').textContent = data.unique_students || 0;
    document.getElementById('ssGroups').textContent   = data.unique_groups   || 0;
    document.getElementById('ssAvg').textContent      = fmtMoney(data.avg_check||0) + ' UZS';
    const daily = data.daily || [];
    const maxRev = Math.max(...daily.map(d => d.revenue||0), 1);
    document.getElementById('ssChartBody').innerHTML = daily.length
      ? `<div style="display:flex;align-items:flex-end;gap:3px;height:70px;padding:0 .5rem">` +
        daily.map(d => {
          const pct = Math.round((d.revenue||0)/maxRev*100);
          return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px" title="${d.date}: ${fmtMoney(d.revenue)} UZS">
            <div style="width:100%;height:${Math.max(pct*0.65,2)}px;background:var(--gold);border-radius:2px 2px 0 0;min-height:2px"></div>
            <div style="font-size:.6rem;color:var(--text3)">${d.date.slice(5)}</div>
          </div>`;
        }).join('') + '</div>'
      : '';
    const body = document.getElementById('ssBody');
    if (!daily.length) { body.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    body.innerHTML = daily.slice().reverse().map(d => `<tr>
      <td class="td-sub">${d.date}</td>
      <td style="font-weight:700">${d.count} ta</td>
      <td>${d.students} ta</td>
      <td class="td-gold">${fmtMoney(d.revenue)} UZS</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadSchoolTopStudents() {
  const search = document.getElementById('tsSearch')?.value || '';
  try {
    const data   = await apiFetch('/orders/?has_student=true&page_size=500');
    const orders = data.items || [];
    const studentMap = {};
    orders.forEach(o => {
      const meta  = o.biz_meta || {};
      const name  = meta.student_name || '';
      if (!name) return;
      const key   = name.toLowerCase().trim();
      if (!studentMap[key]) studentMap[key] = { name, phone: meta.student_phone||'—', group: meta.student_group||'—', count: 0, total: 0, last: null };
      studentMap[key].count++;
      studentMap[key].total += o.final_amount || 0;
      const d = (o.created_at||'').slice(0,10);
      if (!studentMap[key].last || d > studentMap[key].last) studentMap[key].last = d;
    });
    let items = Object.values(studentMap).sort((a,b) => b.total - a.total);
    if (search) {
      const sl = search.toLowerCase();
      items = items.filter(s => s.name.toLowerCase().includes(sl) || s.phone.includes(sl) || s.group.toLowerCase().includes(sl));
    }
    const body = document.getElementById('tsBody');
    if (!items.length) { body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">O\'quvchi topilmadi</td></tr>'; return; }
    const colors = ['#f59e0b','#94a3b8','#c27c1e'];
    body.innerHTML = items.slice(0,50).map((s, i) => `<tr>
      <td style="font-weight:700;text-align:center">${i<3?['🥇','🥈','🥉'][i]:i+1}</td>
      <td class="td-bold">${s.name}</td>
      <td class="td-sub">${s.phone}</td>
      <td><span class="badge badge-blue">${s.group}</span></td>
      <td style="font-weight:700">${s.count} ta</td>
      <td class="td-gold">${fmtMoney(s.total)} UZS</td>
      <td class="td-sub">${fmtMoney(s.count?s.total/s.count:0)} UZS</td>
      <td class="td-sub">${s.last||'—'}</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

let _sgdAllOrders = null;
async function loadSchoolGroupDetail() {
  try {
    if (!_sgdAllOrders) {
      const data = await apiFetch('/orders/?has_student=true&page_size=500');
      _sgdAllOrders = data.items || [];
    }
    const orders = _sgdAllOrders;
    // Build group list
    const groups = [...new Set(orders.map(o => (o.biz_meta||{}).student_group).filter(Boolean))].sort();
    const sel = document.getElementById('sgdGroup');
    if (sel && sel.options.length <= 1) {
      groups.forEach(g => { const o = document.createElement('option'); o.value = g; o.textContent = g; sel.appendChild(o); });
    }
    const selectedGroup = sel?.value || '';
    const body = document.getElementById('sgdBody');
    if (!selectedGroup) { body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Guruh tanlang</td></tr>'; return; }
    const grpOrders = orders.filter(o => (o.biz_meta||{}).student_group === selectedGroup);
    const stuMap = {};
    grpOrders.forEach(o => {
      const meta = o.biz_meta || {};
      const key  = (meta.student_name||'').toLowerCase();
      if (!key) return;
      if (!stuMap[key]) stuMap[key] = { name: meta.student_name||'—', phone: meta.student_phone||'—', count: 0, total: 0, last: null };
      stuMap[key].count++;
      stuMap[key].total += o.final_amount || 0;
      const d = (o.created_at||'').slice(0,10);
      if (!stuMap[key].last || d > stuMap[key].last) stuMap[key].last = d;
    });
    const students = Object.values(stuMap).sort((a,b) => b.total - a.total);
    document.getElementById('sgdStudents').textContent = students.length;
    document.getElementById('sgdOrders').textContent   = grpOrders.length;
    document.getElementById('sgdRevenue').textContent  = fmtMoney(students.reduce((s,x)=>s+x.total,0)) + ' UZS';
    if (!students.length) { body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">O\'quvchi topilmadi</td></tr>'; return; }
    body.innerHTML = students.map((s,i) => `<tr>
      <td style="font-weight:700;color:var(--text2)">${i+1}</td>
      <td class="td-bold">${s.name}</td>
      <td class="td-sub">${s.phone}</td>
      <td style="font-weight:700">${s.count} ta</td>
      <td class="td-gold">${fmtMoney(s.total)} UZS</td>
      <td class="td-sub">${s.last||'—'}</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadSchoolPayments() {
  const period = document.getElementById('spPeriod')?.value || 'month';
  try {
    const data  = await apiFetch('/analytics/cashier-report?period=' + period);
    // cashier-report returns per-cashier; sum up payment methods
    const methodTotals = { cash:0, card:0, click:0, payme:0, qr:0 };
    const methodCounts = { cash:0, card:0, click:0, payme:0, qr:0 };
    (data||[]).forEach(c => {
      Object.keys(methodTotals).forEach(m => {
        methodTotals[m] += c[m] || 0;
        if (c[m] > 0) methodCounts[m]++;
      });
    });
    const totalRev = Object.values(methodTotals).reduce((s,v)=>s+v, 0) || 1;
    const LABELS = { cash:'Naqd', card:'Karta', click:'Click', payme:'Payme', qr:'QR' };
    const COLORS = { cash:'#10b981', card:'#3b82f6', click:'#f59e0b', payme:'#8b5cf6', qr:'#ec4899' };
    const methods = Object.entries(methodTotals).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]);
    // Mini bar chart
    document.getElementById('spPieBody').innerHTML = methods.length
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
    const body = document.getElementById('spBody');
    if (!methods.length) { body.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    body.innerHTML = methods.map(([m,v]) => `<tr>
      <td><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${COLORS[m]||'#666'};margin-right:.5rem"></span><b>${LABELS[m]||m}</b></td>
      <td style="font-weight:700">${methodCounts[m]} ta tranzaksiya</td>
      <td class="td-gold">${fmtMoney(v)} UZS</td>
      <td style="font-weight:700;color:${COLORS[m]||'var(--gold)'}">${Math.round(v/totalRev*100)}%</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadSchoolMonthly() {
  try {
    const data    = await apiFetch('/analytics/school-stats?period=month');
    const monthly = (data.monthly || []).slice(-6);
    const body    = document.getElementById('smBody');
    const maxRev  = Math.max(...monthly.map(m=>m.revenue||0), 1);
    document.getElementById('smChartBody').innerHTML = monthly.length
      ? `<div style="display:flex;align-items:flex-end;gap:6px;height:80px;padding:0 .5rem">` +
        monthly.map(m => {
          const pct = Math.round((m.revenue||0)/maxRev*100);
          return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px" title="${m.month}: ${fmtMoney(m.revenue)} UZS">
            <div style="width:100%;height:${Math.max(pct*0.72,2)}px;background:var(--gold);border-radius:2px 2px 0 0"></div>
            <div style="font-size:.65rem;color:var(--text3)">${m.month.slice(5)}</div>
          </div>`;
        }).join('') + '</div>'
      : '';
    if (!monthly.length) { body.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    body.innerHTML = monthly.slice().reverse().map((m, i, arr) => {
      const prev = arr[i+1];
      const chg  = prev && prev.revenue > 0 ? Math.round((m.revenue - prev.revenue)/prev.revenue*100) : null;
      const chgHtml = chg === null ? '—' : `<span style="color:${chg>=0?'var(--success)':'var(--danger)'}">${chg>=0?'+':''}${chg}%</span>`;
      return `<tr>
        <td class="td-bold">${m.month}</td>
        <td style="font-weight:700">${m.count} ta</td>
        <td>${m.students} ta</td>
        <td class="td-gold">${fmtMoney(m.revenue)} UZS</td>
        <td>${chgHtml}</td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

async function loadSchoolTopCourses() {
  const period = document.getElementById('stcPeriod')?.value || 'month';
  const now    = new Date();
  const start  = period === 'week' ? new Date(now - 7*86400000) : new Date(now - 30*86400000);
  try {
    const data   = await apiFetch('/orders/?has_student=true&page_size=500');
    const orders = (data.items||[]).filter(o => new Date(o.created_at) >= start);
    // Aggregate order items (products/courses)
    const courseMap = {};
    orders.forEach(o => {
      (o.items||[]).forEach(item => {
        const name = item.product_name || item.name || '—';
        if (!courseMap[name]) courseMap[name] = { count: 0, students: new Set(), revenue: 0 };
        courseMap[name].count++;
        courseMap[name].revenue += item.total_price || 0;
        const sname = (o.biz_meta||{}).student_name || '';
        if (sname) courseMap[name].students.add(sname.toLowerCase());
      });
    });
    const items    = Object.entries(courseMap).sort((a,b) => b[1].revenue - a[1].revenue);
    const totalRev = items.reduce((s,[,v])=>s+v.revenue, 0) || 1;
    const body     = document.getElementById('stcBody');
    if (!items.length) { body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const colors = ['#f59e0b','#3b82f6','#10b981','#ef4444','#8b5cf6'];
    body.innerHTML = items.map(([name, s], i) => `<tr>
      <td style="font-weight:700;color:${colors[i%colors.length]};text-align:center">${i+1}</td>
      <td class="td-bold">${name}</td>
      <td style="font-weight:700">${s.count} ta</td>
      <td>${s.students.size} ta</td>
      <td class="td-gold">${fmtMoney(s.revenue)} UZS</td>
      <td style="font-weight:700;color:${colors[i%colors.length]}">${Math.round(s.revenue/totalRev*100)}%</td>
    </tr>`).join('');
  } catch(err) { toast(err.message,'error'); }
}

