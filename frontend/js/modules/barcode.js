/**
 * Barcode Scanner moduli (BOSQICH 4.3)
 *
 * Ikkita rejim:
 *   1. BarcodeDetector API (Chrome 83+, Edge) — kamera orqali real-time
 *   2. Manual input — kassir qo'lda barcode yozadi (universal fallback)
 *
 * Ishlatilishi:
 *   import { BarcodeScanner } from './barcode.js';
 *   const scanner = new BarcodeScanner({ onScan: (code) => addProductByBarcode(code) });
 *   scanner.startCamera();   // kamera rejimi
 *   scanner.startManual();   // qo'lda rejim
 */

import { API }       from '../core/api.js';
import { showToast } from '../ui/toast.js';

export class BarcodeScanner {
    constructor({ onScan, onError } = {}) {
        this._api     = new API();
        this._onScan  = onScan  || (() => {});
        this._onError = onError || ((e) => showToast(e, 'error'));

        this._stream    = null;
        this._detector  = null;
        this._rafId     = null;
        this._videoEl   = null;
        this._active    = false;
        this._lastCode  = null;
        this._lastTime  = 0;

        this._supported = typeof BarcodeDetector !== 'undefined';
    }

    get isSupported() { return this._supported; }
    get isActive()    { return this._active; }

    // ── Kamera rejimi ─────────────────────────────────────────────────────

    async startCamera(videoElementId = 'barcodeVideo') {
        if (!this._supported) {
            showToast('Brauzeringiz kamera skanerini qo\'llab-quvvatlamaydi. Qo\'lda kiritish rejimiga o\'ting.', 'warning');
            this.startManual();
            return;
        }

        try {
            this._stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'environment', width: 640, height: 480 }
            });

            this._videoEl = document.getElementById(videoElementId);
            if (!this._videoEl) throw new Error('Video element topilmadi');

            this._videoEl.srcObject = this._stream;
            await this._videoEl.play();

            this._detector = new BarcodeDetector({
                formats: ['ean_13', 'ean_8', 'qr_code', 'code_128', 'code_39', 'upc_a', 'upc_e']
            });

            this._active = true;
            this._scanLoop();
        } catch (err) {
            this._onError('Kamera ochilmadi: ' + err.message);
            this.startManual();
        }
    }

    async _scanLoop() {
        if (!this._active || !this._videoEl) return;

        try {
            const barcodes = await this._detector.detect(this._videoEl);
            for (const bc of barcodes) {
                const now = Date.now();
                // Bir xil kodni 2 sekundda bir marta yuboramiz
                if (bc.rawValue !== this._lastCode || now - this._lastTime > 2000) {
                    this._lastCode = bc.rawValue;
                    this._lastTime = now;
                    this._onScan(bc.rawValue);
                    this._flashIndicator();
                }
            }
        } catch { /* frame o'tkazib yuboramiz */ }

        this._rafId = requestAnimationFrame(() => this._scanLoop());
    }

    stopCamera() {
        this._active = false;
        if (this._rafId) cancelAnimationFrame(this._rafId);
        if (this._stream) {
            this._stream.getTracks().forEach(t => t.stop());
            this._stream = null;
        }
        if (this._videoEl) this._videoEl.srcObject = null;
    }

    _flashIndicator() {
        const el = document.getElementById('barcodeScanIndicator');
        if (!el) return;
        el.classList.add('scanned');
        setTimeout(() => el.classList.remove('scanned'), 300);
    }

    // ── Qo'lda kiritish rejimi ────────────────────────────────────────────

    startManual(inputElementId = 'barcodeInput') {
        const input = document.getElementById(inputElementId);
        if (!input) return;

        input.focus();
        const handler = (e) => {
            if (e.key === 'Enter' && input.value.trim()) {
                this._onScan(input.value.trim());
                input.value = '';
            }
        };
        input.addEventListener('keydown', handler);
        this._manualCleanup = () => input.removeEventListener('keydown', handler);
    }

    stopManual() {
        this._manualCleanup?.();
    }

    // ── API orqali mahsulot izlash ────────────────────────────────────────

    async findProductByBarcode(barcode) {
        const res = await this._api.get('/products/', { barcode });
        if (res.success && res.data?.items?.length) {
            return res.data.items[0];
        }
        return null;
    }

    destroy() {
        this.stopCamera();
        this.stopManual();
    }
}

// ── BarcodeScanner modali (POS da ishlatish uchun) ───────────────────────────

export function createBarcodeScannerModal(onProductFound) {
    const modal = document.createElement('div');
    modal.className = 'modal barcode-modal';
    modal.id = 'barcodeScanModal';
    modal.innerHTML = `
        <div class="modal-overlay"></div>
        <div class="modal-content glass">
            <div class="modal-header">
                <h2>Barcode Skaner</h2>
                <button class="modal-close btn-icon glass" id="barcodeScanClose">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                        <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                </button>
            </div>
            <div class="modal-body barcode-body">
                <div class="barcode-video-wrap">
                    <video id="barcodeVideo" class="barcode-video" playsinline autoplay muted></video>
                    <div class="barcode-scan-line" id="barcodeScanIndicator"></div>
                    <div class="barcode-corners"></div>
                </div>
                <div class="barcode-manual">
                    <p>yoki qo'lda kiriting:</p>
                    <div class="input-wrapper">
                        <input type="text" id="barcodeInput" placeholder="Barcode..." autocomplete="off">
                        <kbd>Enter</kbd>
                    </div>
                </div>
                <div class="barcode-result" id="barcodeResult"></div>
            </div>
        </div>`;

    document.body.appendChild(modal);

    const scanner = new BarcodeScanner({
        onScan: async (code) => {
            const resultEl = document.getElementById('barcodeResult');
            if (resultEl) resultEl.textContent = `Qidirmoqda: ${code}...`;

            const product = await scanner.findProductByBarcode(code);
            if (product) {
                if (resultEl) resultEl.textContent = `Topildi: ${product.name}`;
                onProductFound(product);
                setTimeout(() => closeModal(), 800);
            } else {
                if (resultEl) resultEl.textContent = `❌ Mahsulot topilmadi: ${code}`;
                showToast(`Barcode ${code} — mahsulot topilmadi`, 'warning');
            }
        }
    });

    modal.querySelector('.modal-overlay').addEventListener('click', closeModal);
    modal.querySelector('#barcodeScanClose').addEventListener('click', closeModal);

    function closeModal() {
        scanner.destroy();
        modal.remove();
    }

    // Kamera va qo'lda rejimni boshlash
    scanner.startCamera('barcodeVideo');
    scanner.startManual('barcodeInput');

    setTimeout(() => modal.classList.add('open'), 10);
    return { scanner, close: closeModal };
}
