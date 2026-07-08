import { API_BASE } from './config.js';

// Bir vaqtning o'zida bir nechta 401 kelsa (POS/planshet parallel so'rovlar),
// refresh faqat BIR MARTA bajarilsin — barcha so'rovlar shu bitta natijani kutadi.
let _refreshInFlight = null;

// API Service - Backend bilan aloqa uchun
class API {
    constructor() {
        this.baseURL = API_BASE;
        this.token = localStorage.getItem('access_token');
        this.refreshToken = localStorage.getItem('refresh_token');
    }
    
    // Token olish
    getToken() {
        return this.token;
    }
    
    // Token yangilash
    setToken(token) {
        this.token = token;
        localStorage.setItem('access_token', token);
        // Service Worker background sync uchun IndexedDB auth_meta ga ham saqlaymiz
        try {
            const req = indexedDB.open('restopos_db');
            req.onsuccess = e => {
                const db = e.target.result;
                if (db.objectStoreNames.contains('auth_meta')) {
                    const tx = db.transaction('auth_meta', 'readwrite');
                    tx.objectStore('auth_meta').put({ key: 'access_token', value: token });
                }
                db.close();
            };
        } catch {}
    }
    
    setRefreshToken(token) {
        this.refreshToken = token;
        localStorage.setItem('refresh_token', token);
    }
    
    // Tokenlarni tozalash
    clearTokens() {
        this.token = null;
        this.refreshToken = null;
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
    }
    
    // Headers tayyorlash
    getHeaders() {
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        };
        
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }
        
        return headers;
    }
    
    // Token muddati tugagan bo'lsa yangilash (refresh token bilan — qayta login shart emas)
    async refreshAccessToken() {
        // Boshqa so'rov allaqachon refresh qilyapti — o'shani kutamiz (stampede oldini olish)
        if (_refreshInFlight) return _refreshInFlight;

        // Eng yangi refresh tokenni localStorage'dan o'qiymiz (boshqa API instansiyasi
        // yangilagan bo'lishi mumkin). localStorage native app (Capacitor/Electron)'da saqlanadi.
        this.refreshToken = localStorage.getItem('refresh_token');
        if (!this.refreshToken) {
            throw new Error('Refresh token mavjud emas');
        }

        _refreshInFlight = (async () => {
            try {
                const response = await fetch(`${this.baseURL}/auth/refresh`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        refresh_token: this.refreshToken
                    })
                });

                if (!response.ok) {
                    // 401 → refresh muddati tugagan YOKI admin xodimni faolsizlantirgan (is_active=False)
                    throw new Error('Tokenni yangilab bo\'lmadi');
                }

                const data = await response.json();
                this.setToken(data.access_token);
                this.setRefreshToken(data.refresh_token);

                return data.access_token;
            } catch (error) {
                this.clearTokens();
                window.location.href = '/shared/login.html';
                throw error;
            } finally {
                _refreshInFlight = null;
            }
        })();

        return _refreshInFlight;
    }
    
    // Asosiy request metodi
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        
        const config = {
            ...options,
            headers: {
                ...this.getHeaders(),
                ...options.headers
            }
        };
        
        // Body bo'lsa JSON stringify qilish
        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }

        // status — xato javobda ham qaytariladi (offline vs server xatosini farqlash uchun).
        // status 0 → fetch umuman javob olmadi (tarmoq yo'q); 503 → Service Worker offline fallback.
        let status = 0;
        try {
            let response = await fetch(url, config);
            status = response.status;

            // Token muddati tugagan bo'lsa — refresh token bilan avtomatik yangilash
            if (response.status === 401 && localStorage.getItem('refresh_token')) {
                try {
                    // refreshAccessToken YANGI access tokenni qaytaradi (this.token emas —
                    // boshqa instansiya yangilagan bo'lsa ham to'g'ri token ishlatilsin)
                    const newToken = await this.refreshAccessToken();

                    // Qaytadan so'rov yuborish
                    config.headers = {
                        ...config.headers,
                        'Authorization': `Bearer ${newToken}`
                    };

                    response = await fetch(url, config);
                    status = response.status;
                } catch (refreshError) {
                    this.clearTokens();
                    window.location.href = '/shared/login.html';
                    throw refreshError;
                }
            }

            // Javobni qayta ishlash
            const contentType = response.headers.get('content-type');
            const isJson = contentType && contentType.includes('application/json');
            const body = isJson ? await response.json() : await response.text();

            // Xato javob — MUVAFFAQIYAT SHAKLI O'ZGARMAYDI ({success:false,error,data}),
            // faqat status/offline QO'SHILADI (mavjud iste'molchilar buzilmaydi — additive).
            if (!response.ok) {
                const msg = isJson ? (body.detail || body.message || 'Xatolik yuz berdi') : 'Xatolik yuz berdi';
                return {
                    success: false,
                    error: msg,
                    data: null,
                    status,
                    offline: (status === 503 || status === 0),  // 503 = SW offline; 0 = javob yo'q
                };
            }

            return {
                success: true,
                data: body,
                status
            };
        } catch (error) {
            // fetch o'zi rad etdi → tarmoq/internet yo'q (offline). Refresh redirect throw ham shu yerda.
            console.error('API Error:', error);

            return {
                success: false,
                error: error.message,
                data: null,
                status,
                offline: true,
            };
        }
    }
    
    // GET so'rovi
    async get(endpoint, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;
        
        return this.request(url, {
            method: 'GET'
        });
    }
    
    // POST so'rovi
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: data
        });
    }
    
    // PUT so'rovi
    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: data
        });
    }
    
    // PATCH so'rovi
    async patch(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PATCH',
            body: data
        });
    }
    
    // DELETE so'rovi
    async delete(endpoint) {
        return this.request(endpoint, {
            method: 'DELETE'
        });
    }
    
    // File upload
    async upload(endpoint, file, additionalData = {}) {
        const formData = new FormData();
        formData.append('file', file);
        
        Object.keys(additionalData).forEach(key => {
            formData.append(key, additionalData[key]);
        });
        
        return this.request(endpoint, {
            method: 'POST',
            headers: {
                // Content-Type o'rnatilmaydi, browser o'zi o'rnatadi
            },
            body: formData
        });
    }
    
    // Multiple file upload
    async uploadMultiple(endpoint, files, additionalData = {}) {
        const formData = new FormData();
        
        files.forEach((file, index) => {
            formData.append(`files[${index}]`, file);
        });
        
        Object.keys(additionalData).forEach(key => {
            formData.append(key, additionalData[key]);
        });
        
        return this.request(endpoint, {
            method: 'POST',
            headers: {},
            body: formData
        });
    }
    
    // Download file
    async download(endpoint, filename) {
        try {
            const response = await fetch(`${this.baseURL}${endpoint}`, {
                method: 'GET',
                headers: this.getHeaders()
            });
            
            if (!response.ok) {
                throw new Error('Faylni yuklab bo\'lmadi');
            }
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename || 'download';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            return { success: true };
        } catch (error) {
            console.error('Download error:', error);
            return { success: false, error: error.message };
        }
    }
}

export { API };