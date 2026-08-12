/**
 * Windows RAW spooler — baytlarni o'rnatilgan printer NAVBATIGA to'g'ridan
 * yuboradi (drayver bayt oqimiga TEGMAYDI).
 *
 * NAMUNA/JUFT: electron/lan-socket.js — u TCP transporti, bu esa USB (spooler)
 * transporti. Ikkalasi ham protokolga BOG'LIQ EMAS: ESC/POS ham, TSPL ham bir
 * xil "shu baytlarni shu printerga ber" deb yuboriladi.
 *
 * NEGA PowerShell + C#:
 *   Windows'da RAW chop etish = winspool.drv: OpenPrinter → StartDocPrinter
 *   (datatype "RAW") → WritePrinter. Node'da bunga to'g'ridan kirish YO'Q va
 *   `printer` npm moduli NATIVE addon (node-gyp) — u ataylab qo'shilmagan
 *   (electron-builder install-app-deps butun loyiha uchun buzilmasin).
 *   PowerShell `Add-Type` bilan C# ni ish vaqtida kompilyatsiya qiladi —
 *   qo'shimcha bog'liqlik YO'Q (.NET Framework Windows 10 da mavjud).
 *
 * NIMA ISHLAMAYDI (sinab ko'rilgan yo'llar, takrorlamang):
 *   · Out-Printer / print /D:  → GDI drayveri orqali, TSPL MATN bo'lib bosiladi
 *   · copy /b file USB002      → Windows USB portini yoziladigan qurilma qilmaydi
 *   · copy /b file \\pc\share  → printer share qilinishi va autentifikatsiya kerak
 *
 * Electron'ga bog'liq emas — oddiy `node` bilan ham sinash mumkin.
 */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');

