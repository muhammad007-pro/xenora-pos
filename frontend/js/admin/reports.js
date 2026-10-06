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

// ── CHEK BO'YICHA FOYDA (receiptProfit) ──────────────────────────────────────
// FAQAT KO'RSATISH: hech narsa yozmaydi. Barcha son `/profit/by-receipt` dan,
// u esa `/profit/summary` ning O'Z funksiyasini ishlatadi — shu sabab
// "Sof foyda" kartasi "Foyda tahlili" ekrani bilan AYNAN mos keladi.
//
// ⚠️ Chek qatori YALPI (sotuv) foydani ko'rsatadi, vozvrat esa ALOHIDA qator:
// vozvrat sotuv sanasiga emas, QAYTARILGAN sanaga yoziladi (utils/revenue.py
// QOIDA 1), ya'ni davrdagi vozvrat boshqa davrda sotilgan chekka tegishli
// bo'lishi mumkin. Shuning uchun uni chek qatorlariga tarqatib YUBORMAYMIZ.
let rpPage = 1;
let _rpInit = false;

const _rpMarginBadge = (m) => m >= 30 ? 'badge-green' : m >= 10 ? 'badge-amber' : 'badge-red';

function _rpInitFilters() {
  if (_rpInit) return;
  ['rpPeriod','rpFrom','rpTo','rpSort','rpOrder'].forEach(id =>
    document.getElementById(id)?.addEventListener('change', () => { rpPage = 1; loadReceiptProfit(); }));
  document.getElementById('rpClearBtn')?.addEventListener('click', () => {
    ['rpFrom','rpTo'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    const p = document.getElementById('rpPeriod'); if (p) p.value = 'week';
    rpPage = 1; loadReceiptProfit();
  });
  _rpInit = true;
}

async function loadReceiptProfit() {
  _rpInitFilters();
  const params = new URLSearchParams({
    period:    document.getElementById('rpPeriod')?.value || 'week',
    sort:      document.getElementById('rpSort')?.value   || 'date',
    order:     document.getElementById('rpOrder')?.value  || 'desc',
    page:      rpPage,
    page_size: 50,
  });
  // Sana oralig'i berilsa — backend'da u `period` dan USTUN turadi
  // (core/timeutils.period_dates). Faqat bittasi berilsa ham ishlaydi.
  const from = document.getElementById('rpFrom')?.value;
  const to   = document.getElementById('rpTo')?.value;
  if (from) params.set('date_from', from);
  if (to)   params.set('date_to',   to);

  const body = document.getElementById('rpBody');
  const foot = document.getElementById('rpFoot');
  try {
    const d = await apiFetch('/profit/by-receipt?' + params);
    const t = d.totals || {};

    document.getElementById('rpSalesProfit').textContent   = fmtMoney(t.sales_profit || 0);
    document.getElementById('rpReturnsProfit').textContent = t.returns_profit ? '−' + fmtMoney(t.returns_profit) : '0';
    document.getElementById('rpNetProfit').textContent     = fmtMoney(t.net_profit || 0);
    document.getElementById('rpNetMargin').textContent     = (t.net_margin_pct || 0) + '%';
    document.getElementById('rpElapsed').textContent       = `${d.elapsed_ms} ms · ${d.period?.from} — ${d.period?.to}`;

    // Xizmat asosli bizneslarda (salon/fitnes/mehmonxona) "Foyda tahlili"
    // uchrashuv/bron asosida hisoblanadi — bu panel esa faqat chek sotuvi.
    // Farqni do'konchi XATO deb o'ylamasligi uchun backend izoh yuboradi.
    const noteEl = document.getElementById('rpNote');
    if (noteEl) {
      noteEl.textContent   = d.note || '';
      noteEl.style.display = d.note ? '' : 'none';
    }

    const items = d.items || [];
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Bu davrda sotuv topilmadi</td></tr>';
      foot.innerHTML = '';
      document.getElementById('rpPaginInfo').textContent = '0 ta';
      document.getElementById('rpPagination').innerHTML = '';
      return;
    }

    body.innerHTML = items.map(it => `
      <tr style="cursor:pointer" onclick="openReceiptProfit(${it.order_id})">
        <td class="td-sub">${fmtDate(it.created_at)}</td>
        <td class="td-bold">${it.daily_number != null ? '#' + it.daily_number : escH(it.order_number || '—')}</td>
        <td class="td-sub">${it.lines}</td>
        <td class="td-sub">${it.discount_amount ? '−' + fmtMoney(it.discount_amount) : '—'}</td>
        <td>${fmtMoney(it.revenue)}</td>
        <td class="td-sub">${fmtMoney(it.cost)}</td>
        <td style="color:var(--success);font-weight:700">${fmtMoney(it.profit)}</td>
        <td><span class="badge ${_rpMarginBadge(it.margin_pct)}">${it.margin_pct}%</span></td>
      </tr>`).join('');

    // JAMI qatori — DAVR bo'yicha (sahifa bo'yicha EMAS). Vozvrat alohida
    // qatorda, chunki u qaytarilgan sana bo'yicha ayriladi.
    const retRow = t.returns_count ? `
      <tr style="color:var(--danger)">
        <td colspan="4" style="text-align:right;padding-top:.5rem">Vozvrat (${t.returns_count} ta, qaytarilgan sana bo'yicha)</td>
        <td>−${fmtMoney(t.returns_revenue)}</td>
        <td>−${fmtMoney(t.returns_cost)}</td>
        <td style="font-weight:700">−${fmtMoney(t.returns_profit)}</td>
        <td></td>
      </tr>` : '';
    foot.innerHTML = `
      <tr style="border-top:1px solid var(--border)">
        <td colspan="4" style="text-align:right;color:var(--text3);padding-top:.5rem">Sotuv jami (${t.receipts_count} chek)</td>
        <td>${fmtMoney(t.sales_revenue)}</td>
        <td class="td-sub">${fmtMoney(t.sales_cost)}</td>
        <td style="font-weight:700">${fmtMoney(t.sales_profit)}</td>
        <td><span class="badge ${_rpMarginBadge(t.sales_margin_pct)}">${t.sales_margin_pct}%</span></td>
      </tr>
      ${retRow}
      <tr style="border-top:1px solid var(--border);font-weight:800">
        <td colspan="4" style="text-align:right">SOF FOYDA (davr)</td>
        <td>${fmtMoney(t.net_revenue)}</td>
        <td>${fmtMoney(t.net_cost)}</td>
        <td class="td-gold">${fmtMoney(t.net_profit)}</td>
        <td><span class="badge ${_rpMarginBadge(t.net_margin_pct)}">${t.net_margin_pct}%</span></td>
      </tr>`;

    document.getElementById('rpPaginInfo').textContent = `${items.length} / ${d.total} ta chek`;
    let pg = '';
    if ((d.total_pages || 1) > 1) {
      pg += `<button class="pager-btn" ${rpPage<=1?'disabled':''} onclick="rpPage--;loadReceiptProfit()">‹</button>`;
      pg += `<span style="padding:0 .5rem">${rpPage} / ${d.total_pages}</span>`;
      pg += `<button class="pager-btn" ${rpPage>=d.total_pages?'disabled':''} onclick="rpPage++;loadReceiptProfit()">›</button>`;
    }
    document.getElementById('rpPagination').innerHTML = pg;
  } catch (err) { toast(err.message, 'error'); }
}

