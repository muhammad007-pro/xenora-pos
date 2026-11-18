/* ─────────────────────────────────────────────────────────────────────────────
   Toshkent sanasi/vaqti — YAGONA MANBA (classic <script src>, money.js naqshi:
   funksiyalar window ga o'rnatiladi; inline skriptlar ham, ES modullar ham oladi).

   NEGA: `new Date().toISOString().slice(0,10)` — UTC sana. Toshkent 00:00–05:00
   oralig'ida u KECHAGI sanani beradi ("bugun" filtri kechani ko'rsatadi, sana
   maydoni kecha bilan to'ladi). Server vaqtini `iso.slice(0,16)` bilan kesish
   esa UTC soatni ko'rsatadi (5 soat orqada; MANHATTAN smena ro'yxati 2026-10).
   Hisobotlar Toshkent kuni bo'yicha — ekran ham shunday bo'lsin, qurilma
   zonasidan qat'i nazar.

   tkYmd(v?)      → 'YYYY-MM-DD'        (v yo'q = hozir)
   tkYmdHm(v?)    → 'YYYY-MM-DDTHH:MM'  (datetime-local input qiymati)
   tkDateTime(v)  → 'YYYY-MM-DD HH:MM'  (ekranda; avvalgi slice formati)
   tkMonthStart() → 'YYYY-MM-01'        (joriy oy boshi)
   tkAddDays(ymd, n) → 'YYYY-MM-DD'     (sof sana arifmetikasi, zonasiz)

   Kirish: Date | ms | server satri. Zonasiz satr ("2026-10-24T19:02:09") UTC
   deb o'qiladi (backend shartnomasi); faqat sana satri ("2026-10-24") — sana
   sifatida, siljitilmaydi. Bo'sh/yaroqsiz/undefined → ''.
   ⚠️ "Hozir" FAQAT argumentsiz chaqiruvda: `tkYmd(o.created_at)` maydon yo'q
   bo'lsa bugungi sanani emas, '' beradi (avvalgi `(x||'').slice` kabi).
   ───────────────────────────────────────────────────────────────────────────── */
(function (g) {
  var FMT = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Tashkent', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  });
  var DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

  function parts(v) {
    if (v === undefined || v === null || v === '') return null;
    if (typeof v === 'string') {
      var s = v.trim();
      if (DATE_ONLY.test(s)) return { y: s.slice(0, 4), m: s.slice(5, 7), d: s.slice(8, 10), H: '00', M: '00' };
      v = new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(s) ? s : s + 'Z');
    } else if (!(v instanceof Date)) {
      v = new Date(v);
    }
    if (isNaN(v)) return null;
    var p = {};
    FMT.formatToParts(v).forEach(function (x) { p[x.type] = x.value; });
    return { y: p.year, m: p.month, d: p.day, H: p.hour, M: p.minute };
  }

  function tkYmd(v)     { var p = parts(arguments.length ? v : new Date()); return p ? p.y + '-' + p.m + '-' + p.d : ''; }
  function tkYmdHm(v)   { var p = parts(arguments.length ? v : new Date()); return p ? p.y + '-' + p.m + '-' + p.d + 'T' + p.H + ':' + p.M : ''; }
  function tkDateTime(v) { var p = parts(v); return p ? p.y + '-' + p.m + '-' + p.d + ' ' + p.H + ':' + p.M : ''; }
  function tkMonthStart() { return tkYmd().slice(0, 8) + '01'; }
  function tkAddDays(ymd, n) {
    var a = String(ymd).split('-').map(Number);
    return new Date(Date.UTC(a[0], a[1] - 1, a[2] + n)).toISOString().slice(0, 10);
  }

  g.tkYmd = tkYmd;
  g.tkYmdHm = tkYmdHm;
  g.tkDateTime = tkDateTime;
  g.tkMonthStart = tkMonthStart;
  g.tkAddDays = tkAddDays;
})(window);
