// Offline cache boshqaruvi
class OfflineCache {
    constructor() {
        this.dbName = 'RestoPOS-Offline';
        this.dbVersion = 1;
        this.db = null;
        this.init();
    }
    
    async init() {
        this.db = await this.openDatabase();
    }
    
    async openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);
            
            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);
            
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                
                // Offline buyurtmalar
                if (!db.objectStoreNames.contains('orders')) {
                    const ordersStore = db.createObjectStore('orders', { 
                        keyPath: 'id', 
                        autoIncrement: true 
                    });
                    ordersStore.createIndex('created_at', 'created_at');
                    ordersStore.createIndex('synced', 'synced');
                }
                
                // Offline to'lovlar
                if (!db.objectStoreNames.contains('payments')) {
                    const paymentsStore = db.createObjectStore('payments', { 
                        keyPath: 'id', 
                        autoIncrement: true 
                    });
                    paymentsStore.createIndex('created_at', 'created_at');
                    paymentsStore.createIndex('synced', 'synced');
                }
                
                // Kesh ma'lumotlar
                if (!db.objectStoreNames.contains('cache')) {
                    const cacheStore = db.createObjectStore('cache', { 
                        keyPath: 'key' 
                    });
                    cacheStore.createIndex('expires_at', 'expires_at');
                }
            };
        });
    }
    
    // Buyurtmani saqlash
    async saveOrder(order) {
        if (!this.db) await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['orders'], 'readwrite');
            const store = transaction.objectStore('orders');
            
            const orderData = {
                ...order,
                synced: false,
                created_at: new Date().toISOString()
            };
            
            const request = store.add(orderData);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }
    
    // Sinxronizatsiya qilinmagan buyurtmalarni olish
    async getUnsyncedOrders() {
        if (!this.db) await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['orders'], 'readonly');
            const store = transaction.objectStore('orders');
            const index = store.index('synced');
            
            const request = index.getAll(false);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }
    
    // Buyurtmani sinxronizatsiya qilingan deb belgilash
    async markOrderSynced(id) {
        if (!this.db) await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['orders'], 'readwrite');
            const store = transaction.objectStore('orders');
            
            const getRequest = store.get(id);
            getRequest.onsuccess = () => {
                const order = getRequest.result;
                if (order) {
                    order.synced = true;
                    const putRequest = store.put(order);
                    putRequest.onsuccess = () => resolve();
                    putRequest.onerror = () => reject(putRequest.error);
                } else {
                    resolve();
                }
            };
            getRequest.onerror = () => reject(getRequest.error);
        });
    }
    
    // To'lovni saqlash
    async savePayment(payment) {
        if (!this.db) await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['payments'], 'readwrite');
            const store = transaction.objectStore('payments');
            
            const paymentData = {
                ...payment,
                synced: false,
                created_at: new Date().toISOString()
            };
            
            const request = store.add(paymentData);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }
    
    // Kesh ma'lumotlarni saqlash
    async setCache(key, data, ttl = 3600) {
        if (!this.db) await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['cache'], 'readwrite');
            const store = transaction.objectStore('cache');
            
            const cacheData = {
                key,
                data,
                expires_at: Date.now() + (ttl * 1000)
            };
            
            const request = store.put(cacheData);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }
    
    // Kesh ma'lumotlarni olish
    async getCache(key) {
        if (!this.db) await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['cache'], 'readonly');
            const store = transaction.objectStore('cache');
            
            const request = store.get(key);
            request.onsuccess = () => {
                const data = request.result;
                if (data && data.expires_at > Date.now()) {
                    resolve(data.data);
                } else {
                    resolve(null);
                }
            };
            request.onerror = () => reject(request.error);
        });
    }
    
    // Eski kesh ma'lumotlarni tozalash
    async cleanExpiredCache() {
        if (!this.db) await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['cache'], 'readwrite');
            const store = transaction.objectStore('cache');
            const index = store.index('expires_at');
            
            const range = IDBKeyRange.upperBound(Date.now());
            const request = index.openCursor(range);
            
            request.onsuccess = (event) => {
                const cursor = event.target.result;
                if (cursor) {
                    cursor.delete();
                    cursor.continue();
                } else {
                    resolve();
                }
            };
            request.onerror = () => reject(request.error);
        });
    }
}

// Global offline cache instance
const offlineCache = new OfflineCache();

// Sinxronizatsiyani ro'yxatdan o'tkazish
if ('serviceWorker' in navigator && 'SyncManager' in window) {
    navigator.serviceWorker.ready.then((registration) => {
        registration.sync.register('sync-orders');
        registration.sync.register('sync-payments');
    });
}

export { OfflineCache, offlineCache };