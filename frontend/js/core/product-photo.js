/**
 * XENORA — mahsulot rasmi: yuklashdan OLDIN klient tomonda kichraytirish.
 *
 * NEGA: telefon kamerasi 3-12 MB JPEG beradi (12-50 MP). Server 5 MB dan
 * kattasini rad etadi (core/product_images.py) va baribir 800px WebP ga
 * siqadi — ya'ni katta faylni mobil internetda yuborish bekor vaqt va pul.
 * Bu yerda uzun tomon 1600px gacha (server 800px dan 2 barobar zaxira —
 * ikki marta siqishda sifat yo'qolmasin) kichraytiriladi: ~0.3-0.8 MB.
 *
 * Xavfsiz: har qanday xatoda (dekod bo'lmadi, canvas yo'q, eski brauzer)
 * ASL fayl qaytariladi — server o'z tekshiruvini baribir qiladi.
 *
 * Classic <script> (import EMAS): admin.html + inventory/suppliers/
 * purchase_receipts.html inline skriptlari `window.XenoraPhoto` ni ishlatadi.
 * Yo'q bo'lsa ham sahifalar ishlaydi (asl fayl yuboriladi).
 *
 * Kamera tugmasi bu yerda EMAS — u oddiy HTML:
 *   <input type="file" accept="image/*" capture="environment">
 * (AI-Ombor bilan aynan bir xil). APK/telefonda kamera to'g'ridan ochiladi,
 * kompyuter brauzeri `capture` ni e'tiborsiz qoldirib fayl tanlashni ochadi.
 */
(function (g) {
  'use strict';

  var MAX_SIDE = 1600;
  var JPEG_QUALITY = 0.85;
  // Kichik va o'lchami me'yorda fayl tegilmaydi (logo, skrinshot, tayyor rasm)
  var SKIP_BELOW_BYTES = 1024 * 1024;

  function decode(file) {
    if (typeof g.createImageBitmap === 'function') {
      // imageOrientation:'from-image' — telefon EXIF aylanishi qo'llanadi
      // (canvas'dan keyin EXIF yo'qoladi, server endi uni to'g'rilay olmaydi)
      return g.createImageBitmap(file, { imageOrientation: 'from-image' })
        .catch(function () { return decodeViaImg(file); });
    }
    return decodeViaImg(file);
  }

  function decodeViaImg(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('decode')); };
      img.src = url;
    });
  }

  function toBlob(canvas, type, quality) {
    return new Promise(function (resolve) {
      try { canvas.toBlob(resolve, type, quality); } catch (e) { resolve(null); }
    });
  }

  /**
   * @param {File} file
   * @returns {Promise<File>} kichraytirilgan (yoki o'zgarmagan asl) fayl
   */
  async function shrink(file) {
    if (!file || !/^image\/(jpeg|png|webp)$/i.test(file.type || '')) return file;
    try {
      var img = await decode(file);
      var w = img.width || img.naturalWidth, h = img.height || img.naturalHeight;
      if (!w || !h) return file;
      var scale = Math.min(1, MAX_SIDE / Math.max(w, h));
      if (scale === 1 && file.size <= SKIP_BELOW_BYTES) return file;

      var cw = Math.max(1, Math.round(w * scale)), ch = Math.max(1, Math.round(h * scale));
      var canvas = document.createElement('canvas');
      canvas.width = cw; canvas.height = ch;
      var ctx = canvas.getContext('2d');
      if (!ctx) return file;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(img, 0, 0, cw, ch);
      if (img.close) img.close();

      // PNG/WebP — shaffoflik bo'lishi mumkin → WebP (alfa saqlanadi).
      // Brauzer WebP bermasa (blob.type boshqa) — JPEG.
      var wantWebp = !/jpeg/i.test(file.type);
      var blob = wantWebp ? await toBlob(canvas, 'image/webp', JPEG_QUALITY) : null;
      if (!blob || blob.type !== 'image/webp') blob = await toBlob(canvas, 'image/jpeg', JPEG_QUALITY);
      if (!blob) return file;
      // Kattalashib ketsa (allaqachon siqilgan kichik rasm) — asli yaxshiroq
      if (blob.size >= file.size) return file;

      var ext = blob.type === 'image/webp' ? '.webp' : '.jpg';
      var base = String(file.name || 'rasm').replace(/\.[^.]+$/, '') || 'rasm';
      return new File([blob], base + ext, { type: blob.type, lastModified: Date.now() });
    } catch (e) {
      return file;
    }
  }

  /** Server javobidan foydalanuvchiga ko'rsatiladigan rasm xatosi matni. */
  async function uploadError(res) {
    var detail = '';
    try { detail = ((await res.json()) || {}).detail || ''; } catch (e) { /* JSON emas */ }
    return "Mahsulot saqlandi, lekin rasm yuklanmadi" + (detail ? ': ' + detail : '');
  }

  g.XenoraPhoto = { shrink: shrink, uploadError: uploadError, MAX_SIDE: MAX_SIDE };
})(window);
