// Dropdown komponenti
class Dropdown {
    constructor(element, options = {}) {
        this.element = element;
        this.options = {
            placement: 'bottom-start',
            trigger: 'click',
            closeOnSelect: true,
            closeOnClickOutside: true,
            ...options
        };
        
        this.isOpen = false;
        this.trigger = element.querySelector('.dropdown-trigger') || element;
        this.menu = element.querySelector('.dropdown-menu');
        
        this.init();
    }
    
    init() {
        if (!this.menu) {
            this.createMenu();
        }
        
        this.setupEventListeners();
        this.menu.style.position = 'absolute';
        this.menu.style.display = 'none';
    }
    
    createMenu() {
        this.menu = document.createElement('div');
        this.menu.className = 'dropdown-menu glass';
        
        const items = this.element.querySelectorAll('[data-dropdown-item]');
        items.forEach(item => {
            this.menu.appendChild(item.cloneNode(true));
        });
        
        this.element.appendChild(this.menu);
    }
    
    setupEventListeners() {
        if (this.options.trigger === 'click') {
            this.trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggle();
            });
        } else if (this.options.trigger === 'hover') {
            this.trigger.addEventListener('mouseenter', () => this.open());
            this.trigger.addEventListener('mouseleave', () => this.close());
        }
        
        if (this.options.closeOnClickOutside) {
            document.addEventListener('click', (e) => {
                if (this.isOpen && !this.element.contains(e.target)) {
                    this.close();
                }
            });
        }
        
        if (this.options.closeOnSelect) {
            this.menu.addEventListener('click', (e) => {
                const item = e.target.closest('[data-value]');
                if (item) {
                    this.selectItem(item);
                    this.close();
                }
            });
        }
        
        window.addEventListener('resize', () => {
            if (this.isOpen) {
                this.updatePosition();
            }
        });
        
        window.addEventListener('scroll', () => {
            if (this.isOpen) {
                this.updatePosition();
            }
        }, true);
    }
    
    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    }
    
    open() {
        this.menu.style.display = 'block';
        this.updatePosition();
        this.isOpen = true;
        this.element.classList.add('dropdown-open');
        
        this.emit('open');
    }
    
    close() {
        this.menu.style.display = 'none';
        this.isOpen = false;
        this.element.classList.remove('dropdown-open');
        
        this.emit('close');
    }
    
    updatePosition() {
        const triggerRect = this.trigger.getBoundingClientRect();
        const menuRect = this.menu.getBoundingClientRect();
        
        let top, left;
        
        switch(this.options.placement) {
            case 'bottom-start':
                top = triggerRect.bottom + 4;
                left = triggerRect.left;
                break;
            case 'bottom-end':
                top = triggerRect.bottom + 4;
                left = triggerRect.right - menuRect.width;
                break;
            case 'top-start':
                top = triggerRect.top - menuRect.height - 4;
                left = triggerRect.left;
                break;
            case 'top-end':
                top = triggerRect.top - menuRect.height - 4;
                left = triggerRect.right - menuRect.width;
                break;
            default:
                top = triggerRect.bottom + 4;
                left = triggerRect.left;
        }
        
        // Ekran chegarasini tekshirish
        if (left + menuRect.width > window.innerWidth) {
            left = window.innerWidth - menuRect.width - 8;
        }
        if (left < 8) {
            left = 8;
        }
        if (top + menuRect.height > window.innerHeight) {
            top = triggerRect.top - menuRect.height - 4;
        }
        
        this.menu.style.top = top + 'px';
        this.menu.style.left = left + 'px';
    }
    
    selectItem(item) {
        const value = item.dataset.value;
        const label = item.textContent;
        
        const valueInput = this.element.querySelector('input[type="hidden"]');
        if (valueInput) {
            valueInput.value = value;
        }
        
        const labelElement = this.trigger.querySelector('.dropdown-label');
        if (labelElement) {
            labelElement.textContent = label;
        }
        
        this.emit('select', { value, label, item });
    }
    
    getValue() {
        const valueInput = this.element.querySelector('input[type="hidden"]');
        return valueInput ? valueInput.value : null;
    }
    
    setValue(value) {
        const item = this.menu.querySelector(`[data-value="${value}"]`);
        if (item) {
            this.selectItem(item);
        }
    }
    
    addItem(label, value) {
        const item = document.createElement('div');
        item.className = 'dropdown-item';
        item.dataset.value = value;
        item.textContent = label;
        this.menu.appendChild(item);
    }
    
    removeItem(value) {
        const item = this.menu.querySelector(`[data-value="${value}"]`);
        if (item) {
            item.remove();
        }
    }
    
    clearItems() {
        this.menu.innerHTML = '';
    }
    
    on(event, callback) {
        if (!this._events) this._events = {};
        if (!this._events[event]) this._events[event] = [];
        this._events[event].push(callback);
    }
    
    emit(event, data) {
        if (this._events && this._events[event]) {
            this._events[event].forEach(cb => cb(data));
        }
    }
    
    destroy() {
        this.close();
        this.trigger.removeEventListener('click', this.toggle);
        document.removeEventListener('click', this.close);
        window.removeEventListener('resize', this.updatePosition);
    }
}

// Dropdown ni avtomatik ishga tushirish
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-dropdown]').forEach(el => {
        const options = {
            placement: el.dataset.placement || 'bottom-start',
            trigger: el.dataset.trigger || 'click'
        };
        new Dropdown(el, options);
    });
});

export { Dropdown };