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

/* ── Xonalar + Bronlar (jurnal klasteri, refaktoring 3-bo'lak) ── */
// ── Hotel Rooms (mehmonxona) ──────────────────────────────────────────────────
const ROOM_STATUS = {
  available:   { lbl:"Bo'sh",        cls:'badge-green', color:'var(--success)' },
  occupied:    { lbl:'Band',         cls:'badge-red',   color:'var(--danger)'  },
  cleaning:    { lbl:'Tozalanmoqda', cls:'badge-amber', color:'var(--warning)' },
  maintenance: { lbl:"Ta'mirlashda", cls:'badge-gray',  color:'var(--text2)'   },
};
const ROOM_TYPE_LBL = { standard:'Standart', double:'Juft', suite:'Lyuks', vip:'VIP', family:'Oilaviy', dormitory:'Yotoqxona' };

async function loadHotelRooms() {
  const floor  = document.getElementById('hrFloorFilter')?.value  || '';
  const status = document.getElementById('hrStatusFilter')?.value || '';
  const params = new URLSearchParams({ page_size: 200 });
  if (floor)  params.set('floor',  floor);
  if (status) params.set('status', status);
  try {
    const data  = await apiFetch('/rooms/overview/');
    const rooms = Array.isArray(data) ? data : [];
    const filtered = rooms.filter(r =>
      (!floor  || String(r.floor) === floor) &&
      (!status || r.status === status)
    );
    document.getElementById('hrTotal').textContent     = rooms.length;
    document.getElementById('hrAvailable').textContent = rooms.filter(r => r.status === 'available').length;
    document.getElementById('hrOccupied').textContent  = rooms.filter(r => r.status === 'occupied').length;
    document.getElementById('hrCleaning').textContent  = rooms.filter(r => r.status === 'cleaning').length;
    const floors = [...new Set(rooms.map(r => r.floor))].sort();
    const sel = document.getElementById('hrFloorFilter');
    if (sel && sel.options.length <= 1 && floors.length) {
      floors.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f; opt.textContent = f + '-qavat';
        sel.appendChild(opt);
      });
    }
    const badge = document.getElementById('hotelBadge');
    const occ = rooms.filter(r => r.status === 'occupied').length;
    if (badge) { badge.textContent = occ; badge.style.display = occ > 0 ? '' : 'none'; }
    const grid = document.getElementById('hotelRoomGrid');
    if (!filtered.length) {
      grid.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text3);grid-column:1/-1">Xona topilmadi</div>';
      return;
    }
    grid.innerHTML = filtered.map(r => {
      const st  = ROOM_STATUS[r.status] || { lbl: r.status, cls: '', color: 'var(--text2)' };
      const bk  = r.booking;
      return `<div style="background:var(--bg2);border:1.5px solid ${bk ? 'var(--danger)' : r.status==='available' ? 'var(--success)' : 'var(--border2)'};border-radius:var(--r2);padding:1rem;cursor:pointer;transition:border-color .2s" onclick="switchPage('hotelBookings')">
        <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:.5rem">
          <span style="font-size:1.25rem;font-weight:800;color:var(--gold)">${r.number}</span>
          <span class="badge ${st.cls}">${st.lbl}</span>
        </div>
        <div style="font-size:.75rem;color:var(--text2);margin-bottom:.375rem">${ROOM_TYPE_LBL[r.room_type]||r.room_type} · ${r.capacity} kishi</div>
        <div style="font-size:.8125rem;font-weight:600;color:var(--gold);margin-bottom:.5rem">${fmtMoney(r.price_per_night)} / tun</div>
        ${bk ? `<div style="font-size:.75rem;color:var(--text)">👤 ${bk.guest_name}</div>
                <div style="font-size:.75rem;color:var(--text2)">${bk.check_in} → ${bk.check_out}</div>` :
                `<div style="font-size:.75rem;color:var(--text3)">${r.floor}-qavat ${r.name ? '· '+r.name : ''}</div>`}
        ${r.status !== 'available' ? `<button class="act-btn" style="margin-top:.5rem;font-size:.75rem;padding:.2rem .5rem" onclick="event.stopPropagation();hrSetStatus(${r.id},'available')">Bo'shat</button>` : ''}
        <div style="margin-top:.5rem;display:flex;gap:.35rem">
          <button class="act-btn" style="font-size:.75rem;padding:.2rem .5rem" onclick="event.stopPropagation();openRoomModal(${r.id})">Tahrir</button>
          <button class="act-btn" style="font-size:.75rem;padding:.2rem .5rem;color:var(--danger)" onclick="event.stopPropagation();deleteRoom(${r.id})">O'chir</button>
        </div>
      </div>`;
    }).join('');
  } catch(err) { toast(err.message, 'error'); }
}

async function hrSetStatus(id, status) {
  try {
    const res = await fetch(`${API_BASE}/rooms/${id}`, {
      method: 'PATCH',
      headers: { 'Authorization':'Bearer '+token, 'Content-Type':'application/json' },
      body: JSON.stringify({ status })
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast('Holat yangilandi', 'success');
    loadHotelRooms();
  } catch(err) { toast(err.message, 'error'); }
}

// ── Hotel Bookings ────────────────────────────────────────────────────────────
let hbCurrentPage = 1, hbStatusVal = '';

const HB_STATUS = {
  pending:    { lbl:'Kutilmoqda',   cls:'badge-amber' },
  confirmed:  { lbl:'Tasdiqlangan', cls:'badge-blue'  },
  checked_in: { lbl:'Keldi',        cls:'badge-green'  },
  checked_out:{ lbl:'Ketdi',        cls:'badge-gray'   },
  cancelled:  { lbl:'Bekor',        cls:'badge-red'    },
};
const HB_NEXT = { pending:'confirmed', confirmed:'checked_in', checked_in:'checked_out' };
const HB_NEXT_LBL = { pending:'Tasdiqlash', confirmed:"Ro'yxatdan o'tkazish", checked_in:'Chiqish' };

async function loadHotelBookings() {
  const search = document.getElementById('hbSearch')?.value || '';
  const today  = new Date().toISOString().slice(0, 10);
  const params = new URLSearchParams({ page: hbCurrentPage, page_size: 20 });
  if (hbStatusVal) params.set('status', hbStatusVal);
  if (search)      params.set('search', search);
  try {
    const data  = await apiFetch('/rooms/bookings/?' + params);
    const items = data.items || [];
    const total = data.total || 0;
    document.getElementById('hbCheckins').textContent  = items.filter(b => b.check_in  === today && ['confirmed','pending'].includes(b.status)).length;
    document.getElementById('hbCheckouts').textContent = items.filter(b => b.check_out === today && b.status === 'checked_in').length;
    document.getElementById('hbActive').textContent    = items.filter(b => b.status === 'checked_in').length;
    document.getElementById('hbPagInfo').textContent   = `${items.length} / ${total} ta`;
    const body = document.getElementById('hbBody');
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Bron topilmadi</td></tr>';
    } else {
      body.innerHTML = items.map(b => {
        const st     = HB_STATUS[b.status] || { lbl: b.status, cls: '' };
        const room   = b.room;
        const nextSt = HB_NEXT[b.status];
        const paid   = b.paid_amount || 0;
        const debt   = (b.total_amount || 0) - paid;
        return `<tr>
          <td style="font-weight:700;color:var(--gold)">${room ? room.number : '—'}<div style="font-size:.75rem;color:var(--text2)">${room ? ROOM_TYPE_LBL[room.room_type]||'' : ''}</div></td>
          <td><div style="font-weight:600">${b.guest_name}</div><div style="font-size:.75rem;color:var(--text2)">${b.guest_phone||''}</div></td>
          <td style="font-size:.8125rem">${b.check_in}</td>
          <td style="font-size:.8125rem">${b.check_out}</td>
          <td style="text-align:center">${b.nights}</td>
          <td><div style="font-weight:600">${fmtMoney(b.total_amount)} UZS</div>${debt > 0 ? `<div style="font-size:.75rem;color:var(--danger)">Qarzdor: ${fmtMoney(debt)}</div>` : `<div style="font-size:.75rem;color:var(--success)">To'langan</div>`}</td>
          <td><span class="badge ${st.cls}">${st.lbl}</span></td>
          <td class="td-actions">
            ${nextSt ? `<button class="act-btn" title="${HB_NEXT_LBL[b.status]}" onclick="hbNextStatus(${b.id},'${nextSt}')">›</button>` : ''}
            ${b.status !== 'cancelled' && b.status !== 'checked_out' ? `<button class="act-btn" title="Bekor qilish" onclick="hbCancel(${b.id})" style="color:var(--danger)">✕</button>` : ''}
            <button class="act-btn" title="Tahrir (holat)" onclick="openBookingModal(${b.id})">✎</button>
            <button class="act-btn" title="O'chirish" onclick="deleteBooking(${b.id})" style="color:var(--danger)">🗑</button>
          </td>
        </tr>`;
      }).join('');
    }
    document.getElementById('hbPrevBtn').disabled = hbCurrentPage <= 1;
    document.getElementById('hbNextBtn').disabled = items.length < 20;
  } catch(err) { toast(err.message, 'error'); }
}

function hbApplyFilter() { hbStatusVal = document.getElementById('hbFilter')?.value||''; hbCurrentPage=1; loadHotelBookings(); }
function hbPage(dir)     { hbCurrentPage = Math.max(1, hbCurrentPage + dir); loadHotelBookings(); }

async function hbNextStatus(id, newStatus) {
  try {
    const res = await fetch(`${API_BASE}/rooms/bookings/${id}`, {
      method: 'PATCH',
      headers: { 'Authorization':'Bearer '+token, 'Content-Type':'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast(HB_STATUS[newStatus]?.lbl + ' holatiga o\'tkazildi', 'success');
    loadHotelBookings();
    updateHotelBadge();
  } catch(err) { toast(err.message, 'error'); }
}

async function hbCancel(id) {
  try {
    const res = await fetch(`${API_BASE}/rooms/bookings/${id}`, {
      method: 'DELETE',
      headers: { 'Authorization':'Bearer '+token }
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast('Bron bekor qilindi', 'success');
    loadHotelBookings();
  } catch(err) { toast(err.message, 'error'); }
}

async function updateHotelBadge() {
  try {
    const data = await apiFetch('/rooms/?status=occupied&page_size=1');
    const cnt  = data.total || 0;
    const badge = document.getElementById('hotelBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt > 0 ? '' : 'none'; }
  } catch {}
}


// ═══ Hotel: Xona + Bron qo'shish/tahrirlash formalari (stub yopish) ═══════════════
// Backend /rooms + /rooms/bookings CRUD tayyor. nights/total backend hisoblaMAYDI → forma JS'да.
let _hotelRoomsCache = [];

async function openRoomModal(id) {
  let r = null;
  if (id) {
    try { const d = await apiFetch('/rooms/?page_size=500'); r = (d.items||d||[]).find(x=>x.id===id) || null; } catch {}
  }
  document.getElementById('roomModalTitle').textContent = r ? 'Xonani tahrirlash' : 'Yangi xona';
  document.getElementById('rmId').value = r ? r.id : '';
  document.getElementById('rmNumber').value = r ? r.number : '';
  document.getElementById('rmName').value = r ? (r.name||'') : '';
  document.getElementById('rmFloor').value = r ? r.floor : 1;
  document.getElementById('rmType').value = r ? r.room_type : 'standard';
  document.getElementById('rmCapacity').value = r ? r.capacity : 2;
  document.getElementById('rmPrice').value = r ? r.price_per_night : '';
  document.getElementById('rmStatusGroup').style.display = r ? '' : 'none';   // status faqat tahrirда
  if (r) document.getElementById('rmStatus').value = r.status || 'available';
  openModal('roomModal');
}

async function saveRoom() {
  const id = document.getElementById('rmId').value;
  const number = document.getElementById('rmNumber').value.trim();
  const price = parseFloat(document.getElementById('rmPrice').value);
  if (!number) { toast('Xona raqamini kiriting', 'error'); return; }
  if (isNaN(price) || price < 0) { toast("Narx to'g'ri kiritilsin (0 dan kam emas)", 'error'); return; }
  const base = {
    number, name: document.getElementById('rmName').value.trim() || null,
    floor: parseInt(document.getElementById('rmFloor').value,10) || 1,
    room_type: document.getElementById('rmType').value,
    capacity: parseInt(document.getElementById('rmCapacity').value,10) || 1,
    price_per_night: price,
  };
  try {
    if (id) await apiFetchPost(`/rooms/${id}`, { ...base, status: document.getElementById('rmStatus').value }, 'PATCH');
    else    await apiFetchPost('/rooms/', base);
    toast('Saqlandi', 'success'); closeModal('roomModal');
    if (typeof loadHotelRooms === 'function') loadHotelRooms();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteRoom(id) {
  if (!confirm("Xona o'chirilsinmi?")) return;
  try { await apiFetchPost(`/rooms/${id}`, {}, 'DELETE'); toast("O'chirildi", 'success'); loadHotelRooms(); }
  catch (e) { toast(e.message, 'error'); }
}

async function openBookingModal(id) {
  // Xonalar ro'yxati (picker) — narx bilan
  try { const d = await apiFetch('/rooms/?page_size=500'); _hotelRoomsCache = d.items || d || []; } catch { _hotelRoomsCache = []; }
  const sel = document.getElementById('bkRoom');
  sel.innerHTML = _hotelRoomsCache.map(r =>
    `<option value="${r.id}" data-price="${r.price_per_night}">${r.number}${r.name?' — '+r.name:''} (${fmtMoney(r.price_per_night)}/tun${r.status!=='available'?' · '+(ROOM_STATUS[r.status]?.lbl||r.status):''})</option>`).join('');
  let b = null;
  if (id) { try { const d = await apiFetch('/rooms/bookings/?page_size=500'); b = (d.items||d||[]).find(x=>x.id===id) || null; } catch {} }
  document.getElementById('bookingModalTitle').textContent = b ? 'Bronni tahrirlash' : 'Yangi bron';
  document.getElementById('bkId').value = b ? b.id : '';
  document.getElementById('bkGuest').value = b ? b.guest_name : '';
  document.getElementById('bkPhone').value = b ? (b.guest_phone||'') : '';
  if (b) document.getElementById('bkRoom').value = b.room_id;
  document.getElementById('bkCount').value = b ? b.guest_count : 1;
  document.getElementById('bkCheckin').value = b ? b.check_in : '';
  document.getElementById('bkCheckout').value = b ? b.check_out : '';
  document.getElementById('bkStatusGroup').style.display = b ? '' : 'none';
  if (b) document.getElementById('bkStatus').value = b.status || 'pending';
  _bkRecalc();
  openModal('bookingModal');
}

function _bkNightsTotal() {
  const ci = document.getElementById('bkCheckin').value, co = document.getElementById('bkCheckout').value;
  let nights = 0;
  if (ci && co) { const d = (new Date(co) - new Date(ci)) / 86400000; nights = d > 0 ? Math.round(d) : 0; }
  const opt = document.getElementById('bkRoom').selectedOptions[0];
  const price = opt ? parseFloat(opt.dataset.price) || 0 : 0;
  return { nights, total: nights * price };
}
function _bkRecalc() {
  const { nights, total } = _bkNightsTotal();
  document.getElementById('bkNights').textContent = nights;
  document.getElementById('bkTotal').textContent = fmtMoney(total);
}

async function saveBooking() {
  const id = document.getElementById('bkId').value;
  const guest = document.getElementById('bkGuest').value.trim();
  const roomId = parseInt(document.getElementById('bkRoom').value, 10);
  const ci = document.getElementById('bkCheckin').value, co = document.getElementById('bkCheckout').value;
  if (!guest) { toast('Mehmon ismini kiriting', 'error'); return; }
  if (!roomId) { toast('Xona tanlang', 'error'); return; }
  if (!ci || !co) { toast('Kelish va ketish sanasini kiriting', 'error'); return; }
  const { nights, total } = _bkNightsTotal();
  if (nights < 1) { toast('Ketish sanasi kelishdan keyin bo\'lsin (kamida 1 tun)', 'error'); return; }
  const base = {
    room_id: roomId, guest_name: guest, guest_phone: document.getElementById('bkPhone').value.trim() || null,
    guest_count: parseInt(document.getElementById('bkCount').value,10) || 1,
    check_in: ci, check_out: co, nights, total_amount: total,
  };
  try {
    if (id) await apiFetchPost(`/rooms/bookings/${id}`, { status: document.getElementById('bkStatus').value }, 'PATCH');
    else    await apiFetchPost('/rooms/bookings/', base);
    toast('Saqlandi', 'success'); closeModal('bookingModal');
    if (typeof loadHotelBookings === 'function') loadHotelBookings();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteBooking(id) {
  if (!confirm("Bron o'chirilsinmi?")) return;
  try { await apiFetchPost(`/rooms/bookings/${id}`, {}, 'DELETE'); toast("O'chirildi", 'success'); loadHotelBookings(); }
  catch (e) { toast(e.message, 'error'); }
}
