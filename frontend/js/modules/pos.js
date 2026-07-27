/**
 * POS Terminal — asosiy modul
 * IndexedDB offline-first + WebSocket real-time + to'liq cart logikasi
 */
import { API }              from '../core/api.js';
import { AuthService, clearTenantSession } from '../core/auth.js';
import { localDB, STORES }  from '../core/db.js';
import { syncEngine }       from '../core/sync.js';
import { WS_BASE, API_BASE } from '../core/config.js';
import { printReceiptHTML, buildReceipt58, loyaltyRows } from '../core/receipt-print.js';

const api = new API();

// Rasm URL: root-relative "/uploads/..." Electron file:// da ishlamaydi — server
// origin bilan to'liq URL qilamiz (admin core.js:1183 _uplBase bilan aynan bir xil).
const _uplBase = API_BASE.replace('/api/v1', '');
function imgSrc(u) {
  if (!u) return '';
  return /^(https?:|data:|blob:)/i.test(u) ? u : (_uplBase + u);
}

const WS_URL = `${WS_BASE}/ws/pos`;

// ─── Biznes tur ───────────────────────────────────────────────────────────────
// STORE rejimi: magazin, supermarket, dorixona → stol yo'q, xizmat haqi yo'q, barkod ko'rsatiladi
const _STORE_TYPES   = ['store', 'supermarket', 'pharmacy'];
// SERVICE rejimi: go'zallik, fitnes, auto servis, maktab, kimyoviy tozalash → stol yo'q, kurs yo'q
const _SERVICE_TYPES = ['beauty', 'fitness', 'auto_service', 'school', 'dry_cleaning'];

const MODE = (() => {
  try {
    const raw     = localStorage.getItem('restopos_features');
    const cached  = raw ? JSON.parse(raw)?.data : null;
    let bt = cached?.business_type;
    if (!bt) {
      try {
        const tok = localStorage.getItem('access_token');
        if (tok) bt = JSON.parse(atob(tok.split('.')[1]))?.business_type;
      } catch {}
    }
    bt = bt || 'restaurant';
    const isStore       = _STORE_TYPES.includes(bt);
    const isPharmacy    = bt === 'pharmacy';
    const isService     = _SERVICE_TYPES.includes(bt);
    const isBeauty      = bt === 'beauty';
    const isFitness     = bt === 'fitness';
    const isAutoService = bt === 'auto_service';
    const isSchool      = bt === 'school';
    const isDryCleaning = bt === 'dry_cleaning';
    const isHotel       = bt === 'hotel';
    return {
      isStore, isPharmacy,
      isService, isBeauty, isFitness, isAutoService, isSchool, isDryCleaning,
      isHotel,
      taxRate    : isStore ? 0      : 0.12,
      serviceRate: (isStore || isService || isHotel) ? 0 : 0.10,
      hasTable   : !isStore && !isService,
      hasCourses : !isStore && !isService && !isHotel,
      hasTips    : !isStore,
      hasBarcode : isStore,
      businessType: bt,
      // Sotuv atamasi: magazin/dorixona → "Savatcha"/"Chek", restoran/kafe → "Buyurtma"
      saleTerm    : (isStore || isService) ? 'Savatcha' : 'Buyurtma',
      saleSavedMsg: (isStore || isService) ? 'Sotuv yakunlandi' : 'Buyurtma saqlandi',
    };
  } catch { return { isStore:false, isPharmacy:false, isService:false, isBeauty:false, isFitness:false, isAutoService:false, isSchool:false, isDryCleaning:false, isHotel:false, taxRate:0.12, serviceRate:0.10, hasTable:true, hasCourses:true, hasTips:true, hasBarcode:false, businessType:'restaurant', saleTerm:'Buyurtma', saleSavedMsg:'Buyurtma saqlandi' }; }
})();

// BOSQICH 21: faol bo'lim filtri (null = barchasi)
let _activeDeptId = null;
// BUG 3: POS mahsulot ko'rinishi — 'list' (bir qator, ko'p mahsulotda o'qish oson)
// yoki 'grid' (karta). localStorage EMAS (Electron'da ishonchsiz) — sessiya
// davomida oddiy o'zgaruvchi. Default = 'list' (250+ mahsulotda grid siqiladi).
let _posView = 'list';

// ─── Toast ───────────────────────────────────────────────────────────────────
function toast(msg, type = 'info', dur = 3500) {
  const icons = { success: '✓', error: '✕', warning: '!', info: 'i' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<div class="toast-icon">${icons[type] || 'i'}</div><div>${msg}</div>`;
  const c = document.getElementById('toasts');
  c.appendChild(el);
  setTimeout(() => el.remove(), dur);
}

// ─── Formatters ──────────────────────────────────────────────────────────────
// Pul formati BUTUN tizimda bir xil: vergul bilan minglik ajratish (770,000).
// Ko'rsatish (fmt/fmtNum) va input (attachMoneyInput) BIR XIL ajratgichni ishlatadi —
// chalkashlik bo'lmasin (tepada 770,000 / input'da 770000 muammosi).
function fmtNum(n) { return Math.round(Number(n) || 0).toLocaleString('en-US'); }
function fmt(n)    { return fmtNum(n) + ' UZS'; }

// Formatlangan input matnidan sof raqamni oladi ("770,000" → 770000)
function parseMoney(str) { return parseFloat(String(str == null ? '' : str).replace(/[^\d.]/g, '')) || 0; }

// Input'ga jonli minglik formatlash ulaydi (yozayotganda 770000 → 770,000)
function attachMoneyInput(el) {
  if (!el || el._moneyBound) return;
  el._moneyBound = true;
  el.addEventListener('input', () => {
    const digits = el.value.replace(/[^\d]/g, '');
    el.value = digits ? Number(digits).toLocaleString('en-US') : '';
  });
}

// ─── BOSQICH 22: Dorixona — Analog panel ─────────────────────────────────────
async function showAnalogsPanel(product) {
  try {
    const _r = await api.get(`/products/${product.id}/analogs`);
    const analogs = (_r && _r.success && Array.isArray(_r.data)) ? _r.data : [];
    if (!analogs.length) {
      toast(`"${product.name}" tugagan, analog topilmadi`, 'warning');
      return;
    }
    let existing = document.getElementById('analogsOverlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'analogsOverlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:300;display:flex;align-items:center;justify-content:center;padding:1rem';
    overlay.innerHTML = `
      <div style="background:#12121e;border:1px solid rgba(255,255,255,.08);border-radius:1rem;padding:1.5rem;width:100%;max-width:480px;max-height:80vh;overflow-y:auto">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem">
          <div>
            <div style="font-weight:700;font-size:1rem">"${product.name}" tugagan</div>
            <div style="font-size:.8rem;color:#9a9ab8;margin-top:.2rem">Faol modda: ${product.active_ingredient}</div>
          </div>
          <button onclick="document.getElementById('analogsOverlay').remove()" style="background:none;border:none;color:#9a9ab8;font-size:1.5rem;cursor:pointer">&times;</button>
        </div>
        <div style="font-size:.8125rem;color:#5c5c7a;margin-bottom:.875rem">O'rnini bosuvchi dorilar:</div>
        ${analogs.map(a => `
          <div style="display:flex;align-items:center;gap:.75rem;padding:.75rem;border:1.5px solid rgba(255,255,255,.08);border-radius:.625rem;margin-bottom:.5rem;cursor:pointer;transition:.2s"
               onmouseenter="this.style.borderColor='#d4af37'" onmouseleave="this.style.borderColor='rgba(255,255,255,.08)'"
               onclick="document.getElementById('analogsOverlay').remove(); window._posAddAnalog(${a.id})">
            <div style="flex:1">
              <div style="font-weight:600">${a.name}</div>
              ${a.dosage ? `<div style="font-size:.75rem;color:#9a9ab8">${a.dosage} • ${a.drug_form||''}</div>` : ''}
            </div>
            <div style="font-weight:700;color:#d4af37">${fmtNum(a.price)} UZS</div>
            <div style="background:#d4af37;color:#0a0a0f;border:none;border-radius:.5rem;padding:.4rem .75rem;font-size:.8rem;font-weight:600">Qo'shish</div>
          </div>`).join('')}
      </div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  } catch(e) {
    toast('Analog izlashda xatolik', 'error');
  }
}
window._posAddAnalog = (id) => addToCart(id);

// Savdo birligi ko'rsatkichi: "kg", "g", "l" → "/ kg", "/ g", "/ l"; "pcs" → ""
function fmtUnit(u) {
  if (!u || u === 'pcs' || u === 'dona') return '';
  return `/ ${u}`;
}

// O'lchov birligi kg/g/l ekanligini tekshiradi (tarozida tortiluvchi mahsulot)
function isWeightUnit(u) { return ['kg', 'g', 'l', 'litr'].includes(u); }

// Xizmat davomiyligini formatlash: 45 → "45 min", 90 → "1s 30m"
function fmtDuration(min) {
  if (!min || min <= 0) return '';
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  return m ? `${h}s ${m}m` : `${h} soat`;
}

// Abonement davomini formatlash: 30 → "1 oy", 365 → "1 yil"
function fmtPeriod(days) {
  if (!days || days <= 0) return '';
  if (days < 30)  return `${days} kun`;
  if (days < 365) return `${Math.round(days / 30)} oy`;
  const y = Math.round(days / 365);
  return `${y} yil`;
}

// Yaroqlilik muddati holati: 'expired' | 'critical' (≤3 kun) | 'warning' (≤7 kun) | 'ok' | null
function expiryStatus(dateStr) {
  if (!dateStr) return null;
  const diff = Math.floor((new Date(dateStr) - new Date()) / 86400000);
  if (diff < 0)  return 'expired';
  if (diff <= 3) return 'critical';
  if (diff <= 7) return 'warning';
  return 'ok';
}

// ─── Modal helpers ───────────────────────────────────────────────────────────
function openModal(id)  { document.getElementById(id)?.classList.add('open'); }
function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }

// ─── State ───────────────────────────────────────────────────────────────────
const state = {
  products   : [],
  categories : [],
  tables     : [],
  cart       : [],
  discount   : { type: 'pct', value: 0 },
  discountSource: null,   // BOSQICH S2: 'customer' | 'manual' | null (kim chegirmani o'rnatdi)
  customer   : null,
  table      : null,
  orderType  : 'dine-in',
  pendingOrderId: null,
  rxInfo      : null,   // pharmacy: { patient_name, patient_phone, rx_number }
  staffMember : null,   // service: { id, name, specialty }
  carInfo     : null,   // auto_service: { plate, make, model, year }
  studentInfo : null,   // school: { name, phone, group }
  cleaningInfo: null,   // dry_cleaning: { items, color, notes, pickup_date }
};

// ─── Totals ───────────────────────────────────────────────────────────────────
function computeTotals() {
  const sub = state.cart.reduce((s, i) => s + i.price * i.qty, 0);
  let disc = 0;
  if (state.discount.value > 0) {
    disc = state.discount.type === 'pct'
      ? sub * (state.discount.value / 100)
      : Math.min(state.discount.value, sub);
  }
  const afterDisc = sub - disc;
  const tax       = afterDisc * MODE.taxRate;
  const service   = afterDisc * MODE.serviceRate;
  const total     = afterDisc + tax + service;
  return { sub, disc, tax, service, total };
}

// ─── Cart render ─────────────────────────────────────────────────────────────
// Empty-state node cache: `#cartEmpty` cartItems ICHIDA, list.innerHTML uni
// DOMdan o'chiradi. Referensiyani saqlab, kerak bo'lganda qayta qo'yamiz —
// aks holda 2-mahsulotda getElementById(null).style xatosi chiqadi.
const _cartEmptyNode = document.getElementById('cartEmpty');

function renderCart() {
  const list  = document.getElementById('cartItems');
  const empty = _cartEmptyNode;

  if (!state.cart.length) {
    list.innerHTML = '';
    if (empty) { list.appendChild(empty); empty.style.display = ''; }
    document.getElementById('checkoutBtn').disabled = true;
    document.getElementById('holdBtn').disabled     = true;
    renderTotals();
    return;
  }
  if (empty) empty.style.display = 'none';
  list.innerHTML = state.cart.map((item, idx) => `
    <div class="cart-item" data-idx="${idx}">
      <div class="ci-info">
        <div class="ci-name">${item.name}</div>
        ${item._packLabel ? `<div style="font-size:.7rem;color:var(--gold);margin-top:.1rem">📦 ${item._packLabel}</div>` : ''}
        ${item.modLabel ? `<div style="font-size:.7rem;color:var(--text3);margin-top:.1rem">${item.modLabel}</div>` : ''}
        ${MODE.isPharmacy && item._dosage   ? `<div style="font-size:.7rem;color:var(--info);margin-top:.1rem">${item._dosage}</div>` : ''}
        ${MODE.isPharmacy && item._batch    ? `<div style="font-size:.7rem;color:var(--text3);margin-top:.05rem">Partiya: ${item._batch}</div>` : ''}
        ${MODE.isService  && item._master   ? `<div style="font-size:.7rem;color:var(--text2);margin-top:.05rem">✂️ ${item._master.name}</div>` : ''}
        ${MODE.isService  && item._duration ? `<div style="font-size:.7rem;color:var(--text3);margin-top:.05rem">⏱ ${fmtDuration(item._duration)}</div>` : ''}
        ${MODE.isFitness  && item._end_date ? `<div style="font-size:.7rem;color:var(--success);margin-top:.05rem">📅 ${new Date(item._end_date).toLocaleDateString('uz-UZ',{day:'2-digit',month:'2-digit',year:'numeric'})} gacha</div>` : ''}
        ${MODE.isFitness     && item._sessions ? `<div style="font-size:.7rem;color:var(--info);margin-top:.05rem">🏋️ ${item._sessions} seans</div>` : ''}
        ${MODE.isAutoService && item._is_part  ? `<div style="font-size:.7rem;color:var(--text3);margin-top:.05rem">⚙️ Ehtiyot qism</div>` : ''}
        ${MODE.isSchool && item._end_date      ? `<div style="font-size:.7rem;color:var(--success);margin-top:.05rem">📅 ${new Date(item._end_date).toLocaleDateString('uz-UZ',{day:'2-digit',month:'2-digit',year:'numeric'})} gacha</div>` : ''}
        ${MODE.isSchool && item._sessions      ? `<div style="font-size:.7rem;color:var(--info);margin-top:.05rem">📖 ${item._sessions} dars</div>` : ''}
        ${MODE.isDryCleaning && item._cleaning?.items ? `<div style="font-size:.7rem;color:var(--text2);margin-top:.05rem">👔 ${item._cleaning.items}</div>` : ''}
        ${MODE.isDryCleaning && item._cleaning?.pickup_date ? `<div style="font-size:.7rem;color:var(--warning);margin-top:.05rem">📦 ${new Date(item._cleaning.pickup_date).toLocaleDateString('uz-UZ',{day:'2-digit',month:'2-digit'})}</div>` : ''}
        <div style="display:flex;align-items:center;gap:.5rem;margin-top:.2rem">
          <div class="ci-price">${item._weight != null ? `${item._weight} ${item._unit || ''} — ${fmtNum(item.price)}` : `${fmtNum(item.price)} × ${item.qty}${item._unit ? ' ' + item._unit : ''}`}</div>
          ${MODE.hasCourses ? `<select class="course-sel" data-cidx="${idx}" title="Kurs" style="background:var(--bg3);border:1px solid rgba(255,255,255,.08);border-radius:.25rem;color:var(--text2);font-size:.7rem;padding:.1rem .25rem;outline:none;cursor:pointer">
            <option value="1" ${(item.course_number||1)===1?'selected':''}>1-kurs</option>
            <option value="2" ${(item.course_number||1)===2?'selected':''}>2-kurs</option>
            <option value="3" ${(item.course_number||1)===3?'selected':''}>3-kurs</option>
          </select>` : ''}
        </div>
      </div>
      <div class="ci-qty">
        <button class="qty-btn" data-action="dec" data-idx="${idx}">−</button>
        <span class="qty-val">${item.qty}</span>
        <button class="qty-btn" data-action="inc" data-idx="${idx}">+</button>
      </div>
      <div class="ci-total">${fmt(item.price * item.qty)}</div>
      <button class="ci-del" data-action="del" data-idx="${idx}" title="O'chirish">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      </button>
    </div>
  `).join('');

  document.getElementById('checkoutBtn').disabled = false;
  document.getElementById('holdBtn').disabled     = false;
  renderTotals();
  persistCart();
}

function renderTotals() {
  const t = computeTotals();
  document.getElementById('totSubtotal').textContent = fmt(t.sub);
  document.getElementById('totDiscount').textContent = '-' + fmt(t.disc);
  document.getElementById('totTax').textContent      = fmt(t.tax);
  document.getElementById('totService').textContent  = fmt(t.service);
  document.getElementById('totTotal').textContent    = fmt(t.total);
  document.getElementById('discRow').style.display   = t.disc > 0 ? '' : 'none';
  broadcastToDisplay();
}

async function persistCart() {
  try {
    await localDB.clear(STORES.CART);
    for (const item of state.cart) await localDB.put(STORES.CART, item);
  } catch {}
}

// ─── Products ─────────────────────────────────────────────────────────────────
function renderCategories(cats) {
  const bar = document.getElementById('catsBar');
  bar.innerHTML = `<button class="cat-btn active" data-id="">Barchasi</button>` +
    cats.map(c => `<button class="cat-btn" data-id="${c.id}">${c.name}</button>`).join('');
  bar.querySelectorAll('.cat-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      bar.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderProducts(btn.dataset.id ? +btn.dataset.id : null);
    });
  });
}

