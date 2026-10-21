/**
 * XENORA — "? Yordam" oynasi (do'konchi uchun savol-javob, AI'siz).
 *
 * POS (header) va Admin panel (sidebar pasti) UMUMIY moduli — sales-history.js
 * naqshi: classic <script>, `window.XenoraHelp`. Matn `help-content.js` dan
 * (`window.XENORA_HELP`), u esa `docs/help/*.md` dan yig'iladi
 * (`py scripts/build_help.py`). Bu yerda matn YO'Q — faqat ko'rsatish va qidiruv.
 *
 * Ulash: sahifada `data-help-open` atributli tugma bo'lsa, bosilganda ochiladi.
 *
 * ⚠️ POS'ning global klaviatura tinglovchilari (F2/F4/F8/F9, shtrix-kod skaneri
 * `document` keydown) oyna ichidagi bosishlarni ushlamasin — dialog o'z
 * keydown'ini `stopPropagation` qiladi. Aks holda qidiruvda yozilgan harflar
 * skaner buferiga tushishi yoki F4 to'lov oynasini ochishi mumkin edi.
 *
 * Oyna DOM'i birinchi ochilishda yaratiladi (sahifa yuklanishiga ta'sir yo'q).
 * Uslublar `xh-` prefiksi bilan o'z <style> blokida — admin.css / pos.css ga
 * bog'liq emas, ikkala sahifada bir xil ko'rinadi (qorong'i + oq tema).
 */
