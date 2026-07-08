/**
 * Appointment / Booking moduli (BOSQICH 4.4)
 *
 * Salon, fitnes, auto-servis, maktab uchun:
 *   - Kunlik/haftalik kalendar
 *   - Vaqt oraliqlari (time slots)
 *   - Xizmatga master tayinlash
 *   - Mijoz bron qilishi
 *
 * API endpointlar: /appointments/
 */

import { API }       from '../core/api.js';
import { showToast } from '../ui/toast.js';
import { formatMoney } from '../utils/formatter.js';

const SLOT_MINUTES = 30;     // vaqt oralig'i (daqiqa)
const WORK_START   = 9 * 60; // 09:00 (daqiqada)
const WORK_END     = 21 * 60;// 21:00

export class AppointmentModule {
    constructor() {
        this._api          = new API();
        this._appointments = [];
        this._services     = [];
        this._employees    = [];
        this._selectedDate = new Date();
        this._view         = 'day';  // day | week
    }

    async init(containerId) {
        this._container = document.getElementById(containerId);
        if (!this._container) return;

        await this._loadData();
        this._render();
    }

    async _loadData() {
        const [aptRes, svcRes, empRes] = await Promise.all([
            this._api.get('/appointments/', { date: this._dateStr() }),
            this._api.get('/services/'),
            this._api.get('/employees/', { role: 'master' }),
        ]);

        if (aptRes.success) this._appointments = aptRes.data?.items || [];
        if (svcRes.success) this._services     = svcRes.data?.items || [];
        if (empRes.success) this._employees    = empRes.data?.items || [];
    }

    _render() {
        if (!this._container) return;
        this._container.innerHTML = `
            <div class="apt-header">
                <div class="apt-nav">
                    <button class="btn-icon glass" id="aptPrev">&#8249;</button>
                    <h3 class="apt-date-title" id="aptDateTitle">${this._formatDate()}</h3>
                    <button class="btn-icon glass" id="aptNext">&#8250;</button>
                </div>
                <div class="apt-view-toggle">
                    <button class="apt-view-btn ${this._view === 'day' ? 'active' : ''}" data-view="day">Kun</button>
                    <button class="apt-view-btn ${this._view === 'week' ? 'active' : ''}" data-view="week">Hafta</button>
                </div>
                <button class="btn btn-primary" id="aptNewBtn">+ Yangi bron</button>
            </div>
            <div class="apt-calendar" id="aptCalendar">
                ${this._view === 'day' ? this._renderDayView() : this._renderWeekView()}
            </div>`;

        this._attachEvents();
    }

    _renderDayView() {
        const slots = this._generateSlots();
        const cols  = this._employees.length || 1;

        const header = `<div class="apt-grid" style="--cols:${cols + 1}">
            <div class="apt-time-col"></div>
            ${this._employees.map(e => `<div class="apt-emp-header">${e.full_name}</div>`).join('')}
        `;

        const rows = slots.map(slot => {
            const timeLabel = this._slotLabel(slot);
            const cells = this._employees.length
                ? this._employees.map(emp => {
                    const apt = this._appointments.find(a =>
                        a.employee_id === emp.id && this._slotOf(a) === slot
                    );
                    return apt
                        ? `<div class="apt-cell occupied" data-id="${apt.id}" style="background:${this._serviceColor(apt.service_id)}">
                               <span class="apt-customer">${apt.customer_name}</span>
                               <span class="apt-service">${apt.service_name}</span>
                           </div>`
                        : `<div class="apt-cell empty" data-slot="${slot}" data-emp="${emp.id}"></div>`;
                }).join('')
                : `<div class="apt-cell empty" data-slot="${slot}"></div>`;

            return `<div class="apt-time-label">${timeLabel}</div>${cells}`;
        }).join('');

        return header + rows + '</div>';
    }