function renderProducts(catId = null) {
  const grid   = document.getElementById('productsGrid');
  // BUG 3: joriy ko'rinish (grid/list) — innerHTML almashsa ham konteyner klassi saqlanadi
  grid.classList.toggle('list-view', _posView === 'list');
  const search = document.getElementById('searchInput').value.toLowerCase().trim();
  let list     = state.products;
  if (_activeDeptId) list = list.filter(p => p.department_id === _activeDeptId);
  if (catId)  list = list.filter(p => p.category_id === catId);
  if (search) list = list.filter(p =>
    p.name.toLowerCase().includes(search) ||
    (p.barcode && p.barcode.includes(search))
  );
  if (!list.length) {
    grid.innerHTML = '<div class="prod-empty"><div class="prod-empty-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none"><path d="M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2z" stroke="currentColor" stroke-width="1.5"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16" stroke="currentColor" stroke-width="1.5"/></svg></div><p>Mahsulot topilmadi</p><span>Kategoriya yoki qidiruvni o\'zgartiring</span></div>';
    return;
  }
  grid.innerHTML = list.map(p => {
    const expSt  = expiryStatus(p.expiry_date);
    const expBadge = expSt === 'expired'  ? `<div class="expiry-badge expired">Muddati o'tgan!</div>`
                   : expSt === 'critical' ? `<div class="expiry-badge critical">${Math.max(0,Math.floor((new Date(p.expiry_date)-new Date())/86400000))} kun</div>`
                   : expSt === 'warning'  ? `<div class="expiry-badge warning">${Math.ceil((new Date(p.expiry_date)-new Date())/86400000)} kun</div>`
                   : '';
    const rxBadge  = MODE.isPharmacy && p.requires_prescription ? `<div class="rx-badge">Rx</div>` : '';
    const unitLbl  = fmtUnit(p.sale_unit);
    const icon     = p.emoji || (MODE.isPharmacy ? '💊' : MODE.isBeauty ? '✂️' : MODE.isFitness ? '🏋️' : MODE.isAutoService ? '🔧' : MODE.isSchool ? '📚' : MODE.isDryCleaning ? '👔' : MODE.isHotel ? '🛎️' : (p.sale_unit === 'kg' || p.sale_unit === 'g' ? '⚖️' : p.sale_unit === 'l' ? '🥤' : '🛒'));
    const dosageLbl     = MODE.isPharmacy && p.dosage        ? `<div class="dosage-lbl">${p.dosage}</div>` : '';
    const periodBadge   = (MODE.isFitness || MODE.isSchool) && p.period_days    ? `<div class="period-badge">${fmtPeriod(p.period_days)}</div>` : '';
    const sessionsBadge = MODE.isFitness    && p.sessions_count ? `<div class="sessions-badge">🏋️ ${p.sessions_count} seans</div>` : '';
    const lessonsBadge  = MODE.isSchool     && p.sessions_count ? `<div class="sessions-badge">📖 ${p.sessions_count} dars</div>` : '';
    const partBadge     = MODE.isAutoService && (p.is_spare_part || p.product_type === 'part') ? `<div class="part-badge">⚙️ Ehtiyot qism</div>` : '';
    const expiryDate  = MODE.isPharmacy && p.expiry_date && expSt !== 'expired'
      ? `<div class="expiry-date-lbl ${expSt||'ok'}">${new Date(p.expiry_date).toLocaleDateString('uz-UZ',{year:'2-digit',month:'2-digit',day:'2-digit'})}</div>`
      : '';
    const durationBadge = MODE.isService && p.duration_min
      ? `<div class="duration-badge">⏱ ${fmtDuration(p.duration_min)}</div>`
      : '';
    return `
    <div class="product-card${p.is_available === false ? ' unavail' : ''}${expSt==='expired' ? ' unavail' : ''}" data-id="${p.id}" data-unit="${p.sale_unit||'pcs'}">
      ${expBadge}${rxBadge}
      ${p.image_url
        ? `<img class="prod-img" src="${imgSrc(p.image_url)}" alt="${p.name}" loading="lazy" onerror="this.style.display='none'">`
        : `<div class="prod-img" style="display:flex;align-items:center;justify-content:center;font-size:2.5rem;color:var(--text3)">${icon}</div>`
      }
      <div class="prod-body">
        <div class="prod-name">${p.name}</div>
        ${dosageLbl}${expiryDate}${durationBadge}${periodBadge}${sessionsBadge}${lessonsBadge}${partBadge}
        <div class="prod-price">${fmtNum(p.price)} <span class="prod-unit">UZS${unitLbl ? ' '+unitLbl : ''}</span></div>
      </div>
    </div>`;
  }).join('');
  grid.querySelectorAll('.product-card').forEach(card => {
    card.addEventListener('click', () => addToCart(+card.dataset.id));
  });
}

// BOSQICH B4 (pachka/dona): mahsulot pachkali sotiladimi (pack_size≥2 AND pack_price>0)
function isPackProduct(p) {
  return !!(p && p.pack_size >= 2 && p.pack_price > 0);
}

// Pachkali mahsulot uchun modifikator oqimida birlik (pachka/dona) saqlash
let _modUnitMode = null;
// Pachka/Dona tanlov modali uchun joriy mahsulot
let _packChoiceProduct = null;

function showPackChoiceModal(product) {
  _packChoiceProduct = product;
  // #20 atir (hajm): sale_unit "ml" → "Butun (150 ml)" / "ml"; oddiy → "Pachka (N dona)" / "Dona"
  const isVol = product.sale_unit === 'ml';
  const unit  = product.sale_unit || 'dona';
  document.getElementById('packChoiceName').textContent = product.name;
  document.getElementById('packChoicePackLbl').textContent   = isVol ? '🧴 Butun' : '📦 Pachka';
  document.getElementById('packChoicePackPrice').textContent = fmtNum(product.pack_price) + ' UZS';
  document.getElementById('packChoicePackHint').textContent  = product.pack_size + (isVol ? ' ' + unit : ' dona');
  document.getElementById('packChoiceDonaLbl').textContent   = isVol ? unit : 'Dona';
  document.getElementById('packChoiceDonaPrice').textContent = fmtNum(product.price) + ' UZS' + (isVol ? ' / ' + unit : '');
  openModal('packChoiceModal');
}

async function addToCart(productId, presetWeight = null, unitMode = null) {
  const p = state.products.find(x => x.id === productId);
  if (!p) return;
  const card = document.querySelector(`.product-card[data-id="${productId}"]`);
  if (card) { card.style.transform = 'scale(0.95)'; setTimeout(() => card.style.transform = '', 120); }

  // BOSQICH B4: Pachkali mahsulot — AVVAL birlik tanlash (pachka/dona), keyin qolgan
  // oqim (rx-tasdiq, modifikator) bir marta. Pachkasiz mahsulot — tanlovsiz, avvalgidek.
  // Weight (tarozi) mahsulot pachkali bo'lmaydi (B2 bloklaydi) — himoya uchun tekshiramiz.
  if (unitMode == null && presetWeight == null && isPackProduct(p) && !isWeightUnit(p.sale_unit)) {
    showPackChoiceModal(p);
    return;
  }

  // BOSQICH 22: Dorixona — retseptli dori ogohlantirish
  if (MODE.isPharmacy && p.requires_prescription) {
    const ok = confirm(`⚠️ "${p.name}" — retsept bilan beriladigan dori!\n\nRetsept arxiviga kiritilganmi? Davom etishni tasdiqlaysizmi?`);
    if (!ok) return;
  }

  // BOSQICH 22: Dorixona — analog ko'rsatish (faqat is_available=false bo'lsa)
  if (MODE.isPharmacy && !p.is_available && p.active_ingredient) {
    showAnalogsPanel(p);
    return;
  }

  // Fitnes / Maktab: muddatli mahsulot bo'lsa membership modal ochish
  if ((MODE.isFitness || MODE.isSchool) && p.period_days > 0) {
    showMembershipModal(p);
    return;
  }
  // Kimyoviy tozalash: kiyim modali
  if (MODE.isDryCleaning && !state.cleaningInfo) {
    _pendingCleanProduct = p;
    openModal('cleaningModal');
    setTimeout(() => document.getElementById('cleaningItems')?.focus(), 100);
    return;
  }

  // Tarozi mahsulotlar uchun og'irlik modali
  if (isWeightUnit(p.sale_unit)) {
    if (presetWeight != null) {
      doAddToCart(p, [], presetWeight);
    } else {
      showWeightModal(p);
    }
    return;
  }

  let groups = [];
  try {
    const res = await api.get(`/modifiers/groups?product_id=${productId}`);
    groups = Array.isArray(res) ? res : (res?.data ?? res?.items ?? []);
  } catch {}

  if (groups.length) {
    _modUnitMode = unitMode;
    showModifierModal(p, groups);
  } else {
    doAddToCart(p, [], null, unitMode);
  }
}

// ─── Weight / tarozi modal ────────────────────────────────────────────────────
let _weightProduct = null;

function showWeightModal(product) {
  _weightProduct = product;
  document.getElementById('weightProdName').textContent = product.name;
  document.getElementById('weightPriceHint').textContent = `${fmtNum(product.price)} UZS / ${product.sale_unit}`;
  document.getElementById('weightUnitLbl').textContent   = product.sale_unit;
  document.getElementById('weightInput').value           = '';
  document.getElementById('weightTotalAmt').textContent  = '0 UZS';

  // Preset tugmalari: ml (atir #20) / gram / kg uchun boshqacha
  const presets = product.sale_unit === 'ml'
    ? [['10','10 ml'],['20','20 ml'],['30','30 ml'],['50','50 ml'],['100','100 ml'],['150','150 ml']]
    : product.sale_unit === 'g'
    ? [['100','100g'],['200','200g'],['300','300g'],['500','500g'],['750','750g'],['1000','1 kg']]
    : [['0.1','100g'],['0.25','250g'],['0.5','500g'],['1','1 kg'],['1.5','1.5 kg'],['2','2 kg']];
  const container = document.getElementById('weightPresets');
  container.innerHTML = presets.map(([v,lbl]) =>
    `<button class="w-preset" data-w="${v}">${lbl}</button>`
  ).join('');
  container.querySelectorAll('.w-preset').forEach(btn => {
    btn.addEventListener('click', () => {
      document.getElementById('weightInput').value = btn.dataset.w;
      updateWeightPreview();
    });
  });

  openModal('weightModal');
  setTimeout(() => document.getElementById('weightInput').focus(), 100);
}

function updateWeightPreview() {
  const w = parseFloat(document.getElementById('weightInput').value) || 0;
  const total = (_weightProduct?.price || 0) * w;
  document.getElementById('weightTotalAmt').textContent = fmt(total);
}

document.getElementById('weightInput')?.addEventListener('input', updateWeightPreview);

document.getElementById('confirmWeightBtn')?.addEventListener('click', () => {
  const w = parseFloat(document.getElementById('weightInput').value);
  if (!w || w <= 0) { toast('Og\'irlikni kiriting', 'warning'); return; }
  closeModal('weightModal');
  doAddToCart(_weightProduct, [], w);
  toast(`${_weightProduct.name} — ${w} ${_weightProduct.sale_unit} qo'shildi`, 'success');
});

// ─── Membership / To'lov davri modal (Fitnes + Maktab) ───────────────────────
let _fitnessProduct  = null;
let _membershipDates = null;

function showMembershipModal(product) {
  _fitnessProduct = product;
  const nameEl  = document.getElementById('membershipProdName');
  const perEl   = document.getElementById('membershipPeriodLbl');
  const titleEl = document.getElementById('membershipModalTitle');
  const startLbl = document.getElementById('membershipStartLbl');
  const endLbl   = document.getElementById('membershipEndLbl');
  if (nameEl) nameEl.textContent = product.name;
  if (perEl)  perEl.textContent  = fmtPeriod(product.period_days);
  // School uchun modal matnlarini o'zgartirish
  if (MODE.isSchool) {
    if (titleEl)   titleEl.textContent  = "To'lov davri";
    if (startLbl)  startLbl.textContent = "Boshlanish sanasi";
    if (endLbl)    endLbl.textContent   = "Tugash sanasi";
  } else {
    if (titleEl)   titleEl.textContent  = "Abonement";
    if (startLbl)  startLbl.textContent = "Boshlanish sanasi";
    if (endLbl)    endLbl.textContent   = "Tugash sanasi";
  }
  const today = new Date().toISOString().split('T')[0];
  const startInp = document.getElementById('membershipStartDate');
  if (startInp) startInp.value = today;
  updateMembershipEnd();
  openModal('membershipModal');
  setTimeout(() => startInp?.focus(), 100);
}

function updateMembershipEnd() {
  const startVal = document.getElementById('membershipStartDate')?.value;
  const days     = _fitnessProduct?.period_days;
  if (!startVal || !days) return;
  const end = new Date(startVal);
  end.setDate(end.getDate() + days);
  const endStr = end.toISOString().split('T')[0];
  const endFmt = end.toLocaleDateString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const el = document.getElementById('membershipEndDateLbl');
  const hid = document.getElementById('membershipEndDateVal');
  if (el)  el.textContent = `${endFmt} gacha`;
  if (hid) hid.value      = endStr;
}

document.getElementById('membershipStartDate')?.addEventListener('input', updateMembershipEnd);

document.getElementById('confirmMembershipBtn')?.addEventListener('click', () => {
  const start = document.getElementById('membershipStartDate')?.value;
  const end   = document.getElementById('membershipEndDateVal')?.value;
  if (!start) { toast("Boshlanish sanasini kiriting", 'warning'); return; }
  _membershipDates = { start_date: start, end_date: end };
  closeModal('membershipModal');
  doAddToCart(_fitnessProduct, []);
  toast(`${_fitnessProduct.name} — ${fmtPeriod(_fitnessProduct.period_days)} qo'shildi`, 'success');
});

// ─── Modifier modal ───────────────────────────────────────────────────────────
let _modProduct = null;
let _modGroups  = [];

function showModifierModal(product, groups) {
  _modProduct = product;
  _modGroups  = groups;
  document.getElementById('modProdName').textContent = product.name;

  const body = document.getElementById('modBody');
  body.innerHTML = groups.map(g => `
    <div class="mod-group" data-gid="${g.id}">
      <div style="font-size:.875rem;font-weight:700;margin-bottom:.5rem;color:var(--text2)">
        ${g.name}${g.is_required ? ' <span style="color:#ef4444;font-size:.75rem">*majburiy</span>' : ''}
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:.375rem">
        ${(g.modifiers || []).map(m => `
          <label style="display:flex;align-items:center;gap:.375rem;cursor:pointer;padding:.375rem .75rem;border-radius:var(--r);border:1px solid var(--border2);font-size:.8125rem;transition:.2s">
            <input type="${g.type === 'single' ? 'radio' : 'checkbox'}"
              name="mg_${g.id}" value="${m.id}"
              data-name="${m.name.replace(/"/g,'&quot;')}"
              data-delta="${m.price_delta || 0}"
              ${m.is_default ? 'checked' : ''}
              style="accent-color:var(--gold)">
            ${m.name}${m.price_delta ? ` <span style="color:var(--gold)">+${fmtNum(m.price_delta)}</span>` : ''}
          </label>
        `).join('')}
      </div>
    </div>
  `).join('');

  openModal('modifierModal');
}

function collectModifiers() {
  const selected = [];
  _modGroups.forEach(g => {
    const type = g.type === 'single' ? 'radio' : 'checkbox';
    document.querySelectorAll(`input[name="mg_${g.id}"]:checked`).forEach(inp => {
      selected.push({ modifier_id: +inp.value, name: inp.dataset.name, price_delta: +inp.dataset.delta });
    });
  });
  return selected;
}

function doAddToCart(product, modifiers, weight = null, unitMode = null) {
  const modKey   = modifiers.map(m => m.modifier_id).sort().join(',');
  const modDelta = modifiers.reduce((s, m) => s + (m.price_delta || 0), 0);
  // #20 atir: ml ham hajm (necha ml) — weight branch (narx = 1ml × ml). Flakon esa
  // weight=null bo'lgani uchun bu branch'ga kirmaydi → pack branch (pastda).
  const isWeight = isWeightUnit(product.sale_unit) || product.sale_unit === 'ml';
  const isPack   = unitMode === 'pachka' && isPackProduct(product);

  if (isWeight && weight != null) {
    // Og'irlik mahsulot: narx = baho_per_unit × og'irlik; har bir bor yangi qator
    const w     = parseFloat(weight) || 0;
    const unitP = product.price + modDelta;
    const total = unitP * w;
    state.cart.push({
      id: product.id, name: product.name,
      price: total,      // savatda umumiy summa (qty=1)
      qty: 1,
      _modKey: modKey + '_w' + w, // har og'irlik alohida
      modifiers,
      modLabel   : modifiers.map(m => m.name).join(', ') || null,
      _unit      : product.sale_unit,
      _weight    : w,
      _unitPrice : unitP,
      _dosage     : product.dosage         || null,
      _batch      : product.batch_number   || null,
      _duration   : product.duration_min   || null,
      _master     : state.staffMember      ? { ...state.staffMember } : null,
      _period_days: product.period_days    || null,
      _sessions   : product.sessions_count || null,
      _start_date : null,
      _end_date   : null,
      _is_part    : !!(product.is_spare_part || product.product_type === 'part'),
      _cleaning   : MODE.isDryCleaning && state.cleaningInfo ? { ...state.cleaningInfo } : null,
    });
  } else if (isPack) {
    // BOSQICH B4: Pachka — qat'iy pack_price (+modDelta). Ombor pack_size dona
    // (server B3 hisoblaydi). Wholesale QO'LLANMAYDI (pachka o'zi ulgurji). Pachka
    // va dona qatorlari alohida turadi (_modKey '_pk' suffiksi).
    const modLabelP = modifiers.map(m => m.name).join(', ');
    const priceP = (product.pack_price || 0) + modDelta;
    const pkKey  = modKey + '_pk';
    const sameP  = MODE.isService ? null : state.cart.find(x => x.id === product.id && x._modKey === pkKey);
    if (sameP) { sameP.qty++; }
    else {
      state.cart.push({
        id: product.id, name: product.name, price: priceP, qty: 1,
        _modKey: pkKey, modifiers, modLabel: modLabelP || null,
        _unitSold : 'pachka',
        _packLabel: product.sale_unit === 'ml'
          ? `Butun (${product.pack_size} ml)`      // #20 atir: butun flakon
          : `Pachka (${product.pack_size} dona)`,
        _batch    : product.batch_number || null,
        _master   : state.staffMember ? { ...state.staffMember } : null,
      });
    }
  } else {
    // BOSQICH 19: Ko'tara (optom) narxni hisoblash
    const basePrice = product.price + modDelta;
    let finalPrice = basePrice;
    const existingQty = state.cart.filter(x => x.id === product.id).reduce((s, x) => s + x.qty, 0);
    const newTotalQty = existingQty + 1;
    if (
      MODE.isStore && product.wholesale_price && product.wholesale_price > 0 &&
      product.wholesale_min_qty && newTotalQty >= product.wholesale_min_qty
    ) {
      finalPrice = product.wholesale_price + modDelta;
      // Savatdagi mavjud yozuvlarni ham optom narxga o'tkazish
      state.cart.filter(x => x.id === product.id).forEach(x => {
        x.price = product.wholesale_price + modDelta;
        x._isWholesale = true;
      });
      toast(`Ko'tara narx: ${fmtNum(product.wholesale_price)} so'm`, 'info');
    }
    const modLabel   = modifiers.map(m => m.name).join(', ');
    const sameKey = MODE.isService ? null : state.cart.find(x => x.id === product.id && x._modKey === modKey);
    if (sameKey) { sameKey.qty++; sameKey.price = finalPrice; }
    else {
      state.cart.push({
        id: product.id, name: product.name, price: finalPrice, qty: 1,
        _modKey: modKey, modifiers, modLabel: modLabel || null,
        _unitSold   : unitMode === 'dona' ? 'dona' : null,   // BOSQICH B4
        _dosage     : product.dosage         || null,
        _batch      : product.batch_number   || null,
        _duration   : product.duration_min   || null,
        _master     : state.staffMember      ? { ...state.staffMember } : null,
        _period_days: product.period_days    || null,
        _sessions   : product.sessions_count || null,
        _start_date : ((MODE.isFitness || MODE.isSchool) && product.period_days && _membershipDates) ? _membershipDates.start_date : null,
        _end_date   : ((MODE.isFitness || MODE.isSchool) && product.period_days && _membershipDates) ? _membershipDates.end_date   : null,
        _is_part      : !!(product.is_spare_part || product.product_type === 'part'),
        _cleaning     : MODE.isDryCleaning && state.cleaningInfo ? { ...state.cleaningInfo } : null,
        _isWholesale  : finalPrice !== basePrice,
        _wholesaleMin : product.wholesale_min_qty || null,
      });
    }
  }
  if (_membershipDates) _membershipDates = null;
  beep('add');
  renderCart();
}

// ─── Modifier modal events ────────────────────────────────────────────────────
document.getElementById('modCloseBtn').addEventListener('click',  () => closeModal('modifierModal'));
document.getElementById('modCancelBtn').addEventListener('click', () => closeModal('modifierModal'));
document.getElementById('modConfirmBtn').addEventListener('click', () => {
  const mods = collectModifiers();
  const required = _modGroups.filter(g => g.is_required);
  for (const g of required) {
    const checked = document.querySelectorAll(`input[name="mg_${g.id}"]:checked`).length;
    if (!checked) { toast(`"${g.name}" bo'limidan tanlash shart`, 'warning'); return; }
  }
  closeModal('modifierModal');
  doAddToCart(_modProduct, mods, null, _modUnitMode);
  _modUnitMode = null;
});

