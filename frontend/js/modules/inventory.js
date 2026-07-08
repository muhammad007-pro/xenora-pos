import { API } from '../core/api.js';
import { Modal } from '../ui/modal.js';
import { showToast } from '../ui/toast.js';
import { formatMoney, formatNumber } from '../utils/formatter.js';
import { debounce } from '../utils/helpers.js';

class InventoryModule {
    constructor() {
        this.api = new API();
        this.items = [];
        this.categories = [];
        this.currentItem = null;
        this.modal = new Modal('inventoryModal');
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadCategories();
        await this.loadInventory();
        this.renderInventory();
        this.checkLowStock();
    }
    
    setupEventListeners() {
        document.getElementById('addStockBtn')?.addEventListener('click', () => this.openAddStockModal());
        document.getElementById('saveStockBtn')?.addEventListener('click', () => this.saveStock());
        document.getElementById('inventorySearch')?.addEventListener('input', debounce((e) => this.searchInventory(e.target.value), 300));
        document.getElementById('categoryFilter')?.addEventListener('change', () => this.filterInventory());
        document.getElementById('lowStockOnly')?.addEventListener('change', () => this.filterInventory());
        document.getElementById('exportInventory')?.addEventListener('click', () => this.exportInventory());
    }
    
    async loadCategories() {
        const response = await this.api.get('/categories/all');
        this.categories = response.data || [];
        
        const select = document.getElementById('categoryFilter');
        if (select) {
            select.innerHTML = '<option value="">Barcha kategoriyalar</option>' +
                this.categories.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
        }
    }
    
    async loadInventory() {
        const response = await this.api.get('/inventory');
        this.items = response.data?.items || [];
    }
    
    renderInventory(items = null) {
        const tbody = document.getElementById('inventoryTableBody');
        const displayItems = items || this.items;
        
        if (displayItems.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center">Ombor bo\'sh</td></tr>';
            return;
        }
        
        tbody.innerHTML = displayItems.map(item => {
            const status = this.getStockStatus(item);
            const product = item.product || {};
            
            return `
                <tr class="${status.class}">
                    <td>${product.id || '-'}</td>
                    <td>
                        <div class="product-info">
                            <span class="product-name">${product.name || '-'}</span>
                            <small>${item.product?.category?.name || '-'}</small>
                        </div>
                    </td>
                    <td class="quantity ${status.class}">
                        ${formatNumber(item.quantity)} ${item.unit}
                    </td>
                    <td>${formatNumber(item.min_threshold)} ${item.unit}</td>
                    <td>${formatNumber(item.max_threshold)} ${item.unit}</td>
                    <td>
                        <span class="stock-status ${status.class}">${status.text}</span>
                    </td>
                    <td>${item.last_restock ? new Date(item.last_restock).toLocaleDateString() : '-'}</td>
                    <td>
                        <div class="actions">
                            <button class="btn-icon add-stock" data-id="${item.id}" title="Qo'shish">➕</button>
                            <button class="btn-icon remove-stock" data-id="${item.id}" title="Olib tashlash">➖</button>
                            <button class="btn-icon edit-item" data-id="${item.id}" title="Sozlash">⚙️</button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
        
        tbody.querySelectorAll('.add-stock').forEach(btn => {
            btn.addEventListener('click', () => this.openAddStockModal(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.remove-stock').forEach(btn => {
            btn.addEventListener('click', () => this.openRemoveStockModal(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.edit-item').forEach(btn => {
            btn.addEventListener('click', () => this.openEditModal(btn.dataset.id));
        });
        
        this.updateStats();
    }
    
    getStockStatus(item) {
        if (item.quantity <= 0) {
            return { class: 'out-of-stock', text: 'Tugagan' };
        } else if (item.quantity <= item.min_threshold) {
            return { class: 'low-stock', text: 'Kam qolgan' };
        } else if (item.quantity >= item.max_threshold) {
            return { class: 'over-stock', text: 'Ko\'p' };
        }
        return { class: 'normal', text: 'Normal' };
    }
    
    updateStats() {
        const totalItems = this.items.length;
        const lowStockItems = this.items.filter(i => i.quantity <= i.min_threshold).length;
        const outOfStockItems = this.items.filter(i => i.quantity <= 0).length;
        
        const totalValue = this.items.reduce((sum, i) => {
            return sum + (i.quantity * (i.product?.cost_price || 0));
        }, 0);
        
        document.getElementById('totalItems').textContent = totalItems;
        document.getElementById('lowStockCount').textContent = lowStockItems;
        document.getElementById('outOfStockCount').textContent = outOfStockItems;
        document.getElementById('totalInventoryValue').textContent = formatMoney(totalValue);
    }
    
    async checkLowStock() {
        const lowStock = this.items.filter(i => i.quantity <= i.min_threshold);
        if (lowStock.length > 0) {
            showToast(`${lowStock.length} ta mahsulot kam qolgan`, 'warning', 5000);
        }
    }
    
    filterInventory() {
        const searchTerm = document.getElementById('inventorySearch')?.value.toLowerCase() || '';
        const categoryId = document.getElementById('categoryFilter')?.value;
        const lowStockOnly = document.getElementById('lowStockOnly')?.checked;
        
        let filtered = this.items;
        
        if (searchTerm) {
            filtered = filtered.filter(i => 
                i.product?.name?.toLowerCase().includes(searchTerm)
            );
        }
        
        if (categoryId) {
            filtered = filtered.filter(i => i.product?.category_id == categoryId);
        }
        
        if (lowStockOnly) {
            filtered = filtered.filter(i => i.quantity <= i.min_threshold);
        }
        
        this.renderInventory(filtered);
    }
    
    searchInventory(query) {
        this.filterInventory();
    }
    
    openAddStockModal(itemId = null) {
        if (itemId) {
            const item = this.items.find(i => i.id == itemId);
            if (item) this.currentItem = item;
        }
        
        document.getElementById('stockModalTitle').textContent = 'Omborga qo\'shish';
        document.getElementById('stockAction').value = 'add';
        this.modal.open();
    }
    
    openRemoveStockModal(itemId) {
        const item = this.items.find(i => i.id == itemId);
        if (item) this.currentItem = item;
        
        document.getElementById('stockModalTitle').textContent = 'Omborni kamaytirish';
        document.getElementById('stockAction').value = 'remove';
        this.modal.open();
    }
    
    async saveStock() {
        const action = document.getElementById('stockAction').value;
        const quantity = parseFloat(document.getElementById('stockQuantity').value);
        const reason = document.getElementById('stockReason').value;
        
        if (!quantity || quantity <= 0) {
            showToast('Miqdorni to\'g\'ri kiriting', 'warning');
            return;
        }
        
        try {
            if (action === 'add') {
                await this.api.post(`/inventory/${this.currentItem.id}/add-stock`, { quantity, notes: reason });
                showToast('Mahsulot qo\'shildi', 'success');
            } else {
                await this.api.post(`/inventory/${this.currentItem.id}/remove-stock`, { quantity, reason });
                showToast('Mahsulot chiqarildi', 'success');
            }
            
            await this.loadInventory();
            this.renderInventory();
            this.modal.close();
        } catch (error) {
            showToast(error.message || 'Xatolik yuz berdi', 'error');
        }
    }
    
    async exportInventory() {
        try {
            const response = await this.api.get('/inventory/export', { format: 'csv' });
            if (response.data?.file_url) {
                window.open(response.data.file_url, '_blank');
                showToast('Eksport tayyorlandi', 'success');
            }
        } catch (error) {
            showToast('Eksport qilishda xatolik', 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => new InventoryModule());