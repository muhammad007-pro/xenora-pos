import { API } from '../core/api.js';
import { showToast } from '../ui/toast.js';
import { Modal } from '../ui/modal.js';

class SalaryModule {
    constructor() {
        this.api = new API();
        this.modal = new Modal('salaryModal');
        this.salaries = [];
        this.employees = [];
        this.cafes = [];
        this.selectedMonth = new Date().getMonth() + 1;
        this.selectedYear = new Date().getFullYear();
        this.currentEmployee = null;
        
        this.init();
    }
    
    async init() {
        this.populateMonthYearSelects();
        await this.loadData();
        this.setupEventListeners();
        this.renderSalaries();
        this.updateSummary();
    }
    
    populateMonthYearSelects() {
        const monthSelect = document.getElementById('monthSelect');
        const months = ['Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun', 'Iyul', 'Avgust', 'Sentabr', 'Oktabr', 'Noyabr', 'Dekabr'];
        
        monthSelect.innerHTML = months.map((m, i) => 
            `<option value="${i + 1}" ${i + 1 === this.selectedMonth ? 'selected' : ''}>${m}</option>`
        ).join('');
        
        const yearSelect = document.getElementById('yearSelect');
        const currentYear = new Date().getFullYear();
        for (let y = currentYear - 2; y <= currentYear + 1; y++) {
            const option = document.createElement('option');
            option.value = y;
            option.textContent = y;
            if (y === this.selectedYear) option.selected = true;
            yearSelect.appendChild(option);
        }
    }
    
