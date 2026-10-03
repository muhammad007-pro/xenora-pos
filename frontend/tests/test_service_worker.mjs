/**
 * SERVICE WORKER — versiya, kesh tozalash, kod yangilanishi, offline.
 *
 * ═══ NEGA BU TEST BOR ═══
 *
 * 2026-10-03 da aniqlandi: `service-worker.js` dagi `APP_VERSION` **v1.55.1**
 * da qotib qolgan edi — v1.10.1 dan keyin 6+ reliz (1.10.x … 1.12.17)
 * davomida ko'tarilmagan. Eski kesh FAQAT shu qiymat o'zgarganda tozalanadi,
 * ya'ni tozalash hech qachon ishlamagan.
 *
 * Ustiga ikki jiddiy nuqson bor edi:
 *
 *   1. SCOPE. Fayl `/pwa/service-worker.js` da turardi → standart scope
 *      `/pwa/`. Service worker `/app/*`, `/js/*` so'rovlarini UMUMAN
 *      ko'rmasdi (`pwa/manifest.json` esa `"scope": "/"` deb yozilgan).
 *      Endi fayl ildizda va `register()` ga `{scope:'/'}` beriladi.
 *
 *   2. KOD UCHUN CACHE-FIRST. `js/core/*` ES MODUL va bir-birini `import`
 *      qiladi. Cache-first'da eski `receipt-print.js` keshdan kelib, uning
 *      yangi `import './code128.js'` bog'liqligi tarmoqdan izlanardi —
 *      ikki versiya aralashib, import yiqilsa chek butunlay bosilmaydi.
 *      Endi kod uchun network-first + timeout.
 *
 * ⚠️ GOLDEN: OFFLINE BUZILMASIN. Tarmoq yo'q bo'lsa keshdagi nusxa
 * qaytarilishi SHART (3 va 4-bo'limlar aynan shuni qulflaydi).
 *
 * Service worker'ni HAQIQATAN ishga tushiramiz: fayl `node:vm` sandbox'ida
 * baholanadi, `self`/`caches`/`fetch` esa maketlanadi. Ya'ni test faylning
 * ROSTMANA xatti-harakatini o'lchaydi, izohini emas.
 *
 * Ishga tushirish:  node frontend/tests/test_service_worker.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const ROOT = resolve('frontend');
const SW_PATH = resolve(ROOT, 'service-worker.js');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

// ══════════════════════════════════════════════════════════════════════════════
// Maketlar — brauzer SW muhitining kerakli qismi
// ══════════════════════════════════════════════════════════════════════════════

class FakeResponse {
  constructor(body, { status = 200 } = {}) { this.body = body; this.status = status; }
  clone() { return new FakeResponse(this.body, { status: this.status }); }
}

const ORIGIN = 'https://app.xenora.uz';

// Brauzer `caches.match('/shared/offline.html')` ni ORIGIN'ga nisbatan hal
// qiladi — maket ham xuddi shunday qilishi kerak, aks holda nisbiy yo'l
// bilan saqlangan/izlangan yozuvlar bir-birini topmaydi.
const keyOf = req => new URL(typeof req === 'string' ? req : req.url, ORIGIN).href;

class FakeCache {
  constructor() { this.map = new Map(); }
  async match(req)       { return this.map.get(keyOf(req)); }
  async put(req, res)    { this.map.set(keyOf(req), res); }
  async addAll(urls)     { for (const u of urls) this.map.set(keyOf(u), new FakeResponse('pre:' + u)); }
  async delete(req)      { return this.map.delete(keyOf(req)); }
}

function makeCaches() {
  const stores = new Map();
  return {
    stores,
    async open(name) {
      if (!stores.has(name)) stores.set(name, new FakeCache());
      return stores.get(name);
    },
    async keys() { return [...stores.keys()]; },
    async delete(name) { return stores.delete(name); },
    async match(req) {
      for (const c of stores.values()) {
        const hit = await c.match(req);
        if (hit) return hit;
      }
      return undefined;
    },
  };
}

/**
 * Service worker'ni sandbox'da yuklaydi va ishlov beruvchilarni qaytaradi.
 *
 * `timeScale` — SW ichidagi timeout 3500 ms. Testni 3.5 soniya kutishga
 * majburlamaslik uchun `setTimeout` kechikishini kichraytiramiz. Qiymat
 * ham yozib olinadi: timeout HAQIQATAN ishlatilganini tasdiqlash uchun.
 */
