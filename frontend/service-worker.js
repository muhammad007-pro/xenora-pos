/**
 * XENORA Service Worker
 *
 * ⚠️ BU FAYL ILDIZDA TURISHI SHART (`frontend/service-worker.js`).
 * Service worker faqat O'Z PAPKASI va undan pastini boshqaradi (standart
 * scope = skript turgan papka). Ilgari fayl `/pwa/service-worker.js` edi,
 * ya'ni scope `/pwa/` — u `/app/pos.html`, `/js/core/*.js` larni UMUMAN
 * ko'rmasdi: `fetch` ishlov beruvchi ular uchun hech qachon ishlamagan,
 * offline fallback ham ishlamagan. `pwa/manifest.json` esa `"scope": "/"`
 * deb yozilgan — ya'ni niyat boshidan `/` edi.
 *
 * Ildizdan berilganda scope `/` AVTOMATIK bo'ladi va serverdan hech qanday
 * qo'shimcha header talab qilinmaydi. (`Service-Worker-Allowed: /` bilan
 * `/pwa/` dan ham bo'lardi, lekin u header ishlab chiqarish nginx'ida
 * YO'Q — repo'dagi `nginx/conf.d/common.conf` deploy qilinmagan. Shunga
 * tayanish `register({scope:'/'})` ni SecurityError bilan yiqitardi va
 * offline rejimni butunlay o'chirardi.)
 *
 * Strategiyalar:
 *   kod (js/mjs/css) → Network First + timeout, keshga fallback  ⬅ qarang (*)
 *   boshqa statik    → Cache First (rasm/ikonka/shrift — o'zgarmaydi)
 *   API GET          → Stale-While-Revalidate
 *   API POST/PATCH   → Network Only
 *   Navigatsiya      → Network First + offline.html fallback
 *   WebSocket / boshqa origin → o'tkazib yuboriladi
 *
 * (*) NEGA KOD UCHUN CACHE FIRST EMAS: kod fayllari ES MODUL va bir-birini
 * `import` qiladi. Cache-first'da brauzer eski `receipt-print.js` ni keshdan
 * olib, uning yangi `import './code128.js'` bog'liqligini esa tarmoqdan
 * izlaydi — ikki versiya ARALASHADI. Import yiqilsa modul butunlay
 * yuklanmaydi, ya'ni chek bosilmay qoladi. Network-first'da onlayn bo'lsa
 * doim izchil (bir xil versiyali) to'plam keladi.
 *
 * OFFLINE BUZILMAYDI: tarmoq yiqilsa yoki TIMEOUT oshsa keshdagi nusxa
 * qaytariladi — ya'ni offline xatti-harakat avvalgidek. Timeout sekin
 * internetda POS'ni osib qo'ymaslik uchun (kassir kutib turmasin).
 *
 * Background Sync:
 *   'sync-orders' tegi bo'lganda navbatdagi buyurtmalarni yuboradi
 */

// ⚠️ VERSIYA — `frontend/shared/version.js` BILAN BIR XIL BO'LISHI SHART.
// Qo'lda tahrir qilmang: `py scripts/bump_version.py <versiya>` hammasini
// birga ko'taradi. `frontend/tests/test_service_worker.mjs` ikkisining
// tengligini qulflaydi (CI'da ishlaydi) — mos kelmasa test yiqiladi.
//
// NEGA `importScripts('/shared/version.js')` EMAS (bitta manba bo'lardi-ku):
//   1. `importScripts` SINXRON va `install` paytida ishlaydi — fayl 404 bo'lsa
//      service worker UMUMAN o'rnatilmaydi, ya'ni offline rejim o'ladi.
//   2. Brauzer yangilanishni SW SKRIPTI BAYTLARI o'zgarganda aniqlaydi.
//      Versiya boshqa faylda bo'lsa bu fayl o'zgarmaydi va yangilanish
//      aniqlanishi brauzer tafsilotiga (import'larni revalidatsiya qilishiga)
//      bog'lanib qoladi. Literal qiymat — kafolat.
const APP_VERSION   = '1.13.2';
const STATIC_CACHE  = `xenora-static-${APP_VERSION}`;
const API_CACHE     = `xenora-api-${APP_VERSION}`;
const API_BASE      = '/api';

