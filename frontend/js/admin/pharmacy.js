/* ─────────────────────────────────────────────────────────────────────────────
   XENORA admin — DORIXONA (pharmacy) sahifalari moduli.
   admin.html katta <script>'idan ajratildi (refaktoring 2-bo'lak). CLASSIC <script src>
   (modul EMAS), katta scriptdan OLDIN yuklanadi — global scope saqlanadi, inline
   handlerlar tegilmaydi. Shared helper (apiFetch/fmtMoney/toast) katta scriptda (runtime).
   ───────────────────────────────────────────────────────────────────────────── */
// ── Dorixona sahifalari ────────────────────────────────────────────────────────

async function loadPharmStats() {
  const period = document.getElementById('psPeriod')?.value || 'week';
  try {
    const data = await apiFetch('/analytics/pharmacy-stats?period=' + period);
    document.getElementById('psTotal').textContent    = data.total_rx || 0;
    document.getElementById('psPatients').textContent = data.unique_patients || 0;
    document.getElementById('psRevenue').textContent  = fmtMoney(data.total_revenue||0) + ' UZS';
    document.getElementById('psAvg').textContent      = fmtMoney(data.avg_rx_amount||0) + ' UZS';
    const body  = document.getElementById('psBody');
    const daily = data.daily_stats || [];
    if (!daily.length) { body.innerHTML='<tr><td colspan="4" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const maxRev = Math.max(...daily.map(d=>d.revenue||0), 1);
    body.innerHTML = daily.map(d => {
      const pct = Math.round((d.revenue||0)/maxRev*100);
      return `<tr>
        <td class="td-bold">${d.date||'—'}</td>
        <td style="font-weight:700">${d.count} ta</td>
        <td>${d.patients} ta bemor</td>
        <td>
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden;min-width:80px"><div style="width:${pct}%;height:100%;background:var(--gold);border-radius:3px"></div></div>
            <span class="td-gold" style="white-space:nowrap">${fmtMoney(d.revenue||0)} UZS</span>
          </div>
        </td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

let ppCurrentPage = 1;
function ppPage(dir) { ppCurrentPage = Math.max(1, ppCurrentPage+dir); loadPharmPatients(); }

async function loadPharmPatients() {
  const search = document.getElementById('ppSearch')?.value || '';
  const params = new URLSearchParams({ page: ppCurrentPage, page_size: 20 });
  if (search) params.set('search', search);
  try {
    const data  = await apiFetch('/analytics/rx-patients?' + params);
    const items = data.items || [];
    const total = data.total || 0;
    document.getElementById('ppPagInfo').textContent = `${items.length} / ${total} ta bemor`;
    const body = document.getElementById('ppBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Bemor topilmadi</td></tr>'; return; }
    body.innerHTML = items.map((p, i) => `<tr>
      <td style="font-weight:700;color:var(--text2)">${(ppCurrentPage-1)*20+i+1}</td>
      <td class="td-bold">${p.name||'—'}</td>
      <td class="td-sub">${p.phone||'—'}</td>
      <td style="font-weight:700">${p.rx_count||0} ta retsept</td>
      <td class="td-gold">${fmtMoney(p.total_spent||0)} UZS</td>
      <td class="td-sub">${p.last_visit ? p.last_visit.slice(0,10) : '—'}</td>
    </tr>`).join('');
    document.getElementById('ppPrevBtn').disabled = ppCurrentPage <= 1;
    document.getElementById('ppNextBtn').disabled = items.length < 20;
  } catch(err) { toast(err.message,'error'); }
}

async function loadPharmTopMeds() {
  const period = document.getElementById('ptmPeriod')?.value || 'week';
  const now = new Date();
  let dateFrom;
  if (period==='today') dateFrom = new Date(now.getFullYear(),now.getMonth(),now.getDate());
  else if (period==='week') dateFrom = new Date(now - 7*86400000);
  else dateFrom = new Date(now - 30*86400000);
  try {
    const data  = await apiFetch('/analytics/products?date_from=' + dateFrom.toISOString() + '&limit=20');
    const items = (data.products||data||[]).sort((a,b)=>(b.quantity||0)-(a.quantity||0));
    const body  = document.getElementById('ptmBody');
    if (!items.length) { body.innerHTML='<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
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
            <span style="font-weight:700">${it.quantity||0}</span>
          </div>
        </td>
        <td class="td-gold">${fmtMoney(it.revenue||0)} UZS</td>
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

let exDaysFilter = 7;
function exSetDays(days) {
  exDaysFilter = days;
  ['7','30','90','All'].forEach(v => {
    const btn = document.getElementById('exBtn'+v);
    if (btn) btn.style.cssText = '';
  });
  const activeId = days===7?'exBtn7':days===30?'exBtn30':days===90?'exBtn90':'exBtnAll';
  const ab = document.getElementById(activeId);
  if (ab) ab.style.cssText = 'background:var(--gold);color:#000';
  loadPharmExpiry();
}

async function loadPharmExpiry() {
  const today = new Date(); today.setHours(0,0,0,0);
  try {
    const params = exDaysFilter > 0
      ? new URLSearchParams({ has_expiry: 'true', expiry_days: exDaysFilter, page_size: 100 })
      : new URLSearchParams({ has_expiry: 'true', page_size: 100 });
    const data  = await apiFetch('/products/?' + params);
    const items = data.items || [];
    let expired = 0, soon = 0, ok = 0;
    const body = document.getElementById('exBody');
    if (!items.length) {
      ['exExpired','exSoon','exOk'].forEach(id => document.getElementById(id).textContent='0');
      body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Yaroqlilik muddatli dori topilmadi</td></tr>';
      return;
    }
    body.innerHTML = items.map(p => {
      if (!p.expiry_date) return '';
      const exp  = new Date(p.expiry_date); exp.setHours(0,0,0,0);
      const days = Math.ceil((exp - today) / 86400000);
      let cls, lbl;
      if (days < 0)       { expired++; cls='badge-red';   lbl='Muddati o\'tgan'; }
      else if (days <= 30){ soon++;    cls='badge-amber'; lbl=days+' kun qoldi'; }
      else                { ok++;      cls='badge-green'; lbl='Yaroqli'; }
      return `<tr${days<0?' style="background:rgba(239,68,68,.04)"':days<=30?' style="background:rgba(245,158,11,.04)"':''}>
        <td class="td-bold">${p.name||'—'}</td>
        <td><span class="badge badge-blue">${p.category?.name||'—'}</span></td>
        <td class="td-sub">${p.batch_number||'—'}</td>
        <td style="font-weight:${days<0?700:400}">${p.expiry_date?.slice(0,10)||'—'}</td>
        <td style="font-weight:700;color:${days<0?'var(--danger)':days<=30?'var(--warning)':'var(--success)'}">${days>=0?days+' kun':'Tugagan'}</td>
        <td><span class="badge ${cls}">${lbl}</span></td>
      </tr>`;
    }).join('');
    document.getElementById('exExpired').textContent = expired;
    document.getElementById('exSoon').textContent    = soon;
    document.getElementById('exOk').textContent      = ok;
    const badge = document.getElementById('expiryBadge');
    if (badge) { const cnt=expired+soon; badge.textContent=cnt; badge.style.display=cnt>0?'':'none'; }
  } catch(err) { toast(err.message,'error'); }
}

async function loadPharmCats() {
  const period = document.getElementById('pcPeriod')?.value || 'week';
  const now = new Date();
  let dateFrom;
  if (period==='today') dateFrom = new Date(now.getFullYear(),now.getMonth(),now.getDate());
  else if (period==='week') dateFrom = new Date(now - 7*86400000);
  else dateFrom = new Date(now - 30*86400000);
  try {
    const data = await apiFetch('/analytics/categories?date_from=' + dateFrom.toISOString());
    const cats = data.categories || data || [];
    const body = document.getElementById('pcBody');
    if (!cats.length) { body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
    const totalRev = cats.reduce((s,c)=>s+(c.revenue||0), 0) || 1;
    const maxRev   = Math.max(...cats.map(c=>c.revenue||0), 1);
    const colors   = ['#3b82f6','#f59e0b','#10b981','#ef4444','#8b5cf6','#ec4899'];
    body.innerHTML = cats.map((cat, i) => {
      const pct   = Math.round((cat.revenue||0)/maxRev*100);
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

async function loadPharmCashier() {
  const period = document.getElementById('pharmCaPeriod')?.value || 'week';
  try {
    const data = await apiFetch('/analytics/cashier-report?period=' + period);
    const body = document.getElementById('pharmCaBody');
    if (!data.length) { body.innerHTML='<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>'; return; }
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
      </tr>`;
    }).join('');
  } catch(err) { toast(err.message,'error'); }
}