    _renderWeekView() {
        const days = [];
        const start = new Date(this._selectedDate);
        start.setDate(start.getDate() - start.getDay() + 1); // Dushanba

        for (let i = 0; i < 7; i++) {
            const d = new Date(start);
            d.setDate(start.getDate() + i);
            const dayStr = d.toISOString().slice(0, 10);
            const dayApts = this._appointments.filter(a => a.date === dayStr);
            const dayNames = ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sha', 'Ya'];

            days.push(`
                <div class="week-day ${this._isToday(d) ? 'today' : ''}">
                    <div class="week-day-header">
                        <span class="week-day-name">${dayNames[i]}</span>
                        <span class="week-day-num">${d.getDate()}</span>
                    </div>
                    <div class="week-day-apts">
                        ${dayApts.map(a => `
                            <div class="week-apt" data-id="${a.id}" style="background:${this._serviceColor(a.service_id)}">
                                <span>${a.start_time}</span>
                                <span>${a.customer_name}</span>
                            </div>`).join('') || '<div class="week-empty">—</div>'}
                    </div>
                </div>`);
        }

        return `<div class="week-view">${days.join('')}</div>`;
    }

    _attachEvents() {
        this._container.querySelector('#aptPrev')?.addEventListener('click', () => {
            this._shiftDate(-1);
        });
        this._container.querySelector('#aptNext')?.addEventListener('click', () => {
            this._shiftDate(+1);
        });
        this._container.querySelectorAll('.apt-view-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this._view = btn.dataset.view;
                this._render();
            });
        });
        this._container.querySelector('#aptNewBtn')?.addEventListener('click', () => {
            this._openNewBookingModal();
        });

        // Bo'sh katakka bosish → yangi bron
        this._container.querySelectorAll('.apt-cell.empty').forEach(cell => {
            cell.addEventListener('click', () => {
                this._openNewBookingModal({
                    slot:       cell.dataset.slot,
                    employeeId: cell.dataset.emp,
                });
            });
        });

        // Band katakka bosish → bron tafsiloti
        this._container.querySelectorAll('.apt-cell.occupied').forEach(cell => {
            cell.addEventListener('click', () => {
                this._showAppointmentDetail(parseInt(cell.dataset.id));
            });
        });
    }

    async _openNewBookingModal(defaults = {}) {
        const modal = document.createElement('div');
        modal.className = 'modal apt-modal open';
        modal.innerHTML = `
            <div class="modal-overlay"></div>
            <div class="modal-content glass">
                <div class="modal-header">
                    <h2>Yangi bron</h2>
                    <button class="modal-close btn-icon glass">&times;</button>
                </div>
                <div class="modal-body">
                    <form id="aptForm" class="apt-form">
                        <div class="form-group">
                            <label>Mijoz ismi</label>
                            <input type="text" name="customer_name" placeholder="To'liq ism" required>
                        </div>
                        <div class="form-group">
                            <label>Telefon</label>
                            <input type="tel" name="customer_phone" placeholder="+998xx">
                        </div>
                        <div class="form-group">
                            <label>Xizmat</label>
                            <select name="service_id" required>
                                <option value="">Tanlang...</option>
                                ${this._services.map(s => `<option value="${s.id}">${s.name} — ${formatMoney(s.price)}</option>`).join('')}
                            </select>
                        </div>
                        ${this._employees.length ? `
                        <div class="form-group">
                            <label>Master</label>
                            <select name="employee_id">
                                <option value="">Istalgan</option>
                                ${this._employees.map(e => `<option value="${e.id}" ${defaults.employeeId == e.id ? 'selected' : ''}>${e.full_name}</option>`).join('')}
                            </select>
                        </div>` : ''}
                        <div class="form-group">
                            <label>Sana</label>
                            <input type="date" name="date" value="${this._dateStr()}" required>
                        </div>
                        <div class="form-group">
                            <label>Vaqt</label>
                            <select name="start_time" required>
                                ${this._generateSlots().map(slot => {
                                    const lbl = this._slotLabel(slot);
                                    const sel = defaults.slot == slot ? 'selected' : '';
                                    return `<option value="${lbl}" ${sel}>${lbl}</option>`;
                                }).join('')}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Izoh</label>
                            <textarea name="notes" rows="2" placeholder="Qo'shimcha ma'lumot..."></textarea>
                        </div>
                        <div class="modal-actions">
                            <button type="button" class="btn btn-outline modal-close">Bekor qilish</button>
                            <button type="submit" class="btn btn-primary">Saqlash</button>
                        </div>
                    </form>
                </div>
            </div>`;

        document.body.appendChild(modal);
        modal.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => modal.remove());
        });
        modal.querySelector('.modal-overlay').addEventListener('click', () => modal.remove());

        modal.querySelector('#aptForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const fd   = new FormData(e.target);
            const data = Object.fromEntries(fd.entries());
            const res  = await this._api.post('/appointments/', data);
            if (res.success) {
                showToast('Bron saqlandi', 'success');
                modal.remove();
                await this._loadData();
                this._render();
            } else {
                showToast(res.error || 'Xatolik', 'error');
            }
        });
    }

    _showAppointmentDetail(id) {
        const apt = this._appointments.find(a => a.id === id);
        if (!apt) return;

        const modal = document.createElement('div');
        modal.className = 'modal apt-modal open';
        modal.innerHTML = `
            <div class="modal-overlay"></div>
            <div class="modal-content glass">
                <div class="modal-header">
                    <h2>Bron #${apt.id}</h2>
                    <button class="modal-close btn-icon glass">&times;</button>
                </div>
                <div class="modal-body apt-detail">
                    <div class="detail-row"><span>Mijoz:</span><strong>${apt.customer_name}</strong></div>
                    <div class="detail-row"><span>Telefon:</span><strong>${apt.customer_phone || '—'}</strong></div>
                    <div class="detail-row"><span>Xizmat:</span><strong>${apt.service_name}</strong></div>
                    <div class="detail-row"><span>Master:</span><strong>${apt.employee_name || 'Belgilanmagan'}</strong></div>
                    <div class="detail-row"><span>Vaqt:</span><strong>${apt.date} ${apt.start_time}</strong></div>
                    <div class="detail-row"><span>Holat:</span><span class="status-badge status-${apt.status}">${this._statusLabel(apt.status)}</span></div>
                    ${apt.notes ? `<div class="detail-row"><span>Izoh:</span><span>${apt.notes}</span></div>` : ''}
                    <div class="modal-actions">
                        <button class="btn btn-danger" id="aptCancel">Bekor qilish</button>
                        <button class="btn btn-primary" id="aptComplete">Yakunlash</button>
                    </div>
                </div>
            </div>`;

        document.body.appendChild(modal);
        modal.querySelectorAll('.modal-close, .modal-overlay').forEach(el => {
            el.addEventListener('click', () => modal.remove());
        });

        modal.querySelector('#aptCancel')?.addEventListener('click', async () => {
            await this._updateStatus(id, 'cancelled');
            modal.remove();
        });
        modal.querySelector('#aptComplete')?.addEventListener('click', async () => {
            await this._updateStatus(id, 'completed');
            modal.remove();
        });
    }

    async _updateStatus(id, status) {
        const res = await this._api.patch(`/appointments/${id}`, { status });
        if (res.success) {
            showToast(`Holat: ${this._statusLabel(status)}`, 'success');
            await this._loadData();
            this._render();
        }
    }

    // ── Yordamchilar ──────────────────────────────────────────────────────

    _generateSlots() {
        const slots = [];
        for (let m = WORK_START; m < WORK_END; m += SLOT_MINUTES) slots.push(m);
        return slots;
    }

    _slotLabel(minutes) {
        const h = Math.floor(minutes / 60).toString().padStart(2, '0');
        const m = (minutes % 60).toString().padStart(2, '0');
        return `${h}:${m}`;
    }

    _slotOf(apt) {
        const [h, m] = apt.start_time.split(':').map(Number);
        return h * 60 + m;
    }

    _dateStr(d = this._selectedDate) {
        return d.toISOString().slice(0, 10);
    }

    _formatDate() {
        return this._selectedDate.toLocaleDateString('uz-UZ', { weekday:'long', year:'numeric', month:'long', day:'numeric' });
    }

    _isToday(d) {
        const today = new Date();
        return d.toDateString() === today.toDateString();
    }

    _shiftDate(delta) {
        const d = new Date(this._selectedDate);
        if (this._view === 'day')  d.setDate(d.getDate() + delta);
        if (this._view === 'week') d.setDate(d.getDate() + delta * 7);
        this._selectedDate = d;
        this._loadData().then(() => this._render());
    }

    _serviceColor(serviceId) {
        const colors = ['#c9a84c', '#4caf50', '#2196f3', '#e91e63', '#9c27b0', '#ff5722'];
        return colors[(serviceId || 0) % colors.length] + '33';
    }

    _statusLabel(status) {
        const map = { pending:'Kutilmoqda', confirmed:'Tasdiqlangan', completed:'Yakunlangan', cancelled:'Bekor qilingan', no_show:"Ko'rinmadi" };
        return map[status] || status;
    }
}
