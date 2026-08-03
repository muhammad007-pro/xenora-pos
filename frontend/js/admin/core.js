const _lport = window.location.port;
const _isDev = ['5500','5501','3000','4200','8080'].includes(_lport) && ['localhost','127.0.0.1'].includes(window.location.hostname);
const API_BASE = _isDev ? 'http://localhost:8000/api/v1' : ((window.XENORA_SERVER||'')+'/api/v1');
let token    = localStorage.getItem('access_token');
let currentPage = 'dashboard';

if (!token) location.href = '../shared/login.html';

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type='info', dur=3500) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), dur);
}

// ── Format ────────────────────────────────────────────────────────────────────
// fmtMoney — umumiy money.js dan (window.fmtMoney, vergulli). Bu yerda qayta
// aniqlanmaydi: barcha sahifa bir xil formatda bo'lsin (ilgari 'uz-UZ' bo'sh joy edi).
function fmtDate(d)  { return new Date(d).toLocaleString('uz-UZ',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}); }

// ── Auth ──────────────────────────────────────────────────────────────────────
function getUser() { try { return JSON.parse(localStorage.getItem('user')||'{}'); } catch { return {}; } }
const user = getUser();
document.getElementById('sbAvatar').textContent = (user.full_name||'A')[0].toUpperCase();
document.getElementById('sbName').textContent   = user.full_name || user.username || 'Admin';
document.getElementById('sbRole').textContent   = ({admin:'Administrator',menejer:'Menejer',cashier:'Kassir',waiter:'Ofitsiant',kitchen:'Oshpaz'}[user.role?.name||user.role]||user.role?.name||'Admin');
// Sana: tor ekranda (mobil) qisqa "13 iyul", keng ekranda to'liq "Dush, 13-iyul, 2026".
// IIFE — global scope'ga yangi nom qo'shmaydi; resize'da qayta hisoblanadi.
(function(){
  const el = document.getElementById('todayDate');
  if (!el) return;
  const upd = () => { el.textContent = new Date().toLocaleDateString('uz-UZ',
    (window.innerWidth <= 640)
      ? {day:'numeric', month:'short'}
      : {weekday:'short', day:'numeric', month:'long', year:'numeric'}); };
  upd();
  window.addEventListener('resize', upd);
})();
document.getElementById('logoutBtn').addEventListener('click', () => { const _t=localStorage.getItem('theme'); localStorage.clear(); if(_t)localStorage.setItem('theme',_t); try{indexedDB.deleteDatabase('restopos_db');}catch(e){} location.replace('../shared/login.html'); });

// ── Business type ─────────────────────────────────────────────────────────────
function getBizType() {
  try {
    const tkn = localStorage.getItem('access_token');
    if (tkn) { const p = JSON.parse(atob(tkn.split('.')[1])); if (p.business_type) return p.business_type; }
  } catch {}
  return getUser().business_type || 'cafe';
}
const bizType = getBizType();

// ── Field definitions ─────────────────────────────────────────────────────────
// type: text|number|area|sel|cats|check   key: product object field
const FIELD_DEFS = {
  name:        {label:'Nomi *',                     type:'text',   key:'name',                 ph:'Nomi', required:true},
  price:       {label:'Narxi (UZS) *',              type:'number', key:'price',                ph:'0'},
  cost_price:  {label:'Tan narx (UZS)',             type:'number', key:'cost_price',           ph:'0'},
  daily_price: {label:'Kunlik narx (UZS) *',        type:'number', key:'daily_price',          ph:'0'},
  category:    {label:'Kategoriya',                 type:'cats',   key:'category_id'},
  description: {label:'Tavsif',                     type:'area',   key:'description',          ph:'Qisqa tavsif...'},
  sale_unit:   {label:"O'lchov birligi",            type:'sel',    key:'sale_unit',
    opts:[['pcs','Dona'],['kg','Kg'],['g','Gramm'],['l','Litr'],['ml','Ml'],['m','Metr'],['sm','Sm'],['box','Quti'],['pack','Upakovka'],['portion','Porsiya']]},
  barcode:         {label:'Shtrix-kod',               type:'text',   key:'barcode',              ph:'Barcode / SKU', mono:true},
  wholesale_price: {label:"Ko'tara narx (UZS)",      type:'number', key:'wholesale_price',      ph:"0 (bo'sh = yo'q)"},
  wholesale_min:   {label:"Ko'tara min. miqdor",     type:'number', key:'wholesale_min_qty',    ph:'10'},
  expiry_days: {label:'Yaroqlilik (kun)',            type:'number', key:'expiry_days',          ph:'365'},
  batch:       {label:'Partiya raqami',             type:'text',   key:'batch_number',         ph:'LOT-001'},
  prescription:{label:'Retsept talab etiladi',      type:'check',  key:'requires_prescription'},
  dosage:      {label:'Dozaj',                      type:'text',   key:'dosage',               ph:'500mg'},
  drug_form:   {label:'Shakli',                     type:'sel',    key:'drug_form',
    opts:[['tablet','Tabletka'],['capsule','Kapsula'],['syrup','Sirop'],['ampule','Ampula'],['injection','Inyeksiya'],['cream','Krem'],['drops','Tomchi'],['powder','Kukun'],['spray','Sprey'],['suppository','Sham'],['other','Boshqa']]},
  dosing_schedule:{label:'Qabul tartibi',           type:'text',   key:'dosing_schedule',      ph:'Kuniga 3 mahal, ovqatdan keyin'},
  active_ingredient:{label:'Faol modda (ta\'sir etuvchi modda)', type:'text', key:'active_ingredient', ph:'Amoxicillin'},
  dur_min:     {label:'Davomiylik (daqiqa)',         type:'number', key:'duration_minutes',     ph:'60'},
  dur_h:       {label:'Davomiylik (soat)',           type:'number', key:'duration_hours',       ph:'2'},
  dur_days:    {label:'Muddat (kun)',                type:'number', key:'duration_days',        ph:'30'},
  dur_weeks:   {label:'Muddat (hafta)',              type:'number', key:'duration_weeks',       ph:'12'},
  lesson_count:{label:'Dars soni',                  type:'number', key:'lesson_count',         ph:'24'},
  visit_limit: {label:'Tashrif limiti (0=cheksiz)', type:'number', key:'visit_limit',          ph:'0'},
  master:      {label:'Usta / Mutaxassis',          type:'text',   key:'master',               ph:'F.I.Sh.'},
  commission_pct:{label:'Komissiya (%)',            type:'number', key:'commission_pct',       ph:'0'},
  cloth_type:  {label:'Kiyim turi',                 type:'sel',    key:'clothing_type',
    opts:[['suit','Kostyum'],['dress',"Ko'ylak/Libos"],['jacket',"Kurtka/Palto"],['carpet','Gilam'],['blanket',"Ko'rpa/Yostiq"],['curtain','Parda'],['other','Boshqa']]},
  capacity:    {label:"Sig'im (kishi)",             type:'number', key:'capacity',             ph:'2'},
  room_type:   {label:'Xona turi',                  type:'sel',    key:'room_type',
    opts:[['single','Yagona (1 kishi)'],['double','Juft (2 kishi)'],['suite',"Lyuks"],['family','Oilaviy'],['dormitory','Yotoqxona']]},
  floor:       {label:'Qavat',                      type:'number', key:'floor',                ph:'1'},
  available:   {label:'Sotuvda mavjud',             type:'check',  key:'is_available',         def:true},
  station:     {label:'Stansiya (oshxona/mangal/bar)', type:'station', key:'station_id'},
  department:  {label:"Bo'lim (seksiya)",            type:'dept',   key:'department_id'},
};

// ── Form config per business type ─────────────────────────────────────────────
// fields: string | [f1, f2] (side-by-side pair)
const FORM_CONFIGS = {
  restaurant:   {title:"Taom qo'shish",         fields:['name',['price','cost_price'],'sale_unit','category','station','description','available']},
  cafe:         {title:"Mahsulot qo'shish",      fields:['name',['price','cost_price'],'sale_unit','category','station','description','available']},
  fast_food:    {title:"Mahsulot qo'shish",      fields:['name',['price','cost_price'],'sale_unit','category','station','available']},
  store:        {title:"Mahsulot qo'shish",      fields:['name',['price','cost_price'],'sale_unit','category','barcode','available']},
  supermarket:  {title:"Mahsulot qo'shish",      fields:['name',['price','cost_price'],'sale_unit',['department','category'],'barcode',['wholesale_price','wholesale_min'],['expiry_days','batch'],'available']},
  pharmacy:     {title:"Dori qo'shish",          fields:['name',['price','cost_price'],'sale_unit','category','barcode','active_ingredient',['dosage','drug_form'],'dosing_schedule',['batch','expiry_days'],'prescription','available']},
  salon:        {title:"Xizmat qo'shish",        fields:['name',['price','commission_pct'],['dur_min','cost_price'],'category','description','available'],
                 alt:{type:'membership',          title:"Abonement qo'shish", fields:['name',['price','dur_days'],'visit_limit']}},
  fitness:      {title:"Xizmat qo'shish",        fields:['name',['price','dur_min'],'category','available'],
                 alt:{type:'membership',          title:"Abonement qo'shish", fields:['name',['price','dur_days'],'visit_limit']}},
  auto_service: {title:"Xizmat qo'shish",        fields:['name',['price','dur_min'],'category','available'],
                 alt:{type:'spare_part',          title:"Ehtiyot qism qo'shish", fields:['name',['price','sale_unit'],'category','barcode','available']}},
  school:       {title:"Kurs qo'shish",          fields:['name',['price','lesson_count'],'category',['dur_weeks','available']]},
  dry_cleaning: {title:"Xizmat qo'shish",        fields:['name',['price','dur_h'],'category','cloth_type','available']},
  hotel:        {title:"Xona turi qo'shish",     fields:['name',['daily_price','capacity'],['room_type','floor'],'available']},
};

// ── Navigation ────────────────────────────────────────────────────────────────
const _prodTitle = (FORM_CONFIGS[bizType] || FORM_CONFIGS.cafe).title;
const pageTitles = { dashboard:'Dashboard', orders:'Buyurtmalar', products:'Mahsulotlar', categories:'Kategoriyalar', specials:'Kunlik maxsus', waiters:'Ofitsiantlar reytingi', reservCalendar:'Bron Kalendar', loyaltyTiers:'Sodiqlik darajalari', topDishes:'Top taomlar', waiterShift:'Smena hisoboti', kitchenStats:'Oshxona vaqti statistikasi', stopList:'Stop-list', staffMeal:'Xodimlar ovqati', modifiers:'Modifikatorlar', stations:'Stansiyalar', storeTop:'Top mahsulotlar', storeMargin:'Foyda marjasi', storeCats:'Kategoriya tahlili', storeCashier:'Kassir hisoboti', storePriceList:"Narx ro'yxati", storeDiscounts:'Chegirmalar', debtList:'Nasiya / Qarz Daftar', promotionsList:'Aksiyalar', quickSellList:'Tez Sotuv Paneli', registersList:'Kassalar', cashRegisterList:'Kassa Smena', receiptSettingsPage:'Chek Sozlamalari', departmentsList:"Bo'limlar (Seksiyalar)", pharmStats:'Retsept statistika', pharmPatients:'Bemorlar', pharmTopMeds:'Top dorilar', pharmExpiry:'Yaroqlilik muddati', pharmCats:'Kategoriya tahlili', pharmCashier:'Kassir hisoboti', prescriptions:'Retseptlar jurnali', memberships:'Abonementlar', masters:'Ustalar reytingi', salonSchedule:'Usta ish grafigi', salonServices:'Xizmat tahlili', salonPeakHours:'Band soatlar', salonExpiring:'Tugayotgan abonementlar', salonClients:'Mijoz tahlili', salonMasterReport:'Usta daromad hisoboti', serviceOrders:'Xizmat buyurtmalari', autoStats:'Auto statistika', autoReady:'Tayyor buyurtmalar', autoDebt:'Qarzlar', autoDuration:'Xizmat vaqti', autoBrands:'Avtomobil markalari', autoClients:'Mijoz tarixi', students:"O'quvchilar jurnali", groups:'Guruhlar statistikasi', schoolStats:'Daromad statistikasi', schoolTopStudents:"O'quvchi reytingi", schoolGroupDetail:'Guruh tafsiloti', schoolPayments:"To'lov tahlili", schoolMonthly:'Oylik hisobot', schoolTopCourses:'Top kurslar', cleaning:'Kimyoviy tozalash jurnali', dryStats:'Statistika', dryReady:'Tayyor buyurtmalar', dryServices:'Xizmat tahlili', dryClients:'Mijoz tarixi', dryWorkload:'Kunlik ish yuki', dryPayments:"To'lov tahlili", hotelRooms:'Xonalar holati', hotelBookings:'Bronlar', hotelStats:'Statistika', hotelOccupancy:'Xona dolzarbligi', hotelGuests:'Mehmon tarixi', hotelDebt:'Qarzlar', hotelArrivals:'Bugungi kelish/ketish', hotelRoomRevenue:'Xona tushumi', customers:'Mijozlar', shifts:'Smenalar', inventory:'Ombor', suppliers:'Firmalar', staff:'Xodimlar', settings:'Sozlamalar', stockIn:'Kirim tarixi', stockOut:"Chiqim / Hisobdan o'chirish", invCount:'Inventarizatsiya', invReport:'Ombor hisoboti',
  storeDashboard:'Magazin Dashboard', abcAnalysis:'ABC Tahlil', reorderAlerts:'Avto-Zakaz / Kam Qoldiq', turnoverAnalysis:'Oborot Tahlili', peakHours:'Peak Soatlar va Kunlar', salesHistory:'Sotuvlar tarixi', reportsHub:'Hisobotlar', auditLog:'Xodimlar faoliyati' };
const addLabels  = { products:_prodTitle, categories:"Kategoriya qo'shish", specials:"Maxsus taom qo'shish", inventory:"Kirim qilish", customers:"Mijoz qo'shish", staff:"Xodim qo'shish", stations:"Stansiya qo'shish", stockOut:"Hisobdan o'chirish" };

// JWT dan features ro'yxatini olish
function getFeatures() {
  try {
    const tkn = localStorage.getItem('access_token');
    if (tkn) { const p = JSON.parse(atob(tkn.split('.')[1])); if (Array.isArray(p.features)) return p.features; }
  } catch {}
  return [];
}
const _features = getFeatures();
function hasFeature(f) { return _features.includes(f) || _features.length === 0; }

// ── Nav itemlarni ko'rsatish (biznes turi + feature flag bo'yicha) ───────────
// Element nav-feature-XXX classiga ega bo'lsa — faqat shu feature JWT da yoqilgan
// bo'lsagina ko'rinadi. Aks holda (flag o'chiq) — yashirin qoladi.
function showNavGroup(selector) {
  document.querySelectorAll(selector).forEach(el => {
    const fClass = [...el.classList].find(c => c.startsWith('nav-feature-'));
    if (!fClass || hasFeature(fClass.replace('nav-feature-', ''))) {
      el.style.display = '';
    }
  });
}

const _restTypes     = ['restaurant','cafe','fast_food'];
const _storeTypes    = ['store','supermarket'];
const _salonTypes    = ['salon','beauty','fitness'];
const _autoTypes     = ['auto_service'];
const _schoolTypes   = ['school'];
const _dryTypes      = ['dry_cleaning'];
const _hotelBizTypes = ['hotel'];

// Restoran/kafe nav itemlari
if (_restTypes.includes(bizType))        showNavGroup('.nav-restaurant');
// QR-menyu faqat restoran va kafe uchun
if (['restaurant','cafe'].includes(bizType)) showNavGroup('.nav-qr-menu');
// Magazin/supermarket nav itemlari (nav-feature-XXX endi hurmat qilinadi)
if (_storeTypes.includes(bizType))       showNavGroup('.nav-store');
// Dorixona
if (bizType === 'pharmacy')              showNavGroup('.nav-pharmacy');
// Mehmonxona
if (bizType === 'hotel')                 showNavGroup('.nav-hotel');
// Kimyoviy tozalash
if (bizType === 'dry_cleaning')          showNavGroup('.nav-dry');
// Maktab/Kurs
if (bizType === 'school')                showNavGroup('.nav-school');
// Auto servis
if (bizType === 'auto_service')          showNavGroup('.nav-auto');
// Salon/Fitnes
if (_salonTypes.includes(bizType))       showNavGroup('.nav-salon');

// Hisobotlar HUB (reportsHub) — biznes turига qarab mos hisobot guruhini ko'rsat
// (store→store kartalar, restoran oilasi→restoran kartalar). Hisobot sahifalari tegilmagan.
(function(){
  const showStore = _storeTypes.includes(bizType);
  const showRest  = _restTypes.includes(bizType);
  document.querySelectorAll('[data-hub-group="store"]').forEach(el => el.style.display = showStore ? '' : 'none');
  document.querySelectorAll('[data-hub-group="restaurant"]').forEach(el => el.style.display = showRest ? '' : 'none');
})();
// Hub kartalarini feature bo'yicha gating: nav-feature-XXX klassли karta faqat o'sha
// feature yoniq bo'lsa ko'rinadi (asosiy kartalar — feature klasssiz — har doim).
// Sidebar bilan AYNI mexanizm. Yashirin kartada grid auto-fit tekis qoladi.
showNavGroup('.report-hub-card');

// "Buyurtmalar" (orders) — aktiv buyurtma oqimi FAQAT ovqatlanish (food) oilasida
// mantiqli. Food bo'lmasa (magazin, dorixona, salon, fitnes, auto, maktab, mehmonxona,
// kimyoviy tozalash) orders navini + dashboard "Oxirgi buyurtmalar" blokini yashiramiz.
// Sotuvlar salesHistory (Sotuvlar tarixi)'da ko'rinadi (u barcha biznesда qoladi).
if (!_restTypes.includes(bizType)) {
  document.querySelector('.nav-item[data-page="orders"]')?.style.setProperty('display', 'none');
  document.getElementById('dashRecentOrders')?.style.setProperty('display', 'none');
}

