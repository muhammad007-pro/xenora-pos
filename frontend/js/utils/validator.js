// Validatsiya funksiyalari
export const validateForm = (data, rules) => {
    const errors = {};
    
    Object.keys(rules).forEach(field => {
        const value = data[field];
        const fieldRules = rules[field];
        
        // Majburiy maydon tekshirish
        if (fieldRules.required && (!value || value.trim() === '')) {
            errors[field] = `${field} majburiy maydon`;
            return;
        }
        
        // Agar qiymat bo'sh bo'lsa, boshqa tekshiruvlarni o'tkazmaymiz
        if (!value || value.trim() === '') {
            return;
        }
        
        // Minimal uzunlik tekshirish
        if (fieldRules.minLength && value.length < fieldRules.minLength) {
            errors[field] = `${field} kamida ${fieldRules.minLength} ta belgi bo'lishi kerak`;
        }
        
        // Maksimal uzunlik tekshirish
        if (fieldRules.maxLength && value.length > fieldRules.maxLength) {
            errors[field] = `${field} ko'pi bilan ${fieldRules.maxLength} ta belgi bo'lishi kerak`;
        }
        
        // Email tekshirish
        if (fieldRules.email) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(value)) {
                errors[field] = 'To\'g\'ri email kiriting';
            }
        }
        
        // Telefon tekshirish
        if (fieldRules.phone) {
            const phoneRegex = /^\+?[0-9\s\-()]{9,15}$/;
            if (!phoneRegex.test(value)) {
                errors[field] = 'To\'g\'ri telefon raqam kiriting';
            }
        }
        
        // Parol tekshirish
        if (fieldRules.password) {
            if (value.length < 6) {
                errors[field] = 'Parol kamida 6 ta belgi bo\'lishi kerak';
            }
        }
        
        // Parol mosligini tekshirish
        if (fieldRules.match) {
            const matchValue = data[fieldRules.match];
            if (value !== matchValue) {
                errors[field] = 'Parollar mos kelmadi';
            }
        }
        
        // Regex pattern tekshirish
        if (fieldRules.pattern) {
            if (!fieldRules.pattern.test(value)) {
                errors[field] = fieldRules.message || 'Noto\'g\'ri format';
            }
        }
    });
    
    return errors;
};

// Email validatsiyasi
export const isValidEmail = (email) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
};

// Telefon validatsiyasi
export const isValidPhone = (phone) => {
    const phoneRegex = /^\+?[0-9\s\-()]{9,15}$/;
    return phoneRegex.test(phone);
};

// Parol kuchini tekshirish
export const getPasswordStrength = (password) => {
    let strength = 0;
    
    if (password.length >= 6) strength++;
    if (password.length >= 8) strength++;
    if (/[a-z]/.test(password)) strength++;
    if (/[A-Z]/.test(password)) strength++;
    if (/[0-9]/.test(password)) strength++;
    if (/[^a-zA-Z0-9]/.test(password)) strength++;
    
    if (strength <= 2) return 'weak';
    if (strength <= 4) return 'medium';
    return 'strong';
};

// Bo'sh maydonlarni tekshirish
export const hasEmptyFields = (data, fields) => {
    return fields.some(field => !data[field] || data[field].trim() === '');
};

// Raqam ekanligini tekshirish
export const isNumeric = (value) => {
    return !isNaN(parseFloat(value)) && isFinite(value);
};

// Minimal qiymat tekshirish
export const minValue = (value, min) => {
    return parseFloat(value) >= min;
};

// Maksimal qiymat tekshirish
export const maxValue = (value, max) => {
    return parseFloat(value) <= max;
};

export default {
    validateForm,
    isValidEmail,
    isValidPhone,
    getPasswordStrength,
    hasEmptyFields,
    isNumeric,
    minValue,
    maxValue
};