/**
 * WINDOWS PRINT SPOOLER QO'RIQCHISI — chek navbatga yig'ilmasin.
 *
 * ═══ MUAMMO (jonli, 1001 BARAKA, 2026-10-14: "2 kunlik chek navbati") ═══
 * USB chek yo'li: HTML → PDF → SumatraPDF `-print-to`. SumatraPDF ishni Windows
 * SPOOLER'iga topshirgan zahoti tugaydi va biz `ok:true` qaytarardik. Printer
 * o'chiq / qog'ozsiz / kabel uzilgan bo'lsa Windows ishni CHEKSIZ saqlaydi va
 * printer qaytganda HAMMASINI birdan bosadi — kassirga hech qanday xato yo'q.
 *
 * ═══ QOIDALAR ═══
 *  1) YUBORISHDAN OLDIN: printer offline / xatoda (qog'oz yo'q, qopqoq ochiq...)
 *     yoki BIZNING oldingi chekimiz hali navbatda (printer bosmayapti) → rad,
 *     navbatga QO'SHILMAYDI.
 *  2) YUBORGANDAN KEYIN: chek `waitMs` ichida navbatdan chiqmasa — BEKOR qilinadi
 *     va xato qaytadi (navbat yig'ilmaydi).
 *  3) TTL: XENORA cheklari (hujjat nomi `xenora_chek_*`) `ttlMs` dan eski bo'lsa
 *     o'chiriladi — eski chek keyinroq kutilmaganda chiqmasin. BOSHQA dasturlar
 *     ishlari (Word, etiketka...) TEGILMAYDI.
 *  4) Windows holatini o'qib bo'lmasa (PowerShell/WMI yo'q) — avvalgi xulq:
 *     chop etish to'silmaydi (fail-open), faqat log.
 *
 * Printer nomi PowerShell'ga ATROF-MUHIT o'zgaruvchisi orqali beriladi —
 * buyruq matniga qo'shilmaydi (nomda tirnoq/belgi bo'lsa ham injection yo'q).
 * Sof Node moduli: `runPs` almashtirilib testlanadi (electron/test-spool-guard.js).
 */
'use strict';
const { execFile } = require('child_process');

const DOC_PREFIX = 'xenora_chek_';
const TTL_MS = 5 * 60 * 1000;          // eski chek qayta chiqmasin
const WAIT_MS = 10000;                  // chek shu vaqt ichida navbatdan chiqishi kerak
const POLL_MS = 500;
const NOT_RESPONDING = "Printer javob bermayapti — qog'ozni tekshiring";

// Win32_Printer.DetectedErrorState — chop etishga to'sqinlik qiladiganlari
const ERROR_STATES = {
    4: "qog'oz tugagan", 5: "qog'oz yo'q (lotok)", 7: 'qopqoq ochiq', 8: "qog'oz tiqilgan",
    9: 'printer offline', 10: "xizmat ko'rsatish kerak",
};
// Win32_Printer.PrinterStatus: 7 = Offline
const STATUS_OFFLINE = 7;

// Bitta PowerShell skript: printer holati + uning navbatidagi ishlar (JSON).
// $env:XN_PRINTER bo'sh → standart printer.
const QUERY_PS = `
$ErrorActionPreference='Stop'
$n=$env:XN_PRINTER
if([string]::IsNullOrWhiteSpace($n)){ $p=Get-CimInstance Win32_Printer -Filter 'Default=TRUE' | Select-Object -First 1 }
else { $p=Get-CimInstance Win32_Printer | Where-Object { $_.Name -eq $n } | Select-Object -First 1 }
if(-not $p){ '{"exists":false}'; exit }
$jobs=@(Get-CimInstance Win32_PrintJob | Where-Object { $_.Name -like ($p.Name + ',*') } | ForEach-Object {
  [pscustomobject]@{ id=[int]$_.JobId; doc=[string]$_.Document; status=[string]$_.JobStatus;
    submitted=([DateTimeOffset]$_.TimeSubmitted).ToUnixTimeMilliseconds() } })
[pscustomobject]@{ exists=$true; name=$p.Name; workOffline=[bool]$p.WorkOffline;
  printerStatus=[int]$p.PrinterStatus; errorState=[int]$p.DetectedErrorState; jobs=$jobs } | ConvertTo-Json -Depth 4 -Compress
`;

// $env:XN_PRINTER + $env:XN_JOBS ("12,15") — faqat shu id'lar o'chiriladi.
const CANCEL_PS = `
$ErrorActionPreference='Stop'
$n=$env:XN_PRINTER; $ids=@($env:XN_JOBS -split ',' | Where-Object { $_ } | ForEach-Object { [int]$_ })
Get-CimInstance Win32_PrintJob | Where-Object { ($_.Name -like ($n + ',*')) -and ($ids -contains [int]$_.JobId) } | Remove-CimInstance
'ok'
`;

function defaultRunPs(script, env) {
    return new Promise((resolve, reject) => {
        execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
            { windowsHide: true, timeout: 8000, env: { ...process.env, ...env } },
            (err, stdout) => (err ? reject(err) : resolve(String(stdout || '').trim())));
    });
}

