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

  /* ── NARX qo'riqchisi (2026-10-14) ───────────────────────────────────────────
     Skaner shtrix-kodni narx/tan narx maydoniga QO'SHIB yuboradi: "12000" +
     "4780019480…" = 1.2e17 (audit: 11 marta, 3 do'kon; BARAKA "Ombor qiymati"
     95,6 trln). Server chegarasi: backend/services/price_guard.py — 1 mlrd.
       • 1 000 000 000 dan katta → RAD (alert, false)
       • 8+ raqamli butun son (masalan bo'sh maydonga EAN-8) → TASDIQ (confirm)
     Maydon formatlangan bo'lishi mumkin ("7,000") — ajratgichlar olib tashlanadi. */
  var PRICE_MAX = 1000000000;
  var PRICE_TOO_BIG_MSG = "Narx juda katta — shtrix-kod narx maydoniga tushib qolmadimi?";

  function _priceDigits(raw) {
    return String(raw == null ? '' : raw).replace(/[\s,]/g, '');
  }

  function priceError(value) {
    if (value === '' || value == null) return null;
    var n = Number(_priceDigits(value));
    if (!(Math.abs(n) <= PRICE_MAX)) return PRICE_TOO_BIG_MSG;
    return null;
  }

  // true = davom etish. `label` — "Narx", "Tan narx" ...
  function guardPrice(raw, label) {
    var s = _priceDigits(raw);
    if (s === '') return true;
    var err = priceError(s);
    if (err) {
      g.alert((label ? label + ': ' : '') + err + '\n\nKiritildi: ' + s +
              '\nRuxsat: 1 000 000 000 so\'m gacha.');
      return false;
    }
    var intPart = s.split('.')[0].replace(/^-/, '');
    if (/^\d{8,}$/.test(intPart)) {
      return g.confirm((label ? label + ': ' : '') + '"' + s + '" — 8 xonali son, shtrix-kodga o\'xshaydi.\n\n' +
                       'Haqiqatan ' + Number(s).toLocaleString('en-US') + ' so\'m kiritmoqchimisiz?');
    }
    return true;
  }

  g.PRICE_MAX         = PRICE_MAX;
  g.priceError        = priceError;
  g.guardPrice        = guardPrice;
  g.QTY_STOCK_MAX    = QTY_STOCK_MAX;
  g.QTY_TOO_BIG_MSG  = TOO_BIG_MSG;
  g.looksLikeBarcode = looksLikeBarcode;
  g.stockQtyError    = stockQtyError;
  g.confirmIfBarcode = confirmIfBarcode;
})(window);
