// Loader komponenti
class Loader {
    constructor() {
        this.loaders = new Map();
        this.init();
    }
    
    init() {
        this.createGlobalLoader();
        this.setupButtonLoaders();
    }
    
    createGlobalLoader() {
        const loader = document.createElement('div');
        loader.id = 'globalLoader';
        loader.className = 'global-loader';
        loader.innerHTML = `
            <div class="loader-content glass">
                <div class="spinner"></div>
                <p class="loader-text">Yuklanmoqda...</p>
            </div>
        `;
        loader.style.display = 'none';
        document.body.appendChild(loader);
    }
    
    setupButtonLoaders() {
        document.querySelectorAll('.btn').forEach(btn => {
            if (!btn.querySelector('.btn-loader')) {
                const loader = document.createElement('span');
                loader.className = 'btn-loader';
                loader.innerHTML = '<span class="spinner spinner-sm"></span>';
                loader.style.display = 'none';
                btn.appendChild(loader);
            }
        });
    }
    
    show(target = 'global', options = {}) {
        const {
            text = 'Yuklanmoqda...',
            overlay = true,
            fullscreen = false
        } = options;
        
        if (target === 'global') {
            const loader = document.getElementById('globalLoader');
            if (loader) {
                loader.querySelector('.loader-text').textContent = text;
                loader.style.display = 'flex';
                
                if (fullscreen) {
                    loader.classList.add('fullscreen');
                }
                
                if (overlay) {
                    this.showOverlay();
                }
            }
        } else if (typeof target === 'string') {
            const element = document.getElementById(target);
            if (element) {
                this.showElementLoader(element, text);
            }
        } else if (target instanceof HTMLElement) {
            this.showElementLoader(target, text);
        }
    }
    
    showElementLoader(element, text = 'Yuklanmoqda...') {
        const loaderId = `loader-${Date.now()}`;
        
        const loader = document.createElement('div');
        loader.id = loaderId;
        loader.className = 'element-loader';
        loader.innerHTML = `
            <div class="loader-wrapper">
                <div class="spinner"></div>
                <p>${text}</p>
            </div>
        `;
        
        element.style.position = 'relative';
        element.appendChild(loader);
        
        this.loaders.set(loaderId, { element, loader });
    }
    
    showButtonLoader(button) {
        if (typeof button === 'string') {
            button = document.getElementById(button);
        }
        
        if (button) {
            button.classList.add('loading');
            button.disabled = true;
            
            const text = button.querySelector('.btn-text');
            const loader = button.querySelector('.btn-loader');
            
            if (text) text.style.display = 'none';
            if (loader) loader.style.display = 'flex';
        }
    }
    
    showOverlay() {
        let overlay = document.getElementById('loaderOverlay');
        
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'loaderOverlay';
            overlay.className = 'loader-overlay';
            document.body.appendChild(overlay);
        }
        
        overlay.style.display = 'block';
    }
    
    hide(target = 'global') {
        if (target === 'global') {
            const loader = document.getElementById('globalLoader');
            if (loader) {
                loader.style.display = 'none';
                loader.classList.remove('fullscreen');
            }
            this.hideOverlay();
        } else if (typeof target === 'string') {
            const element = document.getElementById(target);
            if (element) {
                this.hideElementLoader(element);
            }
        } else if (target instanceof HTMLElement) {
            this.hideElementLoader(target);
        }
    }
    
    hideElementLoader(element) {
        const loader = element.querySelector('.element-loader');
        if (loader) {
            loader.remove();
        }
    }
    
    hideButtonLoader(button) {
        if (typeof button === 'string') {
            button = document.getElementById(button);
        }
        
        if (button) {
            button.classList.remove('loading');
            button.disabled = false;
            
            const text = button.querySelector('.btn-text');
            const loader = button.querySelector('.btn-loader');
            
            if (text) text.style.display = '';
            if (loader) loader.style.display = 'none';
        }
    }
    
    hideOverlay() {
        const overlay = document.getElementById('loaderOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }
    
    hideAll() {
        this.hide('global');
        
        document.querySelectorAll('.element-loader').forEach(el => el.remove());
        document.querySelectorAll('.btn.loading').forEach(btn => {
            this.hideButtonLoader(btn);
        });
        
        this.loaders.clear();
    }
    
    async wrap(promise, target = 'global', options = {}) {
        this.show(target, options);
        
        try {
            const result = await promise;
            return result;
        } finally {
            this.hide(target);
        }
    }
    
    createSkeleton(type = 'text', count = 1) {
        const container = document.createElement('div');
        container.className = 'skeleton-loader';
        
        for (let i = 0; i < count; i++) {
            const skeleton = document.createElement('div');
            skeleton.className = `skeleton skeleton-${type}`;
            container.appendChild(skeleton);
        }
        
        return container;
    }
    
    showSkeleton(container, type = 'card', count = 3) {
        if (typeof container === 'string') {
            container = document.getElementById(container);
        }
        
        if (container) {
            const originalContent = container.innerHTML;
            container.dataset.originalContent = originalContent;
            
            const skeleton = this.createSkeleton(type, count);
            container.innerHTML = '';
            container.appendChild(skeleton);
        }
    }
    
    hideSkeleton(container) {
        if (typeof container === 'string') {
            container = document.getElementById(container);
        }
        
        if (container && container.dataset.originalContent) {
            container.innerHTML = container.dataset.originalContent;
            delete container.dataset.originalContent;
        }
    }
}

// Singleton
const loader = new Loader();

// Global funksiyalar
window.showLoader = (target, options) => loader.show(target, options);
window.hideLoader = (target) => loader.hide(target);
window.showButtonLoader = (button) => loader.showButtonLoader(button);
window.hideButtonLoader = (button) => loader.hideButtonLoader(button);

export { Loader, loader };