// ─── BOSQICH B4: Pachka/Dona tanlov modali tugmalari ──────────────────────────
document.getElementById('packChoicePackBtn')?.addEventListener('click', () => {
  const p = _packChoiceProduct; closeModal('packChoiceModal');
  if (p) addToCart(p.id, null, 'pachka');
});
document.getElementById('packChoiceDonaBtn')?.addEventListener('click', () => {
  const p = _packChoiceProduct; closeModal('packChoiceModal');
  if (!p) return;
  // #20 atir: "ml" tanlansa "necha ml?" (weight modal); oddiy pachka: 'dona' (avvalgidek)
  if (p.sale_unit === 'ml') showWeightModal(p);
  else addToCart(p.id, null, 'dona');
});

// ─── Course select (COURSES feature) ──────────────────────────────────────────
document.getElementById('cartItems').addEventListener('change', e => {
  const sel = e.target.closest('.course-sel');
  if (!sel) return;
  const idx = +sel.dataset.cidx;
  if (state.cart[idx]) state.cart[idx].course_number = +sel.value;
});

// ─── Cart item events ─────────────────────────────────────────────────────────
document.getElementById('cartItems').addEventListener('click', e => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const idx    = +btn.dataset.idx;
  const action = btn.dataset.action;
  if (action === 'inc') state.cart[idx].qty++;
  if (action === 'dec') { state.cart[idx].qty--; if (state.cart[idx].qty <= 0) state.cart.splice(idx, 1); }
  if (action === 'del') state.cart.splice(idx, 1);
  renderCart();
});

document.getElementById('clearCartBtn').addEventListener('click', () => {
  if (!state.cart.length) return;
  state.cart = [];
  state.discount = { type: 'pct', value: 0 };
  state.discountSource = null;   // BOSQICH S2
  state.customer = null;
  state.table    = null;
  updateCustBtn();
  updateTableBtn();
  renderCart();
});

// ─── Order type ───────────────────────────────────────────────────────────────
document.querySelectorAll('.otype-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.otype-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.orderType = btn.dataset.type;
  });
});

// ─── Customer ─────────────────────────────────────────────────────────────────
function updateCustBtn() {
  const btn = document.getElementById('custBtn');
  const lbl = document.getElementById('custBtnLabel');
  if (state.customer) {
    btn.classList.add('has-cust');
    lbl.textContent = `${state.customer.name}${state.customer.phone ? ' (' + state.customer.phone + ')' : ''}`;
  } else {
    btn.classList.remove('has-cust');
    lbl.textContent = 'Mijoz tanlang';
  }
}

document.getElementById('custBtn').addEventListener('click', () => {
  openModal('customerModal'); _posToggleNewCust(false); loadCustomers();
  const db = document.getElementById('custDeselectBtn');   // BOSQICH S2: mijoz tanlangan bo'lsa "olib tashlash"
  if (db) db.style.display = state.customer ? '' : 'none';
});

let custTimer;
document.getElementById('custSearch').addEventListener('input', e => {
  clearTimeout(custTimer);
  custTimer = setTimeout(() => loadCustomers(e.target.value), 350);
});

async function loadCustomers(q = '') {
  const list = document.getElementById('custList');
  list.innerHTML = '<div style="padding:1rem;color:var(--text3);text-align:center">Yuklanmoqda...</div>';
  try {
    const url  = q ? `/customers/?search=${encodeURIComponent(q)}&limit=20` : '/customers/?limit=20';
    const res  = await api.get(url);
    const d     = res && res.data;
    const custs = (d && d.items) || (Array.isArray(d) ? d : []);
    if (!custs.length) { list.innerHTML = '<div style="padding:1rem;color:var(--text3);text-align:center">Topilmadi</div>'; return; }
    list.innerHTML = custs.map(c => `
      <div class="cust-item" data-id="${c.id}" data-name="${c.name}" data-phone="${c.phone || ''}" data-discount="${c.discount_percent || 0}">
        <div class="cust-ava">${c.name[0].toUpperCase()}</div>
        <div class="cust-detail">
          <div class="cust-name-row">${c.name}</div>
          <div class="cust-phone-row">${c.phone || '—'}</div>
        </div>
        <div class="cust-pts">${c.loyalty_points || 0} ball</div>
      </div>
    `).join('');
    list.querySelectorAll('.cust-item').forEach(item => {
      item.addEventListener('click', () => {
        // BOSQICH S2: _posSelectCustomer mijoz chegirmasini avtomatik qo'llaydi
        _posSelectCustomer({ id: +item.dataset.id, name: item.dataset.name, phone: item.dataset.phone, discount_percent: +item.dataset.discount || 0 });
        toast(`${item.dataset.name} tanlandi`, 'success');
      });
    });
  } catch { list.innerHTML = '<div style="padding:1rem;color:var(--text3)">Xatolik</div>'; }
}

// ─── BOSQICH 13: nasiyada tez yangi mijoz qo'shish (kassir) ────────────────────
function _posToggleNewCust(show) {
  const box = document.getElementById('posNewCustBox');
  if (!box) return;
  const on = (show === undefined) ? (box.style.display === 'none') : show;
  box.style.display = on ? '' : 'none';
  if (on) {
    document.getElementById('posNewName').value = '';
    document.getElementById('posNewPhone').value = '';
    const d = document.getElementById('posNewDiscount'); if (d) d.value = '';
    setTimeout(() => document.getElementById('posNewName').focus(), 50);
  }
}
function _posSelectCustomer(c) {
  state.customer = { id: +c.id, name: c.name, phone: c.phone || '', discount_percent: +c.discount_percent || 0 };
  _applyCustomerDiscount();   // BOSQICH S2: mijoz chegirmasini avtomatik qo'llash
  updateCustBtn();
  _posToggleNewCust(false);
  closeModal('customerModal');
}

// BOSQICH S2: mijoz chegirmasini savatga qo'llash (variant A — manual override).
// Qo'lda chegirma (manual) ustun — mijoz chegirmasi uni bosmaydi. Ikki chegirma
// STACK bo'lmaydi (bitta state.discount slot). computeTotals O'ZGARMAYDI.
function _applyCustomerDiscount() {
  if (state.discountSource === 'manual') return;   // qo'lda chegirma ustun
  const pct = state.customer?.discount_percent || 0;
  if (pct > 0) {
    state.discount = { type: 'pct', value: pct };
    state.discountSource = 'customer';
  } else if (state.discountSource === 'customer') {
    // Yangi mijozda chegirma yo'q, lekin oldingi mijoznikini tozalaymiz
    state.discount = { type: 'pct', value: 0 };
    state.discountSource = null;
  }
  renderTotals();
}

// BOSQICH S2: mijozni olib tashlash — customer-source chegirma tozalanadi, manual qoladi
function _posDeselectCustomer() {
  state.customer = null;
  if (state.discountSource === 'customer') {
    state.discount = { type: 'pct', value: 0 };
    state.discountSource = null;
  }
  updateCustBtn();
  renderTotals();
  closeModal('customerModal');
}
document.getElementById('custDeselectBtn')?.addEventListener('click', _posDeselectCustomer);
async function posAddNewCustomer() {
  const name  = document.getElementById('posNewName').value.trim();
  const phone = document.getElementById('posNewPhone').value.trim();
  if (!name)  { toast('Ism kiriting', 'warning'); return; }
  if (!phone) { toast('Telefon kiriting', 'warning'); return; }   // nasiya — telefon majburiy
  // BOSQICH S1: chegirma % (ixtiyoriy, 0-100)
  const discRaw = document.getElementById('posNewDiscount')?.value;
  const disc = discRaw !== '' && discRaw != null ? parseFloat(discRaw) : 0;
  if (!(disc >= 0 && disc <= 100)) { toast("Chegirma 0-100 oralig'ida", 'warning'); return; }
  const btn = document.getElementById('posNewCustSave');
  btn.disabled = true;
  try {
    // Shu do'kon ro'yxatida telefon bo'lsa — mavjudni tanla (dublikat yaratma)
    try {
      const sr = await api.get(`/customers/?search=${encodeURIComponent(phone)}&limit=20`);
      const sd = sr && sr.data;
      const found = ((sd && sd.items) || (Array.isArray(sd) ? sd : [])).find(c => (c.phone || '') === phone);
      if (found) { _posSelectCustomer(found); toast(`${found.name} tanlandi`, 'success'); return; }
    } catch {}
    const res = await api.post('/customers/', { name, phone, discount_percent: disc });
    const c = res && res.data;
    if (!res || !res.success || !c || !c.id) throw new Error((res && res.error) || 'Telefon band yoki xato');
    _posSelectCustomer(c);
    toast("Mijoz qo'shildi va tanlandi", 'success');
  } catch (e) {
    toast(e.message || 'Xato', 'error');   // backend 400: "Bu telefon raqam band" (global unique)
  } finally {
    btn.disabled = false;
  }
}
document.getElementById('posNewCustBtn')?.addEventListener('click', () => _posToggleNewCust());
document.getElementById('posNewCustSave')?.addEventListener('click', posAddNewCustomer);

// ─── Table ────────────────────────────────────────────────────────────────────
function updateCarBtn() {
  const btn = document.getElementById('carBtn');
  const lbl = document.getElementById('carBtnLabel');
  if (!btn || !lbl) return;
  if (state.carInfo?.plate) {
    btn.classList.add('has-cust');
    const parts = [state.carInfo.plate, state.carInfo.make, state.carInfo.model].filter(Boolean);
    lbl.textContent = `🚗 ${parts.join(' ')}`;
  } else {
    btn.classList.remove('has-cust');
    lbl.textContent = "Avtomobil ma'lumotlari";
  }
}

function updateStaffBtn() {
  const btn = document.getElementById('staffBtn');
  const lbl = document.getElementById('staffBtnLabel');
  if (!btn || !lbl) return;
  if (state.staffMember) {
    btn.classList.add('has-cust');
    lbl.textContent = `✂️ ${state.staffMember.name}`;
  } else {
    btn.classList.remove('has-cust');
    lbl.textContent = 'Xodim tanlang';
  }
}

function updateRxBtn() {
  const btn = document.getElementById('rxBtn');
  const lbl = document.getElementById('rxBtnLabel');
  if (!btn || !lbl) return;
  if (state.rxInfo) {
    btn.classList.add('has-cust');
    lbl.textContent = `Rx: ${state.rxInfo.patient_name}`;
  } else {
    btn.classList.remove('has-cust');
    lbl.textContent = "Retsept qo'shish";
  }
}

function updateStudentBtn() {
  const btn = document.getElementById('studentBtn');
  const lbl = document.getElementById('studentBtnLabel');
  if (!btn || !lbl) return;
  if (state.studentInfo?.name) {
    btn.classList.add('has-cust');
    lbl.textContent = `🎓 ${state.studentInfo.name}${state.studentInfo.group ? ' · ' + state.studentInfo.group : ''}`;
  } else {
    btn.classList.remove('has-cust');
    lbl.textContent = "O'quvchi ma'lumotlari";
  }
}

function updateCleaningBtn() {
  const btn = document.getElementById('cleaningBtn');
  const lbl = document.getElementById('cleaningBtnLabel');
  if (!btn || !lbl) return;
  if (state.cleaningInfo?.items) {
    btn.classList.add('has-cust');
    const pd = state.cleaningInfo.pickup_date
      ? ' · ' + new Date(state.cleaningInfo.pickup_date).toLocaleDateString('uz-UZ',{day:'2-digit',month:'2-digit'})
      : '';
    lbl.textContent = `👔 ${state.cleaningInfo.items}${pd}`;
  } else {
    btn.classList.remove('has-cust');
    lbl.textContent = "Buyurtma ma'lumotlari";
  }
}

function updateTableBtn() {
  const lbl   = document.getElementById('tableBtnLabel');
  const label = MODE.isHotel ? 'Xona' : 'Stol';
  if (state.table) {
    lbl.innerHTML = `${label} <span class="table-num">#${state.table.number}</span>`;
    document.getElementById('tableBtn').classList.add('selected');
  } else {
    lbl.textContent = `${label} tanlang`;
    document.getElementById('tableBtn').classList.remove('selected');
  }
}

document.getElementById('tableBtn').addEventListener('click', () => { renderFloorPlan(); openModal('tableModal'); });

function renderFloorPlan() {
  const fp = document.getElementById('floorPlan');
  if (!state.tables.length) {
    fp.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text3)">Stollar topilmadi</div>';
    return;
  }
  const sections = {};
  state.tables.forEach(t => { const sec = t.section || 'Asosiy zal'; (sections[sec] = sections[sec] || []).push(t); });
  fp.innerHTML = Object.entries(sections).map(([sec, tbls]) => `
    <div class="floor-section">
      <div class="floor-sec-title">${sec}</div>
      <div class="tables-grid">
        ${tbls.map(t => `
          <div class="tbl-card ${t.status || 'free'}" data-id="${t.id}" data-num="${t.number}">
            <div class="tbl-num">${t.number}</div>
            <div class="tbl-cap">${t.capacity} kishi</div>
            <div class="tbl-status">${{free:'Bo\'sh',occupied:'Band',reserved:'Bron',cleaning:'Tozalanmoqda'}[t.status]||t.status}</div>
          </div>
        `).join('')}
      </div>
    </div>
  `).join('');
  fp.querySelectorAll('.tbl-card').forEach(card => {
    card.addEventListener('click', () => {
      const tid = +card.dataset.id, tnum = +card.dataset.num;
      // If already have a table and click another → offer merge
      if (state.table && state.table.id !== tid) {
        const el = document.getElementById('mergeSelIds');
        if (el.querySelector(`[data-mid="${tid}"]`)) {
          el.querySelector(`[data-mid="${tid}"]`).remove();
        } else {
          const span = document.createElement('span');
          span.dataset.mid = tid;
          el.appendChild(span);
        }
        card.classList.toggle('merge-sel');
        updateMergeBar();
        return;
      }
      state.table = { id: tid, number: tnum };
      updateTableBtn();
      closeModal('tableModal');
      toast(`Stol #${state.table.number} tanlandi`, 'success');
    });
  });
}

// ─── Discount ─────────────────────────────────────────────────────────────────
let discType = 'pct';
document.querySelectorAll('.disc-type-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.disc-type-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    discType = btn.dataset.dtype;
    document.getElementById('discLabel').textContent = discType === 'pct' ? 'Foiz miqdori' : 'Summa miqdori';
    document.getElementById('discUnit').textContent  = discType === 'pct' ? '%' : 'UZS';
    document.getElementById('discValue').value       = '';
    const presets = document.getElementById('discPresets');
    presets.innerHTML = discType === 'pct'
      ? [5,10,15,20,25,50].map(v => `<button class="disc-preset" data-v="${v}">${v}%</button>`).join('')
      : [5000,10000,20000,50000].map(v => `<button class="disc-preset" data-v="${v}">${fmtNum(v)}</button>`).join('');
    presets.querySelectorAll('.disc-preset').forEach(p => {
      p.addEventListener('click', () => document.getElementById('discValue').value = p.dataset.v);
    });
  });
});
document.getElementById('discPresets').querySelectorAll('.disc-preset').forEach(p => {
  p.addEventListener('click', () => document.getElementById('discValue').value = p.dataset.v);
});
document.getElementById('applyDiscBtn').addEventListener('click', () => {
  const v = parseMoney(document.getElementById('discValue').value);
  if (discType === 'pct' && (v < 0 || v > 100)) { toast('Foiz 0–100 oralig\'ida bo\'lishi kerak', 'error'); return; }
  state.discount = { type: discType, value: v };
  state.discountSource = v > 0 ? 'manual' : null;   // BOSQICH S2: qo'lda → manual (ustun); bo'sh → null
  renderTotals();
  closeModal('discountModal');
  toast(v > 0 ? `Chegirma qo\'llandi` : 'Chegirma olib tashlandi', 'success');
});

// ─── Quick actions ────────────────────────────────────────────────────────────
document.querySelectorAll('.qa-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.dataset.action === 'discount') openModal('discountModal');
    if (btn.dataset.action === 'split')    openSplitModal();
    if (btn.dataset.action === 'print')    printLastReceipt();
    if (btn.dataset.action === 'notes')    toast('Izoh funksiyasi tez orada', 'info');
  });
});

document.getElementById('voiceOrderBtn')?.addEventListener('click', sendVoiceOrder);

function openSplitModal() {
  if (!state.cart.length) { toast('Savat bo\'sh', 'warning'); return; }
  document.getElementById('splitTotalAmt').textContent = fmt(computeTotals().total);
  document.getElementById('splitWaysInput').value = '2';
  document.getElementById('splitResult').classList.remove('show');
  openModal('splitModal');
}
document.querySelectorAll('.ways-quick').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.ways-quick').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('splitWaysInput').value = btn.dataset.w;
  });
});
document.getElementById('doSplitBtn').addEventListener('click', () => {
  const ways = parseInt(document.getElementById('splitWaysInput').value) || 2;
  if (ways < 2) { toast('Kamida 2 kishi', 'error'); return; }
  const per = computeTotals().total / ways;
  document.getElementById('splitPerPerson').textContent = fmt(per);
  document.getElementById('splitResult').classList.add('show');
});
function printLastReceipt() {
  if (!document.getElementById('receiptBody').innerHTML.trim()) { toast('Chek mavjud emas', 'warning'); return; }
  openModal('receiptModal');
}

// ─── Tips ─────────────────────────────────────────────────────────────────────
let tipAmount = 0;
function updateTipDisplay() {
  document.getElementById('tipDisplay').textContent = fmt(tipAmount);
}
document.querySelectorAll('.tip-preset').forEach(btn => {
  btn.addEventListener('click', () => {
    const v = btn.dataset.tip;
    if (v === 'custom') { document.getElementById('tipInput').focus(); return; }
    const pct = parseFloat(v) || 0;
    tipAmount = Math.round(computeTotals().total * pct / 100);
    document.getElementById('tipInput').value = tipAmount ? fmtNum(tipAmount) : '';
    updateTipDisplay();
  });
});
attachMoneyInput(document.getElementById('tipInput'));
document.getElementById('tipInput').addEventListener('input', e => {
  tipAmount = parseMoney(e.target.value);
  updateTipDisplay();
});

// ─── Table merge (TABLE_MERGE feature) ────────────────────────────────────────
let mergeMode = false;
const mergeSelected = new Set();

function updateMergeBar() {
  const ids = [...document.getElementById('mergeSelIds').querySelectorAll('[data-mid]')].map(e => +e.dataset.mid);
  mergeSelected.clear(); ids.forEach(id => mergeSelected.add(id));
  const bar = document.getElementById('mergeBar');
  if (mergeSelected.size === 0) { bar.style.display = 'none'; return; }
  bar.style.display = '';
  document.getElementById('mergeList').textContent = [...mergeSelected].join(', ') + '-stol';
}

document.getElementById('doMergeBtn').addEventListener('click', async () => {
  if (!state.table || mergeSelected.size === 0) { toast('Asosiy stol tanlang, keyin birlashtiriluvchi stollarni belgilang', 'warning'); return; }
  const ids = [...mergeSelected];
  try {
    const res = await api.post(`/tables/${state.table.id}/merge`, { merge_table_ids: ids });
    if (!res || !res.success) throw new Error((res && res.error) || 'Birlashtirish xatoligi');
    toast(`Stol #${state.table.number} bilan birlashtirdi`, 'success');
    document.getElementById('mergeSelIds').innerHTML = '';
    updateMergeBar();
    closeModal('tableModal');
  } catch (err) { toast(err?.message || err?.detail || 'Birlashtirish xatoligi', 'error'); }
});

