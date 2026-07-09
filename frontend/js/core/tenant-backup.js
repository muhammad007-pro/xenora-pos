/**
 * Tenant zaxira — har do'kon FAQAT o'z ma'lumotini kompyuterга (Variant A).
 *
 *  - Backend: GET /backups/my-tenant → gzip JSON (faqat current_user.tenant_id).
 *  - Electron: kunда 2 marta (14:00, 22:00) avtomatik yuklab, Documents/XENORA-Backup/ ga saqlaydi.
 *    App yopiq bo'lsa — keyingi ochilganda o'sha kun o'tkazib yuborilgan slotни oladi (catch-up).
 *  - Faqat DO'KON ADMIN/MANAGER sessiyasида ishlaydi (backup butun do'kon ma'lumoti — maxfiy).
 *    Kassir/ofitsiant yoki super-admin — ishlamaydi (jim).
 *  - "Oxirgi zaxira" ko'rsatkич + "Hozir zaxira olish" tugma (admin uchun).
 *
 *  Mijoz aralashmaydi — fonда avtomatik. Token localStorage'дан (o'z tenant avtomatik).
 */

const IS_ELECTRON = !!(window.electronAPI && window.electronAPI.isElectron && window.electronAPI.saveBackup);

const _lp   = location.port;
const _dev  = ['5500', '5501', '3000', '4200', '8080'].includes(_lp) && ['localhost', '127.0.0.1'].includes(location.hostname);
const API   = _dev ? 'http://localhost:8000/api/v1' : ((window.XENORA_SERVER||'')+'/api/v1');

const SLOTS = [14 * 60, 22 * 60];   // 14:00 va 22:00 (daqiqада)
const LS_LAST = 'xenora_last_backup';   // {at, status, rows, filename, mode}

let _busy = false;
let _cooldownUntil = 0;

// ── Yordamchilar ────────────────────────────────────────────────────────────
function token() { return localStorage.getItem('access_token'); }

function currentUser() {
  try { return JSON.parse(localStorage.getItem('user') || 'null'); } catch { return null; }
}

// Faqat do'kon admin/manager (super-admin EMAS — u server backup ishlatadi)
function isStoreAdmin() {
  const u = currentUser();
  if (!u || u.is_superuser) return false;
  const r = (u.role?.name || u.role || '').toString().toLowerCase();
  return /admin|manager|menej|ega/.test(r);
}

function slotKey(slotMin) {
  const d = new Date();
  return `xbk_${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}_${slotMin}`;
}
function slotDone(slotMin)  { return localStorage.getItem(slotKey(slotMin)) === '1'; }
function markSlotDone(slotMin) { localStorage.setItem(slotKey(slotMin), '1'); }

function getLast() { try { return JSON.parse(localStorage.getItem(LS_LAST) || 'null'); } catch { return null; } }
function setLast(info) { localStorage.setItem(LS_LAST, JSON.stringify(info)); renderPanel(); }

// ── Asosiy: zaxira olish ─────────────────────────────────────────────────────
async function runBackup(mode = 'auto') {
  if (_busy) return false;
  if (!token()) return false;
  if (!isStoreAdmin()) return false;
  // Avtomatik — faqat Electron (brauzerда fonда diskка yozib bo'lmaydi). Qo'lда — hamma joyда.
  if (mode === 'auto' && !IS_ELECTRON) return false;

  _busy = true;
  setStatus('⏳ Zaxira olinmoqda...');
  try {
    const res = await fetch(API + '/backups/my-tenant', {
      headers: { 'Authorization': 'Bearer ' + token() },
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || ('HTTP ' + res.status));
    }
    const buf  = new Uint8Array(await res.arrayBuffer());
    const cd   = res.headers.get('content-disposition') || '';
    const m    = cd.match(/filename="?([^"]+)"?/);
    const name = (m && m[1]) || `backup_${Date.now()}.json.gz`;
    const rows = res.headers.get('x-backup-rows') || '?';

    let savedTo = null;
    if (IS_ELECTRON) {
      const r = await window.electronAPI.saveBackup(name, buf);
      if (!r || !r.ok) throw new Error((r && r.error) || 'Diskка saqlanmadi');
      savedTo = r.path;
    } else {
      // Brauzer: yuklab olish (qo'lда)
      const blob = new Blob([buf], { type: 'application/gzip' });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url; a.download = name; document.body.appendChild(a); a.click();
      a.remove(); URL.revokeObjectURL(url);
      savedTo = 'Yuklamalar (Downloads)';
    }

    setLast({ at: new Date().toISOString(), status: 'ok', rows, filename: name, path: savedTo, mode });
    setStatus('');
    if (mode === 'manual') notify(`Zaxira saqlandi ✓ (${rows} qator)`, 'ok');
    return true;
  } catch (err) {
    setLast({ at: new Date().toISOString(), status: 'error', error: err.message, mode });
    setStatus('');
    if (mode === 'manual') notify('Zaxira xatosi: ' + err.message, 'err');
    console.warn('[tenant-backup]', err);
    return false;
  } finally {
    _busy = false;
  }
}