function loadSW({ fetchImpl, timeScale = 1 / 350 }) {
  const handlers = {};
  const delays = [];
  const caches = makeCaches();

  const self = {
    addEventListener: (type, fn) => { handlers[type] = fn; },
    location: { origin: ORIGIN },
    skipWaiting: async () => {},
    clients: { claim: async () => {} },
    registration: {},
  };

  const sandbox = {
    self, caches, URL, Response: FakeResponse, console,
    fetch: fetchImpl,
    indexedDB: {},
    setTimeout: (fn, ms) => { delays.push(ms); return setTimeout(fn, Math.max(1, ms * timeScale)); },
    clearTimeout,
    Promise, JSON, Map, Set, RegExp, Error,
  };
  sandbox.globalThis = sandbox;

  vm.createContext(sandbox);
  vm.runInContext(readFileSync(SW_PATH, 'utf8'), sandbox, { filename: 'service-worker.js' });

  return { handlers, caches, delays, sandbox };
}

/** `fetch` ishlov beruvchisini chaqirib, javobni oladi. */
async function doFetch(handlers, request) {
  let captured;
  const event = { request, respondWith: p => { captured = p; } };
  handlers.fetch(event);
  return captured === undefined ? '__O\'TKAZIB_YUBORILDI__' : await captured;
}

const req = (url, extra = {}) => ({ url, method: 'GET', mode: 'no-cors', ...extra });

// ══════════════════════════════════════════════════════════════════════════════
// 1) VERSIYA — service worker va version.js BITTA manbadan
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 1) Versiya yagona manba ──');

const swSrc      = readFileSync(SW_PATH, 'utf8');
const versionSrc = readFileSync(resolve(ROOT, 'shared/version.js'), 'utf8');

const swVer  = swSrc.match(/^const APP_VERSION\s+= '([\d.]+)';/m)?.[1];
const appVer = versionSrc.match(/^window\.APP_VERSION = '([\d.]+)';/m)?.[1];

check('1_sw_versiya_topildi', !!swVer, true);
check('1_version_js_topildi', !!appVer, true);
check('1_IKKISI_BIR_XIL', swVer, appVer);
// Eski "mustaqil sxema" (v1.55.1 kabi) qaytib kelmasin
check('1_eski_v_prefiks_yoq', /^const APP_VERSION\s+= 'v/m.test(swSrc), false);

// Kesh nomlari versiyaga bog'langanmi (aks holda tozalash ishlamaydi)
check('1_kesh_nomi_versiyali', /xenora-static-\$\{APP_VERSION\}/.test(swSrc), true);

// ══════════════════════════════════════════════════════════════════════════════
// 2) SCOPE — fayl ildizda, ro'yxatga olish `/` bilan
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 2) Scope ──');

// Fayl ildizda bo'lishi SHART: scope = skript turgan papka.
let swAtRoot = true;
try { readFileSync(SW_PATH); } catch { swAtRoot = false; }
check('2_sw_ildizda', swAtRoot, true);

let swAtOldPath = true;
try { readFileSync(resolve(ROOT, 'pwa/service-worker.js')); } catch { swAtOldPath = false; }
check('2_eski_joyda_YOQ', swAtOldPath, false);

const regSrc = readFileSync(resolve(ROOT, 'shared/register-sw.js'), 'utf8');
check('2_ildizdan_royxat', /register\('\/service-worker\.js',\s*\{\s*scope:\s*'\/'\s*\}\)/.test(regSrc), true);
check('2_eski_royxat_tozalanadi', /getRegistrations/.test(regSrc) && /unregister\(\)/.test(regSrc), true);

