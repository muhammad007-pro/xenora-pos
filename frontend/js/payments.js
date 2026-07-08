import { API } from './core/api.js';
import { AuthService } from './core/auth.js';
import { formatMoney, formatDateTime } from './utils/formatter.js';

class PaymentsModule {
    constructor() {
        this.api = new API();
        this.auth = new AuthService();
        this.payments = [];
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadPayments();
        this.renderPayments();
        this.updateSummary();
    }
    
    setupEventListeners() {
        document.getElementById('filterBtn')?.addEventListener('click', () => this.loadPayments());
        document.getElementById('dateFrom')?.value = this.getDefaultDate();
        document.getElementById('dateTo')?.value = this.getDefaultDate();
    }
    
    getDefaultDate() {
        return new Date().toISOString().split('T')[0];
    }
    
    async loadPayments() {
        const dateFrom = document.getElementById('dateFrom')?.value;
        const dateTo = document.getElementById('dateTo')?.value;
        const method = document.getElementById('paymentMethodFilter')?.value;
        
        const params = { date_from: dateFrom, date_to: dateTo };
        if (method) params.method = method;
        
        const response = await this.api.get('/payments', params);
        this.payments = response.data?.items || [];
    }
    
    renderPayments() {
        const tbody = document.getElementById('paymentsTableBody');
        tbody.innerHTML = this.payments.map(p => `
            <tr>
                <td>${p.id}</td>
                <td>#${p.order_id}</td>
                <td>${formatMoney(p.amount)}</td>
                <td>${this.getMethodName(p.method)}</td>
                <td><span class="status-badge ${p.status}">${this.getStatusName(p.status)}</span></td>
                <td>${p.cashier_id || '-'}</td>
                <td>${formatDateTime(p.created_at)}</td>
                <td>
                    <button class="btn-icon" onclick="window.printReceipt(${p.id})">
                        🖨️
                    </button>
                </td>
            </tr>
        `).join('');
    }
    
    updateSummary() {
        const total = this.payments.reduce((s, p) => s + p.amount, 0);
        const cash = this.payments.filter(p => p.method === 'cash').reduce((s, p) => s + p.amount, 0);
        const card = this.payments.filter(p => p.method === 'card').reduce((s, p) => s + p.amount, 0);
        const online = this.payments.filter(p => ['click', 'payme'].includes(p.method)).reduce((s, p) => s + p.amount, 0);
        
        document.getElementById('totalPayments').textContent = formatMoney(total);
        document.getElementById('cashTotal').textContent = formatMoney(cash);
        document.getElementById('cardTotal').textContent = formatMoney(card);
        document.getElementById('onlineTotal').textContent = formatMoney(online);
    }
    
    getMethodName(method) {
        const names = { cash: 'Naqd', card: 'Karta', click: 'Click', payme: 'Payme' };
        return names[method] || method;
    }
    
    getStatusName(status) {
        const names = { pending: 'Kutilmoqda', paid: 'To\'langan', refunded: 'Qaytarilgan' };
        return names[status] || status;
    }
}

document.addEventListener('DOMContentLoaded', () => new PaymentsModule());