// Kod fayllari uchun tarmoqni qancha kutamiz (ms). Oshsa keshga tushamiz.
// Sekin mobil internetda kassir kutib qolmasligi uchun ataylab qisqa.
const CODE_NET_TIMEOUT_MS = 3500;

// Versiya o'zgarishida yangilanadigan statik resurslar
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/shared/login.html',
    '/shared/offline.html',
    '/app/pos.html',
    '/app/customer-display.html',
    '/app/kitchen.html',
    '/app/admin.html',
    '/app/combo.html',
    '/app/happy_hour.html',
    '/app/membership.html',
    '/app/reservations.html',
    '/app/appointments.html',
    '/app/cafes.html',
    '/app/attendance.html',
    '/styles/main.css',
    '/styles/mobile.css',
    '/styles/pages/pos.css',
    '/styles/pages/kitchen.css',
    '/styles/pages/admin.css',
    '/styles/base/variables.css',
    '/js/core/api.js',
    '/js/core/auth.js',
    '/js/core/auth-guard.js',
    '/js/core/config.js',
    '/js/core/error-handler.js',
    '/js/core/socket.js',
    '/js/core/state.js',
    '/js/core/db.js',
    '/js/core/sync.js',
    '/js/core/tenant-backup.js',
    '/js/core/theme.js',
    '/js/core/features.js',
    '/js/core/sidebar.js',
    '/js/main.js',
    '/js/modules/pos.js',
    '/js/modules/kitchen.js',
    // '/js/modules/admin.js' — O'CHIRILDI (o'lik kod). Uni hech bir sahifa
    // yuklamasdi va importlari mavjud bo'lmagan papkalarga qarardi. Ro'yxatda
    // qolsa `cache.addAll` 404 da REJECT bo'lib, SW o'rnatilishi butunlay
    // yiqilardi — ya'ni offline rejim ishlamay qolardi.
    '/js/modules/barcode.js',
    '/js/modules/camera-scanner.js',
    '/js/ui/toast.js',
    '/js/ui/modal.js',
    '/js/utils/formatter.js',
    '/js/utils/helpers.js',
    '/assets/icons/logo.svg',
];

// Keshlanadigan API endpointlar (GET — Stale-While-Revalidate)
const CACHEABLE_API = [
    '/products',
    '/products/all',
    '/categories',
    '/categories/all',
    '/tables',
    '/tables/all',
    '/customers',
];

// ── O'rnatish ─────────────────────────────────────────────────────────────

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(cache => cache.addAll(STATIC_ASSETS).catch(err => {
                // Bitta fayl yo'q bo'lsa butun o'rnatish bekor bo'lmasin
                console.warn('[SW] Some assets failed to cache:', err);
            }))
            .then(() => self.skipWaiting())
    );
});

// ── Faollashtirish ────────────────────────────────────────────────────────
// Versiya o'zgarsa STATIC_CACHE/API_CACHE nomlari ham o'zgaradi va bu yerda
// MOS KELMAYDIGAN HAMMA kesh o'chiriladi. Ya'ni "versiya ko'tarildi → eski
// kesh majburan tozalandi" kafolati shu bir nechta satrda.
//
// ⚠️ Shu sabab APP_VERSION har relizda ko'tarilishi SHART. U `v1.55.1` da
// qotib qolgan edi (v1.10.1 dan keyin 6+ reliz) — natijada bu tozalash hech
// qachon ishlamagan va brauzer kassirlar eski kodni ko'rishda davom etgan.
// Endi `scripts/bump_version.py` + CI testi buni qulflaydi.

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys
                    .filter(k => k !== STATIC_CACHE && k !== API_CACHE)
                    .map(k => caches.delete(k))
            )
        ).then(() => self.clients.claim())
    );
});

// ── Fetch ushlash ─────────────────────────────────────────────────────────

// Kod fayli (ES modul zanjiri) — versiyalar ARALASHMASLIGI kerak.
function _isCode(pathname) {
    return /\.(?:js|mjs|css)$/i.test(pathname);
}

