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

// ── Chek: LOKAL silent print (do'kon kompyuteridagi printerga) ──
// Backend SERVERda (146.190.225.168) ishlaydi va do'kondagi USB printerga (XP-58C)
// yeta OLMAYDI. Shu sabab chek shu yerda — Electron ichida, yashirin oynada
// yuklanib — LOKAL printerga silent (dialogsiz) yuboriladi.
//
// MUHIM: deviceName BO'SH bo'lsa `deviceName` kalitini BERMAYMIZ (bo'sh satr EMAS)
// — shundagina Electron OS STANDART printerini (XP-58C) ishlatadi. `deviceName:''`
// berish default'ga tushmaydi va chek hech qayerga ketadi (eski bug).
// pageSize — 58mm termal rolik (A4 emas); balandlik chek kontentiga qarab.
const PX_TO_MICRON = 264.58; // 1 CSS px ≈ 264.58 mikron (96dpi)
ipcMain.handle('print-receipt', async (_e, payload) => {
    const { html, deviceName } = payload || {};
    if (!html) return { ok: false, error: "Chek HTML bo'sh" };
    let win = null;
    try {
        win = new BrowserWindow({
            show: false,
            webPreferences: { offscreen: false, sandbox: true },
        });
        await win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
        // Layout + (bo'lsa) rasm/QR yuklanishiga ozgina vaqt
        await new Promise((r) => setTimeout(r, 300));

        // Chek kontenti balandligini o'lchab, sahifa balandligini shунга moslash
        // (termal rolik uzluksiz — ortiqcha bo'sh qog'oz chiqmasin).
        let pageHeight = 200000; // fallback ~200mm
        try {
            const h = await win.webContents.executeJavaScript('document.body.scrollHeight');
            if (h && h > 0) pageHeight = Math.round(h * PX_TO_MICRON) + 6000; // + kichik quyruq
        } catch { /* o'lchab bo'lmasa fallback */ }

        const printOpts = {
            silent: true,
            margins: { marginType: 'none' },
            printBackground: false,
            pageSize: { width: 58000, height: pageHeight }, // 58mm = 58000 mikron
        };
        // Faqat NOMLI printer bo'lsa deviceName beramiz; bo'sh → OS default (XP-58C).
        if (deviceName && String(deviceName).trim()) printOpts.deviceName = String(deviceName).trim();

        const result = await new Promise((resolve) => {
            win.webContents.print(printOpts, (success, failureReason) =>
                resolve({
                    ok: !!success,
                    error: success ? null : (failureReason || 'Printer topilmadi yoki chop bekor qilindi'),
                    device: printOpts.deviceName || '(OS default)',
                })
            );
        });
        return result;
    } catch (err) {
        console.error('print-receipt error', err);
        return { ok: false, error: err.message };
    } finally {
        if (win && !win.isDestroyed()) win.close();
    }
});

// Mavjud printerlar ro'yxati (sozlamada tanlash uchun)
ipcMain.handle('list-printers', async () => {
    try {
        if (!mainWindow) return [];
        const printers = await mainWindow.webContents.getPrintersAsync();
        return (printers || []).map((p) => ({
            name: p.name, displayName: p.displayName, isDefault: p.isDefault, status: p.status,
        }));
    } catch (err) {
        console.error('list-printers error', err);
        return [];
    }
});

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
        backgroundColor: '#070f1e',
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