// ─── Payment ──────────────────────────────────────────────────────────────────
let payMethod = 'cash';
document.querySelectorAll('.pay-method').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.pay-method').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    payMethod = btn.dataset.method;
    document.getElementById('cashSection').style.display = payMethod === 'cash' ? '' : 'none';
    document.getElementById('changeRow').style.display   = 'none';
    document.getElementById('cashInput').value           = '';
  });
});

attachMoneyInput(document.getElementById('cashInput'));
document.getElementById('cashInput').addEventListener('input', () => {
  const given  = parseMoney(document.getElementById('cashInput').value);
  const total  = payableTotal();   // redeem'dan keyingi naqd summasi
  const change = given - total;
  const row    = document.getElementById('changeRow');
  if (given > 0) {
    row.style.display = '';
    document.getElementById('changeAmt').textContent = fmt(Math.max(0, change));
    document.getElementById('changeAmt').style.color = change >= 0 ? 'var(--success)' : 'var(--danger)';
  } else { row.style.display = 'none'; }
});

document.querySelectorAll('.cash-preset').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.id === 'exactBtn') {
      document.getElementById('cashInput').value = Math.ceil(payableTotal() / 1000) * 1000;
    } else {
      document.getElementById('cashInput').value = btn.dataset.amt;
    }
    document.getElementById('cashInput').dispatchEvent(new Event('input'));
  });
});

document.getElementById('checkoutBtn').addEventListener('click', startCheckout);
document.getElementById('doPayBtn').addEventListener('click', doPayment);

// ─── Sodiqlik (loyalty) — POS redeem ───────────────────────────────────────────
// Backend: /loyalty/settings (sozlama) + /loyalty/summary/{id} (balans). Redeem = to'lov
// tenderi: naqd summa = jami − redeem_amount. SERVER qayta tekshiradi (client'ga ishonilmaydi).
let loyaltyCfg = null, loyBalance = 0, redeemPts = 0, redeemAmt = 0, lastLoyalty = null;

async function ensureLoyaltyCfg() {
  if (loyaltyCfg) return loyaltyCfg;
  const r = await api.get('/loyalty/settings').catch(() => null);
  loyaltyCfg = (r && r.success && r.data) ? r.data : { enabled: false };
  return loyaltyCfg;
}
function loyaltyMaxRedeem() {
  if (!loyaltyCfg || !loyaltyCfg.enabled || !loyBalance) return 0;
  const total = computeTotals().total;
  const byPct = Math.floor((total * (loyaltyCfg.max_redeem_percent / 100)) / (loyaltyCfg.redeem_value || 1));
  return Math.max(0, Math.min(loyBalance, byPct));
}
function applyRedeem(pts) {
  const maxR = loyaltyMaxRedeem();
  redeemPts = Math.max(0, Math.min(parseInt(pts, 10) || 0, maxR));
  redeemAmt = redeemPts * (loyaltyCfg?.redeem_value || 0);
  const inp = document.getElementById('redeemInput');
  if (inp && (parseInt(inp.value, 10) || 0) !== redeemPts) inp.value = redeemPts || '';
  const disp = document.getElementById('redeemAmtDisp'); if (disp) disp.textContent = fmt(redeemAmt);
  document.getElementById('cashInput').dispatchEvent(new Event('input'));   // naqd summasini yangilaydi
}
// Redeem'ni hisobga olgan haqiqiy to'lov summasi (naqd/karta shu summani qoplaydi)
function payableTotal() { return Math.max(0, computeTotals().total - (redeemAmt || 0)); }

// Payment modal ochilganda chaqiriladi: sozlama + mijoz balansini yuklaydi, bo'limni ko'rsatadi.
async function posLoyaltyOnOpen() {
  redeemPts = 0; redeemAmt = 0; lastLoyalty = null;
  const sec = document.getElementById('loyaltyPaySection');
  const inp = document.getElementById('redeemInput'); if (inp) inp.value = '';
  const disp = document.getElementById('redeemAmtDisp'); if (disp) disp.textContent = '0 UZS';
  if (!sec) return;
  sec.style.display = 'none'; loyBalance = 0;
  // Offline'da redeem yo'q (server tekshiruvi kerak)
  if (!navigator.onLine || !state.customer?.id) return;
  await ensureLoyaltyCfg();
  if (!loyaltyCfg.enabled) return;
  const s = await api.get(`/loyalty/summary/${state.customer.id}`).catch(() => null);
  loyBalance = (s && s.success && s.data) ? (s.data.points ?? s.data.balance ?? 0) : 0;
  const bal = document.getElementById('loyBal'); if (bal) bal.textContent = loyBalance;
  if (loyBalance >= (loyaltyCfg.min_redeem_points || 1)) sec.style.display = '';
}
document.getElementById('redeemInput')?.addEventListener('input', e => applyRedeem(e.target.value));
document.getElementById('redeemMaxBtn')?.addEventListener('click', () => applyRedeem(loyaltyMaxRedeem()));

let offlineCheckout = false;

// api.js {success,data,status,offline} contract'i. Natija TARMOQ yo'qligидан kelib chiqqanmi?
// (offline flag YOKI brauzer offline). Server xatosi (400/500) bunga KIRMAYDI.
function isOfflineResult(res) {
  return !navigator.onLine || !!(res && res.offline);
}

async function startCheckout() {
  if (!state.cart.length) return;

  // Tarmoq aniq yo'q → serverni chaqirmasdan to'g'ridan-to'g'ri offline navbat oqimи
  if (!navigator.onLine) { beginOfflineCheckout(); return; }

  // BUG 7: reopen qilingan "kutilayotgan" buyurtma — sotuvda YANGI order yaratiladi,
  // shuning uchun eskisini cancel qilamiz (aks holda held ro'yxatida dublikat qoladi).
  // holdBtn'dagi dedup bilan bir xil mantiq.
  const reopenedId = state.pendingOrderId;

  const res   = await api.post('/orders/', buildOrderPayload());
  const order = res && res.data;

  if (res && res.success && order && order.id) {
    // ── Online muvaffaqiyat ──
    state.pendingOrderId = order.id;
    if (reopenedId && reopenedId !== order.id) {
      try { await api.post(`/orders/${reopenedId}/cancel?reason=${encodeURIComponent('Qayta sotildi')}`); } catch {}
    }
    offlineCheckout = false;
    document.getElementById('payOrderNum').textContent = order.order_number || order.id;
    document.getElementById('payTotalAmt').textContent = fmt(computeTotals().total);
    payMethod = 'cash';
    document.querySelectorAll('.pay-method').forEach(b => b.classList.toggle('active', b.dataset.method === 'cash'));
    document.getElementById('cashSection').style.display = '';
    document.getElementById('cashInput').value = '';
    document.getElementById('changeRow').style.display = 'none';
    posLoyaltyOnOpen();   // sodiqlik: balans + redeem bo'limi (mijoz tanlangan bo'lsa)
    openModal('paymentModal');
    return;
  }

  // ── Xato ── TARMOQ yo'qmi (→ navbat) yoki SERVER xatosimi (→ ko'rsat, navbatga tushmasin)?
  if (isOfflineResult(res)) { beginOfflineCheckout(); return; }
  toast((res && res.error) || 'Buyurtma yaratishda xatolik', 'error');
}

// Offline checkout: to'lov modalини offline rejimда ochish (submit'да queueOrder'га yoziladi)
function beginOfflineCheckout() {
  offlineCheckout = true;
  state.pendingOrderId = null;
  const offlineNum = `OFF-${Date.now().toString().slice(-6)}`;
  document.getElementById('payOrderNum').textContent = offlineNum;
  document.getElementById('payTotalAmt').textContent = fmt(computeTotals().total);
  payMethod = 'cash';
  document.querySelectorAll('.pay-method').forEach(b => b.classList.toggle('active', b.dataset.method === 'cash'));
  document.getElementById('cashSection').style.display = '';
  document.getElementById('cashInput').value = '';
  document.getElementById('changeRow').style.display = 'none';
  // Offline badge ko'rsatish
  const badge = document.getElementById('offlinePayBadge');
  if (badge) badge.style.display = '';
  toast('Offline rejim: to\'lov saqlanadi, internet kelganda yuboriladi', 'warning', 4000);
  posLoyaltyOnOpen();   // offline'da redeem yashiriladi (server tekshiruvi kerak)
  openModal('paymentModal');
}

function buildOrderPayload() {
  const t = computeTotals();
  return {
    table_id       : state.table?.id || null,
    customer_id    : state.customer?.id || null,
    order_type     : state.orderType,
    source         : 'pos',
    courses_enabled: MODE.hasCourses && state.cart.some(i => i.course_number > 1),
    items          : state.cart.map(i => ({
      product_id    : i.id,
      // Og'irlik mahsulot: qty = og'irlik (masalan, 0.35), price = umumiy summa
      // Oddiy mahsulot: qty = dona soni, price = dona narxi
      quantity      : i._weight != null ? i._weight : i.qty,
      price         : i._weight != null ? i._unitPrice : i.price,
      weight_unit   : i._unit     || null,
      unit_sold     : i._unitSold || null,   // BOSQICH B4: "pachka"|"dona"|null (server base_qty/narx hisoblaydi)
      course_number : MODE.hasCourses ? (i.course_number || 1) : 1,
      staff_id      : i._master?.id   || null,
      duration_min  : i._duration    || null,
      period_days   : i._period_days || null,
      start_date    : i._start_date  || null,
      end_date      : i._end_date    || null,
      sessions_count: i._sessions    || null,
      modifiers     : (i.modifiers || []).map(m => ({ modifier_id: m.modifier_id, name: m.name, price_delta: m.price_delta })),
    })),
    // C1: savatcha snapshot — held qayta ochilganda modifikator/og'irlik to'liq
    // tiklanadi (biz_meta['cart']). Serverdagi summaga ta'sir qilmaydi.
    cart_snapshot   : state.cart.map(i => ({
      id: i.id, name: i.name, price: i.price, qty: i.qty,
      _modKey: i._modKey || '', modifiers: i.modifiers || [], modLabel: i.modLabel || null,
      _weight: i._weight ?? null, _unit: i._unit || null, _unitPrice: i._unitPrice ?? null,
      _unitSold: i._unitSold || null, _packLabel: i._packLabel || null,   // BOSQICH B4
      course_number: i.course_number || 1,
    })),
    discount_type   : state.discount.value > 0 ? state.discount.type : null,
    discount_value  : state.discount.value || null,
    total_amount    : t.sub,
    discount_amount : t.disc,
    tax_amount      : t.tax,
    service_amount  : t.service,
    final_amount    : t.total,
    rx_patient_name : MODE.isPharmacy    && state.rxInfo  ? state.rxInfo.patient_name  : null,
    rx_patient_phone: MODE.isPharmacy    && state.rxInfo  ? state.rxInfo.patient_phone : null,
    rx_number       : MODE.isPharmacy    && state.rxInfo  ? state.rxInfo.rx_number     : null,
    car_plate       : MODE.isAutoService && state.carInfo   ? state.carInfo.plate          : null,
    car_make        : MODE.isAutoService && state.carInfo   ? state.carInfo.make           : null,
    car_model       : MODE.isAutoService && state.carInfo   ? state.carInfo.model          : null,
    car_year        : MODE.isAutoService && state.carInfo   ? state.carInfo.year           : null,
    student_name    : MODE.isSchool      && state.studentInfo ? state.studentInfo.name     : null,
    student_phone   : MODE.isSchool      && state.studentInfo ? state.studentInfo.phone    : null,
    student_group   : MODE.isSchool      && state.studentInfo ? state.studentInfo.group    : null,
    cleaning_items  : MODE.isDryCleaning && state.cleaningInfo ? state.cleaningInfo.items  : null,
    cleaning_color  : MODE.isDryCleaning && state.cleaningInfo ? state.cleaningInfo.color  : null,
    cleaning_notes  : MODE.isDryCleaning && state.cleaningInfo ? state.cleaningInfo.notes  : null,
    pickup_date     : MODE.isDryCleaning && state.cleaningInfo ? state.cleaningInfo.pickup_date : null,
  };
}

async function doPayment() {
  const t     = computeTotals();
  const due   = payableTotal();   // redeem'dan keyingi to'lanadigan summa (naqd/karta)
  const given = parseMoney(document.getElementById('cashInput').value) || due;
  if (payMethod === 'cash' && given < due) { toast('Qabul qilingan summa yetarli emas', 'error'); return; }
  // BOSQICH 19: Nasiya uchun mijoz tanlanganligini tekshirish
  if (payMethod === 'credit' && !state.customer?.id) {
    toast('Nasiya uchun mijozni tanlang', 'error'); return;
  }
  const btn = document.getElementById('doPayBtn');
  btn.disabled = true; btn.textContent = 'Amalga oshirilmoqda...';

  const paymentPayload = {
    method      : payMethod,
    amount      : due,                          // ball chegirmasidan keyingi summa
    tip_amount  : tipAmount || 0,
    given_amount: payMethod === 'cash' ? given : due,
    change      : payMethod === 'cash' ? Math.max(0, given - due) : 0,
    room_id     : payMethod === 'room_charge' ? (state.table?.id || null) : null,
    redeem_points: redeemPts || 0,              // SERVER qayta tekshiradi
  };

  // ── Offline rejim ──
  if (offlineCheckout) {
    await syncEngine.queueOrder({ ...buildOrderPayload(), payment: paymentPayload });
    closeModal('paymentModal');
    const badge = document.getElementById('offlinePayBadge');
    if (badge) badge.style.display = 'none';
    offlineCheckout = false;
    renderOfflineReceipt(paymentPayload);
    openModal('receiptModal');
    sendEscposPrint(null);   // AVTOMATIK chek (offline ham) — HTML GDI print
    toast('Offline: buyurtma+to\'lov saqlandi', 'warning');
    clearOrderState();
    btn.disabled = false; btn.textContent = 'To\'lovni amalga oshirish';
    return;
  }

  // ── Online rejim ──
  // SMENA MAJBURIY: ochiq smena bo'lmasa savdo bloklanadi (kassa bor biznes).
  // ensureShiftGate false qaytarsa — smena ochish oynasi ko'rsatildi, savdo to'xtaydi.
  const _shiftOk = await ensureShiftGate();
  if (!_shiftOk) {
    toast('Avval smena oching', 'warning');
    btn.disabled = false; btn.textContent = 'To\'lovni amalga oshirish';
    return;
  }

  const orderId = state.pendingOrderId;
  if (!orderId) { toast('Buyurtma topilmadi', 'error'); btn.disabled = false; btn.textContent = 'To\'lovni amalga oshirish'; return; }
  try {
    // api.js {success,...} qaytaradi — muvaffaqiyatsizлик throw qilib catch'ga tushsin
    // (aks holda to'lov o'tmasa ham zakaz tozalanib, chek chiqib ketardi).
    const payRes = await api.post('/payments/', { order_id: orderId, ...paymentPayload });
    if (!payRes || !payRes.success) throw new Error((payRes && payRes.error) || 'To\'lov amalga oshmadi');

    // Sodiqlik natijasi (chek + toast uchun): yig'ilgan/ishlatilgan ball, qolgan balans
    const _pd = payRes.data || {};
    lastLoyalty = (_pd.earned_points || _pd.redeemed_points) ? {
      earned: _pd.earned_points || 0, redeemed: _pd.redeemed_points || 0,
      balance: (_pd.customer_points != null ? _pd.customer_points : null),
    } : null;
    if (lastLoyalty) {
      const parts = [];
      if (lastLoyalty.redeemed) parts.push(`${lastLoyalty.redeemed} ball ishlatildi`);
      if (lastLoyalty.earned)   parts.push(`+${lastLoyalty.earned} ball yig'ildi`);
      if (parts.length) toast(parts.join(', ') + (lastLoyalty.balance != null ? ` (balans: ${lastLoyalty.balance})` : ''), 'success', 4000);
    }

    // BOSQICH 19: Nasiya bo'lsa qarz yozuvini yaratish
    if (payMethod === 'credit' && state.customer?.id) {
      try {
        await api.post('/debts/', {
          customer_id: state.customer.id,
          order_id: orderId,
          amount: t.total,
          notes: 'POS dan nasiya',
        });
      } catch { /* qarz yozilmasa to'lov baribir tasdiqlangan */ }
    }

    closeModal('paymentModal');
    broadcastToDisplay('payment_complete');
    beep('success');
    await showReceipt(orderId);
    toast(payMethod === 'credit' ? 'Nasiya yozildi!' : 'To\'lov qabul qilindi!', 'success');
    clearOrderState();
    loadHeldOrders();   // to'langan buyurtma held ro'yxatidan tushadi
  } catch (err) {
    toast(err?.message || err?.detail || 'To\'lovda xatolik', 'error');
  } finally {
    btn.disabled = false; btn.textContent = 'To\'lovni amalga oshirish';
  }
}

