import { API_BASE } from './config.js';

// Bir vaqtning o'zida bir nechta 401 kelsa (POS/planshet parallel so'rovlar),
// refresh faqat BIR MARTA bajarilsin — barcha so'rovlar shu bitta natijani kutadi.
let _refreshInFlight = null;

// Obuna bloklanганда bir marta yo'naltirish (ko'p parallel so'rov → bitta redirect).
let _subBlockHandled = false;
function _handleSubscriptionBlock(message) {
    if (_subBlockHandled) return;
    const path = (typeof location !== 'undefined' && location.pathname) || '';
    // Blok ekrani va login sahifasining o'zi qayta yo'naltirilmasin (loop bo'lmasin).
    if (/subscription-blocked\.html$/.test(path) || /login\.html$/.test(path)) return;
    _subBlockHandled = true;
    try { sessionStorage.setItem('sub_block_msg', message || ''); } catch {}
    try { window.location.href = '/shared/subscription-blocked.html'; } catch {}
}

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
    // redirectOnFail: refresh muvaffaqiyatsiz bo'lsa login'ga yo'naltirish (default: ha).
    // Fon vazifalari (backup) buni false qiladi — app'ni login'ga uloqtirmaslik uchun.
    async refreshAccessToken(redirectOnFail = true) {
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
                if (redirectOnFail) window.location.href = '/shared/login.html';
                throw error;
            } finally {
                _refreshInFlight = null;
            }
        })();

        return _refreshInFlight;
    }
    
    // Umumiy fetch + 401→refresh→retry (single-flight). Xom Response qaytaradi —
    // JSON (request) ham, binary (fetchBinary) ham shu bitta refresh mantig'idan foydalanadi.
    // redirectOnFail: refresh o'lса login'ga yo'naltirish (request=ha, backup=yo'q).
    async _fetchWithRefresh(url, config, redirectOnFail = true) {
        let response = await fetch(url, config);
        // Token muddati tugagan bo'lsa — refresh token bilan avtomatik yangilash
        if (response.status === 401 && localStorage.getItem('refresh_token')) {
            // refreshAccessToken YANGI access tokenni qaytaradi (boshqa instansiya
            // yangilagan bo'lsa ham to'g'ri token ishlatilsin). Muvaffaqiyatsiz → throw.
            const newToken = await this.refreshAccessToken(redirectOnFail);
            config = {
                ...config,
                headers: { ...config.headers, 'Authorization': `Bearer ${newToken}` }
            };
            response = await fetch(url, config);
        }
        return response;
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
            // 401 → refresh → retry (umumiy _fetchWithRefresh; refresh o'lса login'ga yo'naltiradi).
            const response = await this._fetchWithRefresh(url, config, true);
            status = response.status;

            // Javobni qayta ishlash
            const contentType = response.headers.get('content-type');
            const isJson = contentType && contentType.includes('application/json');
            const body = isJson ? await response.json() : await response.text();

            // Xato javob — MUVAFFAQIYAT SHAKLI O'ZGARMAYDI ({success:false,error,data}),
            // faqat status/offline/code QO'SHILADI (mavjud iste'molchilar buzilmaydi — additive).
            if (!response.ok) {
                // detail dict bo'lishi mumkin ({code,message}) — obuna enforcement shunday yuboradi.
                const rawDetail = isJson ? body.detail : null;
                const isObjDetail = rawDetail && typeof rawDetail === 'object';
                const code = isObjDetail ? (rawDetail.code || null) : null;
                const msg = isObjDetail
                    ? (rawDetail.message || 'Xatolik yuz berdi')
                    : (isJson ? (body.detail || body.message || 'Xatolik yuz berdi') : 'Xatolik yuz berdi');

                // OBUNA BLOK (403 + SUBSCRIPTION_EXPIRED): jim blok BO'LMASIN — butun app
                // o'rniga bitta ekran. Barcha sahifalar shu api.js orqali ishlaydi, shuning
                // uchun bu YAGONA joyda ushlanadi (kassa/hisobot/sozlama — hammasi to'xtaydi).
                if (status === 403 && code === 'SUBSCRIPTION_EXPIRED') {
                    _handleSubscriptionBlock(msg);
                }

                return {
                    success: false,
                    error: msg,
                    code,
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
    
    // Binary (blob/gzip/arrayBuffer) GET/POST — 401→refresh→retry BILAN (request() faqat JSON).
    // Fon vazifasi bo'lgani uchun refresh o'lса login'ga YO'NALTIRMAYDI — sessionExpired qaytaradi
    // (chaqiruvchi toza xabar ko'rsatadi). Qaytaradi:
    //   { success:true, data:Uint8Array, headers, status }
    //   { success:false, error, status, sessionExpired? }
    async fetchBinary(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        // Eng yangi tokenni localStorage'dan (boshqa instansiya yangilagan bo'lishi mumkin).
        const tok = localStorage.getItem('access_token');
        const config = {
            method: 'GET',
            ...options,
            headers: {
                ...(tok ? { 'Authorization': `Bearer ${tok}` } : {}),
                ...(options.headers || {}),
                // DIQQAT: Content-Type QO'YILMAYDI — GET (kerak emas) va multipart (browser
                // boundary qo'yadi) uchun. FormData body'da to'g'ri ishlashi shart.
            }
        };
        try {
            // redirectOnFail:false — backup app'ni login'ga uloqtirmasin.
            const response = await this._fetchWithRefresh(url, config, false);
            if (!response.ok) {
                let detail = 'HTTP ' + response.status;
                try { const j = await response.json(); detail = j.detail || j.message || detail; } catch {}
                return { success: false, error: detail, status: response.status };
            }
            const data = new Uint8Array(await response.arrayBuffer());
            return { success: true, data, headers: response.headers, status: response.status };
        } catch (error) {
            // refreshAccessToken(false) throw qildi → refresh_token ham tugagan (30 kun) YOKI tarmoq.
            const expired = !navigator.onLine ? false : true;
            return {
                success: false,
                status: 401,
                sessionExpired: expired,
                error: expired ? 'Sessiya tugagan, qayta kiring' : (error.message || 'Tarmoq xatosi'),
            };
        }
    }

    // Download file — endi fetchBinary orqali (401→refresh bilan). Brauzerda <a download>.
    async download(endpoint, filename) {
        const res = await this.fetchBinary(endpoint);
        if (!res.success) {
            console.error('Download error:', res.error);
            return { success: false, error: res.error, sessionExpired: res.sessionExpired };
        }
        try {
            const blob = new Blob([res.data]);
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