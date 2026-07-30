/**
 * Kamera shtrix-kod skaner — 2 QATLAM:
 *
 *   1) Capacitor NATIVE (Android APK) — @capacitor-mlkit/barcode-scanning (ML Kit).
 *      Faqat window.Capacitor.isNativePlatform() rost bo'lganda urinadi.
 *   2) FALLBACK (brauzer / Electron .exe / PWA / plagin sinxronlanmagan) —
 *      BarcodeDetector API, mavjud js/modules/barcode.js dagi BarcodeScanner
 *      klassi orqali (kod dublikati yo'q).
 *
 * Natija HAR DOIM window.handleBarcodeScan(code) ga uzatiladi — mavjud
 * USB/qo'lda quvur (lookup -> savatga -> tarozi -> topilmasa xabar,
 * frontend/js/modules/pos.js) TEGILMAYDI, faqat kod manbai qo'shiladi.
 *
 * ⚠️ ML Kit plagin android/package.json ga qo'shildi, lekin native tomon
 * (AndroidManifest CAMERA ruxsati + Gradle bog'lanish) faqat haqiqiy APK
 * build (`npm install` + `npx cap sync android` + gradle) paytida sinaladi.
 * Bu fayl shu build bo'lmaguncha browser fallback orqali ishlaydi (Capacitor
 * mavjud emas / plagin ro'yxatdan o'tmagan holatda ham xavfsiz tushadi).
 */
import { BarcodeScanner as DetectorScanner } from './barcode.js';
import { showToast } from '../ui/toast.js';

const NATIVE_FORMATS = ['EAN_13', 'EAN_8', 'CODE_128', 'CODE_39', 'UPC_A', 'UPC_E', 'QR_CODE'];

function _hasCapacitorNative() {
    return !!(window.Capacitor
        && typeof window.Capacitor.isNativePlatform === 'function'
        && window.Capacitor.isNativePlatform());
}

function _isElectron() {
    return !!(window.electronAPI && window.electronAPI.isElectron);
}

/**
 * "📷 Skaner" tugmasini ko'rsatish shartmi?
 *   - Capacitor APK (native)           -> HA
 *   - Electron .exe (monoblok, USB skaner ishlatadi) -> YO'Q
 *   - Boshqa brauzer/PWA (BarcodeDetector qo'llab-quvvatlansa) -> HA
 */
export function isCameraScanAvailable() {
    if (_hasCapacitorNative()) return true;
    if (_isElectron()) return false;
    return typeof BarcodeDetector !== 'undefined';
}

/**
 * Skanerni ochadi. Capacitor native mavjud bo'lsa ML Kit bilan urinadi,
 * bo'lmasa yoki xato bersa (masalan plagin hali sync qilinmagan) — jimgina
 * BarcodeDetector fallback modaliga tushadi.
 */
export async function openCameraScanner() {
    if (_hasCapacitorNative()) {
        const handled = await _tryNativeScan();
        if (handled) return;
        // native urinish muvaffaqiyatsiz (plagin yo'q/xato) -> pastga tushamiz
    }
    _openFallbackModal();
}

// ── 1-qatlam: Capacitor ML Kit ────────────────────────────────────────────────
async function _tryNativeScan() {
    try {
        const plugin = window.Capacitor?.Plugins?.BarcodeScanner;
        if (!plugin || typeof plugin.scan !== 'function') return false;

        if (typeof plugin.checkPermissions === 'function') {
            const perm = await plugin.checkPermissions();
            if (perm?.camera !== 'granted') {
                const req = await plugin.requestPermissions();
                if (req?.camera !== 'granted') {
                    showToast("Kamera ruxsati berilmadi — sozlamalardan yoqing", 'warning');
                    return true; // foydalanuvchi rad etdi — fallbackka tushish shart emas
                }
            }
        }

        const result = await plugin.scan({ formats: NATIVE_FORMATS });
        const bc = result?.barcodes?.[0];
        const code = bc?.rawValue || bc?.displayValue;
        if (code) {
            window.handleBarcodeScan(code);
        }
        return true;
    } catch (e) {
        console.warn('[camera-scanner] ML Kit ishlamadi, BarcodeDetector fallback:', e?.message || e);
        return false;
    }
}

