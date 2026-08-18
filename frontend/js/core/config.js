/**
 * Frontend konfiguratsiyasi
 *
 * Electron (server rejimi):        window.XENORA_SERVER → http://IP/api/v1
 * Live Server (5500/3000/...):     absolute http://localhost:8000/api/v1
 * Docker local (localhost:80):     relative /api/v1 (nginx proksi)
 * Production (real domain):        relative /api/v1 (nginx proksi)
 *
 * ═══ TUZATISH (mijozda topildi — Fazza Parfum, v1.9.1) ═══
 * Admin panelidagi "Firmalar" bo'limi IFRAME orqali ochiladi
 * (admin.html:2073 → suppliers.html?embed=1). Electron'da `preload.js`
 * SUKUT BO'YICHA faqat ASOSIY freymda ishlaydi, ya'ni iframe ichida
 * `window.XENORA_SERVER` UNDEFINED bo'lardi.
 *
 * Natijada iframe `file://` ni "dev" deb hisoblab, so'rovlarni
 * `http://localhost:8000` ga yuborardi — do'konchining kompyuterida u yerda
 * hech narsa yo'q. Har amal "Server bilan aloqa yo'q" bilan tugardi, holbuki
 * asosiy oynadagi hamma narsa (POS, nasiya) ishlayotgan edi.
 *
 * Ikki qatlamli yechim:
 *   A) `XENORA_SERVER` topilmasa — OTA/YUQORI freymdan olinadi (iframe holati)
 *   C) `file://` uchun `localhost:8000` ga JIMGINA TUSHISH OLIB TASHLANDI —
 *      aynan shu "taxmin" xatoni yaratgan va uni yashirgan edi. Endi manzil
 *      noma'lum bo'lsa KONSOLGA ANIQ xato yoziladi.
 * Uchinchi qatlam electron/main.js da: `nodeIntegrationInSubFrames: true`.
 */

const _proto = window.location.protocol;
const _host  = window.location.host;
const _port  = window.location.port;

// file:// protokoli = bevosita HTML fayl ochish (Electron paketidagi frontend)
const _isFile = _proto === 'file:';

// Live Server yoki boshqa alohida dev server (port 5500, 3000, 4200, 8080...)
// http://localhost:5500, http://127.0.0.1:3000 va h.k. — HAQIQIY dev holati.
const _devServerPorts = ['5500', '5501', '3000', '4200', '8080', '8081'];
const _isLiveServer = _devServerPorts.includes(_port)
    && ['localhost', '127.0.0.1'].includes(window.location.hostname);

/**
 * Electron server manzilini topish.
 * 1) shu freymda (asosiy oyna — preload shu yerda ishlaydi)
 * 2) ota freymda (iframe: preload subframe'da ishlamagan bo'lishi mumkin)
 * 3) eng yuqori freymda (ichma-ich iframe)
 * try/catch — cross-origin ota freymda o'qish SecurityError beradi; bunday
 * holatda shunchaki topilmadi deb hisoblaymiz (jimgina yiqilmaymiz).
 */
function _findServer() {
  if (typeof window === 'undefined') return null;
  if (window.XENORA_SERVER) return window.XENORA_SERVER;
  for (const frame of ['parent', 'top']) {
    try {
      const w = window[frame];
      if (w && w !== window && w.XENORA_SERVER) return w.XENORA_SERVER;
    } catch { /* cross-origin — o'qib bo'lmaydi */ }
  }
  return null;
}

const _xenoraServer = _findServer();

// Manzil noma'lum va sahifa file:// da ochilgan — bu KUTILMAGAN holat
// (Electron'da preload har doim XENORA_SERVER berishi kerak). Ilgari bu yerda
// jimgina `localhost:8000` ishlatilardi va xato "server o'chgan" bo'lib
// ko'rinardi. Endi sabab konsolda ANIQ yoziladi.
if (!_xenoraServer && _isFile) {
  console.error(
    '[XENORA config] XENORA_SERVER topilmadi (file:// sahifa, iframe bo\'lishi mumkin). ' +
    'API manzili aniqlanmadi — so\'rovlar ishlamaydi. preload.js barcha freymlarda ' +
    'ishlayotganini tekshiring (nodeIntegrationInSubFrames).'
  );
}

export const API_BASE = _xenoraServer
  ? `${_xenoraServer}/api/v1`
  : (_isLiveServer ? 'http://localhost:8000/api/v1' : '/api/v1');

export const WS_BASE = _xenoraServer
  ? _xenoraServer.replace(/^http/, 'ws')
  : (_isLiveServer
      ? `${_proto === 'https:' ? 'wss:' : 'ws:'}//localhost:8000`
      : `${_proto === 'https:' ? 'wss:' : 'ws:'}//${_host}`);
