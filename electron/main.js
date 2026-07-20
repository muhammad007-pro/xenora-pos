const { app, BrowserWindow, Menu, ipcMain, dialog, shell, globalShortcut } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execFile } = require('child_process');

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
// Backend SERVERda ishlaydi va do'kondagi USB printerga (XP-58C) yeta OLMAYDI.
// Shu sabab chek shu yerda — Electron ichida — LOKAL printerga silent yuboriladi.
//
// ENCODING (krakozyabra) YECHIMI — PDF orqali (Chrome Ctrl+P AYNAN shu yo'l):
//   1. Chek HTML yashirin oynada render (did-finish-load kutiladi).
//   2. webContents.printToPDF() — Chromium PDF engine (Chrome "Save as PDF"). @page
//      size:58mm → PDF eni 58mm.
//   3. PDF'ni SumatraPDF (-print-to, silent) bilan XP-58C ga yuboramiz. SumatraPDF
//      PDF'ni RASTER qilib GDI orqali bosadi (Chrome kabi). PDF'da "matn baytlari"
//      yo'q → drayver CP437 talqin qilolmaydi → KRAKOZYABRA IMKONSIZ.
//   SumatraPDF bo'lmasa → webContents.print (silent) FALLBACK (regressiya yo'q).
const _delay = (ms) => new Promise((r) => setTimeout(r, ms));

// Bundle qilingan SumatraPDF (extraResources → resources/SumatraPDF.exe;
// dev muhitda electron/vendor/SumatraPDF.exe). Yo'q bo'lsa null → GDI fallback.
function _sumatraExe() {
    try {
        const packaged = path.join(process.resourcesPath || '', 'SumatraPDF.exe');
        if (fs.existsSync(packaged)) return packaged;
    } catch { /* ignore */ }
    try {
        const dev = path.join(__dirname, 'vendor', 'SumatraPDF.exe');
        if (fs.existsSync(dev)) return dev;
    } catch { /* ignore */ }
    return null;
}
function _runExe(exe, args) {
    return new Promise((resolve, reject) => {
        execFile(exe, args, { windowsHide: true }, (err) => (err ? reject(err) : resolve()));
    });
}
ipcMain.handle('print-receipt', async (_e, payload) => {
    const { html, deviceName } = payload || {};
    if (!html) return { ok: false, error: "Chek HTML bo'sh" };
    const dev = (deviceName && String(deviceName).trim()) ? String(deviceName).trim() : null;
    let win = null;
    let pdfPath = null;
    try {
        win = new BrowserWindow({
            show: false,
            width: 400, height: 800,
            webPreferences: { offscreen: false, sandbox: false, backgroundThrottling: false },
            backgroundColor: '#ffffff',
        });
        const wc = win.webContents;
        // Chek HTML TO'LIQ yuklansin: loadURL did-finish-load'da hal bo'ladi
        // (yuklanmasa reject → catch → ok:false). Shundan KEYIN PDF/print.
        await win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
        await _delay(300);   // render / shrift / QR

        // PDF sahifasini 58mm × (kontent balandligi) qilamiz — ortiqcha bo'sh qog'oz yo'q.
        let hmm = 200;
        try {
            const hpx = await wc.executeJavaScript('document.body.scrollHeight');
            if (hpx && hpx > 0) hmm = Math.ceil((hpx / 96) * 25.4) + 4;   // px→mm + kichik quyruq
        } catch { /* o'lchab bo'lmasa 200mm */ }
        try {
            await wc.executeJavaScript(
                "(function(){var s=document.createElement('style');s.textContent='@page{size:58mm "
                + hmm + "mm;margin:0}';document.head.appendChild(s);})()"
            );
        } catch { /* @page bermasak Letter bo'ladi — SumatraPDF fit tuzatadi */ }
        await _delay(60);

        const sumatra = _sumatraExe();
        if (sumatra) {
            // ── PDF yo'li (ISHONCHLI — Chrome kabi raster) ──
            const pdf = await wc.printToPDF({
                printBackground: true,
                preferCSSPageSize: true,
                margins: { top: 0, bottom: 0, left: 0, right: 0 },
            });
            pdfPath = path.join(os.tmpdir(), 'xenora_chek_' + Date.now() + '.pdf');
            fs.writeFileSync(pdfPath, Buffer.from(pdf));
            // SumatraPDF PDF'ni RASTER qilib GDI orqali bosadi (matn bayt yo'q → krakozyabra yo'q).
            const args = dev
                ? ['-print-to', dev, '-silent', '-print-settings', 'fit', pdfPath]
                : ['-print-to-default', '-silent', '-print-settings', 'fit', pdfPath];
            await _runExe(sumatra, args);
            return { ok: true, device: dev || '(OS default)', engine: 'pdf' };
        }

        // ── Fallback: SumatraPDF yo'q → webContents.print (silent GDI) ──
        const printOpts = { silent: true, margins: { marginType: 'none' }, printBackground: true };
        if (dev) printOpts.deviceName = dev;
        const result = await new Promise((resolve) => {
            wc.print(printOpts, (success, failureReason) =>
                resolve({
                    ok: !!success,
                    error: success ? null : (failureReason || 'Printer topilmadi yoki chop bekor qilindi'),
                    device: dev || '(OS default)',
                    engine: 'gdi-fallback',
                })
            );
        });
        return result;
    } catch (err) {
        console.error('print-receipt error', err);
        return { ok: false, error: err.message };
    } finally {
        if (win && !win.isDestroyed()) win.close();
        if (pdfPath) { try { fs.unlinkSync(pdfPath); } catch { /* ignore */ } }
    }
});

// Mavjud printerlar ro'yxati (sozlamada tanlash uchun)
ipcMain.handle('list-printers', async () => {
    try {
        if (!mainWindow) return [];
        const printers = await mainWindow.webContents.getPrintersAsync();
        return (printers || []).map((p) => ({
            name: p.name, displayName: p.displayName || p.name,
            isDefault: !!p.isDefault, status: p.status,
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
