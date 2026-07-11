/**
 * Sync Engine — online↔offline sinxronizatsiya (BOSQICH 3.2 + 3.4)
 *
 * Vazifalar:
 *   - Offline navbatdagi buyurtmalarni internetga chiqqanda serverga yuborish
 *   - Background Sync API bilan integratsiya (agar brauzer qo'llab-quvvatlasa)
 *   - Sinxronizatsiya holati: idle | syncing | error
 *   - Retry backoff: 3 urinish, keyin to'xtaydi
 *
 * Ishlatilishi:
 *   import { syncEngine } from './sync.js';
 *   syncEngine.start();                     // app yuklanganda
 *   syncEngine.on('sync:complete', fn);     // hodisa tinglash
 */

import { localDB, STORES } from './db.js';
import { API }              from './api.js';

const MAX_RETRIES       = 3;
const RETRY_DELAY_MS    = 2000;   // birinchi urinish oralig'i
const VISIBILITY_DELAY  = 500;    // sahifa fokusga kelganda kechikish

class SyncEngine {
    constructor() {
        this._api       = new API();
        this._listeners = {};
        this._state     = 'idle';    // idle | syncing | error
        this._retries   = 0;
        this._timer     = null;
        this._started   = false;
    }

    // ── Hodisalar ────────────────────────────────────────────────────────

    on(event, fn) {
        if (!this._listeners[event]) this._listeners[event] = [];
        this._listeners[event].push(fn);
        return () => this.off(event, fn);
    }

    off(event, fn) {
        if (!this._listeners[event]) return;
        this._listeners[event] = this._listeners[event].filter(f => f !== fn);
    }

    _emit(event, data) {
        (this._listeners[event] || []).forEach(fn => fn(data));
    }

    // ── Start ─────────────────────────────────────────────────────────────

    start() {
        if (this._started) return;
        this._started = true;

        // Onlineга chiqqanda darhol sinxronlash
        window.addEventListener('online', () => {
            this._retries = 0;
            this._scheduleSync(300);
        });

        // Sahifa fokusga kelganda sinxronlash (brauzer tablarida qulay)
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && navigator.onLine) {
                this._scheduleSync(VISIBILITY_DELAY);
            }
        });

        // Background Sync API ro'yxatdan o'tkazish
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.ready.then(reg => {
                if ('sync' in reg) {
                    reg.sync.register('sync-orders').catch(() => {});
                }
            });
        }

        // Agar hozir online bo'lsa, darhol sinxronlash
        if (navigator.onLine) this._scheduleSync(1000);
    }

    // ── Navbatni sinxronlash ──────────────────────────────────────────────

    _scheduleSync(delay = 0) {
        clearTimeout(this._timer);
        this._timer = setTimeout(() => this._runSync(), delay);
    }

    async _runSync() {
        if (this._state === 'syncing') return;
        if (!navigator.onLine)         return;

        const queue = await localDB.getQueue();
        if (!queue.length) {
            this._setState('idle');
            return;
        }

        this._setState('syncing');
        this._emit('sync:start', { count: queue.length });

        let synced  = 0;
        let failed  = 0;

        for (const item of queue) {
            const success = await this._sendOrder(item);
            if (success) {
                await localDB.dequeue(item.local_id);
                synced++;
                this._emit('sync:progress', { synced, total: queue.length });
            } else {
                failed++;
            }
        }

        if (failed === 0) {
            this._retries = 0;
            this._setState('idle');
            localStorage.setItem('last_sync', Date.now().toString());
            this._emit('sync:complete', { synced });
        } else {
            this._retries++;
            if (this._retries < MAX_RETRIES) {
                this._setState('error');
                this._emit('sync:error', { failed, retries: this._retries });
                this._scheduleSync(RETRY_DELAY_MS * Math.pow(2, this._retries));
            } else {
                this._setState('error');
                this._emit('sync:failed', { failed });
            }
        }
    }

    async _sendOrder(orderData) {
        try {
            const { local_id, queued_at, synced: _synced, type: _t, payment: paymentData, ...payload } = orderData;
            // api.js {success,data,status} qaytaradi — yaratilgan zakaz res.data'да.
            // (Ilgari res.id o'qilardi → undefined → hech qachon dequeue bo'lmasди, offline
            //  zakazlar navbatда qotib qolardi. Contract moslashuvi.)
            const res     = await this._api.post('/orders/', payload);
            const created = res && res.data;
            if (!res || !res.success || !created || !created.id) return false;
            // To'lov ma'lumoti ham saqlangan bo'lsa, uni ham yuboramiz.
            // offline_sync=1 — smena gate'ini o'tkazib yubor (offline savdo allaqachon
            // bo'lgan; smena talabi tarmoq tiklanganда bu to'lovni yo'qotmasin).
            if (paymentData) {
                try { await this._api.post('/payments/?offline_sync=1', { ...paymentData, order_id: created.id }); } catch {}
            }
            return true;
        } catch {
            return false;
        }
    }

    _setState(state) {
        this._state = state;
        this._emit('sync:state', state);
    }

    // ── Tashqi API ────────────────────────────────────────────────────────

    get state() { return this._state; }

    async forceSync() {
        this._retries = 0;
        await this._runSync();
    }

    async queueOrder(orderData) {
        await localDB.enqueue(orderData);
        this._emit('sync:queued', orderData);

        // Background Sync API orqali trigger
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.ready.then(reg => {
                if ('sync' in reg) reg.sync.register('sync-orders').catch(() => {});
            });
        }
    }

    async getPendingCount() {
        const q = await localDB.getQueue();
        return q.length;
    }
}

export const syncEngine = new SyncEngine();