function renderOfflineReceipt(payment) {
  const t    = computeTotals();
  const body = document.getElementById('receiptBody');
  body.innerHTML = `
    <div class="receipt-center">
      <h4>XENORA</h4>
      <p>${new Date().toLocaleString('uz-UZ')}</p>
      <div style="background:rgba(245,158,11,.15);color:#f59e0b;border-radius:4px;padding:.25rem .5rem;font-size:.6875rem;margin-top:.375rem">OFFLINE CHEK</div>
    </div>
    <div style="font-size:.7rem;color:var(--text3);margin-bottom:.5rem">
      ${state.table ? 'Stol: #'+state.table.number+' | ' : ''}Internet tiklanganda serverga yuboriladi
      ${MODE.isAutoService && state.carInfo?.plate ? `<br>🚗 ${[state.carInfo.plate, state.carInfo.make, state.carInfo.model, state.carInfo.year].filter(Boolean).join(' ')}` : ''}
    </div>
    <table class="receipt-table">
      <thead><tr><th>Mahsulot</th><th>Soni</th><th>Narxi</th></tr></thead>
      <tbody>${state.cart.map(i=>`<tr><td>${i.name}${i._packLabel?`<br><small style="font-size:.65rem;color:#d4b46c">📦 ${i._packLabel}</small>`:''}</td><td>${i.qty}</td><td style="text-align:right">${fmtNum(i.price*i.qty)}</td></tr>`).join('')}</tbody>
    </table>
    <div class="receipt-totals">
      <div class="rt-row"><span>Jami:</span><span>${fmtNum(t.sub)}</span></div>
      ${t.disc>0?`<div class="rt-row disc"><span>Chegirma${_rcptDiscountLabel()}:</span><span>-${fmtNum(t.disc)}</span></div>`:''}
      ${t.tax>0?`<div class="rt-row"><span>Soliq:</span><span>${fmtNum(t.tax)}</span></div>`:''}
      ${t.service>0?`<div class="rt-row"><span>Xizmat:</span><span>${fmtNum(t.service)}</span></div>`:''}
      ${payment.tip_amount>0?`<div class="rt-row"><span>Choy puli:</span><span>${fmtNum(payment.tip_amount)}</span></div>`:''}
      <div class="rt-row bold"><span>UMUMIY:</span><span>${fmtNum(t.total)} UZS</span></div>
      ${payment.method==='cash'?`<div class="rt-row"><span>Qabul qilindi:</span><span>${fmtNum(payment.given_amount)}</span></div><div class="rt-row"><span>Qaytim:</span><span>${fmtNum(payment.change)}</span></div>`:''}
      ${MODE.isPharmacy && state.rxInfo ? `<div class="rt-row" style="margin-top:.375rem"><span>Bemor:</span><span>${state.rxInfo.patient_name}</span></div>` : ''}
      ${MODE.isPharmacy && state.rxInfo?.rx_number ? `<div class="rt-row"><span>Retsept #:</span><span>${state.rxInfo.rx_number}</span></div>` : ''}
      ${MODE.isService  && state.staffMember ? `<div class="rt-row" style="margin-top:.375rem"><span>Xodim:</span><span>${state.staffMember.name}</span></div>` : ''}
    </div>
    <div class="receipt-footer">${MODE.isPharmacy ? "Sog'lig'ingizga shifa!<br>Farmatsevt: _________________" : MODE.isBeauty ? "Go'zallik uchun rahmat!<br>Yana kutib qolamiz 💅" : MODE.isFitness ? "Muvaffaqiyatli mashg'ulotlar! 💪" : MODE.isAutoService ? "Xizmat uchun rahmat! 🔧" : MODE.isSchool ? "O'qishda muvaffaqiyatlar! 📚" : MODE.isDryCleaning ? "Buyurtmangiz tayyor bo'lganda xabar beramiz! 👔" : MODE.isHotel ? "Xush kelibsiz! Yana kutib qolamiz 🏨" : 'Xarid uchun rahmat!'}</div>
  `;
}

// ─── Receipt + ESC/POS chop etish ─────────────────────────────────────────────
let _printerStatus = { enabled: false, auto_print: false, mode: 'mock' };
let _lastReceiptOrderId = null;
// Chek sozlamalari — chek print CSS'iga + markaziy print servisga uzatiladi.
// font_size: Kichik/Normal/Katta ('small'/'normal'/'large') → 11/13/15px (receipt-print.js).
// print_type (B1): 'usb' (SumatraPDF, default) | 'lan' (IP:port, stub) | 'qr'.
let _receiptCfg = { font_size: 'normal', print_type: 'usb', printer_ip: null, printer_port: null };

async function loadPrinterStatus() {
  try {
    const s = await api.get('/settings/printer/status');
    if (s && s.success && s.data && typeof s.data === 'object') _printerStatus = s.data;
  } catch { /* status olinmasa — window.print fallback ishlaydi */ }
}

async function loadReceiptSettings() {
  try {
    const s = await api.get('/receipt-settings/');
    const d = (s && s.success && s.data) ? s.data : s;   // api.js wrapped yoki xom
    if (d && typeof d === 'object') {
      if (d.font_size)  _receiptCfg.font_size  = d.font_size;
      if (d.print_type) _receiptCfg.print_type = d.print_type;   // B1: usb/lan/qr
      _receiptCfg.printer_ip   = d.printer_ip   || null;
      _receiptCfg.printer_port = d.printer_port || null;
    }
  } catch { /* sozlama olinmasa — 'normal' shrift + 'usb' print ishlatiladi */ }
}

// Markaziy print servisga uzatiladigan print sozlamalari (bir joyda).
function _printOpts(extra) {
  return Object.assign({
    fontSize:    _receiptCfg.font_size,
    printType:   _receiptCfg.print_type,
    printerIp:   _receiptCfg.printer_ip,
    printerPort: _receiptCfg.printer_port,
  }, extra || {});
}

// Chekni LOKAL printerga chiqarish (do'kon kompyuteridagi XP-58).
// MUHIM: Backend SERVERda ishlaydi va do'kondagi USB printerga yeta olmaydi,
// shuning uchun server ESC/POS yo'li ISHLATILMAYDI (mock yolg'on "yuborildi"
// yo'q). Electron'da yashirin oyna orqali silent (dialogsiz) print, brauzerda
// esa oddiy print dialogi (fallback). Chek mazmuni #receiptBody dan olinadi —
// S3 chegirma yorlig'i, pachka, jami — barchasi saqlanadi.
async function sendEscposPrint(_orderId) {
  const inner = (document.getElementById('receiptBody') || {}).innerHTML || '';
  if (!inner.trim()) { toast('Chek mavjud emas', 'warning'); return false; }
  const res = await printReceiptHTML(inner, _printOpts({
    deviceName: _printerStatus.printer_name || '',
    title: 'Chek',
  }));
  if (res && res.ok) {
    if (!res.browser) toast('Chek chiqarildi', 'success');  // brauzer dialogida jimgina
    return true;
  }
  // HAQIQIY xato — jimgina "yuborildi" demaymiz
  toast('Chek chiqmadi: ' + ((res && res.error) || "noma'lum xato"), 'error');
  return false;
}

async function showReceipt(orderId) {
  _lastReceiptOrderId = orderId || null;
  try {
    const rec = await api.get(`/orders/${orderId}/receipt`);
    if (rec && rec.success && rec.data) renderReceiptData(rec.data);   // api.js wrapped
    else renderReceiptFallback(orderId);
  } catch { renderReceiptFallback(orderId); }
  openModal('receiptModal');
  // AVTOMATIK CHEK — to'lovdan so'ng HAR DOIM bir marta chiqadi (kassir bosmaydi).
  // Chek mazmuni #receiptBody da render bo'lgandan keyin (yuqorida) HTML GDI silent
  // print (backend RAW ESC/POS emas — krakozyabra bo'lmasin). did-finish-load
  // main.js da kutiladi. "Chop etish" tugmasi qayta bosish (reprint) uchun qoladi.
  sendEscposPrint(orderId);
}

// BOSQICH B6: chek pachka yorlig'i — savat item'ida _packLabel, server item'ida
// unit_sold + base_qty (1 pachka = base_qty/quantity dona). Pachka bo'lmasa '' qaytadi.
function _rcptPackLabel(i) {
  if (i._packLabel) return i._packLabel;
  const q = i.quantity || i.qty;
  if (i.unit_sold === 'pachka' && i.base_qty && q) {
    const per = Math.round(i.base_qty / q);
    // #20 atir (sale_unit "ml") → "Butun (150 ml)"; oddiy pachka → "Pachka (N dona)"
    return i.sale_unit === 'ml' ? `Butun (${per} ml)` : `Pachka (${per} dona)`;
  }
  return '';
}

// BOSQICH S3: chek chegirma yorlig'i — " -10% (mijoz)" | " -5% (qo'lda)" | "" (bo'sh).
// Chek doim sotuvdan keyin (clearOrderState'dan oldin) render bo'ladi → state joriy.
// Faqat YORLIQ (foiz + manba); chegirma SUMMASI o'zgarmaydi (jami to'g'ri).
function _rcptDiscountLabel() {
  const d = state.discount;
  if (!d || !d.value || d.value <= 0) return '';
  const pct = d.type === 'pct' ? ` -${d.value}%` : '';
  const src = state.discountSource === 'customer' ? ' (mijoz)'
            : state.discountSource === 'manual'   ? " (qo'lda)" : '';
  return `${pct}${src}`;
}

function renderReceiptData(rec) {
  const t    = computeTotals();
  const body = document.getElementById('receiptBody');
  body.innerHTML = `
    <div class="receipt-center">
      <h4>${rec.cafe_name || 'XENORA'}</h4>
      <p>${rec.cafe_address || ''}<br>${new Date().toLocaleString('uz-UZ')}</p>
    </div>
    <div style="font-size:.7rem;color:var(--text3);margin-bottom:.5rem">
      Chek #${rec.order_number || rec.order_id}
      ${state.table ? ' | Stol: #' + state.table.number : ''}
      ${MODE.isAutoService && state.carInfo?.plate ? `<br>🚗 ${[state.carInfo.plate, state.carInfo.make, state.carInfo.model, state.carInfo.year].filter(Boolean).join(' ')}` : ''}
    </div>
    <table class="receipt-table">
      <thead><tr><th>Mahsulot</th><th>Soni</th><th>Narxi</th></tr></thead>
      <tbody>
        ${(rec.items || state.cart).map(i => {
          const d   = MODE.isPharmacy ? (i._dosage || i.dosage || '') : '';
          const m   = MODE.isService  ? (i._master?.name || '') : '';
          const dur = MODE.isService  && i._duration ? fmtDuration(i._duration) : '';
          const per = MODE.isFitness  && i._end_date
            ? `📅 ${new Date(i._end_date).toLocaleDateString('uz-UZ',{day:'2-digit',month:'2-digit',year:'numeric'})} gacha`
            : '';
          const pk  = _rcptPackLabel(i);
          // #20 atir: ml sotuvi — "10 ml" (client: _weight; server: sale_unit=ml, unit_sold≠pachka)
          const ml  = i._weight != null ? `${i._weight} ${i._unit || 'ml'}`
                    : (i.sale_unit === 'ml' && i.unit_sold !== 'pachka' && (i.quantity || i.qty) ? `${i.quantity || i.qty} ml` : '');
          const sub = [pk ? `📦 ${pk}` : '', ml ? `🧴 ${ml}` : '', d, m ? `✂️ ${m}` : '', dur ? `⏱ ${dur}` : '', per].filter(Boolean).join(' · ');
          return `<tr><td>${i.name||i.product_name||''}${sub?`<br><small style="font-size:.65rem;color:#9a9ab8">${sub}</small>`:''}</td><td>${i.quantity||i.qty}</td>
          <td style="text-align:right">${fmtNum(i.total||(i.price*(i.qty||i.quantity)))}</td></tr>`;
        }).join('')}
      </tbody>
    </table>
    <div class="receipt-totals">
      <div class="rt-row"><span>Jami:</span><span>${fmtNum(rec.subtotal||t.sub)}</span></div>
      ${(rec.discount_amount||t.disc)>0 ? `<div class="rt-row disc"><span>Chegirma${_rcptDiscountLabel()}:</span><span>-${fmtNum(rec.discount_amount||t.disc)}</span></div>` : ''}
      ${(rec.tax_amount||t.tax)>0?`<div class="rt-row"><span>Soliq (12%):</span><span>${fmtNum(rec.tax_amount||t.tax)}</span></div>`:''}
      ${(rec.service_amount||t.service)>0?`<div class="rt-row"><span>Xizmat (10%):</span><span>${fmtNum(rec.service_amount||t.service)}</span></div>`:''}
      <div class="rt-row bold"><span>UMUMIY:</span><span>${fmtNum(rec.final_amount||t.total)} UZS</span></div>
      <div class="rt-row"><span>To'lov:</span><span>${payMethod === 'room_charge' ? `🏨 Xona #${state.table?.number||'?'}` : payMethod.toUpperCase()}</span></div>
      ${loyaltyRows(rec)}
      ${MODE.isHotel    && state.table   ? `<div class="rt-row" style="margin-top:.375rem"><span>Xona:</span><span>#${state.table.number}</span></div>` : ''}
      ${MODE.isHotel    && state.customer ? `<div class="rt-row"><span>Mehmon:</span><span>${state.customer.name}</span></div>` : ''}
      ${MODE.isPharmacy && state.rxInfo ? `<div class="rt-row" style="margin-top:.375rem"><span>Bemor:</span><span>${state.rxInfo.patient_name}</span></div>` : ''}
      ${MODE.isPharmacy && state.rxInfo?.rx_number ? `<div class="rt-row"><span>Retsept #:</span><span>${state.rxInfo.rx_number}</span></div>` : ''}
    </div>
    ${MODE.isService && state.staffMember ? `<div class="rt-row" style="margin-top:.375rem"><span>Xodim:</span><span>${state.staffMember.name}</span></div>` : ''}
    <div class="receipt-footer">${MODE.isPharmacy ? "Sog'lig'ingizga shifa!<br>Farmatsevt: _________________" : MODE.isBeauty ? "Go'zallik uchun rahmat!<br>Yana kutib qolamiz 💅" : MODE.isFitness ? "Muvaffaqiyatli mashg'ulotlar! 💪" : MODE.isAutoService ? "Xizmat uchun rahmat! 🔧" : MODE.isSchool ? "O'qishda muvaffaqiyatlar! 📚" : MODE.isDryCleaning ? "Buyurtmangiz tayyor bo'lganda xabar beramiz! 👔" : MODE.isHotel ? "Xush kelibsiz! Yana kutib qolamiz 🏨" : 'Xarid uchun rahmat!'}</div>
    ${rec.fiscal_qr_url ? `
    <div style="margin-top:.625rem;padding:.5rem .75rem;background:rgba(16,185,129,.07);border:1px solid rgba(16,185,129,.18);border-radius:.5rem;text-align:center">
      <div style="font-size:.68rem;font-weight:700;color:#10b981;letter-spacing:.4px">🧾 FISKAL CHEK</div>
      ${rec.fiscal_number ? `<div style="font-size:.65rem;color:var(--text2);margin:.2rem 0">№ ${rec.fiscal_number}</div>` : ''}
      <img src="https://api.qrserver.com/v1/create-qr-code/?size=90x90&data=${encodeURIComponent(rec.fiscal_qr_url)}"
           width="90" height="90" alt="Fiskal QR"
           style="display:block;margin:.375rem auto;border-radius:4px;background:#fff;padding:2px"
           onerror="this.style.display='none'">
      <div style="font-size:.6rem;color:var(--text3)">Soliq ilovasida skanerlang → 1% keshbek</div>
    </div>` : ''}
  `;
}

function renderReceiptFallback(orderId) {
  const t    = computeTotals();
  const body = document.getElementById('receiptBody');
  body.innerHTML = `
    <div class="receipt-center"><h4>XENORA</h4><p>${new Date().toLocaleString('uz-UZ')}</p></div>
    <div style="font-size:.7rem;color:var(--text3);margin-bottom:.5rem">Buyurtma #${orderId}</div>
    <table class="receipt-table">
      <thead><tr><th>Mahsulot</th><th>Soni</th><th>Narxi</th></tr></thead>
      <tbody>${state.cart.map(i=>`<tr><td>${i.name}${i._packLabel?`<br><small style="font-size:.65rem;color:#d4b46c">📦 ${i._packLabel}</small>`:''}</td><td>${i.qty}</td><td style="text-align:right">${fmtNum(i.price*i.qty)}</td></tr>`).join('')}</tbody>
    </table>
    <div class="receipt-totals">
      <div class="rt-row"><span>Jami:</span><span>${fmtNum(t.sub)}</span></div>
      ${t.disc>0?`<div class="rt-row disc"><span>Chegirma${_rcptDiscountLabel()}:</span><span>-${fmtNum(t.disc)}</span></div>`:''}
      ${t.tax>0?`<div class="rt-row"><span>Soliq:</span><span>${fmtNum(t.tax)}</span></div>`:''}
      ${t.service>0?`<div class="rt-row"><span>Xizmat:</span><span>${fmtNum(t.service)}</span></div>`:''}
      <div class="rt-row bold"><span>UMUMIY:</span><span>${fmtNum(t.total)} UZS</span></div>
    </div>
    <div class="receipt-footer">Xarid uchun rahmat!</div>
  `;
}
document.getElementById('printReceiptBtn').addEventListener('click', () => {
  // Chekni LOKAL printerga (Electron silent / brauzer dialog) — reprint ham shu.
  sendEscposPrint(_lastReceiptOrderId);
});

// ─── #21/#22: POS Sotuvlar tarixi + reprint ───────────────────────────────────
// Kassir → o'z bugungi sotuvlari (cashier_id filtri); admin/menejer → barchasi.
// Reprint: admin bilan bir xil buildReceipt58(rec) + printReceiptHTML (PDF/SumatraPDF,
// global payMethod/state'ga tayanmaydi → tarix uchun to'g'ri).
function _shEsc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function _posUser() { try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; } }
function _posIsManager() {
  const u = _posUser();
  if (u.is_superuser) return true;
  const r = canonRole(u.role?.name || u.role || '');
  return r === 'admin' || r === 'manager';
}
const _shPay = { cash: 'Naqd', card: 'Karta', click: 'Click', payme: 'Payme', credit: 'Nasiya', transfer: "O'tkazma", room_charge: 'Xona' };

async function loadSalesHistory() {
  const list = document.getElementById('salesHistoryList');
  const det  = document.getElementById('salesHistoryDetail');
  det.style.display = 'none'; list.style.display = '';
  list.innerHTML = '<div style="text-align:center;padding:1.5rem;color:var(--text3)">Yuklanmoqda…</div>';
  const mgr = _posIsManager();
  document.getElementById('shTitle').textContent = mgr ? 'Sotuvlar tarixi — bugun' : 'Mening sotuvlarim — bugun';
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const params = new URLSearchParams({ page: '1', page_size: '40', date_from: today.toISOString() });
  const u = _posUser();
  if (!mgr && u.id) params.set('cashier_id', String(u.id));   // RBAC: kassir → faqat o'z sotuvlari
  try {
    const res = await api.get('/orders/?' + params.toString());
    const orders = (res && res.data && res.data.items) || [];
    if (!orders.length) {
      list.innerHTML = '<div style="text-align:center;padding:1.5rem;color:var(--text3)">Bugun sotuv yo\'q</div>';
      return;
    }
    list.innerHTML = orders.map(o => {
      const time = o.created_at ? new Date(o.created_at).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' }) : '';
      const num  = o.daily_number != null ? '#' + o.daily_number : (o.order_number || '');
      const pay  = _shPay[o.payment_method] || o.payment_method || '—';
      const who  = mgr && o.waiter_name ? ' · ' + _shEsc(o.waiter_name) : '';
      return `<div class="sh-row" data-sh-detail="${o.id}" style="display:flex;align-items:center;gap:.5rem;padding:.6rem .4rem;border-bottom:1px solid var(--border2);cursor:pointer">
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;font-size:.85rem">${_shEsc(num)} · ${time}</div>
          <div style="font-size:.72rem;color:var(--text3)">${_shEsc(pay)}${who}</div>
        </div>
        <div style="font-weight:700;color:var(--gold);font-size:.85rem">${fmtNum(o.final_amount)}</div>
        <button data-sh-print="${o.id}" title="Chekni chop etish" style="background:var(--bg3);border:1px solid var(--border2);border-radius:.4rem;padding:.35rem .55rem;cursor:pointer;color:var(--text);font-size:.9rem">🖨</button>
      </div>`;
    }).join('');
  } catch {
    list.innerHTML = '<div style="text-align:center;padding:1.5rem;color:var(--danger)">Xatolik — qayta urinib ko\'ring</div>';
  }
}

async function showSalesDetail(id) {
  const list = document.getElementById('salesHistoryList');
  const det  = document.getElementById('salesHistoryDetail');
  list.style.display = 'none'; det.style.display = '';
  det.innerHTML = '<div style="text-align:center;padding:1.5rem;color:var(--text3)">Yuklanmoqda…</div>';
  try {
    const res = await api.get('/orders/' + id + '/receipt');
    const rec = res && res.data;
    if (!rec) { det.innerHTML = '<div style="color:var(--danger);padding:1rem">Chek topilmadi</div>'; return; }
    const rows = (rec.items || []).map(it =>
      `<tr><td style="padding:2px 0">${_shEsc(it.name || '')}</td><td style="text-align:center">${_shEsc(it.quantity)}</td>
       <td style="text-align:right">${fmtNum(it.total)}</td></tr>`).join('');
    const pay = (rec.payment_methods || []).map(p => _shPay[p.method] || p.method).join(', ') || '—';
    det.innerHTML =
      `<button data-sh-back="1" style="background:var(--bg3);border:1px solid var(--border2);border-radius:.4rem;padding:.35rem .6rem;cursor:pointer;color:var(--text);font-size:.8rem;margin-bottom:.6rem">← Orqaga</button>
      <div style="font-weight:700;margin-bottom:.4rem">Chek ${rec.order_number ? '#' + _shEsc(rec.order_number) : ''} · ${_shEsc(rec.date || '')}</div>
      <table style="width:100%;border-collapse:collapse;font-size:.8rem">
        <thead><tr style="color:var(--text3);text-align:left"><th style="padding:2px 0">Mahsulot</th><th style="text-align:center">Soni</th><th style="text-align:right">Jami</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="3" style="color:var(--text3);padding:.5rem">Mahsulot yo\'q</td></tr>'}</tbody>
      </table>
      <div style="border-top:1px dashed var(--border2);margin-top:.5rem;padding-top:.5rem;display:flex;justify-content:space-between;font-weight:700"><span>UMUMIY</span><span style="color:var(--gold)">${fmtNum(rec.final_amount)} UZS</span></div>
      <div style="font-size:.75rem;color:var(--text3);margin-top:.2rem">To'lov: ${_shEsc(pay)}</div>
      <button data-sh-print="${id}" style="margin-top:.75rem;width:100%;background:var(--gold);color:#0a0a0f;border:none;border-radius:.5rem;padding:.55rem;cursor:pointer;font-weight:700">🖨 Chekni chop etish</button>`;
  } catch {
    det.innerHTML = '<div style="color:var(--danger);padding:1rem">Xatolik</div>';
  }
}

async function reprintSale(id) {
  try {
    const res = await api.get('/orders/' + id + '/receipt');
    const rec = res && res.data;
    if (!rec) { toast('Chek topilmadi', 'error'); return; }
    const html = buildReceipt58(rec);   // admin reprint bilan bir xil (global state'siz)
    const r = await printReceiptHTML(html, _printOpts({ deviceName: _printerStatus.printer_name || '', title: 'Chek #' + (rec.order_number || id) }));
    if (r && r.ok) { if (!r.browser) toast('Chek chiqarildi', 'success'); }
    else toast('Chek chiqmadi: ' + ((r && r.error) || "noma'lum xato"), 'error');
  } catch (e) {
    toast('Chek xato: ' + (e?.message || e), 'error');
  }
}

document.getElementById('salesHistoryBtn')?.addEventListener('click', () => {
  openModal('salesHistoryModal');
  loadSalesHistory();
});
document.getElementById('salesHistoryList')?.addEventListener('click', (e) => {
  const pb = e.target.closest('[data-sh-print]');
  if (pb) { e.stopPropagation(); reprintSale(pb.dataset.shPrint); return; }
  const rb = e.target.closest('[data-sh-detail]');
  if (rb) showSalesDetail(rb.dataset.shDetail);
});
document.getElementById('salesHistoryDetail')?.addEventListener('click', (e) => {
  if (e.target.closest('[data-sh-back]')) {
    document.getElementById('salesHistoryDetail').style.display = 'none';
    document.getElementById('salesHistoryList').style.display = '';
    return;
  }
  const pb = e.target.closest('[data-sh-print]');
  if (pb) reprintSale(pb.dataset.shPrint);
});

// ─── #23: POS Ombor qoldig'i (narx + qoldiq; TANNARX faqat admin/view_finance) ──
// Kassir mijozga "bor, X so'm, Y qoldi" deb ayta oladi. Tannarx/ombor qiymatini
// kassir KO'RMAYDI (backend /inventory/pos-stock cost'ni faqat view_finance'ga beradi).
let _posStockTimer = null;
function _stockNum(n) {
  const v = Number(n) || 0;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, '');
}
async function loadPosStock(search = '') {
  const list  = document.getElementById('posStockList');
  const totEl = document.getElementById('posStockTotal');
  list.innerHTML = '<div style="text-align:center;padding:1.5rem;color:var(--text3)">Yuklanmoqda…</div>';
  totEl.style.display = 'none';
  const params = new URLSearchParams({ limit: '400' });
  if (search) params.set('search', search);
  try {
    const res  = await api.get('/inventory/pos-stock?' + params.toString());
    const data = res && res.data;
    const rows = (data && data.items) || [];
    if (!rows.length) {
      list.innerHTML = '<div style="text-align:center;padding:1.5rem;color:var(--text3)">Mahsulot topilmadi</div>';
      return;
    }
    // Ombor qiymati (jami tannarx) — FAQAT admin (backend can_cost bo'lsa qaytaradi)
    if (data.can_cost && data.total_value != null) {
      totEl.style.display = '';
      totEl.textContent = `Ombor qiymati (tannarx): ${fmtNum(data.total_value)} UZS`;
    }
    list.innerHTML = rows.map(r => {
      const low  = (r.quantity != null && r.min_threshold != null && r.quantity <= r.min_threshold);
      const qty  = `${_shEsc(_stockNum(r.quantity))} ${_shEsc(r.unit || r.sale_unit || '')}`;
      const cost = (data.can_cost && r.cost_price != null)
        ? `<div style="font-size:.68rem;color:var(--text3)">Tannarx: ${fmtNum(r.cost_price)}</div>` : '';
      return `<div style="display:flex;align-items:center;gap:.5rem;padding:.55rem .4rem;border-bottom:1px solid var(--border2)">
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;font-size:.85rem">${_shEsc(r.name)}</div>
          <div style="font-size:.72rem;color:var(--gold)">${fmtNum(r.price)} UZS${r.sale_unit ? ' / ' + _shEsc(r.sale_unit) : ''}</div>
          ${cost}
        </div>
        <div style="text-align:right">
          <div style="font-weight:700;font-size:.85rem;color:${low ? 'var(--danger)' : 'var(--text)'}">${qty}</div>
          ${low ? '<div style="font-size:.6rem;color:var(--danger)">kam qoldi</div>' : ''}
        </div>
      </div>`;
    }).join('');
  } catch {
    list.innerHTML = '<div style="text-align:center;padding:1.5rem;color:var(--danger)">Xatolik — qayta urinib ko\'ring</div>';
  }
}
document.getElementById('posStockBtn')?.addEventListener('click', () => {
  const s = document.getElementById('posStockSearch');
  if (s) s.value = '';
  openModal('posStockModal');
  loadPosStock('');
  setTimeout(() => s?.focus(), 100);
});
document.getElementById('posStockSearch')?.addEventListener('input', (e) => {
  const q = e.target.value.trim();
  clearTimeout(_posStockTimer);
  _posStockTimer = setTimeout(() => loadPosStock(q), 250);
});

// ─── Hold order ───────────────────────────────────────────────────────────────
document.getElementById('holdBtn').addEventListener('click', async () => {
  if (!state.cart.length) return;

  // C2: reopen qilingan held (pendingOrderId) qayta saqlansa — eski pending
  // dublikat qolmasligi kerak. Yangi zakaz muvaffaqiyatli yaratilgach eskisini
  // bekor qilamiz (yangilangan savatcha bilan bitta held qoladi).
  const reopenedId = state.pendingOrderId;

  // Tarmoq aniq yo'q → to'g'ridan-to'g'ri navbatga
  if (!navigator.onLine) {
    await syncEngine.queueOrder(buildOrderPayload());
    toast('Offline: saqlandi', 'warning');
    clearOrderState();
    return;
  }

  const res = await api.post('/orders/', buildOrderPayload());
  if (res && res.success && res.data && res.data.id) {
    // C2: eski pending zakazni bekor qilish (dublikat bo'lmasin)
    if (reopenedId && reopenedId !== res.data.id) {
      try { await api.post(`/orders/${reopenedId}/cancel?reason=${encodeURIComponent('Qayta saqlandi')}`); } catch {}
    }
    // Bu HOLD (kutish) — sotuv EMAS, to'lov qilinmagan. Zakaz "Kutilayotgan" ro'yxatida.
    toast('Buyurtma kutishga saqlandi', 'success');
  } else if (isOfflineResult(res)) {
    // Tarmoq uzildi → kafolatли navbatга
    await syncEngine.queueOrder(buildOrderPayload());
    toast('Offline: saqlandi', 'warning');
  } else {
    // Server xatosi — navbatga tushmasin, cart saqlanadi (qayta urinish uchun)
    toast((res && res.error) || 'Saqlashda xatolik', 'error');
    return;
  }
  clearOrderState();
  loadHeldOrders();
});

function clearOrderState() {
  state.cart = []; state.discount = { type: 'pct', value: 0 }; state.discountSource = null;   // BOSQICH S2
  state.customer = null; state.table = null; state.pendingOrderId = null;
  state.rxInfo       = null;
  state.staffMember  = null;
  state.carInfo      = null;
  state.studentInfo  = null;
  state.cleaningInfo = null;
  state.orderType    = MODE.isStore ? 'takeaway' : (MODE.isService ? 'service' : (MODE.isHotel ? 'room_service' : 'dine-in'));
  tipAmount = 0;
  const tipInp = document.getElementById('tipInput');
  if (tipInp) tipInp.value = '';
  updateTipDisplay();
  document.querySelectorAll('.otype-btn').forEach((b, i) => b.classList.toggle('active', i === 0));
  updateCustBtn(); updateTableBtn(); updateRxBtn(); updateStaffBtn(); updateCarBtn();
  updateStudentBtn(); updateCleaningBtn();
  renderCart();
  localDB.clear(STORES.CART).catch(() => {});
}

// ─── Kutilayotgan (held) buyurtmalar ────────────────────────────────────────────
// Hold "Saqlash" pending buyurtma yaratadi. Bu yerda ular ro'yxati ko'rinadi va
// qayta ochib to'lov qilish mumkin (yo'qolmaydi). Magazin rejimida hold yashiriladi.
let _heldOrders = [];

async function loadHeldOrders() {
  const btn = document.getElementById('heldOrdersBtn');
  if (!btn || btn.style.display === 'none') return;
  try {
    const res = await api.get('/orders/?status=pending&page_size=50');
    const data = res?.data ?? res;
    _heldOrders = data?.items ?? (Array.isArray(data) ? data : []);
  } catch { _heldOrders = []; }
  const badge = document.getElementById('heldOrdersBadge');
  if (badge) {
    const n = _heldOrders.length;
    badge.textContent = n;
    badge.style.display = n > 0 ? 'flex' : 'none';
  }
}

function openHeldModal() {
  const list = document.getElementById('heldList');
  if (!_heldOrders.length) {
    list.innerHTML = '<div style="text-align:center;color:var(--text3);padding:2rem">Kutilayotgan buyurtma yo\'q</div>';
  } else {
    list.innerHTML = _heldOrders.map(o => {
      const n     = o.order_number || o.daily_number || o.id;
      const total = o.final_amount ?? o.total_amount ?? 0;
      const cnt   = (o.items || []).length;
      const when  = o.created_at ? new Date(o.created_at).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' }) : '';
      const tbl   = o.table?.number || o.table_number;
      return `<div class="held-row" data-hid="${o.id}" style="display:flex;justify-content:space-between;align-items:center;gap:.75rem;padding:.75rem .875rem;background:var(--bg3);border:1px solid var(--border2);border-radius:.625rem;cursor:pointer">
        <div>
          <div style="font-weight:600;color:var(--text)">#${n}${tbl ? ` · Stol ${tbl}` : ''}</div>
          <div style="font-size:.75rem;color:var(--text3)">${cnt} ta mahsulot${when ? ' · ' + when : ''}</div>
        </div>
        <div style="display:flex;align-items:center;gap:.625rem">
          <div style="font-weight:700;color:var(--gold)">${fmt(total)}</div>
          <button class="held-del" data-hid="${o.id}" title="O'chirish" aria-label="O'chirish" style="flex-shrink:0;width:34px;height:34px;border-radius:.5rem;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:#ef4444;font-size:1rem;cursor:pointer;display:flex;align-items:center;justify-content:center">🗑</button>
        </div>
      </div>`;
    }).join('');
    list.querySelectorAll('.held-row').forEach(row => {
      row.addEventListener('click', () => reopenHeldOrder(+row.dataset.hid));
    });
    // BUG 5: kutilayotgan buyurtmani qo'lda o'chirish (cancel). Reopen click'iga
    // o'tib ketmasligi uchun stopPropagation.
    list.querySelectorAll('.held-del').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const hid = +btn.dataset.hid;
        if (!confirm('Bu kutilayotgan buyurtma o\'chirilsinmi?')) return;
        btn.disabled = true;
        const res = await api.post(`/orders/${hid}/cancel?reason=${encodeURIComponent('Kutilayotgan o\'chirildi')}`);
        if (res && res.success) {
          if (state.pendingOrderId === hid) state.pendingOrderId = null;
          toast('Buyurtma o\'chirildi', 'success');
          await loadHeldOrders();
          openHeldModal();   // ro'yxatni qayta chizish
        } else {
          btn.disabled = false;
          toast((res && res.error) || 'O\'chirishda xatolik', 'error');
        }
      });
    });
  }
  openModal('heldModal');
}

async function reopenHeldOrder(orderId) {
  if (state.cart.length && !confirm('Joriy savatcha almashtiriladi. Davom etasizmi?')) return;
  let order = _heldOrders.find(o => o.id === orderId);
  try {
    const res = await api.get(`/orders/${orderId}`);
    order = res?.data ?? res ?? order;
  } catch {}
  if (!order || !order.items) { toast('Buyurtma topilmadi', 'error'); return; }

  // C1: savatchani to'liq tiklash. Saqlashda biz_meta.cart snapshot bo'lsa —
  // undan (modifikator, og'irlik, narx aynan) tiklaymiz. Bo'lmasa (eski zakaz)
  // buyurtma elementlaridan zaxira tiklash (modifikator/og'irliksiz).
  const snap = order.biz_meta && Array.isArray(order.biz_meta.cart) ? order.biz_meta.cart : null;
  if (snap && snap.length) {
    state.cart = snap.map(i => ({
      id: i.id,
      name: i.name || prodNameById(i.id),
      price: i.price ?? 0,
      qty: i.qty ?? 1,
      _modKey: i._modKey || '',
      modifiers: i.modifiers || [],
      modLabel: i.modLabel || null,
      _weight: i._weight ?? null,
      _unit: i._unit || null,
      _unitPrice: i._unitPrice ?? null,
      _unitSold: i._unitSold || null,      // BOSQICH B4
      _packLabel: i._packLabel || null,    // BOSQICH B4
      course_number: i.course_number || 1,
    }));
  } else {
    state.cart = order.items.map(it => ({
      id: it.product_id,
      name: it.product_name || prodNameById(it.product_id),
      price: it.unit_price ?? it.price ?? 0,
      qty: it.quantity ?? 1,
      _modKey: '',
      modifiers: [],
      modLabel: null,
    }));
  }
  state.pendingOrderId = orderId;   // to'lov shu buyurtmani yakunlaydi (dublikat emas)
  closeModal('heldModal');
  renderCart();
  toast(`Buyurtma #${order.order_number || orderId} ochildi`, 'success');
}

