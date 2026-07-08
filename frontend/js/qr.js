import { API } from './core/api.js';
import { showToast } from './ui/toast.js';

class QRModule {
    constructor() {
        this.api = new API();
        this.tables = [];
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadTables();
        this.renderTablesQR();
    }
    
    setupEventListeners() {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchTab(btn.dataset.tab));
        });
        
        document.getElementById('downloadMenuQr')?.addEventListener('click', () => this.downloadQR('menu'));
        document.getElementById('printMenuQr')?.addEventListener('click', () => this.printQR('menu'));
        document.getElementById('generatePaymentQr')?.addEventListener('click', () => this.generatePaymentQR());
    }
    
    switchTab(tabId) {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabId);
        });
        
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `${tabId}-tab`);
        });
        
        if (tabId === 'menu') {
            this.loadMenuQR();
        }
    }
    
    async loadTables() {
        const response = await this.api.get('/tables/all');
        this.tables = response.data || [];
    }
    
    renderTablesQR() {
        const grid = document.getElementById('tablesQrGrid');
        
        grid.innerHTML = this.tables.map(table => `
            <div class="qr-card glass">
                <h3>Stol #${table.number}</h3>
                <div class="qr-code" id="qr-table-${table.id}"></div>
                <p>${table.name || ''}</p>
                <div class="qr-actions">
                    <button class="btn btn-sm btn-outline download-qr" data-type="table" data-id="${table.id}">
                        Yuklash
                    </button>
                    <button class="btn btn-sm btn-outline print-qr" data-type="table" data-id="${table.id}">
                        Chop etish
                    </button>
                </div>
            </div>
        `).join('');
        
        this.tables.forEach(table => {
            this.generateQRCode(`qr-table-${table.id}`, `table:${table.id}`);
        });
        
        grid.querySelectorAll('.download-qr').forEach(btn => {
            btn.addEventListener('click', () => this.downloadQR('table', btn.dataset.id));
        });
        
        grid.querySelectorAll('.print-qr').forEach(btn => {
            btn.addEventListener('click', () => this.printQR('table', btn.dataset.id));
        });
    }
    
    loadMenuQR() {
        this.generateQRCode('menuQrPreview', 'menu');
    }
    
    generatePaymentQR() {
        const amount = document.getElementById('paymentAmount')?.value;
        if (!amount) {
            showToast('Summa kiriting', 'warning');
            return;
        }
        this.generateQRCode('paymentQrPreview', `payment:${amount}`);
    }
    
    generateQRCode(elementId, data) {
        const element = document.getElementById(elementId);
        if (!element) return;
        
        element.innerHTML = '';
        
        // QR Code library ishlatish
        const qr = document.createElement('img');
        qr.src = `/api/v1/qr/generate?data=${encodeURIComponent(data)}`;
        qr.alt = 'QR Code';
        qr.style.width = '200px';
        qr.style.height = '200px';
        
        element.appendChild(qr);
    }
    
    downloadQR(type, id = null) {
        let url;
        if (type === 'menu') {
            url = '/api/v1/qr/menu';
        } else if (type === 'table' && id) {
            url = `/api/v1/qr/table/${id}`;
        }
        
        if (url) {
            window.open(url, '_blank');
        }
    }
    
    printQR(type, id = null) {
        // Chop etish logikasi
        showToast('Chop etish boshlandi', 'info');
    }
}

document.addEventListener('DOMContentLoaded', () => new QRModule());