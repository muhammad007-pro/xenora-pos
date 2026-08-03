const { contextBridge, ipcRenderer } = require('electron');

// ── XENORA SaaS server manzili (Electron server rejimi) ──
// Frontend (config.js va inline sahifalar) window.XENORA_SERVER ni o'qib,
// API/WS ni to'g'ridan shu serverga yuboradi. main.js dagi SERVER_URL bilan
// BIR XIL bo'lishi shart (sandbox preload local fayl require qila olmaydi).
const XENORA_SERVER = 'http://146.190.225.168';
contextBridge.exposeInMainWorld('XENORA_SERVER', XENORA_SERVER);

// Xavfsiz API ko'prigi
contextBridge.exposeInMainWorld('electronAPI', {
    // App ma'lumotlari
    getVersion: () => ipcRenderer.invoke('get-app-version'),
    getPlatform: () => ipcRenderer.invoke('get-platform'),

    // Tashqi havolalar
    openExternal: (url) => ipcRenderer.invoke('open-external', url),

    // Fayl dialoglari
    showOpenDialog: (options) => ipcRenderer.invoke('show-open-dialog', options),
    showSaveDialog: (options) => ipcRenderer.invoke('show-save-dialog', options),

    // To'liq ekran (sensor monoblok uchun)
    toggleFullscreen: () => ipcRenderer.invoke('toggle-fullscreen'),
    isFullscreen: () => ipcRenderer.invoke('is-fullscreen'),

    // Tenant zaxira — gzip baytlarni Documents/XENORA-Backup/ ga saqlash
    saveBackup: (filename, bytes) => ipcRenderer.invoke('backup:save', { filename, bytes }),
    openBackupFolder: () => ipcRenderer.invoke('backup:open-folder'),
    pickBackupFile: () => ipcRenderer.invoke('backup:pick'),

    // Chek LOKAL silent print (do'kon kompyuteridagi printerga)
    printReceipt: (payload) => ipcRenderer.invoke('print-receipt', payload),
    // Markaziy print servis (B1) — payload.printType (usb/lan/qr) ga qarab transport.
    // Chek + Z-hisobot + kunlik hisobot shu yagona yo'ldan o'tadi.
    printDocument: (payload) => ipcRenderer.invoke('print-document', payload),
    listPrinters: () => ipcRenderer.invoke('list-printers'),
    // Pul qutisi (cash drawer) — USB, chek chop etish yo'lidan (printDocument)
    // MUSTAQIL. LAN uchun alohida chaqiruv shart emas — drawer signali chek
    // bayt oqimiga o'zi qo'shiladi (printDocument payload.openDrawer orqali).
    openCashDrawer: (deviceName) => ipcRenderer.invoke('open-cash-drawer', { deviceName }),

    // Oyna boshqaruvi
    minimize: () => ipcRenderer.send('window-minimize'),
    maximize: () => ipcRenderer.send('window-maximize'),
    close: () => ipcRenderer.send('window-close'),

    // Platforma tekshirish
    isElectron: true
});

// ── Sensor optimizatsiya + ekrandagi to'liq-ekran tugmasi ──
// Har bir sahifada (login, POS, admin, oshxona...) ishlaydi — preload universal.
window.addEventListener('DOMContentLoaded', () => {
    document.body.classList.add('electron-app');

    // Sensor CSS: matn tasodifan belgilanmasin, tap highlight yo'q, bounce yo'q.
    // Kiritish maydonlari (input/textarea) belgilanadigan qoladi.
    const style = document.createElement('style');
    style.textContent = `
      * { -webkit-tap-highlight-color: transparent; }
      html, body { -webkit-user-select: none; user-select: none;
                   -webkit-touch-callout: none; overscroll-behavior: contain; }
      input, textarea, select, [contenteditable="true"] {
                   -webkit-user-select: text; user-select: text; }
      #__xenora_fs:active { transform: scale(.92); }
    `;
    document.head.appendChild(style);

    // Ekrandagi to'liq-ekran toggle tugmasi (barmoq bilan bosiladi — klaviatura shart emas)
    const btn = document.createElement('button');
    btn.id = '__xenora_fs';
    btn.type = 'button';
    btn.setAttribute('aria-label', "To'liq ekran");
    btn.title = "To'liq ekran (F11)";
    btn.textContent = '⛶';
    Object.assign(btn.style, {
        position: 'fixed', bottom: '12px', left: '12px', zIndex: '2147483647',
        width: '46px', height: '46px', borderRadius: '13px',
        border: '1px solid rgba(226,201,122,.45)',
        background: 'rgba(12,12,24,.55)', color: '#e2c97a',
        fontSize: '22px', lineHeight: '44px', textAlign: 'center', padding: '0',
        cursor: 'pointer', opacity: '0.45', backdropFilter: 'blur(4px)',
        boxShadow: '0 2px 10px rgba(0,0,0,.35)', transition: 'opacity .15s, transform .1s',
        webkitUserSelect: 'none', userSelect: 'none', touchAction: 'manipulation'
    });
    const setGlyph = (fs) => { btn.textContent = fs ? '🗕' : '⛶'; btn.style.opacity = fs ? '0.45' : '0.45'; };
    btn.addEventListener('mouseenter', () => btn.style.opacity = '1');
    btn.addEventListener('mouseleave', () => btn.style.opacity = '0.45');
    // sensorда: bosishда to'liq ko'rinsin
    btn.addEventListener('touchstart', () => btn.style.opacity = '1', { passive: true });
    btn.addEventListener('click', async () => {
        const fs = await ipcRenderer.invoke('toggle-fullscreen');
        setGlyph(fs);
    });
    document.body.appendChild(btn);
    ipcRenderer.invoke('is-fullscreen').then(setGlyph).catch(() => {});
});