(function (g) {
  'use strict';

  var PHONE_TEXT = '+998 94 997 47 70';
  var PHONE_TEL = '+998949974770';
  var STYLE_ID = 'xh-style';

  var root = null;        // .xh-overlay
  var els = {};           // { nav, main, search, dialog }
  var activeSection = null;
  var lastFocus = null;
  var searchTimer = null;

  function data() {
    var d = g.XENORA_HELP;
    return (d && Array.isArray(d.sections)) ? d.sections : [];
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /**
   * Qidiruv uchun normallashtirish: kichik harf, barcha apostrof turlari
   * (o' o‘ oʻ o` g') OLIB TASHLANADI — do'konchi "ogirlik", "og'irlik" yoki
   * "o‘g‘irlik" yozishi mumkin, uchalasi bir xil topilsin.
   */
  function norm(s) {
    return String(s == null ? '' : s)
      .toLowerCase()
      .replace(/[‘’ʻʼ`´']/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  /** So'rov bo'yicha savollar: HAR BIR so'z topilishi shart (AND), savol matnidagi moslik oldinda. */
  function search(query) {
    var words = norm(query).split(' ').filter(function (w) { return w.length > 0; });
    if (!words.length) return [];
    var res = [];
    data().forEach(function (sec) {
      sec.items.forEach(function (it) {
        var q = norm(it.q);
        var hay = q + ' ' + norm(it.keys) + ' ' + norm(sec.title) + ' ' + norm(it.text);
        for (var i = 0; i < words.length; i++) { if (hay.indexOf(words[i]) === -1) return; }
        var score = 0;
        words.forEach(function (w) {
          if (q.indexOf(w) !== -1) score += 3;
          if (norm(it.keys).indexOf(w) !== -1) score += 2;
        });
        res.push({ sec: sec, item: it, score: score });
      });
    });
    res.sort(function (a, b) { return b.score - a.score; });
    return res;
  }

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css = [
      '.xh-overlay{--xh-bg:#11161f;--xh-bg2:#171e2a;--xh-bg3:#202938;--xh-text:#e8edf5;--xh-text2:#a9b4c4;--xh-text3:#7d8899;',
      '--xh-border:rgba(255,255,255,.10);--xh-accent:#22c55e;--xh-accent-ink:#04160d;--xh-note:rgba(245,158,11,.12);--xh-note-b:rgba(245,158,11,.45);',
      'position:fixed;inset:0;z-index:9000;display:none;align-items:center;justify-content:center;padding:1rem;',
      'background:rgba(0,0,0,.62);backdrop-filter:blur(3px);font-family:inherit}',
      '.xh-overlay.xh-open{display:flex}',
      'html[data-theme="light"] .xh-overlay{--xh-bg:#ffffff;--xh-bg2:#f6f8fb;--xh-bg3:#eef2f7;--xh-text:#111827;--xh-text2:#374151;--xh-text3:#6b7280;',
      '--xh-border:rgba(15,23,42,.12);--xh-accent:#16a34a;--xh-accent-ink:#ffffff;--xh-note:rgba(245,158,11,.14);--xh-note-b:rgba(217,119,6,.5)}',
      '.xh-dialog{background:var(--xh-bg);color:var(--xh-text);border:1px solid var(--xh-border);border-radius:16px;',
      'width:min(960px,100%);height:min(640px,calc(100vh - 2rem));display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.45)}',
      '.xh-head{display:flex;align-items:center;gap:.75rem;padding:.875rem 1rem;border-bottom:1px solid var(--xh-border);flex-shrink:0}',
      '.xh-title{font-size:1.05rem;font-weight:700;white-space:nowrap}',
      '.xh-search{flex:1;min-width:0;background:var(--xh-bg3);border:1px solid var(--xh-border);border-radius:10px;padding:.55rem .8rem;',
      'color:var(--xh-text);font-size:.9rem;outline:none;font-family:inherit}',
      '.xh-search:focus{border-color:var(--xh-accent)}',
      // POS'ning umumiy input uslubi (rang/fon) .xh-search dan kuchliroq chiqdi —
      // matn qorong'i fonda ko'rinmasdi. Shu sabab aniq selektor + !important.
      '.xh-overlay input.xh-search{color:var(--xh-text)!important;background:var(--xh-bg3)!important;caret-color:var(--xh-text);',
      '-webkit-text-fill-color:var(--xh-text)}',
      '.xh-overlay input.xh-search::placeholder{color:var(--xh-text3);-webkit-text-fill-color:var(--xh-text3);opacity:1}',
      '.xh-close{width:34px;height:34px;flex-shrink:0;border-radius:9px;border:1px solid var(--xh-border);background:var(--xh-bg3);',
      'color:var(--xh-text2);cursor:pointer;font-size:1rem;line-height:1}',
      '.xh-body{flex:1;display:flex;min-height:0}',
      '.xh-nav{width:210px;flex-shrink:0;border-right:1px solid var(--xh-border);background:var(--xh-bg2);overflow-y:auto;padding:.5rem}',
      '.xh-sec{display:flex;justify-content:space-between;align-items:center;width:100%;text-align:left;gap:.5rem;padding:.6rem .7rem;',
      'margin-bottom:2px;border:0;border-radius:9px;background:transparent;color:var(--xh-text2);font-size:.9rem;cursor:pointer;font-family:inherit}',
      '.xh-sec:hover{background:var(--xh-bg3);color:var(--xh-text)}',
      '.xh-sec.xh-active{background:var(--xh-accent);color:var(--xh-accent-ink);font-weight:700}',
      '.xh-sec small{opacity:.75;font-size:.75rem}',
      '.xh-main{flex:1;min-width:0;overflow-y:auto;padding:1rem 1.25rem 1.5rem}',
      '.xh-h{font-size:1.1rem;font-weight:700;margin:0 0 .75rem}',
      '.xh-item{padding:.875rem 1rem;margin-bottom:.75rem;border:1px solid var(--xh-border);border-radius:12px;background:var(--xh-bg2)}',
      '.xh-q{font-size:.98rem;font-weight:700;margin:0 0 .5rem;color:var(--xh-text)}',
      '.xh-sec-tag{display:inline-block;font-size:.7rem;font-weight:600;color:var(--xh-text3);margin-bottom:.25rem;text-transform:uppercase;letter-spacing:.04em}',
      '.xh-a{font-size:.9rem;line-height:1.55;color:var(--xh-text2)}',
      '.xh-a p{margin:.4rem 0}.xh-a ol,.xh-a ul{margin:.4rem 0;padding-left:1.4rem}.xh-a li{margin:.2rem 0}',
      '.xh-a b{color:var(--xh-text);font-weight:600}',
      '.xh-a code{background:var(--xh-bg3);border-radius:5px;padding:0 .3rem;font-size:.85em}',
      '.xh-note{margin:.5rem 0;padding:.55rem .75rem;border-radius:9px;background:var(--xh-note);border:1px solid var(--xh-note-b);color:var(--xh-text)}',
      '.xh-empty{text-align:center;padding:2rem 1rem;color:var(--xh-text2)}',
      '.xh-call{display:inline-block;margin-top:.75rem;padding:.6rem 1rem;border-radius:10px;background:var(--xh-accent);color:var(--xh-accent-ink);',
      'font-weight:700;text-decoration:none;font-size:1rem}',
      '.xh-foot{flex-shrink:0;padding:.6rem 1rem;border-top:1px solid var(--xh-border);font-size:.82rem;color:var(--xh-text3);text-align:center}',
      '.xh-foot a{color:var(--xh-accent);font-weight:700;text-decoration:none}',
      '@media (max-width:700px){.xh-overlay{padding:0}.xh-dialog{height:100vh;border-radius:0}',
      '.xh-body{flex-direction:column}.xh-nav{width:auto;display:flex;gap:.35rem;overflow-x:auto;overflow-y:hidden;border-right:0;',
      'border-bottom:1px solid var(--xh-border);flex-shrink:0}.xh-sec{width:auto;white-space:nowrap;margin:0}.xh-sec small{display:none}',
      '.xh-title{display:none}}',
    ].join('');
    var st = document.createElement('style');
    st.id = STYLE_ID;
    st.textContent = css;
    document.head.appendChild(st);
  }

  function build() {
    if (root) return;
    injectStyle();
    root = document.createElement('div');
    root.className = 'xh-overlay';
    root.id = 'xhOverlay';
    root.innerHTML =
      '<div class="xh-dialog" role="dialog" aria-modal="true" aria-labelledby="xhTitle">' +
        '<div class="xh-head">' +
          '<div class="xh-title" id="xhTitle">❓ Yordam</div>' +
          '<input class="xh-search" id="xhSearch" type="search" autocomplete="off" ' +
                 'placeholder="Savolingizni yozing... masalan: vozvrat, chek, nasiya" aria-label="Yordamdan qidirish">' +
          '<button type="button" class="xh-close" id="xhClose" title="Yopish (Esc)" aria-label="Yopish">✕</button>' +
        '</div>' +
        '<div class="xh-body">' +
          '<nav class="xh-nav" id="xhNav" aria-label="Bo\'limlar"></nav>' +
          '<div class="xh-main" id="xhMain"></div>' +
        '</div>' +
        '<div class="xh-foot">Javob topilmadimi? Qo\'ng\'iroq qiling: ' +
          '<a href="tel:' + PHONE_TEL + '">' + PHONE_TEXT + '</a></div>' +
      '</div>';
    document.body.appendChild(root);
    els.dialog = root.querySelector('.xh-dialog');
    els.nav = root.querySelector('#xhNav');
    els.main = root.querySelector('#xhMain');
    els.search = root.querySelector('#xhSearch');

    els.nav.innerHTML = data().map(function (sec) {
      return '<button type="button" class="xh-sec" data-xh-sec="' + esc(sec.id) + '">' +
        '<span>' + esc(sec.title) + '</span><small>' + sec.items.length + '</small></button>';
    }).join('');

    els.nav.addEventListener('click', function (e) {
      var b = e.target.closest('[data-xh-sec]');
      if (!b) return;
      els.search.value = '';
      showSection(b.getAttribute('data-xh-sec'));
    });
    root.addEventListener('click', function (e) { if (e.target === root) close(); });
    root.querySelector('#xhClose').addEventListener('click', close);
    els.search.addEventListener('input', function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(runSearch, 120);
    });
    // Dialog ichidagi klaviatura POS/admin global tinglovchilariga chiqmasin.
    root.addEventListener('keydown', function (e) {
      e.stopPropagation();
      if (e.key === 'Escape') { e.preventDefault(); close(); return; }
      if (e.key === 'Enter' && e.target === els.search) { e.preventDefault(); clearTimeout(searchTimer); runSearch(); }
      if (e.key === 'Tab') trapFocus(e);
    });
    // FOKUS QAYTARISH: POS o'zi shtrix-kod maydoniga fokus beradi (yuklangandan
    // 800ms keyin, savat amallaridan keyin...). Oyna ochiq paytda shunday bo'lsa,
    // do'konchi yozgan harflar ORQADAGI POS maydoniga ketardi (test: 1280px da
    // 21 ta bosish hujjatga chiqqan). Ochiq paytda fokus oynadan chiqmaydi.
    document.addEventListener('focusin', function (e) {
      if (isOpen() && !root.contains(e.target)) {
        try { els.search.focus(); } catch (err) { /* fokus ixtiyoriy */ }
      }
    }, true);
  }

  function trapFocus(e) {
    var f = els.dialog.querySelectorAll('button, input, a[href]');
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function itemHtml(sec, it, withTag) {
    return '<article class="xh-item" data-xh-item="' + esc(it.id) + '">' +
      (withTag ? '<div class="xh-sec-tag">' + esc(sec.title) + '</div>' : '') +
      '<h4 class="xh-q">' + esc(it.q) + '</h4>' +
      // it.html — build_help.py da EKRANLANGAN (faqat <b>/<code>/ro'yxat/<p>)
      '<div class="xh-a">' + it.html + '</div></article>';
  }

  function setActiveNav(id) {
    els.nav.querySelectorAll('[data-xh-sec]').forEach(function (b) {
      b.classList.toggle('xh-active', b.getAttribute('data-xh-sec') === id);
    });
  }

  function showSection(id) {
    var secs = data();
    var sec = secs.filter(function (s) { return s.id === id; })[0] || secs[0];
    if (!sec) { els.main.innerHTML = notFoundHtml(''); return; }
    activeSection = sec.id;
    setActiveNav(sec.id);
    els.main.innerHTML = '<h3 class="xh-h">' + esc(sec.title) + '</h3>' +
      sec.items.map(function (it) { return itemHtml(sec, it, false); }).join('');
    els.main.scrollTop = 0;
  }

  function notFoundHtml(q) {
    return '<div class="xh-empty" id="xhNotFound">' +
      (q ? '«' + esc(q) + '» bo\'yicha hech narsa topilmadi.<br>' : '') +
      '<b>Topolmadingizmi? Qo\'ng\'iroq qiling:</b><br>' +
      '<a class="xh-call" href="tel:' + PHONE_TEL + '">📞 ' + PHONE_TEXT + '</a></div>';
  }

  function runSearch() {
    var q = els.search.value;
    if (!norm(q)) { showSection(activeSection); return; }
    var res = search(q);
    setActiveNav(null);
    if (!res.length) { els.main.innerHTML = notFoundHtml(q.trim()); return; }
    els.main.innerHTML = '<h3 class="xh-h">Qidiruv: ' + res.length + ' ta javob</h3>' +
      res.map(function (r) { return itemHtml(r.sec, r.item, true); }).join('');
    els.main.scrollTop = 0;
  }

  function open(opts) {
    build();
    lastFocus = document.activeElement;
    var o = opts || {};
    els.search.value = o.query || '';
    if (o.query) runSearch(); else showSection(o.section || activeSection);
    root.classList.add('xh-open');
    // Darhol (oyna endi ko'rinadi) + keyingi tsiklda yana: sensorli ekranda
    // brauzer fokusni bosilgan tugmaga click'dan KEYIN ham qaytarishi mumkin.
    try { els.search.focus(); } catch (e) { /* fokus ixtiyoriy */ }
    setTimeout(function () { try { if (isOpen()) els.search.focus(); } catch (e) { /* fokus ixtiyoriy */ } }, 0);
  }

  function close() {
    if (!root || !root.classList.contains('xh-open')) return;
    root.classList.remove('xh-open');
    clearTimeout(searchTimer);
    if (lastFocus && typeof lastFocus.focus === 'function') {
      try { lastFocus.focus(); } catch (e) { /* element yo'qolgan bo'lishi mumkin */ }
    }
  }

  function isOpen() { return !!(root && root.classList.contains('xh-open')); }

  function bindButtons() {
    document.querySelectorAll('[data-help-open]').forEach(function (b) {
      if (b._xhBound) return;
      b._xhBound = true;
      b.addEventListener('click', function (e) { e.preventDefault(); open(); });
    });
  }

  g.XenoraHelp = { open: open, close: close, isOpen: isOpen, search: search, norm: norm, phone: PHONE_TEXT };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bindButtons);
  else bindButtons();
})(window);
