import { API } from '../core/api.js';
import { showToast } from '../ui/toast.js';
import { Modal } from '../ui/modal.js';

class EmployeesModule {
    constructor() {
        this.api = new API();
        this.modal = new Modal('employeeModal');
        this.employees = [];
        this.cafes = [];
        this.editingId = null;
        
        this.init();
    }
    
    async init() {
        await this.loadData();
        this.setupEventListeners();
        this.renderEmployees();
        this.updateStats();
    }
    
    setupEventListeners() {
        document.getElementById('addEmployeeBtn').addEventListener('click', () => this.openModal());
        document.getElementById('saveEmployeeBtn').addEventListener('click', () => this.saveEmployee());
        document.getElementById('generatePinBtn').addEventListener('click', () => this.generatePin());
        document.getElementById('searchInput').addEventListener('input', () => this.filterEmployees());
        document.getElementById('positionFilter').addEventListener('change', () => this.filterEmployees());
        document.getElementById('cafeFilter').addEventListener('change', () => this.filterEmployees());
        document.getElementById('statusFilter').addEventListener('change', () => this.filterEmployees());
        
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => this.modal.close());
        });
    }
    
    async loadData() {
        try {
            const [employeesRes, cafesRes, attendanceRes] = await Promise.all([
                this.api.get('/employees/list'),
                this.api.get('/cafes/all'),
                this.api.get('/attendance/today')
            ]);
            
            this.employees = employeesRes.data?.items || [];
            this.cafes = cafesRes.data || [];
            this.todayAttendance = attendanceRes.data || [];
            
            this.populateCafeSelect();
            this.populateCafeFilter();
        } catch (error) {
            console.error('Ma\'lumotlarni yuklashda xatolik:', error);
            showToast('Ma\'lumotlarni yuklashda xatolik', 'error');
        }
    }
    
    populateCafeSelect() {
        const select = document.getElementById('cafeId');
        select.innerHTML = '<option value="">Kafe tanlang</option>';
        this.cafes.forEach(cafe => {
            const option = document.createElement('option');
            option.value = cafe.id;
            option.textContent = cafe.name;
            select.appendChild(option);
        });
    }
    
    populateCafeFilter() {
        const select = document.getElementById('cafeFilter');
        select.innerHTML = '<option value="">Barcha kafelar</option>';
        this.cafes.forEach(cafe => {
            const option = document.createElement('option');
            option.value = cafe.id;
            option.textContent = cafe.name;
            select.appendChild(option);
        });
    }
    
    renderEmployees() {
        const tbody = document.getElementById('employeesTableBody');
        
        if (this.employees.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" style="text-align: center; padding: 40px;">
                        <h3>👥 Xodimlar mavjud emas</h3>
                        <p>Yangi xodim qo'shish uchun "Yangi xodim" tugmasini bosing</p>
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = this.employees.map(emp => this.createEmployeeRow(emp)).join('');
        
        tbody.querySelectorAll('.edit-employee').forEach(btn => {
            btn.addEventListener('click', () => this.editEmployee(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.delete-employee').forEach(btn => {
            btn.addEventListener('click', () => this.deleteEmployee(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.attendance-employee').forEach(btn => {
            btn.addEventListener('click', () => this.viewAttendance(btn.dataset.id));
        });
    }
    
    createEmployeeRow(emp) {
        const cafe = this.cafes.find(c => c.id === emp.cafe_id);
        const isPresent = this.todayAttendance?.find(a => a.employee_id === emp.id);
        
        return `
            <tr>
                <td>
                    <div class="employee-info">
                        <div class="employee-avatar">${emp.full_name.charAt(0)}</div>
                        <div>
                            <div class="employee-name">${emp.full_name}</div>
                            <small style="color: var(--text-secondary);">${isPresent ? '🟢 Bugun ishda' : '⚪'}</small>
                        </div>
                    </div>
                </td>
                <td>${this.getPositionText(emp.position)}</td>
                <td>${emp.phone || '-'}</td>
                <td>${cafe?.name || '-'}</td>
                <td><span class="pin-code">${emp.pin_code || '——'}</span></td>
                <td>${emp.salary_rate?.toLocaleString() || 0} UZS</td>
                <td>
                    <span class="status-badge ${emp.is_active ? 'active' : 'inactive'}">
                        ${emp.is_active ? 'Faol' : 'Nofaol'}
                    </span>
                </td>
                <td>
                    <div class="action-buttons">
                        <button class="action-btn attendance-employee" data-id="${emp.id}" title="Davomat">📅</button>
                        <button class="action-btn edit-employee" data-id="${emp.id}" title="Tahrirlash">✏️</button>
                        <button class="action-btn delete-employee" data-id="${emp.id}" title="O'chirish">🗑️</button>
                    </div>
                </td>
            </tr>
        `;
    }
    
    getPositionText(position) {
        const positions = {
            'admin': '👑 Admin',
            'waiter': '🍽️ Ofitsiant',
            'kitchen': '👨‍🍳 Oshpaz',
            'cashier': '💰 Kassir'
        };
        return positions[position] || position;
    }
    
    updateStats() {
        const activeEmployees = this.employees.filter(e => e.is_active);
        const presentToday = this.todayAttendance?.length || 0;
        const avgSalary = activeEmployees.length > 0 
            ? activeEmployees.reduce((sum, e) => sum + (e.salary_rate || 0), 0) / activeEmployees.length 
            : 0;
        
        document.getElementById('totalEmployees').textContent = activeEmployees.length;
        document.getElementById('presentToday').textContent = presentToday;
        document.getElementById('avgSalary').textContent = Math.round(avgSalary).toLocaleString() + ' UZS';
    }
    
    openModal(employee = null) {
        this.editingId = employee?.id || null;
        document.getElementById('modalTitle').textContent = employee ? 'Xodimni tahrirlash' : 'Yangi xodim';
        document.getElementById('employeeForm').reset();
        
        if (employee) {
            document.getElementById('employeeId').value = employee.id;
            document.getElementById('fullName').value = employee.full_name;
            document.getElementById('phone').value = employee.phone || '';
            document.getElementById('position').value = employee.position || 'waiter';
            document.getElementById('cafeId').value = employee.cafe_id || '';
            document.getElementById('salaryRate').value = employee.salary_rate || 0;
            document.getElementById('pinCode').value = employee.pin_code || '';
        }
        
        this.modal.open();
    }
    
    generatePin() {
        const pin = Math.floor(1000 + Math.random() * 9000).toString();
        document.getElementById('pinCode').value = pin;
    }
    
    async saveEmployee() {
        const employeeId = document.getElementById('employeeId').value;
        const data = {
            full_name: document.getElementById('fullName').value,
            phone: document.getElementById('phone').value || null,
            position: document.getElementById('position').value,
            cafe_id: document.getElementById('cafeId').value ? parseInt(document.getElementById('cafeId').value) : null,
            salary_rate: parseFloat(document.getElementById('salaryRate').value) || 0,
            pin_code: document.getElementById('pinCode').value || null
        };
        
        if (!data.full_name) {
            showToast('To\'liq ism majburiy', 'warning');
            return;
        }
        
        try {
            if (employeeId) {
                await this.api.patch(`/employees/${employeeId}`, data);
                showToast('Xodim yangilandi', 'success');
            } else {
                await this.api.post('/employees/create', data);
                showToast('Xodim yaratildi', 'success');
            }
            
            await this.loadData();
            this.renderEmployees();
            this.updateStats();
            this.modal.close();
        } catch (error) {
            console.error('Saqlashda xatolik:', error);
            showToast(error.message || 'Saqlashda xatolik', 'error');
        }
    }
    
    editEmployee(id) {
        const employee = this.employees.find(e => e.id == id);
        if (employee) {
            this.openModal(employee);
        }
    }
    
    async deleteEmployee(id) {
        if (!confirm('Xodimni o\'chirishni xohlaysizmi?')) return;
        
        try {
            await this.api.delete(`/employees/${id}`);
            showToast('Xodim o\'chirildi', 'success');
            await this.loadData();
            this.renderEmployees();
            this.updateStats();
        } catch (error) {
            console.error('O\'chirishda xatolik:', error);
            showToast('O\'chirishda xatolik', 'error');
        }
    }
    
    viewAttendance(id) {
        window.location.href = `attendance.html?employee=${id}`;
    }
    
    filterEmployees() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const position = document.getElementById('positionFilter').value;
        const cafeId = document.getElementById('cafeFilter').value;
        const status = document.getElementById('statusFilter').value;
        
        let filtered = this.employees;
        
        if (searchTerm) {
            filtered = filtered.filter(e => 
                e.full_name.toLowerCase().includes(searchTerm) ||
                (e.phone && e.phone.includes(searchTerm))
            );
        }
        
        if (position) {
            filtered = filtered.filter(e => e.position === position);
        }
        
        if (cafeId) {
            filtered = filtered.filter(e => e.cafe_id == cafeId);
        }
        
        if (status) {
            const isActive = status === 'active';
            filtered = filtered.filter(e => e.is_active === isActive);
        }
        
        const tbody = document.getElementById('employeesTableBody');
        if (filtered.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" style="text-align: center; padding: 40px;">
                        <h3>🔍 Xodim topilmadi</h3>
                        <p>Boshqa kalit so'z yoki filtr bilan qidirib ko'ring</p>
                    </td>
                </tr>
            `;
        } else {
            tbody.innerHTML = filtered.map(emp => this.createEmployeeRow(emp)).join('');
            
            tbody.querySelectorAll('.edit-employee').forEach(btn => {
                btn.addEventListener('click', () => this.editEmployee(btn.dataset.id));
            });
            
            tbody.querySelectorAll('.delete-employee').forEach(btn => {
                btn.addEventListener('click', () => this.deleteEmployee(btn.dataset.id));
            });
            
            tbody.querySelectorAll('.attendance-employee').forEach(btn => {
                btn.addEventListener('click', () => this.viewAttendance(btn.dataset.id));
            });
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new EmployeesModule();
});

export default EmployeesModule;