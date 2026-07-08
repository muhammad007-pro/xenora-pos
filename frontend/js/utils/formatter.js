// Formatter Utilities - Formatlash uchun

// Pul formatlash
export const formatMoney = (amount, currency = 'UZS', locale = 'uz-UZ') => {
    if (amount === null || amount === undefined) return '0 UZS';
    
    try {
        return new Intl.NumberFormat(locale, {
            style: 'currency',
            currency: currency,
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(amount);
    } catch (error) {
        // Agar Intl ishlamasa
        const formatted = amount.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
        return `${formatted} ${currency}`;
    }
};

// Son formatlash
export const formatNumber = (number, locale = 'uz-UZ') => {
    if (number === null || number === undefined) return '0';
    
    return new Intl.NumberFormat(locale).format(number);
};

// Sana formatlash
export const formatDate = (date, format = 'short') => {
    if (!date) return '-';
    
    const d = new Date(date);
    
    if (isNaN(d.getTime())) return '-';
    
    const options = {
        short: { day: '2-digit', month: '2-digit', year: 'numeric' },
        medium: { day: 'numeric', month: 'long', year: 'numeric' },
        long: { day: 'numeric', month: 'long', year: 'numeric', weekday: 'long' }
    };
    
    return d.toLocaleDateString('uz-UZ', options[format] || options.short);
};

// Vaqt formatlash
export const formatTime = (date, includeSeconds = false) => {
    if (!date) return '-';
    
    const d = new Date(date);
    
    if (isNaN(d.getTime())) return '-';
    
    return d.toLocaleTimeString('uz-UZ', {
        hour: '2-digit',
        minute: '2-digit',
        second: includeSeconds ? '2-digit' : undefined
    });
};

// Sana va vaqt formatlash
export const formatDateTime = (date, format = 'medium') => {
    if (!date) return '-';
    
    return `${formatDate(date, format)} ${formatTime(date)}`;
};

// Nisbiy vaqt (5 daqiqa oldin, 2 soat oldin)
export const formatRelativeTime = (date) => {
    if (!date) return '-';
    
    const d = new Date(date);
    const now = new Date();
    const diff = now - d;
    
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const months = Math.floor(days / 30);
    const years = Math.floor(days / 365);
    
    if (years > 0) return `${years} yil oldin`;
    if (months > 0) return `${months} oy oldin`;
    if (days > 0) return `${days} kun oldin`;
    if (hours > 0) return `${hours} soat oldin`;
    if (minutes > 0) return `${minutes} daqiqa oldin`;
    if (seconds > 30) return `${seconds} soniya oldin`;
    return 'hozir';
};

// Davomiylik formatlash (120 daqiqa -> 2 soat 0 daqiqa)
export const formatDuration = (elapsed) => {
    if (!elapsed) return '0 daqiqa';
    
    const minutes = elapsed.minutes || 0;
    const seconds = elapsed.seconds || 0;
    
    if (minutes === 0) {
        return `${seconds} soniya`;
    }
    
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    
    if (hours > 0) {
        return `${hours} soat ${mins} daqiqa`;
    }
    
    return `${mins} daqiqa`;
};

// Telefon raqam formatlash (+998 90 123 45 67)
export const formatPhone = (phone) => {
    if (!phone) return '';
    
    // Raqamlarni ajratish
    const cleaned = phone.replace(/\D/g, '');
    
    // O'zbekiston raqamlari uchun
    if (cleaned.length === 12 && cleaned.startsWith('998')) {
        return `+${cleaned.slice(0, 3)} ${cleaned.slice(3, 5)} ${cleaned.slice(5, 8)} ${cleaned.slice(8, 10)} ${cleaned.slice(10, 12)}`;
    }
    
    // 9 xonali raqamlar uchun
    if (cleaned.length === 9) {
        return `+998 ${cleaned.slice(0, 2)} ${cleaned.slice(2, 5)} ${cleaned.slice(5, 7)} ${cleaned.slice(7, 9)}`;
    }
    
    return phone;
};

// Matn qisqartirish
export const truncate = (text, length = 50, suffix = '...') => {
    if (!text) return '';
    if (text.length <= length) return text;
    return text.substring(0, length).trim() + suffix;
};

// Barcode/SKU formatlash
export const formatBarcode = (barcode) => {
    if (!barcode) return '';
    return barcode.toString().replace(/(.{4})/g, '$1 ').trim();
};

// Foiz formatlash
export const formatPercent = (value, decimals = 1) => {
    if (value === null || value === undefined) return '0%';
    return `${value.toFixed(decimals)}%`;
};

// Fayl hajmi formatlash
export const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// Status matnini olish
export const getStatusText = (status, type = 'order') => {
    const statuses = {
        order: {
            'pending': 'Kutilmoqda',
            'confirmed': 'Tasdiqlangan',
            'preparing': 'Tayyorlanmoqda',
            'ready': 'Tayyor',
            'served': 'Xizmat qilingan',
            'completed': 'Yakunlangan',
            'cancelled': 'Bekor qilingan'
        },
        payment: {
            'pending': 'Kutilmoqda',
            'paid': 'To\'langan',
            'partial': 'Qisman to\'langan',
            'refunded': 'Qaytarilgan',
            'failed': 'Xato'
        },
        table: {
            'free': 'Bo\'sh',
            'occupied': 'Band',
            'reserved': 'Bron qilingan',
            'cleaning': 'Tozalanmoqda'
        },
        user: {
            'active': 'Faol',
            'inactive': 'Nofaol',
            'blocked': 'Bloklangan'
        }
    };
    
    return statuses[type]?.[status] || status;
};