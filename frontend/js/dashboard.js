import { API } from './core/api.js';
import { AuthService } from './core/auth.js';
import { formatMoney, formatNumber } from './utils/formatter.js';

class DashboardModule {
    constructor() {
        this.api = new API();
        this.auth = new AuthService();
        this.charts = {};
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadData();
        this.updateUserInfo();
    }
    
    setupEventListeners() {
        document.querySelectorAll('.date-range-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.date-range-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.loadData(e.target.dataset.range);
            });
        });
        
        document.getElementById('refreshDashboard')?.addEventListener('click', () => this.loadData());
    }
    
    async loadData(range = 'today') {
        try {
            const response = await this.api.get('/analytics/dashboard', { range });
            const data = response.data;
            
            this.updateStats(data);
            this.renderCharts(data);
            this.renderRecentOrders(data.recent_orders);
            this.renderPopularProducts(data.popular_products);
        } catch (error) {
            console.error('Dashboard yuklashda xatolik:', error);
        }
    }
    
    updateStats(data) {
        document.getElementById('totalRevenue').textContent = formatMoney(data.total_revenue);
        document.getElementById('totalOrders').textContent = formatNumber(data.total_orders);
        document.getElementById('totalCustomers').textContent = formatNumber(data.total_customers);
        document.getElementById('averageCheck').textContent = formatMoney(data.average_check);
        
        this.updateTrend('revenueTrend', data.revenue_trend);
        this.updateTrend('ordersTrend', data.orders_trend);
        this.updateTrend('customersTrend', data.customers_trend);
    }
    
    updateTrend(elementId, trend) {
        const element = document.getElementById(elementId);
        if (element) {
            const isPositive = trend >= 0;
            element.textContent = `${isPositive ? '+' : ''}${trend}%`;
            element.className = `stat-trend ${isPositive ? 'up' : 'down'}`;
        }
    }
    
    renderCharts(data) {
        this.renderRevenueChart(data.revenue_data);
        this.renderCategoriesChart(data.categories_data);
        this.renderPaymentMethodsChart(data.payment_methods);
    }
    
    renderRevenueChart(revenueData) {
        const ctx = document.getElementById('revenueChart')?.getContext('2d');
        if (!ctx) return;
        
        if (this.charts.revenue) {
            this.charts.revenue.destroy();
        }
        
        this.charts.revenue = new Chart(ctx, {
            type: 'line',
            data: {
                labels: revenueData.labels || [],
                datasets: [{
                    label: 'Daromad',
                    data: revenueData.values || [],
                    borderColor: '#c9a84c',
                    backgroundColor: 'rgba(201, 168, 76, 0.1)',
                    borderWidth: 3,
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => formatMoney(ctx.raw)
                        }
                    }
                }
            }
        });
    }
    
    renderCategoriesChart(data) {
        const ctx = document.getElementById('categoriesChart')?.getContext('2d');
        if (!ctx) return;
        
        if (this.charts.categories) {
            this.charts.categories.destroy();
        }
        
        this.charts.categories = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.map(c => c.name),
                datasets: [{
                    data: data.map(c => c.revenue),
                    backgroundColor: ['#c9a84c', '#e2c97a', '#9e822e', '#d4af37', '#f4d03f', '#b8960c']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        });
    }
    
    renderPaymentMethodsChart(data) {
        const ctx = document.getElementById('paymentMethodsChart')?.getContext('2d');
        if (!ctx) return;
        
        if (this.charts.paymentMethods) {
            this.charts.paymentMethods.destroy();
        }
        
        const labels = { cash: 'Naqd', card: 'Karta', click: 'Click', payme: 'Payme' };
        
        this.charts.paymentMethods = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: data.map(p => labels[p.method] || p.method),
                datasets: [{
                    data: data.map(p => p.total),
                    backgroundColor: ['#10b981', '#3b82f6', '#06b6d4', '#6366f1']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        });
    }
    
    renderRecentOrders(orders) {
        const tbody = document.getElementById('recentOrdersTable');
        if (!tbody) return;
        
        if (!orders || orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center">Buyurtmalar yo\'q</td></tr>';
            return;
        }
        
        tbody.innerHTML = orders.slice(0, 10).map(order => `
            <tr>
                <td>#${order.order_number}</td>
                <td>${order.table_number || '-'}</td>
                <td>${formatMoney(order.final_amount)}</td>
                <td><span class="status-badge ${order.status}">${this.getStatusText(order.status)}</span></td>
                <td>${new Date(order.created_at).toLocaleTimeString()}</td>
            </tr>
        `).join('');
    }
    
    renderPopularProducts(products) {
        const container = document.getElementById('popularProductsList');
        if (!container) return;
        
        if (!products || products.length === 0) {
            container.innerHTML = '<div class="empty-state">Ma\'lumot yo\'q</div>';
            return;
        }
        
        container.innerHTML = products.slice(0, 5).map((p, i) => `
            <div class="popular-item">
                <span class="rank">#${i + 1}</span>
                <span class="name">${p.name}</span>
                <span class="quantity">${p.quantity} ta</span>
                <span class="revenue">${formatMoney(p.revenue)}</span>
            </div>
        `).join('');
    }
    
    getStatusText(status) {
        const texts = {
            pending: 'Kutilmoqda',
            preparing: 'Tayyorlanmoqda',
            ready: 'Tayyor',
            completed: 'Yakunlangan',
            cancelled: 'Bekor qilingan'
        };
        return texts[status] || status;
    }
    
    updateUserInfo() {
        const user = this.auth.getCurrentUser();
        if (user) {
            document.getElementById('userName').textContent = user.full_name;
            document.getElementById('userRole').textContent = user.role?.name || 'Foydalanuvchi';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => new DashboardModule());