// Hech bir sahifa eski yo'lni ro'yxatga olmasin
const pages = ['index.html', 'shared/login.html', 'app/pos.html', 'js/main.js'];
const stale = pages.filter(p => /serviceWorker\.register\(\s*['"][^'"]*pwa\/service-worker/.test(
  readFileSync(resolve(ROOT, p), 'utf8')));
check('2_sahifalarda_eski_yol_yoq', stale, []);

// manifest `scope` bilan izchil
const manifest = JSON.parse(readFileSync(resolve(ROOT, 'pwa/manifest.json'), 'utf8'));
check('2_manifest_scope_bilan_izchil', manifest.scope, '/');

// ══════════════════════════════════════════════════════════════════════════════
// 3) KOD YANGILANISHI — js/core/* YANGI versiyada yangilanadi
//    (aynan shu nuqson code128.js ni yashirgan bo'lardi)
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 3) Kod yangilanishi (network-first) ──');

{
  const url = 'https://app.xenora.uz/js/core/receipt-print.js';
  const { handlers, caches } = loadSW({
    fetchImpl: async () => new FakeResponse('YANGI_KOD'),
  });

  // Keshda ESKI nusxa turibdi (brauzer ilgari yuklagan)
  const cache = await caches.open(`xenora-static-${swVer}`);
  await cache.put({ url }, new FakeResponse('ESKI_KOD'));

  const res = await doFetch(handlers, req(url));
  check('3_yangi_kod_keldi', res.body, 'YANGI_KOD');

  // Kesh ham yangilanishi kerak (keyingi offline yuklash yangi bo'lsin)
  const after = await cache.match({ url });
  check('3_kesh_ham_yangilandi', after.body, 'YANGI_KOD');
}

// CSS ham kod qatorida
{
  const url = 'https://app.xenora.uz/styles/main.css';
  const { handlers, caches } = loadSW({ fetchImpl: async () => new FakeResponse('YANGI_CSS') });
  const cache = await caches.open(`xenora-static-${swVer}`);
  await cache.put({ url }, new FakeResponse('ESKI_CSS'));
  const res = await doFetch(handlers, req(url));
  check('3_css_ham_yangilanadi', res.body, 'YANGI_CSS');
}

// RASM esa cache-first qoladi (tezlik — mazmuni o'zgarmaydi)
{
  const url = 'https://app.xenora.uz/assets/icons/logo.svg';
  const { handlers, caches } = loadSW({ fetchImpl: async () => new FakeResponse('YANGI_RASM') });
  const cache = await caches.open(`xenora-static-${swVer}`);
  await cache.put({ url }, new FakeResponse('KESHDAGI_RASM'));
  const res = await doFetch(handlers, req(url));
  check('3_rasm_cache_first_qoldi', res.body, 'KESHDAGI_RASM');
}

// ══════════════════════════════════════════════════════════════════════════════
// 4) GOLDEN — OFFLINE BUZILMASIN
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 4) GOLDEN: offline ──');

// 4a) Tarmoq YIQILDI + keshda bor → keshdagi nusxa
{
  const url = 'https://app.xenora.uz/js/core/pos.js';
  const { handlers, caches } = loadSW({
    fetchImpl: async () => { throw new Error('tarmoq yo\'q'); },
  });
  const cache = await caches.open(`xenora-static-${swVer}`);
  await cache.put({ url }, new FakeResponse('KESHDAGI_KOD'));

  const res = await doFetch(handlers, req(url));
  check('4a_offline_keshdan_ishlaydi', res.body, 'KESHDAGI_KOD');
}

// 4b) Tarmoq SEKIN (javob bermaydi) → timeout dan keyin kesh
{
  const url = 'https://app.xenora.uz/js/core/api.js';
  const { handlers, caches, delays } = loadSW({
    fetchImpl: () => new Promise(() => {}),   // hech qachon tugamaydi
  });
  const cache = await caches.open(`xenora-static-${swVer}`);
  await cache.put({ url }, new FakeResponse('KESHDAGI_API'));

  const res = await doFetch(handlers, req(url));
  check('4b_sekin_tarmoq_keshga_tushdi', res.body, 'KESHDAGI_API');
  check('4b_timeout_ishlatildi', delays.length > 0 && delays.every(d => d > 0 && d <= 10000), true);
}

// 4c) Tarmoq yiqildi + keshda ham YO'Q → 503 (sahifa osilib qolmasin)
{
  const { handlers } = loadSW({ fetchImpl: async () => { throw new Error('yoq'); } });
  const res = await doFetch(handlers, req('https://app.xenora.uz/js/core/yangi.js'));
  check('4c_kesh_yoq_tarmoq_yoq', res.status, 503);
}

