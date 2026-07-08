const { app, BrowserWindow, Menu, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

// O'zgaruvchilar faqat bir marta e'lon qilinadi
let mainWindow = null;
let backendProcess = null;
let pythonPath = null;

// Python yo'lini topish
function findPython() {
    const possiblePaths = [
        'python',
        'python3',
        'py',
        process.env.LOCALAPPDATA + '\\Programs\\Python\\Python311\\python.exe',
        process.env.LOCALAPPDATA + '\\Programs\\Python\\Python312\\python.exe',
        'C:\\Python311\\python.exe',
        'C:\\Python312\\python.exe',
        '/usr/bin/python3',
        '/usr/local/bin/python3',
        '/opt/homebrew/bin/python3'
    ];
    
    for (const p of possiblePaths) {
        try {
            const result = require('child_process').execSync(`"${p}" --version`, { 
                stdio: 'pipe',
                timeout: 5000 
            });
            if (result.toString().includes('Python')) {
                console.log('Python found at:', p);
                return p;
            }
        } catch (e) {
            continue;
        }
    }
    return null;
}

// Backend serverni ishga tushirish
function startBackend() {
    pythonPath = findPython();
    
    if (!pythonPath) {
        dialog.showErrorBox('Python topilmadi', 
            'Python o\'rnatilmagan yoki PATH da mavjud emas.\n\n' +
            'Iltimos Python 3.11 yoki 3.12 versiyasini o\'rnating:\n' +
            'https://www.python.org/downloads/');
        return false;
    }
    
    const backendDir = path.join(process.resourcesPath, 'backend');
    
    if (!fs.existsSync(backendDir)) {
        // Development mode uchun
        const devBackendDir = path.join(__dirname, '..', 'backend');
        if (fs.existsSync(devBackendDir)) {
            return startBackendDev(devBackendDir);
        }
        
        dialog.showErrorBox('Backend topilmadi', 
            `Backend papkasi mavjud emas: ${backendDir}`);
        return false;
    }
    
    try {
        backendProcess = spawn(pythonPath, [
            '-m', 'uvicorn', 
            'main:app', 
            '--host', '127.0.0.1', 
            '--port', '8000',
            '--log-level', 'warning'
        ], {
            cwd: backendDir,
            stdio: ['pipe', 'pipe', 'pipe'],
            windowsHide: true
        });
        
        setupBackendProcess();
        return true;
    } catch (error) {
        console.error('Failed to start backend:', error);
        dialog.showErrorBox('Backend xatosi', 
            'Backend serverni ishga tushirib bo\'lmadi:\n' + error.message);
        return false;
    }
}

// Development mode uchun backend
function startBackendDev(backendDir) {
    try {
        backendProcess = spawn(pythonPath, [
            '-m', 'uvicorn', 
            'main:app', 
            '--host', '127.0.0.1', 
            '--port', '8000',
            '--reload'
        ], {
            cwd: backendDir,
            stdio: ['pipe', 'pipe', 'pipe'],
            windowsHide: false
        });
        
        setupBackendProcess();
        return true;
    } catch (error) {
        console.error('Failed to start backend:', error);
        return false;
    }
}

function setupBackendProcess() {
    backendProcess.stdout.on('data', (data) => {
        console.log(`Backend: ${data}`);
    });
    
    backendProcess.stderr.on('data', (data) => {
        console.error(`Backend Error: ${data}`);
    });
    
    backendProcess.on('error', (err) => {
        console.error('Backend process error:', err);
    });
    
    backendProcess.on('exit', (code) => {
        console.log('Backend process exited with code:', code);
        if (code !== 0 && mainWindow) {
            dialog.showErrorBox('Backend xatosi', 
                'Backend server kutilmaganda to\'xtadi. Iltimos dasturni qayta ishga tushiring.');
        }
    });
}

// ── Tenant zaxira — gzip baytlarни kompyuter diskiга (Documents/XENORA-Backup) ──
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
        // bytes — renderer'дан Uint8Array/ArrayBuffer (structured clone)
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

// Tiklash uchun: zaxira faylини tanlash va o'qish (renderer diskка to'g'ridan kira olmaydi)
ipcMain.handle('backup:pick', async () => {
    try {
        const res = await dialog.showOpenDialog(mainWindow, {
            title: 'Tiklash uchun zaxira faylини tanlang',
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

// Asosiy oyna yaratish
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1366,
        height: 768,
        minWidth: 1024,
        minHeight: 600,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        },
        icon: path.join(__dirname, 'assets', 'icon.ico'),
        frame: true,
        titleBarStyle: 'default',
        backgroundColor: '#1a1a2e',
        show: false
    });
    
    // Loading oynasini ko'rsatish
    mainWindow.loadFile(path.join(__dirname, 'loading.html'));
    
    // Oyna tayyor bo'lganda ko'rsatish
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });
    
    // Backend ga ulanishni tekshirish
    let retries = 0;
    const maxRetries = 60;
    
    const checkBackend = setInterval(() => {
        const http = require('http');
        const options = {
            hostname: '127.0.0.1',
            port: 8000,
            path: '/health',
            method: 'GET',
            timeout: 2000
        };
        
        const req = http.request(options, (res) => {
            if (res.statusCode === 200) {
                clearInterval(checkBackend);
                
                // Frontend ni yuklash
                let frontendPath;
                if (fs.existsSync(path.join(process.resourcesPath, 'frontend', 'index.html'))) {
                    frontendPath = path.join(process.resourcesPath, 'frontend', 'index.html');
                } else {
                    frontendPath = path.join(__dirname, '..', 'frontend', 'index.html');
                }
                mainWindow.loadFile(frontendPath);
            }
        });
        
        req.on('error', () => {
            retries++;
            
            if (retries >= maxRetries) {
                clearInterval(checkBackend);
                dialog.showErrorBox('Backend ulanmadi', 
                    'Backend server ishga tushmadi.\n\n' +
                    'Iltimos:\n' +
                    '1. Python 3.11+ o\'rnatilganligini tekshiring\n' +
                    '2. Kerakli kutubxonalar o\'rnatilganligini tekshiring\n' +
                    '3. Antivirus dasturlarni vaqtincha o\'chirib ko\'ring');
            }
        });
        
        req.setTimeout(2000, () => {
            req.destroy();
        });
        
        req.end();
    }, 1000);
    
    // Menu yaratish
    const template = [
        {
            label: 'Fayl',
            submenu: [
                {
                    label: 'Yangilash',
                    accelerator: 'F5',
                    click: () => mainWindow.reload()
                },
                { type: 'separator' },
                {
                    label: 'Chiqish',
                    accelerator: 'CmdOrCtrl+Q',
                    click: () => app.quit()
                }
            ]
        },
        {
            label: 'Ko\'rish',
            submenu: [
                { role: 'reload' },
                { role: 'forceReload' },
                { role: 'toggleDevTools' },
                { type: 'separator' },
                { role: 'resetZoom' },
                { role: 'zoomIn' },
                { role: 'zoomOut' },
                { type: 'separator' },
                { role: 'togglefullscreen' }
            ]
        },
        {
            label: 'Yordam',
            submenu: [
                {
                    label: 'Dastur haqida',
                    click: () => {
                        dialog.showMessageBox(mainWindow, {
                            type: 'info',
                            title: 'XENORA',
                            message: 'XENORA — Biznes boshqaruv tizimi',
                            detail: 'Versiya: 1.0.0\n\n© 2025 XENORA',
                            buttons: ['OK']
                        });
                    }
                }
            ]
        }
    ];
    
    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);
    
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// App tayyor
app.whenReady().then(() => {
    console.log('App starting...');
    
    const backendStarted = startBackend();
    
    if (!backendStarted) {
        app.quit();
        return;
    }
    
    createWindow();
    
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

// Barcha oynalar yopilganda
app.on('window-all-closed', () => {
    app.quit();
});

// App yopilganda backend ni to'xtatish
app.on('before-quit', () => {
    if (backendProcess) {
        try {
            if (process.platform === 'win32') {
                spawn('taskkill', ['/pid', backendProcess.pid, '/f', '/t']);
            } else {
                backendProcess.kill('SIGTERM');
            }
        } catch (e) {
            console.error('Failed to kill backend process:', e);
        }
    }
});