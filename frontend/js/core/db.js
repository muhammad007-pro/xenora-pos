/**
 * IndexedDB wrapper — offline-first ma'lumot saqlash (BOSQICH 2.4 / 3)
 *
 * Saqlanadigan storlar:
 *   products      — mahsulotlar keshi (API dan, offline uchun)
 *   categories    — kategoriyalar keshi
 *   tables        — stollar keshi
 *   cart          — joriy savat (sahifa yangilanishdan omon qoladi)
 *   orders_queue  — offline yaratilgan buyurtmalar navbati
 */

const DB_NAME = 'restopos_db';
const DB_VERSION = 2;

export const STORES = {
    PRODUCTS:      'products',
    CATEGORIES:    'categories',
    TABLES:        'tables',
    CART:          'cart',
    ORDERS_QUEUE:  'orders_queue',
    AUTH_META:     'auth_meta',   // SW background sync uchun token saqlash
};

class LocalDB {
    constructor() {
        this.db = null;
        this._ready = null;
    }

    /** DB ni bir marta ochib, keyingi chaqiruvlarda xuddi shuni qaytaradi */
    init() {
        if (this._ready) return this._ready;

        this._ready = new Promise((resolve, reject) => {
            const req = indexedDB.open(DB_NAME, DB_VERSION);

            req.onupgradeneeded = (e) => {
                const db = e.target.result;

                const storeConfigs = {
                    [STORES.PRODUCTS]:     { keyPath: 'id' },
                    [STORES.CATEGORIES]:   { keyPath: 'id' },
                    [STORES.TABLES]:       { keyPath: 'id' },
                    [STORES.CART]:         { keyPath: 'product_id' },
                    [STORES.ORDERS_QUEUE]: { keyPath: 'local_id', autoIncrement: true },
                    [STORES.AUTH_META]:    { keyPath: 'key' },
                };

                Object.entries(storeConfigs).forEach(([name, opts]) => {
                    if (!db.objectStoreNames.contains(name)) {
                        db.createObjectStore(name, opts);
                    }
                });
            };

            req.onsuccess = (e) => {
                this.db = e.target.result;
                resolve(this.db);
            };

            req.onerror = (e) => reject(e.target.error);
        });

        return this._ready;
    }

    /** Storni to'liq yangilash (eski ma'lumot o'chirilib, yangisi yoziladi) */
    async saveAll(storeName, items = []) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            store.clear();
            items.forEach(item => store.put(item));
            tx.oncomplete = () => resolve();
            tx.onerror  = (e) => reject(e.target.error);
        });
    }

    /** Barcha yozuvlarni olish */
    async getAll(storeName) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readonly');
            const req = tx.objectStore(storeName).getAll();
            req.onsuccess = () => resolve(req.result || []);
            req.onerror  = (e) => reject(e.target.error);
        });
    }

    /** Bitta yozuvni qo'shish/yangilash */
    async put(storeName, item) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const req = tx.objectStore(storeName).put(item);
            req.onsuccess = () => resolve(req.result);
            req.onerror  = (e) => reject(e.target.error);
        });
    }

    /** Bitta yozuvni o'chirish */
    async delete(storeName, key) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const req = tx.objectStore(storeName).delete(key);
            req.onsuccess = () => resolve();
            req.onerror  = (e) => reject(e.target.error);
        });
    }

    /** Storni butunlay tozalash */
    async clear(storeName) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const req = tx.objectStore(storeName).clear();
            req.onsuccess = () => resolve();
            req.onerror  = (e) => reject(e.target.error);
        });
    }

    // ── Offline navbat metodlari ─────────────────────────────────────────────

    /** Buyurtmani offline navbatga qo'shish */
    async enqueue(orderData) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx  = this.db.transaction(STORES.ORDERS_QUEUE, 'readwrite');
            const req = tx.objectStore(STORES.ORDERS_QUEUE).add({
                ...orderData,
                queued_at: new Date().toISOString(),
                synced: false,
            });
            req.onsuccess = () => resolve(req.result);
            req.onerror  = (e) => reject(e.target.error);
        });
    }

    /** Navbatdagi barcha buyurtmalar */
    async getQueue() {
        return this.getAll(STORES.ORDERS_QUEUE);
    }

    /** Sinxronlangan buyurtmani navbatdan o'chirish */
    async dequeue(localId) {
        return this.delete(STORES.ORDERS_QUEUE, localId);
    }
}

/** Singleton instance — barcha modullar shu ob'ektni ishlatadi */
export const localDB = new LocalDB();