// winspool.drv P/Invoke — Reflection.Emit orqali (C# manba EMAS).
//
// ⚠️ `Add-Type -TypeDefinition` (C# manba) ATAYIN ISHLATILMAYDI: u csc.exe ni
// chaqirib C# ni ish vaqtida kompilyatsiya qiladi. Sovuq Windows'da (birinchi
// chop etish, antivirus generatsiya qilingan assembly'ni skanerlaydi) bu
// 30 SONIYAdan oshib ketdi va sinovda timeout berdi — kassir uchun "etiketka
// chiqmadi" degani. Reflection.Emit kompilyatorsiz ishlaydi (~0.3-0.5s).
//
// DOCINFOA struct'i Reflection.Emit'da og'ir — o'rniga uni QO'LDA yig'amiz:
// 3 ta ANSI satr ko'rsatkichi ketma-ket (pDocName, pOutputFile, pDataType),
// StartDocPrinterA esa IntPtr qabul qiladi. Natija bir xil, kod sodda.
const PS_SCRIPT = `param(
  [Parameter(Mandatory=$true)][string]$PrinterName,
  [Parameter(Mandatory=$true)][string]$FilePath,
  [string]$DocName = 'XENORA RAW'
)
$ErrorActionPreference = 'Stop'

# ── Printer mavjudmi (aniq xato xabari uchun; GAC assembly, kompilyatsiya yo'q) ──
Add-Type -AssemblyName System.Drawing
$installed = @([System.Drawing.Printing.PrinterSettings]::InstalledPrinters)
if ($installed -notcontains $PrinterName) {
  Write-Error ("PRINTER_NOT_FOUND:" + ($installed -join '|'))
  exit 2
}

# ── winspool.drv P/Invoke (Reflection.Emit — csc.exe CHAQIRILMAYDI) ──
$asmName = New-Object System.Reflection.AssemblyName('XenoraRawAsm')
$asm = [System.AppDomain]::CurrentDomain.DefineDynamicAssembly($asmName, [System.Reflection.Emit.AssemblyBuilderAccess]::Run)
$mod = $asm.DefineDynamicModule('XenoraRawMod')
$tb  = $mod.DefineType('XenoraRawPrinter', 'Public, Class')

$MA   = [System.Reflection.MethodAttributes]'Public, Static, PinvokeImpl'
$CC   = [System.Reflection.CallingConventions]::Standard
$WINAPI = [System.Runtime.InteropServices.CallingConvention]::Winapi
$ANSI   = [System.Runtime.InteropServices.CharSet]::Ansi

function New-PInvoke([string]$name, [string]$entry, [Type]$ret, [Type[]]$params) {
  $m = $tb.DefinePInvokeMethod($name, 'winspool.drv', $entry, $MA, $CC, $ret, $params, $WINAPI, $ANSI)
  $m.SetImplementationFlags([System.Reflection.MethodImplAttributes]::PreserveSig)
}

New-PInvoke 'OpenPrinter'      'OpenPrinterA'     ([bool]) @([string], [IntPtr].MakeByRefType(), [IntPtr])
New-PInvoke 'StartDocPrinter'  'StartDocPrinterA' ([bool]) @([IntPtr], [int], [IntPtr])
New-PInvoke 'StartPagePrinter' 'StartPagePrinter' ([bool]) @([IntPtr])
New-PInvoke 'WritePrinter'     'WritePrinter'     ([bool]) @([IntPtr], [byte[]], [int], [int].MakeByRefType())
New-PInvoke 'EndPagePrinter'   'EndPagePrinter'   ([bool]) @([IntPtr])
New-PInvoke 'EndDocPrinter'    'EndDocPrinter'    ([bool]) @([IntPtr])
New-PInvoke 'ClosePrinter'     'ClosePrinter'     ([bool]) @([IntPtr])

$RP = $tb.CreateType()
$M = [System.Runtime.InteropServices.Marshal]

$bytes = [System.IO.File]::ReadAllBytes($FilePath)
$h = [IntPtr]::Zero
$written = 0

if (-not $RP::OpenPrinter($PrinterName, [ref]$h, [IntPtr]::Zero)) {
  Write-Error ("PRINTER_OPEN_FAILED:" + $M::GetLastWin32Error()); exit 3
}

# Handle OCHILDI — bundan keyingi HAR QANDAY xatoda ham yopilishi shart,
# shu sabab qolgan hammasi shu try/finally ICHIDA.
try {
  # DOCINFOA: pDocName, pOutputFile(null), pDataType("RAW") — 3 ta ko'rsatkich.
  # ⚠️ [IntPtr]::Size ishlatiladi, Marshal::SizeOf EMAS — PowerShell'da
  # SizeOf([IntPtr]) overload'ni yecha olmaydi (Type obyektini struct deb oladi)
  # va "Exception calling SizeOf with 1 argument(s)" beradi (jonli sinovda chiqdi).
  $ptrSize = [IntPtr]::Size
  $pDoc = $M::StringToHGlobalAnsi($DocName)
  $pRaw = $M::StringToHGlobalAnsi('RAW')
  $di   = $M::AllocHGlobal($ptrSize * 3)
  try {
    $M::WriteIntPtr($di, 0, $pDoc)
    $M::WriteIntPtr($di, $ptrSize, [IntPtr]::Zero)
    $M::WriteIntPtr($di, $ptrSize * 2, $pRaw)

    if (-not $RP::StartDocPrinter($h, 1, $di)) {
      Write-Error ("STARTDOC_FAILED:" + $M::GetLastWin32Error()); exit 4
    }
    try {
      if (-not $RP::StartPagePrinter($h)) {
        Write-Error ("STARTPAGE_FAILED:" + $M::GetLastWin32Error()); exit 5
      }
      try {
        if (-not $RP::WritePrinter($h, $bytes, $bytes.Length, [ref]$written)) {
          Write-Error ("WRITE_FAILED:" + $M::GetLastWin32Error()); exit 6
        }
      } finally { [void]$RP::EndPagePrinter($h) }
    } finally { [void]$RP::EndDocPrinter($h) }
  } finally {
    if ($di   -ne $null -and $di   -ne [IntPtr]::Zero) { $M::FreeHGlobal($di) }
    if ($pDoc -ne $null -and $pDoc -ne [IntPtr]::Zero) { $M::FreeHGlobal($pDoc) }
    if ($pRaw -ne $null -and $pRaw -ne [IntPtr]::Zero) { $M::FreeHGlobal($pRaw) }
  }
} finally { [void]$RP::ClosePrinter($h) }
Write-Output ("RAW_OK:" + $written)
`;