document.querySelectorAll('.nav-item[data-page]').forEach(item => {
  item.addEventListener('click', () => switchPage(item.dataset.page));
});
document.querySelectorAll('[data-page]').forEach(el => {
  if (el.tagName === 'A') el.addEventListener('click', e => { e.preventDefault(); switchPage(el.dataset.page); });
});

function switchPage(page) {
  currentPage = page;
  document.querySelectorAll('.admin-page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const pageEl = document.getElementById('page' + page.charAt(0).toUpperCase() + page.slice(1));
  if (pageEl) pageEl.classList.add('active');
  // BOSQICH 16: Firmalar iframe — lazy-load (faqat birinchi kirilganda src o'rnatiladi;
  // ?embed=1 → suppliers.html "← Admin panel" havolasini yashiradi)
  if (page === 'suppliers') {
    const fr = document.getElementById('suppliersFrame');
    if (fr && !fr.getAttribute('src')) fr.src = 'suppliers.html?embed=1';
  }
  document.querySelectorAll(`.nav-item[data-page="${page}"]`).forEach(n => n.classList.add('active'));
  document.getElementById('pageTitle').textContent   = pageTitles[page] || page;
  document.getElementById('addBtnLabel').textContent = addLabels[page] || 'Qo\'shish';
  document.getElementById('addBtn').style.display    = addLabels[page] ? '' : 'none';
  loadPageData(page);
  if (typeof initStatCountUp === 'function') initStatCountUp();  // yangi sahifa stat raqamlariga count-up ulash
}

document.getElementById('refreshBtn').addEventListener('click', () => loadPageData(currentPage));

// Auto-refresh: oyna/tab yana faollashsa (POS'da savdo qilib qaytganда) dashboard
// KPI + "Sotuv dinamikasi" grafigi avtomatik yangilanadi — qo'lda F5 shart emas.
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && currentPage === 'dashboard' && typeof loadDashboard === 'function') loadDashboard();
});

// ── Modal ochish/yopish (modal-overlay tizimi) ───────────────────────────────
// debtModal, payDebtModal, promoModal, quickSellModal, poModal, shiftOpenModal...
// Bu modallar hech qaysi admin-page ichida emas — faqat .open class bilan ko'rinadi.
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('open');
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}
// Esc tugmasi bilan ochiq modalni yopish
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
});

// ── Dark/Light mode toggle ────────────────────────────────────────────────────
(function() {
  const html = document.documentElement;
  const stored = localStorage.getItem('theme') || 'dark';
  html.setAttribute('data-theme', stored);

  function applyAdminTheme(t) {
    html.setAttribute('data-theme', t);
    localStorage.setItem('theme', t);
    const sun  = document.getElementById('themeIconSun');
    const moon = document.getElementById('themeIconMoon');
    if (sun)  sun.style.display  = t === 'light' ? '' : 'none';
    if (moon) moon.style.display = t === 'dark'  ? '' : 'none';
  }
  applyAdminTheme(stored);

  document.getElementById('themeToggleBtn')?.addEventListener('click', () => {
    const cur = html.getAttribute('data-theme') || 'dark';
    applyAdminTheme(cur === 'dark' ? 'light' : 'dark');
  });
})();

// ── API helper ────────────────────────────────────────────────────────────────
async function apiFetch(path) {
  const res = await fetch(API_BASE + path, { headers:{'Authorization':'Bearer '+token} });
  if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||res.statusText); }
  return res.json();
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const [analytics, orders, trends] = await Promise.all([
      apiFetch('/analytics/summary?period=today').catch(() => null),
      apiFetch('/orders/?limit=8&page=1').catch(() => null),
      // o'sish % (trend) — alohida endpoint, mavjud raqam to'ldirishga TEGMAYDI
      apiFetch('/analytics/dashboard?range=today').catch(() => null),
    ]);
    if (trends) {
      setKpiTrend('kpiRevTrend',  trends.revenue_trend,   'kecha');
      setKpiTrend('kpiOrdTrend',  trends.orders_trend,    'kecha');
      setKpiTrend('kpiCustTrend', trends.customers_trend, 'kecha');
      setKpiTrend('kpiAvgTrend',  trends.avg_check_trend, 'kecha');
    }
    // Sof foyda — MAXFIY: backend faqat view_finance bo'lsa net_profit qaytaradi.
    // null/yo'q bo'lsa karta yashirin qoladi (kassir ko'rmaydi).
    const npCard = document.getElementById('kpiNetProfitCard');
    if (npCard) {
      if (trends && trends.net_profit != null) {
        document.getElementById('kpiNetProfit').textContent = fmtMoney(trends.net_profit);
        setKpiTrend('kpiProfitTrend', trends.profit_trend, 'kecha');
        npCard.style.display = '';
      } else {
        npCard.style.display = 'none';
      }
    }
    renderMonthlyGoal(trends);
    if (analytics) {
      document.getElementById('kpiRevenue').textContent   = fmtMoney(analytics.total_revenue||0);
      document.getElementById('kpiOrders').textContent    = analytics.total_orders||0;
      document.getElementById('kpiCustomers').textContent = analytics.total_customers||0;
      document.getElementById('kpiAvgOrder').textContent  = fmtMoney(analytics.avg_order||0);
      if (analytics.by_payment_method) {
        let cash=0,card=0,online=0,total=0;
        analytics.by_payment_method.forEach(m => {
          total += m.amount||0;
          if (m.method==='cash') cash=m.amount||0;
          else if (m.method==='card') card=m.amount||0;
          else online += m.amount||0;
        });
        document.getElementById('donutTotal').textContent = analytics.total_orders||0;
        document.getElementById('lgCash').textContent   = fmtMoney(cash);
        document.getElementById('lgCard').textContent   = fmtMoney(card);
        document.getElementById('lgOnline').textContent = fmtMoney(online);
      }
    }
    if (orders) renderRecentOrders(orders.items||orders||[]);
    renderBarChart(analytics?.daily_revenue || []);
  } catch (err) { toast('Dashboard yuklanmadi: '+err.message, 'error'); }
}

// KPI o'sish ko'rsatkichi: ▲ yashil (musbat), ▼ qizil (manfiy), → neytral (0).
// Faqat trend spanini to'ldiradi — qiymat/count-up'ga tegmaydi.
function setKpiTrend(id, pct, label){
  const el = document.getElementById(id);
  if (!el) return;
  const v = Number(pct);
  if (!isFinite(v)) { el.textContent = ''; el.className = 'kpi-trend'; return; }
  const flat = v === 0, up = v > 0;
  el.className = 'kpi-trend ' + (flat ? 'trend-flat' : up ? 'trend-up' : 'trend-down');
  const arrow = flat ? '→' : up ? '▲' : '▼';
  el.textContent = `${arrow} ${Math.abs(v)}% ${label}`;
}

// ── Oylik maqsad (progress ring) ────────────────────────────────────────────────
// MAXFIY: backend faqat view_finance bo'lsa monthly_goal_target qaytaradi (aks holda null).
//  null   → karta yashirin (kassir ko'rmaydi)
//  0      → maqsad belgilanmagan (egasiga "Belgilash" taklifi)
//  >0     → progress ring
function renderMonthlyGoal(trends){
  const card  = document.getElementById('monthlyGoalCard');
  const empty = document.getElementById('monthlyGoalEmpty');
  if (!card || !empty) return;
  const t = trends && trends.monthly_goal_target;
  if (t == null) { card.style.display = 'none'; empty.style.display = 'none'; return; }
  if (t > 0) {
    empty.style.display = 'none';
    const pct = Math.max(0, Number(trends.goal_pct) || 0);
    const shown = Math.round(pct);
    document.getElementById('goalPctText').textContent  = shown;
    document.getElementById('goalRemaining').textContent = fmtMoney(trends.goal_remaining || 0) + ' UZS';
    document.getElementById('goalDaysLeft').textContent  = trends.days_left != null ? trends.days_left : '—';
    // ring to'lish (foiz 100% bilan cheklanadi; C = 2πr, r=52)
    const C = 326.726, fill = document.getElementById('goalRingFill');
    const off = C * (1 - Math.min(pct, 100) / 100);
    const apply = () => { fill.style.strokeDashoffset = off; };
    if (window.matchMedia && matchMedia('(prefers-reduced-motion:reduce)').matches) apply();
    else requestAnimationFrame(() => requestAnimationFrame(apply));
    // markazdagi foiz — count-up (mavjud daCountUp observer 'goalPct' ni kuzatadi)
    document.getElementById('goalPct').textContent = shown;
    card.style.display = '';
  } else {
    card.style.display = 'none';
    empty.style.display = '';
  }
}

// Sozlama: egasi oylik maqsadni o'qiydi/saqlaydi (view_finance kerak — yo'q bo'lsa 403 → blok yashirin)
async function loadMonthlyGoalSetting(){
  const wrap = document.getElementById('monthlyGoalSetWrap');
  if (!wrap) return;
  try {
    const d = await apiFetch('/settings/monthly-goal');
    const inp = document.getElementById('monthlyGoalInput');
    if (inp) inp.value = d && d.target ? d.target : '';
    wrap.style.display = '';
  } catch (e) {
    wrap.style.display = 'none';   // view_finance yo'q (403) → yashirin
  }
}
async function saveMonthlyGoal(){
  const inp = document.getElementById('monthlyGoalInput');
  const msg = document.getElementById('monthlyGoalMsg');
  const target = parseFloat(inp.value) || 0;
  if (target < 0) { if (msg) msg.textContent = 'Manfiy bo\'lmasin'; return; }
  try {
    await apiFetchPost('/settings/monthly-goal', { target }, 'PATCH');
    if (msg) { msg.style.color = 'var(--success)'; msg.textContent = '✓ Saqlandi'; setTimeout(()=>msg.textContent='', 2500); }
    if (currentPage === 'dashboard') loadDashboard();
  } catch (e) {
    if (msg) { msg.style.color = 'var(--danger)'; msg.textContent = 'Xato: ' + e.message; }
  }
}

