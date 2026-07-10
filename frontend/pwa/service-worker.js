/**
 * XENORA Service Worker (BOSQICH 3.3)
 *
 * Strategiyalar:
 *   statik fayllar  → Cache First (versiyalangan cache)
 *   API GET         → Stale-While-Revalidate (kesh + fon yangilanish)
 *   API POST/PATCH  → Network Only (o'zgartiruvchi so'rovlar keshulanmaydi)
 *   WebSocket       → o'tkazib yuboriladi
 *   Navigatsiya     → Network First + offline.html fallback
 *
 * Background Sync:
 *   'sync-orders' tegi bo'lganda navbatdagi buyurtmalarni yuboradi
 */

const APP_VERSION   = 'v1.22.0';
const STATIC_CACHE  = `restopos-static-${APP_VERSION}`;
const API_CACHE     = `restopos-api-${APP_VERSION}`;
const API_BASE      = '/api';

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
    '/js/modules/admin.js',
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

self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    // WebSocket — o'tkazib yuboramiz
    if (url.protocol === 'ws:' || url.protocol === 'wss:') return;

    // POST/PATCH/DELETE API — keshulanmaydi
    if (url.pathname.startsWith(API_BASE) && request.method !== 'GET') {
        event.respondWith(networkOnly(request));
        return;
    }

    // GET API — stale-while-revalidate
    if (url.pathname.startsWith(API_BASE) && _isCacheableAPI(url.pathname)) {
        event.respondWith(staleWhileRevalidate(request, API_CACHE));
        return;
    }

    // Navigatsiya — network first, offline fallback
    if (request.mode === 'navigate') {
        event.respondWith(networkFirstNav(request));
        return;
    }

    // Statik resurslar — cache first
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
            JSON.stringify({ error: 'Offline', detail: 'Internet aloqasi yo\'q' }),
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
