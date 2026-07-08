import { AuthService } from './core/auth.js';
import { showToast } from './ui/toast.js';
import { validateForm } from './utils/validator.js';
import { ThemeManager } from './core/theme.js';
class LoginPage {
    constructor() {
        this.form = document.getElementById('loginForm');
        this.authService = new AuthService();
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.checkAuth();
        this.setupPasswordToggle();
    }
    
    setupEventListeners() {
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));
    }
    
    setupPasswordToggle() {
        const toggleBtn = document.querySelector('.password-toggle');
        const passwordInput = document.getElementById('password');
        
        toggleBtn?.addEventListener('click', () => {
            const type = passwordInput.type === 'password' ? 'text' : 'password';
            passwordInput.type = type;
            
            // Toggle icon
            const icon = toggleBtn.querySelector('svg');
            if (type === 'text') {
                icon.innerHTML = `<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24M1 1l22 22" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`;
            } else {
                icon.innerHTML = `<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/>`;
            }
        });
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        
        const formData = new FormData(this.form);
        const data = Object.fromEntries(formData.entries());
        
        // Validation
        const errors = validateForm(data, {
            username: { required: true, minLength: 3 },
            password: { required: true, minLength: 6 }
        });
        
        if (Object.keys(errors).length > 0) {
            this.showErrors(errors);
            return;
        }
        
        // Show loading state
        this.setLoading(true);
        
        try {
            const response = await this.authService.login(data.username, data.password);
            
            if (response.success) {
                showToast('Muvaffaqiyatli kirdingiz!', 'success');
                
                // Redirect based on role
                setTimeout(() => {
                    const user = this.authService.getCurrentUser();
                    const roleName = user.role?.name || user.role || '';
                    if (roleName === 'admin') {
                        window.location.href = '../app/admin.html';
                    } else if (roleName === 'kitchen') {
                        window.location.href = '../app/kitchen.html';
                    } else {
                        window.location.href = '../app/pos.html';
                    }
                }, 1000);
            }
        } catch (error) {
            showToast(error.message || 'Kirishda xatolik', 'error');
            this.setLoading(false);
        }
    }
    
    setLoading(isLoading) {
        const submitBtn = this.form.querySelector('button[type="submit"]');
        if (isLoading) {
            submitBtn.classList.add('loading');
            submitBtn.disabled = true;
        } else {
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
        }
    }
    
    showErrors(errors) {
        Object.entries(errors).forEach(([field, message]) => {
            const formGroup = document.getElementById(field)?.closest('.form-group');
            if (formGroup) {
                formGroup.classList.add('error');
                let errorEl = formGroup.querySelector('.error-message');
                if (!errorEl) {
                    errorEl = document.createElement('div');
                    errorEl.className = 'error-message';
                    formGroup.appendChild(errorEl);
                }
                errorEl.textContent = message;
            }
        });
    }
    
    checkAuth() {
        const authService = new AuthService();
        if (authService.isAuthenticated()) {
            window.location.href = '../app/pos.html';
        }
    }
}

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    new LoginPage();
});

// Theme toggle
new ThemeManager();