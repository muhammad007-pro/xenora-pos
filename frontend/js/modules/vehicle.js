/**
 * Vehicle moduli — auto servis uchun avtomobil va xizmat buyurtmalari (BOSQICH 4.4)
 *
 * Ishlatilishi:
 *   import { VehicleModule } from './vehicle.js';
 *   const mod = new VehicleModule();
 *   await mod.init('containerId');
 */

import { API }        from '../core/api.js';
import { showToast }  from '../ui/toast.js';
import { formatMoney } from '../utils/formatter.js';

const ORDER_STATUS = {
    pending:     { label: 'Kutilmoqda',  cls: 'badge-warning' },
    in_progress: { label: 'Jarayonda',   cls: 'badge-info'    },
    done:        { label: 'Tayyor',       cls: 'badge-success' },
    delivered:   { label: 'Topshirildi', cls: 'badge-active'  },
};

export class VehicleModule {
    constructor() {
        this._api      = new API();
        this._vehicles = [];
        this._orders   = [];
        this._customers = [];
        this._tab      = 'vehicles'; // vehicles | orders
    }

    async init(containerId) {
        this._container = document.getElementById(containerId);
        if (!this._container) return;
        await this._load();
        this._render();
    }

    async _load() {
        const [vRes, oRes, cRes] = await Promise.all([
            this._api.get('/vehicles/', { page_size: 200 }),
            this._api.get('/vehicles/orders/', { page_size: 200 }),
            this._api.get('/customers/', { page_size: 500 }),
        ]);
        this._vehicles  = vRes.success ? (vRes.data?.items || []) : [];
        this._orders    = oRes.success ? (oRes.data?.items || []) : [];
        this._customers = cRes.success ? (cRes.data?.items || []) : [];
    }

