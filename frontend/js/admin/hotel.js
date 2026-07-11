/* ─────────────────────────────────────────────────────────────────────────────
   XENORA admin — MEHMONXONA (hotel) moduli.
   admin.html katta <script>'idan ajratildi (refaktoring 2-bo'lak). CLASSIC script
   (modul EMAS) — global scope saqlanadi; funksiyalar window'da qoladi, inline
   onclick/onchange handlerlar tegilmasdan ishlaydi. Katta scriptdan OLDIN yuklanadi
   (badge-init updateHotelDebtBadge() ni sinxron chaqiradi). Shared helper (apiFetch,
   fmtMoney, toast) katta scriptda — runtime'da chaqiriladi.
   ───────────────────────────────────────────────────────────────────────────── */
// HOTEL – 6 ta professional funksiya (BOSQICH 14q)
// ═══════════════════════════════════════════════════════════════
async function loadHotelStats() {
  const period = document.getElementById('htPeriod')?.value || 'month';
  try {
    const d = await apiFetch('/analytics/hotel-stats?period=' + period);
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('htRevenue',   fmtMoney(d.total_revenue)  + ' UZS');
    set('htPaid',      fmtMoney(d.total_paid)      + ' UZS');
    set('htDebt',      fmtMoney(d.debt_total)      + ' UZS');
    set('htNights',    (d.total_nights || 0)       + ' kun');
    set('htTotalRooms', d.total_rooms  || 0);
    set('htOccupied',  d.occupied_now  || 0);
    set('htOccPct',   (d.occupancy_pct || 0)       + '%');
    const daily = d.daily || [];
    const maxRev = Math.max(...daily.map(x => x.revenue), 1);
    const chart = document.getElementById('htChartBody');
    if (chart) chart.innerHTML = daily.length
      ? `<div style="display:flex;align-items:flex-end;gap:4px;height:120px;margin-top:1rem;padding:0 .5rem">` +
        daily.map(x => {
          const h = Math.max(4, Math.round(x.revenue / maxRev * 110));
          return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;cursor:default" title="${x.date}: ${fmtMoney(x.revenue)} UZS">
            <div style="width:100%;height:${h}px;background:var(--gold);border-radius:3px 3px 0 0;opacity:.85"></div>
            <div style="font-size:.6rem;color:var(--text3);writing-mode:vertical-rl;transform:rotate(180deg);max-height:36px;overflow:hidden">${x.date.slice(5)}</div>
          </div>`;
        }).join('') + '</div>'
      : '<p style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</p>';
  } catch(err) { toast(err.message,'error'); }
}

async function loadHotelOccupancy() {
  const period = document.getElementById('hoPeriod')?.value || 'month';
  try {
    const [roomsData, bkData] = await Promise.all([
      apiFetch('/rooms/?page_size=200'),
      apiFetch('/rooms/bookings/?page_size=500'),
    ]);
    const rooms    = roomsData.items || roomsData || [];
    const bookings = bkData.items   || bkData   || [];

    const now = new Date();
    const cutoff = period === 'week' ? new Date(now - 7*86400000) : new Date(now - 30*86400000);

    const bkFiltered = bookings.filter(b => b.status !== 'cancelled' && new Date(b.created_at) >= cutoff);
    const bkByRoom = {};
    bkFiltered.forEach(b => {
      if (!bkByRoom[b.room_id]) bkByRoom[b.room_id] = { count:0, nights:0, revenue:0 };
      bkByRoom[b.room_id].count++;
      bkByRoom[b.room_id].nights  += b.nights || 0;
      bkByRoom[b.room_id].revenue += b.total_amount || 0;
    });
    const STATUS_LBL = { available:'Bo\'sh', occupied:'Band', cleaning:'Tozalanmoqda', maintenance:'Ta\'mirda' };
    const STATUS_CLR = { available:'var(--success)', occupied:'var(--danger)', cleaning:'var(--warning)', maintenance:'var(--text3)' };
    const body = document.getElementById('hoBody');
    body.innerHTML = rooms.length
      ? rooms.map(r => {
          const s = bkByRoom[r.id] || { count:0, nights:0, revenue:0 };
          return `<tr>
            <td><b>${r.number || r.name}</b></td>
            <td>${r.room_type || '—'}</td>
            <td>${fmtMoney(r.price_per_night || 0)} UZS</td>
            <td>${s.count}</td>
            <td>${s.nights}</td>
            <td class="td-gold">${fmtMoney(s.revenue)} UZS</td>
            <td><span style="color:${STATUS_CLR[r.status]||'var(--text2)'}">${STATUS_LBL[r.status]||r.status||'—'}</span></td>
          </tr>`;
        }).join('')
      : '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text3)">Xonalar yo\'q</td></tr>';
  } catch(err) { toast(err.message,'error'); }
}

async function loadHotelGuests() {
  const search = (document.getElementById('hgSearch')?.value || '').toLowerCase();
  try {
    const data = await apiFetch('/rooms/bookings/?page_size=500');
    const bookings = data.items || data || [];
    const guestMap = {};
    bookings.filter(b => b.status !== 'cancelled').forEach(b => {
      const key = (b.guest_phone || '') + '|' + (b.guest_name || '');
      if (!guestMap[key]) guestMap[key] = { name: b.guest_name||'—', phone: b.guest_phone||'—', count:0, nights:0, total:0, paid:0, last:'' };
      guestMap[key].count++;
      guestMap[key].nights += b.nights || 0;
      guestMap[key].total  += b.total_amount || 0;
      guestMap[key].paid   += b.paid_amount  || 0;
      const d = b.check_in || b.created_at || '';
      if (d > guestMap[key].last) guestMap[key].last = d;
    });
    let guests = Object.values(guestMap).sort((a,b) => b.count - a.count);
    if (search) guests = guests.filter(g => g.name.toLowerCase().includes(search) || g.phone.includes(search));
    const body = document.getElementById('hgBody');
    body.innerHTML = guests.length
      ? guests.map((g,i) => `<tr>
          <td>${i+1}</td>
          <td><b>${g.name}</b></td>
          <td>${g.phone}</td>
          <td>${g.count}</td>
          <td>${g.nights}</td>
          <td class="td-gold">${fmtMoney(g.total)} UZS</td>
          <td>${fmtMoney(g.paid)} UZS</td>
          <td>${g.last ? fmtDate(g.last) : '—'}</td>
        </tr>`).join('')
      : '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Mehmon topilmadi</td></tr>';
  } catch(err) { toast(err.message,'error'); }
}

async function loadHotelDebt() {
  try {
    const data = await apiFetch('/rooms/bookings/?page_size=500');
    const bookings = (data.items || data || []).filter(b =>
      b.status !== 'cancelled' && (b.total_amount || 0) > (b.paid_amount || 0)
    );
    const totalDebt = bookings.reduce((s,b) => s + ((b.total_amount||0)-(b.paid_amount||0)), 0);
    const el = document.getElementById('hdTotalDebt');
    if (el) el.textContent = 'Jami qarz: ' + fmtMoney(totalDebt) + ' UZS';
    const badge = document.getElementById('hotelDebtBadge');
    if (badge) { badge.textContent = bookings.length; badge.style.display = bookings.length ? '' : 'none'; }
    const STATUS_LBL = { pending:'Kutilmoqda', confirmed:'Tasdiqlangan', checked_in:'Kirgan', checked_out:'Chiqqan' };
    const body = document.getElementById('hdBody');
    body.innerHTML = bookings.length
      ? bookings.map(b => {
          const debt = (b.total_amount||0)-(b.paid_amount||0);
          return `<tr>
            <td>${b.room_id || '—'}</td>
            <td><b>${b.guest_name||'—'}</b></td>
            <td>${b.guest_phone||'—'}</td>
            <td>${b.nights||0}</td>
            <td>${fmtMoney(b.total_amount||0)} UZS</td>
            <td>${fmtMoney(b.paid_amount||0)} UZS</td>
            <td style="color:var(--danger);font-weight:700">${fmtMoney(debt)} UZS</td>
            <td>${STATUS_LBL[b.status]||b.status||'—'}</td>
          </tr>`;
        }).join('')
      : '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Qarzli bron yo\'q</td></tr>';
  } catch(err) { toast(err.message,'error'); }
}

async function updateHotelDebtBadge() {
  try {
    const data = await apiFetch('/rooms/bookings/?page_size=500');
    const cnt = (data.items || data || []).filter(b =>
      b.status !== 'cancelled' && (b.total_amount||0) > (b.paid_amount||0)
    ).length;
    const badge = document.getElementById('hotelDebtBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt > 0 ? '' : 'none'; }
  } catch {}
}

async function loadHotelArrivals() {
  const today = new Date().toISOString().slice(0,10);
  try {
    const data = await apiFetch('/rooms/bookings/?page_size=500');
    const bookings = data.items || data || [];
    const checkins  = bookings.filter(b => b.check_in  && b.check_in.slice(0,10)  === today);
    const checkouts = bookings.filter(b => b.check_out && b.check_out.slice(0,10) === today);
    const renderTable = (list, tbodyId) => {
      const STATUS_LBL = { pending:'Kutilmoqda', confirmed:'Tasdiqlangan', checked_in:'Kirgan', checked_out:'Chiqqan', cancelled:'Bekor' };
      const STATUS_CLR = { pending:'var(--warning)', confirmed:'var(--gold)', checked_in:'var(--success)', checked_out:'var(--text3)', cancelled:'var(--danger)' };
      const body = document.getElementById(tbodyId);
      body.innerHTML = list.length
        ? list.map(b => `<tr>
            <td>${b.room_id||'—'}</td>
            <td><b>${b.guest_name||'—'}</b></td>
            <td>${b.guest_phone||'—'}</td>
            <td>${b.nights||0}</td>
            <td class="td-gold">${fmtMoney(b.total_amount||0)} UZS</td>
            <td><span style="color:${STATUS_CLR[b.status]||'var(--text2)'}">${STATUS_LBL[b.status]||b.status||'—'}</span></td>
          </tr>`).join('')
        : `<tr><td colspan="6" style="text-align:center;padding:1.5rem;color:var(--text3)">Yo'q</td></tr>`;
    };
    renderTable(checkins,  'haCheckinBody');
    renderTable(checkouts, 'haCheckoutBody');
  } catch(err) { toast(err.message,'error'); }
}

async function loadHotelRoomRevenue() {
  const period = document.getElementById('hrrPeriod')?.value || 'month';
  try {
    const [roomsData, bkData] = await Promise.all([
      apiFetch('/rooms/?page_size=200'),
      apiFetch('/rooms/bookings/?page_size=500'),
    ]);
    const rooms    = roomsData.items || roomsData || [];
    const bookings = bkData.items   || bkData   || [];

    const now = new Date();
    const cutoff = period === 'week' ? new Date(now - 7*86400000) : new Date(now - 30*86400000);
    const bkFiltered = bookings.filter(b => b.status !== 'cancelled' && new Date(b.created_at) >= cutoff);

    const rMap = {};
    rooms.forEach(r => { rMap[r.id] = r; });
    const revByRoom = {};
    bkFiltered.forEach(b => {
      if (!revByRoom[b.room_id]) revByRoom[b.room_id] = { count:0, nights:0, revenue:0 };
      revByRoom[b.room_id].count++;
      revByRoom[b.room_id].nights  += b.nights || 0;
      revByRoom[b.room_id].revenue += b.total_amount || 0;
    });
    const totalRev = Object.values(revByRoom).reduce((s,v) => s+v.revenue, 0) || 1;
    const sorted = Object.entries(revByRoom)
      .map(([rid, s]) => ({ room: rMap[rid], ...s, rid }))
      .sort((a,b) => b.revenue - a.revenue);
    const body = document.getElementById('hrrBody');
    body.innerHTML = sorted.length
      ? sorted.map((row, i) => {
          const r = row.room;
          const pct = Math.round(row.revenue / totalRev * 100);
          return `<tr>
            <td>${i+1}</td>
            <td><b>${r ? (r.number||r.name) : row.rid}</b></td>
            <td>${r ? (r.room_type||'—') : '—'}</td>
            <td>${r ? fmtMoney(r.price_per_night||0)+' UZS' : '—'}</td>
            <td>${row.count}</td>
            <td>${row.nights}</td>
            <td class="td-gold">${fmtMoney(row.revenue)} UZS</td>
            <td><div style="display:flex;align-items:center;gap:.5rem">
              <div style="flex:1;height:6px;background:var(--bg3);border-radius:3px"><div style="width:${pct}%;height:100%;background:var(--gold);border-radius:3px"></div></div>
              <span style="font-size:.75rem;min-width:28px;text-align:right">${pct}%</span>
            </div></td>
          </tr>`;
        }).join('')
      : '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Ma\'lumot yo\'q</td></tr>';
  } catch(err) { toast(err.message,'error'); }
}
