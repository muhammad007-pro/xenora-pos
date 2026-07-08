/**
 * AuthGuard — Sahifa kirish nazorati (RBAC)
 *
 * Har bir himoyalangan sahifada import qilib, AuthGuard.check() chaqiriladi.
 * Ruxsatsiz foydalanuvchi 403 ekranini ko'radi, admin/menejer hammasiga kiradi.
 *
 * Ishlatilishi:
 *   import { AuthGuard } from '../js/core/auth-guard.js';
 *   AuthGuard.check();          // faqat kirish tekshirish
 *   AuthGuard.check('cashier'); // to'g'ridan-to'g'ri rol tekshirish
 */

// Sahifa nomi → ruxsat berilgan rollar (lower-case substring match)
// '*' → barcha rol
const PAGE_ROLES = {
  'pos':          ['*'],                                       // POS — barchaga
  'kitchen':      ['admin','manager','chef','oshpaz','kitchen'],
  'tables':       ['admin','manager','waiter','ofitsiant'],
  'reservations': ['admin','manager','resepshnist'],
  'appointments': ['admin','manager','master','usta','trainer','murabbiy','administrator'],
  'services':     ['admin','manager'],
  'customers':    ['admin','manager','cashier','kassir','pharmacist','farmatsevt'],
  'inventory':    ['admin','manager','omborchi','pharmacist','farmatsevt'],
  'recipes':      ['admin','manager','chef','oshpaz'],
  'analytics':    ['admin','manager'],
  'employees':    ['admin','manager'],
  'shift':        ['admin','manager','cashier','kassir'],
  'delivery':     ['admin','manager'],
  'loyalty':      ['admin','manager','cashier','kassir'],
  'barcode':      ['admin','manager','cashier','kassir','sotuvchi'],
  'expiry':       ['admin','manager','pharmacist','farmatsevt','omborchi'],
  'suppliers':    ['admin','manager'],
  'vehicles':     ['admin','manager','mechanic','mexanik','qabulchi'],
  'membership':   ['admin','manager'],
  'settings':     ['admin'],
  'admin':        ['admin','manager'],
};

// Rollar guruhlamasini sozlash — role.name → canonical group
function canonicalRole(roleName = '') {
  const n = (roleName || '').toLowerCase();
  if (n.includes('super') || n.includes('admin')) return 'admin';
  if (n.includes('manager') || n.includes('menej')) return 'manager';
  if (n.includes('cashier') || n.includes('kassir')) return 'cashier';
  if (n.includes('waiter') || n.includes('ofits')) return 'waiter';
  if (n.includes('chef') || n.includes('oshpaz')) return 'chef';
  return n; // raw — substring match handles the rest
}

function getCurrentUser() {
  try { return JSON.parse(localStorage.getItem('user') || 'null'); }
  catch { return null; }
}

function getPageName() {
  return location.pathname.split('/').pop().replace('.html', '').toLowerCase();
}

function canAccess(user, page) {
  if (!user) return false;
  if (user.is_superuser) return true;

  const allowed = PAGE_ROLES[page];
  if (!allowed) return true; // unlisted page — allow

  if (allowed.includes('*')) return true;

  const roleName = (user.role?.name || '').toLowerCase();
  const canon    = canonicalRole(roleName);

  return allowed.some(r => {
    const rL = r.toLowerCase();
    return canon === rL || roleName.includes(rL) || rL.includes(canon);
  });
}

function show403(page) {
  document.body.innerHTML = `
  <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;background:#0a0a0f;color:#f0f0f8;font-family:'Inter',sans-serif;gap:1.25rem;text-align:center;padding:2rem">
    <div style="font-size:4rem">🔒</div>
    <div style="font-size:1.5rem;font-weight:700;color:#d4af37">Kirish taqiqlangan</div>
    <div style="color:#9a9ab8;max-width:360px">
      Siz <strong>${page}</strong> sahifasiga kirishga ruxsat etilmagan.<br>
      Agar bu xato deb o'ylasangiz, adminstratorga murojaat qiling.
    </div>
    <div style="display:flex;gap:.75rem;margin-top:.75rem">
      <a href="javascript:history.back()" style="padding:.625rem 1.25rem;border-radius:.5rem;background:rgba(255,255,255,.08);color:#f0f0f8;text-decoration:none;font-size:.875rem;font-weight:500">← Orqaga</a>
      <a href="/app/pos.html" style="padding:.625rem 1.25rem;border-radius:.5rem;background:linear-gradient(135deg,#c9a84c,#e2c97a);color:#07070f;text-decoration:none;font-size:.875rem;font-weight:600">🏠 POS ga</a>
    </div>
  </div>`;
}

const AuthGuard = {
  check(requiredRole = null) {
    const user = getCurrentUser();
    const tk   = localStorage.getItem('access_token');

    // 1. Login check
    if (!tk || !user) {
      localStorage.removeItem('user');
      location.href = '../shared/login.html';
      return false;
    }

    // 2. Direct role override (e.g. AuthGuard.check('admin') / AuthGuard.check('superuser'))
    if (requiredRole) {
      const rn = (user.role?.name || '').toLowerCase();
      // 'superuser' — faqat is_superuser=true foydalanuvchilar
      const ok = requiredRole.toLowerCase() === 'superuser'
        ? user.is_superuser === true
        : user.is_superuser || rn.includes(requiredRole.toLowerCase());
      if (!ok) { show403(getPageName()); return false; }
    }

    // 3. Page-based RBAC check
    const page = getPageName();
    if (!canAccess(user, page)) {
      show403(page);
      return false;
    }

    return true;
  },

  /** Returns true/false without redirecting — use for conditional UI */
  can(page) {
    const user = getCurrentUser();
    return canAccess(user, page || getPageName());
  },

  /** Returns canonical role for current user */
  myRole() {
    const user = getCurrentUser();
    if (!user) return null;
    if (user.is_superuser) return 'admin';
    return canonicalRole(user.role?.name || '');
  },

  isAdmin()   { return ['admin'].includes(this.myRole()); },
  isManager() { return ['admin','manager'].includes(this.myRole()); },
};

export { AuthGuard };
