import { API } from '../../core/api.js';
import { AuthService } from '../../core/auth.js';
import { StateManager } from '../../core/state.js';
import { showToast } from '../../ui/toast.js';
import { Modal } from '../../ui/modal.js';
import { formatMoney, formatDate, formatDateTime } from '../../utils/formatter.js';
import { debounce } from '../../utils/helpers.js';

class AdminModule {
    constructor() {
        this.api = new API();
        this.auth = new AuthService();
        this.state = new StateManager();
        
        this.currentSection = 'dashboard';
        this.users = [];
        this.products = [];
        this.categories = [];
        this.roles = [];
        
        this.modals = {
            user: new Modal('userModal'),
            product: new Modal('productModal')
        };
        
        this.charts = {};
        
        this.init();
    }
    
    async init() {
        this.checkAuth();
        this.setupEventListeners();
        this.setupNavigation();
        await this.loadInitialData();
        this.updateUI();
        this.hideLoadingScreen();
    }
    
    checkAuth() {
        const user = this.auth.getCurrentUser();
        if (!user || !user.is_superuser) {
            window.location.href = '../shared/login.html';
            return;
        }
    }
    
    setupEventListeners() {
        // Sidebar
        document.getElementById('sidebarCollapse')?.addEventListener('click', () => this.toggleSidebar());
        document.getElementById('mobileMenuToggle')?.addEventListener('click', () => this.toggleMobileMenu());
        
        // Theme
        document.getElementById('themeToggle')?.addEventListener('click', () => this.toggleTheme());
        
        // Refresh
        document.getElementById('refreshBtn')?.addEventListener('click', () => this.refreshCurrentSection());
        
        // Logout
        document.getElementById('logoutBtn')?.addEventListener('click', () => this.logout());
        
        // User section
        document.getElementById('addUserBtn')?.addEventListener('click', () => this.openUserModal());
        document.getElementById('saveUserBtn')?.addEventListener('click', () => this.saveUser());
        document.getElementById('userSearch')?.addEventListener('input', debounce(() => this.filterUsers(), 300));
        document.getElementById('userRoleFilter')?.addEventListener('change', () => this.filterUsers());
        document.getElementById('userStatusFilter')?.addEventListener('change', () => this.filterUsers());
        document.getElementById('selectAllUsers')?.addEventListener('change', (e) => this.selectAllUsers(e.target.checked));
        
        // Product section
        document.getElementById('addProductBtn')?.addEventListener('click', () => this.openProductModal());
        document.getElementById('saveProductBtn')?.addEventListener('click', () => this.saveProduct());
        document.getElementById('manageCategoriesBtn')?.addEventListener('click', () => this.openCategoryManager());
        document.getElementById('productSearch')?.addEventListener('input', debounce(() => this.filterProducts(), 300));
        
        // Date range
        document.querySelectorAll('.date-range-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.setDateRange(e.target.dataset.range));
        });
        
        // Password toggle for user form
        const passwordInput = document.getElementById('userPassword');
        const confirmInput = document.getElementById('confirmPassword');
        
