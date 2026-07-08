/**
 * Services moduli — salon, fitnes, auto-servis uchun xizmatlar boshqaruvi (BOSQICH 4.4)
 *
 * Ishlatilishi:
 *   import { ServicesModule } from './services.js';
 *   const mod = new ServicesModule();
 *   await mod.init('containerId');
 */

import { API }        from '../core/api.js';
import { showToast }  from '../ui/toast.js';
import { formatMoney } from '../utils/formatter.js';

const CAT_LABELS = {
    hair: 'Soch', nail: 'Tirnoq', massage: 'Massaj',
    fitness: 'Fitnes', repair: "Ta'mirlash", course: 'Kurs', other: 'Boshqa',
};

export class ServicesModule {
    constructor() {
        this._api      = new API();
        this._services = [];
        this._filter   = '';
        this._category = '';
    }

    async init(containerId) {
        this._container = document.getElementById(containerId);
        if (!this._container) return;
        await this._load();
        this._render();
    }

    async _load() {
        const res = await this._api.get('/services/', { page_size: 200 });
        this._services = res.success ? (res.data?.items || []) : [];
    }

    _render() {
        if (!this._container) return;
        this._container.innerHTML = `
            <div class="svc-toolbar">
                <input class="svc-search" type="text" placeholder="Xizmat qidirish..." value="${this._filter}">
                <select class="svc-cat-filter">
                    <option value="">Barcha kategoriyalar</option>
                    ${Object.entries(CAT_LABELS).map(([v, l]) =>
                        `<option value="${v}" ${this._category === v ? 'selected' : ''}>${l}</option>`
                    ).join('')}
                </select>
                <button class="btn btn-primary svc-add-btn">+ Xizmat qo'shish</button>
            </div>
            <div class="svc-grid" id="svcGrid"></div>`;

        this._renderGrid();

        this._container.querySelector('.svc-search').addEventListener('input', (e) => {
            this._filter = e.target.value.toLowerCase();
            this._renderGrid();
        });
        this._container.querySelector('.svc-cat-filter').addEventListener('change', (e) => {
            this._category = e.target.value;
            this._renderGrid();
        });
        this._container.querySelector('.svc-add-btn').addEventListener('click', () => {
            this._openForm();
        });
    }

    _renderGrid() {
        const grid = this._container.querySelector('#svcGrid');
        if (!grid) return;

        let list = this._services;
        if (this._filter)   list = list.filter(s => s.name.toLowerCase().includes(this._filter));
        if (this._category) list = list.filter(s => s.category === this._category);

        if (!list.length) {
            grid.innerHTML = '<div class="svc-empty">Xizmat topilmadi</div>';
            return;
        }

        grid.innerHTML = list.map(s => `
            <div class="svc-card ${s.is_active ? '' : 'svc-inactive'}" data-id="${s.id}">
                <div class="svc-accent" style="background:${s.color}"></div>
                <div class="svc-card-body">
                    <div class="svc-name">${s.name}</div>
                    <div class="svc-cat">${CAT_LABELS[s.category] || s.category || '—'}</div>
                    <div class="svc-price">${formatMoney(s.price)}</div>
                    <div class="svc-dur">⏱ ${s.duration_minutes} daqiqa</div>
                </div>
                <div class="svc-actions">
                    <button class="btn btn-sm btn-outline svc-edit">✏️</button>
                    <button class="btn btn-sm btn-outline svc-toggle">${s.is_active ? "O'chirish" : 'Yoqish'}</button>
                </div>
            </div>`).join('');

        grid.querySelectorAll('.svc-edit').forEach(btn => {
            const id = btn.closest('.svc-card').dataset.id;
            btn.addEventListener('click', () => this._openForm(this._services.find(s => s.id == id)));
        });
        grid.querySelectorAll('.svc-toggle').forEach(btn => {
            const card = btn.closest('.svc-card');
            const svc = this._services.find(s => s.id == card.dataset.id);
            btn.addEventListener('click', () => this._toggle(svc));
        });
    }

    async _toggle(svc) {
        const res = await this._api.patch(`/services/${svc.id}`, { is_active: !svc.is_active });
        if (res.success) {
            showToast(svc.is_active ? "O'chirildi" : 'Yoqildi', 'success');
            await this._load();
            this._renderGrid();
        }
    }

    _openForm(svc = null) {
        const modal = document.createElement('div');
        modal.className = 'modal open';
        modal.innerHTML = `
            <div class="modal-overlay"></div>
            <div class="modal-content glass" style="max-width:460px">
                <div class="modal-header">
                    <h2>${svc ? 'Xizmatni tahrirlash' : 'Yangi xizmat'}</h2>
                    <button class="modal-close btn-icon glass">&times;</button>
                </div>
                <div class="modal-body">
                    <form class="svc-form">
                        <div class="form-group">
                            <label>Nomi *</label>
                            <input type="text" name="name" value="${svc?.name || ''}" required>
                        </div>
                        <div class="form-group">
                            <label>Kategoriya</label>
                            <select name="category">
                                ${Object.entries(CAT_LABELS).map(([v, l]) =>
                                    `<option value="${v}" ${svc?.category === v ? 'selected' : ''}>${l}</option>`
                                ).join('')}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Narxi (so'm)</label>
                            <input type="number" name="price" value="${svc?.price || 0}" min="0">
                        </div>
                        <div class="form-group">
                            <label>Davomiyligi (daqiqa)</label>
                            <input type="number" name="duration_minutes" value="${svc?.duration_minutes || 30}" min="5">
                        </div>
                        <div class="form-group">
                            <label>Rang</label>
                            <input type="color" name="color" value="${svc?.color || '#c9a84c'}">
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
            data.price = parseFloat(data.price) || 0;
            data.duration_minutes = parseInt(data.duration_minutes) || 30;

            const res = svc
                ? await this._api.patch(`/services/${svc.id}`, data)
                : await this._api.post('/services/', data);

            if (res.success) {
                showToast('Saqlandi', 'success');
                modal.remove();
                await this._load();
                this._renderGrid();
            } else {
                showToast(res.error || 'Xatolik', 'error');
            }
        });
    }
}
