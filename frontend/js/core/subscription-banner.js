/**
 * Obuna ogohlantirish banneri (BOSQICH 4 — jim blok bo'lmasin).
 *
 * error-handler.js (30+ sahifa: POS, admin, ...) init paytida chaqiradi.
 * /cafes/my/subscription (enforcement'siz istisno endpoint) holatiga qarab:
 *   - expiring (7/3/1 kun qoldi) → yumshoq amber banner (yopib qo'ysa bo'ladi)
 *   - grace (muhlat davri)        → QATTIQ to'q banner (yopib bo'lmaydi)
 *   - blocked                     → bloklangan ekranga yo'naltiradi (proaktiv)
 *   - enforce=false / active      → hech narsa (dark deploy'da ko'rinmaydi)
 *
 * Himoya: har qanday xato → jim (sahifa hech qachon buzilmaydi).
 */
import { API_BASE } from './config.js';

const BANNER_ID = 'xenora-sub-banner';

function _dismissedKey(state, n) { return `sub_banner_dismiss_${state}_${n}`; }

function _render({ text, hard }) {
    if (document.getElementById(BANNER_ID)) return;
    const bar = document.createElement('div');
    bar.id = BANNER_ID;
    bar.setAttribute('role', 'status');
    Object.assign(bar.style, {
        position: 'fixed', top: '0', left: '0', right: '0', zIndex: '99997',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px',
        padding: '9px 40px 9px 16px', fontSize: '13.5px', fontWeight: '600',
        color: '#fff', textAlign: 'center',
        background: hard ? '#b91c1c' : '#b45309',
        boxShadow: '0 2px 8px rgba(0,0,0,.35)',
    });
    bar.innerHTML = `<span>${hard ? '&#9888;' : '&#9203;'}</span><span>${text}</span>`;

    if (!hard) {
        // Yumshoq banner — yopish tugmasi (bir sessiyaga).
        const x = document.createElement('button');
        x.textContent = '✕';
        Object.assign(x.style, {
            position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)',
            background: 'transparent', border: '0', color: '#fff', fontSize: '15px',
            cursor: 'pointer', lineHeight: '1', padding: '4px',
        });
        x.addEventListener('click', () => {
            try { sessionStorage.setItem(bar.dataset.dkey, '1'); } catch {}
            bar.remove();
        });
        bar.appendChild(x);
    }
    document.body.prepend(bar);
    return bar;
}

async function _check() {
    let tok = null;
    try { tok = localStorage.getItem('access_token'); } catch {}
    if (!tok) return;
    let d;
    try {
        const r = await fetch(`${API_BASE}/cafes/my/subscription`, {
            headers: { 'Authorization': `Bearer ${tok}`, 'Accept': 'application/json' },
        });
        if (!r.ok) return;               // 401/403/xato — jim (banner shart emas)
        d = await r.json();
    } catch { return; }                  // tarmoq yo'q — jim

    if (!d || !d.enforce) return;        // KILL-SWITCH o'chiq → hech qachon ko'rinmaydi

    // Bloklangan (muhlat ham tugagan) — bitta ekranga proaktiv yo'naltirish.
    if (d.blocked) {
        const path = location.pathname || '';
        if (!/subscription-blocked\.html$/.test(path) && !/login\.html$/.test(path)) {
            try { sessionStorage.setItem('sub_block_msg', d.message || ''); } catch {}
            location.href = '/shared/subscription-blocked.html';
        }
        return;
    }

    if (d.state === 'grace') {
        const n = d.grace_days_left != null ? d.grace_days_left : 0;
        _render({
            text: `Obuna muddati tugadi — to'lov uchun ${n} kun muhlat qoldi, aks holda hisob bloklanadi.`,
            hard: true,
        });
        return;
    }

    if (d.state === 'expiring') {
        const n = d.days_left != null ? d.days_left : 0;
        const dkey = _dismissedKey('expiring', n);
        let dismissed = false;
        try { dismissed = sessionStorage.getItem(dkey) === '1'; } catch {}
        if (dismissed) return;
        const bar = _render({ text: `Obuna ${n} kundan keyin tugaydi. Iltimos, yangilang.`, hard: false });
        if (bar) bar.dataset.dkey = dkey;
    }
}

export function initSubscriptionBanner() {
    // Sahifa yuklanib bo'lgach — asosiy oqimni bloklamasin.
    try {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => setTimeout(_check, 400));
        } else {
            setTimeout(_check, 400);
        }
    } catch {}
}
