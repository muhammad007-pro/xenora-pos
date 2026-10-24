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
// `sent` — baytlar printerga YOZILGANMI. Qayta urinish FAQAT `sent:false` da
// xavfsiz: yozilgandan keyingi timeout'da qayta yuborish chekni IKKI marta bosardi.
function sendRawTcp(ip, port, bytes, timeoutMs) {
    return new Promise((resolve) => {
        let settled = false;
        let sent = false;
        const finish = (result) => {
            if (settled) return;
            settled = true;
            try { sock.destroy(); } catch { /* ignore */ }
            resolve({ ...result, sent });
        };
        const sock = net.createConnection({ host: ip, port, timeout: timeoutMs || 5000 });
        sock.on('connect', () => {
            sent = true;   // yozish boshlandi — bundan keyin qayta yuborilmaydi
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

/**
 * Chegaralangan qayta urinish (chek navbati 2026-10-14): ulanib bo'lmasa
 * `attempts` martagacha (sukut 3), har biri `timeoutMs`; baytlar YOZILGAN
 * bo'lsa (sent) — qayta urinilmaydi (dublikat chek bo'lmasin). Navbat YO'Q:
 * hammasi yiqilsa darrov xato — chek keyinroq kutilmaganda chiqmaydi.
 */
async function sendRawTcpWithRetry(ip, port, bytes, { attempts = 3, timeoutMs = 3000, gapMs = 700,
                                                       sender = sendRawTcp, sleep = (ms) => new Promise((r) => setTimeout(r, ms)) } = {}) {
    let res;
    for (let i = 1; i <= attempts; i++) {
        res = await sender(ip, port, bytes, timeoutMs);
        if (res.ok || res.sent) return { ...res, attempts: i };
        if (i < attempts) await sleep(gapMs);
    }
    return { ...res, attempts, error: `${res.error} — ${attempts} marta urinildi. Printer javob bermayapti — qog'ozni va ulanishni tekshiring` };
}

module.exports = { sendRawTcp, sendRawTcpWithRetry, friendlyNetError };
