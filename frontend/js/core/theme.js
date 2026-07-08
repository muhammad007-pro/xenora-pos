// Theme Manager - Dark/Light rejimini boshqarish
export class ThemeManager {
    constructor() {
        this.theme = localStorage.getItem('theme') || 'dark';
        this.listeners = [];
        this.init();
    }
    
    init() {
        this.applyTheme(this.theme);
        this.setupSystemThemeListener();
    }
    
    applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        this.theme = theme;
        localStorage.setItem('theme', theme);
        
        // Iconlarni yangilash
        this.updateThemeIcons(theme);
        
        // Tinglovchilarga xabar berish
        this.notifyListeners(theme);
    }
    
    toggle() {
        const newTheme = this.theme === 'dark' ? 'light' : 'dark';
        this.applyTheme(newTheme);
        return newTheme;
    }
    
    setTheme(theme) {
        if (theme === 'dark' || theme === 'light') {
            this.applyTheme(theme);
        }
    }
    
    getCurrentTheme() {
        return this.theme;
    }
    
    isDark() {
        return this.theme === 'dark';
    }
    
    isLight() {
        return this.theme === 'light';
    }
    
    updateThemeIcons(theme) {
        const sunIcons = document.querySelectorAll('.sun-icon');
        const moonIcons = document.querySelectorAll('.moon-icon');
        
        sunIcons.forEach(icon => {
            icon.style.display = theme === 'dark' ? 'none' : 'block';
        });
        
        moonIcons.forEach(icon => {
            icon.style.display = theme === 'dark' ? 'block' : 'none';
        });
    }
    
    setupSystemThemeListener() {
        // Agar foydalanuvchi qo'lda tanlamagan bo'lsa, sistema temasini kuzatish
        if (!localStorage.getItem('theme')) {
            const darkModeMedia = window.matchMedia('(prefers-color-scheme: dark)');
            
            const handleChange = (e) => {
                this.applyTheme(e.matches ? 'dark' : 'light');
            };
            
            darkModeMedia.addEventListener('change', handleChange);
            
            // Dastlabki qiymat
            if (darkModeMedia.matches) {
                this.applyTheme('dark');
            }
        }
    }
    
    // Tinglovchi qo'shish (boshqa komponentlar uchun)
    addListener(callback) {
        this.listeners.push(callback);
        return () => {
            this.listeners = this.listeners.filter(cb => cb !== callback);
        };
    }
    
    notifyListeners(theme) {
        this.listeners.forEach(callback => {
            try {
                callback(theme);
            } catch (e) {
                console.error('Theme listener error:', e);
            }
        });
    }
    
    // CSS o'zgaruvchilarni dinamik o'zgartirish
    setVariable(name, value) {
        document.documentElement.style.setProperty(name, value);
    }
    
    getVariable(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }
}

// Singleton instance
const themeManager = new ThemeManager();

// Global funksiyalar
export const toggleTheme = () => themeManager.toggle();
export const setTheme = (theme) => themeManager.setTheme(theme);
export const getCurrentTheme = () => themeManager.getCurrentTheme();
export const isDarkMode = () => themeManager.isDark();
export const onThemeChange = (callback) => themeManager.addListener(callback);

export default themeManager;