// ── Xodimlar faoliyati (audit log) ──────────────────────────────────────────
let auditPage = 1;
let _auditStaffLoaded = false;
function _aesc(s){ return String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
async function loadAuditLog(){
  const body = document.getElementById('auditBody');
  if (!body) return;
  if (!_auditStaffLoaded){
    try{
      const staff = await apiFetch('/audit-logs/staff');
      const sel = document.getElementById('auditUserFilter');
      sel.innerHTML = '<option value="">Barcha xodimlar</option>' + (staff||[]).map(s=>`<option value="${s.id}">${_aesc(s.name)}</option>`).join('');
      _auditStaffLoaded = true;
    }catch{}
  }
  body.innerHTML = Array.from({length:6}).map(()=>`<tr class="sk-row"><td><span class="sk-line" style="width:60%"></span></td><td><span class="sk-line" style="width:64px;height:18px;border-radius:99px"></span></td><td><span class="sk-line" style="width:80%"></span></td><td><span class="sk-line" style="width:90px;margin-left:auto"></span></td></tr>`).join('');
  const u  = document.getElementById('auditUserFilter').value;
  const a  = document.getElementById('auditActionFilter').value;
  const df = document.getElementById('auditDateFrom').value;
  const dt = document.getElementById('auditDateTo').value;
  let qs = `?page=${auditPage}&page_size=50`;
  if (u)  qs += `&user_id=${u}`;
  if (a)  qs += `&action=${a}`;
  if (df) qs += `&date_from=${df}T00:00:00`;
  if (dt) qs += `&date_to=${dt}T23:59:59`;
  try{
    const d = await apiFetch('/audit-logs'+qs);
    if (!d.items.length){
      body.innerHTML = `<tr><td colspan="4" class="audit-empty"><div class="ae-ico">👁</div><div class="ae-title">Faoliyat topilmadi</div><div class="ae-hint">Xodimlar harakatlari (buyurtma, qaytarish, narx...) shu yerда ko'rinadi</div></td></tr>`;
      document.getElementById('auditPager').style.display='none';
      return;
    }
    body.innerHTML = d.items.map(it=>{
      const ai = auditAction(it.action);
      return `<tr>
        <td class="td-bold">${_aesc(it.user_name||'—')}</td>
        <td><span class="audit-badge ${ai.cls}">${ai.label}</span></td>
        <td>${auditText(it)}</td>
        <td class="td-sub" style="text-align:right;white-space:nowrap" title="${_aesc(it.created_at||'')}">${auditTime(it.created_at)}</td>
      </tr>`;
    }).join('');
    const pages = Math.max(1, Math.ceil(d.total / d.page_size));
    const pg = document.getElementById('auditPager');
    pg.style.display = pages>1 ? '' : 'none';
    document.getElementById('auditPageInfo').textContent = `${d.total} ta yozuv · ${auditPage}/${pages}`;
    document.getElementById('auditPrev').disabled = auditPage<=1;
    document.getElementById('auditNext').disabled = auditPage>=pages;
  }catch(e){
    body.innerHTML = `<tr><td colspan="4" class="audit-empty"><div class="ae-title">Xatolik: ${_aesc(e.message)}</div></td></tr>`;
  }
}
function auditAction(a){
  return ({
    CREATE:{label:'Yaratdi',  cls:'aa-create'},
    UPDATE:{label:"O'zgartirdi",cls:'aa-update'},
    DELETE:{label:"O'chirdi/Bekor",cls:'aa-delete'},
    RETURN:{label:'Qaytardi', cls:'aa-return'},
    LOGIN: {label:'Kirdi',    cls:'aa-login'},
  })[a] || {label:_aesc(a), cls:'aa-login'};
}
function auditTime(iso){
  if(!iso) return '—';
  const d = new Date(iso), diff=(Date.now()-d.getTime())/1000;
  if(diff<60)    return 'hozir';
  if(diff<3600)  return Math.floor(diff/60)+' daq oldin';
  if(diff<86400) return Math.floor(diff/3600)+' soat oldin';
  return d.toLocaleString('uz-UZ',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
}
function auditText(it){
  const d = it.detail||{};
  const m = n => (n!=null ? Number(n).toLocaleString('uz-UZ')+" so'm" : '');
  if(it.resource==='orders'){
    const num = _aesc(d.order_number||it.resource_id);
    if(it.action==='CREATE') return `Buyurtma #${num} qabul qildi${d.total!=null?' — '+m(d.total):''}${d.table?' (stol '+_aesc(d.table)+')':''}`;
    if(it.action==='DELETE') return `Buyurtma #${num} ni <b>bekor qildi</b>${d.total!=null?' — '+m(d.total):''}${d.reason?', sabab: '+_aesc(d.reason):''}`;
  }
  if(it.resource==='products'){
    if(it.action==='UPDATE'){
      let t = `Mahsulot "${_aesc(d.name||it.resource_id)}" o'zgartirdi`;
      if(d.price_old!=d.price_new) t += ` — narx <b>${m(d.price_old)} → ${m(d.price_new)}</b>`;
      return t;
    }
    if(it.action==='DELETE') return `Mahsulot "${_aesc(d.name||it.resource_id)}" o'chirdi`;
  }
  if(it.resource==='returns') return `Qaytarish ${_aesc(d.return_number||'')} — ${m(d.total_amount)}${d.reason?', '+_aesc(d.reason):''}`;
  if(it.resource==='shifts'){
    if(it.action==='CREATE') return `Smena ochdi${d.starting_cash!=null?" (boshlang'ich "+m(d.starting_cash)+')':''}`;
    return `Smenani yopdi${d.total_sales!=null?' — savdo '+m(d.total_sales):''}${d.shortage?', farq '+m(d.shortage):''}`;
  }
  if(it.resource==='auth') return `Tizimga kirdi${d.username?' ('+_aesc(d.username)+')':''}`;
  return _aesc(JSON.stringify(d));
}

function renderRecentOrders(orders) {
  const body = document.getElementById('recentOrdersBody');
  if (!orders.length) { body.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:var(--text3)">Buyurtmalar yo\'q</td></tr>'; return; }
  const statusMap = {
    pending:   ['Kutmoqda','badge-blue'],
    confirmed: ['Tasdiqlangan','badge-blue'],
    preparing: ['Tayyorlanmoqda','badge-amber'],
    ready:     ['Tayyor','badge-green'],
    completed: ['Bajarildi','badge-green'],
    cancelled: ['Bekor','badge-red'],
  };
  body.innerHTML = orders.slice(0,8).map(o => {
    const [sLbl, sCls] = statusMap[o.status]||['—','badge-gray'];
    return `<tr>
      <td class="td-bold">#${o.order_number||o.id}</td>
      <td class="td-sub">${fmtDate(o.created_at)}</td>
      <td>${o.table_number ? 'Stol '+o.table_number : o.order_type||'—'}</td>
      <td>${o.items_count||''} ta</td>
      <td class="td-gold">${fmtMoney(o.final_amount)} UZS</td>
      <td><span class="badge ${sCls}">${sLbl}</span></td>
      <td>${o.payment_method||'—'}</td>
    </tr>`;
  }).join('');
}

// ── Sotuv dinamikasi — silliq AREA grafik (toza SVG, kutubxonasiz, Electron file:// da ishlaydi) ──
// Ma'lumot: [{date, revenue}]. Endpoint TEGILMAYDI — faqat render.
// Qiymatni "chiroyli" qadamga yaxlitlaydi (1/2/2.5/5 × 10^k) — aniq Y yorliqlar uchun
function _niceStep(x) {
  if (x <= 0) return 1;
  const exp = Math.floor(Math.log10(x));
  const base = Math.pow(10, exp);
  const f = x / base;
  const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
  return nice * base;
}
function _shortMoney(v) {
  if (v >= 1e9) return (v / 1e9).toFixed(v % 1e9 === 0 ? 0 : 1) + 'B';
  if (v >= 1e6) return (v / 1e6).toFixed(v % 1e6 === 0 ? 0 : 1) + 'M';
  if (v >= 1e3) return Math.round(v / 1e3) + 'K';
  return String(Math.round(v));
}
// Catmull-Rom → kubik bezier (silliq egri chiziq)
function _smoothPath(pts) {
  if (!pts.length) return '';
  if (pts.length === 1) return `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
    const t = 0.16;
    const c1x = p1[0] + (p2[0] - p0[0]) * t, c1y = p1[1] + (p2[1] - p0[1]) * t;
    const c2x = p2[0] - (p3[0] - p1[0]) * t, c2y = p2[1] - (p3[1] - p1[1]) * t;
    d += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

function renderBarChart(daily) {
  const chart = document.getElementById('revenueChart');
  if (!chart) return;
  const data = (daily || []).map(d => ({ date: d.date, val: +d.revenue || 0 }));

  // Bo'sh yoki hammasi 0 → "Ma'lumot yo'q" (crash emas)
  if (!data.length || !data.some(d => d.val > 0)) {
    chart.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:200px;color:var(--text3);gap:.5rem">
      <svg width="34" height="34" viewBox="0 0 24 24" fill="none"><path d="M3 3v18h18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M7 14l3-3 3 3 4-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity=".5"/></svg>
      <span style="font-size:.85rem">Ma'lumot yo'q</span></div>`;
    return;
  }

  const W = 600, H = 220, padL = 52, padR = 12, padT = 16, padB = 26;
  const iw = W - padL - padR, ih = H - padT - padB;
  const n = data.length;
  // Avtomatik masshtab: chiroyli qadam (step) → aniq yorliqlar (0, 1M, 2M, 3M, 4M)
  const rawMax  = Math.max(...data.map(d => d.val), 1);
  const step    = _niceStep(rawMax / 4);
  const niceMax = Math.max(step, Math.ceil(rawMax / step) * step);
  const nTicks  = Math.round(niceMax / step);
  const X = i => padL + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
  const Y = v => padT + ih - (v / niceMax) * ih;
  const pts = data.map((d, i) => [X(i), Y(d.val)]);

  const linePath = _smoothPath(pts);
  const areaPath = `${linePath} L${X(n - 1).toFixed(1)},${(padT + ih).toFixed(1)} L${X(0).toFixed(1)},${(padT + ih).toFixed(1)} Z`;

  // Y gridlar + yorliqlar
  let grid = '', ylabels = '';
  for (let t = 0; t <= nTicks; t++) {
    const v = step * t, gy = Y(v).toFixed(1);
    grid += `<line x1="${padL}" y1="${gy}" x2="${W - padR}" y2="${gy}" stroke="currentColor" stroke-width="0.5" opacity="0.12"/>`;
    ylabels += `<text x="${padL - 8}" y="${(+gy + 3).toFixed(1)}" text-anchor="end" font-size="9" fill="currentColor" opacity="0.55">${_shortMoney(v)}</text>`;
  }

  // X yorliqlar (sana kuni) — ko'p bo'lsa siyraklashtirish
  const xStep = n > 10 ? Math.ceil(n / 6) : 1;
  let xlabels = '';
  data.forEach((d, i) => {
    if (i % xStep !== 0 && i !== n - 1) return;
    xlabels += `<text x="${X(i).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="9" fill="currentColor" opacity="0.55">${new Date(d.date).getDate()}</text>`;
  });

  // Oxirgi nuqta (yoki yagona nuqta) belgilanadi
  let dots = '';
  pts.forEach(([px, py], i) => {
    if (n === 1 || i === n - 1) dots += `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="3.5" fill="#22c55e" stroke="var(--bg2)" stroke-width="1.5"/>`;
  });

  chart.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block;height:auto;color:var(--text)" xmlns="http://www.w3.org/2000/svg">
    <defs><linearGradient id="revArea" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#22c55e" stop-opacity="0.32"/>
      <stop offset="1" stop-color="#22c55e" stop-opacity="0.02"/>
    </linearGradient></defs>
    <g>${grid}</g>
    <path d="${areaPath}" fill="url(#revArea)"/>
    <path d="${linePath}" fill="none" stroke="#22c55e" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
    <g>${ylabels}</g><g>${xlabels}</g><g>${dots}</g>
  </svg>`;
}

// ═══ Dashboard atmosphere — visual layer only (no data/nav/SPA logic) ═══════════
function _daReduced(){ return window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches; }

function initDashAtmos(){
  const host = document.getElementById('dashAtmos');
  if (!host || host.dataset.ready) return;
  host.dataset.ready = '1';

  // rotating girih mandala (16-fold symmetry)
  let petals = '';
  for (let i=0;i<16;i++) petals += `<use href="#daPetal" transform="rotate(${i*22.5} 300 300)"/>`;
  const mandala = document.createElement('div');
  mandala.className = 'da-mandala';
  mandala.innerHTML = `
    <svg viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg">
      <defs><path id="daPetal" d="M300 300 L312 150 L300 68 L288 150 Z" fill="none" stroke="#d4b46c" stroke-width="1.1"/></defs>
      <g fill="none" stroke="#d4b46c" stroke-width="1.1">
        <circle cx="300" cy="300" r="252"/><circle cx="300" cy="300" r="190"/>
        <circle cx="300" cy="300" r="120"/><circle cx="300" cy="300" r="60"/>
        <rect x="160" y="160" width="280" height="280"/>
        <rect x="160" y="160" width="280" height="280" transform="rotate(45 300 300)"/>
        <polygon points="300,88 423,160 423,440 300,512 177,440 177,160"/>
      </g>
      <g>${petals}</g>
    </svg>`;
  host.appendChild(mandala);

  // breathing light blobs
  host.insertAdjacentHTML('beforeend', '<div class="da-glow g1"></div><div class="da-glow g2"></div><div class="da-glow g3"></div>');

  // floating gold particles (skip on reduced-motion / small screens)
  if (!_daReduced() && window.innerWidth > 640){
    for (let i=0;i<14;i++){
      const p = document.createElement('div');
      p.className = 'da-particle';
      const sz = (2 + Math.random()*3).toFixed(1);
      p.style.left = (Math.random()*100).toFixed(2) + '%';
      p.style.width = p.style.height = sz + 'px';
      p.style.animationDuration = (9 + Math.random()*9).toFixed(1) + 's';
      p.style.animationDelay = (-Math.random()*18).toFixed(1) + 's';
      p.style.opacity = (0.4 + Math.random()*0.4).toFixed(2);
      host.appendChild(p);
    }
  }
}

// count-up: animates 0→value; final frame restores the exact formatted string
function daCountUp(el){
  const raw = (el.textContent||'').trim();
  const digits = raw.replace(/\D/g,'');
  if (!digits || _daReduced()) return;
  const target = parseInt(digits,10);
  if (!isFinite(target) || target<=0) return;
  el._daCounting = true;
  const dur = 1300, t0 = performance.now();
  (function frame(now){
    const p = Math.min(1,(now-t0)/dur);
    const e = 1 - Math.pow(1-p,3); // ease-out cubic
    if (p < 1){
      el.textContent = Math.round(target*e).toLocaleString('uz-UZ');
      requestAnimationFrame(frame);
    } else {
      el.textContent = raw;        // exact original — format never drifts
      el._daCounting = false;
    }
  })(performance.now());
}
function initDashCountUp(){
  ['kpiRevenue','kpiOrders','kpiCustomers','kpiAvgOrder','kpiNetProfit','goalPct','donutTotal'].forEach(id => {
    const el = document.getElementById(id);
    if (!el || el._daObserved) return;
    el._daObserved = true;
    new MutationObserver(() => {
      if (el._daCounting) return;
      const t = (el.textContent||'').trim();
      if (/\d/.test(t) && t !== el._daLast){ el._daLast = t; daCountUp(el); }
    }).observe(el, { childList:true, characterData:true, subtree:true });
  });
}

// gentle 3D tilt on hover (dashboard cards only)
function _daTilt(e){
  const el = e.currentTarget, r = el.getBoundingClientRect();
  const x = (e.clientX-r.left)/r.width - .5, y = (e.clientY-r.top)/r.height - .5;
  el.style.transform = `translateY(-2px) rotateX(${(-y*7).toFixed(2)}deg) rotateY(${(x*7).toFixed(2)}deg)`;
}
function _daTiltReset(e){ e.currentTarget.style.transform = ''; }
function initDashTilt(){
  if (_daReduced() || (window.matchMedia && matchMedia('(hover: none)').matches)) return;
  document.querySelectorAll('#pageDashboard .kpi-card, #pageDashboard .chart-card').forEach(el => {
    if (el._daTilt) return;
    el._daTilt = true;
    el.style.transition = 'transform .12s ease, border-color var(--tr), box-shadow var(--tr)';
    el.addEventListener('mousemove', _daTilt);
    el.addEventListener('mouseleave', _daTiltReset);
  });
}
// BOSQICH 5: count-up'ni butun admin SPA stat/kpi raqamlariga kengaytirish.
// Dashboard KPI'lar initDashCountUp bilan kuzatiladi (bu ularni _daObserved bo'lgani
// uchun o'tkazib yuboradi). Faqat TOZA raqam (bo'sh joy/nuqta/vergul) sanaydi —
// "12 / 30", "45%", matn yoki "—" tegilmaydi (noto'g'ri oraliq raqam chiqmasin).
function initStatCountUp(){
  if (_daReduced()) return;
  document.querySelectorAll('.stat-value, .kpi-value, .ms-val').forEach(el => {
    if (el._daObserved) return;
    el._daObserved = true;
    new MutationObserver(() => {
      if (el._daCounting) return;
      const t = (el.textContent||'').trim();
      if (!/^\d[\d\s., ]*$/.test(t)) return;   // faqat toza raqam
      if (t !== el._daLast){ el._daLast = t; daCountUp(el); }
    }).observe(el, { childList:true, characterData:true, subtree:true });
  });
}
document.addEventListener('DOMContentLoaded', () => { initDashAtmos(); initDashCountUp(); initDashTilt(); initStatCountUp(); });

// ── Orders page ───────────────────────────────────────────────────────────────
let ordersPage = 1;
async function loadOrders() {
  const status = document.getElementById('orderStatusFilter').value;
  const search = document.getElementById('ordersSearch').value;
  const params = new URLSearchParams({ page:ordersPage, limit:15 });
  if (status) params.set('status', status);
  if (search) params.set('search', search);
  try {
    const data = await apiFetch('/orders/?' + params);
    const orders = data.items||data||[];
    const statusMap = { pending:['Kutmoqda','badge-blue'], confirmed:['Tasdiqlangan','badge-blue'], preparing:['Tayyorlanmoqda','badge-amber'], ready:['Tayyor','badge-green'], completed:['Bajarildi','badge-green'], cancelled:['Bekor','badge-red'] };
    const body = document.getElementById('ordersBody');
    if (!orders.length) { body.innerHTML='<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Buyurtma topilmadi</td></tr>'; return; }
    body.innerHTML = orders.map(o => {
      const [sLbl,sCls] = statusMap[o.status]||['—','badge-gray'];
      return `<tr>
        <td class="td-bold">#${o.order_number||o.id}</td>
        <td class="td-sub">${fmtDate(o.created_at)}</td>
        <td>${o.customer_name||'—'}</td>
        <td>${o.table_number?'#'+o.table_number:'—'}</td>
        <td>${o.order_type||'dine-in'}</td>
        <td class="td-gold">${fmtMoney(o.final_amount)}</td>
        <td><span class="badge ${sCls}">${sLbl}</span></td>
        <td class="td-actions">
          <button class="act-btn" title="Ko'rish"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8"/></svg></button>
          ${o.status==='completed'?'':`<button class="act-btn danger" title="Bekor" onclick="cancelOrder(${o.id})"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2"/></svg></button>`}
        </td>
      </tr>`;
    }).join('');
    const total = data.total||orders.length;
    document.getElementById('ordersPaginInfo').textContent = `${orders.length} / ${total} ta`;
  } catch (err) { toast(err.message,'error'); }
}
async function cancelOrder(id) {
  if (!confirm('Buyurtmani bekor qilasizmi?')) return;
  try {
    await fetch(API_BASE+'/orders/'+id, {method:'PATCH',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({status:'cancelled'})});
    toast('Bekor qilindi','success'); loadOrders();
  } catch { toast('Xatolik','error'); }
}
document.getElementById('orderStatusFilter').addEventListener('change', () => { ordersPage=1; loadOrders(); });

// ── Sotuvlar tarixi ───────────────────────────────────────────────────────────
let salesPage = 1;
let _salesFiltersInit = false;

const _payLabel = { cash:'Naqd', card:'Karta', click:'Click', payme:'Payme', credit:'Nasiya', transfer:"O'tkazma" };
const _statusSales = { completed:['Yakunlangan','badge-green'], paid:['To\'langan','badge-green'], pending:['Kutmoqda','badge-blue'], preparing:['Tayyorlanmoqda','badge-amber'], ready:['Tayyor','badge-green'], cancelled:['Bekor','badge-red'] };

async function _initSalesFilters() {
  if (_salesFiltersInit) return;
  // Kassirlar (tenant userlari) va kassalar (tenant kassalari) — backend tenant bo'yicha filtrlaydi
  try {
    const users = await apiFetch('/users/?page_size=200');
    const list = users.items || users || [];
    document.getElementById('shCashier').innerHTML = '<option value="">Barcha kassirlar</option>' +
      list.map(u => `<option value="${u.id}">${escH(u.full_name||u.username)}</option>`).join('');
  } catch {}
  try {
    const regs = await apiFetch('/cash-registers/');
    const rlist = Array.isArray(regs) ? regs : (regs.items||[]);
    document.getElementById('shRegister').innerHTML = '<option value="">Barcha kassalar</option>' +
      rlist.map(r => `<option value="${r.id}">${escH(r.name)}</option>`).join('');
  } catch {}
  ['shFrom','shTo','shCashier','shRegister'].forEach(id =>
    document.getElementById(id).addEventListener('change', () => { salesPage=1; loadSalesHistory(); }));
  document.getElementById('shClearBtn').addEventListener('click', () => {
    ['shFrom','shTo','shCashier','shRegister'].forEach(id => document.getElementById(id).value='');
    salesPage=1; loadSalesHistory();
  });
  _salesFiltersInit = true;
}

async function loadSalesHistory() {
  await _initSalesFilters();
  const params = new URLSearchParams({ page: salesPage, page_size: 20 });
  const from = document.getElementById('shFrom').value;
  const to   = document.getElementById('shTo').value;
  const cid  = document.getElementById('shCashier').value;
  const rid  = document.getElementById('shRegister').value;
  if (from) params.set('date_from', from + 'T00:00:00');
  if (to)   params.set('date_to',   to   + 'T23:59:59');
  if (cid)  params.set('cashier_id', cid);
  if (rid)  params.set('register_id', rid);

  const body = document.getElementById('salesBody');
  try {
    const data = await apiFetch('/orders/?' + params);
    const orders = data.items || [];
    if (!orders.length) { body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Sotuvlar topilmadi</td></tr>'; document.getElementById('salesPaginInfo').textContent='0 ta'; document.getElementById('salesPagination').innerHTML=''; return; }
    body.innerHTML = orders.map(o => {
      const [sLbl,sCls] = _statusSales[o.status] || [o.status||'—','badge-gray'];
      const pay = o.payment_method ? (_payLabel[o.payment_method]||o.payment_method) : '—';
      return `<tr style="cursor:pointer" onclick="openSaleDetail(${o.id})">
        <td class="td-bold">${o.daily_number != null ? '#'+o.daily_number : '—'}</td>
        <td class="td-sub">${fmtDate(o.created_at)}</td>
        <td>${escH(o.waiter_name||'—')}</td>
        <td>${escH(o.register_name||'—')}</td>
        <td>${pay}</td>
        <td class="td-gold">${fmtMoney(o.final_amount)}</td>
        <td><span class="badge ${sCls}">${sLbl}</span></td>
        <td class="td-actions"><button class="act-btn" title="Chekni chop etish" data-reprint="${o.id}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M6 9V3h12v6M6 21h12v-6H6v6z" stroke="currentColor" stroke-width="1.8"/><path d="M18 9h2a2 2 0 012 2v5a2 2 0 01-2 2h-2" stroke="currentColor" stroke-width="1.8"/></svg></button><button class="act-btn" title="Ko'rish" onclick="event.stopPropagation();openSaleDetail(${o.id})"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8"/></svg></button></td>
      </tr>`;
    }).join('');
    const total = data.total || orders.length;
    const pages = data.total_pages || 1;
    document.getElementById('salesPaginInfo').textContent = `${orders.length} / ${total} ta`;
    let pg = '';
    if (pages > 1) {
      pg += `<button class="pager-btn" ${salesPage<=1?'disabled':''} onclick="salesPage--;loadSalesHistory()">‹</button>`;
      pg += `<span style="padding:0 .5rem">${salesPage} / ${pages}</span>`;
      pg += `<button class="pager-btn" ${salesPage>=pages?'disabled':''} onclick="salesPage++;loadSalesHistory()">›</button>`;
    }
    document.getElementById('salesPagination').innerHTML = pg;
  } catch (err) { toast(err.message,'error'); }
}

async function openSaleDetail(id) {
  openModal('saleDetailModal');
  const bodyEl = document.getElementById('sdBody');
  bodyEl.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text3)">Yuklanmoqda...</div>';
  try {
    const o = await apiFetch('/orders/' + id);
    document.getElementById('sdTitle').textContent = 'Chek ' + (o.daily_number != null ? '#'+o.daily_number : (o.order_number||''));
    const _rb = document.getElementById('sdReprintBtn'); if (_rb) _rb.dataset.reprint = id;
    const pay = o.payment_method ? (_payLabel[o.payment_method]||o.payment_method) : '—';
    const rows = (o.items||[]).map(it => `
      <tr>
        <td>${escH(it.product_name||'#'+it.product_id)}</td>
        <td style="text-align:center">${it.quantity}</td>
        <td style="text-align:right">${fmtMoney(it.unit_price)}</td>
        <td style="text-align:right">${fmtMoney(it.total_price)}</td>
      </tr>`).join('');
    const line = (lbl,val,bold) => `<div style="display:flex;justify-content:space-between;padding:.3rem 0;${bold?'font-weight:700;font-size:1.05rem;border-top:1px solid var(--border);margin-top:.3rem;padding-top:.5rem':''}"><span style="color:var(--text3)">${lbl}</span><span${bold?' class="td-gold"':''}>${fmtMoney(val)}</span></div>`;
    bodyEl.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:.4rem .75rem;font-size:.875rem;margin-bottom:1rem">
        <div><span style="color:var(--text3)">Chek №:</span> <b>${o.daily_number != null ? '#'+o.daily_number : '—'}</b></div>
        <div><span style="color:var(--text3)">Sana:</span> ${fmtDate(o.created_at)}</div>
        <div><span style="color:var(--text3)">Kassir:</span> ${escH(o.waiter_name||'—')}</div>
        <div><span style="color:var(--text3)">Kassa:</span> ${escH(o.register_name||'—')}</div>
        <div><span style="color:var(--text3)">To'lov:</span> ${pay}</div>
        <div><span style="color:var(--text3)">Status:</span> ${(_statusSales[o.status]||[o.status])[0]}</div>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:.85rem">
        <thead><tr style="color:var(--text3);text-align:left"><th style="padding:.3rem 0">Mahsulot</th><th style="text-align:center">Soni</th><th style="text-align:right">Narx</th><th style="text-align:right">Jami</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4" style="text-align:center;color:var(--text3);padding:1rem">Mahsulot yo\'q</td></tr>'}</tbody>
      </table>
      <div style="margin-top:1rem">
        ${line('Oraliq summa', o.total_amount)}
        ${(o.discount_amount>0)?line('Chegirma', -o.discount_amount):''}
        ${(o.tax_amount>0)?line('Soliq', o.tax_amount):''}
        ${line('YAKUNIY', o.final_amount, true)}
      </div>`;
  } catch (err) { bodyEl.innerHTML = `<div style="color:var(--red);padding:1rem">Xatolik: ${escH(err.message)}</div>`; }
}

// ── Products page ─────────────────────────────────────────────────────────────
// Extra column config per bizType
const _serviceTypes = ['salon','fitness','auto_service','school','dry_cleaning'];
const _hotelTypes   = ['hotel'];
function _extraHeader() {
  if (_serviceTypes.includes(bizType)) return 'Davomiylik';
  if (_hotelTypes.includes(bizType))   return "Sig'im";
  if (bizType === 'pharmacy')          return 'Dozaj';
  return 'Shtrix-kod';
}
function _extraCell(p) {
  if (_serviceTypes.includes(bizType)) return p.duration_minutes ? p.duration_minutes+' min' : (p.duration_hours ? p.duration_hours+' soat' : '—');
  if (_hotelTypes.includes(bizType))   return p.capacity ? p.capacity+' kishi' : '—';
  if (bizType === 'pharmacy')          return p.dosage || '—';
  return `<span style="font-family:monospace">${p.barcode||'—'}</span>`;
}

async function loadProducts() {
  // Set table header for extra column
  const thExtra = document.getElementById('thExtra');
  if (thExtra) thExtra.textContent = _extraHeader();

  const search = document.getElementById('productsSearch').value;
  const catId  = document.getElementById('productsCatFilter').value;
  // BUG 4: backend `page_size` kutadi (`limit` e'tiborga olinmasdi → 20 default).
  // 500 — barcha "Umumiy" mahsulot bir ekranda ko'rinsin (inventory bilan izchil),
  // hammasini belgilab bulk kategoriya berish uchun.
  const params = new URLSearchParams({ page:1, page_size:500 });
  if (search) params.set('search', search);
  if (catId)  params.set('category_id', catId);
  try {
    // Load category filter options once
    if (!cachedCategories.length) {
      const cats = await apiFetch('/categories/all').catch(()=>[]);
      cachedCategories = cats || [];
      const flt = document.getElementById('productsCatFilter');
      if (flt && cachedCategories.length) {
        const cur = flt.value;
        flt.innerHTML = '<option value="">Barcha kategoriyalar</option>' +
          cachedCategories.map(c=>`<option value="${c.id}"${c.id==cur?' selected':''}>${c.name}</option>`).join('');
      }
    }
    const data = await apiFetch('/products/?' + params);
    const prods = data.items||data||[];
    _loadedProducts = prods;   // BOSQICH B7: pachka sozlash modali uchun (nom/narx/pack)
    const body  = document.getElementById('productsBody');
    if (!prods.length) { body.innerHTML='<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Mahsulot topilmadi</td></tr>'; _resetBulkSelection(); return; }
    body.innerHTML = prods.map(p => {
      const priceVal = p.daily_price ? fmtMoney(p.daily_price)+'/kun' : fmtMoney(p.price||0);
      return `<tr>
        <td style="text-align:center"><input type="checkbox" class="prod-cb" value="${p.id}" style="width:16px;height:16px;accent-color:var(--gold);cursor:pointer"></td>
        <td class="td-sub">${p.id}</td>
        <td class="td-bold">${p.name}</td>
        <td>${p.category_name||'—'}</td>
        <td class="td-gold">${priceVal} UZS</td>
        <td class="td-sub">${_extraCell(p)}</td>
        <td><span class="badge ${p.is_available!==false?'badge-green':'badge-red'}">${p.is_available!==false?'Faol':'Nofaol'}</span></td>
        <td class="td-actions">
          <button class="act-btn" title="Tahrirlash" onclick='openProductModal(${JSON.stringify(p)})'><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="1.8"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="1.8"/></svg></button>
          <button class="act-btn danger" title="O'chirish" onclick="deleteProduct(${p.id},'${p.name.replace(/'/g,"\\'")}')"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" stroke="currentColor" stroke-width="1.8"/></svg></button>
        </td>
      </tr>`;
    }).join('');
    document.getElementById('productsPaginInfo').textContent = `${prods.length} ta`;
    _resetBulkSelection();          // yangi ro'yxatда belgilash tozalanadi
    refreshBulkCatOptions();        // bulk kategoriya select'ini yangilash
  } catch (err) { toast(err.message,'error'); }
}
document.getElementById('productsSearch').addEventListener('input', () => loadProducts());
document.getElementById('productsCatFilter').addEventListener('change', () => loadProducts());

// ── BUG 4: Bulk (ommaviy) kategoriya berish ────────────────────────────────────
let _selectedProductIds = new Set();

function _updateBulkBar() {
  const bar = document.getElementById('productsBulkBar');
  if (!bar) return;
  const n = _selectedProductIds.size;
  const cnt = document.getElementById('bulkCount');
  if (cnt) cnt.textContent = `${n} ta tanlandi`;
  bar.style.display = n > 0 ? 'flex' : 'none';
}

// Ro'yxat qayta yuklanganда — belgilash tozalanadi (yangi qatorlar belgisiz)
function _resetBulkSelection() {
  _selectedProductIds.clear();
  const sa = document.getElementById('productsSelectAll');
  if (sa) { sa.checked = false; sa.indeterminate = false; }
  _updateBulkBar();
}

// "Bekor" — belgilangan qatorlarni ham tozalaydi (ro'yxat qayta yuklanmaydi)
function clearBulkSelection() {
  _selectedProductIds.clear();
  document.querySelectorAll('#productsBody .prod-cb').forEach(cb => { cb.checked = false; });
  const sa = document.getElementById('productsSelectAll');
  if (sa) { sa.checked = false; sa.indeterminate = false; }
  _updateBulkBar();
}

function _syncSelectAllState() {
  const all = document.querySelectorAll('#productsBody .prod-cb');
  const checked = document.querySelectorAll('#productsBody .prod-cb:checked');
  const sa = document.getElementById('productsSelectAll');
  if (sa) {
    sa.checked = all.length > 0 && checked.length === all.length;
    sa.indeterminate = checked.length > 0 && checked.length < all.length;
  }
}

function refreshBulkCatOptions() {
  const sel = document.getElementById('bulkCatSelect');
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = '<option value="">Kategoriya tanlang...</option>' +
    cachedCategories.map(c => `<option value="${c.id}"${c.id==cur?' selected':''}>${c.name}</option>`).join('');
}

async function bulkAssignCategory() {
  const catId = parseInt(document.getElementById('bulkCatSelect').value);
  if (!catId) { toast('Kategoriya tanlang', 'warning'); return; }
  if (!_selectedProductIds.size) { toast('Mahsulot tanlang', 'warning'); return; }
  const ids = [..._selectedProductIds];
  const btn = document.getElementById('bulkAssignBtn');
  btn.disabled = true; btn.textContent = '...';
  try {
    const res = await fetch(`${API_BASE}/products/bulk-category`, {
      method: 'PATCH',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_ids: ids, category_id: catId }),
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || 'Xatolik'); }
    const data = await res.json().catch(()=>({}));
    toast(data.message || 'Kategoriya berildi', 'success');
    cachedCategories = [];   // kategoriya nomlari yangilansin
    loadProducts();          // ichida _resetBulkSelection chaqiriladi
  } catch (err) { toast(err.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Berish'; }
}

// Delegatsiya: qator checkbox'lari (har renderда yangi) — bitta listener tbody'da
document.getElementById('productsBody')?.addEventListener('change', (e) => {
  const cb = e.target;
  if (!cb.classList || !cb.classList.contains('prod-cb')) return;
  const id = parseInt(cb.value);
  if (cb.checked) _selectedProductIds.add(id); else _selectedProductIds.delete(id);
  _syncSelectAllState();
  _updateBulkBar();
});

// "Hammasini belgilash" (thead)
document.getElementById('productsSelectAll')?.addEventListener('change', (e) => {
  const on = e.target.checked;
  document.querySelectorAll('#productsBody .prod-cb').forEach(cb => {
    cb.checked = on;
    const id = parseInt(cb.value);
    if (on) _selectedProductIds.add(id); else _selectedProductIds.delete(id);
  });
  e.target.indeterminate = false;
  _updateBulkBar();
});

document.getElementById('bulkAssignBtn')?.addEventListener('click', bulkAssignCategory);
document.getElementById('bulkCancelBtn')?.addEventListener('click', clearBulkSelection);
document.getElementById('bulkNewCatBtn')?.addEventListener('click', () => openCategoryModal());

// ── BOSQICH B7: Pachka sozlash (eski ma'lumot tuzatish — guided) ───────────────
// Egа tanlagan mahsulotlarga pachka narxi/o'lchami QO'LDA sozlaydi. AVTOMAT
// ommaviy narx o'zgartirish YO'Q — faqat ✓ belgilangan mahsulot saqlanadi.
let _loadedProducts = [];
const _pkInput = 'width:100%;padding:.4rem .5rem;background:var(--bg3);border:1px solid var(--border2);border-radius:.375rem;color:var(--text);font-size:.8125rem';

function _pkRowHtml(p) {
  const on = !!(p.pack_size >= 2 && p.pack_price > 0);
  return `<div class="pk-row" data-id="${p.id}" data-price="${p.price||0}" style="border:1px solid var(--border2);border-radius:var(--r);padding:.625rem .75rem">
    <label style="display:flex;align-items:center;gap:.5rem;cursor:pointer;font-weight:600;font-size:.875rem">
      <input type="checkbox" class="pk-on" ${on?'checked':''} style="width:16px;height:16px;accent-color:var(--gold)">
      ${p.name} <span style="font-weight:400;color:var(--text3);font-size:.75rem">— joriy narx: ${fmtMoney(p.price||0)}</span>
    </label>
    <div class="pk-fields" style="display:${on?'block':'none'};margin-top:.5rem">
      <div class="fld-row fld-row-3" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:.5rem">
        <input class="pk-dona" type="number" min="0" placeholder="Dona narxi" value="${on?(p.price||''):''}" style="${_pkInput}">
        <input class="pk-pack" type="number" min="0" placeholder="Pachka narxi" value="${p.pack_price??''}" style="${_pkInput}">
        <input class="pk-size" type="number" min="2" placeholder="Dona soni" value="${p.pack_size??''}" style="${_pkInput}">
      </div>
      <button type="button" class="pk-move" style="margin-top:.375rem;font-size:.72rem;background:var(--bg3);border:1px solid var(--border2);border-radius:.375rem;padding:.25rem .5rem;cursor:pointer;color:var(--text2)">Joriy narx (${fmtMoney(p.price||0)}) → Pachka narxi</button>
      <div class="pk-preview" style="font-size:.72rem;color:var(--text3);margin-top:.375rem"></div>
    </div>
  </div>`;
}

function _pkUpdatePreview(row) {
  const dona = parseFloat(row.querySelector('.pk-dona').value);
  const pack = parseFloat(row.querySelector('.pk-pack').value);
  const size = parseInt(row.querySelector('.pk-size').value);
  const old  = parseFloat(row.dataset.price) || 0;
  const prev = row.querySelector('.pk-preview');
  if (dona > 0 && pack > 0 && size >= 2) {
    prev.innerHTML = `Eski: narx ${fmtMoney(old)} → <span style="color:var(--gold)">Yangi: dona ${fmtMoney(dona)}, pachka ${fmtMoney(pack)}, 1 pachka = ${size} dona</span>`;
  } else {
    prev.textContent = "Dona narxi + pachka narxi + dona soni (≥2) — hammasi to'ldirilsin";
  }
}

function openPackSetup() {
  if (!_selectedProductIds.size) { toast('Avval mahsulot(lar)ni belgilang', 'warning'); return; }
  const sel = _loadedProducts.filter(p => _selectedProductIds.has(p.id));
  if (!sel.length) { toast('Tanlangan mahsulot topilmadi', 'warning'); return; }
  document.getElementById('packSetupBody').innerHTML = sel.map(_pkRowHtml).join('');
  document.getElementById('pkBulkSize').value = '';
  document.getElementById('packSetupModal').classList.add('open');
  document.querySelectorAll('#packSetupBody .pk-row').forEach(_pkUpdatePreview);
}

function closePackSetup() { document.getElementById('packSetupModal').classList.remove('open'); }

document.getElementById('packSetupBody')?.addEventListener('change', (e) => {
  if (e.target.classList.contains('pk-on')) {
    e.target.closest('.pk-row').querySelector('.pk-fields').style.display = e.target.checked ? 'block' : 'none';
  }
});
document.getElementById('packSetupBody')?.addEventListener('input', (e) => {
  const c = e.target.classList;
  if (c.contains('pk-dona') || c.contains('pk-pack') || c.contains('pk-size')) _pkUpdatePreview(e.target.closest('.pk-row'));
});
document.getElementById('packSetupBody')?.addEventListener('click', (e) => {
  if (e.target.classList.contains('pk-move')) {
    const row = e.target.closest('.pk-row');
    row.querySelector('.pk-pack').value = row.dataset.price;
    _pkUpdatePreview(row);
  }
});
document.getElementById('pkBulkSizeBtn')?.addEventListener('click', () => {
  const v = parseInt(document.getElementById('pkBulkSize').value);
  if (!(v >= 2)) { toast("Dona soni ≥ 2 bo'lsin", 'warning'); return; }
  document.querySelectorAll('#packSetupBody .pk-row').forEach(row => {
    if (row.querySelector('.pk-on').checked) { row.querySelector('.pk-size').value = v; _pkUpdatePreview(row); }
  });
});

async function savePackSetup() {
  const rows = [...document.querySelectorAll('#packSetupBody .pk-row')].filter(r => r.querySelector('.pk-on').checked);
  if (!rows.length) { toast('Hech qaysi mahsulot belgilanmagan', 'warning'); return; }
  const jobs = [];
  for (const row of rows) {
    const dona = parseFloat(row.querySelector('.pk-dona').value);
    const pack = parseFloat(row.querySelector('.pk-pack').value);
    const size = parseInt(row.querySelector('.pk-size').value);
    const name = row.querySelector('.pk-on').parentElement.textContent.trim();
    if (!(dona > 0)) { toast(`"${name}": dona narxini kiriting`, 'error'); return; }
    if (!(pack > 0)) { toast(`"${name}": pachka narxini kiriting`, 'error'); return; }
    if (!(size >= 2)) { toast(`"${name}": dona soni ≥ 2 bo'lsin`, 'error'); return; }
    jobs.push({ id: parseInt(row.dataset.id), body: { price: dona, pack_price: pack, pack_size: size } });
  }
  const btn = document.getElementById('pkSaveBtn');
  btn.disabled = true; btn.textContent = 'Saqlanmoqda...';
  let ok = 0, fail = 0;
  for (const j of jobs) {
    try {
      const res = await fetch(`${API_BASE}/products/${j.id}`, {
        method: 'PATCH', headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
        body: JSON.stringify(j.body),
      });
      if (res.ok) ok++; else fail++;
    } catch { fail++; }
  }
  btn.disabled = false; btn.textContent = 'Saqlash';
  toast(`${ok} ta saqlandi${fail ? `, ${fail} ta xato` : ''}`, fail ? 'warning' : 'success');
  if (ok) { closePackSetup(); cachedCategories = []; loadProducts(); }
}

document.getElementById('pkSaveBtn')?.addEventListener('click', savePackSetup);
document.getElementById('bulkPackSetupBtn')?.addEventListener('click', openPackSetup);
// Pachka sozlash faqat store/supermarket/pharmacy da
if (!['store', 'supermarket', 'pharmacy'].includes(bizType)) {
  const _b = document.getElementById('bulkPackSetupBtn');
  if (_b) _b.style.display = 'none';
}

// ── Customers page ────────────────────────────────────────────────────────────
async function loadCustomers() {
  const search = document.getElementById('custsSearch').value;
  const params = new URLSearchParams({ limit:30 });
  if (search) params.set('search', search);
  try {
    const data  = await apiFetch('/customers/?' + params);
    const custs = data.items||data||[];
    _loadedCustomers = custs;   // BOSQICH S1: tahrir modali uchun
    const body  = document.getElementById('customersBody');
    const tierMap = { bronze:'🥉 Bronze', silver:'🥈 Silver', gold:'🥇 Gold', platinum:'💎 Platinum' };
    if (!custs.length) { body.innerHTML='<tr><td colspan="9" style="text-align:center;padding:2rem;color:var(--text3)">Mijoz topilmadi</td></tr>'; return; }
    body.innerHTML = custs.map(c => `<tr>
      <td class="td-sub">${c.id}</td>
      <td class="td-bold">${c.name}</td>
      <td class="td-sub">${c.phone||'—'}</td>
      <td>${c.discount_percent ? c.discount_percent + '%' : '—'}</td>
      <td>${c.total_orders||0}</td>
      <td class="td-gold">${fmtMoney(c.total_spent||0)} UZS</td>
      <td>${c.loyalty_points||0} ball</td>
      <td>${tierMap[c.loyalty_tier]||c.loyalty_tier||'—'}</td>
      <td class="td-actions"><button class="act-btn" data-edit-cust="${c.id}" title="Tahrirlash"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="1.8"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="1.8"/></svg></button></td>
    </tr>`).join('');
  } catch (err) { toast(err.message,'error'); }
}

// ── BOSQICH S1: Mijoz qo'shish/tahrirlash (chegirma % bilan) ───────────────────
let _loadedCustomers = [];
let _editingCustomerId = null;

function openCustomerAdd() {
  _editingCustomerId = null;
  document.getElementById('ceModalTitle').textContent = 'Yangi Mijoz';
  document.getElementById('ceName').value = '';
  document.getElementById('cePhone').value = '';
  document.getElementById('ceDiscount').value = '';
  document.getElementById('customerEditModal').classList.add('open');
  setTimeout(() => document.getElementById('ceName').focus(), 60);
}
function openCustomerEdit(id) {
  const c = _loadedCustomers.find(x => x.id === id);
  if (!c) return;
  _editingCustomerId = id;
  document.getElementById('ceModalTitle').textContent = 'Mijozni tahrirlash';
  document.getElementById('ceName').value = c.name || '';
  document.getElementById('cePhone').value = c.phone || '';
  document.getElementById('ceDiscount').value = c.discount_percent != null ? c.discount_percent : '';
  document.getElementById('customerEditModal').classList.add('open');
  setTimeout(() => document.getElementById('ceName').focus(), 60);
}
function closeCustomerModal() { document.getElementById('customerEditModal').classList.remove('open'); }

async function saveCustomer() {
  const name  = document.getElementById('ceName').value.trim();
  const phone = document.getElementById('cePhone').value.trim();
  const discRaw = document.getElementById('ceDiscount').value;
  const disc = discRaw !== '' ? parseFloat(discRaw) : 0;
  if (!name)  { toast('Ism kiriting', 'error'); return; }
  if (!phone) { toast('Telefon kiriting', 'error'); return; }
  if (!(disc >= 0 && disc <= 100)) { toast("Chegirma 0-100 oralig'ida bo'lsin", 'error'); return; }
  const body = { name, phone, discount_percent: disc };
  const btn = document.getElementById('ceSaveBtn');
  btn.disabled = true; btn.textContent = 'Saqlanmoqda...';
  try {
    // apiFetch faqat GET — PATCH/POST uchun apiFetchPost
    if (_editingCustomerId) await apiFetchPost(`/customers/${_editingCustomerId}`, body, 'PATCH');
    else                    await apiFetchPost('/customers/', body, 'POST');
    closeCustomerModal();
    toast(_editingCustomerId ? 'Saqlandi' : "Mijoz qo'shildi", 'success');
    loadCustomers();
  } catch (e) { toast(e.message || 'Xato', 'error'); }   // backend 400: telefon band / chegirma 0-100
  finally { btn.disabled = false; btn.textContent = 'Saqlash'; }
}

document.getElementById('customersBody')?.addEventListener('click', (e) => {
  const b = e.target.closest('[data-edit-cust]');
  if (b) openCustomerEdit(parseInt(b.dataset.editCust));
});
document.getElementById('ceCloseBtn')?.addEventListener('click', closeCustomerModal);
document.getElementById('ceCancelBtn')?.addEventListener('click', closeCustomerModal);
document.getElementById('ceSaveBtn')?.addEventListener('click', saveCustomer);
document.getElementById('customerEditModal')?.addEventListener('click', (e) => { if (e.target.id === 'customerEditModal') closeCustomerModal(); });

// ── Shifts page ───────────────────────────────────────────────────────────────
async function loadShifts() {
  try {
    const data   = await apiFetch('/shifts/');
    const shifts = data.items||data||[];
    const body   = document.getElementById('shiftsBody');
    if (!shifts.length) { body.innerHTML='<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Smena topilmadi</td></tr>'; return; }
    body.innerHTML = shifts.map(s => `<tr>
      <td class="td-sub">${s.id}</td>
      <td class="td-bold">${s.user_name||s.cashier||'—'}</td>
      <td class="td-sub">${fmtDate(s.start_time)}</td>
      <td class="td-sub">${s.end_time?fmtDate(s.end_time):'—'}</td>
      <td class="td-gold">${fmtMoney(s.total_sales||0)} UZS</td>
      <td>${fmtMoney(s.cash_sales||0)} UZS</td>
      <td><span class="badge ${s.end_time?'badge-gray':'badge-green'}">${s.end_time?'Yopilgan':'Faol'}</span></td>
      <td class="td-actions">
        <button class="act-btn" onclick="viewShiftReport(${s.id})" title="Hisobot"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" stroke-width="1.8"/><path d="M14 2v6h6M9 13h6M9 17h4" stroke="currentColor" stroke-width="1.8"/></svg></button>
      </td>
    </tr>`).join('');
    const active = shifts.filter(s=>!s.end_time).length;
    document.getElementById('shiftActive').textContent  = active;
    document.getElementById('shiftRevTotal').textContent = fmtMoney(shifts.filter(s=>!s.end_time).reduce((a,s)=>a+(s.total_sales||0),0)) + ' UZS';
    document.getElementById('shiftOrdTotal').textContent = '—';
  } catch (err) { toast(err.message,'error'); }
}
async function viewShiftReport(shiftId) {
  try {
    const rep = await apiFetch('/shifts/'+shiftId+'/report');
    toast(`Smena #${shiftId}: ${fmtMoney(rep.summary?.total_revenue)} UZS, ${rep.summary?.total_orders} buyurtma`,'info',5000);
  } catch { toast('Hisobot yuklanmadi','error'); }
}

// ── Page load dispatcher ──────────────────────────────────────────────────────
function loadPageData(page) {
  if (page==='dashboard')  loadDashboard();
  if (page==='orders')     loadOrders();
  if (page==='salesHistory') loadSalesHistory();
  if (page==='products')   loadProducts();
  if (page==='categories') loadCategories();
  if (page==='specials')   loadSpecials();
  if (page==='waiters')    loadWaiters();
  if (page==='reservCalendar') loadReservCalendar();
  if (page==='loyaltyTiers')   loadLoyaltyTiers();
  if (page==='topDishes')      loadTopDishes();
  if (page==='waiterShift')    loadWaiterShift();
  if (page==='kitchenStats')   loadKitchenStats();
  if (page==='stopList')       loadStopList();
  if (page==='staffMeal')      { smLoadSelects(); loadStaffMeals(); }
  if (page==='modifiers')      loadModifiers();
  if (page==='storeTop')       loadStoreTop();
  if (page==='storeMargin')    loadStoreMargin();
  if (page==='storeCats')      loadStoreCats();
  if (page==='storeCashier')   loadStoreCashier();
  if (page==='storePriceList') loadStorePriceList();
  if (page==='storeDiscounts')       loadStoreDiscounts();
  if (page==='debtList')             { loadDebtSummary(); loadDebts(); }
  if (page==='promotionsList')       loadPromotions();
  if (page==='quickSellList')        loadQuickSellItems();
  if (page==='registersList')        loadRegisters();
  if (page==='cashRegisterList')     loadShiftsPage();
  if (page==='receiptSettingsPage')  loadReceiptSettings();
  if (page==='departmentsList')      loadDepartments();
  if (page==='pharmStats')     loadPharmStats();
  if (page==='pharmPatients')  loadPharmPatients();
  if (page==='pharmTopMeds')   loadPharmTopMeds();
  if (page==='pharmExpiry')    loadPharmExpiry();
  if (page==='pharmCats')      loadPharmCats();
  if (page==='pharmCashier')   loadPharmCashier();
  if (page==='salonSchedule')    loadSalonSchedule();
  if (page==='salonServices')    loadSalonServices();
  if (page==='salonPeakHours')   loadSalonPeakHours();
  if (page==='salonExpiring')    loadSalonExpiring();
  if (page==='salonClients')     loadSalonClients();
  if (page==='salonMasterReport') loadSalonMasterReport();
  if (page==='autoStats')    loadAutoStats();
  if (page==='autoReady')    loadAutoReady();
  if (page==='autoDebt')     loadAutoDebt();
  if (page==='autoDuration') loadAutoDuration();
  if (page==='autoBrands')   loadAutoBrands();
  if (page==='autoClients')  loadAutoClients();
  if (page==='schoolStats')       loadSchoolStats();
  if (page==='schoolTopStudents') loadSchoolTopStudents();
  if (page==='schoolGroupDetail') loadSchoolGroupDetail();
  if (page==='schoolPayments')    loadSchoolPayments();
  if (page==='schoolMonthly')     loadSchoolMonthly();
  if (page==='schoolTopCourses')  loadSchoolTopCourses();
  if (page==='dryStats')    loadDryStats();
  if (page==='dryReady')    loadDryReady();
  if (page==='dryServices') loadDryServices();
  if (page==='dryClients')  loadDryClients();
  if (page==='dryWorkload') loadDryWorkload();
  if (page==='dryPayments') loadDryPayments();
  if (page==='customers')  loadCustomers();
  if (page==='shifts')     loadShifts();
  if (page==='inventory')     { loadInventory(); loadInventoryValue(); }   // #10: ombor qiymati KPI
  if (page==='stockIn')       loadStockIn();
  if (page==='stockOut')      loadStockOut();
  if (page==='invCount')      loadInvCountList();
  if (page==='invReport')     loadInvReport();
  if (page==='prescriptions') loadPrescriptions();
  if (page==='memberships')    loadMemberships();
  if (page==='masters')        loadMasters();
  if (page==='serviceOrders')  loadServiceOrders();
  if (page==='students')       loadStudents();
  if (page==='groups')         loadGroups();
  if (page==='cleaning')       loadCleaning();
  if (page==='hotelRooms')     loadHotelRooms();
  if (page==='hotelBookings')  loadHotelBookings();
  if (page==='hotelStats')       loadHotelStats();
  if (page==='hotelOccupancy')   loadHotelOccupancy();
  if (page==='hotelGuests')      loadHotelGuests();
  if (page==='hotelDebt')        loadHotelDebt();
  if (page==='hotelArrivals')    loadHotelArrivals();
  if (page==='hotelRoomRevenue') loadHotelRoomRevenue();
  if (page==='branches')  loadBranches();
  if (page==='staff')     loadStaff();
  if (page==='settings')  { loadSettings(); loadMonthlyGoalSetting(); }
  if (page==='auditLog')  loadAuditLog();
  if (page==='stations')  loadStationsAdmin();
  // BOSQICH 27: Aqlli hisobot
  if (page==='storeDashboard')    loadStoreDashboard();
  if (page==='abcAnalysis')       loadAbcAnalysis();
  if (page==='reorderAlerts')     { loadReorderAlerts(); loadReorderSuppliers(); }
  if (page==='turnoverAnalysis')  loadTurnoverAnalysis();
  if (page==='peakHours')         loadPeakHours();
}

// ── Pending badge ─────────────────────────────────────────────────────────────
async function updatePendingBadge() {
  try {
    const data = await apiFetch('/kitchen/orders');
    const cnt  = (data.pending||[]).length + (data.preparing||[]).length;
    document.getElementById('pendingOrdersBadge').textContent = cnt;
    document.getElementById('pendingOrdersBadge').style.display = cnt > 0 ? '' : 'none';
  } catch {}
}

// ── Low stock badge ───────────────────────────────────────────────────────────
async function updateLowStockBadge() {
  try {
    const data = await apiFetch('/inventory/low-stock');
    const cnt  = (data||[]).length;
    const badge = document.getElementById('lowStockBadge');
    if (badge) { badge.textContent = cnt; badge.style.display = cnt > 0 ? '' : 'none'; }
    const el = document.getElementById('invLow');
    if (el && currentPage === 'inventory') el.textContent = cnt;
  } catch {}
}

// ── Chart period ──────────────────────────────────────────────────────────────
document.querySelectorAll('.period-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // Grafikni tanlangan davr bo'yicha qayta yukla (Hafta=7 kun, Oy=30 kun).
    // Faqat grafik — KPI raqamlari "bugun" bo'yicha o'zgarmaydi.
    const a = await apiFetch('/analytics/summary?period=' + (btn.dataset.p || 'week')).catch(() => null);
    renderBarChart(a?.daily_revenue || []);
  });
});