function prodNameById(id) { return state.products.find(p => p.id === id)?.name || 'Mahsulot'; }

document.getElementById('heldOrdersBtn')?.addEventListener('click', async () => {
  await loadHeldOrders();
  openHeldModal();
});

// ─── Modal close ──────────────────────────────────────────────────────────────
document.querySelectorAll('[data-close]').forEach(el => {
  el.addEventListener('click', () => closeModal(el.dataset.close));
});

// ─── Sidebar / UI ─────────────────────────────────────────────────────────────
document.getElementById('sidebarToggle')?.addEventListener('click', () =>
  document.getElementById('sidebar').classList.toggle('wide'));
document.getElementById('fullscreenBtn')?.addEventListener('click', () => {
  if (!document.fullscreenElement) document.documentElement.requestFullscreen?.();
  else document.exitFullscreen?.();
});

// ─── BUG 3: Grid/List ko'rinishini almashtirish ─────────────────────────────────
const _ICON_GRID = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.8"/><rect x="14" y="3" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.8"/><rect x="3" y="14" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.8"/><rect x="14" y="14" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.8"/></svg>`;
const _ICON_LIST = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M8 6h13M8 12h13M8 18h13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="3.5" cy="6" r="1.3" fill="currentColor"/><circle cx="3.5" cy="12" r="1.3" fill="currentColor"/><circle cx="3.5" cy="18" r="1.3" fill="currentColor"/></svg>`;

function applyPosView() {
  const grid = document.getElementById('productsGrid');
  if (grid) grid.classList.toggle('list-view', _posView === 'list');
  const btn = document.getElementById('viewToggleBtn');
  if (btn) {
    const isList = _posView === 'list';
    // Tugmada — o'tiladigan ko'rinish ikonkasi (list'da → grid ikonka)
    btn.innerHTML = isList ? _ICON_GRID : _ICON_LIST;
    btn.title = isList ? "Katta (grid) ko'rinishga o'tish" : "Ro'yxat (list) ko'rinishga o'tish";
  }
}

function togglePosView() {
  _posView = _posView === 'list' ? 'grid' : 'list';
  applyPosView();
}

document.getElementById('viewToggleBtn')?.addEventListener('click', togglePosView);
applyPosView();   // boshlang'ich ikonka + grid klassi

// ─── Audio feedback ───────────────────────────────────────────────────────────
let _audioCtx = null;
function beep(type = 'add') {
  try {
    if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const ctx = _audioCtx;
    if (ctx.state === 'suspended') ctx.resume();
    const play = (freq, startAt, dur, vol = 0.25) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.connect(g); g.connect(ctx.destination);
      o.frequency.value = freq;
      o.type = 'sine';
      g.gain.setValueAtTime(vol, ctx.currentTime + startAt);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + startAt + dur);
      o.start(ctx.currentTime + startAt);
      o.stop(ctx.currentTime + startAt + dur + 0.01);
    };
    if (type === 'add')     { play(880, 0, 0.08); }
    else if (type === 'error')   { play(220, 0, 0.25, 0.35); }
    else if (type === 'success') { play(660, 0, 0.1); play(880, 0.1, 0.15); }
  } catch {}
}

// ─── Mijoz ekrani (Customer Display — BroadcastChannel) ───────────────────────
const _custChannel = ('BroadcastChannel' in window) ? new BroadcastChannel('restopos_customer_display') : null;

function broadcastToDisplay(extraType) {
  if (!_custChannel) return;
  const totals = computeTotals();
  _custChannel.postMessage({
    type        : extraType || 'cart_update',
    businessType: MODE.businessType,
    businessName: (localStorage.getItem('restopos_features') && JSON.parse(localStorage.getItem('restopos_features'))?.data?.company_name) || 'XENORA',
    cart        : state.cart.map(i => ({ name: i.name, qty: i.qty, price: i.price, _unit: i._unit })),
    totals,
    ts          : Date.now(),
  });
}

document.getElementById('custDisplayBtn')?.addEventListener('click', () => {
  const w = window.open('../app/customer-display.html', 'customer_display',
    'width=1024,height=768,menubar=no,toolbar=no,location=no,status=no');
  if (!w) toast('Popup bloklangan. Brauzer ruxsat bering.', 'warning');
});

// ─── Barcode scanner ──────────────────────────────────────────────────────────
let _bcTimer = null;

async function handleBarcodeScan(code) {
  if (!code || code.length < 2) return;
  const statusEl = document.getElementById('barcodeStatus');
  statusEl.textContent = 'Qidirilmoqda...';
  statusEl.className   = '';

  // Avval xotiradagi mahsulotlardan qidirish (offline-first)
  let found = state.products.find(p => p.barcode === code);
  let weightKg = null;
  let calcPrice = null;

  if (!found) {
    try {
      // Ko'p barcode tizimi orqali qidirish (multi-barcode + tarozi barcode)
      const _r = await api.get(`/barcodes/lookup/${encodeURIComponent(code)}`);
      const bcRes = (_r && _r.success) ? _r.data : null;
      if (bcRes && bcRes.id) {
        found = bcRes;
        weightKg  = bcRes.weight_kg  || null;
        calcPrice = bcRes.calculated_price || null;
        // lookup `unit` qaytaradi; addToCart/isWeightUnit `sale_unit` ni o'qiydi → moslab qo'yamiz
        if (bcRes.sale_unit == null && bcRes.unit != null) bcRes.sale_unit = bcRes.unit;
        if (!state.products.find(p => p.id === bcRes.id)) state.products.push(bcRes);
      }
    } catch {}
  }

  if (!found) {
    try {
      const res = await api.get(`/products/?search=${encodeURIComponent(code)}&page_size=1`);
      const d   = res && res.data;
      const items = (d && d.items) || (Array.isArray(d) ? d : []);
      found = items.find(p => p.barcode === code) || items[0] || null;
      if (found && !state.products.find(p => p.id === found.id)) {
        state.products.push(found);
      }
    } catch {}
  }

  if (found) {
    if (weightKg && calcPrice) {
      // Tarozi barcode: og'irlik bo'yicha narx qo'shish
      statusEl.textContent = `✓ ${found.name} (${weightKg.toFixed(3)} kg)`;
      statusEl.className   = 'found';
      // Tarozi: og'irlik (kg) RAQAM sifatida uzatiladi → doAddToCart unitPrice × weightKg hisoblaydi
      addToCart(found.id, weightKg);
    } else {
      statusEl.textContent = `✓ ${found.name}`;
      statusEl.className   = 'found';
      addToCart(found.id);
    }
  } else {
    statusEl.textContent = 'Topilmadi: ' + code;
    statusEl.className   = 'notfound';
    toast(`Barkod topilmadi: ${code}`, 'warning');
    beep('error');
  }

  // 3 soniyadan keyin status tozalanadi
  clearTimeout(_bcTimer);
  _bcTimer = setTimeout(() => { statusEl.textContent = 'Tayyor'; statusEl.className = ''; }, 3000);
}

