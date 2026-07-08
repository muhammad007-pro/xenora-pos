/**
 * Global xato ushlash va offline/online banner moduli.
 *
 * Har bir sahifada bir marta init() chaqiriladi:
 *   import { initErrorHandler } from '../js/core/error-handler.js';
 *   initErrorHandler();
 */

// ── Offline banner ─────────────────────────────────────────────────────────────

function _createBanner() {
    if (document.getElementById('offline-banner')) return;

    const banner = document.createElement('div');
    banner.id = 'offline-banner';
    banner.setAttribute('role', 'status');
    banner.setAttribute('aria-live', 'polite');
    banner.innerHTML = `
      <span class="offline-icon">&#9888;</span>
      <span class="offline-text">Internet aloqasi yo'q — offline rejim</span>
    `;
    Object.assign(banner.style, {
        position:        'fixed',
        top:             '0',
        left:            '0',
        right:           '0',
        zIndex:          '99999',
        display:         'none',
        alignItems:      'center',
        justifyContent:  'center',
        gap:             '8px',
        padding:         '10px 16px',
        background:      '#b45309',
        color:           '#fff',
        fontSize:        '14px',
        fontWeight:      '500',
        boxShadow:       '0 2px 8px rgba(0,0,0,.35)',
        transition:      'opacity .3s',
    });
    document.body.prepend(banner);
    return banner;
}

function _showBanner() {
    const b = document.getElementById('offline-banner') || _createBanner();
    if (!b) return;
    b.style.display = 'flex';
    b.style.opacity = '0';
    requestAnimationFrame(() => { b.style.opacity = '1'; });
}

function _hideBanner() {
    const b = document.getElementById('offline-banner');
    if (!b) return;
    b.style.opacity = '0';
    setTimeout(() => { b.style.display = 'none'; }, 300);
}

function _initOfflineBanner() {
    _createBanner();
    if (!navigator.onLine) _showBanner();
    window.addEventListener('offline', _showBanner);
    window.addEventListener('online',  () => {
        _hideBanner();
        _showToast('Internet aloqasi tiklandi', 'success');
    });
}

// ── Toast ──────────────────────────────────────────────────────────────────────

function _showToast(message, type = 'error', duration = 4000) {
    // Agar loyihaning o'z toast tizimi mavjud bo'lsa — unga yo'naltiriladi
    if (window.__toast) {
        window.__toast(message, type);
        return;
    }

    let container = document.getElementById('_err-toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = '_err-toast-container';
        Object.assign(container.style, {
            position:      'fixed',
            bottom:        '24px',
            right:         '24px',
            zIndex:        '99998',
            display:       'flex',
            flexDirection: 'column',
            gap:           '8px',
        });
        document.body.appendChild(container);
    }

    const colors = {
        error:   '#dc2626',
        warning: '#d97706',
        success: '#16a34a',
        info:    '#2563eb',
    };

    const toast = document.createElement('div');
    Object.assign(toast.style, {
        background:   colors[type] || colors.error,
        color:        '#fff',
        padding:      '10px 16px',
        borderRadius: '8px',
        fontSize:     '14px',
        maxWidth:     '360px',
        boxShadow:    '0 4px 12px rgba(0,0,0,.25)',
        opacity:      '0',
        transform:    'translateY(8px)',
        transition:   'opacity .25s, transform .25s',
    });
    toast.textContent = message;
    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.style.opacity   = '1';
        toast.style.transform = 'translateY(0)';
    });

    setTimeout(() => {
        toast.style.opacity   = '0';
        toast.style.transform = 'translateY(8px)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ── Global xato ushlash ────────────────────────────────────────────────────────

function _onGlobalError(event) {
    const msg = event?.message || 'Noma\'lum xato';
    // Brauzer kengaytmalaridan kelgan xatolarni ignore qilamiz
    if (msg.includes('Extension') || msg.includes('chrome-extension')) return;
    console.error('[GlobalError]', msg, event);
    _showToast(`Xato: ${msg}`, 'error');
}

function _onUnhandledRejection(event) {
    const reason = event?.reason;
    let msg = 'Asinxron xato';
    if (reason instanceof Error)     msg = reason.message;
    else if (typeof reason === 'string') msg = reason;

    // 401 → login sahifasiga yo'naltirish (token muddati o'tgan)
    if (msg.includes('401') || msg.includes('Unauthorized')) {
        localStorage.removeItem('access_token');
        const loginPath = location.pathname.includes('/owner/')
            ? '../shared/login.html'
            : (location.pathname.includes('/app/') ? '../shared/login.html' : 'shared/login.html');
        location.href = loginPath;
        return;
    }

    // Network xatosi — offline bo'lsa banner ko'rsatilgan, qo'shimcha toast shart emas
    if (!navigator.onLine) return;

    console.error('[UnhandledRejection]', reason);
    _showToast(`Xato: ${msg}`, 'error');
}

// ── Eksport ────────────────────────────────────────────────────────────────────

/**
 * Bir marta chaqiriladi, odatda sahifa yuklanganda.
 * Offline banner, global xato handler va unhandledRejection ni yoqadi.
 */
export function initErrorHandler() {
    _initOfflineBanner();
    window.addEventListener('error',               _onGlobalError);
    window.addEventListener('unhandledrejection',  _onUnhandledRejection);
}

/** Dastur ichidan toast ko'rsatish uchun */
export function showToast(message, type = 'error', duration = 4000) {
    _showToast(message, type, duration);
}