        if (passwordInput && confirmInput) {
            confirmInput.addEventListener('input', () => this.validatePasswordMatch());
        }
    }
    
    setupNavigation() {
        document.querySelectorAll('.nav-item[data-section]').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const section = item.dataset.section;
                this.switchSection(section);
            });
        });
    }
    
    switchSection(section) {
        // Update active nav item
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.section === section);
        });
        
        // Hide all sections
        document.querySelectorAll('.content-section').forEach(s => {
            s.classList.remove('active');
        });
        
        // Show selected section
        const sectionElement = document.getElementById(`${section}-section`);
        if (sectionElement) {
            sectionElement.classList.add('active');
        }
        
        this.currentSection = section;
        
        // Update page title
        const titles = {
            'dashboard': 'Dashboard',
            'users': 'Foydalanuvchilar',
            'roles': 'Rollar va Ruxsatlar',
            'menu': 'Menyu boshqaruvi',
            'tables': 'Stollar',
            'inventory': 'Ombor',
            'analytics': 'Analitika',
            'reports': 'Hisobotlar',
            'employees': 'Xodimlar',
            'shifts': 'Smenalar',
            'settings': 'Sozlamalar',
            'printer': 'Printer sozlamalari',
            'backup': 'Zaxiralash'
        };
        
        document.getElementById('pageTitle').textContent = titles[section] || section;
        document.getElementById('breadcrumbCurrent').textContent = titles[section] || section;
        
        // Load section data
        this.loadSectionData(section);
    }
    
    async loadSectionData(section) {
        switch(section) {
            case 'dashboard':
                await this.loadDashboardData();
                break;
            case 'users':
                await this.loadUsers();
                break;
            case 'menu':
                await this.loadMenuData();
                break;
            case 'analytics':
                await this.loadAnalyticsData();
                break;
            case 'reports':
                await this.loadReportsData();
                break;
        }
    }
    
    async loadInitialData() {
        try {
            this.updateLoadingProgress(20);
            
            // Load roles
            const rolesResponse = await this.api.get('/roles');
            this.roles = rolesResponse.data;
            this.populateRoleSelect();
            this.updateLoadingProgress(40);
            
            // Load categories
            const categoriesResponse = await this.api.get('/categories');
            this.categories = categoriesResponse.data;
            this.populateCategorySelect();
            this.updateLoadingProgress(60);
            
            // Load dashboard data
            await this.loadDashboardData();
            this.updateLoadingProgress(80);
            
            // Load users
            await this.loadUsers();
            this.updateLoadingProgress(100);
            
        } catch (error) {
            console.error('Failed to load initial data:', error);
            showToast('Ma\'lumotlarni yuklashda xatolik', 'error');
        }
    }
    
    async loadDashboardData() {
        try {
            const range = this.state.get('dateRange') || 'today';
            const response = await this.api.get('/analytics/dashboard', { range });
            
            const data = response.data;
            
            // Update stats
            document.getElementById('totalRevenue').textContent = formatMoney(data.total_revenue);
            document.getElementById('totalOrders').textContent = data.total_orders;
            document.getElementById('totalCustomers').textContent = data.total_customers;
            document.getElementById('averageCheck').textContent = formatMoney(data.average_check);
            
            // Update trends
            this.updateTrend('revenueTrend', data.revenue_trend);
            this.updateTrend('ordersTrend', data.orders_trend);
            this.updateTrend('customersTrend', data.customers_trend);
            this.updateTrend('avgCheckTrend', data.avg_check_trend);
            
            // Render charts
            this.renderRevenueChart(data.revenue_data);
            this.renderPopularProductsChart(data.popular_products);
            this.renderCategoriesChart(data.categories_data);
            this.renderPaymentMethodsChart(data.payment_methods);
            
            // Render recent orders
            this.renderRecentOrders(data.recent_orders);
            
        } catch (error) {
            console.error('Failed to load dashboard data:', error);
        }
    }
    
    updateTrend(elementId, trend) {
        const element = document.getElementById(elementId);
        if (element) {
            const isPositive = trend > 0;
            element.textContent = `${isPositive ? '+' : ''}${trend}%`;
            element.className = `stat-trend ${isPositive ? 'up' : 'down'}`;
        }
    }
    
    renderRevenueChart(data) {
        const ctx = document.getElementById('revenueChart')?.getContext('2d');
        if (!ctx) return;
        
        if (this.charts.revenue) {
            this.charts.revenue.destroy();
        }
        
        this.charts.revenue = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Daromad',
                    data: data.values,
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
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => `${formatMoney(context.raw)}`
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
    
    renderPopularProductsChart(data) {
        const ctx = document.getElementById('popularProductsChart')?.getContext('2d');
        if (!ctx) return;
        
        if (this.charts.popularProducts) {
            this.charts.popularProducts.destroy();
        }
        
        this.charts.popularProducts = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(p => p.name),
                datasets: [{
                    label: 'Sotilgan',
                    data: data.map(p => p.quantity),
                    backgroundColor: 'rgba(201, 168, 76, 0.8)',
                    borderRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    legend: {
                        display: false
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
                    backgroundColor: [
                        '#c9a84c',
                        '#e2c97a',
                        '#9e822e',
                        '#d4af37',
                        '#f4d03f',
                        '#b8960c'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right'
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const value = context.raw;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percent = ((value / total) * 100).toFixed(1);
                                return `${context.label}: ${formatMoney(value)} (${percent}%)`;
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
        
        const labels = {
            'cash': 'Naqd',
            'card': 'Karta',
            'click': 'Click',
            'payme': 'Payme'
        };
        
        this.charts.paymentMethods = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: data.map(p => labels[p.method] || p.method),
                datasets: [{
                    data: data.map(p => p.total),
                    backgroundColor: [
                        '#10b981',
                        '#3b82f6',
                        '#06b6d4',
                        '#6366f1'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }
    
    renderRecentOrders(orders) {
        const tbody = document.getElementById('recentOrdersTable');
        if (!tbody) return;
        
        tbody.innerHTML = orders.map(order => `
            <tr>
                <td><strong>#${order.order_number}</strong></td>
                <td>Stol #${order.table_number}</td>
                <td>${order.waiter_name || '-'}</td>
                <td>${formatMoney(order.final_amount)}</td>
                <td>
                    <span class="status-badge ${order.status}">
                        ${this.getStatusText(order.status)}
                    </span>
                </td>
                <td>${formatTime(order.created_at)}</td>
            </tr>
        `).join('');
    }
    
    async loadUsers() {
        try {
            const response = await this.api.get('/users');
            this.users = response.data;
            this.renderUsersTable(this.users);
            document.getElementById('usersCount').textContent = this.users.length;
        } catch (error) {
            console.error('Failed to load users:', error);
        }
    }
    
    renderUsersTable(users) {
        const tbody = document.getElementById('usersTableBody');
        if (!tbody) return;
        
        tbody.innerHTML = users.map(user => `
            <tr>
                <td><input type="checkbox" class="user-checkbox" value="${user.id}"></td>
                <td>${user.id}</td>
                <td>
                    <div class="user-info-cell">
                        <img src="${user.avatar || '../assets/images/avatar-placeholder.jpg'}" 
                             alt="${user.full_name}" 
                             class="user-avatar-small">
                        <span>${user.full_name}</span>
                    </div>
                </td>
                <td>${user.username}</td>
                <td>${user.email}</td>
                <td>${user.phone || '-'}</td>
                <td>
                    <span class="role-badge">${user.role?.name || '-'}</span>
                </td>
                <td>
                    <span class="status-badge ${user.status}">
                        ${this.getUserStatusText(user.status)}
                    </span>
                </td>
                <td>${user.last_login ? formatDateTime(user.last_login) : '-'}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn-icon glass edit-user" data-id="${user.id}">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="2"/>
                                <path d="M18.5 2.5a2.12 2.12 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="2"/>
                            </svg>
                        </button>
                        <button class="btn-icon glass delete-user" data-id="${user.id}">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" stroke="currentColor" stroke-width="2"/>
                                <path d="M8 4V2h8v2" stroke="currentColor" stroke-width="2"/>
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
        
        // Add event listeners
        tbody.querySelectorAll('.edit-user').forEach(btn => {
            btn.addEventListener('click', () => this.editUser(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.delete-user').forEach(btn => {
            btn.addEventListener('click', () => this.deleteUser(btn.dataset.id));
        });
    }
    
    filterUsers() {
        const searchTerm = document.getElementById('userSearch')?.value.toLowerCase() || '';
        const roleFilter = document.getElementById('userRoleFilter')?.value || '';
        const statusFilter = document.getElementById('userStatusFilter')?.value || '';
        
        const filtered = this.users.filter(user => {
            const matchesSearch = !searchTerm || 
                user.full_name?.toLowerCase().includes(searchTerm) ||
                user.username?.toLowerCase().includes(searchTerm) ||
                user.email?.toLowerCase().includes(searchTerm);
            
            const matchesRole = !roleFilter || user.role?.name === roleFilter;
            const matchesStatus = !statusFilter || user.status === statusFilter;
            
            return matchesSearch && matchesRole && matchesStatus;
        });
        
        this.renderUsersTable(filtered);
    }
    
    openUserModal(userId = null) {
        const modal = this.modals.user;
        const title = document.getElementById('userModalTitle');
        const form = document.getElementById('userForm');
        const passwordHint = document.getElementById('passwordHint');
        
        form.reset();
        
        if (userId) {
            title.textContent = 'Foydalanuvchini tahrirlash';
            const user = this.users.find(u => u.id == userId);
            if (user) {
                form.full_name.value = user.full_name || '';
                form.username.value = user.username || '';
                form.email.value = user.email || '';
                form.phone.value = user.phone || '';
                form.role_id.value = user.role_id || '';
                form.status.value = user.status || 'active';
                form.is_superuser.checked = user.is_superuser || false;
                
                // Password not required for edit
                form.password.required = false;
                form.confirm_password.required = false;
                passwordHint.textContent = 'Bo\'sh qoldirilsa, o\'zgarmaydi';
            }
            form.dataset.userId = userId;
        } else {
            title.textContent = 'Yangi foydalanuvchi';
            form.password.required = true;
            form.confirm_password.required = true;
            passwordHint.textContent = 'Kamida 6 ta belgi';
            delete form.dataset.userId;
        }
        
        modal.open();
    }
    
    async saveUser() {
        const form = document.getElementById('userForm');
        
        // Validate
        if (!this.validateUserForm()) {
            return;
        }
        
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        
        // Convert checkbox
        data.is_superuser = form.is_superuser.checked;
        
        // Remove confirm_password
        delete data.confirm_password;
        
        // Remove empty password
        if (!data.password) {
            delete data.password;
        }
        
        const userId = form.dataset.userId;
        const saveBtn = document.getElementById('saveUserBtn');
        
        try {
            saveBtn.classList.add('loading');
            saveBtn.disabled = true;
            
            if (userId) {
                await this.api.patch(`/users/${userId}`, data);
                showToast('Foydalanuvchi yangilandi', 'success');
            } else {
                await this.api.post('/users', data);
                showToast('Foydalanuvchi yaratildi', 'success');
            }
            
            await this.loadUsers();
            this.modals.user.close();
            
        } catch (error) {
            showToast(error.message || 'Saqlashda xatolik', 'error');
        } finally {
            saveBtn.classList.remove('loading');
            saveBtn.disabled = false;
        }
    }
    
    validateUserForm() {
        const form = document.getElementById('userForm');
        const password = form.password.value;
        const confirm = form.confirm_password.value;
        const userId = form.dataset.userId;
        
        // Check required fields
        if (!form.full_name.value || !form.username.value || !form.email.value) {
            showToast('Barcha majburiy maydonlarni to\'ldiring', 'warning');
            return false;
        }
        
        // Email validation
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(form.email.value)) {
            showToast('To\'g\'ri email kiriting', 'warning');
            return false;
        }
        
        // Password validation for new users
        if (!userId) {
            if (!password || password.length < 6) {
                showToast('Parol kamida 6 ta belgidan iborat bo\'lishi kerak', 'warning');
                return false;
            }
        }
        
        // Password confirmation
        if (password && password !== confirm) {
            showToast('Parollar mos kelmadi', 'warning');
            return false;
        }
        
        return true;
    }
    
    validatePasswordMatch() {
        const password = document.getElementById('userPassword').value;
        const confirm = document.getElementById('confirmPassword').value;
        const confirmInput = document.getElementById('confirmPassword');
        
        if (confirm && password !== confirm) {
            confirmInput.style.borderColor = 'var(--danger)';
            return false;
        } else if (confirm) {
            confirmInput.style.borderColor = 'var(--success)';
            return true;
        }
        return true;
    }
    
    async editUser(userId) {
        this.openUserModal(userId);
    }
    
    async deleteUser(userId) {
        if (!confirm('Foydalanuvchini o\'chirishni xohlaysizmi?')) {
            return;
        }
        
        try {
            await this.api.delete(`/users/${userId}`);
            showToast('Foydalanuvchi o\'chirildi', 'success');
            await this.loadUsers();
        } catch (error) {
            showToast('O\'chirishda xatolik', 'error');
        }
    }
    
    selectAllUsers(checked) {
        document.querySelectorAll('.user-checkbox').forEach(cb => {
            cb.checked = checked;
        });
    }
    
    async loadMenuData() {
        try {
            const response = await this.api.get('/products');
            this.products = response.data;
            
            this.renderCategoriesList();
            this.renderProductsTable(this.products);
        } catch (error) {
            console.error('Failed to load menu data:', error);
        }
    }
    
    renderCategoriesList() {
        const container = document.getElementById('adminCategoriesList');
        if (!container) return;
        
        container.innerHTML = this.categories.map(category => `
            <div class="category-item-admin" data-id="${category.id}">
                <span class="category-name">${category.name}</span>
                <span class="category-count">${category.product_count || 0}</span>
                <div class="category-actions">
                    <button class="btn-icon glass edit-category" data-id="${category.id}">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="2"/>
                            <path d="M18.5 2.5a2.12 2.12 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="2"/>
                        </svg>
                    </button>
                </div>
            </div>
        `).join('');
        
        // Add "All categories" option
        container.insertAdjacentHTML('afterbegin', `
            <div class="category-item-admin active" data-id="">
                <span class="category-name">Barcha mahsulotlar</span>
                <span class="category-count">${this.products.length}</span>
            </div>
        `);
        
        // Add event listeners
        container.querySelectorAll('.category-item-admin').forEach(item => {
            item.addEventListener('click', () => this.filterProductsByCategory(item.dataset.id));
        });
    }
    
    renderProductsTable(products) {
        const tbody = document.getElementById('productsTableBody');
        if (!tbody) return;
        
        tbody.innerHTML = products.map(product => `
            <tr>
                <td>
                    <img src="${product.image_url || '../assets/images/product-placeholder.jpg'}" 
                         alt="${product.name}" 
                         class="product-thumbnail">
                </td>
                <td>
                    <strong>${product.name}</strong>
                    ${product.description ? `<br><small>${product.description.substring(0, 50)}...</small>` : ''}
                </td>
                <td>${product.category?.name || '-'}</td>
                <td>${formatMoney(product.price)}</td>
                <td>${product.cost_price ? formatMoney(product.cost_price) : '-'}</td>
                <td>
                    <span class="status-badge ${product.is_active ? 'active' : 'inactive'}">
                        ${product.is_active ? 'Faol' : 'Nofaol'}
                    </span>
                </td>
                <td>
                    <div class="action-buttons">
                        <button class="btn-icon glass edit-product" data-id="${product.id}">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="2"/>
                                <path d="M18.5 2.5a2.12 2.12 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="2"/>
                            </svg>
                        </button>
                        <button class="btn-icon glass delete-product" data-id="${product.id}">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" stroke="currentColor" stroke-width="2"/>
                                <path d="M8 4V2h8v2" stroke="currentColor" stroke-width="2"/>
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
        
        // Add event listeners
        tbody.querySelectorAll('.edit-product').forEach(btn => {
            btn.addEventListener('click', () => this.editProduct(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.delete-product').forEach(btn => {
            btn.addEventListener('click', () => this.deleteProduct(btn.dataset.id));
        });
    }
    
    filterProductsByCategory(categoryId) {
        // Update active state
        document.querySelectorAll('.category-item-admin').forEach(item => {
            item.classList.toggle('active', item.dataset.id === categoryId);
        });
        
        if (!categoryId) {
            this.renderProductsTable(this.products);
        } else {
            const filtered = this.products.filter(p => p.category_id == categoryId);
            this.renderProductsTable(filtered);
        }
    }
    
    filterProducts() {
        const searchTerm = document.getElementById('productSearch')?.value.toLowerCase() || '';
        
        const filtered = this.products.filter(p => 
            p.name.toLowerCase().includes(searchTerm) ||
            p.barcode?.toLowerCase().includes(searchTerm)
        );
        
        this.renderProductsTable(filtered);
    }
    
    openProductModal(productId = null) {
        const modal = this.modals.product;
        const title = document.getElementById('productModalTitle');
        const form = document.getElementById('productForm');
        
        form.reset();
        this.populateCategorySelect();
        
        if (productId) {
            title.textContent = 'Mahsulotni tahrirlash';
            const product = this.products.find(p => p.id == productId);
            if (product) {
                form.name.value = product.name || '';
                form.category_id.value = product.category_id || '';
                form.price.value = product.price || '';
                form.cost_price.value = product.cost_price || '';
                form.barcode.value = product.barcode || '';
                form.preparation_time.value = product.preparation_time || 15;
                form.description.value = product.description || '';
                form.is_active.checked = product.is_active;
                form.is_available.checked = product.is_available;
            }
            form.dataset.productId = productId;
        } else {
            title.textContent = 'Yangi mahsulot';
            delete form.dataset.productId;
        }
        
        modal.open();
    }
    
    populateCategorySelect() {
        const select = document.getElementById('productCategory');
        if (!select) return;
        
        select.innerHTML = '<option value="">Kategoriya tanlang</option>' +
            this.categories.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
    }
    
    populateRoleSelect() {
        const select = document.getElementById('userRole');
        if (!select) return;
        
        select.innerHTML = '<option value="">Rol tanlang</option>' +
            this.roles.map(r => `<option value="${r.id}">${r.name}</option>`).join('');
    }
    
    async saveProduct() {
        const form = document.getElementById('productForm');
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        
        // Convert checkboxes
        data.is_active = form.is_active.checked;
        data.is_available = form.is_available.checked;
        
        // Convert numbers
        data.price = parseFloat(data.price);
        data.cost_price = parseFloat(data.cost_price) || 0;
        data.preparation_time = parseInt(data.preparation_time) || 15;
        
        const productId = form.dataset.productId;
        
        try {
            if (productId) {
                await this.api.patch(`/products/${productId}`, data);
                showToast('Mahsulot yangilandi', 'success');
            } else {
                await this.api.post('/products', data);
                showToast('Mahsulot yaratildi', 'success');
            }
            
            await this.loadMenuData();
            this.modals.product.close();
            
        } catch (error) {
            showToast(error.message || 'Saqlashda xatolik', 'error');
        }
    }
    
    async editProduct(productId) {
        this.openProductModal(productId);
    }
    
    async deleteProduct(productId) {
        if (!confirm('Mahsulotni o\'chirishni xohlaysizmi?')) {
            return;
        }
        
        try {
            await this.api.delete(`/products/${productId}`);
            showToast('Mahsulot o\'chirildi', 'success');
            await this.loadMenuData();
        } catch (error) {
            showToast('O\'chirishda xatolik', 'error');
        }
    }
    
    openCategoryManager() {
        // Category management modal
        showToast('Kategoriya boshqaruvi tez orada...', 'info');
    }
    
    setDateRange(range) {
        this.state.set('dateRange', range);
        
        document.querySelectorAll('.date-range-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.range === range);
        });
        
        this.loadDashboardData();
    }
    
    async loadAnalyticsData() {
        // Will be implemented
    }
    
    async loadReportsData() {
        // Will be implemented
    }
    
    refreshCurrentSection() {
        this.loadSectionData(this.currentSection);
        showToast('Yangilandi', 'info');
    }
    
    toggleSidebar() {
        document.getElementById('sidebar')?.classList.toggle('collapsed');
    }
    
    toggleMobileMenu() {
        document.getElementById('sidebar')?.classList.toggle('open');
    }
    
    toggleTheme() {
        const html = document.documentElement;
        const currentTheme = html.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        html.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        
        // Update charts theme if needed
    }
    
    updateUI() {
        // Update user info
        const user = this.auth.getCurrentUser();
        if (user) {
            document.getElementById('adminName').textContent = user.full_name;
        }
        
        // Update date
        this.updateDateDisplay();
        setInterval(() => this.updateDateDisplay(), 1000);
        
        // Restore theme
        const savedTheme = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', savedTheme);
    }
    
    updateDateDisplay() {
        const now = new Date();
        const options = { 
            weekday: 'long', 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric' 
        };
        document.getElementById('dateText').textContent = now.toLocaleDateString('uz-UZ', options);
    }
    
    updateLoadingProgress(percent) {
        const progressBar = document.getElementById('loadingProgress');
        if (progressBar) {
            progressBar.style.width = `${percent}%`;
        }
    }
    
    hideLoadingScreen() {
        const loadingScreen = document.getElementById('loadingScreen');
        loadingScreen?.classList.add('hidden');
    }
    
    getStatusText(status) {
        const texts = {
            'pending': 'Kutilmoqda',
            'preparing': 'Tayyorlanmoqda',
            'ready': 'Tayyor',
            'served': 'Xizmat ko\'rsatildi',
            'completed': 'Yakunlangan',
            'cancelled': 'Bekor qilingan'
        };
        return texts[status] || status;
    }
    
    getUserStatusText(status) {
        const texts = {
            'active': 'Faol',
            'inactive': 'Nofaol',
            'blocked': 'Bloklangan'
        };
        return texts[status] || status;
    }
    
    async logout() {
        if (confirm('Tizimdan chiqishni xohlaysizmi?')) {
            await this.auth.logout();
            window.location.href = '../shared/login.html';
        }
    }
}

// Initialize Admin Module
document.addEventListener('DOMContentLoaded', () => {
    window.admin = new AdminModule();
});

export default AdminModule;