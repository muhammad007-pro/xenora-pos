// State Manager - Global holat boshqaruvi
class StateManager {
    constructor() {
        this.state = {};
        this.listeners = new Map();
        this.persistedKeys = new Set();
        
        // Saqlangan holatni yuklash
        this.loadPersistedState();
    }
    
    // Holatni olish
    get(key, defaultValue = null) {
        return this.state.hasOwnProperty(key) ? this.state[key] : defaultValue;
    }
    
    // Holatni o'rnatish
    set(key, value) {
        const oldValue = this.state[key];
        this.state[key] = value;
        
        // Agar o'zgargan bo'lsa tinglovchilarni chaqirish
        if (oldValue !== value) {
            this.notifyListeners(key, value, oldValue);
            
            // Persist qilish kerak bo'lsa
            if (this.persistedKeys.has(key)) {
                this.persistKey(key, value);
            }
        }
        
        return value;
    }
    
    // Bir nechta qiymatni o'rnatish
    setMultiple(updates) {
        const changes = [];
        
        Object.entries(updates).forEach(([key, value]) => {
            const oldValue = this.state[key];
            this.state[key] = value;
            
            if (oldValue !== value) {
                changes.push({ key, value, oldValue });
                
                if (this.persistedKeys.has(key)) {
                    this.persistKey(key, value);
                }
            }
        });
        
        // Tinglovchilarni chaqirish
        changes.forEach(({ key, value, oldValue }) => {
            this.notifyListeners(key, value, oldValue);
        });
    }
    
    // Holatni yangilash (funksiya orqali)
    update(key, updater) {
        const oldValue = this.state[key];
        const newValue = updater(oldValue);
        return this.set(key, newValue);
    }
    
    // Holat mavjudligini tekshirish
    has(key) {
        return this.state.hasOwnProperty(key);
    }
    
    // Holatni o'chirish
    delete(key) {
        if (this.state.hasOwnProperty(key)) {
            const oldValue = this.state[key];
            delete this.state[key];
            
            this.notifyListeners(key, undefined, oldValue);
            
            if (this.persistedKeys.has(key)) {
                this.removePersistedKey(key);
            }
            
            return true;
        }
        
        return false;
    }
    
    // Barcha holatni tozalash
    clear() {
        const keys = Object.keys(this.state);
        
        keys.forEach(key => {
            const oldValue = this.state[key];
            delete this.state[key];
            this.notifyListeners(key, undefined, oldValue);
            
            if (this.persistedKeys.has(key)) {
                this.removePersistedKey(key);
            }
        });
    }
    
    // Holatni kuzatish
    watch(key, callback) {
        if (!this.listeners.has(key)) {
            this.listeners.set(key, new Set());
        }
        
        this.listeners.get(key).add(callback);
        
        // Hozirgi qiymat bilan darhol chaqirish
        if (this.state.hasOwnProperty(key)) {
            callback(this.state[key], null);
        }
        
        // Cleanup funksiyasini qaytarish
        return () => this.unwatch(key, callback);
    }
    
    // Kuzatishni to'xtatish
    unwatch(key, callback) {
        if (this.listeners.has(key)) {
            this.listeners.get(key).delete(callback);
            
            if (this.listeners.get(key).size === 0) {
                this.listeners.delete(key);
            }
        }
    }
    
    // Tinglovchilarni chaqirish
    notifyListeners(key, newValue, oldValue) {
        if (this.listeners.has(key)) {
            this.listeners.get(key).forEach(callback => {
                try {
                    callback(newValue, oldValue);
                } catch (error) {
                    console.error('State listener xatosi:', error);
                }
            });
        }
        
        // Umumiy tinglovchilar
        if (this.listeners.has('*')) {
            this.listeners.get('*').forEach(callback => {
                try {
                    callback({ key, newValue, oldValue });
                } catch (error) {
                    console.error('State listener xatosi:', error);
                }
            });
        }
    }
    
    // Holatni persist qilish
    persist(key, value = true) {
        if (value) {
            this.persistedKeys.add(key);
            
            // Agar hozir qiymat bo'lsa saqlash
            if (this.state.hasOwnProperty(key)) {
                this.persistKey(key, this.state[key]);
            }
        } else {
            this.persistedKeys.delete(key);
            this.removePersistedKey(key);
        }
    }
    
    // Kalitni localStorage ga saqlash
    persistKey(key, value) {
        try {
            const data = {
                value,
                timestamp: Date.now()
            };
            localStorage.setItem(`state_${key}`, JSON.stringify(data));
        } catch (error) {
            console.error('State persist xatosi:', error);
        }
    }
    
    // Kalitni localStorage dan o'chirish
    removePersistedKey(key) {
        try {
            localStorage.removeItem(`state_${key}`);
        } catch (error) {
            console.error('State persist remove xatosi:', error);
        }
    }
    
    // Saqlangan holatni yuklash
    loadPersistedState() {
        this.persistedKeys.forEach(key => {
            try {
                const stored = localStorage.getItem(`state_${key}`);
                
                if (stored) {
                    const data = JSON.parse(stored);
                    
                    // 7 kundan eski bo'lsa o'chirish
                    if (Date.now() - data.timestamp > 7 * 24 * 60 * 60 * 1000) {
                        this.removePersistedKey(key);
                        return;
                    }
                    
                    this.state[key] = data.value;
                }
            } catch (error) {
                console.error('State load xatosi:', error);
            }
        });
    }
    
    // Holatni eksport qilish
    exportState() {
        return {
            state: { ...this.state },
            persistedKeys: Array.from(this.persistedKeys),
            timestamp: Date.now()
        };
    }
    
    // Holatni import qilish
    importState(data) {
        if (!data || !data.state) return false;
        
        this.clear();
        
        Object.entries(data.state).forEach(([key, value]) => {
            this.state[key] = value;
        });
        
        if (data.persistedKeys) {
            this.persistedKeys = new Set(data.persistedKeys);
            
            // Import qilingan persist qiymatlarni saqlash
            this.persistedKeys.forEach(key => {
                if (this.state.hasOwnProperty(key)) {
                    this.persistKey(key, this.state[key]);
                }
            });
        }
        
        return true;
    }
    
    // Holatni kuzatish (computed)
    computed(dependencies, compute) {
        let currentValue;
        
        const updateValue = () => {
            const values = dependencies.map(dep => this.get(dep));
            const newValue = compute(...values);
            
            if (newValue !== currentValue) {
                currentValue = newValue;
            }
        };
        
        // Dastlabki qiymatni hisoblash
        updateValue();
        
        // Har bir bog'liqlikni kuzatish
        const unwatchers = dependencies.map(dep => 
            this.watch(dep, () => {
                updateValue();
            })
        );
        
        // Cleanup funksiyasini qaytarish
        return {
            get value() {
                return currentValue;
            },
            destroy: () => {
                unwatchers.forEach(unwatch => unwatch());
            }
        };
    }
}

export { StateManager };