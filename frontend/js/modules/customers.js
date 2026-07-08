import { API } from '../core/api.js';
import { Modal } from '../ui/modal.js';
import { showToast } from '../ui/toast.js';
import { formatMoney, formatDate, formatPhone } from '../utils/formatter.js';
import { debounce } from '../utils/helpers.js';

class CustomersModule {
    constructor() {
        this.api = new API();
        this.customers = [];
        this.currentCustomer = null;
        this.modal = new Modal('customerModal');
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadCustomers();
        this.renderCustomers();
    }
    
    setupEventListeners() {
        document.getElementById('addCustomerBtn')?.addEventListener('click', () => this.openModal());
        document.getElementById('saveCustomerBtn')?.addEventListener('click', () => this.saveCustomer());
        document.getElementById('customerSearch')?.addEventListener('input', debounce((e) => this.searchCustomers(e.target.value), 300));
        
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => this.modal.close());
        });
    }
    
    async loadCustomers() {
        const response = await this.api.get('/customers');
        this.customers = response.data?.items || [];
    }
    
    renderCustomers(customers = null) {
        const tbody = document.getElementById('customersTableBody');
        const displayCustomers = customers || this.customers;
        
        if (displayCustomers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center">Mijozlar topilmadi</td></tr>';
            return;
        }
        
        tbody.innerHTML = displayCustomers.map(customer => `
            <tr>
                <td>${customer.id}</td>
                <td>
                    <div class="customer-info">
                        <span class="customer-name">${customer.name}</span>
                    </div>
                </td>
                <td>${formatPhone(customer.phone) || '-'}</td>
                <td>${customer.email || '-'}</td>
                <td>${customer.total_visits || 0}</td>
                <td>${formatMoney(customer.total_spent || 0)}</td>
                <td>${customer.points || 0}</td>
                <td>
                    <div class="actions">
                        <button class="btn-icon view-customer" data-id="${customer.id}" title="Ko'rish">👁️</button>
                        <button class="btn-icon edit-customer" data-id="${customer.id}" title="Tahrirlash">✏️</button>
                        <button class="btn-icon customer-orders" data-id="${customer.id}" title="Buyurtmalar">📋</button>
                    </div>
                </td>
            </tr>
        `).join('');
        
        tbody.querySelectorAll('.view-customer').forEach(btn => {
            btn.addEventListener('click', () => this.viewCustomer(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.edit-customer').forEach(btn => {
            btn.addEventListener('click', () => this.editCustomer(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.customer-orders').forEach(btn => {
            btn.addEventListener('click', () => this.showCustomerOrders(btn.dataset.id));
        });
        
        document.getElementById('customersCount').textContent = displayCustomers.length;
    }
    
    async searchCustomers(query) {
        if (!query) {
            this.renderCustomers();
            return;
        }
        
        const response = await this.api.get('/customers/search', { query });
        this.renderCustomers(response.data || []);
    }
    
    openModal(customer = null) {
        this.currentCustomer = customer;
        const form = document.getElementById('customerForm');
        const title = document.getElementById('customerModalTitle');
        
        form.reset();
        
        if (customer) {
            title.textContent = 'Mijozni tahrirlash';
            form.name.value = customer.name || '';
            form.phone.value = customer.phone || '';
            form.email.value = customer.email || '';
            form.birthday.value = customer.birthday?.split('T')[0] || '';
        } else {
            title.textContent = 'Yangi mijoz';
        }
        
        this.modal.open();
    }
    
    async saveCustomer() {
        const form = document.getElementById('customerForm');
        const data = Object.fromEntries(new FormData(form));
        
        try {
            if (this.currentCustomer) {
                await this.api.patch(`/customers/${this.currentCustomer.id}`, data);
                showToast('Mijoz yangilandi', 'success');
            } else {
                await this.api.post('/customers', data);
                showToast('Mijoz yaratildi', 'success');
            }
            
            await this.loadCustomers();
            this.renderCustomers();
            this.modal.close();
        } catch (error) {
            showToast(error.message || 'Xatolik yuz berdi', 'error');
        }
    }
    
    viewCustomer(id) {
        const customer = this.customers.find(c => c.id == id);
        if (!customer) return;
        
        this.showCustomerDetails(customer);
    }
    
    editCustomer(id) {
        const customer = this.customers.find(c => c.id == id);
        if (customer) this.openModal(customer);
    }
    
    async showCustomerOrders(id) {
        try {
            const response = await this.api.get(`/customers/${id}/orders`);
            const orders = response.data?.items || [];
            
            const ordersHtml = orders.map(order => `
                <div class="order-item">
                    <span>#${order.order_number}</span>
                    <span>${formatDate(order.created_at)}</span>
                    <span>${formatMoney(order.final_amount)}</span>
                    <span class="status-badge ${order.status}">${order.status}</span>
                </div>
            `).join('');
            
            // Modalda ko'rsatish
            const detailModal = new Modal('customerOrdersModal');
            const container = document.getElementById('customerOrdersList');
            if (container) {
                container.innerHTML = ordersHtml || '<p>Buyurtmalar topilmadi</p>';
            }
            detailModal.open();
        } catch (error) {
            showToast('Buyurtmalarni yuklashda xatolik', 'error');
        }
    }
    
    showCustomerDetails(customer) {
        const detailModal = new Modal('customerDetailModal');
        
        document.getElementById('detailName').textContent = customer.name;
        document.getElementById('detailPhone').textContent = formatPhone(customer.phone) || '-';
        document.getElementById('detailEmail').textContent = customer.email || '-';
        document.getElementById('detailVisits').textContent = customer.total_visits || 0;
        document.getElementById('detailSpent').textContent = formatMoney(customer.total_spent || 0);
        document.getElementById('detailPoints').textContent = customer.points || 0;
        document.getElementById('detailCreated').textContent = formatDate(customer.created_at);
        
        detailModal.open();
    }
}

document.addEventListener('DOMContentLoaded', () => new CustomersModule());