function _isOurs(job, docName) {
    const d = String(job.doc || '');
    return docName ? d.includes(docName) : d.includes(DOC_PREFIX);
}

function createSpoolGuard({ runPs = defaultRunPs, now = () => Date.now(), sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
                            ttlMs = TTL_MS, waitMs = WAIT_MS, pollMs = POLL_MS, log = console } = {}) {

    async function query(printerName) {
        const out = await runPs(QUERY_PS, { XN_PRINTER: printerName || '' });
        const q = JSON.parse(out || '{}');
        if (q && q.jobs && !Array.isArray(q.jobs)) q.jobs = [q.jobs];   // ConvertTo-Json bitta elementni massivsiz beradi
        return q;
    }

    async function cancel(printerName, ids) {
        if (!ids.length) return;
        await runPs(CANCEL_PS, { XN_PRINTER: printerName, XN_JOBS: ids.join(',') });
    }

    // Printer holatidan kassirga tushunarli sabab (yoki null — bosish mumkin)
    function blockReason(q) {
        if (!q || q.exists === false) return null;   // nom topilmadi — SumatraPDF o'zi xato beradi
        if (q.workOffline || q.printerStatus === STATUS_OFFLINE) return 'printer offline';
        if (ERROR_STATES[q.errorState]) return ERROR_STATES[q.errorState];
        return null;
    }

    /**
     * Yuborishdan OLDIN. Qaytaradi: { ok:true, printer } | { ok:false, error }.
     * Eski (TTL) XENORA cheklarini o'chiradi; printer xato/offline yoki
     * BIZNING yangi chekimiz hali navbatda bo'lsa — rad.
     */
    async function before(printerName) {
        let q;
        try { q = await query(printerName); } catch (e) {
            log.warn('[spool-guard] holat o\'qilmadi — tekshiruvsiz davom:', e && e.message);
            return { ok: true, checked: false };
        }
        if (!q || q.exists === false) return { ok: true, checked: false };
        const ours = (q.jobs || []).filter((j) => _isOurs(j));
        const stale = ours.filter((j) => now() - Number(j.submitted || 0) > ttlMs);
        if (stale.length) {
            try { await cancel(q.name, stale.map((j) => j.id)); log.warn(`[spool-guard] ${stale.length} ta eski chek navbatdan o'chirildi (${q.name})`); }
            catch (e) { log.warn('[spool-guard] eski chekni o\'chirib bo\'lmadi:', e && e.message); }
        }
        const reason = blockReason(q);
        if (reason) return { ok: false, error: `${NOT_RESPONDING} (${reason})`, printer: q.name };
        const fresh = ours.length - stale.length;
        if (fresh > 0) return { ok: false, error: `${NOT_RESPONDING} (oldingi chek hali chiqmagan)`, printer: q.name };
        return { ok: true, checked: true, printer: q.name };
    }

    /**
     * Yuborgandan KEYIN: `docName` (shu chek fayli) navbatdan chiqishini kutadi.
     * Chiqmasa — BEKOR qiladi va xato. Holat o'qilmasa — ok (avvalgi xulq).
     */
    async function after(printerName, docName) {
        const deadline = now() + waitMs;
        let lastQ = null;
        for (;;) {
            try { lastQ = await query(printerName); } catch (e) {
                log.warn('[spool-guard] keyingi holat o\'qilmadi:', e && e.message);
                return { ok: true, checked: false };
            }
            const mine = (lastQ.jobs || []).filter((j) => _isOurs(j, docName));
            if (!mine.length) return { ok: true, checked: true };
            if (now() >= deadline) {
                try { await cancel(lastQ.name, mine.map((j) => j.id)); } catch (e) {
                    log.warn('[spool-guard] chekni bekor qilib bo\'lmadi:', e && e.message);
                }
                const reason = blockReason(lastQ);
                return { ok: false, cancelled: true,
                         error: `${NOT_RESPONDING}${reason ? ` (${reason})` : ''} — chek navbatga qo'yilmadi` };
            }
            await sleep(pollMs);
        }
    }

    /** Ilova ishga tushganda: BARCHA printerlardagi eski XENORA cheklarini tozalash. */
    async function purgeStaleAll() {
        const script = `
$ErrorActionPreference='Stop'
$cut=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - [int64]$env:XN_TTL
$old=@(Get-CimInstance Win32_PrintJob | Where-Object { ([string]$_.Document) -like '*${DOC_PREFIX}*' -and
  ([DateTimeOffset]$_.TimeSubmitted).ToUnixTimeMilliseconds() -lt $cut })
$old | Remove-CimInstance
$old.Count`;
        try {
            const n = Number(await runPs(script, { XN_TTL: String(ttlMs) })) || 0;
            if (n) log.warn(`[spool-guard] ishga tushishda ${n} ta eski chek navbatdan o'chirildi`);
            return n;
        } catch (e) {
            log.warn('[spool-guard] ishga tushish tozalovi bajarilmadi:', e && e.message);
            return 0;
        }
    }

    return { before, after, purgeStaleAll, query, blockReason };
}

module.exports = { createSpoolGuard, DOC_PREFIX, TTL_MS, WAIT_MS, NOT_RESPONDING, ERROR_STATES };