// ── Product CRUD ──────────────────────────────────────────────────────────────
let editingProductId = null;
let cachedCategories = [];
let pmTabMode = 'main';
let pmImageFile = null;   // mahsulot rasm fayli (yaratgandan keyin yuklanadi)
let _pmExistingPlu = '';      // tahrirlashda mavjud tarozi PLU (weight_variable barcode)
let _pmExistingPluId = null;  // uning ProductBarcode id si

const _cs = `width:100%;padding:.5625rem .75rem;background:var(--bg3);border:1px solid var(--border2);border-radius:var(--r);color:var(--text);outline:none;font-family:inherit`;

function fldHtml(fname, product) {
  const fd = FIELD_DEFS[fname];
  if (!fd) return '';
  const eid = 'pmf_' + fname;
  const val = product ? (product[fd.key] ?? '') : '';
  if (fd.type === 'check') {
    const chk = product ? !!(product[fd.key] ?? fd.def) : !!(fd.def);
    return `<label style="display:flex;align-items:center;gap:.625rem;cursor:pointer;font-size:.875rem;padding:.25rem 0">
      <input id="${eid}" type="checkbox" ${chk?'checked':''} style="width:16px;height:16px;accent-color:var(--gold)"> ${fd.label}
    </label>`;
  }
  let ctrl = '';
  if (fd.type === 'area') {
    ctrl = `<textarea id="${eid}" rows="2" placeholder="${fd.ph||''}" style="${_cs};resize:vertical">${val||''}</textarea>`;
  } else if (fd.type === 'dept') {
    ctrl = `<select id="${eid}" style="${_cs}"><option value="">— Bo'limsiz —</option></select>`;
  } else if (fd.type === 'cats') {
    ctrl = `<select id="${eid}" style="${_cs}"><option value="">— tanlang —</option></select>`;
  } else if (fd.type === 'station') {
    ctrl = `<select id="${eid}" style="${_cs}"><option value="">— Stansiyasiz (displeysiz) —</option></select>`;
  } else if (fd.type === 'sel') {
    ctrl = `<select id="${eid}" style="${_cs}">${fd.opts.map(([v,l])=>`<option value="${v}"${val===v?' selected':''}>${l}</option>`).join('')}</select>`;
  } else {
    ctrl = `<input id="${eid}" type="${fd.type}" placeholder="${fd.ph||''}" value="${val||''}" style="${_cs}${fd.mono?';font-family:monospace':''}">`;
  }
  return `<div><label style="display:block;font-size:.8125rem;font-weight:500;color:var(--text2);margin-bottom:.375rem">${fd.label}</label>${ctrl}</div>`;
}

