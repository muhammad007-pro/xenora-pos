/**
 * Suppliers moduli — magazin, dorixona uchun yetkazib beruvchilar (BOSQICH 4.3)
 *
 * Ishlatilishi:
 *   import { SuppliersModule } from './suppliers.js';
 *   const mod = new SuppliersModule();
 *   await mod.init('containerId');
 */

import { API }       from '../core/api.js';
import { showToast } from '../ui/toast.js';

export class SuppliersModule {
    constructor() {
        this._api       = new API();
        this._suppliers = [];
        this._search    = '';
    }

    async init(containerId) {
        this._container = document.getElementById(containerId);
        if (!this._container) return;
        await this._load();
        this._render();
    }

    async _load() {
        const res = await this._api.get('/suppliers/', { page_size: 200 });
        this._suppliers = res.success ? (res.data?.items || []) : [];
    }

    _render() {
        if (!this._container) return;
        this._container.innerHTML = `
            <div class="sup-toolbar">
                <input class="sup-search" type="text" placeholder="Qidirish (nom, telefon...)">
                <button class="btn btn-primary sup-add-btn">+ Qo'shish</button>
            </div>
            <div class="sup-table-wrap">
                <table class="sup-table">
                    <thead>
                        <tr>
                            <th>Nomi</th><th>Kontakt</th><th>Telefon</th>
                            <th>Email</th><th>INN</th><th>Holat</th><th>Amallar</th>
                        </tr>
                    </thead>
                    <tbody id="supTbody"></tbody>
                </table>
            </div>`;

        this._renderRows();

        this._container.querySelector('.sup-search').addEventListener('input', (e) => {
            this._search = e.target.value.toLowerCase();
            this._renderRows();
        });
        this._container.querySelector('.sup-add-btn').addEventListener('click', () => this._openForm());
    }

    _renderRows() {
        const tbody = this._container.querySelector('#supTbody');
        if (!tbody) return;

        const list = this._search
            ? this._suppliers.filter(s =>
                s.name?.toLowerCase().includes(this._search) ||
                s.contact_person?.toLowerCase().includes(this._search) ||
                s.phone?.includes(this._search))
            : this._suppliers;

        if (!list.length) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--text-secondary)">Yetkazib beruvchi topilmadi</td></tr>`;
            return;
        }

        tbody.innerHTML = list.map(s => `
            <tr data-id="${s.id}">
                <td><strong>${s.name}</strong>${s.address ? `<div style="font-size:11px;color:var(--text-secondary)">${s.address}</div>` : ''}</td>
                <td>${s.contact_person || '—'}</td>
                <td>${s.phone || '—'}</td>
                <td>${s.email || '—'}</td>
                <td>${s.tax_id || '—'}</td>
                <td><span class="${s.is_active ? 'badge-active' : 'badge-inactive'}">${s.is_active ? 'Faol' : 'Nofaol'}</span></td>
                <td>
                    <button class="btn btn-sm btn-outline sup-edit">✏️</button>
                    <button class="btn btn-sm btn-outline sup-toggle">${s.is_active ? "O'chirish" : 'Yoqish'}</button>
                </td>
            </tr>`).join('');

        tbody.querySelectorAll('.sup-edit').forEach(btn => {
            const id = btn.closest('tr').dataset.id;
            btn.addEventListener('click', () => this._openForm(this._suppliers.find(s => s.id == id)));
        });
        tbody.querySelectorAll('.sup-toggle').forEach(btn => {
            const id = btn.closest('tr').dataset.id;
            const s  = this._suppliers.find(s => s.id == id);
            btn.addEventListener('click', () => this._toggle(s));
        });
    }

    async _toggle(s) {
        const res = await this._api.patch(`/suppliers/${s.id}`, { is_active: !s.is_active });
        if (res.success) {
            showToast(s.is_active ? "O'chirildi" : 'Yoqildi', 'success');
            await this._load();
            this._renderRows();
        }
    }

    _openForm(s = null) {
        const modal = document.createElement('div');
        modal.className = 'modal open';
        modal.innerHTML = `
            <div class="modal-overlay"></div>
            <div class="modal-content glass" style="max-width:500px">
                <div class="modal-header">
                    <h2>${s ? 'Tahrirlash' : 'Yangi yetkazib beruvchi'}</h2>
                    <button class="modal-close btn-icon glass">&times;</button>
                </div>
                <div class="modal-body">
                    <form class="sup-form">
                        <div class="form-group">
                            <label>Nomi *</label>
                            <input type="text" name="name" value="${s?.name || ''}" required>
                        </div>
                        <div class="form-group">
                            <label>Kontakt shaxs</label>
                            <input type="text" name="contact_person" value="${s?.contact_person || ''}">
                        </div>
                        <div class="form-group">
                            <label>Telefon</label>
                            <input type="tel" name="phone" value="${s?.phone || ''}">
                        </div>
                        <div class="form-group">
                            <label>Email</label>
                            <input type="email" name="email" value="${s?.email || ''}">
                        </div>
                        <div class="form-group">
                            <label>INN</label>
                            <input type="text" name="tax_id" value="${s?.tax_id || ''}">
                        </div>
                        <div class="form-group">
                            <label>Manzil</label>
                            <textarea name="address" rows="2">${s?.address || ''}</textarea>
                        </div>
                        <div class="form-group">
                            <label>Izoh</label>
                            <textarea name="notes" rows="2">${s?.notes || ''}</textarea>
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
            if (!data.name) { showToast('Nomi kiriting', 'warning'); return; }

            const res = s
                ? await this._api.patch(`/suppliers/${s.id}`, data)
                : await this._api.post('/suppliers/', data);

            if (res.success) {
                showToast('Saqlandi', 'success');
                modal.remove();
                await this._load();
                this._renderRows();
            } else {
                showToast(res.error || 'Xatolik', 'error');
            }
        });
    }
}
