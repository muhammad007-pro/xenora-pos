/**
 * Expiry Date (Yaroqlilik muddati) moduli (BOSQICH 4.5)
 *
 * Dorixona va oziq-ovqat do'konlari uchun:
 *   - Muddati tugaydigan mahsulotlar ro'yxati (ranglar bo'yicha)
 *   - Alert: 7 kun qolsa → sariq, o'tgan → qizil
 *   - Mahsulotga expiry_date qo'shish/tahrirlash
 *   - Oylik/haftalik expiry hisoboti
 *
 * API endpointlar:
 *   GET  /products/?expiry_before=DATE
 *   POST /products/{id}/expiry  { expiry_date, batch_number, quantity }
 */

import { API }       from '../core/api.js';
import { showToast } from '../ui/toast.js';

const WARN_DAYS     = 30;   // ogohlantirish: N kun qolsa
const CRITICAL_DAYS = 7;    // kritik: N kun qolsa

export class ExpiryModule {
    constructor() {
        this._api      = new API();
        this._products = [];
        this._filter   = 'all';  // all | critical | warning | expired
    }

    async init(containerId) {
        this._container = document.getElementById(containerId);
        if (!this._container) return;

        await this._load();
        this._render();

        // Har 1 daqiqada yangilash
        this._interval = setInterval(() => this._load().then(() => this._renderList()), 60000);
    }

    destroy() {
        clearInterval(this._interval);
    }

    async _load() {
        const today     = new Date().toISOString().slice(0, 10);
        const warnDate  = this._addDays(WARN_DAYS);
        const res = await this._api.get('/products/', {
            has_expiry: true,
            expiry_before: warnDate,
            page_size: 200,
        });
        if (res.success) {
            this._products = (res.data?.items || []).map(p => ({
                ...p,
                _status: this._expiryStatus(p.expiry_date),
            }));
        }
    }

