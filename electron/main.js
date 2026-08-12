const { app, BrowserWindow, Menu, ipcMain, dialog, shell, globalShortcut } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execFile } = require('child_process');
const { buildReceiptBytes, buildTestReceiptBytes, DRAWER_KICK } = require('./escpos-builder');
const { sendRawTcp } = require('./lan-socket');

// ── XENORA SaaS server manzili ──
// Backend SERVERDA ishlaydi (http://178.128.251.218). Electron o'z backendini
// ISHGA TUSHIRMAYDI — faqat local frontend'ni ko'rsatadi va shu serverga ulanadi.
// preload.js dagi XENORA_SERVER bilan BIR XIL bo'lishi shart.
const SERVER_URL = 'http://178.128.251.218';

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
// ══ MARKAZIY PRINT SERVIS (B1) ══════════════════════════════════════════════
// Bitta kirish nuqtasi: printDocument(payload). payload.printType ga qarab
// TRANSPORT tanlaydi. Har transport bir xil shakl: async send(html, opts) →
// { ok, error, ... }. Kelajakda yangi transport = shu obyektga yangi kalit;
// printDocument O'ZGARMAYDI. default "usb" → hozirgi SumatraPDF (regressiya yo'q).

// ── USB transport = AYNAN hozirgi SumatraPDF yo'li (render→PDF→SumatraPDF→GDI
//    fallback). Kod o'zgarmadi — faqat o'raldi. Chek shu orqali toza chiqadi. ──
const usbTransport = {
    async send(html, opts) {
        const dev = (opts && opts.deviceName && String(opts.deviceName).trim())
            ? String(opts.deviceName).trim() : null;
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
            console.error('usbTransport error', err);
            return { ok: false, error: err.message };
        } finally {
            if (win && !win.isDestroyed()) win.close();
            if (pdfPath) { try { fs.unlinkSync(pdfPath); } catch { /* ignore */ } }
        }
    },
};

// ── LAN transport (B2 — TO'LIQ) ────────────────────────────────────────────────
// Tarmoq (LAN/Wi-Fi) termal printerlari — RAW ESC/POS baytlarni TCP 9100
// (RAW/JetDirect) portida kutadi, PDF EMAS. USB (SumatraPDF/printToPDF) yo'liga
// UMUMAN TEGILMAYDI — bu ALOHIDA transport, faqat printType:'lan' tanlanganda
// chaqiriladi.
//
// Oqim: chek HTML (yashirin BrowserWindow'da) -> DOM'dan structured ma'lumot
// (do'kon nomi, qatorlar, jami/soliq/umumiy) o'qiladi -> escpos-builder.js
// (backend/services/escpos_service.py namunasi, JS'ga ko'chirilgan) ESC/POS
// baytga aylantiradi -> net.connect orqali RAW TCP yuboriladi.

// Chek HTML'dagi BARQAROR klasslar (.receipt-center/.receipt-table/.rt-row/
// .receipt-footer) — pos.js:renderReceiptData, receipt-print.js:buildReceipt58
// va admin.html reprint UCHALASI HAM shu bir xil klasslarni ishlatadi (chek
// dizayn tizimi). Shu sabab bu ekstraktsiya HTML matnini emas, DOM tuzilishini
// o'qiydi — chek HTML'i o'zgarsa ham (matn/rang) klasslar saqlansa ishlayveradi.
const _RECEIPT_EXTRACT_JS = `(function(){
  // <br> ni bo'shliqqa aylantiradi (aks holda "Croissant<br>pachka" ->
  // "Croissantpachka" bo'lib qo'shilib ketardi — mahsulot nomi + pachka/og'irlik
  // yorlig'i bir xil <td> ichida bo'lishi mumkin).
  function txt(el){
    if (!el) return '';
    var clone = el.cloneNode(true);
    clone.querySelectorAll('br').forEach(function(br){ br.replaceWith(' - '); });
    return clone.textContent.replace(/\\s+/g,' ').trim();
  }
  var center = document.querySelector('.receipt-center');
  var storeName = txt(center && center.querySelector('h4'));
  var addressLines = [];
  var addrP = center ? center.querySelector('p') : null;
  if (addrP) {
    addrP.innerHTML.split(/<br\\s*\\/?>/i).forEach(function(chunk){
      var d = document.createElement('div'); d.innerHTML = chunk;
      var t = (d.textContent||'').trim();
      if (t) addressLines.push(t);
    });
  }
  var meta = txt(center ? center.nextElementSibling : null);
  var rows = [];
  document.querySelectorAll('.receipt-table tbody tr').forEach(function(tr){
    var tds = tr.querySelectorAll('td');
    if (tds.length >= 3) rows.push({ name: txt(tds[0]), qty: txt(tds[1]), price: txt(tds[tds.length-1]) });
    else if (tds.length) rows.push({ name: txt(tds[0]), qty: '', price: '' });
  });
  var totals = [];
  document.querySelectorAll('.receipt-totals .rt-row').forEach(function(r){
    var spans = r.querySelectorAll('span');
    if (spans.length >= 2) totals.push({ label: txt(spans[0]), value: txt(spans[1]), bold: r.classList.contains('bold') });
  });
  var fiscalNumber = null;
  var fiscalMatch = document.body.textContent.match(/№\\s*([\\w-]+)/);
  if (document.body.textContent.indexOf('FISKAL') !== -1 && fiscalMatch) fiscalNumber = fiscalMatch[1];
  var footer = txt(document.querySelector('.receipt-footer'));
  return { storeName: storeName, addressLines: addressLines, meta: meta, rows: rows, totals: totals, footer: footer, fiscalNumber: fiscalNumber };
})()`;

