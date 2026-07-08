import { API } from './core/api.js';
import { AuthService } from './core/auth.js';
import { Modal } from './ui/modal.js';
import { showToast } from './ui/toast.js';
import { formatDateTime } from './utils/formatter.js';

class UsersModule {
    constructor() {
        this.api = new API();
        this.auth = new AuthService();
        this.users = [];
        this.roles = [];
        this.modal = new Modal('userModal');
        this.currentUser = null;
        this.init();
    }
    
    async init() {
        this.setupEventListeners();
        await this.loadRoles();
        await this.loadUsers();
        this.renderUsers();
    }
    
    setupEventListeners() {
        document.getElementById('addUserBtn')?.addEventListener('click', () => this.openModal());
        document.getElementById('saveUserBtn')?.addEventListener('click', () => this.saveUser());
        document.getElementById('userSearch')?.addEventListener('input', (e) => this.filterUsers(e.target.value));
        document.getElementById('roleFilter')?.addEventListener('change', () => this.filterUsers());
        document.getElementById('statusFilter')?.addEventListener('change', () => this.filterUsers());
    }
    
    async loadRoles() {
        const response = await this.api.get('/roles');
        this.roles = response.data || [];
        this.populateRoleSelect();
    }
    
    async loadUsers() {
        const response = await this.api.get('/users');
        this.users = response.data?.items || [];
    }
    
    populateRoleSelect() {
        const select = document.getElementById('userRole');
        if (select) {
            select.innerHTML = '<option value="">Rol tanlang</option>' +
                this.roles.map(r => `<option value="${r.id}">${r.name}</option>`).join('');
        }
    }
    
    renderUsers(users = null) {
        const tbody = document.getElementById('usersTableBody');
        const displayUsers = users || this.users;
        
        tbody.innerHTML = displayUsers.map(user => `
            <tr>
                <td>${user.id}</td>
                <td>
                    <div class="user-info">
                        <span class="user-name">${user.full_name}</span>
                        <span class="user-username">@${user.username}</span>
                    </div>
                </td>
                <td>${user.email}</td>
                <td>${user.phone || '-'}</td>
                <td>${user.role?.name || '-'}</td>
                <td>
                    <span class="status-badge ${user.is_active ? 'active' : 'inactive'}">
                        ${user.is_active ? 'Faol' : 'Nofaol'}
                    </span>
                </td>
                <td>${user.last_login ? formatDateTime(user.last_login) : '-'}</td>
                <td>
                    <div class="actions">
                        <button class="btn-icon edit-user" data-id="${user.id}">✏️</button>
                        <button class="btn-icon reset-password" data-id="${user.id}">🔑</button>
                        <button class="btn-icon toggle-user" data-id="${user.id}">
                            ${user.is_active ? '🔴' : '🟢'}
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
        
        tbody.querySelectorAll('.edit-user').forEach(btn => {
            btn.addEventListener('click', () => this.editUser(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.reset-password').forEach(btn => {
            btn.addEventListener('click', () => this.resetPassword(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.toggle-user').forEach(btn => {
            btn.addEventListener('click', () => this.toggleUser(btn.dataset.id));
        });
    }
    
    filterUsers(searchTerm = '') {
        const roleFilter = document.getElementById('roleFilter')?.value;
        const statusFilter = document.getElementById('statusFilter')?.value;
        
        let filtered = this.users;
        
        if (searchTerm) {
            filtered = filtered.filter(u => 
                u.full_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                u.username?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                u.email?.toLowerCase().includes(searchTerm.toLowerCase())
            );
        }
        
        if (roleFilter) {
            filtered = filtered.filter(u => u.role?.id == roleFilter);
        }
        
        if (statusFilter) {
            const isActive = statusFilter === 'active';
            filtered = filtered.filter(u => u.is_active === isActive);
        }
        
        this.renderUsers(filtered);
    }
    
    openModal(user = null) {
        this.currentUser = user;
        const title = document.getElementById('userModalTitle');
        const form = document.getElementById('userForm');
        
        form.reset();
        this.populateRoleSelect();
        
        if (user) {
            title.textContent = 'Foydalanuvchini tahrirlash';
            form.full_name.value = user.full_name || '';
            form.username.value = user.username || '';
            form.email.value = user.email || '';
            form.phone.value = user.phone || '';
            form.role_id.value = user.role_id || '';
            form.is_active.checked = user.is_active;
        } else {
            title.textContent = 'Yangi foydalanuvchi';
        }
        
        this.modal.open();
    }
    
    async saveUser() {
        const form = document.getElementById('userForm');
        const data = Object.fromEntries(new FormData(form));
        
        data.is_active = form.is_active.checked;
        data.role_id = data.role_id ? parseInt(data.role_id) : null;
        
        if (!this.currentUser && !data.password) {
            showToast('Parol kiriting', 'warning');
            return;
        }
        
        if (data.password && data.password !== data.confirm_password) {
            showToast('Parollar mos kelmadi', 'warning');
            return;
        }
        
        delete data.confirm_password;
        
        try {
            if (this.currentUser) {
                await this.api.patch(`/users/${this.currentUser.id}`, data);
                showToast('Foydalanuvchi yangilandi', 'success');
            } else {
                await this.api.post('/users', data);
                showToast('Foydalanuvchi yaratildi', 'success');
            }
            
            await this.loadUsers();
            this.renderUsers();
            this.modal.close();
        } catch (error) {
            showToast(error.message || 'Xatolik yuz berdi', 'error');
        }
    }
    
    editUser(id) {
        const user = this.users.find(u => u.id == id);
        if (user) this.openModal(user);
    }
    
    async resetPassword(id) {
        const newPassword = prompt('Yangi parolni kiriting:');
        if (!newPassword) return;
        
        try {
            await this.api.post(`/users/${id}/reset-password`, { new_password: newPassword });
            showToast('Parol yangilandi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
    
    async toggleUser(id) {
        const user = this.users.find(u => u.id == id);
        if (!user) return;
        
        try {
            await this.api.patch(`/users/${id}`, { is_active: !user.is_active });
            await this.loadUsers();
            this.renderUsers();
            showToast('Foydalanuvchi holati o\'zgartirildi', 'success');
        } catch (error) {
            showToast('Xatolik yuz berdi', 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => new UsersModule());