    _render() {
        if (!this._container) return;
        this._container.innerHTML = `
            <div class="veh-tabs">
                <button class="veh-tab ${this._tab === 'vehicles' ? 'active' : ''}" data-tab="vehicles">🚗 Avtomobillar (${this._vehicles.length})</button>
                <button class="veh-tab ${this._tab === 'orders' ? 'active' : ''}" data-tab="orders">🔧 Buyurtmalar (${this._orders.length})</button>
            </div>
            <div id="vehContent"></div>`;

        this._renderContent();

        this._container.querySelectorAll('.veh-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                this._tab = btn.dataset.tab;
                this._container.querySelectorAll('.veh-tab').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this._renderContent();
            });
        });
    }

    _renderContent() {
        const el = this._container.querySelector('#vehContent');
        if (!el) return;
        this._tab === 'vehicles' ? this._renderVehicles(el) : this._renderOrders(el);
    }

    _renderVehicles(el) {
        el.innerHTML = `
            <div class="veh-toolbar">
                <input class="veh-search" type="text" placeholder="Davlat raqami, model...">
                <button class="btn btn-primary veh-add-btn">+ Avtomobil qo'shish</button>
            </div>
            <div class="veh-grid" id="vehGrid">
                ${this._vehicles.length ? this._vehicles.map(v => this._vehicleCard(v)).join('') :
                  '<div class="veh-empty">Avtomobil topilmadi</div>'}
            </div>`;

        el.querySelector('.veh-search').addEventListener('input', (e) => {
            const s = e.target.value.toLowerCase();
            const grid = el.querySelector('#vehGrid');
            const list = s ? this._vehicles.filter(v =>
                v.plate_number?.toLowerCase().includes(s) ||
                v.brand?.toLowerCase().includes(s) ||
                v.model?.toLowerCase().includes(s)
            ) : this._vehicles;
            grid.innerHTML = list.map(v => this._vehicleCard(v)).join('') ||
                '<div class="veh-empty">Topilmadi</div>';
            this._attachVehicleEvents(grid);
        });
        el.querySelector('.veh-add-btn').addEventListener('click', () => this._openVehicleForm());
        this._attachVehicleEvents(el.querySelector('#vehGrid'));
    }

    _vehicleCard(v) {
        const cust = this._customers.find(c => c.id === v.customer_id);
        return `<div class="veh-card" data-id="${v.id}">
            <div class="veh-plate">${v.plate_number}</div>
            <div class="veh-info">${[v.brand, v.model, v.year].filter(Boolean).join(' · ')}</div>
            <div class="veh-color">${v.color || ''}</div>
            ${cust ? `<div class="veh-owner">👤 ${cust.name}</div>` : ''}
            <div class="veh-actions">
                <button class="btn btn-sm btn-outline veh-order-btn">+ Buyurtma</button>
                <button class="btn btn-sm btn-outline veh-edit-btn">✏️</button>
            </div>
        </div>`;
    }

    _attachVehicleEvents(grid) {
        grid.querySelectorAll('.veh-order-btn').forEach(btn => {
            const id = btn.closest('.veh-card').dataset.id;
            btn.addEventListener('click', () => this._openOrderForm(parseInt(id)));
        });
        grid.querySelectorAll('.veh-edit-btn').forEach(btn => {
            const id = btn.closest('.veh-card').dataset.id;
            btn.addEventListener('click', () => this._openVehicleForm(this._vehicles.find(v => v.id == id)));
        });
    }

    _renderOrders(el) {
        el.innerHTML = `
            <div class="veh-toolbar">
                <select class="order-status-filter">
                    <option value="">Barcha holatlar</option>
                    ${Object.entries(ORDER_STATUS).map(([v, l]) =>
                        `<option value="${v}">${l.label}</option>`
                    ).join('')}
                </select>
                <button class="btn btn-primary order-add-btn">+ Yangi buyurtma</button>
            </div>
            <div class="order-list" id="orderList">
                ${this._renderOrderList(this._orders)}
            </div>`;

        el.querySelector('.order-status-filter').addEventListener('change', (e) => {
            const list = e.target.value
                ? this._orders.filter(o => o.status === e.target.value)
                : this._orders;
            el.querySelector('#orderList').innerHTML = this._renderOrderList(list);
            this._attachOrderEvents(el.querySelector('#orderList'));
        });
        el.querySelector('.order-add-btn').addEventListener('click', () => this._openOrderForm());
        this._attachOrderEvents(el.querySelector('#orderList'));
    }

    _renderOrderList(orders) {
        if (!orders.length) return '<div class="veh-empty">Buyurtma topilmadi</div>';
        return orders.map(o => {
            const v   = this._vehicles.find(v => v.id === o.vehicle_id);
            const st  = ORDER_STATUS[o.status] || { label: o.status, cls: '' };
            return `<div class="order-item" data-id="${o.id}">
                <div class="order-num">${o.order_number || '#' + o.id}</div>
                <div class="order-vehicle">${v ? v.plate_number + ' · ' + (v.brand || '') : '—'}</div>
                <div class="order-desc">${o.description}</div>
                <div class="order-amount">${formatMoney(o.total_amount)}</div>
                <span class="badge ${st.cls}">${st.label}</span>
                <div class="order-actions">
                    ${o.status !== 'delivered' ? `
                    <button class="btn btn-sm btn-outline order-next-btn">Keyingi holat</button>` : ''}
                </div>
            </div>`;
        }).join('');
    }

    _attachOrderEvents(el) {
        el.querySelectorAll('.order-next-btn').forEach(btn => {
            const id    = btn.closest('.order-item').dataset.id;
            const order = this._orders.find(o => o.id == id);
            btn.addEventListener('click', () => this._nextStatus(order));
        });
    }

    async _nextStatus(order) {
        const flow = ['pending', 'in_progress', 'done', 'delivered'];
        const idx  = flow.indexOf(order.status);
        if (idx === -1 || idx === flow.length - 1) return;
        const res = await this._api.patch(`/vehicles/orders/${order.id}`, { status: flow[idx + 1] });
        if (res.success) {
            showToast(`Holat: ${ORDER_STATUS[flow[idx + 1]]?.label}`, 'success');
            await this._load();
            this._renderContent();
        }
    }

    _openVehicleForm(v = null) {
        const modal = document.createElement('div');
        modal.className = 'modal open';
        modal.innerHTML = `
            <div class="modal-overlay"></div>
            <div class="modal-content glass" style="max-width:460px">
                <div class="modal-header">
                    <h2>${v ? 'Avtomobilni tahrirlash' : 'Yangi avtomobil'}</h2>
                    <button class="modal-close btn-icon glass">&times;</button>
                </div>
                <div class="modal-body">
                    <form class="veh-form">
                        <div class="form-group">
                            <label>Davlat raqami *</label>
                            <input type="text" name="plate_number" value="${v?.plate_number || ''}" placeholder="01A 123 BC" required>
                        </div>
                        <div class="form-group">
                            <label>Brend</label>
                            <input type="text" name="brand" value="${v?.brand || ''}" placeholder="Chevrolet">
                        </div>
                        <div class="form-group">
                            <label>Model</label>
                            <input type="text" name="model" value="${v?.model || ''}" placeholder="Cobalt">
                        </div>
                        <div class="form-group">
                            <label>Yil</label>
                            <input type="number" name="year" value="${v?.year || ''}" min="1970" max="2030">
                        </div>
                        <div class="form-group">
                            <label>Rang</label>
                            <input type="text" name="color" value="${v?.color || ''}" placeholder="Oq">
                        </div>
                        <div class="form-group">
                            <label>Mijoz</label>
                            <select name="customer_id">
                                <option value="">Tanlang</option>
                                ${this._customers.map(c =>
                                    `<option value="${c.id}" ${v?.customer_id === c.id ? 'selected' : ''}>${c.name}</option>`
                                ).join('')}
                            </select>
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
            if (data.year)        data.year        = parseInt(data.year);
            if (data.customer_id) data.customer_id = parseInt(data.customer_id) || null;
            else                  delete data.customer_id;

            const res = v
                ? await this._api.patch(`/vehicles/${v.id}`, data)
                : await this._api.post('/vehicles/', data);

            if (res.success) {
                showToast('Saqlandi', 'success');
                modal.remove();
                await this._load();
                this._renderContent();
            } else {
                showToast(res.error || 'Xatolik', 'error');
            }
        });
    }

    _openOrderForm(vehicleId = null) {
        const vehicle = this._vehicles.find(v => v.id === vehicleId);
        const modal   = document.createElement('div');
        modal.className = 'modal open';
        modal.innerHTML = `
            <div class="modal-overlay"></div>
            <div class="modal-content glass" style="max-width:480px">
                <div class="modal-header">
                    <h2>Yangi xizmat buyurtmasi</h2>
                    <button class="modal-close btn-icon glass">&times;</button>
                </div>
                <div class="modal-body">
                    <form class="order-form">
                        <div class="form-group">
                            <label>Avtomobil</label>
                            <select name="vehicle_id">
                                <option value="">Tanlang</option>
                                ${this._vehicles.map(v =>
                                    `<option value="${v.id}" ${v.id === vehicleId ? 'selected' : ''}>${v.plate_number} · ${v.brand || ''}</option>`
                                ).join('')}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Muammo tavsifi *</label>
                            <textarea name="description" rows="3" required placeholder="Nima muammo bor?"></textarea>
                        </div>
                        <div class="form-group">
                            <label>Narxi (so'm)</label>
                            <input type="number" name="total_amount" min="0" value="0">
                        </div>
                        <div class="form-group">
                            <label>Qabul qilish sanasi</label>
                            <input type="datetime-local" name="intake_date" value="${new Date().toISOString().slice(0,16)}" required>
                        </div>
                        <div class="form-group">
                            <label>Izoh</label>
                            <textarea name="notes" rows="2"></textarea>
                        </div>
                        <div class="modal-actions">
                            <button type="button" class="btn btn-outline modal-close">Bekor qilish</button>
                            <button type="submit" class="btn btn-primary">Yaratish</button>
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
            data.total_amount = parseFloat(data.total_amount) || 0;
            if (data.vehicle_id) data.vehicle_id = parseInt(data.vehicle_id);
            else delete data.vehicle_id;

            const res = await this._api.post('/vehicles/orders/', data);
            if (res.success) {
                showToast('Buyurtma yaratildi', 'success');
                modal.remove();
                await this._load();
                this._tab = 'orders';
                this._render();
            } else {
                showToast(res.error || 'Xatolik', 'error');
            }
        });
    }
}