// 4d) Navigatsiya offline → offline.html fallback
{
  const url = 'https://app.xenora.uz/app/pos.html';
  const { handlers, caches } = loadSW({ fetchImpl: async () => { throw new Error('yoq'); } });
  const cache = await caches.open(`xenora-static-${swVer}`);
  await cache.put({ url: 'https://app.xenora.uz/shared/offline.html' }, new FakeResponse('OFFLINE_SAHIFA'));

  const res = await doFetch(handlers, req(url, { mode: 'navigate' }));
  check('4d_navigatsiya_offline_fallback', res.body, 'OFFLINE_SAHIFA');
}

// 4e) O'ZGARTIRUVCHI so'rov (buyurtma POST) hech qachon keshlanmaydi —
//     offline navbat mantig'i shunga tayanadi (js/core/sync.js)
{
  const url = 'https://app.xenora.uz/api/v1/orders/';
  const { handlers, caches } = loadSW({ fetchImpl: async () => { throw new Error('yoq'); } });
  const res = await doFetch(handlers, req(url, { method: 'POST' }));
  check('4e_POST_503_qaytaradi', res.status, 503);
  const keys = await caches.keys();
  const total = (await Promise.all(keys.map(async k => (await caches.open(k)).map.size)))
    .reduce((a, b) => a + b, 0);
  check('4e_POST_keshlanmadi', total, 0);
}

// ══════════════════════════════════════════════════════════════════════════════
// 5) VERSIYA O'ZGARSA ESKI KESH TOZALANADI
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 5) Eski kesh tozalanishi ──');

{
  const { handlers, caches } = loadSW({ fetchImpl: async () => new FakeResponse('x') });

  // Eski relizlardan qolgan keshlar (shu jumladan qotib qolgan v1.55.1)
  await caches.open('restopos-static-v1.55.1');
  await caches.open('restopos-api-v1.55.1');
  await caches.open('xenora-static-1.12.16');
  // Joriy versiya keshlari
  await caches.open(`xenora-static-${swVer}`);
  await caches.open(`xenora-api-${swVer}`);

  check('5_oldin_kesh_soni', (await caches.keys()).length, 5);

  // activate — barcha mos kelmaydigan keshni o'chiradi
  let waited;
  handlers.activate({ waitUntil: p => { waited = p; } });
  await waited;

  const left = (await caches.keys()).sort();
  check('5_keyin_faqat_joriy_qoldi', left, [`xenora-api-${swVer}`, `xenora-static-${swVer}`]);
  check('5_qotib_qolgan_v1.55.1_ochdi', left.includes('restopos-static-v1.55.1'), false);
  check('5_oldingi_reliz_keshi_ochdi', left.includes('xenora-static-1.12.16'), false);
}

// ══════════════════════════════════════════════════════════════════════════════
// 6) BOSHQA ORIGIN — qo'l tegizilmaydi (cdnjs'dan Chart.js)
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 6) Boshqa origin ──');

{
  const { handlers } = loadSW({ fetchImpl: async () => new FakeResponse('SW_ARALASHDI') });
  const res = await doFetch(handlers, req('https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js'));
  check('6_cdn_otkazib_yuborildi', res, '__O\'TKAZIB_YUBORILDI__');
}

// ══════════════════════════════════════════════════════════════════════════════
// 7) O'rnatish (install) — ro'yxatdagi fayl yo'q bo'lsa ham SW o'rnatiladi
//    (ilgari `admin.js` 404 i butun offline rejimni yiqitgan)
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 7) Install chidamliligi ──');

{
  const { handlers, caches } = loadSW({ fetchImpl: async () => new FakeResponse('x') });
  // addAll ni ataylab yiqitamiz
  const orig = caches.open;
  caches.open = async name => {
    const c = await orig.call(caches, name);
    c.addAll = async () => { throw new Error('404'); };
    return c;
  };

  let waited, threw = false;
  handlers.install({ waitUntil: p => { waited = p; } });
  try { await waited; } catch { threw = true; }
  check('7_addAll_404_da_install_yiqilmadi', threw, false);
}

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
