/**
 * Frontend konfiguratsiyasi
 *
 * file:// yoki Live Server (5500):  absolute http://localhost:8000/api/v1
 * Docker local (localhost:80):      relative /api/v1 (nginx proksi)
 * Production (real domain):         relative /api/v1 (nginx proksi)
 */

const _proto = window.location.protocol;
const _host  = window.location.host;
const _port  = window.location.port;

// file:// protokoli = bevosita HTML fayl ochish (hech qanday server yo'q)
const _isFile = _proto === 'file:';

// Live Server yoki boshqa alohida dev server (port 5500, 3000, 4200, 8080...)
// http://localhost:5500, http://127.0.0.1:3000 va h.k.
const _devServerPorts = ['5500', '5501', '3000', '4200', '8080', '8081'];
const _isLiveServer = _devServerPorts.includes(_port)
    && ['localhost', '127.0.0.1'].includes(window.location.hostname);

const _isDev = _isFile || _isLiveServer;

// Electron server rejimi (SaaS): preload window.XENORA_SERVER ni beradi
// (masalan 'http://146.190.225.168'). Bu belgilangan bo'lsa — file:// dev
// mantig'idan USTUN turadi va API/WS to'g'ridan serverga yo'naltiriladi.
const _xenoraServer = (typeof window !== 'undefined' && window.XENORA_SERVER)
  ? window.XENORA_SERVER : null;

export const API_BASE = _xenoraServer
  ? `${_xenoraServer}/api/v1`
  : (_isDev ? 'http://localhost:8000/api/v1' : '/api/v1');

export const WS_BASE = _xenoraServer
  ? _xenoraServer.replace(/^http/, 'ws')
  : (_isDev
      ? `${_proto === 'https:' ? 'wss:' : 'ws:'}//localhost:8000`
      : `${_proto === 'https:' ? 'wss:' : 'ws:'}//${_host}`);
