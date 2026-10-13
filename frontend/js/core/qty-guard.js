/* ── Miqdor qo'riqchisi — shtrix-kod miqdor maydoniga tushib qolmasin ─────────
   MUAMMO: skaner fokus MIQDOR maydonida turganida o'qiydi va omborga
   508 681 002 822 184 dona kirim bo'ladi (prod: XOZMAG 7, BARAKA 1 marta).

   Ikki qatlam:
   1) OMBOR maydonlari (kirim, boshlang'ich qoldiq, priyomka, inventarizatsiya,
      hisobdan chiqarish ...) — 1 000 000 dan katta miqdor RAD etiladi.
      Server ham xuddi shu chegarani tekshiradi (backend/services/quantity_guard.py)
      — bu yerdagisi faqat tezroq va aniqroq xabar uchun.
   2) SOTUV (POS) — to'smaydi, faqat 8+ raqamli butun son kiritilsa
      "bu shtrix-kodga o'xshaydi" deb TASDIQ so'raydi.

   <script src> orqali (modul EMAS) ulanadi — funksiyalar window'ga o'rnatiladi
   (money.js bilan bir xil naqsh), inline skriptlar ham, ES modullar ham chaqira oladi.

   stockQtyError(value)      → xato matni yoki null (ombor maydonlari uchun)
   looksLikeBarcode(raw)     → 8+ raqamli butun son matnimi
   confirmIfBarcode(raw, u)  → shtrix-kodga o'xshasa confirm(); true = davom etish
   ─────────────────────────────────────────────────────────────────────────── */
(function (g) {
  var QTY_STOCK_MAX = 1000000;
  var TOO_BIG_MSG = "Miqdor juda katta — shtrix-kod kiritib qo'ymadingizmi?";

  function looksLikeBarcode(raw) {
    var s = String(raw == null ? '' : raw).replace(/\s+/g, '');
    return /^\d{8,}$/.test(s);
  }

  function stockQtyError(value) {
    var n = Number(value);
    if (value === '' || value == null) return null;   // bo'sh — chaqiruvchining o'z tekshiruvi
    if (!(Math.abs(n) <= QTY_STOCK_MAX)) return TOO_BIG_MSG;
    return null;
  }

  function confirmIfBarcode(raw, unit) {
    if (!looksLikeBarcode(raw)) return true;
    var s = String(raw).replace(/\s+/g, '');
    return g.confirm(
      '"' + s + '" — bu shtrix-kodga o\'xshaydi.\n\n' +
      'Haqiqatan ' + s + (unit ? ' ' + unit : '') + ' kiritmoqchimisiz?'
    );
  }

  g.QTY_STOCK_MAX    = QTY_STOCK_MAX;
  g.QTY_TOO_BIG_MSG  = TOO_BIG_MSG;
  g.looksLikeBarcode = looksLikeBarcode;
  g.stockQtyError    = stockQtyError;
  g.confirmIfBarcode = confirmIfBarcode;
})(window);
