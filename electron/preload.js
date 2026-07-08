const { contextBridge, ipcRenderer } = require('electron');

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
    
    // Backend boshqaruvi
    restartBackend: () => ipcRenderer.invoke('restart-backend'),

    // Tenant zaxira — gzip baytlarни Documents/XENORA-Backup/ ga saqlash
    saveBackup: (filename, bytes) => ipcRenderer.invoke('backup:save', { filename, bytes }),
    openBackupFolder: () => ipcRenderer.invoke('backup:open-folder'),
    pickBackupFile: () => ipcRenderer.invoke('backup:pick'),
    
    // Oyna boshqaruvi
    minimize: () => ipcRenderer.send('window-minimize'),
    maximize: () => ipcRenderer.send('window-maximize'),
    close: () => ipcRenderer.send('window-close'),
    
    // Platforma tekshirish
    isElectron: true
});

// DOM tayyor bo'lganda
window.addEventListener('DOMContentLoaded', () => {
    // Electron muhitida ekanligini belgilash
    document.body.classList.add('electron-app');
});