    setupEventListeners() {
        document.getElementById('calculateAllBtn').addEventListener('click', () => this.calculateAll());
        document.getElementById('saveSalaryBtn').addEventListener('click', () => this.saveSalary());
        document.getElementById('prevMonth').addEventListener('click', () => this.changeMonth(-1));
        document.getElementById('nextMonth').addEventListener('click', () => this.changeMonth(1));
        document.getElementById('monthSelect').addEventListener('change', (e) => this.setMonth(e.target.value));
        document.getElementById('yearSelect').addEventListener('change', (e) => this.setYear(e.target.value));
        document.getElementById('searchInput').addEventListener('input', () => this.filterSalaries());
        document.getElementById('cafeFilter').addEventListener('change', () => this.filterSalaries());
        document.getElementById('statusFilter').addEventListener('change', () => this.filterSalaries());
        
        document.getElementById('bonus').addEventListener('input', () => this.updateTotalSalary());
        document.getElementById('deduction').addEventListener('input', () => this.updateTotalSalary());
        
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => this.modal.close());
        });
    }
    
    async loadData() {
        try {
            const [employeesRes, cafesRes, salariesRes] = await Promise.all([
                this.api.get('/employees/list', { is_active: true }),
                this.api.get('/cafes/all'),
                this.api.get('/salaries', { month: this.selectedMonth, year: this.selectedYear })
            ]);
            
            this.employees = employeesRes.data?.items || [];
            this.cafes = cafesRes.data || [];
            this.salaries = salariesRes.data?.items || [];
            
            this.populateCafeFilter();
        } catch (error) {
            console.error('Ma\'lumotlarni yuklashda xatolik:', error);
            showToast('Ma\'lumotlarni yuklashda xatolik', 'error');
        }
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
    
    renderSalaries() {
        const tbody = document.getElementById('salaryTableBody');
        
        const employeesWithSalary = this.salaries.map(s => s.employee_id);
        const employeesWithoutSalary = this.employees.filter(e => !employeesWithSalary.includes(e.id));
        
        const allRows = [
            ...this.salaries.map(s => this.createSalaryRow(s)),
            ...employeesWithoutSalary.map(e => this.createEmptyRow(e))
        ];
        
        if (allRows.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 40px;">💰 Ma'lumot topilmadi</td></tr>`;
        } else {
            tbody.innerHTML = allRows.join('');
        }
        
        tbody.querySelectorAll('.calculate-btn').forEach(btn => {
            btn.addEventListener('click', () => this.openCalculateModal(btn.dataset.id));
        });
        
        tbody.querySelectorAll('.pay-btn').forEach(btn => {
            btn.addEventListener('click', () => this.markAsPaid(btn.dataset.id));
        });
    }
    
    createSalaryRow(salary) {
        const employee = this.employees.find(e => e.id === salary.employee_id);
        const cafe = this.cafes.find(c => c.id === employee?.cafe_id);
        
        return `
            <tr>
                <td>
                    <div class="employee-info">
                        <div class="employee-avatar">${salary.employee_name?.charAt(0) || '?'}</div>
                        <span>${salary.employee_name || '-'}</span>
                    </div>
                </td>
                <td>${cafe?.name || '-'}</td>
                <td>${this.getPositionText(employee?.position)}</td>
                <td>${salary.total_hours?.toFixed(1) || 0} soat</td>
                <td>${salary.hourly_rate?.toLocaleString() || 0} UZS</td>
                <td>${salary.base_salary?.toLocaleString() || 0} UZS</td>
                <td>${salary.bonus?.toLocaleString() || 0} UZS</td>
                <td><strong>${salary.total_salary?.toLocaleString() || 0} UZS</strong></td>
                <td>
                    <span class="status-badge ${salary.is_paid ? 'paid' : 'unpaid'}">
                        ${salary.is_paid ? '✅ To\'langan' : '⏳ Kutilmoqda'}
                    </span>
                </td>
                <td>
                    <div class="action-buttons">
                        ${!salary.is_paid ? 
                            `<button class="action-btn pay-btn" data-id="${salary.id}">💵 To'lash</button>` : 
                            `<button class="action-btn" disabled>✅</button>`
                        }
                    </div>
                </td>
            </tr>
        `;
    }
    
    createEmptyRow(employee) {
        const cafe = this.cafes.find(c => c.id === employee.cafe_id);
        
        return `
            <tr>
                <td>
                    <div class="employee-info">
                        <div class="employee-avatar">${employee.full_name.charAt(0)}</div>
                        <span>${employee.full_name}</span>
                    </div>
                </td>
                <td>${cafe?.name || '-'}</td>
                <td>${this.getPositionText(employee.position)}</td>
                <td colspan="5" style="color: var(--text-secondary);">— Hisoblanmagan —</td>
                <td>
                    <span class="status-badge unpaid">Hisoblanmagan</span>
                </td>
                <td>
                    <div class="action-buttons">
                        <button class="action-btn calculate-btn" data-id="${employee.id}">📊 Hisoblash</button>
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
    
    updateSummary() {
        const total = this.salaries.reduce((sum, s) => sum + (s.total_salary || 0), 0);
        const paid = this.salaries.filter(s => s.is_paid).reduce((sum, s) => sum + (s.total_salary || 0), 0);
        const unpaid = total - paid;
        const totalHours = this.salaries.reduce((sum, s) => sum + (s.total_hours || 0), 0);
        
        document.getElementById('totalSalary').textContent = Math.round(total).toLocaleString() + ' UZS';
        document.getElementById('paidSalary').textContent = Math.round(paid).toLocaleString() + ' UZS';
        document.getElementById('unpaidSalary').textContent = Math.round(unpaid).toLocaleString() + ' UZS';
        document.getElementById('totalHours').textContent = totalHours.toFixed(1) + ' soat';
    }
    
    async openCalculateModal(employeeId) {
        const employee = this.employees.find(e => e.id == employeeId);
        if (!employee) return;
        
        this.currentEmployee = employee;
        
        try {
            const attendanceRes = await this.api.get(`/attendance/employee/${employeeId}/summary`, {
                month: this.selectedMonth,
                year: this.selectedYear
            });
            
            const data = attendanceRes.data || {};
            
            document.getElementById('employeeId').value = employeeId;
            document.getElementById('employeeInfo').innerHTML = `
                <h4>${employee.full_name}</h4>
                <p>${this.getPositionText(employee.position)} • ${data.days_present || 0} kun ishlagan</p>
            `;
            document.getElementById('totalHours').value = data.total_hours || 0;
            document.getElementById('hourlyRate').value = employee.salary_rate || 0;
            
            const baseSalary = (data.total_hours || 0) * (employee.salary_rate || 0);
            document.getElementById('baseSalary').value = Math.round(baseSalary);
            document.getElementById('bonus').value = 0;
            document.getElementById('deduction').value = 0;
            document.getElementById('totalSalaryInput').value = Math.round(baseSalary);
            
            this.modal.open();
        } catch (error) {
            console.error('Davomat ma\'lumotlarini yuklashda xatolik:', error);
            showToast('Davomat ma\'lumotlarini yuklashda xatolik', 'error');
        }
    }
    
    updateTotalSalary() {
        const base = parseFloat(document.getElementById('baseSalary').value) || 0;
        const bonus = parseFloat(document.getElementById('bonus').value) || 0;
        const deduction = parseFloat(document.getElementById('deduction').value) || 0;
        
        document.getElementById('totalSalaryInput').value = Math.round(base + bonus - deduction);
    }
    
    async saveSalary() {
        const employeeId = document.getElementById('employeeId').value;
        const bonus = parseFloat(document.getElementById('bonus').value) || 0;
        const deduction = parseFloat(document.getElementById('deduction').value) || 0;
        const notes = document.getElementById('notes').value;
        
        try {
            await this.api.post(`/salaries/calculate/${employeeId}`, {
                month: this.selectedMonth,
                year: this.selectedYear,
                bonus: bonus,
                deduction: deduction,
                notes: notes
            });
            
            showToast('Ish haqi hisoblandi', 'success');
            await this.loadData();
            this.renderSalaries();
            this.updateSummary();
            this.modal.close();
        } catch (error) {
            console.error('Hisoblashda xatolik:', error);
            showToast(error.message || 'Hisoblashda xatolik', 'error');
        }
    }
    
    async markAsPaid(salaryId) {
        if (!confirm('Ish haqi to\'langan deb belgilansinmi?')) return;
        
        try {
            await this.api.post(`/salaries/${salaryId}/pay`);
            showToast('To\'langan deb belgilandi', 'success');
            await this.loadData();
            this.renderSalaries();
            this.updateSummary();
        } catch (error) {
            console.error('To\'lashda xatolik:', error);
            showToast('To\'lashda xatolik', 'error');
        }
    }
    
    async calculateAll() {
        if (!confirm(`${this.selectedMonth}-oy uchun barcha xodimlarga ish haqi hisoblansinmi?`)) return;
        
        const employeesWithoutSalary = this.employees.filter(e => 
            !this.salaries.find(s => s.employee_id === e.id)
        );
        
        let successCount = 0;
        for (const emp of employeesWithoutSalary) {
            try {
                await this.api.post(`/salaries/calculate/${emp.id}`, {
                    month: this.selectedMonth,
                    year: this.selectedYear,
                    bonus: 0,
                    deduction: 0
                });
                successCount++;
            } catch (error) {
                console.error(`${emp.full_name} uchun hisoblashda xatolik:`, error);
            }
        }
        
        showToast(`${successCount} ta xodim uchun ish haqi hisoblandi`, 'success');
        await this.loadData();
        this.renderSalaries();
        this.updateSummary();
    }
    
    changeMonth(delta) {
        let newMonth = this.selectedMonth + delta;
        let newYear = this.selectedYear;
        
        if (newMonth < 1) {
            newMonth = 12;
            newYear--;
        } else if (newMonth > 12) {
            newMonth = 1;
            newYear++;
        }
        
        this.selectedMonth = newMonth;
        this.selectedYear = newYear;
        
        document.getElementById('monthSelect').value = newMonth;
        document.getElementById('yearSelect').value = newYear;
        
        this.loadData().then(() => {
            this.renderSalaries();
            this.updateSummary();
        });
    }
    
    setMonth(month) {
        this.selectedMonth = parseInt(month);
        this.loadData().then(() => {
            this.renderSalaries();
            this.updateSummary();
        });
    }
    
    setYear(year) {
        this.selectedYear = parseInt(year);
        this.loadData().then(() => {
            this.renderSalaries();
            this.updateSummary();
        });
    }
    
    filterSalaries() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const cafeId = document.getElementById('cafeFilter').value;
        const status = document.getElementById('statusFilter').value;
        
        let filtered = [...this.salaries];
        
        if (searchTerm) {
            filtered = filtered.filter(s => 
                s.employee_name?.toLowerCase().includes(searchTerm)
            );
        }
        
        if (cafeId) {
            filtered = filtered.filter(s => {
                const emp = this.employees.find(e => e.id === s.employee_id);
                return emp?.cafe_id == cafeId;
            });
        }
        
        if (status === 'paid') {
            filtered = filtered.filter(s => s.is_paid);
        } else if (status === 'unpaid') {
            filtered = filtered.filter(s => !s.is_paid);
        }
        
        const tbody = document.getElementById('salaryTableBody');
        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 40px;">🔍 Ma'lumot topilmadi</td></tr>`;
        } else {
            tbody.innerHTML = filtered.map(s => this.createSalaryRow(s)).join('');
            
            tbody.querySelectorAll('.pay-btn').forEach(btn => {
                btn.addEventListener('click', () => this.markAsPaid(btn.dataset.id));
            });
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new SalaryModule();
});

export default SalaryModule;