    _render() {
        if (!this._container) return;
        this._container.innerHTML = `
            <div class="expiry-header">
                <h2>Yaroqlilik muddati nazorati</h2>
                <div class="expiry-stats">
                    <div class="stat-card stat-expired"  id="statExpired"></div>
                    <div class="stat-card stat-critical" id="statCritical"></div>
                    <div class="stat-card stat-warning"  id="statWarning"></div>
                    <div class="stat-card stat-ok"       id="statOk"></div>
                </div>
            </div>
            <div class="expiry-filter">
                <button class="filter-btn active" data-filter="all">Barchasi</button>
                <button class="filter-btn"        data-filter="expired">Muddati o'tgan</button>
                <button class="filter-btn"        data-filter="critical">Kritik (${CRITICAL_DAYS} kun)</button>
                <button class="filter-btn"        data-filter="warning">Ogohlantirish (${WARN_DAYS} kun)</button>
                <button class="filter-btn"        data-filter="ok">Yaxshi</button>
            </div>
            <div class="expiry-list" id="expiryList"></div>
            <button class="btn btn-primary expiry-add-btn" id="expiryAddBtn">
                + Muddatli mahsulot qo'shish
            </button>`;

        this._renderStats();
        this._renderList();

        this._container.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this._filter = btn.dataset.filter;
                this._container.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this._renderList();
            });
        });

        this._container.querySelector('#expiryAddBtn')?.addEventListener('click', () => {
            this._openAddModal();
        });
    }

    _renderStats() {
        const groups = this._groupByStatus();
        const el = (id) => document.getElementById(id);

        const setCard = (id, label, count, icon) => {
            const e = el(id);
            if (e) e.innerHTML = `<span class="stat-icon">${icon}</span><span class="stat-count">${count}</span><span class="stat-label">${label}</span>`;
        };

        setCard('statExpired',  "Muddati o'tgan", groups.expired.length,  '🚫');
        setCard('statCritical', 'Kritik',          groups.critical.length, '🔴');
        setCard('statWarning',  'Ogohlantirish',   groups.warning.length,  '🟡');
        setCard('statOk',       'Yaxshi',          groups.ok.length,       '✅');
    }

    _renderList() {
        const listEl = document.getElementById('expiryList');
        if (!listEl) return;

        const groups  = this._groupByStatus();
        const all     = [...groups.expired, ...groups.critical, ...groups.warning, ...groups.ok];
        const items   = this._filter === 'all' ? all : (groups[this._filter] || []);

        if (!items.length) {
            listEl.innerHTML = '<div class="expiry-empty">Mahsulot topilmadi</div>';
            return;
        }

        listEl.innerHTML = items.map(p => {
            const daysLeft = this._daysLeft(p.expiry_date);
            const daysText = daysLeft < 0
                ? `${Math.abs(daysLeft)} kun o'tgan`
                : daysLeft === 0
                    ? 'Bugun tugaydi!'
                    : `${daysLeft} kun qoldi`;

            return `
                <div class="expiry-item expiry-${p._status}" data-id="${p.id}">
                    <div class="expiry-item-info">
                        <div class="expiry-product-name">${p.name}</div>
                        <div class="expiry-batch">${p.batch_number ? `Partiya: ${p.batch_number}` : ''}</div>
                        <div class="expiry-qty">Miqdor: ${p.quantity_in_stock ?? '—'} ${p.sale_unit !== 'pcs' ? p.sale_unit : ''}</div>
                    </div>
                    <div class="expiry-item-date">
                        <div class="expiry-date">${this._formatDate(p.expiry_date)}</div>
                        <div class="expiry-days expiry-days-${p._status}">${daysText}</div>
                    </div>
                    <div class="expiry-item-actions">
                        <button class="btn-icon expiry-edit-btn" data-id="${p.id}" title="Tahrirlash">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="2"/>
                                <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="2"/>
                            </svg>
                        </button>
                        ${p._status === 'expired' ? `
                        <button class="btn btn-danger btn-sm expiry-remove-btn" data-id="${p.id}">O'chirish</button>` : ''}
                    </div>
                </div>`;
        }).join('');

        listEl.querySelectorAll('.expiry-edit-btn').forEach(btn => {
            btn.addEventListener('click', () => this._openEditModal(parseInt(btn.dataset.id)));
        });
        listEl.querySelectorAll('.expiry-remove-btn').forEach(btn => {
            btn.addEventListener('click', () => this._removeExpired(parseInt(btn.dataset.id)));
        });
    }

    async _openAddModal() {
        const res = await this._api.get('/products/', { page_size: 200 });
        const allProducts = res.success ? (res.data?.items || []) : [];

        this._showExpiryForm({ allProducts });
    }

    async _openEditModal(productId) {
        const res = await this._api.get(`/products/${productId}`);
        const product = res.success ? res.data : null;

        const allRes = await this._api.get('/products/', { page_size: 200 });
        const allProducts = allRes.success ? (allRes.data?.items || []) : [];

        this._showExpiryForm({ allProducts, product });
    }

    _showExpiryForm({ allProducts, product = null }) {
        const modal = document.createElement('div');
        modal.className = 'modal open';
        modal.innerHTML = `
            <div class="modal-overlay"></div>
            <div class="modal-content glass">
                <div class="modal-header">
                    <h2>${product ? 'Muddatni tahrirlash' : 'Muddatli mahsulot'}</h2>
                    <button class="modal-close btn-icon glass">&times;</button>
                </div>
                <div class="modal-body">
                    <form id="expiryForm">
                        ${!product ? `
                        <div class="form-group">
                            <label>Mahsulot</label>
                            <select name="product_id" required>
                                <option value="">Tanlang...</option>
                                ${allProducts.map(p => `<option value="${p.id}">${p.name}</option>`).join('')}
                            </select>
                        </div>` : `<input type="hidden" name="product_id" value="${product.id}">`}
                        <div class="form-group">
                            <label>Yaroqlilik muddati</label>
                            <input type="date" name="expiry_date" value="${product?.expiry_date || ''}" required>
                        </div>
                        <div class="form-group">
                            <label>Partiya raqami</label>
                            <input type="text" name="batch_number" value="${product?.batch_number || ''}" placeholder="LOT-001">
                        </div>
                        <div class="modal-actions">
                            <button type="button" class="btn btn-outline modal-close">Bekor qilish</button>
                            <button type="submit" class="btn btn-primary">Saqlash</button>
                        </div>
                    </form>
                </div>
            </div>`;

        document.body.appendChild(modal);
        modal.querySelectorAll('.modal-close, .modal-overlay').forEach(e => {
            e.addEventListener('click', () => modal.remove());
        });

        modal.querySelector('#expiryForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const fd   = new FormData(e.target);
            const data = Object.fromEntries(fd.entries());
            const id   = data.product_id;
            delete data.product_id;

            const res = await this._api.patch(`/products/${id}`, data);
            if (res.success) {
                showToast('Muddat saqlandi', 'success');
                modal.remove();
                await this._load();
                this._renderStats();
                this._renderList();
            } else {
                showToast(res.error || 'Xatolik', 'error');
            }
        });
    }

    async _removeExpired(productId) {
        if (!confirm('Muddati o\'tgan mahsulotni o\'chirasizmi?')) return;
        const res = await this._api.delete(`/products/${productId}`);
        if (res.success) {
            showToast('Mahsulot o\'chirildi', 'success');
            this._products = this._products.filter(p => p.id !== productId);
            this._renderStats();
            this._renderList();
        }
    }

    // ── Yordamchilar ──────────────────────────────────────────────────────

    _groupByStatus() {
        const groups = { expired: [], critical: [], warning: [], ok: [] };
        this._products.forEach(p => groups[p._status]?.push(p));
        return groups;
    }

    _expiryStatus(dateStr) {
        if (!dateStr) return 'ok';
        const days = this._daysLeft(dateStr);
        if (days < 0)           return 'expired';
        if (days <= CRITICAL_DAYS) return 'critical';
        if (days <= WARN_DAYS)     return 'warning';
        return 'ok';
    }

    _daysLeft(dateStr) {
        const exp   = new Date(dateStr);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return Math.ceil((exp - today) / (1000 * 60 * 60 * 24));
    }

    _addDays(n) {
        const d = new Date();
        d.setDate(d.getDate() + n);
        return d.toISOString().slice(0, 10);
    }

    _formatDate(dateStr) {
        if (!dateStr) return '—';
        return new Date(dateStr).toLocaleDateString('uz-UZ');
    }
}

// ── Backend: products modeliga expiry qo'shish migratsiyanı eslatma ──────────
// Quyidagi ustunlar kerak (alembic migratsiyasida qo'shilsin):
//   expiry_date   DATE nullable
//   batch_number  VARCHAR(50) nullable