function fldVal(fname) {
  const fd = FIELD_DEFS[fname];
  const el = document.getElementById('pmf_' + fname);
  if (!el || !fd) return undefined;
  if (fd.type === 'check') return el.checked;
  if (fd.type === 'number') return el.value !== '' ? parseFloat(el.value) : null;
  if (fd.type === 'dept') return el.value ? parseInt(el.value) : null;
  if (fd.type === 'cats') return el.value ? parseInt(el.value) : null;
  if (fd.type === 'station') return el.value ? parseInt(el.value) : null;
  return el.value.trim() || null;
}

async function _loadCats() {
  if (cachedCategories.length) return cachedCategories;
  try { cachedCategories = await apiFetch('/categories/all') || []; } catch { cachedCategories = []; }
  return cachedCategories;
}

// Kategoriya tanlanmaganda — "Umumiy" default kategoriyani topadi yoki yaratadi.
// Backend category_id ni majburiy qiladi; bu 422 chalkashlikni oldini oladi.
// id qaytaradi, xatoda null.
async function ensureDefaultCategory() {
  const cats = await _loadCats();
  const found = cats.find(c => (c.name || '').trim().toLowerCase() === 'umumiy');
  if (found) return found.id;
  try {
    const res = await fetch(`${API_BASE}/categories/`, {
      method:'POST', headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},
      body: JSON.stringify({ name: 'Umumiy' }),
    });
    if (!res.ok) return null;
    const c = await res.json();
    cachedCategories = [];   // keshni yangilash — keyingi safar ro'yxatda chiqsin
    return c?.id || null;
  } catch { return null; }
}

let _cachedDepts = null;
async function _loadDepts() {
  if (_cachedDepts) return _cachedDepts;
  try { _cachedDepts = await apiFetch('/departments/?is_active=true') || []; } catch { _cachedDepts = []; }
  return _cachedDepts;
}
function _clearDeptsCache() { _cachedDepts = null; }

let _cachedStations = null;
async function _loadStationsCache() {
  if (_cachedStations) return _cachedStations;
  try { _cachedStations = await apiFetch('/stations/') || []; } catch { _cachedStations = []; }
  return _cachedStations;
}