async function openReceiptProfit(orderId) {
  openModal('receiptProfitModal');
  const el = document.getElementById('rpdBody');
  el.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text3)">Yuklanmoqda...</div>';
  try {
    const d = await apiFetch('/profit/by-receipt/' + orderId);
    document.getElementById('rpdTitle').textContent =
      'Chek foydasi ' + (d.daily_number != null ? '#' + d.daily_number : (d.order_number || ''));

    const rows = (d.items || []).map(i => `
      <tr>
        <td class="td-bold">${escH(i.product_name || '#' + i.product_id)}</td>
        <td style="text-align:center">${i.quantity}${i.unit_sold ? ' ' + escH(i.unit_sold) : ''}</td>
        <td style="text-align:right">${fmtMoney(i.unit_price)}</td>
        <td style="text-align:right;color:var(--danger)">${i.discount_share ? '−' + fmtMoney(i.discount_share) : '—'}</td>
        <td style="text-align:right">${fmtMoney(i.revenue)}</td>
        <td style="text-align:right" class="td-sub">${fmtMoney(i.cost)}</td>
        <td style="text-align:right;color:var(--success);font-weight:700">${fmtMoney(i.profit)}</td>
        <td style="text-align:right"><span class="badge ${_rpMarginBadge(i.margin_pct)}">${i.margin_pct}%</span></td>
      </tr>`).join('');

    const dc = d.discount || {};
    // Chegirma qanday taqsimlangani: koef = 1 − chegirma/subtotal, har qator
    // shunga ko'paytiriladi. Σ(ulush) = buyurtma chegirmasi (kafolat).
    const _qoldiq = Math.abs((dc.allocated_total || 0) - (dc.order_discount || 0)) > 1;
    const discBlock = dc.order_discount > 0 ? `
      <div style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:.6rem .75rem;margin:.75rem 0;font-size:.8rem;line-height:1.6">
        <b>Chegirma taqsimi:</b> ${fmtMoney(dc.order_discount)} — proporsional
        (koeffitsiyent <b>${dc.factor}</b>, ya'ni har qator
        <b>${(dc.factor * 100).toFixed(2)}%</b> qiymatida hisoblanadi).
        <br>Qatorlarga tarqatilgani: <b>${fmtMoney(dc.allocated_total)}</b>
        ${_qoldiq ? '<span style="color:var(--warning)"> ⚠️ qoldiq bor</span>'
                  : '<span style="color:var(--success)"> ✓ to&rsquo;liq</span>'}
      </div>` : '';

    const rt = d.returns_totals || {};
    const tt = d.totals || {};
    const retBlock = (d.returns || []).length ? `
      <div class="dt-head" style="margin-top:1rem;padding:0"><h3 class="dt-title" style="color:var(--danger)">Qaytarish — foydadan ayriladi</h3></div>
      <table style="width:100%;border-collapse:collapse;font-size:.82rem">
        <thead><tr style="color:var(--text3);text-align:left"><th style="padding:.3rem 0">Hujjat</th><th>Mahsulot</th><th style="text-align:center">Soni</th><th style="text-align:right">Summa</th><th style="text-align:right">Tan narx</th><th style="text-align:right">Foyda</th><th>Ayrilgan sana</th></tr></thead>
        <tbody>${d.returns.map(r => `
          <tr style="color:var(--danger)">
            <td>${escH(r.return_number || '—')}</td>
            <td>${escH(r.product_name || '—')}</td>
            <td style="text-align:center">${r.quantity}</td>
            <td style="text-align:right">−${fmtMoney(r.revenue)}</td>
            <td style="text-align:right">−${fmtMoney(r.cost)}</td>
            <td style="text-align:right;font-weight:700">−${fmtMoney(r.profit)}</td>
            <td class="td-sub">${fmtDate(r.counted_at)}</td>
          </tr>`).join('')}</tbody>
      </table>
      <div style="font-size:.75rem;color:var(--text3);margin-top:.4rem;line-height:1.5">
        ⚠️ Vozvrat <b>qaytarilgan sana</b> davriga yoziladi — yuqoridagi chek foydasi
        (<b>${fmtMoney(tt.profit)}</b>) o&rsquo;zgarmaydi, ayirish o&rsquo;sha davr
        jamisida ko&rsquo;rinadi. Jami ayrilgan: <b>−${fmtMoney(rt.profit || 0)}</b>.
      </div>` : '';

    const line = (lbl, val, bold, color) =>
      `<div style="display:flex;justify-content:space-between;padding:.3rem 0;${bold ? 'font-weight:800;border-top:1px solid var(--border);margin-top:.3rem;padding-top:.5rem' : ''}"><span style="color:var(--text3)">${lbl}</span><span${color ? ` style="color:${color}"` : ''}>${fmtMoney(val)}</span></div>`;

    // Hisobotlar FAQAT `completed` ni sanaydi (`_sales_query`). Ro'yxatdan
    // bosilganda bu holat yuzaga kelmaydi, lekin to'g'ridan ochilsa raqamlar
    // "hisobotga kirmaydi" degan ogohlantirish bilan ko'rsatiladi.
    const statusWarn = d.status && d.status !== 'completed' ? `
      <div style="background:rgba(245,158,11,.1);border:1px solid var(--warning);border-radius:8px;padding:.5rem .7rem;margin-bottom:.75rem;font-size:.78rem;line-height:1.5">
        ⚠️ Chek holati — <b>${escH(d.status)}</b>. Yakunlanmagan chek foyda
        hisobotlariga <b>kirmaydi</b>; pastdagi raqamlar faqat ma'lumot uchun.
      </div>` : '';

    el.innerHTML = `
      ${statusWarn}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:.3rem .75rem;font-size:.84rem;margin-bottom:.75rem">
        <div><span style="color:var(--text3)">Chek №:</span> <b>${d.daily_number != null ? '#' + d.daily_number : '—'}</b></div>
        <div><span style="color:var(--text3)">Sana:</span> ${fmtDate(d.created_at)}</div>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:.82rem">
        <thead><tr style="color:var(--text3);text-align:left"><th style="padding:.3rem 0">Mahsulot</th><th style="text-align:center">Soni</th><th style="text-align:right">Narx</th><th style="text-align:right">Chegirma</th><th style="text-align:right">Tushum</th><th style="text-align:right">Tan narx</th><th style="text-align:right">Foyda</th><th style="text-align:right">Marja</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="8" style="text-align:center;color:var(--text3);padding:1rem">Qator yo&rsquo;q</td></tr>'}</tbody>
      </table>
      ${discBlock}
      <div style="margin-top:.5rem">
        ${line('Tushum (chegirma ayirilgan)', tt.revenue)}
        ${line('Tan narx (sotuvdagi snapshot)', tt.cost)}
        ${line('FOYDA', tt.profit, true, 'var(--gold)')}
        <div style="display:flex;justify-content:space-between;padding:.3rem 0"><span style="color:var(--text3)">Marja</span><span><span class="badge ${_rpMarginBadge(tt.margin_pct)}">${tt.margin_pct}%</span></span></div>
      </div>
      ${(tt.tax_amount > 0 || tt.service_charge > 0) ? `
      <div style="font-size:.75rem;color:var(--text3);margin-top:.5rem;line-height:1.5">
        Chekda soliq ${fmtMoney(tt.tax_amount)} va xizmat haqi ${fmtMoney(tt.service_charge)} bor
        (yakuniy summa ${fmtMoney(tt.final_amount)}). Bular <b>mahsulot daromadi emas</b> —
        foyda hisobiga kirmaydi.
      </div>` : ''}
      ${retBlock}`;
  } catch (err) {
    el.innerHTML = `<div style="color:var(--red);padding:1rem">Xatolik: ${escH(err.message)}</div>`;
  }
}
