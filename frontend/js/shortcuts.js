// Klaviatura qisqa yo'llari
class ShortcutsManager {
    constructor() {
        this.shortcuts = new Map();
        this.init();
    }
    
    init() {
        document.addEventListener('keydown', (e) => this.handleKeydown(e));
        this.registerDefaultShortcuts();
    }
    
    registerDefaultShortcuts() {
        // Umumiy qisqa yo'llar
        this.register('F1', () => this.showHelp(), 'Yordam');
        this.register('F5', () => location.reload(), 'Yangilash');
        this.register('Escape', () => this.closeModals(), 'Modal yopish');
        
        // Navigatsiya
        this.register('Alt+D', () => this.navigate('/'), 'Dashboard');
        this.register('Alt+P', () => this.navigate('/pos'), 'POS');
        this.register('Alt+K', () => this.navigate('/kitchen'), 'Oshxona');
        this.register('Alt+A', () => this.navigate('/admin'), 'Admin');
        this.register('Alt+R', () => this.navigate('/reports'), 'Hisobotlar');
        
        // POS qisqa yo'llari
        this.register('F2', () => this.trigger('open-table-modal'), 'Stol tanlash');
        this.register('F3', () => this.trigger('open-customer-modal'), 'Mijoz tanlash');
        this.register('F4', () => this.trigger('open-discount-modal'), 'Chegirma');
        this.register('F9', () => this.trigger('open-payment-modal'), 'To\'lov');
        this.register('F12', () => this.trigger('hold-order'), 'Saqlash');
        
        // Qidiruv
        this.register('Ctrl+K', () => this.focusSearch(), 'Qidirish');
        this.register('Ctrl+F', () => this.focusSearch(), 'Qidirish');
    }
    
    register(keys, callback, description = '') {
        const normalized = this.normalizeKeys(keys);
        this.shortcuts.set(normalized, { callback, description, keys });
    }
    
    unregister(keys) {
        const normalized = this.normalizeKeys(keys);
        this.shortcuts.delete(normalized);
    }
    
    normalizeKeys(keys) {
        return keys.toLowerCase()
            .replace(/\s+/g, '')
            .split('+')
            .sort()
            .join('+');
    }
    
    handleKeydown(e) {
        const keys = [];
        
        if (e.ctrlKey) keys.push('ctrl');
        if (e.altKey) keys.push('alt');
        if (e.shiftKey) keys.push('shift');
        if (e.metaKey) keys.push('cmd');
        
        if (!['Control', 'Alt', 'Shift', 'Meta'].includes(e.key)) {
            if (e.key === ' ') {
                keys.push('space');
            } else if (e.key.length === 1) {
                keys.push(e.key.toLowerCase());
            } else {
                keys.push(e.key.toLowerCase());
            }
        }
        
        if (keys.length === 0) return;
        
        const normalized = keys.sort().join('+');
        const shortcut = this.shortcuts.get(normalized);
        
        if (shortcut) {
            e.preventDefault();
            shortcut.callback();
        }
    }
    
    showHelp() {
        const help = document.createElement('div');
        help.className = 'shortcuts-help glass';
        help.innerHTML = `
            <h3>Klaviatura qisqa yo'llari</h3>
            <div class="shortcuts-list">
                ${Array.from(this.shortcuts.entries()).map(([_, s]) => `
                    <div class="shortcut-item">
                        <kbd>${s.keys}</kbd>
                        <span>${s.description}</span>
                    </div>
                `).join('')}
            </div>
            <button class="btn btn-primary close-help">Yopish</button>
        `;
        
        document.body.appendChild(help);
        
        help.querySelector('.close-help').addEventListener('click', () => {
            help.remove();
        });
        
        setTimeout(() => help.remove(), 10000);
    }
    
    navigate(path) {
        window.location.href = path;
    }
    
    trigger(action) {
        window.dispatchEvent(new CustomEvent('shortcut', { detail: { action } }));
    }
    
    focusSearch() {
        document.querySelector('input[type="search"]')?.focus();
    }
    
    closeModals() {
        document.querySelectorAll('.modal.active').forEach(modal => {
            modal.classList.remove('active');
        });
    }
    
    getShortcutsList() {
        return Array.from(this.shortcuts.values());
    }
}

const shortcuts = new ShortcutsManager();
export default shortcuts;