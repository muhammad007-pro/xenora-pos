// Toast Service - Bildirishnomalar uchun
class ToastService {
    constructor() {
        this.container = null;
        this.defaultDuration = 3000;
        this.position = 'top-right';
        this.maxToasts = 5;
        this.toasts = [];
        
        this.init();
    }
    
    init() {
        this.createContainer();
    }
    
    createContainer() {
        // Mavjud containerni tekshirish
        let container = document.getElementById('toastContainer');
        
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = `toast-container ${this.position}`;
            document.body.appendChild(container);
        }
        
        this.container = container;
    }
    
    show(message, type = 'info', duration = this.defaultDuration) {
        const toast = this.createToast(message, type);
        
        this.container.appendChild(toast);
        this.toasts.push(toast);
        
        // Maksimal sondan oshsa eng eskisini o'chirish
        if (this.toasts.length > this.maxToasts) {
            this.removeToast(this.toasts[0]);
        }
        
        // Avtomatik yopish
        if (duration > 0) {
            setTimeout(() => {
                this.removeToast(toast);
            }, duration);
        }
        
        // Animatsiya uchun
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
        
        return toast;
    }
    
    createToast(message, type) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icons = {
            success: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M20 6L9 17l-5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>`,
            error: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>`,
            warning: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M12 9v4M12 17h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                <path d="M12 2L2 20h20L12 2z" stroke="currentColor" stroke-width="2"/>
            </svg>`,
            info: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                <path d="M12 8v8M12 16h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>`
        };
        
        toast.innerHTML = `
            <div class="toast-icon">${icons[type] || icons.info}</div>
            <div class="toast-content">
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close" onclick="this.closest('.toast').remove()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
            </button>
            <div class="toast-progress" style="animation-duration: ${this.defaultDuration}ms"></div>
        `;
        
        return toast;
    }
    
    removeToast(toast) {
        toast.classList.remove('show');
        
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
            
            const index = this.toasts.indexOf(toast);
            if (index > -1) {
                this.toasts.splice(index, 1);
            }
        }, 300);
    }
    
    success(message, duration) {
        return this.show(message, 'success', duration);
    }
    
    error(message, duration) {
        return this.show(message, 'error', duration);
    }
    
    warning(message, duration) {
        return this.show(message, 'warning', duration);
    }
    
    info(message, duration) {
        return this.show(message, 'info', duration);
    }
    
    // Barcha toastlarni yopish
    clear() {
        this.toasts.forEach(toast => this.removeToast(toast));
    }
    
    // Pozitsiyani o'zgartirish
    setPosition(position) {
        this.position = position;
        this.container.className = `toast-container ${position}`;
    }
}

// Singleton instance
const toastService = new ToastService();

export const showToast = (message, type, duration) => {
    return toastService.show(message, type, duration);
};

export { ToastService };