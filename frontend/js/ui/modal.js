// Modal Service - Modal oynalar uchun
class Modal {
    constructor(modalId) {
        this.modal = document.getElementById(modalId);
        this.overlay = this.modal?.querySelector('.modal-overlay');
        this.closeBtn = this.modal?.querySelector('.modal-close');
        this.isOpen = false;
        
        this.init();
    }
    
    init() {
        if (!this.modal) {
            console.warn(`Modal "${this.modal?.id}" topilmadi`);
            return;
        }
        
        // Overlay bosilganda yopish
        this.overlay?.addEventListener('click', () => this.close());
        
        // Yopish tugmasi
        this.closeBtn?.addEventListener('click', () => this.close());
        
        // ESC tugmasi
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) {
                this.close();
            }
        });
        
        // Modal-content ga click event yopilmasligi uchun
        const modalContent = this.modal.querySelector('.modal-content');
        modalContent?.addEventListener('click', (e) => e.stopPropagation());
    }
    
    open() {
        if (!this.modal) return;
        
        this.modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
        
        requestAnimationFrame(() => {
            this.modal.classList.add('active');
            this.overlay?.classList.add('active');
        });
        
        this.isOpen = true;
        
        // Event emit
        this.emit('open');
    }
    
    close() {
        if (!this.modal) return;
        
        this.modal.classList.remove('active');
        this.overlay?.classList.remove('active');
        document.body.style.overflow = '';
        
        setTimeout(() => {
            if (!this.isOpen) {
                this.modal.style.display = 'none';
            }
        }, 300);
        
        this.isOpen = false;
        
        // Event emit
        this.emit('close');
    }
    
    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    }
    
    // Modal ichidagi elementni olish
    getElement(selector) {
        return this.modal?.querySelector(selector);
    }
    
    // Modal ichidagi barcha elementlarni olish
    getElements(selector) {
        return this.modal?.querySelectorAll(selector);
    }
    
    // Title o'rnatish
    setTitle(title) {
        const titleElement = this.modal?.querySelector('.modal-title');
        if (titleElement) {
            titleElement.textContent = title;
        }
    }
    
    // Content o'rnatish
    setContent(content) {
        const body = this.modal?.querySelector('.modal-body');
        if (body) {
            if (typeof content === 'string') {
                body.innerHTML = content;
            } else {
                body.innerHTML = '';
                body.appendChild(content);
            }
        }
    }
    
    // Loading holatini ko'rsatish
    setLoading(loading) {
        const content = this.modal?.querySelector('.modal-content');
        if (loading) {
            content?.classList.add('loading');
        } else {
            content?.classList.remove('loading');
        }
    }
    
    // Event listener qo'shish
    on(event, callback) {
        if (!this._events) this._events = {};
        if (!this._events[event]) this._events[event] = [];
        this._events[event].push(callback);
    }
    
    // Event emit qilish
    emit(event, data) {
        if (this._events && this._events[event]) {
            this._events[event].forEach(cb => cb(data));
        }
    }
    
    // Modalni tozalash
    destroy() {
        if (this.modal) {
            this.close();
            this.modal.remove();
            this.modal = null;
        }
    }
}

export { Modal };