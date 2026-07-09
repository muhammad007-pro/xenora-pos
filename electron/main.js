const { app, BrowserWindow, Menu, ipcMain, dialog, shell, globalShortcut } = require('electron');
const path = require('path');
const fs = require('fs');

// ── XENORA SaaS server manzili ──
// Backend SERVERDA ishlaydi (http://146.190.225.168). Electron o'z backendini
// ISHGA TUSHIRMAYDI — faqat local frontend'ni ko'rsatadi va shu serverga ulanadi.
// preload.js dagi XENORA_SERVER bilan BIR XIL bo'lishi shart.
const SERVER_URL = 'http://146.190.225.168';

let mainWindow = null;

// ── Tenant zaxira — gzip baytlarni kompyuter diskiga (Documents/XENORA-Backup) ──
function backupDir() {
    const dir = path.join(app.getPath('documents'), 'XENORA-Backup');
    fs.mkdirSync(dir, { recursive: true });
    return dir;
}

ipcMain.handle('backup:save', async (_e, payload) => {
    try {
        const { filename, bytes } = payload || {};
        const dir  = backupDir();
        // Fayl nomini xavfsizlash (path traversal / noto'g'ri belgilar)
        const safe = String(filename || `backup_${Date.now()}.json.gz`).replace(/[^a-zA-Z0-9._-]/g, '_');
        const full = path.join(dir, safe);
        // bytes — renderer'dan Uint8Array/ArrayBuffer (structured clone)
        fs.writeFileSync(full, Buffer.from(bytes));
        return { ok: true, path: full };
    } catch (err) {
        console.error('backup:save error', err);
        return { ok: false, error: err.message };
    }
});

ipcMain.handle('backup:open-folder', async () => {
    try {
        const dir = backupDir();
        await shell.openPath(dir);
        return { ok: true, path: dir };
    } catch (err) {
        return { ok: false, error: err.message };
    }
});

// Tiklash uchun: zaxira faylini tanlash va o'qish (renderer diskka to'g'ridan kira olmaydi)
ipcMain.handle('backup:pick', async () => {
    try {
        const res = await dialog.showOpenDialog(mainWindow, {
            title: 'Tiklash uchun zaxira faylini tanlang',
            defaultPath: backupDir(),
            properties: ['openFile'],
            filters: [{ name: 'XENORA zaxira', extensions: ['gz', 'json'] }],
        });
        if (res.canceled || !res.filePaths.length) return { ok: false, canceled: true };
        const fp = res.filePaths[0];
        const bytes = fs.readFileSync(fp);
        return { ok: true, name: path.basename(fp), bytes: new Uint8Array(bytes) };
    } catch (err) {
        return { ok: false, error: err.message };
    }
});

// ── To'liq ekran toggle (sensor monoblok — ekrandagi tugma orqali, klaviatura shart emas) ──
ipcMain.handle('toggle-fullscreen', () => {
    if (!mainWindow) return false;
    const next = !mainWindow.isFullScreen();
    mainWindow.setFullScreen(next);
    return next; // yangi holat (true = to'liq ekran)
});
ipcMain.handle('is-fullscreen', () => (mainWindow ? mainWindow.isFullScreen() : false));

// Kirish nuqtasi — TO'G'RIDAN login sahifasi (landing/index.html chetlab o'tiladi).
// login.html allaqachon: token bo'lsa avtomatik app'ga (rol bo'yicha) yo'naltiradi.
function resolveFrontend() {
    const packaged = path.join(process.resourcesPath, 'frontend', 'shared', 'login.html');
    if (fs.existsSync(packaged)) return packaged;
    return path.join(__dirname, '..', 'frontend', 'shared', 'login.html');
}

// Serverga ulanishni tekshirish (health). Ulansa yoki urinishlar tugasa —
// baribir local frontend yuklanadi (offline rejim: IndexedDB + sync navbat).
function waitForServerThenLoad() {
    const { URL } = require('url');
    const u = new URL(SERVER_URL);
    const httpMod = u.protocol === 'https:' ? require('https') : require('http');
    const port = u.port || (u.protocol === 'https:' ? 443 : 80);

    let retries = 0;
    const maxRetries = 12; // ~12s kutadi, keyin offline rejimda ochadi
    let loaded = false;

    const loadFrontend = (online) => {
        if (loaded) return;
        loaded = true;
        clearInterval(timer);
        console.log(online ? 'Server online — frontend yuklanmoqda' : 'Server javob bermadi — offline rejim');
        mainWindow.loadFile(resolveFrontend());
    };

    const timer = setInterval(() => {
        const req = httpMod.request(
            { hostname: u.hostname, port, path: '/health', method: 'GET', timeout: 3000 },
            (res) => {
                if (res.statusCode === 200) loadFrontend(true);
                res.resume();
            }
        );
        req.on('error', () => {
            retries++;
            if (retries >= maxRetries) loadFrontend(false);
        });
        req.on('timeout', () => req.destroy());
        req.end();
    }, 1000);
}

// Asosiy oyna yaratish
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1366,
        height: 768,
        minWidth: 1024,
        minHeight: 600,
        // Sensor monoblok: to'liq ekran boshlanadi; chiqish ekrandagi tugma yoki F11.
        fullscreen: true,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            // file:// frontend remote serverga (http://IP) so'rov yuboradi.
            // Desktop app + remote API uchun CORS/SOP ni o'chiramiz (faqat o'z
            // ishonchli local frontend'imiz yuklanadi, tashqi kontent emas).
            webSecurity: false,
            preload: path.join(__dirname, 'preload.js')
        },
        icon: path.join(__dirname, 'assets', 'icon.ico'),
        frame: true,
        autoHideMenuBar: true,   // menyu paneli umuman ko'rinmasin
        titleBarStyle: 'default',
        backgroundColor: '#1a1a2e',
        show: false
    });
    // Menyu (File/Ko'rish/Yordam) BUTUNLAY yo'q — kassa dasturi, toza
    mainWindow.setMenuBarVisibility(false);

    // Loading oynasini ko'rsatish
    mainWindow.loadFile(path.join(__dirname, 'loading.html'));

    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });

    // Server health — keyin frontend
    waitForServerThenLoad();

    mainWindow.on('closed', () => { mainWindow = null; });
}

app.whenReady().then(() => {
    console.log('XENORA server rejimida ishga tushmoqda... Server:', SERVER_URL);

    // Ilova menyusini BUTUNLAY olib tashlash (hech qanday menyu bar bo'lmasin)
    Menu.setApplicationMenu(null);

    createWindow();

    // F11 = to'liq ekran toggle (klaviatura uchun; menyu yo'q, shuning uchun globalShortcut)
    globalShortcut.register('F11', () => {
        if (mainWindow) mainWindow.setFullScreen(!mainWindow.isFullScreen());
    });

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
    app.quit();
});