// ── Rejalashtiruvchi (faqat Electron) ────────────────────────────────────────
async function checkSlots() {
  if (!IS_ELECTRON || !isStoreAdmin() || _busy || Date.now() < _cooldownUntil) return;
  const now = new Date();
  const cur = now.getHours() * 60 + now.getMinutes();
  for (const s of SLOTS) {
    if (cur >= s && !slotDone(s)) {           // vaqt o'tgan + bajarilmagan → catch-up
      const ok = await runBackup('auto');
      if (ok) markSlotDone(s);
      else _cooldownUntil = Date.now() + 10 * 60 * 1000;  // xato → 10 daqiqа kutib qayta urinamiz
      break;                                  // bir yurishда bitta slot
    }
  }
}

// ── UI: Sozlamalar → "Zaxira nusxa" bo'limидаги #xenoraBackupPanel'га quriladi ─
// (Suzuvchi widget YO'Q. Panel bo'lmagan sahifada — faqat fonда timer ishlaydi.)
function mountPanel() {
  const host = document.getElementById('xenoraBackupPanel');
  if (!host || host._xbkMounted || !isStoreAdmin()) return;
  host._xbkMounted = true;
  host.innerHTML = `
    <div id="xbkWhen" style="display:flex;align-items:center;gap:.5rem;font-size:.875rem;color:var(--text2,#9fcbb9);margin-bottom:1rem">
      <span style="font-size:1.15rem">🗄</span><span class="xbk-when-txt">Zaxira holati...</span>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:.75rem">
      <button class="btn btn-gold"    id="xbkNow">📥 Hozir zaxira olish</button>
      <button class="btn btn-outline" id="xbkRestore">↺ Zaxiradan tiklash</button>
      ${IS_ELECTRON ? '<button class="btn btn-outline" id="xbkOpen">📁 Zaxira papkasi</button>' : ''}
    </div>
    <div id="xbkStatus" style="margin-top:.75rem;font-size:.8125rem;min-height:1.1rem"></div>
  `;
  host.querySelector('#xbkNow').addEventListener('click', async (e) => {
    const b = e.currentTarget; b.disabled = true; await runBackup('manual'); b.disabled = false;
  });
  host.querySelector('#xbkRestore').addEventListener('click', async (e) => {
    const b = e.currentTarget; b.disabled = true; await restoreNow(); b.disabled = false;
  });
  const openBtn = host.querySelector('#xbkOpen');
  if (openBtn) openBtn.addEventListener('click', () => window.electronAPI.openBackupFolder?.());
  renderPanel();
}

function renderPanel() {
  const el = document.querySelector('#xbkWhen .xbk-when-txt');
  if (!el) return;
  const last = getLast();
  if (last && last.at) {
    const d = new Date(last.at);
    const s = d.toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    el.textContent = last.status === 'ok' ? `Oxirgi zaxira: ${s}` : `Oxirgi urinish (xato): ${s}`;
    el.style.color = last.status === 'ok' ? 'var(--text2,#9fcbb9)' : 'var(--danger,#f87171)';
  } else {
    el.textContent = 'Zaxira hali olinmagan';
  }
}

function setStatus(txt) { const e = document.getElementById('xbkStatus'); if (e) e.textContent = txt; }
function notify(txt, kind) {
  const e = document.getElementById('xbkStatus');
  if (e) {
    e.textContent = txt;
    e.style.color = kind === 'err' ? 'var(--danger,#f87171)' : 'var(--success,#34d399)';
    setTimeout(() => { if (e) e.textContent = ''; }, 5000);
  }
}

// ── TIKLASH (restore) — ENG NOZIK: fayl tanlash + ogohlantirish + yuklash ─────
async function pickBackupFile() {
  // Electron — Documents/XENORA-Backup дан tanlash (renderer diskка to'g'ridan kira olmaydi)
  if (IS_ELECTRON && window.electronAPI.pickBackupFile) {
    const r = await window.electronAPI.pickBackupFile();
    if (!r || !r.ok) return null;   // bekor yoki xato
    return { name: r.name, blob: new Blob([r.bytes], { type: 'application/gzip' }) };
  }
  // Brauzer — <input type=file>
  return new Promise((resolve) => {
    let inp = document.getElementById('xbkFileInput');
    if (!inp) {
      inp = document.createElement('input');
      inp.type = 'file'; inp.accept = '.gz,.json'; inp.id = 'xbkFileInput';
      inp.style.display = 'none'; document.body.appendChild(inp);
    }
    inp.value = '';
    inp.onchange = () => { const f = inp.files && inp.files[0]; resolve(f ? { name: f.name, blob: f } : null); };
    inp.click();
  });
}