// Chek HTML'ni yashirin oynada yuklab, structured ma'lumotni DOM'dan o'qiydi.
// USB yo'lidagi BILAN BIR XIL yashirin-oyna texnikasi (usbTransport) — faqat
// printToPDF o'rniga executeJavaScript bilan matn o'qiladi.
async function _extractReceiptStructure(html) {
    let win = null;
    try {
        win = new BrowserWindow({
            show: false, width: 400, height: 800,
            webPreferences: { offscreen: false, sandbox: false, backgroundThrottling: false },
        });
        await win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
        await _delay(150);
        const structured = await win.webContents.executeJavaScript(_RECEIPT_EXTRACT_JS);
        return structured || {};
    } finally {
        if (win && !win.isDestroyed()) win.close();
    }
}

const lanTransport = {
    async send(html, opts) {
        const o = opts || {};
        const ip = o.printerIp ? String(o.printerIp).trim() : '';
        const port = Number(o.printerPort || 0) || 9100;
        if (!ip) {
            return { ok: false, engine: 'lan-tcp',
                error: 'LAN IP kiritilmagan — sozlamalarda "Printer IP" ni to\'ldiring' };
        }
        let structured;
        try {
            structured = await _extractReceiptStructure(html);
        } catch (err) {
            console.error('lanTransport extract error', err);
            return { ok: false, engine: 'lan-tcp', error: "Chek ma'lumotini o'qib bo'lmadi: " + err.message };
        }
        const widthMm = Number(o.paperWidth) === 80 ? 80 : 58;
        let bytes;
        try {
            bytes = buildReceiptBytes(structured, widthMm, { openDrawer: !!o.openDrawer });
        } catch (err) {
            console.error('lanTransport build error', err);
            return { ok: false, engine: 'lan-tcp', error: 'Chek formatlashda xato: ' + err.message };
        }
        return sendRawTcp(ip, port, bytes, 5000);
    },
};

// ── QR transport — STUB (kelajak). ──
const qrTransport = {
    async send(_html, _opts) {
        return { ok: false, engine: 'qr-stub', error: 'QR print tez orada' };
    },
};

const _transports = { usb: usbTransport, lan: lanTransport, qr: qrTransport };

// ── MARKAZIY: printType ga qarab transport tanlab, send() chaqiradi ──
async function printDocument(payload) {
    const p = payload || {};
    if (!p.html) return { ok: false, error: "Print HTML bo'sh" };
    const type = (p.printType && String(p.printType).trim().toLowerCase()) || 'usb';
    const transport = _transports[type] || usbTransport;   // noma'lum tur → usb (regressiya yo'q)
    try {
        return await transport.send(p.html, p);
    } catch (err) {
        console.error('printDocument error', err);
        return { ok: false, error: err.message };
    }
}

// Yangi markaziy IPC — Z-hisobot / kunlik hisobot (B4) shu orqali o'tadi.
ipcMain.handle('print-document', (_e, payload) => printDocument(payload));
// Orqaga moslik: chek hozircha 'print-receipt' IPC ishlatadi → printDocument
// (printType bo'sh → 'usb' → AYNI SumatraPDF yo'li). Chek natijasi o'zgarmaydi.
ipcMain.handle('print-receipt', (_e, payload) =>
    printDocument({ ...(payload || {}), printType: (payload && payload.printType) || 'usb' }));

// ── Pul qutisi (cash drawer) — USB, printType'dan MUSTAQIL, ALOHIDA yo'l ──────
// LAN: drawer-kick bayti bevosita chek bayt oqimiga qo'shiladi (lanTransport
// ichida, yuqorida) — alohida chaqiruv shart emas.
// USB: chek SumatraPDF orqali PDF sifatida chop etiladi (usbTransport) — PDF
// ESC/POS buyruqlarini olib o'ta olmaydi (rasterlanadi), shuning uchun drawer
// signalini USB PRINTER NAVBATIGA (Windows spooler) RAW datatype bilan
// TO'G'RIDAN yuborish kerak — bu usbTransport'ga (SumatraPDF/chek chop etish
// yo'liga) UMUMAN TEGMAYDI, mutlaqo ALOHIDA, additive IPC.
//
// ⚠️ `printer` npm moduli (Windows RAW spooler yozish uchun — Node'ning o'zida
// bunday imkoniyat yo'q) ATAYIN package.json ga QO'SHILMADI — bu native C++
// addon (node-gyp/build tools kerak) va uni asosiy dependencies'ga qo'shish
// `npm install`/`postinstall` (electron-builder install-app-deps) ni BUTUN
// LOYIHA uchun buzishi mumkin (Eco Aroma build jarayoni xavf ostida qolmasin).
// Kerak bo'lsa QO'LDA: `cd electron && npm install printer` (ixtiyoriy, faqat
// USB pul qutisi uchun — LAN pul qutisi va USB/LAN chek chop etish bunga
// muhtoj EMAS). O'rnatilmagan bo'lsa tushunarli xato qaytaradi, CRASH EMAS.
async function openCashDrawerUsb(deviceName) {
    let printerLib;
    try {
        printerLib = require('printer');
    } catch (err) {
        return { ok: false, error: "Pul qutisi (USB) uchun 'printer' moduli o'rnatilmagan (npm install kerak)" };
    }
    return new Promise((resolve) => {
        try {
            printerLib.printDirect({
                data: DRAWER_KICK,
                printer: deviceName || undefined,
                type: 'RAW',
                success: () => resolve({ ok: true }),
                error: (err) => resolve({ ok: false, error: String((err && err.message) || err) }),
            });
        } catch (err) {
            resolve({ ok: false, error: err.message });
        }
    });
}
ipcMain.handle('open-cash-drawer', (_e, payload) => openCashDrawerUsb(payload && payload.deviceName));

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