// Win32 xato kodini kassir tushunadigan xabarga o'giradi (crash EMAS).
function friendlyRawError(stderr, printerName) {
    const s = String(stderr || '');
    const nf = s.match(/PRINTER_NOT_FOUND:([^\r\n]*)/);
    if (nf) {
        const list = (nf[1] || '').split('|').filter(Boolean);
        return `"${printerName}" printeri Windows'da topilmadi`
            + (list.length ? `. Mavjud: ${list.join(', ')}` : '');
    }
    if (/PRINTER_OPEN_FAILED:1801/.test(s)) return `Printer nomi noto'g'ri: "${printerName}" — Windows'da bunday printer yo'q`;
    if (/PRINTER_OPEN_FAILED:5\b/.test(s)) return `Printerga ruxsat yo'q ("${printerName}") — administrator huquqi kerak bo'lishi mumkin`;
    if (/PRINTER_OPEN_FAILED/.test(s))     return `Printerni ochib bo'lmadi ("${printerName}") — o'chiq yoki uzilgan`;
    if (/STARTDOC_FAILED/.test(s))         return `Chop etish topshirig'i boshlanmadi ("${printerName}") — navbat to'xtagan (pauza) bo'lishi mumkin`;
    if (/WRITE_FAILED/.test(s))            return `Printerga yozib bo'lmadi ("${printerName}") — qog'oz tugagan yoki kabel uzilgan`;
    if (/Add-Type|csc\.exe|CS\d{4}/.test(s)) return 'Windows PowerShell/.NET komponenti ishlamadi — RAW chop etish mumkin emas';
    const first = s.split(/\r?\n/).find((l) => l.trim());
    return `RAW chop etish xatosi ("${printerName}")` + (first ? ': ' + first.trim() : '');
}

/**
 * Baytlarni Windows printer navbatiga RAW ko'rinishda yuboradi.
 *
 * printerName — Windows'dagi printer nomi (masalan "Xprinter XP-365B")
 * bytes       — Buffer (ESC/POS yoki TSPL — farqi yo'q)
 * timeoutMs   — osilib qolmaslik uchun (standart 15s: Add-Type birinchi
 *               chaqiruvda C# ni kompilyatsiya qiladi, ~1-2s ketadi)
 */
function sendRawToPrinter(printerName, bytes, timeoutMs) {
    return new Promise((resolve) => {
        const name = String(printerName || '').trim();
        if (!name) {
            return resolve({ ok: false, engine: 'raw-spooler', error: 'Printer nomi kiritilmagan' });
        }
        if (process.platform !== 'win32') {
            return resolve({ ok: false, engine: 'raw-spooler',
                error: 'RAW (USB) chop etish faqat Windows\'da ishlaydi' });
        }

        const stamp = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        const binPath = path.join(os.tmpdir(), `xenora_raw_${stamp}.bin`);
        const ps1Path = path.join(os.tmpdir(), `xenora_raw_${stamp}.ps1`);
        const cleanup = () => {
            for (const f of [binPath, ps1Path]) {
                try { fs.unlinkSync(f); } catch { /* ignore */ }
            }
        };

        try {
            fs.writeFileSync(binPath, bytes);
            // BOM bilan yozamiz — PowerShell skript kodlashini aniq bilsin.
            fs.writeFileSync(ps1Path, '\ufeff' + PS_SCRIPT, 'utf8');
        } catch (err) {
            cleanup();
            return resolve({ ok: false, engine: 'raw-spooler',
                error: 'Vaqtinchalik fayl yozilmadi: ' + err.message });
        }

        execFile(
            'powershell.exe',
            ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
             '-File', ps1Path, '-PrinterName', name, '-FilePath', binPath],
            { windowsHide: true, timeout: timeoutMs || 15000 },
            (err, stdout, stderr) => {
                cleanup();
                if (err) {
                    if (err.killed) {
                        return resolve({ ok: false, engine: 'raw-spooler',
                            error: `Printer javob bermadi ("${name}") — vaqt tugadi` });
                    }
                    return resolve({ ok: false, engine: 'raw-spooler',
                        error: friendlyRawError(stderr || err.message, name) });
                }
                const m = String(stdout || '').match(/RAW_OK:(\d+)/);
                if (!m) {
                    return resolve({ ok: false, engine: 'raw-spooler',
                        error: friendlyRawError(stderr || stdout, name) });
                }
                resolve({ ok: true, engine: 'raw-spooler', device: name, bytes: Number(m[1]) });
            },
        );
    });
}

module.exports = { sendRawToPrinter, friendlyRawError, PS_SCRIPT };
