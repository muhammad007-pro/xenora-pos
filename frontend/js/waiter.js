import { API } from './core/api.js';
import { AuthService } from './core/auth.js';
import { WebSocketManager } from './core/socket.js';
import { showToast } from './ui/toast.js';
import { formatMoney, formatTime } from './utils/formatter.js';

class WaiterModule {
    constructor() {
        this.api = new API();
        this.auth = new AuthService();
        this.ws = new WebSocketManager();
        this.tables = [];
        this.activeOrders = [];
        this.currentShift = null;
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        this.setupWebSocket();
        await this.loadInitialData();
        this.renderTables();
        this.renderOrders();
        this.updateUI();
    }
    
    setupEventListeners() {
        document.querySelectorAll('.quick-action').forEach(btn => {
            btn.addEventListener('click', () => this.handleQuickAction(btn.dataset.action));
        });
    }
    
    setupWebSocket() {
        this.ws.connect();
        
        this.ws.on('new_order', (data) => {
            this.activeOrders.push(data);
            this.renderOrders();
            showToast('Yangi buyurtma!', 'info');
        });
        
        this.ws.on('order_ready', (data) => {
            showToast(`Buyurtma #${data.order_number} tayyor!`, 'success');
        });
        
        this.ws.on('table_status_changed', (data) => {
            const table = this.tables.find(t => t.id === data.table_id);
            if (table) {
                table.status = data.status;
                this.renderTables();
            }
        });
    }
    
    async loadInitialData() {
        const [tablesRes, ordersRes, shiftRes] = await Promise.all([
            this.api.get('/tables/all'),
            this.api.get('/orders', { status: 'pending,preparing,ready' }),
            this.api.get('/shifts/active')
        ]);
        
        this.tables = tablesRes.data || [];
        this.activeOrders = ordersRes.data?.items || [];
        this.currentShift = shiftRes.data;
    }
    
    renderTables() {
        const grid = document.getElementById('waiterTablesGrid');
        
        grid.innerHTML = this.tables.map(table => `
            <div class="table-card ${table.status}" data-id="${table.id}">
                <div class="table-number">${table.number}</div>
                <div class="table-status">${this.getTableStatusText(table.status)}</div>
                <div class="table-capacity">${table.capacity} kishi</div>
                ${table.current_order ? `<div class="table-order">#${table.current_order.order_number}</div>` : ''}
            </div>
        `).join('');
        
        grid.querySelectorAll('.table-card').forEach(card => {
            card.addEventListener('click', () => this.selectTable(card.dataset.id));
        });
    }
    
    renderOrders() {
        const list = document.getElementById('waiterOrdersList');
        
        if (this.activeOrders.length === 0) {
            list.innerHTML = '<div class="empty-state">Faol buyurtmalar yo\'q</div>';
            return;
        }
        
        list.innerHTML = this.activeOrders.map(order => `
            <div class="order-card ${order.status}" data-id="${order.id}">
                <div class="order-header">
                    <span class="order-number">#${order.order_number}</span>
                    <span class="order-status">${this.getOrderStatusText(order.status)}</span>
                </div>
                <div class="order-info">
                    <span>Stol: ${order.table_number || '-'}</span>
                    <span>${formatTime(order.created_at)}</span>
                </div>
                <div class="order-items">
                    ${order.items?.slice(0, 3).map(i => `
                        <div>${i.quantity}x ${i.product_name}</div>
                    `).join('')}
                    ${order.items?.length > 3 ? `<div>+${order.items.length - 3} ta...</div>` : ''}
                </div>
                <div class="order-footer">
                    <span class="order-total">${formatMoney(order.final_amount)}</span>
                    <div class="order-actions">
                        <button class="btn-icon view-order" data-id="${order.id}">👁️</button>
                        <button class="btn-icon payment-order" data-id="${order.id}">💰</button>
                    </div>
                </div>
            </div>
        `).join('');
        
        list.querySelectorAll('.view-order').forEach(btn => {
            btn.addEventListener('click', () => this.viewOrder(btn.dataset.id));
        });
        
        list.querySelectorAll('.payment-order').forEach(btn => {
            btn.addEventListener('click', () => this.processPayment(btn.dataset.id));
        });
    }
    
    handleQuickAction(action) {
        switch(action) {
            case 'new-order':
                window.location.href = 'app/pos.html';
                break;
            case 'shift-close':
                this.closeShift();
                break;
            default:
                showToast('Tez orada...', 'info');
        }
    }
    
    selectTable(tableId) {
        window.location.href = `app/pos.html?table=${tableId}`;
    }
    
    viewOrder(orderId) {
        window.location.href = `app/pos.html?order=${orderId}`;
    }
    
    processPayment(orderId) {
        window.location.href = `payments.html?order=${orderId}`;
    }
    
    async closeShift() {
        if (!this.currentShift) {
            showToast('Faol smena yo\'q', 'warning');
            return;
        }
        
        const endingCash = prompt('Yakuniy kassa summasini kiriting:');
        if (!endingCash) return;
        
        try {
            await this.api.post(`/shifts/${this.currentShift.id}/close`, {
                ending_cash: parseFloat(endingCash)
            });
            showToast('Smena yopildi', 'success');
            window.location.href = 'shared/login.html';
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    updateUI() {
        const user = this.auth.getCurrentUser();
        if (user) {
            document.getElementById('waiterName').textContent = user.full_name;
        }
        
        if (this.currentShift) {
            const startTime = new Date(this.currentShift.start_time);
            document.getElementById('currentShift').textContent = 
                `Smena: ${startTime.getHours()}:${String(startTime.getMinutes()).padStart(2, '0')} - hozir`;
        }
    }
    
    getTableStatusText(status) {
        const texts = { free: 'Bo\'sh', occupied: 'Band', reserved: 'Bron' };
        return texts[status] || status;
    }
    
    getOrderStatusText(status) {
        const texts = {
            pending: 'Kutilmoqda',
            preparing: 'Tayyorlanmoqda',
            ready: 'Tayyor'
        };
        return texts[status] || status;
    }
}

document.addEventListener('DOMContentLoaded', () => new WaiterModule());