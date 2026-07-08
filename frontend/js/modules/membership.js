/**
 * Membership moduli — fitnes, kurs/maktab uchun a'zolik tizimi (BOSQICH 4.4)
 *
 * Ishlatilishi:
 *   import { MembershipModule } from './membership.js';
 *   const mod = new MembershipModule();
 *   await mod.init('containerId');
 */

import { API }        from '../core/api.js';
import { showToast }  from '../ui/toast.js';
import { formatMoney } from '../utils/formatter.js';

const STATUS_LABELS = {
    active: 'Faol', expired: "Muddati o'tgan",
    frozen: 'Muzlatilgan', cancelled: 'Bekor qilingan',
};
const STATUS_CLASS = {
    active: 'badge-active', expired: 'badge-expired',
    frozen: 'badge-frozen', cancelled: 'badge-cancelled',
};

export class MembershipModule {
    constructor() {
        this._api         = new API();
        this._memberships = [];
        this._customers   = [];
        this._statusFilter = '';
    }

    async init(containerId) {
        this._container = document.getElementById(containerId);
        if (!this._container) return;
        await this._load();
        this._render();
    }

    async _load() {
        const [memRes, custRes] = await Promise.all([
            this._api.get('/memberships/', { page_size: 200 }),
            this._api.get('/customers/', { page_size: 500 }),
        ]);
        this._memberships = memRes.success ? (memRes.data?.items || []) : [];
        this._customers   = custRes.success ? (custRes.data?.items || []) : [];
    }

    _render() {
        if (!this._container) return;
        const stats = this._calcStats();

        this._container.innerHTML = `
            <div class="mem-stats">
                <div class="mem-stat mem-stat-active">
                    <div class="mem-stat-val">${stats.active}</div>
                    <div class="mem-stat-lbl">Faol</div>
                </div>
                <div class="mem-stat mem-stat-expired">
                    <div class="mem-stat-val">${stats.expired}</div>
                    <div class="mem-stat-lbl">Muddati o'tgan</div>
                </div>
                <div class="mem-stat mem-stat-frozen">
                    <div class="mem-stat-val">${stats.frozen}</div>
                    <div class="mem-stat-lbl">Muzlatilgan</div>
                </div>
                <div class="mem-stat">
                    <div class="mem-stat-val">${this._memberships.length}</div>
                    <div class="mem-stat-lbl">Jami</div>
                </div>
            </div>
            <div class="mem-toolbar">
                <select class="mem-status-filter">
                    <option value="">Barcha holatlar</option>
                    ${Object.entries(STATUS_LABELS).map(([v, l]) =>
                        `<option value="${v}" ${this._statusFilter === v ? 'selected' : ''}>${l}</option>`
                    ).join('')}
                </select>
                <button class="btn btn-primary mem-add-btn">+ A'zolik qo'shish</button>
            </div>
            <div class="mem-list" id="memList"></div>`;

        this._renderList();

        this._container.querySelector('.mem-status-filter').addEventListener('change', (e) => {
            this._statusFilter = e.target.value;
            this._renderList();
        });
        this._container.querySelector('.mem-add-btn').addEventListener('click', () => {
            this._openForm();
        });
    }

    _renderList() {
        const listEl = this._container.querySelector('#memList');
        if (!listEl) return;

        let list = this._memberships;
        if (this._statusFilter) list = list.filter(m => m.status === this._statusFilter);

        if (!list.length) {
            listEl.innerHTML = '<div class="mem-empty">A\'zolik topilmadi</div>';
            return;
        }

        listEl.innerHTML = list.map(m => {
            const cust = this._customers.find(c => c.id === m.customer_id);
            const daysLeft = Math.ceil((new Date(m.end_date) - new Date()) / 86400000);
            const expiring = daysLeft <= 7 && daysLeft > 0 && m.status === 'active';
            const pct = m.visits_total > 0 ? Math.min((m.visits_used / m.visits_total) * 100, 100) : null;

            return `
                <div class="mem-item" data-id="${m.id}">
                    <div class="mem-customer">
                        <strong>${cust?.name || '—'}</strong>
                        <div class="mem-phone">${cust?.phone || ''}</div>
                    </div>
                    <div class="mem-plan">${m.plan_name}</div>
                    <div class="mem-dates">
                        <div>${m.start_date} → ${m.end_date}</div>
                        ${expiring ? `<div class="mem-expiring">⚠️ ${daysLeft} kun qoldi</div>` : ''}
                    </div>
                    <div class="mem-visits">
                        ${m.visits_total > 0
                            ? `${m.visits_used}/${m.visits_total}
                               <div class="mem-bar"><div class="mem-fill" style="width:${pct}%"></div></div>`
                            : `${m.visits_used} (∞)`}
                    </div>
                    <span class="badge ${STATUS_CLASS[m.status] || ''}">${STATUS_LABELS[m.status] || m.status}</span>
                    <div class="mem-actions">
                        ${m.status === 'active'
                            ? `<button class="btn btn-sm btn-outline mem-visit-btn">+Tashrif</button>`
                            : ''}
                        <button class="btn btn-sm btn-outline mem-edit-btn">✏️</button>
                    </div>
                </div>`;
        }).join('');

        listEl.querySelectorAll('.mem-visit-btn').forEach(btn => {
            const id = btn.closest('.mem-item').dataset.id;
            btn.addEventListener('click', () => this._recordVisit(id));
        });
        listEl.querySelectorAll('.mem-edit-btn').forEach(btn => {
            const id = btn.closest('.mem-item').dataset.id;
            btn.addEventListener('click', () => this._openForm(this._memberships.find(m => m.id == id)));
        });
    }

