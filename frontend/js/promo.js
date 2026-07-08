import { API } from './core/api.js';
import { AuthService } from './core/auth.js';
import { Modal } from './ui/modal.js';
import { showToast } from './ui/toast.js';
import { formatMoney, formatDate } from './utils/formatter.js';

class PromoModule {
    constructor() {
        this.api = new API();
        this.auth = new AuthService();
        this.promos = [];
        this.modal = new Modal('promoModal');
        this.currentPromo = null;
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadPromos();
        this.renderPromos();
    }
    
    setupEventListeners() {
        document.getElementById('addPromoBtn')?.addEventListener('click', () => this.openModal());
        
        document.getElementById('promoForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.savePromo();
        });
        
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => this.modal.close());
        });
    }
    
    async loadPromos() {
        const response = await this.api.get('/discounts');
        this.promos = response.data?.items || [];
    }
    
    renderPromos() {
        const grid = document.getElementById('promoGrid');
        
        if (this.promos.length === 0) {
            grid.innerHTML = '<div class="empty-state">Hozircha promolar yo\'q</div>';
            return;
        }
        
        grid.innerHTML = this.promos.map(p => `
            <div class="promo-card glass ${p.is_active ? '' : 'inactive'}">
                <div class="promo-header">
                    <h3>${p.name}</h3>
                    <span class="promo-badge ${p.is_active ? 'active' : 'inactive'}">
                        ${p.is_active ? 'Faol' : 'Nofaol'}
                    </span>
                </div>
                <div class="promo-body">
                    <div class="promo-value">
                        ${p.type === 'percentage' ? p.value + '%' : formatMoney(p.value)}
                    </div>
                    <div class="promo-details">
                        <p>Minimal buyurtma: ${formatMoney(p.min_order_amount)}</p>
                        ${p.valid_from ? `<p>Boshlanish: ${formatDate(p.valid_from)}</p>` : ''}
                        ${p.valid_to ? `<p>Tugash: ${formatDate(p.valid_to)}</p>` : ''}
                        ${p.usage_limit ? `<p>Foydalanilgan: ${p.used_count}/${p.usage_limit}</p>` : ''}
                    </div>
                </div>
                <div class="promo-footer">
                    <button class="btn-icon edit-promo" data-id="${p.id}">✏️</button>
                    <button class="btn-icon toggle-promo" data-id="${p.id}">
                        ${p.is_active ? '🔴' : '🟢'}
                    </button>
                    <button class="btn-icon delete-promo" data-id="${p.id}">🗑️</button>
                </div>
            </div>
        `).join('');
        
        grid.querySelectorAll('.edit-promo').forEach(btn => {
            btn.addEventListener('click', () => this.editPromo(btn.dataset.id));
        });
        
        grid.querySelectorAll('.toggle-promo').forEach(btn => {
            btn.addEventListener('click', () => this.togglePromo(btn.dataset.id));
        });
        
        grid.querySelectorAll('.delete-promo').forEach(btn => {
            btn.addEventListener('click', () => this.deletePromo(btn.dataset.id));
        });
    }
    
    openModal(promo = null) {
        this.currentPromo = promo;
        const title = document.getElementById('modalTitle');
        const form = document.getElementById('promoForm');
        
        form.reset();
        
        if (promo) {
            title.textContent = 'Promoni tahrirlash';
            form.name.value = promo.name;
            form.type.value = promo.type;
            form.value.value = promo.value;
            form.min_order_amount.value = promo.min_order_amount;
            form.valid_from.value = promo.valid_from?.split('T')[0] || '';
            form.valid_to.value = promo.valid_to?.split('T')[0] || '';
            form.usage_limit.value = promo.usage_limit || '';
        } else {
            title.textContent = 'Yangi promo';
        }
        
        this.modal.open();
    }
    
    async savePromo() {
        const form = document.getElementById('promoForm');
        const data = Object.fromEntries(new FormData(form));
        
        data.value = parseFloat(data.value);
        data.min_order_amount = parseFloat(data.min_order_amount) || 0;
        data.usage_limit = data.usage_limit ? parseInt(data.usage_limit) : null;
        
        try {
            if (this.currentPromo) {
                await this.api.patch(`/discounts/${this.currentPromo.id}`, data);
                showToast('Promo yangilandi', 'success');
            } else {
                await this.api.post('/discounts', data);
                showToast('Promo yaratildi', 'success');
            }
            
            await this.loadPromos();
            this.renderPromos();
            this.modal.close();
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    editPromo(id) {
        const promo = this.promos.find(p => p.id == id);
        if (promo) this.openModal(promo);
    }
    
    async togglePromo(id) {
        try {
            await this.api.patch(`/discounts/${id}/toggle`);
            await this.loadPromos();
            this.renderPromos();
            showToast('Promo holati o\'zgartirildi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    async deletePromo(id) {
        if (!confirm('Promoni o\'chirishni xohlaysizmi?')) return;
        
        try {
            await this.api.delete(`/discounts/${id}`);
            await this.loadPromos();
            this.renderPromos();
            showToast('Promo o\'chirildi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => new PromoModule());import { API } from './core/api.js';
import { AuthService } from './core/auth.js';
import { Modal } from './ui/modal.js';
import { showToast } from './ui/toast.js';
import { formatMoney, formatDate } from './utils/formatter.js';

class PromoModule {
    constructor() {
        this.api = new API();
        this.auth = new AuthService();
        this.promos = [];
        this.modal = new Modal('promoModal');
        this.currentPromo = null;
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadPromos();
        this.renderPromos();
    }
    
    setupEventListeners() {
        document.getElementById('addPromoBtn')?.addEventListener('click', () => this.openModal());
        
        document.getElementById('promoForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.savePromo();
        });
        
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => this.modal.close());
        });
    }
    
    async loadPromos() {
        const response = await this.api.get('/discounts');
        this.promos = response.data?.items || [];
    }
    
    renderPromos() {
        const grid = document.getElementById('promoGrid');
        
        if (this.promos.length === 0) {
            grid.innerHTML = '<div class="empty-state">Hozircha promolar yo\'q</div>';
            return;
        }
        
        grid.innerHTML = this.promos.map(p => `
            <div class="promo-card glass ${p.is_active ? '' : 'inactive'}">
                <div class="promo-header">
                    <h3>${p.name}</h3>
                    <span class="promo-badge ${p.is_active ? 'active' : 'inactive'}">
                        ${p.is_active ? 'Faol' : 'Nofaol'}
                    </span>
                </div>
                <div class="promo-body">
                    <div class="promo-value">
                        ${p.type === 'percentage' ? p.value + '%' : formatMoney(p.value)}
                    </div>
                    <div class="promo-details">
                        <p>Minimal buyurtma: ${formatMoney(p.min_order_amount)}</p>
                        ${p.valid_from ? `<p>Boshlanish: ${formatDate(p.valid_from)}</p>` : ''}
                        ${p.valid_to ? `<p>Tugash: ${formatDate(p.valid_to)}</p>` : ''}
                        ${p.usage_limit ? `<p>Foydalanilgan: ${p.used_count}/${p.usage_limit}</p>` : ''}
                    </div>
                </div>
                <div class="promo-footer">
                    <button class="btn-icon edit-promo" data-id="${p.id}">✏️</button>
                    <button class="btn-icon toggle-promo" data-id="${p.id}">
                        ${p.is_active ? '🔴' : '🟢'}
                    </button>
                    <button class="btn-icon delete-promo" data-id="${p.id}">🗑️</button>
                </div>
            </div>
        `).join('');
        
        grid.querySelectorAll('.edit-promo').forEach(btn => {
            btn.addEventListener('click', () => this.editPromo(btn.dataset.id));
        });
        
        grid.querySelectorAll('.toggle-promo').forEach(btn => {
            btn.addEventListener('click', () => this.togglePromo(btn.dataset.id));
        });
        
        grid.querySelectorAll('.delete-promo').forEach(btn => {
            btn.addEventListener('click', () => this.deletePromo(btn.dataset.id));
        });
    }
    
    openModal(promo = null) {
        this.currentPromo = promo;
        const title = document.getElementById('modalTitle');
        const form = document.getElementById('promoForm');
        
        form.reset();
        
        if (promo) {
            title.textContent = 'Promoni tahrirlash';
            form.name.value = promo.name;
            form.type.value = promo.type;
            form.value.value = promo.value;
            form.min_order_amount.value = promo.min_order_amount;
            form.valid_from.value = promo.valid_from?.split('T')[0] || '';
            form.valid_to.value = promo.valid_to?.split('T')[0] || '';
            form.usage_limit.value = promo.usage_limit || '';
        } else {
            title.textContent = 'Yangi promo';
        }
        
        this.modal.open();
    }
    
    async savePromo() {
        const form = document.getElementById('promoForm');
        const data = Object.fromEntries(new FormData(form));
        
        data.value = parseFloat(data.value);
        data.min_order_amount = parseFloat(data.min_order_amount) || 0;
        data.usage_limit = data.usage_limit ? parseInt(data.usage_limit) : null;
        
        try {
            if (this.currentPromo) {
                await this.api.patch(`/discounts/${this.currentPromo.id}`, data);
                showToast('Promo yangilandi', 'success');
            } else {
                await this.api.post('/discounts', data);
                showToast('Promo yaratildi', 'success');
            }
            
            await this.loadPromos();
            this.renderPromos();
            this.modal.close();
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    editPromo(id) {
        const promo = this.promos.find(p => p.id == id);
        if (promo) this.openModal(promo);
    }
    
    async togglePromo(id) {
        try {
            await this.api.patch(`/discounts/${id}/toggle`);
            await this.loadPromos();
            this.renderPromos();
            showToast('Promo holati o\'zgartirildi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    async deletePromo(id) {
        if (!confirm('Promoni o\'chirishni xohlaysizmi?')) return;
        
        try {
            await this.api.delete(`/discounts/${id}`);
            await this.loadPromos();
            this.renderPromos();
            showToast('Promo o\'chirildi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => new PromoModule());