function getCfg() { return FORM_CONFIGS[bizType] || FORM_CONFIGS.cafe; }

function openProductModal(product = null) {
  editingProductId = product?.id || null;
  const cfg = getCfg();
  pmTabMode = (product?.product_type === cfg.alt?.type) ? 'alt' : 'main';
  buildProductModal(product);
  document.getElementById('productModal').classList.add('open');
  setTimeout(() => document.getElementById('pmf_name')?.focus(), 120);
}

function closeProductModal() { document.getElementById('productModal').classList.remove('open'); }

function pmSwitchTab(mode) { pmTabMode = mode; buildProductModal(null); setTimeout(()=>document.getElementById('pmf_name')?.focus(),80); }

function buildProductModal(product) {
  const cfg = getCfg();
  const isAlt = pmTabMode === 'alt' && cfg.alt;
  const activeCfg = isAlt ? cfg.alt : cfg;
  const verb = editingProductId ? "tahrirlash" : "qo'shish";
  document.getElementById('pmTitle').textContent = activeCfg.title.replace("qo'shish", verb);

  let html = '';
  if (cfg.alt) {
    const ma = pmTabMode === 'main';
    html += `<div style="display:flex;gap:3px;background:var(--bg4);border-radius:var(--r);padding:3px">
      <button onclick="pmSwitchTab('main')" style="flex:1;padding:.375rem;border-radius:calc(var(--r) - 2px);font-size:.8125rem;font-weight:600;cursor:pointer;border:none;background:${ma?'var(--bg2)':'transparent'};color:${ma?'var(--gold)':'var(--text2)'}">${cfg.title.replace(" qo'shish",'')}</button>
      <button onclick="pmSwitchTab('alt')"  style="flex:1;padding:.375rem;border-radius:calc(var(--r) - 2px);font-size:.8125rem;font-weight:600;cursor:pointer;border:none;background:${!ma?'var(--bg2)':'transparent'};color:${!ma?'var(--gold)':'var(--text2)'}">${cfg.alt.title.replace(" qo'shish",'')}</button>
    </div>`;
  }
  for (const f of activeCfg.fields) {
    if (Array.isArray(f)) {
      // `fld-row` klassi — faqat mobil uchun ilgak (styles/mobile.css, ≤430px da
      // ustma-ust). Inline stil desktopda o'zgarmaydi, klass hech narsa qo'shmaydi.
      html += `<div class="fld-row" style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem">${f.map(fn=>fldHtml(fn,product)).join('')}</div>`;
    } else {
      html += fldHtml(f, product);
    }
  }
  document.getElementById('pmBody').innerHTML = html;

  // ── Rasm yuklash (barcha biznes turlari uchun) ──────────────────────────────
  pmImageFile = null;
  const _uplBase = API_BASE.replace('/api/v1', '');
  const curImg = product?.image_url ? (_uplBase + product.image_url) : '';
  const imgBlock = document.createElement('div');
  imgBlock.style.cssText = 'margin-top:.25rem';
  imgBlock.innerHTML = `
    <label style="display:block;font-size:.8125rem;color:var(--text2);margin-bottom:.375rem;font-weight:500">Rasm</label>
    <input type="file" id="pmf_image" accept="image/*" style="width:100%;font-size:.8125rem;color:var(--text2)">
    <img id="pmImgPrev" alt="" style="${curImg?'':'display:none;'}margin-top:.5rem;max-height:96px;border-radius:.5rem;border:1px solid var(--border2)" src="${curImg}">`;
  document.getElementById('pmBody').appendChild(imgBlock);
  document.getElementById('pmf_image').addEventListener('change', function () {
    const f = this.files && this.files[0];
    pmImageFile = f || null;
    const pv = document.getElementById('pmImgPrev');
    if (f) { pv.src = URL.createObjectURL(f); pv.style.display = ''; }
  });

  // ── Boshlang'ich qoldiq (faqat YANGI mahsulot + inventory flagi) ────────────
  if (!editingProductId && typeof hasFeature === 'function' && hasFeature('inventory')) {
    const stockBlock = document.createElement('div');
    stockBlock.style.cssText = 'margin-top:.75rem';
    stockBlock.innerHTML = `
      <label style="display:block;font-size:.8125rem;color:var(--text2);margin-bottom:.375rem;font-weight:500">Boshlang'ich qoldiq (ixtiyoriy)</label>
      <input type="number" id="pmf_stock" min="0" step="0.01" placeholder="0" style="width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:var(--r);padding:.5625rem .75rem;color:var(--text);font-size:.875rem">
      <div style="font-size:.75rem;color:var(--text3);margin-top:.25rem">Kiritilsa — ombor kirimi sifatida yoziladi</div>`;
    document.getElementById('pmBody').appendChild(stockBlock);
  }

  // ── Tarozi PLU (faqat og'irlik birligi: kg/g/l/ml) — weight_variable barcode ──
  const _saleUnitEl = document.getElementById('pmf_sale_unit');
  if (_saleUnitEl) {
    const _weightUnits = ['kg','g','l','ml','litr'];
    _pmExistingPlu = ''; _pmExistingPluId = null;
    const pluBlock = document.createElement('div');
    pluBlock.id = 'pmPluBlock';
    pluBlock.style.cssText = 'margin-top:.75rem';
    pluBlock.innerHTML = `
      <label style="display:block;font-size:.8125rem;color:var(--text2);margin-bottom:.375rem;font-weight:500">Tarozi PLU kodi (ixtiyoriy)</label>
      <input type="text" id="pmf_plu" inputmode="numeric" maxlength="5" placeholder="5 raqamli PLU (masalan 00123)" style="width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:var(--r);padding:.5625rem .75rem;color:var(--text);font-size:.875rem;font-family:monospace">
      <div style="font-size:.75rem;color:var(--text3);margin-top:.25rem">Tarozi shtrix-kodidagi PLU. Kiritilsa — tarozi kodi skaner qilinganda mahsulot og'irligi bilan savatga tushadi.</div>`;
    document.getElementById('pmBody').appendChild(pluBlock);
    const togglePlu = () => { pluBlock.style.display = _weightUnits.includes(_saleUnitEl.value) ? '' : 'none'; };
    _saleUnitEl.addEventListener('change', togglePlu);
    togglePlu();
    // Tahrirlashda: mavjud weight_variable barcode'ni yuklab, maydonni to'ldirish
    if (editingProductId) {
      apiFetch(`/barcodes/product/${editingProductId}`).then(list => {
        const wv = (list || []).find(b => b.weight_variable);
        if (wv) {
          _pmExistingPlu = wv.barcode; _pmExistingPluId = wv.id;
          const el = document.getElementById('pmf_plu');
          if (el) el.value = wv.barcode;
        }
      }).catch(() => {});
    }
  }

  // ── BOSQICH B2: Pachka/Dona (store/supermarket/pharmacy) ────────────────────
  // price = DONA narxi. pack_price = 1 pachka narxi, pack_size = pachkadagi dona.
  // OG'IRLIK (tarozi: kg/g/l) mahsulotда yashiriladi. "ml" (atir #20) — pack (Butun
  // flakon) bilan birga bo'ladi, bloklanmaydi.
  // DIQQAT: B2'da faqat saqlanadi — POS/ombor HALI ishlatmaydi (B3+).
  if (['store', 'supermarket', 'pharmacy'].includes(bizType)) {
    const _pcs = 'width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:var(--r);padding:.5625rem .75rem;color:var(--text);font-size:.875rem';
    const packBlock = document.createElement('div');
    packBlock.id = 'pmPackBlock';
    packBlock.style.cssText = 'margin-top:.75rem';
    packBlock.innerHTML = `
      <label id="pmPackTitle" style="display:block;font-size:.8125rem;color:var(--text2);margin-bottom:.375rem;font-weight:500">Pachka bilan sotish (ixtiyoriy)</label>
      <div class="fld-row" style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem">
        <input type="number" id="pmf_pack_price" min="0" step="0.01" placeholder="Pachka narxi (30000)" style="${_pcs}">
        <input type="number" id="pmf_pack_size" min="2" step="1" placeholder="Pachkadagi dona (10)" style="${_pcs}">
      </div>
      <div id="pmPackHint" style="font-size:.75rem;color:var(--text3);margin-top:.25rem">Kiritilsa — yuqoridagi <b>narx = DONA narxi</b> bo'ladi. Ikkalasi ham to'ldirilsin (pachka narxi + dona soni ≥ 2).</div>`;
    document.getElementById('pmBody').appendChild(packBlock);

    // Tahrirlashda: mavjud qiymatlarni to'ldirish
    if (product) {
      if (product.pack_price != null) document.getElementById('pmf_pack_price').value = product.pack_price;
      if (product.pack_size  != null) document.getElementById('pmf_pack_size').value  = product.pack_size;
    }

    // Pack × Weight ziddiyati: OG'IRLIK (kg/g/l) birlikда pack blok yashiriladi + tozalanadi.
    // #20 atir: "ml" HAJM birligi — pack (Butun flakon) BILAN birga bo'ladi, shuning uchun
    // ml BLOKLANMAYDI (POS ham isWeightUnit'da ml YO'Q, "Butun/ml" tanlovi uchun).
    const _saleUnitEl2 = document.getElementById('pmf_sale_unit');
    if (_saleUnitEl2) {
      const _wUnits = ['kg', 'g', 'l', 'litr'];
      // HAJM/OG'IRLIK birliklari (atir/suyuqlik) — yorliqlar "Flakon" ko'rinishida.
      const _volUnits = ['ml', 'l', 'litr', 'g', 'kg', 'dl', 'cl'];
      // #20b (KOSMETIK): pack yorliqlari sale_unit ga qarab DINAMIK — FAQAT matn,
      // funksiya (pack_size/pack_price/price qiymatlar, saqlash) TEGILMAYDI.
      const _priceInput = document.getElementById('pmf_price');
      const _priceLabel = _priceInput ? _priceInput.parentElement.querySelector('label') : null;
      const _origPriceLabel = _priceLabel ? _priceLabel.textContent : '';
      const updatePackLabels = () => {
        const u = (_saleUnitEl2.value || '').toLowerCase();
        const title = document.getElementById('pmPackTitle');
        const hint  = document.getElementById('pmPackHint');
        const pp = document.getElementById('pmf_pack_price');
        const ps = document.getElementById('pmf_pack_size');
        if (_volUnits.includes(u)) {
          // Atir/suyuqlik — "Flakon (butun)" yorliqlari
          if (title) title.textContent = 'Butun (flakon) bilan sotish (ixtiyoriy)';
          if (pp) pp.placeholder = 'Flakon narxi (250000)';
          if (ps) ps.placeholder = `Flakon hajmi (${u})`;
          if (hint) hint.innerHTML = `Kiritilsa — yuqoridagi <b>narx = 1 ${u} narxi</b> bo'ladi. Ikkalasi ham to'ldirilsin (flakon narxi + hajm).`;
          if (_priceLabel) _priceLabel.textContent = `1 ${u} narxi (UZS) *`;
        } else {
          // Do'kon (dona) — avvalgidek "Pachka" yorliqlari
          if (title) title.textContent = 'Pachka bilan sotish (ixtiyoriy)';
          if (pp) pp.placeholder = 'Pachka narxi (30000)';
          if (ps) ps.placeholder = 'Pachkadagi dona (10)';
          if (hint) hint.innerHTML = "Kiritilsa — yuqoridagi <b>narx = DONA narxi</b> bo'ladi. Ikkalasi ham to'ldirilsin (pachka narxi + dona soni ≥ 2).";
          if (_priceLabel) _priceLabel.textContent = _origPriceLabel;   // avvalgidek
        }
      };
      const togglePack = () => {
        const isW = _wUnits.includes(_saleUnitEl2.value);
        packBlock.style.display = isW ? 'none' : '';
        if (isW) {
          document.getElementById('pmf_pack_price').value = '';
          document.getElementById('pmf_pack_size').value = '';
        }
        updatePackLabels();   // yorliqlar birlikка mos yangilansin
      };
      _saleUnitEl2.addEventListener('change', togglePack);
      togglePack();
    }
  }

  // BOSQICH 15: narx + tan narx kiritilganda foyda marjasini jonli ko'rsatish
  const _pEl = document.getElementById('pmf_price'), _cEl = document.getElementById('pmf_cost_price');
  if (_pEl && _cEl) {
    const hint = document.createElement('div');
    hint.style.cssText = 'font-size:.75rem;margin-top:.375rem';
    _cEl.parentElement.appendChild(hint);
    const updMargin = () => {
      const p = parseFloat(_pEl.value)||0, c = parseFloat(_cEl.value)||0;
      if (p > 0 && c > 0) {
        const m = (p - c) / p * 100;
        hint.textContent = `Foyda: ${fmtMoney(p - c)} UZS · marja ${m.toFixed(1)}%`;
        hint.style.color = m < 15 ? '#ef4444' : '#10b981';
      } else hint.textContent = '';
    };
    _pEl.addEventListener('input', updMargin);
    _cEl.addEventListener('input', updMargin);
    updMargin();
  }

  if (activeCfg.fields.flat().includes('department')) {
    _loadDepts().then(depts => {
      const sel = document.getElementById('pmf_department');
      if (!sel) return;
      sel.innerHTML = '<option value="">— Bo\'limsiz —</option>' +
        depts.map(d=>`<option value="${d.id}"${product?.department_id===d.id?' selected':''}>${d.icon?d.icon+' ':''}${d.name}</option>`).join('');
    });
  }

  if (activeCfg.fields.flat().includes('category')) {
    _loadCats().then(cats => {
      const sel = document.getElementById('pmf_category');
      if (!sel) return;
      sel.innerHTML = '<option value="">— tanlang —</option>' +
        cats.map(c=>`<option value="${c.id}"${product?.category_id===c.id?' selected':''}>${c.name}</option>`).join('');
    });
  }

  if (activeCfg.fields.flat().includes('station')) {
    _loadStationsCache().then(stations => {
      const sel = document.getElementById('pmf_station');
      if (!sel) return;
      sel.innerHTML = '<option value="">— Stansiyasiz (displeysiz) —</option>' +
        stations.map(s => {
          const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${s.color};margin-right:4px"></span>`;
          return `<option value="${s.id}"${product?.station_id===s.id?' selected':''}>${s.name}${s.has_display?'':' ⊘'}</option>`;
        }).join('');
    });
  }
}

