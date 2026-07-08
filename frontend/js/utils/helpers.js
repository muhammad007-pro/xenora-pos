// Helper Utilities - Yordamchi funksiyalar

// Debounce - tez-tez chaqiriladigan funksiyalarni cheklash
export const debounce = (func, wait) => {
    let timeout;
    
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
};

// Throttle - funksiya chaqirish chastotasini cheklash
export const throttle = (func, limit) => {
    let inThrottle;
    
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
};

// ID yaratish
export const generateId = (prefix = '') => {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 9);
    return prefix ? `${prefix}_${timestamp}_${random}` : `${timestamp}_${random}`;
};

// Order number yaratish
export const generateOrderNumber = () => {
    const date = new Date();
    const year = date.getFullYear().toString().slice(-2);
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const random = Math.floor(Math.random() * 9999).toString().padStart(4, '0');
    
    return `${year}${month}${day}${random}`;
};

// Deep clone
export const deepClone = (obj) => {
    if (obj === null || typeof obj !== 'object') return obj;
    
    if (obj instanceof Date) return new Date(obj);
    if (obj instanceof Array) return obj.map(item => deepClone(item));
    
    const cloned = {};
    for (const key in obj) {
        if (obj.hasOwnProperty(key)) {
            cloned[key] = deepClone(obj[key]);
        }
    }
    
    return cloned;
};

// Obyektlarni solishtirish
export const isEqual = (obj1, obj2) => {
    return JSON.stringify(obj1) === JSON.stringify(obj2);
};

// LocalStorage ga saqlash
export const storage = {
    set: (key, value) => {
        try {
            localStorage.setItem(key, JSON.stringify(value));
            return true;
        } catch (e) {
            return false;
        }
    },
    
    get: (key, defaultValue = null) => {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch (e) {
            return defaultValue;
        }
    },
    
    remove: (key) => {
        localStorage.removeItem(key);
    },
    
    clear: () => {
        localStorage.clear();
    }
};

// Cookie lar bilan ishlash
export const cookie = {
    set: (name, value, days = 7) => {
        const expires = new Date(Date.now() + days * 864e5).toUTCString();
        document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/`;
    },
    
    get: (name) => {
        return document.cookie.split('; ').reduce((r, v) => {
            const parts = v.split('=');
            return parts[0] === name ? decodeURIComponent(parts[1]) : r;
        }, '');
    },
    
    delete: (name) => {
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
    }
};

// URL parametrlarini olish
export const getUrlParams = (url = window.location.href) => {
    const params = {};
    const urlObj = new URL(url);
    
    urlObj.searchParams.forEach((value, key) => {
        params[key] = value;
    });
    
    return params;
};

// Query string yaratish
export const buildQueryString = (params) => {
    return Object.entries(params)
        .filter(([_, value]) => value !== null && value !== undefined)
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
        .join('&');
};

// Scroll to element
export const scrollTo = (element, offset = 0) => {
    const target = typeof element === 'string' 
        ? document.querySelector(element) 
        : element;
    
    if (target) {
        const y = target.getBoundingClientRect().top + window.pageYOffset + offset;
        window.scrollTo({ top: y, behavior: 'smooth' });
    }
};

// Copy to clipboard
export const copyToClipboard = async (text) => {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (err) {
        // Fallback
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        return true;
    }
};

// Sleep funksiyasi
export const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// Retry funksiyasi
export const retry = async (fn, retries = 3, delay = 1000) => {
    try {
        return await fn();
    } catch (error) {
        if (retries <= 0) throw error;
        await sleep(delay);
        return retry(fn, retries - 1, delay * 1.5);
    }
};

// Array ni guruhlash
export const groupBy = (array, key) => {
    return array.reduce((result, item) => {
        const groupKey = typeof key === 'function' ? key(item) : item[key];
        if (!result[groupKey]) result[groupKey] = [];
        result[groupKey].push(item);
        return result;
    }, {});
};

// Array ni sortlash
export const sortBy = (array, key, order = 'asc') => {
    return [...array].sort((a, b) => {
        const aVal = typeof key === 'function' ? key(a) : a[key];
        const bVal = typeof key === 'function' ? key(b) : b[key];
        
        if (order === 'asc') {
            return aVal > bVal ? 1 : -1;
        } else {
            return aVal < bVal ? 1 : -1;
        }
    });
};

// Unique qiymatlar
export const unique = (array, key = null) => {
    if (key) {
        return array.filter((item, index, self) => 
            index === self.findIndex(t => t[key] === item[key])
        );
    }
    return [...new Set(array)];
};

// Validatsiya
export const validators = {
    email: (email) => {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    },
    
    phone: (phone) => {
        const cleaned = phone.replace(/\D/g, '');
        return cleaned.length >= 9 && cleaned.length <= 15;
    },
    
    password: (password) => {
        return password.length >= 6;
    },
    
    required: (value) => {
        return value !== null && value !== undefined && value !== '';
    }
};

export default {
    debounce,
    throttle,
    generateId,
    generateOrderNumber,
    deepClone,
    isEqual,
    storage,
    cookie,
    getUrlParams,
    buildQueryString,
    scrollTo,
    copyToClipboard,
    sleep,
    retry,
    groupBy,
    sortBy,
    unique,
    validators
};