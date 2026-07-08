import { API } from '../core/api.js';
import { showToast } from '../ui/toast.js';
import { Modal } from '../ui/modal.js';

class AttendanceModule {
    constructor() {
        this.api = new API();
        this.modal = new Modal('checkinModal');
        this.employees = [];
        this.cafes = [];
        this.attendance = [];
        this.selectedDate = new Date().toISOString().split('T')[0];
        
        this.init();
    }
    
    async init() {
        await this.loadData();
        this.setupEventListeners();
        this.renderAttendance();
        this.updateSummary();
    }
    
    setupEventListeners() {
        document.getElementById('checkInBtn').addEventListener('click', () => this.openCheckinModal());
        document.getElementById('confirmCheckin').addEventListener('click', () => this.confirmCheckin());
        document.getElementById('prevDay').addEventListener('click', () => this.changeDate(-1));
        document.getElementById('nextDay').addEventListener('click', () => this.changeDate(1));
        document.getElementById('todayBtn').addEventListener('click', () => this.setToday());
        document.getElementById('selectedDate').addEventListener('change', (e) => this.setDate(e.target.value));
        document.getElementById('searchInput').addEventListener('input', () => this.filterAttendance());
        document.getElementById('cafeFilter').addEventListener('change', () => this.filterAttendance());
        document.getElementById('statusFilter').addEventListener('change', () => this.filterAttendance());
        
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => this.modal.close());
        });
    }
    
    async loadData() {
        try {
            const [employeesRes, cafesRes, attendanceRes] = await Promise.all([
                this.api.get('/employees/list', { is_active: true }),
                this.api.get('/cafes/all'),
                this.api.get('/attendance', { date: this.selectedDate })
            ]);
            
            this.employees = employeesRes.data?.items || [];
            this.cafes = cafesRes.data || [];
            this.attendance = attendanceRes.data?.items || [];
            
            this.populateEmployeeSelect();
            this.populateCafeFilter();
        } catch (error) {
            console.error('Ma\'lumotlarni yuklashda xatolik:', error);
            showToast('Ma\'lumotlarni yuklashda xatolik', 'error');
        }
    }
    
    populateEmployeeSelect() {
        const select = document.getElementById('employeeSelect');
        const todayAttendedIds = this.attendance.map(a => a.employee_id);
        
        const availableEmployees = this.employees.filter(e => !todayAttendedIds.includes(e.id));
        
        select.innerHTML = '<option value="">Xodim tanlang</option>';
        availableEmployees.forEach(emp => {
            const option = document.createElement('option');
            option.value = emp.id;
            option.textContent = `${emp.full_name} - ${this.getPositionText(emp.position)}`;
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
    
    renderAttendance() {
        const tbody = document.getElementById('attendanceTableBody');
        const selectedDate = this.selectedDate;
        
        document.getElementById('selectedDate').value = selectedDate;
        
        if (this.attendance.length === 0) {
            const allEmployees = this.employees.filter(e => e.is_active);
            tbody.innerHTML = allEmployees.map(emp => this.createEmptyRow(emp)).join('');
        } else {
            tbody.innerHTML = this.attendance.map(att => this.createAttendanceRow(att)).join('');
        }
        
        tbody.querySelectorAll('.checkout-btn').forEach(btn => {
            btn.addEventListener('click', () => this.checkout(btn.dataset.id));
        });
    }
    
    createAttendanceRow(att) {
        const employee = this.employees.find(e => e.id === att.employee_id);
        const cafe = this.cafes.find(c => c.id === employee?.cafe_id);
        const canCheckout = !att.check_out && this.selectedDate === new Date().toISOString().split('T')[0];
        
        return `
            <tr>
                <td>
                    <div class="employee-info">
                        <div class="employee-avatar">${att.employee_name?.charAt(0) || '?'}</div>
                        <span>${att.employee_name || '-'}</span>
                    </div>
                </td>
                <td>${this.getPositionText(employee?.position)}</td>
                <td>${cafe?.name || '-'}</td>
                <td>${att.check_in ? new Date(att.check_in).toLocaleTimeString('uz-UZ') : '-'}</td>
                <td>${att.check_out ? new Date(att.check_out).toLocaleTimeString('uz-UZ') : '——'}</td>
                <td>${att.hours_worked ? att.hours_worked.toFixed(2) + ' soat' : '-'}</td>
                <td>
                    <span class="status-badge ${att.status}">${this.getStatusText(att.status)}</span>
                </td>
                <td>
                    ${canCheckout ? 
                        `<button class="checkout-btn" data-id="${att.id}">🚪 Chiqish</button>` : 
                        `<button class="checkout-btn" disabled>——</button>`
                    }
                </td>
            </tr>
        `;
    }
    
    createEmptyRow(emp) {
        const cafe = this.cafes.find(c => c.id === emp.cafe_id);
        const canCheckin = this.selectedDate === new Date().toISOString().split('T')[0];
        
        return `
            <tr>
                <td>
                    <div class="employee-info">
                        <div class="employee-avatar">${emp.full_name.charAt(0)}</div>
                        <span>${emp.full_name}</span>
                    </div>
                </td>
                <td>${this.getPositionText(emp.position)}</td>
                <td>${cafe?.name || '-'}</td>
                <td colspan="4" style="color: var(--text-secondary);">— Kelmagan —</td>
                <td>
                    <span class="status-badge absent">Kelmadi</span>
                </td>
                <td>
                    ${canCheckin ? 
                        `<button class="checkout-btn" onclick="document.getElementById('checkInBtn').click(); document.getElementById('employeeSelect').value='${emp.id}'">✅ Keldi</button>` : 
                        `<button class="checkout-btn" disabled>——</button>`
                    }
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
    
    getStatusText(status) {
        const statuses = {
            'present': '✅ Keldi',
            'absent': '❌ Kelmadi',
            'late': '⚠️ Kech qoldi',
            'early_leave': '🏃 Erta ketdi'
        };
        return statuses[status] || status;
    }
    
    updateSummary() {
        const totalActive = this.employees.filter(e => e.is_active).length;
        const present = this.attendance.filter(a => a.status === 'present').length;
        const absent = totalActive - this.attendance.length;
        const late = this.attendance.filter(a => a.status === 'late').length;
        
        document.getElementById('totalEmployees').textContent = totalActive;
        document.getElementById('presentCount').textContent = present;
        document.getElementById('absentCount').textContent = absent;
        document.getElementById('lateCount').textContent = late;
    }
    
    openCheckinModal() {
        this.populateEmployeeSelect();
        
        const hasAvailable = document.getElementById('employeeSelect').options.length > 1;
        if (!hasAvailable) {
            showToast('Bugun hamma xodimlar check-in qilgan', 'info');
            return;
        }
        
        this.modal.open();
    }
    
    async confirmCheckin() {
        const employeeId = document.getElementById('employeeSelect').value;
        const pin = document.getElementById('pinInput').value;
        const notes = document.getElementById('notesInput').value;
        
        if (!employeeId) {
            showToast('Xodim tanlang', 'warning');
            return;
        }
        
        try {
            await this.api.post('/attendance/check-in', {
                employee_id: parseInt(employeeId),
                pin_code: pin || null,
                notes: notes || null
            });
            
            showToast('Check-in muvaffaqiyatli', 'success');
            await this.loadData();
            this.renderAttendance();
            this.updateSummary();
            this.modal.close();
            document.getElementById('checkinForm').reset();
        } catch (error) {
            console.error('Check-in xatosi:', error);
            showToast(error.message || 'Check-in da xatolik', 'error');
        }
    }
    
    async checkout(attendanceId) {
        if (!confirm('Check-out qilishni xohlaysizmi?')) return;
        
        try {
            await this.api.post('/attendance/check-out', {
                attendance_id: parseInt(attendanceId)
            });
            
            showToast('Check-out muvaffaqiyatli', 'success');
            await this.loadData();
            this.renderAttendance();
            this.updateSummary();
        } catch (error) {
            console.error('Check-out xatosi:', error);
            showToast('Check-out da xatolik', 'error');
        }
    }
    
    changeDate(days) {
        const date = new Date(this.selectedDate);
        date.setDate(date.getDate() + days);
        this.selectedDate = date.toISOString().split('T')[0];
        this.loadData().then(() => {
            this.renderAttendance();
            this.updateSummary();
        });
    }
    
    setToday() {
        this.selectedDate = new Date().toISOString().split('T')[0];
        this.loadData().then(() => {
            this.renderAttendance();
            this.updateSummary();
        });
    }
    
    setDate(date) {
        this.selectedDate = date;
        this.loadData().then(() => {
            this.renderAttendance();
            this.updateSummary();
        });
    }
    
    filterAttendance() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const cafeId = document.getElementById('cafeFilter').value;
        const status = document.getElementById('statusFilter').value;
        
        let filtered = this.attendance.length > 0 ? this.attendance : 
            this.employees.filter(e => e.is_active).map(emp => ({ employee_id: emp.id, employee_name: emp.full_name, status: 'absent' }));
        
        if (searchTerm) {
            filtered = filtered.filter(a => 
                a.employee_name?.toLowerCase().includes(searchTerm)
            );
        }
        
        if (cafeId) {
            filtered = filtered.filter(a => {
                const emp = this.employees.find(e => e.id === a.employee_id);
                return emp?.cafe_id == cafeId;
            });
        }
        
        if (status) {
            filtered = filtered.filter(a => a.status === status);
        }
        
        const tbody = document.getElementById('attendanceTableBody');
        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 40px;">🔍 Ma'lumot topilmadi</td></tr>`;
        } else {
            tbody.innerHTML = filtered.map(item => {
                if (item.id) {
                    return this.createAttendanceRow(item);
                } else {
                    const emp = this.employees.find(e => e.id === item.employee_id);
                    return this.createEmptyRow(emp);
                }
            }).join('');
            
            tbody.querySelectorAll('.checkout-btn').forEach(btn => {
                if (!btn.disabled) {
                    btn.addEventListener('click', () => this.checkout(btn.dataset.id));
                }
            });
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new AttendanceModule();
});

export default AttendanceModule;