// ── 2-qatlam: BarcodeDetector fallback (o'z modali, alohida id'lar) ──────────
let _stylesInjected = false;
function _injectStyles() {
    if (_stylesInjected) return;
    _stylesInjected = true;
    const s = document.createElement('style');
    s.id = 'camScanStyles';
    s.textContent = `
#camScanModal{position:fixed;inset:0;z-index:9500;display:flex;align-items:center;justify-content:center;padding:1rem}
#camScanModal .cs-overlay{position:absolute;inset:0;background:rgba(0,0,0,.78)}
#camScanModal .cs-box{position:relative;background:var(--bg2,#0a1628);border:1px solid var(--border2,rgba(255,255,255,.08));border-radius:1rem;width:100%;max-width:420px;overflow:hidden}
#camScanModal .cs-head{padding:.875rem 1.125rem;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border2,rgba(255,255,255,.08))}
#camScanModal .cs-head h3{font-size:.9375rem;font-weight:700;margin:0;color:var(--text,#e8eef5)}
#camScanModal .cs-close{width:30px;height:30px;border-radius:8px;border:none;background:var(--bg3,#0f2038);color:var(--text2,#8b9bb0);cursor:pointer;font-size:1rem}
#camScanModal .cs-video-wrap{position:relative;aspect-ratio:4/3;background:#000}
#camScanModal .cs-video-wrap video{width:100%;height:100%;object-fit:cover}
#camScanModal .cs-line{position:absolute;left:10%;right:10%;top:50%;height:2px;background:#22c55e;box-shadow:0 0 8px #22c55e;animation:csScanMove 2s ease-in-out infinite}
#camScanModal .cs-line.scanned{background:#22c55e;box-shadow:0 0 14px #22c55e}
@keyframes csScanMove{0%,100%{top:15%}50%{top:85%}}
#camScanModal .cs-result{padding:.75rem 1.125rem;font-size:.8125rem;color:var(--text2,#8b9bb0);min-height:20px}
`;
    document.head.appendChild(s);
}

function _openFallbackModal() {
    if (typeof BarcodeDetector === 'undefined') {
        showToast("Bu qurilma kamera skanerini qo'llab-quvvatlamaydi", 'warning');
        return;
    }
    if (document.getElementById('camScanModal')) return; // allaqachon ochiq

    _injectStyles();

    const modal = document.createElement('div');
    modal.id = 'camScanModal';
    modal.innerHTML = `
      <div class="cs-overlay"></div>
      <div class="cs-box">
        <div class="cs-head">
          <h3>📷 Barkod skaner</h3>
          <button type="button" class="cs-close" id="camScanCloseBtn">✕</button>
        </div>
        <div class="cs-video-wrap">
          <video id="camScanVideo" playsinline autoplay muted></video>
          <div class="cs-line" id="camScanLine"></div>
        </div>
        <div class="cs-result" id="camScanResult">Barkodni kameraga ko'rsating...</div>
      </div>`;
    document.body.appendChild(modal);

    const scanner = new DetectorScanner({
        onScan: (code) => {
            const resultEl = document.getElementById('camScanResult');
            const lineEl = document.getElementById('camScanLine');
            if (resultEl) resultEl.textContent = `✓ Topildi: ${code}`;
            lineEl?.classList.add('scanned');
            window.handleBarcodeScan(code);
            setTimeout(close, 700);
        },
        onError: (msg) => {
            const resultEl = document.getElementById('camScanResult');
            if (resultEl) resultEl.textContent = msg;
        },
    });

    function close() {
        scanner.destroy();
        modal.remove();
    }

    modal.querySelector('.cs-overlay').addEventListener('click', close);
    modal.querySelector('#camScanCloseBtn').addEventListener('click', close);
    document.addEventListener('keydown', function escClose(e) {
        if (e.key === 'Escape') { close(); document.removeEventListener('keydown', escClose); }
    });

    scanner.startCamera('camScanVideo');
}