function confirmRestore(name) {
  return new Promise((resolve) => {
    const ov = document.createElement('div');
    ov.innerHTML = `
      <style>
        #xbk-rov{position:fixed;inset:0;z-index:9700;background:rgba(3,17,12,.72);backdrop-filter:blur(5px);
          display:flex;align-items:center;justify-content:center;padding:1rem;
          font-family:-apple-system,Segoe UI,sans-serif}
        #xbk-rov .m{background:#0b2e23;border:1px solid rgba(239,68,68,.4);border-radius:16px;max-width:420px;
          width:100%;color:#ecf6ef;box-shadow:0 24px 60px rgba(0,0,0,.6);overflow:hidden}
        #xbk-rov .mh{padding:1rem 1.25rem;font-weight:800;font-size:1rem;color:#f59e0b;
          border-bottom:1px solid rgba(255,255,255,.08);display:flex;align-items:center;gap:.5rem}
        #xbk-rov .mb{padding:1.1rem 1.25rem;font-size:.86rem;line-height:1.55;color:#c9e0d5}
        #xbk-rov .mb b{color:#ebd297}
        #xbk-rov .mf{display:flex;gap:.6rem;padding:1rem 1.25rem;border-top:1px solid rgba(255,255,255,.08)}
        #xbk-rov button{flex:1;padding:.7rem;border-radius:10px;font-weight:700;font-size:.85rem;cursor:pointer;
          border:1px solid transparent;font-family:inherit}
        #xbk-rov .c{background:rgba(255,255,255,.06);color:#9fcbb9;border-color:rgba(255,255,255,.12)}
        #xbk-rov .o{background:#ef4444;color:#fff}
        #xbk-rov .o:hover{background:#dc2626}
      </style>
      <div class="m" id="xbk-rov">
        <div class="mh">⚠️ Ma'lumotni tiklash</div>
        <div class="mb">
          <b>${(name || '').replace(/[<>&]/g, '')}</b> zaxirasidан tiklamoqchisiz.<br><br>
          Bu amal <b>hozirgi ma'lumotни</b> (mahsulot, buyurtma, mijoz, ombor, sozlamалар...)
          shu zaxira bilan <b>ALMASHTIRADI</b>. Joriy loginlar, filial va obuna saqlanadi.<br><br>
          Xavfsizlik uchun tiklашdan oldin joriy holат avtomatik zaxiralanadi.
        </div>
        <div class="mf">
          <button class="c" id="xbkRC">Bekor</button>
          <button class="o" id="xbkRO">Ha, tiklash</button>
        </div>
      </div>`;
    ov.id = 'xbk-rov-wrap';
    document.body.appendChild(ov);
    const done = (v) => { ov.remove(); resolve(v); };
    ov.querySelector('#xbkRC').onclick = () => done(false);
    ov.querySelector('#xbkRO').onclick = () => done(true);
  });
}

async function restoreNow() {
  if (!isStoreAdmin() || !token()) return false;
  const picked = await pickBackupFile();
  if (!picked) return false;                 // bekor qilindi
  const yes = await confirmRestore(picked.name);
  if (!yes) return false;
  setStatus('⏳ Tiklanmoqda...');
  try {
    const fd = new FormData();
    fd.append('file', picked.blob, picked.name);
    const res = await fetch(API + '/backups/my-tenant/restore', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token() },   // Content-Type YO'Q (brauzer boundary qo'yadi)
      body: fd,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ('HTTP ' + res.status));
    const rows = (data.restored && data.restored.inserted_rows) || 0;
    notify(`Tiklandi ✓ (${rows} qator). Sahifa yangilanadi...`, 'ok');
    setTimeout(() => location.reload(), 2200);
    return true;
  } catch (err) {
    notify('Tiklash xatosi: ' + err.message, 'err');
    return false;
  }
}

// ── Tashqi API ───────────────────────────────────────────────────────────────
window.XenoraBackup = {
  runNow: () => runBackup('manual'),
  restore: () => restoreNow(),
  openFolder: () => window.electronAPI?.openBackupFolder?.(),
  last: getLast,
};

// ── Init ─────────────────────────────────────────────────────────────────────
function init() {
  if (!isStoreAdmin()) return;      // faqat do'kon admin/manager (RBAC)
  mountPanel();                     // faqat Sozlamалар (#xenoraBackupPanel bor) sahifada UI chiqadi
  if (IS_ELECTRON) {                // avtomatik kunlik timer — sahifadan qat'i nazar fonда
    checkSlots();                   // load'да catch-up (o'tkazib yuborilgan slot)
    setInterval(checkSlots, 60 * 1000);
  }
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
