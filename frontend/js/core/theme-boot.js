/* ═══════════════════════════════════════════════════════════════════════════
   XENORA — TEMA (qora/oq) YAGONA YUKLOVCHISI
   ───────────────────────────────────────────────────────────────────────────
   ULANISH: <head> ichida, CSS'lardan OLDIN, ODDIY (modul emas, defer/async
   emas) skript sifatida:   <script src="../js/core/theme-boot.js"></script>

   NEGA (2026-10, jonli shikoyat "oq rejimda ba'zi panellar qora bo'ladi"):
     • app/ sahifalarining ko'pi temani UMUMAN o'qimasdi → har doim qora;
     • admin.html / pos.html temani <body> OXIRIDAGI skriptda qo'yardi →
       sahifa avval qora chizilib, keyin oqqa sakrardi (miltillash);
     • iframe (admin ichidagi Firmalar) boshqa oynada almashtirilgan temani
       bilmasdi.
   Bu fayl: saqlangan tanlovni CHIZISHDAN OLDIN qo'yadi, boshqa oyna/iframe
   almashtirsa darhol ergashadi (`storage` hodisasi) va o'z tugmasi yo'q
   sahifaga tema tugmasini qo'shadi.

   KALIT: localStorage 'theme' = 'dark' | 'light' (admin/pos/login bilan bir
   xil — ular o'zgarishsiz ishlayveradi). Sukut — 'dark' (avvalgidek).
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  var KEY = 'theme';
  var html = document.documentElement;

  function read() {
    try { var t = localStorage.getItem(KEY); return t === 'light' ? 'light' : 'dark'; }
    catch (e) { return 'dark'; }
  }

  function syncIcons(t) {
    // Sahifalarning o'z tugmalaridagi quyosh/oy ikonkalari (admin, pos, theme.js)
    var sun = document.getElementById('themeIconSun'), moon = document.getElementById('themeIconMoon');
    if (sun) sun.style.display = t === 'light' ? '' : 'none';
    if (moon) moon.style.display = t === 'dark' ? '' : 'none';
    var own = document.getElementById('xnThemeBtn');
    if (own) {
      own.textContent = t === 'light' ? '☾' : '☀';
      own.title = t === 'light' ? 'Qora rejim' : 'Oq rejim';
    }
  }

  function apply(t, save) {
    t = t === 'light' ? 'light' : 'dark';
    html.setAttribute('data-theme', t);
    if (save) { try { localStorage.setItem(KEY, t); } catch (e) { /* xususiy rejim */ } }
    syncIcons(t);
  }

  // 1) Chizishdan OLDIN — miltillash yo'q
  apply(read(), false);

  // 2) Boshqa oyna / iframe / admin tugmasi almashtirsa — ergashamiz
  window.addEventListener('storage', function (e) {
    if (e.key === KEY || e.key === null) apply(read(), false);
  });
  // bfcache'dan qaytganda (← tugmasi) eski tema qolmasin
  window.addEventListener('pageshow', function () { apply(read(), false); });

  window.XenoraTheme = {
    get: function () { return html.getAttribute('data-theme') === 'light' ? 'light' : 'dark'; },
    set: function (t) { apply(t, true); },
    toggle: function () { var n = this.get() === 'light' ? 'dark' : 'light'; apply(n, true); return n; },
  };

  // 3) Tugma — sahifada O'Z tema tugmasi bo'lmasa. iframe ichida qo'shilmaydi
  //    (tashqi oynadagi tugma boshqaradi, `storage` orqali yetib keladi).
  var OWN = '#themeToggleBtn,#themeBtn,.theme-toggle,[data-theme-toggle]';
  function addButton() {
    if (window.self !== window.top) return;
    if (document.body && document.body.hasAttribute('data-no-theme-btn')) return;
    if (document.querySelector(OWN) || document.getElementById('xnThemeBtn')) return;
    var b = document.createElement('button');
    b.type = 'button';
    b.id = 'xnThemeBtn';
    b.setAttribute('data-theme-toggle', '');
    b.setAttribute('aria-label', 'Tema');
    b.addEventListener('click', function () { window.XenoraTheme.toggle(); });
    // Sarlavha bo'lsa — uning oxiriga; bo'lmasa — ekran burchagiga
    var host = document.querySelector('.ph,.page-header,.topbar,.header,header');
    b.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;'
      + 'width:36px;height:36px;border-radius:10px;cursor:pointer;font-size:1.05rem;line-height:1;'
      + 'border:1px solid rgba(34,197,94,.35);background:rgba(34,197,94,.1);color:#22c55e;';
    if (host) {
      b.style.marginLeft = 'auto';
      host.appendChild(b);
    } else {
      b.style.position = 'fixed';
      b.style.left = '12px';
      b.style.bottom = '12px';
      b.style.zIndex = '9000';
      document.body.appendChild(b);
    }
    syncIcons(window.XenoraTheme.get());
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addButton);
  else addButton();
})();
