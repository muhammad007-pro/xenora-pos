import { API } from './core/api.js';
import { AuthService } from './core/auth.js';
import { showToast } from './ui/toast.js';
import { StateManager } from './core/state.js';

class SettingsModule {
    constructor() {
        this.api = new API();
        this.auth = new AuthService();
        this.state = new StateManager();
        this.settings = {};
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadSettings();
        this.renderSettings();
    }
    
    setupEventListeners() {
        document.getElementById('saveSettings')?.addEventListener('click', () => this.saveSettings());
        document.getElementById('themeSelect')?.addEventListener('change', (e) => this.changeTheme(e.target.value));
        document.getElementById('testPrinter')?.addEventListener('click', () => this.testPrinter());
        document.getElementById('createBackup')?.addEventListener('click', () => this.createBackup());
        document.getElementById('logoutAll')?.addEventListener('click', () => this.logoutAllDevices());
    }
    
    async loadSettings() {
        const response = await this.api.get('/settings');
        this.settings = response.data || {};
    }
    
    renderSettings() {
        document.getElementById('printerEnabled').checked = this.settings.printer?.enabled || false;
        document.getElementById('printerPort').value = this.settings.printer?.port || 'COM1';
        document.getElementById('soundEnabled').checked = this.settings.kitchen?.sound_enabled !== false;
        document.getElementById('autoPrint').checked = this.settings.kitchen?.auto_print !== false;
        
        const theme = localStorage.getItem('theme') || 'dark';
        document.getElementById('themeSelect').value = theme;
    }
    
    async saveSettings() {
        const settings = {
            printer: {
                enabled: document.getElementById('printerEnabled').checked,
                port: document.getElementById('printerPort').value
            },
            kitchen: {
                sound_enabled: document.getElementById('soundEnabled').checked,
                auto_print: document.getElementById('autoPrint').checked
            }
        };
        
        try {
            await this.api.patch('/settings', settings);
            showToast('Sozlamalar saqlandi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    changeTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }
    
    async testPrinter() {
        try {
            const response = await this.api.post('/settings/printer/test');
            if (response.data?.success) {
                showToast('Printer ishlayapti', 'success');
            } else {
                showToast('Printer ulanmagan', 'warning');
            }
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    async createBackup() {
        try {
            const response = await this.api.post('/settings/backup/create');
            showToast('Zaxira yaratildi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    async logoutAllDevices() {
        if (!confirm('Barcha qurilmalardan chiqishni xohlaysizmi?')) return;
        
        try {
            await this.api.post('/auth/logout-all');
            showToast('Barcha qurilmalardan chiqildi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => new SettingsModule());