/* ─────────────────────────────────────────────────────────────────────────────
   Umumiy pul formati — BARCHA sahifada bir xil vergulli minglik ajratgich.
   Ilgari har sahifa o'zicha formatlar edi: POS 'en-US' (770,000), admin 'uz-UZ'
   (770 000 — bo'sh joy), report Intl 'uz-UZ' → chalkash ko'rinish. Bu modul yagona
   manba: hamma joyda vergul (770,000). <script src> orqali (modul EMAS) ulanadi —
   funksiyalar window ga o'rnatiladi, inline skriptlar to'g'ridan chaqira oladi.

   fmtMoney(n)  → "770,000"  (butun, birliksiz — chaqiruvchi ' UZS'/' so'm' qo'shadi)
   fmtNum(n)    → fmtMoney alias (POS moslik)
   parseMoney(s)→ "770,000" → 770000  (formatlangan matndan sof raqam)
   attachMoneyInput(el) → input'ga jonli minglik format ulaydi (yozganda 770000→770,000)
   ───────────────────────────────────────────────────────────────────────────── */
(function (g) {
  function fmtMoney(n) {
    return Math.round(Number(n) || 0).toLocaleString('en-US');
  }
  function parseMoney(str) {
    return parseFloat(String(str == null ? '' : str).replace(/[^\d.]/g, '')) || 0;
  }
  function attachMoneyInput(el) {
    if (!el || el._moneyBound) return;
    el._moneyBound = true;
    // type=number vergulni qabul qilmaydi — matnli inputga o'tkazamiz.
    if (el.getAttribute('type') === 'number') {
      el.setAttribute('type', 'text');
      el.setAttribute('inputmode', 'numeric');
    }
    el.addEventListener('input', function () {
      var digits = el.value.replace(/[^\d]/g, '');
      el.value = digits ? Number(digits).toLocaleString('en-US') : '';
    });
  }

  // MIQDOR (ombor qoldig'i, kg/l) — 3 xonagacha, oxiridagi nollarsiz:
  // 8.665000000000001 → "8.665", 2.5 → "2.5", 3 → "3". Float qo'shish xatosi
  // (0.265 + 8.4) ekranga uzun son bo'lib chiqmasin. Server ham 3 xonada saqlaydi.
  function fmtQty(n) {
    var v = Math.round((Number(n) || 0) * 1000) / 1000;
    return String(v === 0 ? 0 : v);   // -0 → "0"
  }

  g.fmtMoney = fmtMoney;
  g.fmtQty = fmtQty;
  g.fmtNum = fmtMoney;          // POS/eski moslik
  g.parseMoney = parseMoney;
  g.attachMoneyInput = attachMoneyInput;
})(window);