self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    // WebSocket — o'tkazib yuboramiz
    if (url.protocol === 'ws:' || url.protocol === 'wss:') return;

    // BOSHQA ORIGIN (cdnjs'dan Chart.js kabi) — umuman qo'l tegizmaymiz.
    // Keshlashning foydasi yo'q (javob "opaque"), brauzer o'zi yaxshiroq
    // bajaradi. Ilgari bular ham cacheFirst'ga tushardi.
    if (url.origin !== self.location.origin) return;

    // O'ZGARTIRUVCHI so'rovlar (API bo'lsa ham, bo'lmasa ham) keshulanmaydi
    if (request.method !== 'GET') {
        event.respondWith(networkOnly(request));
        return;
    }

    // GET API — stale-while-revalidate (faqat ro'yxatdagilar)
    if (url.pathname.startsWith(API_BASE)) {
        if (_isCacheableAPI(url.pathname)) {
            event.respondWith(staleWhileRevalidate(request, API_CACHE));
        } else {
            event.respondWith(networkOnly(request));
        }
        return;
    }

    // Navigatsiya — network first, offline fallback
    if (request.mode === 'navigate') {
        event.respondWith(networkFirstNav(request));
        return;
    }

    // KOD (js/mjs/css) — network first + timeout, keshga fallback.
    // Sarlavhadagi (*) izohga qara: ES modul zanjirida eski va yangi
    // versiyalar aralashmasligi uchun.
    if (_isCode(url.pathname)) {
        event.respondWith(networkFirstCode(request, STATIC_CACHE));
        return;
    }

    // Qolgan statik (rasm, ikonka, shrift, svg) — cache first.
    // Bular mazmuni o'zgarmaydi; tezlik muhimroq.
    event.respondWith(cacheFirst(request, STATIC_CACHE));
});

function _isCacheableAPI(pathname) {
    return CACHEABLE_API.some(p => pathname.includes(p));
}

// ── Strategiyalar ─────────────────────────────────────────────────────────

async function cacheFirst(request, cacheName) {
    const cached = await caches.match(request);
    if (cached) return cached;

    try {
        const response = await fetch(request);
        if (response && response.status === 200) {
            const cache = await caches.open(cacheName);
            cache.put(request, response.clone());
        }
        return response;
    } catch {
        return new Response('Offline', { status: 503 });
    }
}

/**
 * KOD uchun: tarmoq birinchi, lekin CHEKSIZ KUTMAYDI.
 *
 *   onlayn        → tarmoqdan yangi nusxa, kesh ham yangilanadi
 *   tarmoq yiqildi→ keshdagi nusxa (OFFLINE AVVALGIDEK ISHLAYDI)
 *   tarmoq sekin  → CODE_NET_TIMEOUT_MS dan keyin keshdagi nusxa
 *   kesh ham yo'q → tarmoq javobini kutib qolamiz (boshqa ilojsiz)
 *
 * ⚠️ Timeout tarmoq so'rovini BEKOR QILMAYDI — u fonda davom etadi va
 * tugaganda keshni yangilaydi. Ya'ni keyingi yuklash yangi bo'ladi.
 */
async function networkFirstCode(request, cacheName) {
    const cache = await caches.open(cacheName);

    const network = fetch(request).then(response => {
        if (response && response.status === 200) {
            // Fonda keshni yangilaymiz (timeout bo'lgan holat uchun ham)
            cache.put(request, response.clone()).catch(() => {});
        }
        return response;
    });

    const cached = await cache.match(request);

    // Keshda yo'q — tarmoqni kutishdan boshqa ilojimiz yo'q
    if (!cached) {
        try {
            return await network;
        } catch {
            return new Response('Offline', { status: 503 });
        }
    }

    // Keshda bor — tarmoqni cheklangan vaqt kutamiz
    let timer;
    const timeout = new Promise(resolve => {
        timer = setTimeout(() => resolve(null), CODE_NET_TIMEOUT_MS);
    });

    try {
        const winner = await Promise.race([network.catch(() => null), timeout]);
        if (winner && winner.status === 200) return winner;
        return cached;          // timeout yoki tarmoq xatosi → kesh
    } finally {
        clearTimeout(timer);
    }
}

async function staleWhileRevalidate(request, cacheName) {
    const cache  = await caches.open(cacheName);
    const cached = await cache.match(request);

    // Fon yangilanishi
    const fetchPromise = fetch(request).then(response => {
        if (response && response.status === 200) {
            cache.put(request, response.clone());
        }
        return response;
    }).catch(() => null);

    return cached || fetchPromise;
}

