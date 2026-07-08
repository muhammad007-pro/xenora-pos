import { API } from '../core/api.js';
import { AuthService } from '../core/auth.js';
import { WebSocketManager } from '../core/socket.js';
import { StateManager } from '../core/state.js';
import { showToast } from '../ui/toast.js';
import { Modal } from '../ui/modal.js';
import { formatTime, formatDuration } from '../utils/formatter.js';

class KitchenModule {
    constructor() {
        this.api = new API();
        this.auth = new AuthService();
        this.ws = new WebSocketManager();
        this.state = new StateManager();
        
        this.orders = {
            pending: [],
            preparing: [],
            ready: [],
            completed: []
        };
        
        this.currentStation = 'all';
        this.soundEnabled = true;
        this.autoRefreshInterval = null;
        this.timerInterval = null;
        this.currentOrder = null;
        
        this.modals = {
            orderDetail: new Modal('orderDetailModal'),
            history: new Modal('historyModal')
        };
        
        this.sounds = {
            newOrder: document.getElementById('newOrderSound'),
            urgent: document.getElementById('urgentOrderSound')
        };
        
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadInitialData();
        this.setupWebSocket();
        this.startAutoRefresh();
        this.startTimer();
        this.renderAllColumns();
        this.updateStats();
        this.loadSoundPreference();
        this.hideLoadingScreen();
    }
    