const barcodeInput = document.getElementById('barcodeInput');
barcodeInput?.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    e.preventDefault();
    const code = barcodeInput.value.trim();
    barcodeInput.value = '';
    handleBarcodeScan(code);
  }
});

// ─── Search + keyboard ────────────────────────────────────────────────────────
let srchTimer;
document.getElementById('searchInput').addEventListener('input', () => {
  clearTimeout(srchTimer);
  srchTimer = setTimeout(() => renderProducts(), 250);
});
document.addEventListener('keydown', e => {
  // Ctrl/Cmd+K — qidiruv
  if ((e.ctrlKey||e.metaKey) && e.key === 'k') { e.preventDefault(); document.getElementById('searchInput').focus(); }
  // F2 — barcode / qidiruv fokus
  if (e.key === 'F2') { e.preventDefault(); (barcodeInput || document.getElementById('searchInput')).focus(); }
  // F4 — to'lov modali
  if (e.key === 'F4') { e.preventDefault(); document.getElementById('checkoutBtn').click(); }
  // F8 — buyurtmani to'xtatib qo'yish (hold)
  if (e.key === 'F8') { e.preventDefault(); document.getElementById('holdBtn').click(); }
  // F9 — oxirgi mahsulotni savatdan olib tashlash (qaytarish/undo)
  if (e.key === 'F9') {
    e.preventDefault();
    if (state.cart.length) {
      const removed = state.cart.pop();
      renderCart();
      beep('error');
      toast(`"${removed.name}" olib tashlandi`, 'info');
    }
  }
  // F3 — retsept (dorixona)
  if (e.key === 'F3' && MODE.isPharmacy) { e.preventDefault(); document.getElementById('rxBtn')?.click(); }
  // Esc — ochiq modallarni yopish
  if (e.key === 'Escape') document.querySelectorAll('.modal-wrap.open').forEach(m => m.classList.remove('open'));
});

// ─── Logout ───────────────────────────────────────────────────────────────────
document.getElementById('logoutBtn')?.addEventListener('click', () => {
  // TENANT IZOLYATSIYA + haqiqiy chiqish: token, user, do'kon kodi, feature va
  // IndexedDB offline keshni TO'LIQ tozalash (avval AuthService.logout static
  // chaqiruv edi — undefined, hech narsa tozalanmasdi va chiqib bo'lmasdi).
  clearTenantSession();
  location.replace('../shared/login.html');
});

// ─── Offline banner ───────────────────────────────────────────────────────────
window.addEventListener('offline', () => document.getElementById('offlineBanner').classList.add('show'));
window.addEventListener('online',  () => document.getElementById('offlineBanner').classList.remove('show'));
if (!navigator.onLine) document.getElementById('offlineBanner').classList.add('show');

// ─── WebSocket ────────────────────────────────────────────────────────────────
let posWs = null;

function connectWS() {
  const token = localStorage.getItem('access_token');
  if (!token) return;
  posWs = new WebSocket(`${WS_URL}?token=${token}`);
  const dot = document.getElementById('wsDot');
  posWs.onopen  = () => dot.classList.add('on');
  posWs.onclose = () => { posWs = null; dot.classList.remove('on'); setTimeout(connectWS, 5000); };
  posWs.onerror = () => posWs.close();
  posWs.onmessage = e => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'order_ready')   toast(`Buyurtma #${msg.order_number} tayyor!`, 'success', 6000);
      if (msg.type === 'notification')  toast(msg.message || msg.title, 'info', 5000);
    } catch {}
  };
}

function sendVoiceOrder() {
  if (!state.cart.length) { toast('Savat bo\'sh', 'warning'); return; }
  const payload = {
    type  : 'voice_order',
    table : state.table ? { id: state.table.id, number: state.table.number, name: state.table.name } : null,
    items : state.cart.map(i => ({ product_name: i.name, quantity: i.qty })),
  };
  if (posWs && posWs.readyState === WebSocket.OPEN) {
    posWs.send(JSON.stringify(payload));
    toast('Ovozli e\'lon yuborildi', 'success');
  } else {
    toast('WebSocket ulanmagan', 'error');
  }
}

// ─── Auto servis: Avtomobil modal ────────────────────────────────────────────
document.getElementById('carConfirmBtn')?.addEventListener('click', () => {
  const plate = (document.getElementById('carPlate')?.value  || '').trim().toUpperCase();
  const make  = (document.getElementById('carMake')?.value   || '').trim();
  const model = (document.getElementById('carModel')?.value  || '').trim();
  const year  = (document.getElementById('carYear')?.value   || '').trim();
  if (!plate) { toast("Davlat raqamini kiriting", 'warning'); return; }
  state.carInfo = { plate, make, model, year };
  updateCarBtn();
  closeModal('carModal');
  toast(`🚗 ${[plate, make, model].filter(Boolean).join(' ')} saqlandi`, 'success');
});