    async _recordVisit(id) {
        const res = await this._api.post(`/memberships/${id}/visit`);
        if (res.success) {
            showToast('Tashrif qayd etildi', 'success');
            await this._load();
            this._renderList();
        } else {
            showToast(res.error || 'Xatolik', 'error');
        }
    }

    _openForm(m = null) {
        const today = new Date().toISOString().slice(0, 10);
        const modal = document.createElement('div');
        modal.className = 'modal open';
        modal.innerHTML = `
            <div class="modal-overlay"></div>
            <div class="modal-content glass" style="max-width:480px">
                <div class="modal-header">
                    <h2>${m ? "A'zolikni tahrirlash" : "Yangi a'zolik"}</h2>
                    <button class="modal-close btn-icon glass">&times;</button>
                </div>
                <div class="modal-body">
                    <form class="mem-form">
                        ${!m ? `
                        <div class="form-group">
                            <label>Mijoz *</label>
                            <select name="customer_id" required>
                                <option value="">Tanlang...</option>
                                ${this._customers.map(c =>
                                    `<option value="${c.id}">${c.name} (${c.phone || '—'})</option>`
                                ).join('')}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Tarif *</label>
                            <select name="plan_name">
                                <option value="basic">Basic</option>
                                <option value="standard">Standard</option>
                                <option value="premium">Premium</option>
                                <option value="unlimited">Unlimited</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Narxi</label>
                            <input type="number" name="price" min="0" value="0">
                        </div>
                        <div class="form-group">
                            <label>Tashriflar soni (0=cheksiz)</label>
                            <input type="number" name="visits_total" min="0" value="0">
                        </div>` : ''}
                        <div class="form-group">
                            <label>Boshlanish *</label>
                            <input type="date" name="start_date" value="${m?.start_date || today}" ${m ? 'readonly' : ''} required>
                        </div>
                        <div class="form-group">
                            <label>Tugash *</label>
                            <input type="date" name="end_date" value="${m?.end_date || ''}" required>
                        </div>
                        <div class="form-group">
                            <label>Izoh</label>
                            <textarea name="notes" rows="2">${m?.notes || ''}</textarea>
                        </div>
                        <div class="modal-actions">
                            <button type="button" class="btn btn-outline modal-close">Bekor qilish</button>
                            <button type="submit" class="btn btn-primary">Saqlash</button>
                        </div>
                    </form>
                </div>
            </div>`;

        document.body.appendChild(modal);
        modal.querySelectorAll('.modal-close, .modal-overlay').forEach(el => {
            el.addEventListener('click', () => modal.remove());
        });

        modal.querySelector('form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.target));
            if (data.price)        data.price        = parseFloat(data.price);
            if (data.visits_total) data.visits_total = parseInt(data.visits_total);
            if (data.customer_id)  data.customer_id  = parseInt(data.customer_id);

            const res = m
                ? await this._api.patch(`/memberships/${m.id}`, { end_date: data.end_date, notes: data.notes })
                : await this._api.post('/memberships/', data);

            if (res.success) {
                showToast('Saqlandi', 'success');
                modal.remove();
                await this._load();
                this._render();
            } else {
                showToast(res.error || 'Xatolik', 'error');
            }
        });
    }

    _calcStats() {
        const s = { active: 0, expired: 0, frozen: 0 };
        this._memberships.forEach(m => { if (s[m.status] !== undefined) s[m.status]++; });
        return s;
    }
}