    setupEventListeners() {
        // Station change
        document.getElementById('stationSelect')?.addEventListener('change', (e) => {
            this.currentStation = e.target.value;
            this.refreshOrders();
        });
        
        // Refresh button
        document.getElementById('refreshBtn')?.addEventListener('click', () => this.refreshOrders());
        
        // Sound toggle
        document.getElementById('soundToggle')?.addEventListener('click', () => this.toggleSound());
        
        // Fullscreen
        document.getElementById('fullscreenBtn')?.addEventListener('click', () => this.toggleFullscreen());
        
        // Filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.setFilter(e.target.dataset.filter));
        });
        
        // History modal
        document.getElementById('historyBtn')?.addEventListener('click', () => this.openHistoryModal());
        document.getElementById('applyHistoryFilter')?.addEventListener('click', () => this.loadHistory());
        
        // Print summary
        document.getElementById('printSummaryBtn')?.addEventListener('click', () => this.printSummary());
        
        // Logout
        document.getElementById('logoutBtn')?.addEventListener('click', () => this.logout());
        
        // Modal actions
        document.getElementById('modalStartPreparing')?.addEventListener('click', () => this.startPreparing());
        document.getElementById('modalMarkReady')?.addEventListener('click', () => this.markAsReady());
        
        // Column collapse
        document.querySelectorAll('.collapse-column').forEach(btn => {
            btn.addEventListener('click', (e) => this.toggleColumn(e.target.closest('.orders-column')));
        });
    }
    
    async loadInitialData() {
        try {
            await this.refreshOrders();
        } catch (error) {
            showToast('Ma\'lumotlarni yuklashda xatolik', 'error');
            console.error('Failed to load orders:', error);
        }
    }
    
    async refreshOrders() {
        try {
            const response = await this.api.get('/kitchen/orders', {
                station: this.currentStation
            });
            
            if (response.success) {
                this.orders = response.data;
                this.renderAllColumns();
                this.updateStats();
                this.updateLastUpdate();
            }
            
        } catch (error) {
            console.error('Failed to refresh orders:', error);
            this.setConnectionStatus('disconnected');
        }
    }
    
    setupWebSocket() {
        this.ws.connect();
        
        this.ws.on('connected', () => {
            this.setConnectionStatus('connected');
            this.ws.send({ type: 'join_room', room: 'kitchen' });
        });
        
        this.ws.on('disconnected', () => {
            this.setConnectionStatus('disconnected');
        });
        
        this.ws.on('new_order', (data) => {
            this.handleNewOrder(data);
        });
        
        this.ws.on('order_updated', (data) => {
            this.handleOrderUpdate(data);
        });
        
        this.ws.on('order_status_changed', (data) => {
            this.handleOrderStatusChange(data);
        });
    }
    
    handleNewOrder(order) {
        // Play sound
        if (this.soundEnabled) {
            if (order.urgent) {
                this.sounds.urgent?.play().catch(e => console.log('Ovoz xatosi'));
            } else {
                this.sounds.newOrder?.play().catch(e => console.log('Ovoz xatosi'));
            }
        }
        
        // Add to pending
        this.orders.pending.unshift(order);
        
        // Show notification
        showToast(`Yangi buyurtma #${order.order_number} - Stol #${order.table_number}`, 'info', 5000);
        
        // Update UI
        this.renderColumn('pending');
        this.updateStats();
        
        // Highlight new order
        setTimeout(() => {
            const card = document.querySelector(`[data-order-id="${order.id}"]`);
            card?.classList.add('new');
            setTimeout(() => card?.classList.remove('new'), 500);
        }, 100);
    }
    
    handleOrderUpdate(data) {
        const { order_id, status, items } = data;
        
        // Find and update order
        Object.keys(this.orders).forEach(statusKey => {
            const index = this.orders[statusKey].findIndex(o => o.id === order_id);
            if (index !== -1) {
                const order = this.orders[statusKey][index];
                
                if (status && status !== statusKey) {
                    // Move to new status column
                    this.orders[statusKey].splice(index, 1);
                    order.status = status;
                    if (items) order.items = items;
                    this.orders[status].unshift(order);
                } else {
                    // Update in place
                    if (items) order.items = items;
                }
                
                return;
            }
        });
        
        this.renderAllColumns();
        this.updateStats();
    }
    
    handleOrderStatusChange(data) {
        this.handleOrderUpdate(data);
    }
    
    renderAllColumns() {
        this.renderColumn('pending');
        this.renderColumn('preparing');
        this.renderColumn('ready');
        this.renderColumn('completed');
    }
    
    renderColumn(status) {
        const container = document.getElementById(`${status}Orders`);
        const countElement = document.getElementById(`${status}ColumnCount`);
        
        if (!container) return;
        
        const orders = this.orders[status] || [];
        
        if (orders.length === 0) {
            container.innerHTML = `
                <div class="empty-column">
                    <div class="empty-icon">${this.getEmptyIcon(status)}</div>
                    <p>${this.getEmptyMessage(status)}</p>
                </div>
            `;
        } else {
            container.innerHTML = '';
            orders.forEach(order => {
                const card = this.createOrderCard(order, status);
                container.appendChild(card);
            });
        }
        
        if (countElement) {
            countElement.textContent = orders.length;
        }
    }
    
    createOrderCard(order, status) {
        const card = document.createElement('div');
        card.className = `kitchen-order-card ${order.urgent ? 'urgent' : ''}`;
        card.dataset.orderId = order.id;
        card.dataset.orderType = order.order_type;
        
        const timeElapsed = this.getTimeElapsed(order.created_at);
        const timerClass = timeElapsed.minutes > 15 ? 'urgent' : '';
        
        card.innerHTML = `
            <div class="order-card-header">
                <div class="order-number-wrapper">
                    <span class="order-number">#${order.order_number}</span>
                    <span class="order-type-icon">${this.getOrderTypeIcon(order.order_type)}</span>
                </div>
                <div class="order-time">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                        <path d="M12 6v6l4 2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                    <span class="timer ${timerClass}" data-order-id="${order.id}">
                        ${formatDuration(timeElapsed)}
                    </span>
                </div>
            </div>
            
            <div class="order-card-body">
                <div class="table-info">
                    <span class="table-number">Stol #${order.table_number || 'Olib ketish'}</span>
                    <span>${order.waiter_name || 'Ofitsiant'}</span>
                </div>
                <div class="order-items-preview">
                    ${this.renderItemsPreview(order.items)}
                </div>
                ${order.notes ? `<div class="order-notes-preview">📝 ${order.notes.substring(0, 50)}</div>` : ''}
            </div>
            
            <div class="order-card-footer">
                <div class="item-count">
                    ${order.items.length} ta mahsulot
                </div>
                <div class="action-buttons">
                    ${this.getActionButtons(order, status)}
                </div>
            </div>
        `;
        
        // Add click handler
        card.addEventListener('click', (e) => {
            if (!e.target.closest('.action-btn')) {
                this.openOrderDetail(order);
            }
        });
        
        // Add action button handlers
        card.querySelectorAll('.action-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                this.handleOrderAction(order, action);
            });
        });
        
        return card;
    }
    
    renderItemsPreview(items) {
        const maxItems = 3;
        const preview = items.slice(0, maxItems).map(item => `
            <div class="order-item-preview">
                <span class="item-quantity">${item.quantity}x</span>
                <span class="item-name">${item.product_name}</span>
                ${item.notes ? `<span class="item-notes">*</span>` : ''}
            </div>
        `).join('');
        
        if (items.length > maxItems) {
            return preview + `<div class="order-item-preview more">+${items.length - maxItems} ta qo'shimcha...</div>`;
        }
        
        return preview;
    }
    
    getActionButtons(order, status) {
        switch(status) {
            case 'pending':
                return `
                    <button class="action-btn start" data-action="start">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                            <path d="M10 8l6 4-6 4V8z" fill="currentColor"/>
                        </svg>
                        Boshlash
                    </button>
                    <button class="action-btn print" data-action="print">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <path d="M6 9V3h12v6M6 21h12v-6H6v6z" stroke="currentColor" stroke-width="2"/>
                        </svg>
                    </button>
                `;
            case 'preparing':
                return `
                    <button class="action-btn ready" data-action="ready">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <path d="M20 6L9 17l-5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                        Tayyor
                    </button>
                    <button class="action-btn print" data-action="print">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <path d="M6 9V3h12v6M6 21h12v-6H6v6z" stroke="currentColor" stroke-width="2"/>
                        </svg>
                    </button>
                `;
            case 'ready':
                return `
                    <button class="action-btn print" data-action="print">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <path d="M6 9V3h12v6M6 21h12v-6H6v6z" stroke="currentColor" stroke-width="2"/>
                        </svg>
                        Chop etish
                    </button>
                `;
            default:
                return '';
        }
    }
    
    async handleOrderAction(order, action) {
        try {
            switch(action) {
                case 'start':
                    await this.api.patch(`/kitchen/orders/${order.id}/start`);
                    showToast(`#${order.order_number} tayyorlash boshlandi`, 'info');
                    break;
                case 'ready':
                    await this.api.patch(`/kitchen/orders/${order.id}/ready`);
                    showToast(`#${order.order_number} tayyor`, 'success');
                    break;
                case 'print':
                    await this.printOrder(order);
                    break;
            }
            
            await this.refreshOrders();
            
        } catch (error) {
            showToast('Amalni bajarishda xatolik', 'error');
        }
    }
    
    async openOrderDetail(order) {
        this.currentOrder = order;
        
        // Populate modal
        document.getElementById('modalOrderNumber').textContent = order.order_number;
        document.getElementById('modalOrderType').textContent = this.getOrderTypeText(order.order_type);
        document.getElementById('modalOrderTime').textContent = formatTime(order.created_at);
        document.getElementById('modalTableNumber').textContent = order.table_number ? `#${order.table_number}` : '-';
        document.getElementById('modalWaiter').textContent = order.waiter_name || '-';
        document.getElementById('modalCustomer').textContent = order.customer_name || '-';
        
        // Render items
        const itemsContainer = document.getElementById('modalOrderItems');
        itemsContainer.innerHTML = order.items.map(item => `
            <div class="order-item-detail">
                <input type="checkbox" class="item-status-checkbox" 
                       data-item-id="${item.id}" 
                       ${item.status === 'ready' ? 'checked' : ''}>
                <div class="item-details">
                    <div class="item-name">${item.product_name}</div>
                    <div class="item-meta">
                        <span>${item.quantity}x</span>
                        ${item.notes ? `<span class="item-notes">📝 ${item.notes}</span>` : ''}
                    </div>
                </div>
            </div>
        `).join('');
        
        // Notes
        const notesContainer = document.getElementById('modalOrderNotes');
        if (order.notes) {
            notesContainer.innerHTML = `<strong>Izoh:</strong> ${order.notes}`;
            notesContainer.style.display = 'block';
        } else {
            notesContainer.style.display = 'none';
        }
        
        // Update action buttons visibility
        this.updateModalActions(order.status);
        
        this.modals.orderDetail.open();
    }
    
    updateModalActions(status) {
        const startBtn = document.getElementById('modalStartPreparing');
        const readyBtn = document.getElementById('modalMarkReady');
        
        if (status === 'pending') {
            startBtn.style.display = 'flex';
            readyBtn.style.display = 'none';
        } else if (status === 'preparing') {
            startBtn.style.display = 'none';
            readyBtn.style.display = 'flex';
        } else {
            startBtn.style.display = 'none';
            readyBtn.style.display = 'none';
        }
    }
    
    async startPreparing() {
        if (!this.currentOrder) return;
        await this.handleOrderAction(this.currentOrder, 'start');
        this.modals.orderDetail.close();
    }
    
    async markAsReady() {
        if (!this.currentOrder) return;
        
        // Belgilangan itemlarni tekshirish
        const checkedItems = document.querySelectorAll('.item-status-checkbox:checked');
        if (checkedItems.length === 0) {
            showToast('Kamida bitta mahsulotni tayyor deb belgilang', 'warning');
            return;
        }
        
        await this.handleOrderAction(this.currentOrder, 'ready');
        this.modals.orderDetail.close();
    }
    
    async printOrder(order) {
        try {
            await this.api.post('/printer/kitchen-order', {
                order_id: order.id
            });
            showToast('Chop etish boshlandi', 'info');
        } catch (error) {
            showToast('Chop etishda xatolik', 'error');
        }
    }
    
    async printSummary() {
        try {
            await this.api.post('/printer/kitchen-summary', {
                date: new Date().toISOString().split('T')[0],
                station: this.currentStation
            });
            showToast('Hisobot chop etilmoqda', 'info');
        } catch (error) {
            showToast('Hisobotni chop etishda xatolik', 'error');
        }
    }
    
    setFilter(filter) {
        this.state.set('orderFilter', filter);
        
        // Update UI
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === filter);
        });
        
        this.applyFilter();
    }
    
    applyFilter() {
        const filter = this.state.get('orderFilter') || 'all';
        
        document.querySelectorAll('.kitchen-order-card').forEach(card => {
            const orderType = card.dataset.orderType;
            if (filter === 'all' || orderType === filter) {
                card.style.display = '';
            } else {
                card.style.display = 'none';
            }
        });
    }
    
    updateStats() {
        document.getElementById('pendingCount').textContent = this.orders.pending.length;
        document.getElementById('preparingCount').textContent = this.orders.preparing.length;
        document.getElementById('readyCount').textContent = this.orders.ready.length;
    }
    
    startAutoRefresh() {
        this.autoRefreshInterval = setInterval(() => {
            this.refreshOrders();
            this.updateTimers();
        }, 30000);
    }
    
    startTimer() {
        this.timerInterval = setInterval(() => {
            this.updateCurrentTime();
            this.updateTimers();
        }, 1000);
    }
    
    updateCurrentTime() {
        const timeElement = document.getElementById('currentTime');
        if (timeElement) {
            const now = new Date();
            timeElement.textContent = now.toLocaleTimeString('uz-UZ');
        }
    }
    
    updateTimers() {
        document.querySelectorAll('.timer').forEach(timer => {
            const orderId = timer.dataset.orderId;
            const order = this.findOrderById(orderId);
            
            if (order) {
                const elapsed = this.getTimeElapsed(order.created_at);
                timer.textContent = formatDuration(elapsed);
                
                if (elapsed.minutes > 15) {
                    timer.classList.add('urgent');
                }
            }
        });
    }
    
    findOrderById(orderId) {
        for (const status of ['pending', 'preparing', 'ready', 'completed']) {
            const order = this.orders[status].find(o => o.id == orderId);
            if (order) return order;
        }
        return null;
    }
    
    getTimeElapsed(createdAt) {
        const created = new Date(createdAt);
        const now = new Date();
        const diff = now - created;
        
        return {
            minutes: Math.floor(diff / 60000),
            seconds: Math.floor((diff % 60000) / 1000)
        };
    }
    
    setConnectionStatus(status) {
        const dot = document.querySelector('.status-dot');
        const text = document.getElementById('connectionText');
        
        if (dot && text) {
            dot.className = `status-dot ${status}`;
            text.textContent = status === 'connected' ? 'Ulangan' : 
                              status === 'connecting' ? 'Ulanmoqda...' : 'Aloqa uzilgan';
        }
    }
    
    updateLastUpdate() {
        const element = document.getElementById('lastUpdate');
        if (element) {
            element.textContent = 'hozir';
        }
    }
    
    toggleSound() {
        this.soundEnabled = !this.soundEnabled;
        
        const soundOn = document.querySelector('.sound-on');
        const soundOff = document.querySelector('.sound-off');
        
        if (soundOn && soundOff) {
            soundOn.style.display = this.soundEnabled ? 'block' : 'none';
            soundOff.style.display = this.soundEnabled ? 'none' : 'block';
        }
        
        localStorage.setItem('kitchenSound', this.soundEnabled);
    }
    
    loadSoundPreference() {
        const saved = localStorage.getItem('kitchenSound');
        if (saved !== null) {
            this.soundEnabled = saved === 'true';
            this.toggleSound(); // UI ni yangilash
            this.toggleSound(); // Qaytarish
        }
    }
    
    toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    }
    
    toggleColumn(column) {
        column?.classList.toggle('collapsed');
    }
    
    async openHistoryModal() {
        this.modals.history.open();
        
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('historyDateFrom').value = today;
        document.getElementById('historyDateTo').value = today;
        
        await this.loadHistory();
    }
    
    async loadHistory() {
        try {
            const from = document.getElementById('historyDateFrom').value;
            const to = document.getElementById('historyDateTo').value;
            const station = document.getElementById('historyStation').value;
            
            const response = await this.api.get('/kitchen/history', {
                date_from: from,
                date_to: to,
                station: station || undefined
            });
            
            this.renderHistoryTable(response.data.items || []);
            
        } catch (error) {
            showToast('Tarixni yuklashda xatolik', 'error');
        }
    }
    
    renderHistoryTable(orders) {
        const tbody = document.getElementById('historyTableBody');
        
        if (orders.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 2rem;">
                        Ma'lumot topilmadi
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = orders.map(order => `
            <tr>
                <td><strong>#${order.order_number}</strong></td>
                <td>${order.table_number ? 'Stol #' + order.table_number : '-'}</td>
                <td>${this.getOrderTypeText(order.order_type)}</td>
                <td>${order.station || '-'}</td>
                <td>${formatTime(order.created_at)}</td>
                <td>${order.preparation_time || '-'} daqiqa</td>
                <td>
                    <span class="status-badge ${order.status}">
                        ${this.getStatusText(order.status)}
                    </span>
                </td>
            </tr>
        `).join('');
    }
    
    getOrderTypeIcon(type) {
        const icons = {
            'dine-in': '🍽️',
            'takeaway': '🥡',
            'delivery': '🚚'
        };
        return icons[type] || '📋';
    }
    
    getOrderTypeText(type) {
        const texts = {
            'dine-in': 'Shu yerda',
            'takeaway': 'Olib ketish',
            'delivery': 'Yetkazish'
        };
        return texts[type] || type;
    }
    
    getStatusText(status) {
        const texts = {
            'pending': 'Kutilmoqda',
            'preparing': 'Tayyorlanmoqda',
            'ready': 'Tayyor',
            'completed': 'Yakunlangan',
            'cancelled': 'Bekor qilingan'
        };
        return texts[status] || status;
    }
    
    getEmptyIcon(status) {
        const icons = {
            'pending': '📋',
            'preparing': '👨‍🍳',
            'ready': '✅',
            'completed': '📦'
        };
        return icons[status] || '📭';
    }
    
    getEmptyMessage(status) {
        const messages = {
            'pending': 'Kutilayotgan buyurtmalar yo\'q',
            'preparing': 'Tayyorlanayotgan buyurtmalar yo\'q',
            'ready': 'Tayyor buyurtmalar yo\'q',
            'completed': 'Yakunlangan buyurtmalar yo\'q'
        };
        return messages[status] || 'Buyurtmalar yo\'q';
    }
    
    hideLoadingScreen() {
        const loadingScreen = document.getElementById('loadingScreen');
        if (loadingScreen) {
            loadingScreen.classList.add('hidden');
        }
    }
    
    async logout() {
        if (confirm('Tizimdan chiqishni xohlaysizmi?')) {
            clearInterval(this.autoRefreshInterval);
            clearInterval(this.timerInterval);
            this.ws.disconnect();
            
            await this.auth.logout();
            window.location.href = '../shared/login.html';
        }
    }
    
    destroy() {
        clearInterval(this.autoRefreshInterval);
        clearInterval(this.timerInterval);
        this.ws.disconnect();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.kitchen = new KitchenModule();
});

window.addEventListener('beforeunload', () => {
    if (window.kitchen) {
        window.kitchen.destroy();
    }
});

export default KitchenModule;