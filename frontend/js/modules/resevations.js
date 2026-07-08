import { API } from '../core/api.js';
import { Modal } from '../ui/modal.js';
import { showToast } from '../ui/toast.js';
import { formatDate, formatTime, formatPhone } from '../utils/formatter.js';

class ReservationsModule {
    constructor() {
        this.api = new API();
        this.reservations = [];
        this.tables = [];
        this.customers = [];
        this.currentReservation = null;
        this.modal = new Modal('reservationModal');
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadTables();
        await this.loadCustomers();
        await this.loadReservations();
        this.renderReservations();
    }
    
    setupEventListeners() {
        document.getElementById('addReservationBtn')?.addEventListener('click', () => this.openModal());
        document.getElementById('saveReservationBtn')?.addEventListener('click', () => this.saveReservation());
        document.getElementById('filterDate')?.addEventListener('change', (e) => this.filterByDate(e.target.value));
        document.getElementById('filterStatus')?.addEventListener('change', () => this.filterReservations());
        
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => this.modal.close());
        });
    }
    
    async loadTables() {
        const response = await this.api.get('/tables/all');
        this.tables = response.data || [];
        this.populateTableSelect();
    }
    
    async loadCustomers() {
        const response = await this.api.get('/customers/all');
        this.customers = response.data || [];
        this.populateCustomerSelect();
    }
    
    async loadReservations() {
        const response = await this.api.get('/reservations');
        this.reservations = response.data?.items || [];
    }
    
    populateTableSelect() {
        const select = document.getElementById('reservationTable');
        if (select) {
            select.innerHTML = '<option value="">Stol tanlang</option>' +
                this.tables.map(t => `<option value="${t.id}">Stol #${t.number} (${t.capacity} kishi)</option>`).join('');
        }
    }
    
    populateCustomerSelect() {
        const select = document.getElementById('reservationCustomer');
        if (select) {
            select.innerHTML = '<option value="">Mijoz tanlang</option>' +
                this.customers.map(c => `<option value="${c.id}">${c.name} - ${formatPhone(c.phone)}</option>`).join('');
        }
    }
    
    renderReservations(reservations = null) {
        const container = document.getElementById('reservationsList');
        const displayReservations = reservations || this.reservations;
        
        if (displayReservations.length === 0) {
            container.innerHTML = '<div class="empty-state">Bronlar yo\'q</div>';
            return;
        }
        
        // Sana bo'yicha guruhlash
        const grouped = this.groupByDate(displayReservations);
        
        container.innerHTML = Object.entries(grouped).map(([date, items]) => `
            <div class="reservation-group">
                <h3 class="group-date">${formatDate(date)}</h3>
                <div class="reservations-grid">
                    ${items.map(r => this.createReservationCard(r)).join('')}
                </div>
            </div>
        `).join('');
        
        container.querySelectorAll('.edit-reservation').forEach(btn => {
            btn.addEventListener('click', () => this.editReservation(btn.dataset.id));
        });
        
        container.querySelectorAll('.cancel-reservation').forEach(btn => {
            btn.addEventListener('click', () => this.cancelReservation(btn.dataset.id));
        });
        
        container.querySelectorAll('.confirm-reservation').forEach(btn => {
            btn.addEventListener('click', () => this.updateStatus(btn.dataset.id, 'confirmed'));
        });
        
        container.querySelectorAll('.complete-reservation').forEach(btn => {
            btn.addEventListener('click', () => this.updateStatus(btn.dataset.id, 'completed'));
        });
    }
    
    createReservationCard(reservation) {
        const statusClass = this.getStatusClass(reservation.status);
        const statusText = this.getStatusText(reservation.status);
        
        return `
            <div class="reservation-card glass ${statusClass}" data-id="${reservation.id}">
                <div class="reservation-header">
                    <span class="reservation-time">
                        <strong>${formatTime(reservation.reservation_time)}</strong>
                    </span>
                    <span class="reservation-status ${statusClass}">${statusText}</span>
                </div>
                <div class="reservation-body">
                    <p><strong>${reservation.customer?.name || 'Mijoz'}</strong></p>
                    <p>📞 ${formatPhone(reservation.customer?.phone) || '-'}</p>
                    <p>🪑 Stol #${reservation.table?.number || '-'} • ${reservation.guests_count} kishi</p>
                    ${reservation.notes ? `<p class="notes">📝 ${reservation.notes}</p>` : ''}
                </div>
                <div class="reservation-footer">
                    ${this.getActionButtons(reservation)}
                </div>
            </div>
        `;
    }
    
    getActionButtons(reservation) {
        if (reservation.status === 'pending') {
            return `
                <button class="btn-icon confirm-reservation" data-id="${reservation.id}" title="Tasdiqlash">✅</button>
                <button class="btn-icon edit-reservation" data-id="${reservation.id}" title="Tahrirlash">✏️</button>
                <button class="btn-icon cancel-reservation" data-id="${reservation.id}" title="Bekor qilish">❌</button>
            `;
        } else if (reservation.status === 'confirmed') {
            return `
                <button class="btn-icon complete-reservation" data-id="${reservation.id}" title="Yakunlash">✔️</button>
                <button class="btn-icon cancel-reservation" data-id="${reservation.id}" title="Bekor qilish">❌</button>
            `;
        }
        return '';
    }
    
    groupByDate(reservations) {
        return reservations.reduce((groups, r) => {
            const date = r.reservation_time.split('T')[0];
            if (!groups[date]) groups[date] = [];
            groups[date].push(r);
            return groups;
        }, {});
    }
    
    filterByDate(date) {
        if (!date) {
            this.renderReservations();
            return;
        }
        
        const filtered = this.reservations.filter(r => 
            r.reservation_time.startsWith(date)
        );
        this.renderReservations(filtered);
    }
    
    filterReservations() {
        const status = document.getElementById('filterStatus')?.value;
        const date = document.getElementById('filterDate')?.value;
        
        let filtered = this.reservations;
        
        if (status) {
            filtered = filtered.filter(r => r.status === status);
        }
        
        if (date) {
            filtered = filtered.filter(r => r.reservation_time.startsWith(date));
        }
        
        this.renderReservations(filtered);
    }
    
    openModal(reservation = null) {
        this.currentReservation = reservation;
        const form = document.getElementById('reservationForm');
        const title = document.getElementById('reservationModalTitle');
        
        form.reset();
        this.populateTableSelect();
        this.populateCustomerSelect();
        
        // Default vaqtni ertaga qo'yish
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        tomorrow.setHours(19, 0, 0, 0);
        
        if (reservation) {
            title.textContent = 'Bronni tahrirlash';
            form.table_id.value = reservation.table_id;
            form.customer_id.value = reservation.customer_id;
            form.reservation_time.value = reservation.reservation_time.slice(0, 16);
            form.duration_minutes.value = reservation.duration_minutes;
            form.guests_count.value = reservation.guests_count;
            form.notes.value = reservation.notes || '';
        } else {
            title.textContent = 'Yangi bron';
            form.reservation_time.value = tomorrow.toISOString().slice(0, 16);
            form.duration_minutes.value = 120;
            form.guests_count.value = 2;
        }
        
        this.modal.open();
    }
    
    async saveReservation() {
        const form = document.getElementById('reservationForm');
        const data = Object.fromEntries(new FormData(form));
        
        data.table_id = parseInt(data.table_id);
        data.customer_id = parseInt(data.customer_id);
        data.duration_minutes = parseInt(data.duration_minutes);
        data.guests_count = parseInt(data.guests_count);
        
        try {
            if (this.currentReservation) {
                await this.api.patch(`/reservations/${this.currentReservation.id}`, data);
                showToast('Bron yangilandi', 'success');
            } else {
                await this.api.post('/reservations', data);
                showToast('Bron yaratildi', 'success');
            }
            
            await this.loadReservations();
            this.renderReservations();
            this.modal.close();
        } catch (error) {
            showToast(error.message || 'Xatolik yuz berdi', 'error');
        }
    }
    
    editReservation(id) {
        const reservation = this.reservations.find(r => r.id == id);
        if (reservation) this.openModal(reservation);
    }
    
    async updateStatus(id, status) {
        try {
            await this.api.patch(`/reservations/${id}/status`, { status });
            await this.loadReservations();
            this.renderReservations();
            showToast('Bron holati yangilandi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    async cancelReservation(id) {
        if (!confirm('Bronni bekor qilishni xohlaysizmi?')) return;
        
        try {
            await this.api.delete(`/reservations/${id}`);
            await this.loadReservations();
            this.renderReservations();
            showToast('Bron bekor qilindi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    getStatusClass(status) {
        const classes = {
            pending: 'warning',
            confirmed: 'success',
            cancelled: 'danger',
            completed: 'info'
        };
        return classes[status] || '';
    }
    
    getStatusText(status) {
        const texts = {
            pending: 'Kutilmoqda',
            confirmed: 'Tasdiqlangan',
            cancelled: 'Bekor qilingan',
            completed: 'Yakunlangan'
        };
        return texts[status] || status;
    }
}

document.addEventListener('DOMContentLoaded', () => new ReservationsModule());