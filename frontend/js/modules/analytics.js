import { API } from '../core/api.js';
import { AuthService } from '../core/auth.js';
import { formatMoney, formatNumber, formatPercent } from '../utils/formatter.js';
import { showToast } from '../ui/toast.js';

class AnalyticsModule {
    constructor() {
        this.api = new API();
        this.auth = new AuthService();
        this.charts = {};
        this.currentRange = 'today';
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadData();
        this.updateDateDisplay();
    }
    
    setupEventListeners() {
        document.querySelectorAll('.date-range-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.currentRange = e.target.dataset.range;
                document.querySelectorAll('.date-range-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.loadData();
            });
        });
        
        document.getElementById('exportAnalytics')?.addEventListener('click', () => this.exportData());
        document.getElementById('refreshAnalytics')?.addEventListener('click', () => this.loadData());
        document.getElementById('dateFrom')?.addEventListener('change', () => this.loadData());
        document.getElementById('dateTo')?.addEventListener('change', () => this.loadData());
    }
    
    async loadData() {
        try {
            const dateFrom = document.getElementById('dateFrom')?.value;
            const dateTo = document.getElementById('dateTo')?.value;
            
            const params = { range: this.currentRange };
            if (dateFrom) params.date_from = dateFrom;
            if (dateTo) params.date_to = dateTo;
            
            const response = await this.api.get('/analytics/dashboard', params);
            const data = response.data;
            
            this.updateStats(data);
            this.renderCharts(data);
            this.renderTopProducts(data.popular_products);
            this.renderRecentOrders(data.recent_orders);
            this.renderSalesByHour(data.hourly_sales);
        } catch (error) {
            showToast('Ma\'lumotlarni yuklashda xatolik', 'error');
        }
    }
    
    updateStats(data) {
        document.getElementById('totalRevenue').textContent = formatMoney(data.total_revenue);
        document.getElementById('totalOrders').textContent = formatNumber(data.total_orders);
        document.getElementById('totalCustomers').textContent = formatNumber(data.total_customers);
        document.getElementById('averageCheck').textContent = formatMoney(data.average_check);
        document.getElementById('completionRate').textContent = formatPercent(data.completion_rate || 0);
        
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
                labels: revenueData?.labels || [],
                datasets: [{
                    label: 'Daromad',
                    data: revenueData?.values || [],
                    borderColor: '#c9a84c',
                    backgroundColor: 'rgba(201, 168, 76, 0.1)',
                    borderWidth: 3,
                    tension: 0.4,
                    fill: true,
                    pointBackgroundColor: '#c9a84c',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 6
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
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value) => formatMoney(value)
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
                labels: data?.map(c => c.name) || [],
                datasets: [{
                    data: data?.map(c => c.revenue) || [],
                    backgroundColor: ['#c9a84c', '#e2c97a', '#9e822e', '#d4af37', '#f4d03f', '#b8960c'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right' },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                const percent = ((ctx.raw / total) * 100).toFixed(1);
                                return `${ctx.label}: ${formatMoney(ctx.raw)} (${percent}%)`;
                            }
                        }
                    }
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
                labels: data?.map(p => labels[p.method] || p.method) || [],
                datasets: [{
                    data: data?.map(p => p.total) || [],
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
    
    renderTopProducts(products) {
        const container = document.getElementById('topProductsList');
        if (!container) return;
        
        if (!products || products.length === 0) {
            container.innerHTML = '<div class="empty-state">Ma\'lumot yo\'q</div>';
            return;
        }
        
        container.innerHTML = products.slice(0, 10).map((p, i) => `
            <div class="product-rank-item">
                <span class="rank">#${i + 1}</span>
                <div class="product-info">
                    <span class="product-name">${p.name}</span>
                    <span class="product-meta">${p.quantity} ta • ${formatMoney(p.revenue)}</span>
                </div>
            </div>
        `).join('');
    }
    
    renderRecentOrders(orders) {
        const tbody = document.getElementById('recentOrdersTable');
        if (!tbody) return;
        
        if (!orders || orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center">Buyurtmalar yo\'q</td></tr>';
            return;
        }
        
        tbody.innerHTML = orders.map(order => `
            <tr>
                <td><strong>#${order.order_number}</strong></td>
                <td>${order.table_number || '-'}</td>
                <td>${order.waiter_name || '-'}</td>
                <td>${formatMoney(order.final_amount)}</td>
                <td><span class="status-badge ${order.status}">${this.getStatusText(order.status)}</span></td>
                <td>${new Date(order.created_at).toLocaleTimeString()}</td>
            </tr>
        `).join('');
    }
    
    renderSalesByHour(hourlyData) {
        const container = document.getElementById('hourlySalesChart');
        if (!container) return;
        
        // Soatlik savdo grafigi
        const ctx = container.getContext('2d');
        
        if (this.charts.hourly) {
            this.charts.hourly.destroy();
        }
        
        const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`);
        const data = hourlyData || Array(24).fill(0);
        
        this.charts.hourly = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: hours,
                datasets: [{
                    label: 'Savdo',
                    data: data,
                    backgroundColor: 'rgba(201, 168, 76, 0.7)',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value) => formatMoney(value)
                        }
                    }
                }
            }
        });
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
    
    updateDateDisplay() {
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('dateFrom').value = today;
        document.getElementById('dateTo').value = today;
    }
    
    async exportData() {
        try {
            const format = document.getElementById('exportFormat')?.value || 'csv';
            const response = await this.api.get('/analytics/export', {
                report_type: 'sales',
                format: format
            });
            
            if (response.data?.file_url) {
                window.open(response.data.file_url, '_blank');
                showToast('Eksport tayyorlandi', 'success');
            }
        } catch (error) {
            showToast('Eksport qilishda xatolik', 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => new AnalyticsModule());