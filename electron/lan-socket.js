/**
 * RAW TCP orqali ESC/POS bayt yuborish — Electron'ga bog'liq emas (sof Node
 * `net` moduli), shuning uchun oddiy `node` skripti bilan ham sinash mumkin
 * (mock TCP server bilan). main.js buni require qilib ishlatadi.
 */
'use strict';
const net = require('net');

// Tarmoq xatosini kassir tushunadigan xabarga o'giradi (crash EMAS).
function friendlyNetError(err, ip, port) {
    const code = err && err.code;
    if (code === 'ECONNREFUSED') return `Printer ulanishni rad etdi (${ip}:${port}) — printer o'chiq yoki port noto'g'ri`;
    if (code === 'EHOSTUNREACH' || code === 'ENETUNREACH') return `Printerga (${ip}:${port}) tarmoq orqali yetib bo'lmadi — IP/Wi-Fi ni tekshiring`;
    if (code === 'ETIMEDOUT') return `Printer javob bermadi (${ip}:${port}) — vaqt tugadi`;
    return `LAN printer xatosi (${ip}:${port}): ` + ((err && err.message) || 'nomaʼlum');
}

// RAW ESC/POS baytni TCP orqali yuboradi. Timeout — osilib qolmaslik uchun
// (printer/tarmoq javob bermasa 5s dan keyin aniq xato bilan qaytadi).
function sendRawTcp(ip, port, bytes, timeoutMs) {
    return new Promise((resolve) => {
        let settled = false;
        const finish = (result) => {
            if (settled) return;
            settled = true;
            try { sock.destroy(); } catch { /* ignore */ }
            resolve(result);
        };
        const sock = net.createConnection({ host: ip, port, timeout: timeoutMs || 5000 });
        sock.on('connect', () => {
            sock.write(bytes, (err) => {
                if (err) return finish({ ok: false, engine: 'lan-tcp', error: 'Bayt yuborishda xato: ' + err.message });
                sock.end();
            });
        });
        sock.on('close', () => finish({ ok: true, engine: 'lan-tcp', device: `${ip}:${port}`, bytes: bytes.length }));
        sock.on('timeout', () => finish({ ok: false, engine: 'lan-tcp', error: `Printer javob bermadi (${ip}:${port}) — vaqt tugadi (${Math.round((timeoutMs || 5000) / 1000)}s)` }));
        sock.on('error', (err) => finish({ ok: false, engine: 'lan-tcp', error: friendlyNetError(err, ip, port) }));
    });
}

module.exports = { sendRawTcp, friendlyNetError };