document.getElementById('carClearBtn')?.addEventListener('click', () => {
  state.carInfo = null;
  ['carPlate','carMake','carModel','carYear'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  updateCarBtn();
  closeModal('carModal');
});

// ─── Maktab: O'quvchi modal ───────────────────────────────────────────────────
document.getElementById('studentConfirmBtn')?.addEventListener('click', () => {
  const name  = (document.getElementById('studentName')?.value  || '').trim();
  const phone = (document.getElementById('studentPhone')?.value || '').trim();
  const group = (document.getElementById('studentGroup')?.value || '').trim();
  if (!name) { toast("O'quvchi ismini kiriting", 'warning'); return; }
  state.studentInfo = { name, phone, group };
  updateStudentBtn();
  closeModal('studentModal');
  toast(`🎓 ${name} saqlandi`, 'success');
});

document.getElementById('studentClearBtn')?.addEventListener('click', () => {
  state.studentInfo = null;
  ['studentName','studentPhone','studentGroup'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  updateStudentBtn();
  closeModal('studentModal');
});

// ─── Kimyoviy tozalash: Kiyim modal ──────────────────────────────────────────
let _pendingCleanProduct = null;

document.getElementById('cleaningConfirmBtn')?.addEventListener('click', () => {
  const items  = (document.getElementById('cleaningItems')?.value       || '').trim();
  const color  = (document.getElementById('cleaningColor')?.value       || '').trim();
  const notes  = (document.getElementById('cleaningNotes')?.value       || '').trim();
  const pickup = (document.getElementById('cleaningPickupDate')?.value  || '').trim();
  if (!items) { toast("Kiyim turini kiriting", 'warning'); return; }
  state.cleaningInfo = { items, color, notes, pickup_date: pickup || null };
  updateCleaningBtn();
  closeModal('cleaningModal');
  toast(`👔 ${items} — buyurtma saqlandi`, 'success');
  if (_pendingCleanProduct) {
    const p = _pendingCleanProduct; _pendingCleanProduct = null;
    doAddToCart(p, []);
  }
});

document.getElementById('cleaningClearBtn')?.addEventListener('click', () => {
  state.cleaningInfo = null;
  _pendingCleanProduct = null;
  ['cleaningItems','cleaningColor','cleaningNotes','cleaningPickupDate'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  updateCleaningBtn();
  closeModal('cleaningModal');
});

// ─── Dorixona: Retsept modal ──────────────────────────────────────────────────
document.getElementById('rxConfirmBtn')?.addEventListener('click', () => {
  const name  = (document.getElementById('rxPatientName')?.value  || '').trim();
  const phone = (document.getElementById('rxPatientPhone')?.value || '').trim();
  const rxNum = (document.getElementById('rxNumber')?.value       || '').trim();
  if (!name) { toast("Bemor ismini kiriting", 'warning'); return; }
  state.rxInfo = { patient_name: name, patient_phone: phone, rx_number: rxNum };
  updateRxBtn();
  closeModal('rxModal');
  toast(`Retsept saqlandi: ${name}`, 'success');
});

document.getElementById('rxClearBtn')?.addEventListener('click', () => {
  state.rxInfo = null;
  const fn = document.getElementById('rxPatientName');
  const fp = document.getElementById('rxPatientPhone');
  const fr = document.getElementById('rxNumber');
  if (fn) fn.value = '';
  if (fp) fp.value = '';
  if (fr) fr.value = '';
  updateRxBtn();
  closeModal('rxModal');
});

// ─── Xodimlar yuklash (service rejim) ────────────────────────────────────────
async function loadStaff(q = '') {
  const list = document.getElementById('staffList');
  if (!list) return;
  list.innerHTML = '<div style="padding:1rem;color:var(--text3);text-align:center">Yuklanmoqda...</div>';
  try {
    const url  = q ? `/staff/?search=${encodeURIComponent(q)}&limit=30` : '/staff/?limit=30&is_active=true';
    const res  = await api.get(url);
    const d       = res && res.data;
    const members = (d && d.items) || (Array.isArray(d) ? d : []);
    if (!members.length) {
      list.innerHTML = '<div style="padding:1rem;color:var(--text3);text-align:center">Xodimlar topilmadi</div>';
      return;
    }
    list.innerHTML = members.map(m => `
      <div class="cust-item" data-id="${m.id}" data-name="${m.name||m.full_name||''}" data-spec="${m.specialty||m.role||m.position||''}">
        <div class="cust-ava">${(m.name||m.full_name||'X')[0].toUpperCase()}</div>
        <div class="cust-detail">
          <div class="cust-name-row">${m.name||m.full_name||''}</div>
          <div class="cust-phone-row">${m.specialty||m.role||m.position||''}</div>
        </div>
      </div>
    `).join('');
    list.querySelectorAll('.cust-item').forEach(item => {
      item.addEventListener('click', () => {
        state.staffMember = { id: +item.dataset.id, name: item.dataset.name, specialty: item.dataset.spec };
        updateStaffBtn();
        closeModal('staffModal');
        toast(`${state.staffMember.name} tanlandi`, 'success');
      });
    });
  } catch {
    list.innerHTML = '<div style="padding:1rem;color:var(--text3)">Xodimlar topilmadi</div>';
  }
}

document.getElementById('staffClearBtn')?.addEventListener('click', () => {
  state.staffMember = null;
  updateStaffBtn();
  closeModal('staffModal');
});

let staffTimer;
document.getElementById('staffSearch')?.addEventListener('input', e => {
  clearTimeout(staffTimer);
  staffTimer = setTimeout(() => loadStaff(e.target.value), 350);
});

// ─── Biznes tur UI moslash ────────────────────────────────────────────────────
function applyBusinessMode() {
  if (!MODE.isStore && !MODE.isService) return; // restoran/kafe — hech narsani o'zgartirmaymiz

  // Oshxonasiz biznes turlari (store/dorixona/xizmat): kitchen_display feature
  // o'chiq bo'lsa "Oshxona" navini yashir. Restoran/kafe yuqorida early-return
  // qildi va kitchen_display ularda yoqilgan — ular ta'sirlanmaydi.
  if (!posHasFeature('kitchen_display')) {
    const kitchenNav = document.querySelector('.sidebar a.nav-item[href="kitchen.html"]');
    if (kitchenNav) kitchenNav.style.display = 'none';
  }

  // "Bronlar" (stol bandlash) — faqat table_reservation yoqilgan biznesda (restoran/kafe).
  // Magazin/do'kon/xizmatda bu feature yo'q → navni yashiramiz.
  if (!posHasFeature('table_reservation')) {
    const resNav = document.querySelector('.sidebar a.nav-item[href="reservations.html"]');
    if (resNav) resNav.style.display = 'none';
  }

  const tableBtn = document.getElementById('tableBtn');

  // Savatcha sarlavhasini biznes turiga moslash ("Buyurtma" → "Savatcha")
  const cartHeadTitle = document.getElementById('cartHeadTitle');
  if (cartHeadTitle) cartHeadTitle.textContent = MODE.saleTerm;

  // ── STORE rejimi (magazin / supermarket / dorixona) ──
  if (MODE.isStore) {
    document.getElementById('barcodeRow')?.classList.add('visible');
    if (tableBtn) tableBtn.style.display = 'none';
    state.orderType = 'takeaway';
    document.querySelectorAll('.otype-btn').forEach(b => b.classList.toggle('active', b.dataset.type === 'takeaway'));
    // Buyurtma turi qatorini yashirish (do'konda sotuv — Shu yerda/Olib ketish/Yetkazish kerak emas)
    const otypeRow = document.querySelector('.otype-row');
    if (otypeRow) otypeRow.style.display = 'none';
    document.getElementById('taxRow')?.style.setProperty('display','none');
    document.getElementById('svcRow')?.style.setProperty('display','none');
    document.getElementById('tipsSection')?.style.setProperty('display','none');

    // BOSQICH 19: Nasiya to'lov tugmasini ko'rsatish (store/supermarket uchun)
    const creditBtn = document.getElementById('creditMethod');
    if (creditBtn && (MODE.businessType === 'store' || MODE.businessType === 'supermarket')) {
      creditBtn.style.display = '';
      const payMethodsEl = document.querySelector('.pay-methods');
      if (payMethodsEl) payMethodsEl.classList.add('has-credit');
    }

    // BOSQICH 20: Tez sotuv panelini yuklash (store/supermarket uchun)
    if (MODE.businessType === 'store' || MODE.businessType === 'supermarket') {
      loadQuickSellPanel();
      loadDeptsBar();    // BOSQICH 21: Bo'limlar filtri
    }
  }

  // ── SERVICE rejimi (go'zallik / fitnes / auto) ──
  if (MODE.isService) {
    if (tableBtn) tableBtn.style.display = 'none';
    // Buyurtma turi qatorini yashirish (dine-in/takeaway/delivery service uchun mantiqsiz)
    const otypeRow = document.querySelector('.otype-row');
    if (otypeRow) otypeRow.style.display = 'none';
    state.orderType = 'service';
    // Xizmat haqi qatorini yashirish (serviceRate = 0)
    document.getElementById('svcRow')?.style.setProperty('display','none');

    // Xodim / Master tugmasini qo'shish
    const cartMeta = document.querySelector('.cart-meta');
    if (cartMeta && !document.getElementById('staffBtn')) {
      const staffBtn = document.createElement('button');
      staffBtn.id = 'staffBtn';
      staffBtn.className = 'cust-btn';
      staffBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="3" stroke="currentColor" stroke-width="1.8"/><path d="M6.5 20c0-3 2.5-5.5 5.5-5.5s5.5 2.5 5.5 5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M17 3l1 1-5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'
                         + '<span id="staffBtnLabel">Xodim tanlang</span>';
      cartMeta.insertBefore(staffBtn, otypeRow || cartMeta.lastElementChild);
      staffBtn.addEventListener('click', () => { openModal('staffModal'); loadStaff(); });
    }
  }

  // ── Hotel-specific: Xona labellash, buyurtma turlari, "Xonaga" to'lov ──
  if (MODE.isHotel) {
    // Stol → Xona relabeling
    const tblLbl = document.getElementById('tableBtnLabel');
    if (tblLbl) tblLbl.textContent = 'Xona tanlang';
    const tblModalTitle = document.querySelector('#tableModal .modal-header h3');
    if (tblModalTitle) tblModalTitle.textContent = 'Xona tanlash';

    // Buyurtma turlari hotel uchun
    const otypeBtns = document.querySelectorAll('.otype-btn');
    const hotelTypes  = ['room_service', 'restaurant', 'minibar'];
    const hotelLabels = ['Xona xizmati', 'Restoran', 'Minibar'];
    otypeBtns.forEach((btn, i) => {
      if (hotelLabels[i]) btn.textContent = hotelLabels[i];
      if (hotelTypes[i])  btn.dataset.type = hotelTypes[i];
    });
    state.orderType = 'room_service';
    document.querySelectorAll('.otype-btn').forEach((b, i) => b.classList.toggle('active', i === 0));

    // Xizmat haqi qatorini yashirish (serviceRate = 0)
    document.getElementById('svcRow')?.style.setProperty('display','none');

    // "Xonaga yozish" to'lov tugmasini ko'rsatish
    const rcBtn = document.getElementById('roomChargeMethod');
    if (rcBtn) {
      rcBtn.style.display = '';
      document.querySelector('.pay-methods').style.gridTemplateColumns = 'repeat(5,1fr)';
    }
  }

  // ── Auto servis-specific: Avtomobil ma'lumotlari tugmasi ──
  if (MODE.isAutoService) {
    const cartMeta = document.querySelector('.cart-meta');
    if (cartMeta && !document.getElementById('carBtn')) {
      const carBtn = document.createElement('button');
      carBtn.id = 'carBtn';
      carBtn.className = 'cust-btn';
      carBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 17H3a2 2 0 01-2-2V9a2 2 0 012-2h1l2-4h10l2 4h1a2 2 0 012 2v6a2 2 0 01-2 2h-2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="7.5" cy="17.5" r="2.5" stroke="currentColor" stroke-width="1.8"/><circle cx="16.5" cy="17.5" r="2.5" stroke="currentColor" stroke-width="1.8"/></svg>'
                       + '<span id="carBtnLabel">Avtomobil ma\'lumotlari</span>';
      cartMeta.insertBefore(carBtn, document.querySelector('.otype-row') || cartMeta.lastElementChild);
      carBtn.addEventListener('click', () => {
        if (state.carInfo) {
          const ep = document.getElementById('carPlate');
          const em = document.getElementById('carMake');
          const emo = document.getElementById('carModel');
          const ey = document.getElementById('carYear');
          if (ep)  ep.value  = state.carInfo.plate || '';
          if (em)  em.value  = state.carInfo.make  || '';
          if (emo) emo.value = state.carInfo.model || '';
          if (ey)  ey.value  = state.carInfo.year  || '';
        }
        openModal('carModal');
      });
    }
  }

  // ── Maktab-specific: O'quvchi tugmasini qo'shish ──
  if (MODE.isSchool) {
    const cartMeta = document.querySelector('.cart-meta');
    if (cartMeta && !document.getElementById('studentBtn')) {
      const studentBtn = document.createElement('button');
      studentBtn.id = 'studentBtn';
      studentBtn.className = 'cust-btn';
      studentBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 14l9-5-9-5-9 5 9 5z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 14l6.16-3.422A12 12 0 0112 21a12 12 0 01-6.16-10.422L12 14z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>'
                           + '<span id="studentBtnLabel">O\'quvchi ma\'lumotlari</span>';
      cartMeta.insertBefore(studentBtn, document.querySelector('.otype-row') || cartMeta.lastElementChild);
      studentBtn.addEventListener('click', () => {
        if (state.studentInfo) {
          const fn = document.getElementById('studentName');
          const fp = document.getElementById('studentPhone');
          const fg = document.getElementById('studentGroup');
          if (fn) fn.value = state.studentInfo.name  || '';
          if (fp) fp.value = state.studentInfo.phone || '';
          if (fg) fg.value = state.studentInfo.group || '';
        }
        openModal('studentModal');
        setTimeout(() => document.getElementById('studentName')?.focus(), 100);
      });
    }
  }

  // ── Kimyoviy tozalash-specific: Buyurtma tugmasini qo'shish ──
  if (MODE.isDryCleaning) {
    const cartMeta = document.querySelector('.cart-meta');
    if (cartMeta && !document.getElementById('cleaningBtn')) {
      const cleaningBtn = document.createElement('button');
      cleaningBtn.id = 'cleaningBtn';
      cleaningBtn.className = 'cust-btn';
      cleaningBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M20.38 3.46L16 2a4 4 0 01-8 0L3.62 3.46a2 2 0 00-1.34 2.23l.58 3.57a1 1 0 00.99.84H7v10a2 2 0 002 2h6a2 2 0 002-2V10h3.15a1 1 0 00.99-.84l.58-3.57a2 2 0 00-1.34-2.23z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
                            + '<span id="cleaningBtnLabel">Buyurtma ma\'lumotlari</span>';
      cartMeta.insertBefore(cleaningBtn, document.querySelector('.otype-row') || cartMeta.lastElementChild);
      cleaningBtn.addEventListener('click', () => {
        if (state.cleaningInfo) {
          const fi = document.getElementById('cleaningItems');
          const fc = document.getElementById('cleaningColor');
          const fn = document.getElementById('cleaningNotes');
          const fp = document.getElementById('cleaningPickupDate');
          if (fi) fi.value = state.cleaningInfo.items       || '';
          if (fc) fc.value = state.cleaningInfo.color       || '';
          if (fn) fn.value = state.cleaningInfo.notes       || '';
          if (fp) fp.value = state.cleaningInfo.pickup_date || '';
        }
        openModal('cleaningModal');
        setTimeout(() => document.getElementById('cleaningItems')?.focus(), 100);
      });
    }
  }

  // ── Dorixona-specific: Retsept tugmasini qo'shish ──
  if (MODE.isPharmacy) {
    const cartMeta = document.querySelector('.cart-meta');
    if (cartMeta && !document.getElementById('rxBtn')) {
      const rxBtn = document.createElement('button');
      rxBtn.id = 'rxBtn';
      rxBtn.className = 'cust-btn';
      rxBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" stroke="currentColor" stroke-width="1.8"/><rect x="9" y="3" width="6" height="4" rx="1" stroke="currentColor" stroke-width="1.8"/><path d="M9 12h6M9 16h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>'
                      + '<span id="rxBtnLabel">Retsept qo\'shish</span>';
      cartMeta.insertBefore(rxBtn, cartMeta.querySelector('.otype-row'));
      rxBtn.addEventListener('click', () => {
        // Mavjud ma'lumotlarni forma ga yuklash
        if (state.rxInfo) {
          const fn = document.getElementById('rxPatientName');
          const fp = document.getElementById('rxPatientPhone');
          const fr = document.getElementById('rxNumber');
          if (fn) fn.value = state.rxInfo.patient_name  || '';
          if (fp) fp.value = state.rxInfo.patient_phone || '';
          if (fr) fr.value = state.rxInfo.rx_number     || '';
        }
        openModal('rxModal');
      });
    }
  }

  // Barkod inputga fokus (faqat store rejimida)
  if (MODE.isStore) setTimeout(() => document.getElementById('barcodeInput')?.focus(), 800);
}

// ─── Data loading ─────────────────────────────────────────────────────────────
async function loadData() {
  document.getElementById('ldBar').style.width = '20%';

  const catsRes = await api.get('/categories/all').catch(() => null);
  const cats = Array.isArray(catsRes?.data) ? catsRes.data : null;
  state.categories = cats ?? await localDB.getAll(STORES.CATEGORIES);
  if (cats) await localDB.saveAll(STORES.CATEGORIES, cats);
  document.getElementById('ldBar').style.width = '45%';

  const prodsRes = await api.get('/products/all').catch(() => null);
  const prods = Array.isArray(prodsRes?.data) ? prodsRes.data : null;
  state.products = prods ?? await localDB.getAll(STORES.PRODUCTS);
  if (prods) await localDB.saveAll(STORES.PRODUCTS, prods);
  document.getElementById('ldBar').style.width = '65%';

  const tblsRes = await api.get('/tables/').catch(() => null);
  const tblsData = tblsRes?.data;
  const tbls = tblsData?.items ?? (Array.isArray(tblsData) ? tblsData : null);
  state.tables = tbls ?? await localDB.getAll(STORES.TABLES);
  if (tbls) await localDB.saveAll(STORES.TABLES, state.tables);
  document.getElementById('ldBar').style.width = '85%';

  const saved = await localDB.getAll(STORES.CART);
  if (saved?.length) state.cart = saved;
  document.getElementById('ldBar').style.width = '100%';
}

// ─── User display ─────────────────────────────────────────────────────────────
// Rol nomini kanonik guruhga keltiradi (admin-guard.js bilan bir xil mantiq)
function canonRole(n = '') {
  n = (n || '').toLowerCase();
  if (n.includes('super') || n.includes('admin'))  return 'admin';
  if (n.includes('manager') || n.includes('menej')) return 'manager';
  if (n.includes('cashier') || n.includes('kassir')) return 'cashier';
  if (n.includes('waiter') || n.includes('ofits'))  return 'waiter';
  if (n.includes('chef') || n.includes('oshpaz') || n.includes('kitchen')) return 'kitchen';
  return n;
}

// Sidebar linklarini rol bo'yicha yashiradi — kassir faqat POS-ga kerakli
// narsalarni ko'radi (admin/ombor/analitika/hisobot linklari umuman chiqmaydi).
function applySidebarRoles(roleName, isSuper) {
  const canon = canonRole(roleName);
  document.querySelectorAll('.sidebar a.nav-item[data-roles]').forEach(a => {
    const allowed = (a.dataset.roles || '').split(/\s+/).filter(Boolean);
    const ok = isSuper
      || allowed.includes('*')
      || allowed.some(r => canon === r || roleName.includes(r));
    a.style.display = ok ? '' : 'none';
  });
}

function renderUser() {
  try {
    const raw  = localStorage.getItem('user') || '{}';
    const user = JSON.parse(raw);
    const name = user.full_name || user.username || 'Foydalanuvchi';
    const roleName = (user.role?.name || user.role || '').toLowerCase();
    const roleMap = { admin:'Admin', cashier:'Kassir', waiter:'Ofitsiant', kitchen:'Oshpaz' };
    document.getElementById('userAvatar').textContent = name[0]?.toUpperCase() || 'U';
    document.getElementById('userName').textContent   = name;
    document.getElementById('userRole').textContent   = roleMap[user.role?.name||user.role] || user.role?.name || 'Kassir';
    applySidebarRoles(roleName, !!user.is_superuser);
  } catch {}
}

// ─── Kassa + smena gate (cash_register flagi) ────────────────────────────────
// JWT features ro'yxatidan flag tekshirish (admin.html dagi hasFeature kabi)
function posHasFeature(flag) {
  try {
    const tok = localStorage.getItem('access_token');
    if (!tok) return false;
    const p = JSON.parse(atob(tok.split('.')[1]));
    return Array.isArray(p.features) && p.features.includes(flag);
  } catch { return false; }
}

function currentUserId() {
  try { return JSON.parse(localStorage.getItem('user') || '{}').id || null; }
  catch { return null; }
}

// Smena majburiy biznesmi? Kassa bor joyda (cash_register YOKI z_report) — food +
// retail + dorixona. Bron bizneslari (salon/fitnes/...) da smena talab qilinmaydi.
function shiftRequired() {
  return posHasFeature('cash_register') || posHasFeature('z_report');
}

// Faol smenani ta'minlaydi. Ochiq smena bo'lsa state.shiftId ni to'ldirib TRUE
// qaytaradi. Bo'lmasa smena ochish gate'ini ko'rsatadi va FALSE qaytaradi (savdo
// bloklanadi). Smena kerak bo'lmagan biznesda darhol TRUE. Kassa (register)
// IXTIYORIY — registrsiz oddiy smena ham ochiladi.
async function ensureShiftGate() {
  if (!shiftRequired()) return true;
  try {
    const _actRes = await api.get('/shifts/active');   // {success,data} — data: null yoki faol smena
    const active  = (_actRes && _actRes.success) ? _actRes.data : null;
    if (active && active.id) {
      state.shiftId = active.id;
      state.registerId = active.register_id || null;
      return true;
    }
    const _regRes = await api.get('/cash-registers/');
    const _regList = (_regRes && _regRes.success && Array.isArray(_regRes.data)) ? _regRes.data : [];
    const regs = _regList.filter(r => r.is_active);

    const sel = document.getElementById('gateRegister');
    const row = document.getElementById('gateRegisterRow');
    if (regs.length) {
      sel.innerHTML = regs.map(r => `<option value="${r.id}">${(r.name||'').replace(/</g,'&lt;')}</option>`).join('');
      if (row) row.style.display = '';
    } else {
      // Kassa yozuvi yo'q — registrsiz smena ochiladi (kassa tanlash yashiriladi).
      sel.innerHTML = '';
      if (row) row.style.display = 'none';
    }
    document.getElementById('gateStartCash').value = '0';
    document.getElementById('gateError').style.display = 'none';
    openModal('openShiftGate');

    const btn = document.getElementById('gateOpenBtn');
    btn.onclick = async () => {
      const regId = regs.length ? (+document.getElementById('gateRegister').value || null) : null;
      const startCash = +document.getElementById('gateStartCash').value || 0;
      const err = document.getElementById('gateError');
      btn.disabled = true; btn.textContent = 'Ochilmoqda...';
      try {
        const sres = await api.post('/shifts/', {
          user_id: currentUserId(), starting_cash: startCash, register_id: regId
        });
        if (!sres || !sres.success || !sres.data || !sres.data.id) {
          throw new Error((sres && sres.error) || 'Smena ochilmadi');
        }
        state.shiftId = sres.data.id;
        state.registerId = regId;
        closeModal('openShiftGate');
        toast('Smena ochildi', 'success');
      } catch (e) {
        err.textContent = e.message || 'Smena ochilmadi';
        err.style.display = '';
      } finally {
        btn.disabled = false; btn.textContent = 'Smenani ochish';
      }
    };
    return false;   // smena hali ochilmadi — savdo bloklanadi
  } catch (e) {
    // Smena holatini aniqlab bo'lmadi (tarmoq) — frontendда bloklamaymiz;
    // backend baribir ochiq smenani talab qiladi (409).
    console.warn('Shift gate skip:', e);
    return true;
  }
}

// ─── Global keyboard-wedge barcode scanner ───────────────────────────────────
// USB barcode scanners (keyboard wedge) send characters rapidly then Enter.
// This captures scans even when barcodeInput is not focused.
(function () {
  let _buf = '', _t0 = 0, _timer = null;
  document.addEventListener('keydown', function (e) {
    // Skip when an input/textarea/select is focused (user is typing)
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    // Function keys and special keys — not barcode chars
    if (e.key.length > 1 && e.key !== 'Enter') { _buf = ''; return; }

    const now = Date.now();
    if (e.key === 'Enter') {
      if (_buf.length >= 4 && (now - _t0) < 600) {
        clearTimeout(_timer);
        const code = _buf; _buf = ''; _t0 = 0;
        e.preventDefault();
        handleBarcodeScan(code);
      } else { _buf = ''; }
      return;
    }
    if (_buf.length === 0) _t0 = now;
    _buf += e.key;
    clearTimeout(_timer);
    // Some scanners don't send Enter — flush after 120ms of silence
    _timer = setTimeout(function () {
      if (_buf.length >= 6) handleBarcodeScan(_buf);
      _buf = ''; _t0 = 0;
    }, 120);
  });
})();

// ─── Elektron tarozi — Web Serial API ────────────────────────────────────────
let _scalePort = null;

async function connectScale() {
  if (!navigator.serial) {
    toast('Web Serial API bu brauzerda qo\'llab-quvvatlanmaydi (Chrome/Edge kerak)', 'warning');
    return;
  }
  try {
    _scalePort = await navigator.serial.requestPort();
    // Umumiy tarozi sozlamalari: 9600 baud, 8N1
    await _scalePort.open({ baudRate: 9600, dataBits: 8, stopBits: 1, parity: 'none' });
    toast('Tarozi ulandi ✓', 'success');
    beep('success');
    _scaleReadLoop();
  } catch (err) {
    if (err.name !== 'AbortError') toast('Tarozi ulanmadi: ' + (err.message || err), 'error');
  }
}

async function _scaleReadLoop() {
  if (!_scalePort?.readable) return;
  const reader = _scalePort.readable.getReader();
  let buf = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += new TextDecoder().decode(value);
      // Majority of scales output: "  1.250 kg\r\n" or "ST,GS,+  1.250kg"
      const m = buf.match(/([+-]?\d+\.?\d*)\s*(kg|g|lb)\b/i);
      if (m) {
        const raw  = parseFloat(m[1]);
        const unit = m[2].toLowerCase();
        const kg   = unit === 'g' ? raw / 1000 : unit === 'lb' ? raw * 0.453592 : raw;
        const inp  = document.getElementById('weightInput');
        if (inp && document.getElementById('weightModal')?.classList.contains('open')) {
          inp.value = kg.toFixed(3);
          inp.dispatchEvent(new Event('input'));
        }
        buf = '';
      }
      if (buf.length > 256) buf = buf.slice(-64);
    }
  } catch {} finally { reader.releaseLock(); }
}

document.getElementById('scaleConnectBtn')?.addEventListener('click', connectScale);

// ─── Init ─────────────────────────────────────────────────────────────────────
async function init() {
  if (!localStorage.getItem('access_token')) {
    location.href = '../shared/login.html'; return;
  }
  try {
    renderUser();
    // localStorage tokenini IndexedDB auth_meta ga sinxronlaymiz (SW background sync uchun)
    const existingToken = localStorage.getItem('access_token');
    if (existingToken) {
      localDB.put(STORES.AUTH_META, { key: 'access_token', value: existingToken }).catch(() => {});
    }
    syncEngine.start();

    // Sync badge yangilash
    async function refreshSyncBadge() {
      const n = await syncEngine.getPendingCount();
      const badge = document.getElementById('syncBadge');
      const pending = document.getElementById('offlinePendingCount');
      if (badge) { badge.classList.toggle('show', n > 0); document.getElementById('syncBadgeText').textContent = `${n} ta kutmoqda`; }
      if (pending) { pending.style.display = n > 0 ? '' : 'none'; pending.textContent = `${n} ta kutmoqda`; }
    }
    syncEngine.on('sync:queued',   refreshSyncBadge);
    syncEngine.on('sync:complete', d => {
      refreshSyncBadge();
      if (d?.synced > 0) toast(`${d.synced} ta buyurtma yuborildi`, 'success');
    });
    syncEngine.on('sync:progress', refreshSyncBadge);
    syncEngine.on('sync:failed',   () => toast('Buyurtma yuborishda xatolik', 'error'));
    refreshSyncBadge();

    await loadData();
    applyBusinessMode();
    renderCategories(state.categories);
    renderProducts();
    renderCart();
    await ensureShiftGate();
    loadPrinterStatus();
    loadReceiptSettings();   // "Shrift o'lchami" — chek print CSS'iga
    loadHeldOrders();   // kutilayotgan buyurtmalar sonini ko'rsatish (badge)
  } catch (e) {
    console.error('POS init error:', e);
  } finally {
    setTimeout(() => {
      document.getElementById('loadingScreen').classList.add('hidden');
      connectWS();
    }, 350);
  }
}

init();

// ─── BOSQICH 20: Tez sotuv paneli ────────────────────────────────────────────
async function loadQuickSellPanel() {
  const panel = document.getElementById('quickSellPanel');
  const btns  = document.getElementById('quickSellButtons');
  if (!panel || !btns) return;
  try {
    const _r = await api.get('/quick-sell/');
    const items = (_r && _r.success && Array.isArray(_r.data)) ? _r.data : [];
    if (!items.length) return;
    panel.style.display = '';
    btns.innerHTML = items.map(item => `<button onclick="quickSellAdd(${item.product_id})" style="background:${item.color};color:#fff;border:none;border-radius:8px;padding:.35rem .7rem;cursor:pointer;font-size:.82rem;font-weight:600;white-space:nowrap">${item.display_name}</button>`).join('');
  } catch {}
}
function quickSellAdd(productId) {
  const product = state.products.find(p => p.id === productId);
  if (product) {
    addToCart(productId);
  } else {
    api.get(`/products/${productId}`).then(res => {
      const p = res && res.data;
      if (p && p.id) { state.products.push(p); addToCart(productId); }
      else toast('Mahsulot topilmadi', 'warning');
    }).catch(() => toast('Mahsulot topilmadi', 'warning'));
  }
}

// ─── BOSQICH 21: Bo'limlar filtri (departments) ───────────────────────────────
async function loadDeptsBar() {
  const bar = document.getElementById('deptsBar');
  const btnsEl = document.getElementById('deptsBarBtns');
  if (!bar || !btnsEl) return;
  try {
    const _r = await api.get('/departments/?is_active=true');
    const depts = (_r && _r.success && Array.isArray(_r.data)) ? _r.data : [];
    if (!depts.length) return;
    bar.style.display = '';
    btnsEl.innerHTML =
      `<button onclick="filterByDept(null)" id="deptBtn_all" style="padding:.3rem .75rem;border-radius:20px;border:1px solid var(--border2);background:var(--gold);color:#07070f;font-size:.78rem;font-weight:700;cursor:pointer;white-space:nowrap;flex-shrink:0">Barchasi</button>` +
      depts.map(d =>
        `<button onclick="filterByDept(${d.id},'${d.color}')" id="deptBtn_${d.id}" style="padding:.3rem .75rem;border-radius:20px;border:1px solid var(--border2);background:var(--bg3);color:var(--text);font-size:.78rem;font-weight:600;cursor:pointer;white-space:nowrap;flex-shrink:0">
          ${d.icon||''}${d.icon?' ':''}${d.name}
        </button>`
      ).join('');
  } catch {}
}

function filterByDept(deptId, color) {
  _activeDeptId = deptId;
  // Button styles
  document.querySelectorAll('#deptsBarBtns button').forEach(b => {
    b.style.background = 'var(--bg3)';
    b.style.color = 'var(--text)';
    b.style.borderColor = 'var(--border2)';
  });
  const activeBtn = deptId ? document.getElementById(`deptBtn_${deptId}`) : document.getElementById('deptBtn_all');
  if (activeBtn) {
    activeBtn.style.background = color || 'var(--gold)';
    activeBtn.style.color = '#fff';
    activeBtn.style.borderColor = 'transparent';
    if (!color) activeBtn.style.color = '#07070f';
  }
  // Kategoriyalarni filtr qil: faqat bu bo'limga tegishli kategoriyalar
  const catsBar = document.getElementById('catsBar');
  if (catsBar) {
    catsBar.querySelectorAll('.cat-btn:not([data-id=""])').forEach(btn => {
      const catId = parseInt(btn.dataset.id);
      const cat = state.categories?.find(c => c.id === catId);
      btn.style.display = (!deptId || cat?.department_id == deptId) ? '' : 'none';
    });
    // "Barchasi" kategoriyasini ko'rsatish
    const allCatBtn = catsBar.querySelector('.cat-btn[data-id=""]');
    if (allCatBtn) allCatBtn.style.display = '';
  }
  // Mahsulotlarni filtr qil
  renderProducts();
}

