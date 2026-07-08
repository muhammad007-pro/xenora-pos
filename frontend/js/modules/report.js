import { API } from '../core/api.js';
import { showToast } from '../ui/toast.js';
import { formatMoney, formatDate, formatDateTime } from '../utils/formatter.js';

class ReportModule {
    constructor() {
        this.api = new API();
        this.currentReport = 'daily';
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.setDefaultDates();
        this.loadReport();
    }
    
    setupEventListeners() {
        document.querySelectorAll('.report-type-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.currentReport = e.target.dataset.report;
                document.querySelectorAll('.report-type-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.loadReport();
            });
        });
        
        document.getElementById('generateReport')?.addEventListener('click', () => this.loadReport());
        document.getElementById('printReport')?.addEventListener('click', () => this.printReport());
        document.getElementById('exportReport')?.addEventListener('click', () => this.exportReport());
        document.getElementById('exportPdf')?.addEventListener('click', () => this.exportPdf());
        document.getElementById('exportExcel')?.addEventListener('click', () => this.exportExcel());
    }
    
    setDefaultDates() {
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('reportDateFrom').value = today;
        document.getElementById('reportDateTo').value = today;
    }
    
    async loadReport() {
        const dateFrom = document.getElementById('reportDateFrom')?.value;
        const dateTo = document.getElementById('reportDateTo')?.value;
        
        try {
            let response;
            
            switch(this.currentReport) {
                case 'daily':
                    response = await this.api.get('/reports/daily', { date: dateFrom });
                    this.renderDailyReport(response.data);
                    break;
                case 'sales':
                    response = await this.api.get('/reports/sales', { date_from: dateFrom, date_to: dateTo });
                    this.renderSalesReport(response.data);
                    break;
                case 'products':
                    response = await this.api.get('/reports/products', { date_from: dateFrom, date_to: dateTo });
                    this.renderProductsReport(response.data);
                    break;
                case 'staff':
                    response = await this.api.get('/reports/staff', { date_from: dateFrom, date_to: dateTo });
                    this.renderStaffReport(response.data);
                    break;
                case 'shift':
                    response = await this.api.get('/reports/shift');
                    this.renderShiftReport(response.data);
                    break;
            }
        } catch (error) {
            showToast('Hisobotni yuklashda xatolik', 'error');
        }
    }
    
    renderDailyReport(data) {
        const container = document.getElementById('reportContent');
        
        container.innerHTML = `
            <div class="report-header">
                <h2>Kunlik hisobot - ${formatDate(data.date)}</h2>
            </div>
            
            <div class="report-summary glass">
                <div class="summary-card">
                    <span class="label">Jami savdo</span>
                    <span class="value">${formatMoney(data.total_sales)}</span>
                </div>
                <div class="summary-card">
                    <span class="label">Naqd savdo</span>
                    <span class="value">${formatMoney(data.cash_sales)}</span>
                </div>
                <div class="summary-card">
                    <span class="label">Karta savdo</span>
                    <span class="value">${formatMoney(data.card_sales)}</span>
                </div>
                <div class="summary-card">
                    <span class="label">Buyurtmalar</span>
                    <span class="value">${data.orders_count}</span>
                </div>
                <div class="summary-card">
                    <span class="label">O'rtacha chek</span>
                    <span class="value">${formatMoney(data.avg_check)}</span>
                </div>
            </div>
            
            <div class="report-section glass">
                <h3>Ommabop mahsulotlar</h3>
                <div class="popular-items">
                    ${data.popular_items?.map(item => `
                        <div class="popular-item">
                            <span class="name">${item.name}</span>
                            <span class="quantity">${item.quantity} ta</span>
                        </div>
                    `).join('') || '<p>Ma\'lumot yo\'q</p>'}
                </div>
            </div>
            
            <div class="report-section glass">
                <h3>Buyurtmalar</h3>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Stol</th>
                            <th>Ofitsiant</th>
                            <th>Summa</th>
                            <th>To'lov</th>
                            <th>Holat</th>
                            <th>Vaqt</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.orders?.map(order => `
                            <tr>
                                <td>#${order.order_number}</td>
                                <td>${order.table_number || '-'}</td>
                                <td>${order.waiter_name || '-'}</td>
                                <td>${formatMoney(order.final_amount)}</td>
                                <td>${this.getPaymentMethod(order.payment_method)}</td>
                                <td><span class="status-badge ${order.status}">${this.getStatusText(order.status)}</span></td>
                                <td>${formatDateTime(order.created_at)}</td>
                            </tr>
                        `).join('') || '<tr><td colspan="7">Buyurtmalar yo\'q</td></tr>'}
                    </tbody>
                </table>
            </div>
        `;
    }
    
    renderSalesReport(data) {
        const container = document.getElementById('reportContent');
        
        container.innerHTML = `
            <div class="report-header">
                <h2>Savdo hisoboti</h2>
                <p>${formatDate(data.date_from)} - ${formatDate(data.date_to)}</p>
            </div>
            
            <div class="report-summary glass">
                <div class="summary-card">
                    <span class="label">Jami savdo</span>
                    <span class="value">${formatMoney(data.total_sales)}</span>
                </div>
            </div>
            
            <div class="report-section glass">
                <h3>Kunlik savdo</h3>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Sana</th>
                            <th>Summa</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.daily_sales?.map(day => `
                            <tr>
                                <td>${formatDate(day.date)}</td>
                                <td>${formatMoney(day.total)}</td>
                            </tr>
                        `).join('') || '<tr><td colspan="2">Ma\'lumot yo\'q</td></tr>'}
                    </tbody>
                </table>
            </div>
            
            <div class="report-section glass">
                <h3>To'lov usullari</h3>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Usul</th>
                            <th>Soni</th>
                            <th>Summa</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.payment_methods?.map(p => `
                            <tr>
                                <td>${this.getPaymentMethod(p.method)}</td>
                                <td>${p.count}</td>
                                <td>${formatMoney(p.total)}</td>
                            </tr>
                        `).join('') || '<tr><td colspan="3">Ma\'lumot yo\'q</td></tr>'}
                    </tbody>
                </table>
            </div>
        `;
    }
    
    renderProductsReport(data) {
        const container = document.getElementById('reportContent');
        
        container.innerHTML = `
            <div class="report-header">
                <h2>Mahsulotlar hisoboti</h2>
                <p>${formatDate(data.date_from)} - ${formatDate(data.date_to)}</p>
            </div>
            
            <div class="report-section glass">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Mahsulot</th>
                            <th>Kategoriya</th>
                            <th>Soni</th>
                            <th>Daromad</th>
                            <th>Buyurtmalar</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.products?.map(p => `
                            <tr>
                                <td>${p.name}</td>
                                <td>${p.category || '-'}</td>
                                <td>${p.quantity}</td>
                                <td>${formatMoney(p.revenue)}</td>
                                <td>${p.orders_count}</td>
                            </tr>
                        `).join('') || '<tr><td colspan="5">Ma\'lumot yo\'q</td></tr>'}
                    </tbody>
                </table>
            </div>
        `;
    }
    
    renderStaffReport(data) {
        const container = document.getElementById('reportContent');
        
        container.innerHTML = `
            <div class="report-header">
                <h2>Xodimlar hisoboti</h2>
                <p>${formatDate(data.date_from)} - ${formatDate(data.date_to)}</p>
            </div>
            
            <div class="report-section glass">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Xodim</th>
                            <th>Buyurtmalar</th>
                            <th>Jami savdo</th>
                            <th>O'rtacha chek</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.staff?.map(s => `
                            <tr>
                                <td>${s.name}</td>
                                <td>${s.orders_count}</td>
                                <td>${formatMoney(s.total_sales)}</td>
                                <td>${formatMoney(s.avg_check)}</td>
                            </tr>
                        `).join('') || '<tr><td colspan="4">Ma\'lumot yo\'q</td></tr>'}
                    </tbody>
                </table>
            </div>
        `;
    }
    
    renderShiftReport(data) {
        const container = document.getElementById('reportContent');
        
        container.innerHTML = `
            <div class="report-header">
                <h2>Smena hisoboti</h2>
            </div>
            
            ${data.shifts?.map(shift => `
                <div class="report-section glass">
                    <h3>${shift.user_name} - ${formatDate(shift.start_time)}</h3>
                    <div class="shift-details">
                        <div class="detail-row">
                            <span>Smena vaqti:</span>
                            <span>${new Date(shift.start_time).toLocaleTimeString()} - ${shift.end_time ? new Date(shift.end_time).toLocaleTimeString() : 'Faol'}</span>
                        </div>
                        <div class="detail-row">
                            <span>Boshlang'ich kassa:</span>
                            <span>${formatMoney(shift.starting_cash)}</span>
                        </div>
                        <div class="detail-row">
                            <span>Yakuniy kassa:</span>
                            <span>${shift.ending_cash ? formatMoney(shift.ending_cash) : '-'}</span>
                        </div>
                        <div class="detail-row">
                            <span>Jami savdo:</span>
                            <span>${formatMoney(shift.total_sales)}</span>
                        </div>
                        <div class="detail-row">
                            <span>Naqd savdo:</span>
                            <span>${formatMoney(shift.cash_sales)}</span>
                        </div>
                        <div class="detail-row">
                            <span>Karta savdo:</span>
                            <span>${formatMoney(shift.card_sales)}</span>
                        </div>
                        <div class="detail-row">
                            <span>Buyurtmalar:</span>
                            <span>${shift.orders_count}</span>
                        </div>
                    </div>
                </div>
            `).join('') || '<p>Ma\'lumot yo\'q</p>'}
        `;
    }
    
    getPaymentMethod(method) {
        const methods = { cash: 'Naqd', card: 'Karta', click: 'Click', payme: 'Payme' };
        return methods[method] || method || '-';
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
    
    async printReport() {
        try {
            await this.api.post('/printer/report', { report_type: this.currentReport });
            showToast('Hisobot chop etilmoqda', 'success');
        } catch (error) {
            showToast('Chop etishda xatolik', 'error');
        }
    }
    
    async exportReport() {
        await this.downloadReport('csv');
    }
    
    async exportExcel() {
        await this.downloadReport('excel');
    }
    
    async exportPdf() {
        await this.downloadReport('pdf');
    }
    
    async downloadReport(format) {
        try {
            const dateFrom = document.getElementById('reportDateFrom')?.value;
            const dateTo = document.getElementById('reportDateTo')?.value;
            
            const response = await this.api.get('/reports/export', {
                report_type: this.currentReport,
                date_from: dateFrom,
                date_to: dateTo,
                format: format
            });
            
            if (response.data?.file_url) {
                window.open(response.data.file_url, '_blank');
                showToast('Hisobot yuklandi', 'success');
            }
        } catch (error) {
            showToast('Eksport qilishda xatolik', 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => new ReportModule());