async function networkOnly(request) {
    try {
        return await fetch(request);
    } catch {
        return new Response(
            JSON.stringify({ error: 'Offline', detail: "Internet aloqasi yo'q" }),
            { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
    }
}

async function networkFirstNav(request) {
    try {
        const response = await fetch(request);
        if (response && response.status === 200) {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(request, response.clone());
        }
        return response;
    } catch {
        const cached = await caches.match(request);
        if (cached) return cached;
        return caches.match('/shared/offline.html');
    }
}

// ── Background Sync ───────────────────────────────────────────────────────

self.addEventListener('sync', event => {
    if (event.tag === 'sync-orders') {
        event.waitUntil(_bgSyncOrders());
    }
});

async function _bgSyncOrders() {
    // SW kontekstida IndexedDB dan to'g'ridan-to'g'ri o'qish
    const orders = await _getQueuedOrders();
    const token  = await _getAuthToken();
    if (!token || !orders.length) return;

    const apiBase = self.location.origin;

    for (const order of orders) {
        try {
            const { local_id, queued_at, synced, type: _t, payment: paymentData, ...payload } = order;
            const res = await fetch(`${apiBase}/api/v1/orders/`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body:    JSON.stringify(payload),
            });
            if (res.ok) {
                const created = await res.json();
                // To'lov ma'lumoti ham saqlangan bo'lsa, uni ham yuboramiz
                if (paymentData && created.id) {
                    try {
                        await fetch(`${apiBase}/api/v1/payments/`, {
                            method:  'POST',
                            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                            body:    JSON.stringify({ ...paymentData, order_id: created.id }),
                        });
                    } catch {}
                }
                await _dequeueOrder(local_id);
            }
        } catch { /* birini o'tkazib yuboramiz, keyingi urinishda yana */ }
    }
}

// SW kontekstida IndexedDB operatsiyalari
// Versiya ko'rsatmaymiz — main thread bilan konflikt bo'lmasin
function _openDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open('restopos_db');
        req.onsuccess = e => resolve(e.target.result);
        req.onerror   = e => reject(e.target.error);
    });
}

async function _getQueuedOrders() {
    try {
        const db = await _openDB();
        return new Promise((resolve, reject) => {
            const tx  = db.transaction('orders_queue', 'readonly');
            const req = tx.objectStore('orders_queue').getAll();
            req.onsuccess = () => resolve(req.result || []);
            req.onerror   = e => reject(e.target.error);
        });
    } catch { return []; }
}

async function _dequeueOrder(localId) {
    try {
        const db = await _openDB();
        return new Promise((resolve, reject) => {
            const tx  = db.transaction('orders_queue', 'readwrite');
            const req = tx.objectStore('orders_queue').delete(localId);
            req.onsuccess = () => resolve();
            req.onerror   = e => reject(e.target.error);
        });
    } catch {}
}

async function _getAuthToken() {
    try {
        const db = await _openDB();
        return new Promise((resolve) => {
            if (!db.objectStoreNames.contains('auth_meta')) { db.close(); resolve(null); return; }
            const tx  = db.transaction('auth_meta', 'readonly');
            const req = tx.objectStore('auth_meta').get('access_token');
            req.onsuccess = () => { db.close(); resolve(req.result?.value || null); };
            req.onerror   = () => { db.close(); resolve(null); };
        });
    } catch { return null; }
}

// ── Push bildirishnomalar ─────────────────────────────────────────────────

self.addEventListener('push', event => {
    const data = event.data?.json() || {};
    event.waitUntil(
        self.registration.showNotification(data.title || 'XENORA', {
            body:    data.body    || 'Yangi bildirishnoma',
            icon:    '/assets/icons/icon-192x192.png',
            badge:   '/assets/icons/badge-72x72.png',
            vibrate: [200, 100, 200],
            tag:     data.tag    || 'default',
            data:    data.data   || {},
        })
    );
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    const url = event.notification.data?.url || '/';
    event.waitUntil(
        clients.matchAll({ type: 'window' }).then(list => {
            const existing = list.find(c => c.url.includes(url));
            if (existing) return existing.focus();
            return clients.openWindow(url);
        })
    );
});