async function saveProduct() {
  const cfg = getCfg();
  const isAlt = pmTabMode === 'alt' && cfg.alt;
  const activeCfg = isAlt ? cfg.alt : cfg;
  const allFields = activeCfg.fields.flat();

  if (!fldVal('name')) { toast('Nomi kiritilmagan','error'); return; }

  const payload = { is_active:true, product_type: isAlt ? cfg.alt.type : 'product' };
  for (const f of allFields) {
    const fd = FIELD_DEFS[f];
    if (!fd) continue;
    const v = fldVal(f);
    if (v !== undefined) payload[fd.key] = v;
  }

  const priceField = allFields.includes('price') ? 'price' : allFields.includes('daily_price') ? 'daily_price' : null;
  if (priceField && (!payload[priceField] || payload[priceField] <= 0)) { toast('Narx kiritilmagan','error'); return; }

  // ── BOSQICH B2: Pachka/Dona validatsiya + payload ─────────────────────────────
  // Pack blok ko'rinsa (store-oila, weight emas): ikkovi to'g'ri bo'lsin yoki ikkovi bo'sh.
  // Har doim payload'ga yoziladi (null ham) — tahrirda pachkani tozalash ishlashi uchun.
  const _packBlock = document.getElementById('pmPackBlock');
  if (_packBlock && _packBlock.style.display !== 'none') {
    const ppRaw = document.getElementById('pmf_pack_price').value;
    const psRaw = document.getElementById('pmf_pack_size').value;
    const packPrice = ppRaw !== '' ? parseFloat(ppRaw) : null;
    const packSize  = psRaw !== '' ? parseInt(psRaw)  : null;
    if (packPrice != null || packSize != null) {
      // Biri to'ldirilsa — ikkalasi ham to'g'ri bo'lishi shart
      if (!(packSize >= 2))   { toast("Pachkadagi dona soni kamida 2 bo'lsin", 'error'); return; }
      if (!(packPrice > 0))   { toast('Pachka narxini kiriting', 'error'); return; }
      payload.pack_price = packPrice;
      payload.pack_size  = packSize;
    } else {
      payload.pack_price = null;
      payload.pack_size  = null;
    }
  } else {
    // Weight mahsulot yoki pack blok yo'q → pachkasiz (tozalab yuboriladi)
    payload.pack_price = null;
    payload.pack_size  = null;
  }

  // Kategoriya majburiy (backend category_id talab qiladi). Tanlanmagan bo'lsa —
  // "Umumiy" default kategoriya avtomatik ishlatiladi; yaratib bo'lmasa ochiq xato.
  if (allFields.includes('category') && !payload.category_id) {
    const defCat = await ensureDefaultCategory();
    if (!defCat) { toast('Kategoriya tanlang', 'warning'); return; }
    payload.category_id = defCat;
  }

  const btn = document.getElementById('pmSaveBtn');
  btn.disabled=true; btn.textContent='Saqlanmoqda...';
  try {
    const method = editingProductId ? 'PATCH' : 'POST';
    const url    = editingProductId ? `${API_BASE}/products/${editingProductId}` : `${API_BASE}/products/`;
    const res    = await fetch(url, { method, headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    const saved = await res.json().catch(()=>({}));

    // Rasm tanlangan bo'lsa — mahsulot id si bilan yuklaymiz
    const prodId = editingProductId || saved.id;
    if (pmImageFile && prodId) {
      const fd = new FormData(); fd.append('file', pmImageFile);
      await fetch(`${API_BASE}/products/${prodId}/image`, {
        method:'POST', headers:{'Authorization':'Bearer '+token}, body: fd,
      }).catch(()=>{});
    }

    // Boshlang'ich qoldiq — faqat yangi mahsulotda, kiritilgan bo'lsa omborga kirim.
    // BUG 9: Inventory qatori endi create_product'da DOIM yaratiladi (0 qoldiq).
    // Shuning uchun POST /inventory/ (yaratish) o'rniga add-stock bilan kirim
    // qilamiz — to'g'ri StockMovement (kelim) yoziladi.
    const stockEl = document.getElementById('pmf_stock');
    const startStock = stockEl ? (parseFloat(stockEl.value) || 0) : 0;
    if (!editingProductId && saved.id && startStock > 0) {
      try {
        const invRes = await fetch(`${API_BASE}/inventory/product/${saved.id}`, {
          headers:{'Authorization':'Bearer '+token},
        });
        if (invRes.ok) {
          const inv = await invRes.json();
          const costPrice = parseFloat(payload.cost_price) || 0;
          await fetch(`${API_BASE}/inventory/${inv.id}/add-stock`, {
            method:'POST', headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},
            body: JSON.stringify({ quantity: startStock, unit_cost: costPrice, notes: "Boshlang'ich qoldiq" }),
          });
        }
      } catch {}
    }

    // Tarozi PLU (weight_variable barcode) — qo'shish / yangilash / o'chirish
    const _pluBlock = document.getElementById('pmPluBlock');
    const _pluEl    = document.getElementById('pmf_plu');
    const newPlu = (_pluBlock && _pluBlock.style.display !== 'none' && _pluEl) ? _pluEl.value.trim() : '';
    if (prodId && newPlu !== (_pmExistingPlu || '')) {
      // eski PLU bo'lsa avval o'chiramiz (o'zgargan yoki tozalangan)
      if (_pmExistingPluId) {
        await fetch(`${API_BASE}/barcodes/${_pmExistingPluId}`, {
          method:'DELETE', headers:{'Authorization':'Bearer '+token},
        }).catch(()=>{});
      }
      if (newPlu) {
        const qs = new URLSearchParams({ product_id: prodId, barcode: newPlu, weight_variable: 'true', barcode_type: 'weight' });
        const r = await fetch(`${API_BASE}/barcodes/?${qs}`, {
          method:'POST', headers:{'Authorization':'Bearer '+token},
        }).catch(()=>null);
        if (r && !r.ok) { const e = await r.json().catch(()=>({})); toast('PLU saqlanmadi: ' + (e.detail || 'xato'), 'warning'); }
      }
    }

    closeProductModal();
    toast(editingProductId ? 'Yangilandi' : "Qo'shildi", 'success');
    cachedCategories=[]; loadProducts();
  } catch (err) {
    toast(err.message,'error');
    // BUG 1/8: barkod band bo'lsa — modal ochiq qoladi (yopilmaydi), barkod
    // maydonini belgilaymiz va fokuslaymiz, foydalanuvchi nima bo'lganini ko'rsin.
    if (/barcode|barkod|band/i.test(err.message || '')) {
      const bcEl = document.getElementById('pmf_barcode');
      if (bcEl) {
        bcEl.style.borderColor = '#ef4444';
        bcEl.focus();
        bcEl.addEventListener('input', () => { bcEl.style.borderColor = ''; }, { once: true });
      }
    }
  }
  finally { btn.disabled=false; btn.textContent='Saqlash'; }
}

async function deleteProduct(id, name) {
  if (!confirm(`"${name}" ni o'chirmoqchimisiz?`)) return;
  try {
    const res = await fetch(`${API_BASE}/products/${id}`, { method:'DELETE', headers:{'Authorization':'Bearer '+token} });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast("O'chirildi",'success'); loadProducts();
  } catch (err) { toast(err.message,'error'); }
}

// ── Categories CRUD ───────────────────────────────────────────────────────────
let editingCategoryId = null;

async function loadCategories() {
  try {
    const cats = await apiFetch('/categories/all') || [];
    cachedCategories = cats;
    const flt = document.getElementById('productsCatFilter');
    if (flt) {
      const cur = flt.value;
      flt.innerHTML = '<option value="">Barcha kategoriyalar</option>' +
        cats.map(c=>`<option value="${c.id}"${c.id==cur?' selected':''}>${c.name}</option>`).join('');
    }
    refreshBulkCatOptions();   // BUG 4: yangi kategoriya bulk select'da ham chiqsin
    const body = document.getElementById('categoriesBody');
    if (!body) return;
    if (!cats.length) { body.innerHTML='<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text3)">Kategoriya topilmadi</td></tr>'; return; }
    body.innerHTML = cats.map(c => `<tr>
      <td class="td-sub">${c.id}</td>
      <td class="td-bold">${c.name}</td>
      <td><span style="display:inline-flex;align-items:center;gap:.5rem"><span style="width:16px;height:16px;border-radius:4px;background:${c.color||'var(--gold)'};display:inline-block;flex-shrink:0"></span>${c.color||'—'}</span></td>
      <td>${c.sort_order||0}</td>
      <td class="td-actions">
        <button class="act-btn" onclick='openCategoryModal(${JSON.stringify(c)})' title="Tahrirlash"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="1.8"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="1.8"/></svg></button>
        <button class="act-btn danger" onclick="deleteCategory(${c.id},'${c.name.replace(/'/g,"\\'")}')"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" stroke="currentColor" stroke-width="1.8"/></svg></button>
      </td>
    </tr>`).join('');
  } catch (err) { toast(err.message,'error'); }
}

function openCategoryModal(cat = null) {
  editingCategoryId = cat?.id || null;
  document.getElementById('cmTitle').textContent = cat ? 'Kategoriya tahrirlash' : "Kategoriya qo'shish";
  document.getElementById('cmName').value  = cat?.name || '';
  document.getElementById('cmColor').value = cat?.color || '#d4b46c';
  document.getElementById('cmSort').value  = cat?.sort_order ?? 0;
  document.getElementById('categoryModal').classList.add('open');
  setTimeout(()=>document.getElementById('cmName').focus(), 100);
}

function closeCategoryModal() { document.getElementById('categoryModal').classList.remove('open'); }

async function saveCategory() {
  const name = document.getElementById('cmName').value.trim();
  if (!name) { toast('Nomi kiritilmagan','error'); return; }
  const payload = { name, color:document.getElementById('cmColor').value, sort_order:parseInt(document.getElementById('cmSort').value)||0 };
  const btn = document.getElementById('cmSaveBtn');
  btn.disabled=true; btn.textContent='Saqlanmoqda...';
  try {
    const method = editingCategoryId ? 'PATCH' : 'POST';
    const url = editingCategoryId ? `${API_BASE}/categories/${editingCategoryId}` : `${API_BASE}/categories/`;
    const res = await fetch(url, { method, headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    closeCategoryModal();
    toast(editingCategoryId ? 'Yangilandi' : "Qo'shildi",'success');
    cachedCategories=[]; loadCategories();
  } catch (err) { toast(err.message,'error'); }
  finally { btn.disabled=false; btn.textContent='Saqlash'; }
}

async function deleteCategory(id, name) {
  if (!confirm(`"${name}" kategoriyasini o'chirmoqchimisiz?`)) return;
  try {
    const res = await fetch(`${API_BASE}/categories/${id}`, { method:'DELETE', headers:{'Authorization':'Bearer '+token} });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast("O'chirildi",'success'); cachedCategories=[]; loadCategories();
  } catch (err) { toast(err.message,'error'); }
}

document.getElementById('addBtn').addEventListener('click', () => {
  if (currentPage === 'products')     openProductModal();
  if (currentPage === 'categories')   openCategoryModal();
  if (currentPage === 'specials')     openSpecialModal();
  if (currentPage === 'inventory')    openRestockPicker();
  if (currentPage === 'stockOut')     toast("Hisobdan o'chirish uchun mahsulot qatoridagi tugmasini bosing",'info');
  if (currentPage === 'memberships')   window.open('memberships.html','_blank');
  if (currentPage === 'serviceOrders') window.open('vehicles.html','_blank');
  if (currentPage === 'students')      toast("O'quvchi POS orqali qo'shiladi",'info');
  if (currentPage === 'groups')        toast("Guruhlar POS buyurtmalardan avtomatik to'planadi",'info');
  if (currentPage === 'cleaning')      toast('Buyurtma POS orqali qabul qilinadi','info');
  if (currentPage === 'hotelRooms')    openRoomModal();
  if (currentPage === 'hotelBookings') openBookingModal();
  if (currentPage === 'customers')    openCustomerAdd();
  if (currentPage === 'staff')        openStaffModal();
  if (currentPage === 'stations')     openStationModal();
});

// ── Init (barcha modul <script src> yuklangач ishga tushadi) ────────────────────
// DOMContentLoaded ichida: badge-init feature-modul funksiyalarini (updateHotelBadge,
// updateSalonExpiryBadge...) chaqiradi — ular alohida modul fayllarda. DCL barcha
// classic skript yuklangandan KEYIN ishga tushadi, shuning uchun hammasi aniqlangan.
document.addEventListener('DOMContentLoaded', () => {
document.getElementById('addBtn').style.display = 'none';
switchPage('dashboard');
setInterval(updatePendingBadge, 15000);
updatePendingBadge();
if (_storeTypes.includes(bizType)) {
  updateLowStockBadge();
  setInterval(updateLowStockBadge, 60000);
  // BOSQICH 27: reorder badge
  async function updateReorderBadge() {
    try {
      const d = await apiFetch('/analytics/reorder-alerts');
      const cnt = d.total || 0;
      const el = document.getElementById('reorderBadge');
      if (el) { el.textContent = cnt; el.style.display = cnt > 0 ? '' : 'none'; }
    } catch {}
  }
  updateReorderBadge();
  setInterval(updateReorderBadge, 120000);
}
if (_restTypes.includes(bizType)) {
  updateStopListBadge();
  setInterval(updateStopListBadge, 60000);
}
if (_storeTypes.includes(bizType)) {
  updateActiveDiscountsBadge();
  updateDebtBadge();
  setInterval(updateDebtBadge, 120000);
}
if (_salonTypes.includes(bizType)) {
  updateExpiringBadge();
  setInterval(updateExpiringBadge, 120000);
  updateSalonExpiryBadge();
  setInterval(updateSalonExpiryBadge, 120000);
}
if (_autoTypes.includes(bizType)) {
  updateServiceBadge();
  setInterval(updateServiceBadge, 60000);
  updateAutoReadyBadge();
  updateAutoDebtBadge();
  setInterval(updateAutoReadyBadge, 60000);
}
if (_schoolTypes.includes(bizType)) {
  apiFetch('/orders/?has_student=true&page_size=1').then(d => {
    const cnt = d.total || 0;
    const badge = document.getElementById('studentBadge');
    if (badge && cnt > 0) { badge.textContent = cnt; badge.style.display = ''; }
  }).catch(() => {});
}
if (_dryTypes.includes(bizType)) {
  updateCleaningBadge();
  setInterval(updateCleaningBadge, 60000);
  apiFetch('/orders/?has_cleaning=true&status=ready&page_size=1').then(d => {
    const cnt = d.total || 0;
    const badge = document.getElementById('dryReadyBadge');
    if (badge && cnt > 0) { badge.textContent = cnt; badge.style.display = ''; }
  }).catch(() => {});
}
if (_hotelBizTypes.includes(bizType)) {
  updateHotelBadge();
  setInterval(updateHotelBadge, 60000);
  updateHotelDebtBadge();
  setInterval(updateHotelDebtBadge, 120000);
}
if (bizType === 'pharmacy') {
  updateExpiryBadge();
  setInterval(updateExpiryBadge, 120000);
}
});  // ── Init tugadi (DOMContentLoaded) ──

// ── Staff CRUD ─────────────────────────────────────────────────────────────────
// ── Stations Admin CRUD ───────────────────────────────────────────────────────
let _editStationId = null;

async function loadStationsAdmin() {
  const tbody = document.getElementById('stationsBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center">Yuklanmoqda...</td></tr>';
  try {
    const rows = await apiFetch('/stations/');
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#888">Stansiyalar yo\'q. Qo\'shish uchun tugmani bosing.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(s => `
      <tr>
        <td>${s.id}</td>
        <td><span style="font-weight:600">${s.name}</span></td>
        <td><span style="display:inline-block;width:22px;height:22px;border-radius:4px;background:${s.color};border:1px solid #ccc;vertical-align:middle"></span> <small>${s.color}</small></td>
        <td>${s.has_display ? '<span class="badge badge-success">Ha</span>' : '<span class="badge badge-secondary">Yo\'q</span>'}</td>
        <td>${s.display_order}</td>
        <td>${s.is_active ? '<span class="badge badge-success">Faol</span>' : '<span class="badge badge-danger">Nofaol</span>'}</td>
        <td>
          <button class="btn btn-sm btn-outline" onclick="openStationModal(${s.id})">Tahrirlash</button>
          <button class="btn btn-sm btn-danger" onclick="deleteStation(${s.id})">O'chirish</button>
        </td>
      </tr>`).join('');
  } catch (err) { tbody.innerHTML = `<tr><td colspan="7" style="color:red">${err.message}</td></tr>`; }
}

function openStationModal(id = null) {
  _editStationId = id;
  document.getElementById('stationModalTitle').textContent = id ? 'Stansiyani tahrirlash' : 'Yangi stansiya';
  document.getElementById('stationName').value        = '';
  document.getElementById('stationColor').value       = '#d4b46c';
  document.getElementById('stationOrder').value       = '0';
  document.getElementById('stationHasDisplay').checked = true;
  document.getElementById('stationIsActive').checked  = true;
  if (id) {
    apiFetch(`/stations/${id}`).then(s => {
      document.getElementById('stationName').value         = s.name;
      document.getElementById('stationColor').value        = s.color || '#d4b46c';
      document.getElementById('stationOrder').value        = s.display_order ?? 0;
      document.getElementById('stationHasDisplay').checked = s.has_display;
      document.getElementById('stationIsActive').checked   = s.is_active;
    }).catch(() => {});
  }
  document.getElementById('stationModal').style.display = 'flex';
}

function closeStationModal() {
  document.getElementById('stationModal').style.display = 'none';
  _editStationId = null;
}

async function saveStation() {
  const name = document.getElementById('stationName').value.trim();
  if (!name) { toast('Stansiya nomini kiriting','error'); return; }
  const body = {
    name,
    color:         document.getElementById('stationColor').value,
    display_order: parseInt(document.getElementById('stationOrder').value) || 0,
    has_display:   document.getElementById('stationHasDisplay').checked,
    is_active:     document.getElementById('stationIsActive').checked,
  };
  try {
    const url    = _editStationId ? `${API_BASE}/stations/${_editStationId}` : `${API_BASE}/stations/`;
    const method = _editStationId ? 'PATCH' : 'POST';
    const res = await fetch(url, { method, headers: { 'Content-Type':'application/json', 'Authorization':`Bearer ${token}` }, body: JSON.stringify(body) });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || 'Xatolik'); }
    toast(_editStationId ? 'Stansiya yangilandi' : 'Stansiya qo\'shildi', 'success');
    closeStationModal();
    loadStationsAdmin();
    _cachedStations = null; // mahsulot formasidagi cache ni tozalash
  } catch (err) { toast(err.message, 'error'); }
}

async function deleteStation(id) {
  if (!confirm('Stansiyani o\'chirishni tasdiqlang?')) return;
  try {
    const res = await fetch(`${API_BASE}/stations/${id}`, { method: 'DELETE', headers: { 'Authorization':`Bearer ${token}` } });
    if (!res.ok && res.status !== 204) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || 'Xatolik'); }
    toast('Stansiya o\'chirildi', 'success');
    loadStationsAdmin();
    _cachedStations = null;
  } catch (err) { toast(err.message, 'error'); }
}

let _editStaffId = null;

async function loadStaff() {
  const search    = document.getElementById('staffSearch')?.value.trim() || '';
  const roleFilter = document.getElementById('staffRoleFilter')?.value || '';
  const params    = new URLSearchParams({ page:1, page_size:100 });
  if (search) params.set('search', search);
  const body = document.getElementById('staffBody');
  try {
    const data = await apiFetch('/users/?' + params);
    let users = data.items || data || [];
    if (roleFilter) users = users.filter(u => (u.role?.name || '').toLowerCase() === roleFilter);
    if (!users.length) {
      body.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text3)">Xodim topilmadi</td></tr>';
      return;
    }
    body.innerHTML = users.map(u => {
      const roleName = u.role?.name || u.role || '—';
      const roleColors = { admin:'badge-purple', manager:'badge-blue', waiter:'badge-blue', kitchen:'badge-amber', cashier:'badge-green' };
      const roleBadge = roleColors[roleName] || 'badge-blue';
      return `<tr>
        <td class="td-sub">${u.id}</td>
        <td class="td-bold">${u.full_name || '—'}</td>
        <td class="td-sub" style="font-family:monospace">${u.username || '—'}</td>
        <td><span class="badge ${roleBadge}">${roleName}</span></td>
        <td class="td-sub">${u.branch_id ? 'Filial #'+u.branch_id : '—'}</td>
        <td style="text-align:center">${u.has_pin ? '<span style="color:var(--gold)">●</span>' : '<span style="color:var(--text3)">○</span>'}</td>
        <td><span class="badge ${u.is_active?'badge-green':'badge-red'}">${u.is_active?'Faol':'Nofaol'}</span></td>
        <td class="td-actions">
          <button class="act-btn" title="Tahrirlash" onclick='openStaffModal(${JSON.stringify(u)})'><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="1.8"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="1.8"/></svg></button>
          <button class="act-btn" title="PIN tiklash" onclick="resetStaffPin(${u.id},'${(u.full_name||u.username).replace(/'/g,"\\'")}')" style="color:var(--gold)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><rect x="2" y="11" width="20" height="11" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M7 11V7a5 5 0 0110 0v4" stroke="currentColor" stroke-width="1.8"/></svg>
          </button>
          <button class="act-btn danger" title="O'chirish" onclick="deleteStaff(${u.id},'${(u.full_name||u.username).replace(/'/g,"\\'")}')" ${u.id === (JSON.parse(localStorage.getItem('user')||'{}').id) ? 'disabled' : ''}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" stroke="currentColor" stroke-width="1.8"/></svg>
          </button>
        </td>
      </tr>`;
    }).join('');
  } catch (err) { toast(err.message,'error'); }
}

let _staffRoles    = [];
let _staffBranches = [];

async function openStaffModal(user = null) {
  _editStaffId = user?.id || null;
  document.getElementById('smTitle').textContent = user ? 'Xodimni tahrirlash' : "Xodim qo'shish";
  document.getElementById('smPassLabel').textContent = user ? 'Yangi parol (bo\'sh = o\'zgarmas)' : 'Parol (yoki PIN)';
  document.getElementById('smFullName').value  = user?.full_name  || '';
  // Sintetik telefon (pin-… — faqat PIN bilan kiruvchi xodim) ko'rsatilmaydi.
  document.getElementById('smPhone').value     = (user?.phone && !String(user.phone).startsWith('pin-')) ? user.phone : '';
  document.getElementById('smUsername').value  = user?.username   || '';
  document.getElementById('smEmail').value     = user?.email      || '';
  document.getElementById('smPassword').value  = '';
  document.getElementById('smPin').value       = '';
  document.getElementById('smActive').checked  = user ? !!user.is_active : true;

  // Load roles
  if (!_staffRoles.length) {
    try { _staffRoles = await apiFetch('/roles/'); } catch { _staffRoles = []; }
  }
  // Rollarni biznes turiga qarab filtrlash (xato #4):
  // ovqatlanish (restoran/kafe/fast_food) — admin+cashier+kitchen+waiter;
  // magazin/xizmat — kitchen/waiter (oshxona/ofitsiant) rollari mantiqsiz → yashiriladi.
  const _foodBiz = ['restaurant','cafe','fast_food'].includes(bizType);
  const _foodOnlyRoles = ['kitchen','waiter'];
  const _visibleRoles = _staffRoles.filter(r =>
    _foodBiz || !_foodOnlyRoles.includes((r.name||'').toLowerCase())
  );
  const roleSel = document.getElementById('smRole');
  roleSel.innerHTML = '<option value="">— tanlang —</option>' +
    _visibleRoles.map(r => `<option value="${r.id}" ${user?.role_id===r.id?'selected':''}>${r.name}</option>`).join('');

  // Load branches
  if (!_staffBranches.length) {
    try { _staffBranches = await apiFetch('/branches/'); } catch { _staffBranches = []; }
  }
  const branchSel = document.getElementById('smBranch');
  branchSel.innerHTML = '<option value="">— tanlang —</option>' +
    _staffBranches.map(b => `<option value="${b.id}" ${user?.branch_id===b.id?'selected':''}>${b.name}</option>`).join('');

  const modal = document.getElementById('staffModal');
  modal.style.opacity='1'; modal.style.visibility='visible';
  document.getElementById('staffModalBox').style.transform='scale(1) translateY(0)';
  setTimeout(() => document.getElementById('smFullName').focus(), 100);
}

function closeStaffModal() {
  const modal = document.getElementById('staffModal');
  modal.style.opacity='0'; modal.style.visibility='hidden';
  document.getElementById('staffModalBox').style.transform='scale(.95) translateY(10px)';
}

async function saveStaff() {
  const fullName = document.getElementById('smFullName').value.trim();
  const username = document.getElementById('smUsername').value.trim();
  const email    = document.getElementById('smEmail').value.trim();
  const phone    = document.getElementById('smPhone').value.trim();
  const password = document.getElementById('smPassword').value;
  const pin      = document.getElementById('smPin').value.trim();
  const roleId   = parseInt(document.getElementById('smRole').value) || null;
  const branchId = parseInt(document.getElementById('smBranch').value) || null;
  const isActive = document.getElementById('smActive').checked;

  // Xodim faqat ISM + PIN bilan qo'shilishi mumkin — telefon/username/email/parol ixtiyoriy.
  // Kassir/ofitsiant 4-xonali PIN bilan tez kiradi (access_code + PIN). Kamida PIN yoki parol shart.
  if (!fullName) { toast('Ism majburiy','error'); return; }
  if (pin && (pin.length !== 4 || !/^\d{4}$/.test(pin))) { toast('PIN 4 xonali raqam bo\'lishi kerak','error'); return; }
  if (!_editStaffId && !password && !pin) { toast('Parol yoki PIN kiritilishi shart','error'); return; }

  const body = { full_name:fullName, is_active:isActive };
  if (phone)     body.phone     = phone;   // bo'sh telefon yuborilmaydi (PIN-only xodim)
  if (username)  body.username  = username;
  if (email)     body.email     = email;
  if (password)  body.password  = password;
  if (pin)       body.pin = pin;
  if (roleId)    body.role_id   = roleId;
  if (branchId)  body.branch_id = branchId;

  const btn = document.getElementById('smSaveBtn');
  btn.disabled = true; btn.textContent = 'Saqlanmoqda...';
  try {
    if (_editStaffId) {
      await apiFetchPost(`/users/${_editStaffId}`, body, 'PATCH');
    } else {
      if (!body.password && !body.pin) { toast('Parol yoki PIN kiritilishi shart','error'); return; }
      await apiFetchPost('/users/', body, 'POST');
    }
    toast(_editStaffId ? 'Yangilandi' : "Qo'shildi", 'success');
    closeStaffModal();
    loadStaff();
  } catch (err) { toast(err.message,'error'); }
  finally { btn.disabled=false; btn.textContent='Saqlash'; }
}

async function deleteStaff(id, name) {
  if (!confirm(`"${name}" xodimini o'chirmoqchimisiz?`)) return;
  try {
    const res = await fetch(`${API_BASE}/users/${id}`, { method:'DELETE', headers:{'Authorization':'Bearer '+token} });
    if (!res.ok) { const e=await res.json().catch(()=>({})); throw new Error(e.detail||'Xatolik'); }
    toast("O'chirildi",'success');
    loadStaff();
  } catch(e) { toast(e.message,'error'); }
}

async function resetStaffPin(id, name) {
  const pin = prompt(`"${name}" uchun yangi 4 xonali PIN kiriting (bo'sh qoldirsa PIN o'chiriladi):`);
  if (pin === null) return;
  if (pin !== '' && (pin.length !== 4 || !/^\d{4}$/.test(pin))) {
    toast('PIN 4 xonali raqam bo\'lishi kerak','error'); return;
  }
  try {
    await apiFetchPost(`/users/${id}`, { pin: pin || '' }, 'PATCH');
    toast(pin ? 'PIN yangilandi' : 'PIN o\'chirildi', 'success');
    loadStaff();
  } catch(e) { toast(e.message,'error'); }
}

async function apiFetchPost(path, body, method='POST') {
  const res = await fetch(API_BASE + path, {
    method, headers:{ 'Authorization':'Bearer '+token, 'Content-Type':'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) { const e=await res.json().catch(()=>({})); throw new Error(e.detail||res.statusText); }
  return res.json().catch(()=>({}));
}

document.getElementById('staffSearch')?.addEventListener('input', () => { if(currentPage==='staff') loadStaff(); });
document.getElementById('staffRoleFilter')?.addEventListener('change', () => { if(currentPage==='staff') loadStaff(); });

// ═══════════════════════════════════════════════════════
// BOSQICH 20 — Promotions (Aksiyalar)
// ═══════════════════════════════════════════════════════
let _promoEditId = null;
async function loadPromotions() {
  const type = document.getElementById('promoTypeFilter')?.value || '';
  const active = document.getElementById('promoActiveFilter')?.value || '';
  let url = `/promotions/?page_size=100`;
  if (type) url += `&promo_type=${type}`;
  if (active !== '') url += `&is_active=${active}`;
  const data = await apiFetch(url);
  const items = data.items || data || [];
  const tb = document.getElementById('promosTbody');
  if (!tb) return;
  if (!items.length) { tb.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#888">Aksiyalar yo\'q</td></tr>'; return; }
  const TYPE_LABELS = { buy_x_get_y:'2+Y bepul', flash_price:'Flash narx', min_amount:'Min summa', min_qty_discount:'Min miqdor' };
  tb.innerHTML = items.map(p => `<tr>
    <td><b>${escH(p.name)}</b></td>
    <td>${TYPE_LABELS[p.promo_type]||p.promo_type}</td>
    <td>${p.product_name||'—'}</td>
    <td style="font-size:.8rem;color:#666">${_promoCondition(p)}</td>
    <td style="color:#22c55e">${_promoDiscount(p)}</td>
    <td style="font-size:.8rem">${p.start_date?p.start_date.slice(0,10):''} ${p.end_date?'→ '+p.end_date.slice(0,10):''}</td>
    <td><span style="padding:.2rem .5rem;border-radius:20px;font-size:.8rem;background:${p.is_active?'#dcfce7':'#fee2e2'};color:${p.is_active?'#16a34a':'#dc2626'}">${p.is_active?'Faol':'Nofaol'}</span></td>
    <td style="display:flex;gap:.25rem">
      <button class="tb-btn" onclick="togglePromo(${p.id},${!p.is_active})">${p.is_active?'O\'ch':'Yoq'}</button>
      <button class="tb-btn" style="color:#ef4444" onclick="deletePromo(${p.id})">O'ch</button>
    </td>
  </tr>`).join('');
  const badge = document.getElementById('promosBadge');
  if (badge) { const cnt = items.filter(p=>p.is_active).length; badge.textContent = cnt; badge.style.display = cnt ? '' : 'none'; }
}
function _promoCondition(p) {
  if (p.promo_type==='buy_x_get_y') return `${p.buy_qty} olsang → ${p.get_qty} bepul`;
  if (p.promo_type==='flash_price') return `Flash: ${fmtNum(p.flash_price)} so'm`;
  if (p.promo_type==='min_amount') return `Min: ${fmtNum(p.min_purchase_amount)} so'm`;
  if (p.promo_type==='min_qty_discount') return `Min: ${p.min_purchase_qty} dona`;
  return '';
}
function _promoDiscount(p) {
  if (p.promo_type==='buy_x_get_y') return `${p.get_qty} dona bepul`;
  if (p.promo_type==='flash_price') return `${fmtNum(p.flash_price)} so'm`;
  if (p.discount_type==='percentage') return `-${p.discount_value}%`;
  return `-${fmtNum(p.discount_value)} so'm`;
}
async function openPromoModal(id=null) {
  _promoEditId = id;
  document.getElementById('promoModalTitle').textContent = id ? 'Aksiyani tahrirlash' : 'Yangi aksiya';
  document.getElementById('pmName').value = '';
  document.getElementById('pmType').value = 'buy_x_get_y';
  document.getElementById('pmBuyQty').value = 2;
  document.getElementById('pmGetQty').value = 1;
  document.getElementById('pmFlashPriceVal').value = '';
  document.getElementById('pmMinAmt').value = '';
  document.getElementById('pmDiscVal').value = '';
  document.getElementById('pmDiscVal2').value = '';
  document.getElementById('pmMinQtyVal').value = '';
  document.getElementById('pmStartDate').value = '';
  document.getElementById('pmEndDate').value = '';
  document.getElementById('pmTimeFrom').value = '';
  document.getElementById('pmTimeTo').value = '';
  // Load products
  const prods = await apiFetch(`/products/?page_size=200&is_active=true`);
  const sel = document.getElementById('pmProduct');
  sel.innerHTML = '<option value="">— Barcha mahsulotlar —</option>' +
    (prods.items||[]).map(p=>`<option value="${p.id}">${escH(p.name)}</option>`).join('');
  promoTypeChanged();
  openModal('promoModal');
}
function promoTypeChanged() {
  const t = document.getElementById('pmType')?.value;
  document.getElementById('pmBuyXGetY').style.display = t==='buy_x_get_y' ? '' : 'none';
  document.getElementById('pmFlashPrice').style.display = t==='flash_price' ? '' : 'none';
  document.getElementById('pmMinAmount').style.display = t==='min_amount' ? '' : 'none';
  document.getElementById('pmMinQty').style.display = t==='min_qty_discount' ? '' : 'none';
}
async function savePromotion() {
  const type = document.getElementById('pmType').value;
  const body = {
    name: document.getElementById('pmName').value.trim(),
    promo_type: type,
    product_id: +document.getElementById('pmProduct').value || null,
    buy_qty: +document.getElementById('pmBuyQty').value || 2,
    get_qty: +document.getElementById('pmGetQty').value || 1,
    flash_price: +document.getElementById('pmFlashPriceVal').value || null,
    min_purchase_amount: +document.getElementById('pmMinAmt').value || 0,
    discount_type: document.getElementById('pmDiscType').value || 'percentage',
    discount_value: +document.getElementById('pmDiscVal').value || +document.getElementById('pmDiscVal2').value || 0,
    min_purchase_qty: +document.getElementById('pmMinQtyVal').value || 0,
    start_date: document.getElementById('pmStartDate').value || null,
    end_date: document.getElementById('pmEndDate').value || null,
    time_from: document.getElementById('pmTimeFrom').value || null,
    time_to: document.getElementById('pmTimeTo').value || null,
    is_active: true,
  };
  if (!body.name) return toast('Nomi kiritilmagan', 'error');
  const method = _promoEditId ? 'PUT' : 'POST';
  const url = _promoEditId ? `/promotions/${_promoEditId}` : `/promotions/`;
  await apiFetchPost(url, body, method);   // apiFetch faqat GET — mutation uchun apiFetchPost
  closeModal('promoModal');
  loadPromotions();
  toast('Saqlandi!');
}
async function togglePromo(id, active) {
  await apiFetchPost(`/promotions/${id}`, { is_active: active }, 'PUT');
  loadPromotions();
}
async function deletePromo(id) {
  if (!confirm('Aksiyani o\'chirasizmi?')) return;
  await apiFetchPost(`/promotions/${id}`, null, 'DELETE');
  loadPromotions();
  toast('O\'chirildi');
}

// ═══════════════════════════════════════════════════════
// BOSQICH 20 — Quick Sell
// ═══════════════════════════════════════════════════════
let _qsSelectedProductId = null;
async function loadQuickSellItems() {
  const items = await apiFetch(`/quick-sell/`);
  const grid = document.getElementById('quickSellGrid');
  if (!grid) return;
  if (!items.length) { grid.innerHTML = '<p style="color:#888;grid-column:1/-1">Tez sotuv mahsulotlari yo\'q. "Qo\'shish" tugmasini bosing.</p>'; return; }
  grid.innerHTML = items.map(item => `<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:.75rem;text-align:center;position:relative">
    <div style="width:40px;height:40px;border-radius:50%;background:${item.color};margin:0 auto .5rem;display:flex;align-items:center;justify-content:center;color:#fff;font-size:1.2rem">
      ${escH(item.display_name?.charAt(0)||'?')}
    </div>
    <div style="font-weight:600;font-size:.9rem">${escH(item.display_name)}</div>
    <div style="color:#22c55e;font-size:.85rem">${fmtNum(item.price||0)} so'm</div>
    <button onclick="removeQuickSell(${item.id})" style="position:absolute;top:6px;right:6px;background:none;border:none;color:#ef4444;cursor:pointer;font-size:1.1rem" title="O'chirish">×</button>
  </div>`).join('');
}
async function openAddQuickSellModal() {
  _qsSelectedProductId = null;
  document.getElementById('qsSearch').value = '';
  document.getElementById('qsName').value = '';
  document.getElementById('qsColor').value = '#4CAF50';
  document.getElementById('qsProductList').style.display = 'none';
  openModal('quickSellModal');
}
async function searchQsProducts() {
  const q = document.getElementById('qsSearch').value.trim();
  if (q.length < 1) { document.getElementById('qsProductList').style.display = 'none'; return; }
  const data = await apiFetch(`/products/?search=${encodeURIComponent(q)}&page_size=10&is_active=true`);
  const list = document.getElementById('qsProductList');
  const items = data.items || [];
  if (!items.length) { list.innerHTML = '<div style="padding:.5rem;color:#888">Topilmadi</div>'; list.style.display = ''; return; }
  list.innerHTML = items.map(p => `<div onclick="selectQsProduct(${p.id},'${escH(p.name)}')" style="padding:.5rem .75rem;cursor:pointer;border-bottom:1px solid #f3f4f6" onmouseover="this.style.background='#f3f4f6'" onmouseout="this.style.background=''">${escH(p.name)} — ${fmtNum(p.price)} so'm</div>`).join('');
  list.style.display = '';
}
function selectQsProduct(id, name) {
  _qsSelectedProductId = id;
  document.getElementById('qsSearch').value = name;
  document.getElementById('qsName').value = name.slice(0,15);
  document.getElementById('qsProductList').style.display = 'none';
}
async function addQuickSellItem() {
  if (!_qsSelectedProductId) return toast('Mahsulot tanlanmagan', 'error');
  const body = { product_id: _qsSelectedProductId, display_name: document.getElementById('qsName').value.trim() || null, color: document.getElementById('qsColor').value };
  await apiFetchPost(`/quick-sell/?product_id=${_qsSelectedProductId}&display_name=${encodeURIComponent(body.display_name||'')}&color=${encodeURIComponent(body.color)}`, null, 'POST');
  closeModal('quickSellModal');
  loadQuickSellItems();
  toast('Qo\'shildi!');
}
async function removeQuickSell(id) {
  if (!confirm('O\'chirasizmi?')) return;
  await apiFetchPost(`/quick-sell/${id}`, null, 'DELETE');
  loadQuickSellItems();
  toast('O\'chirildi');
}

// BOSQICH 6: Tizim A (Purchase Orders / eski Priyomka) JS olib tashlandi.
// Yangi Tizim B: purchase_receipts.html / suppliers.html / supplier_debt.html.

