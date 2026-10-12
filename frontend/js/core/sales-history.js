/* XENORA — Sotuvlar tarixi: sana oralig'i + kunlar bo'yicha guruhlash.
 *
 * POS (salesHistoryModal) va admin (pageSalesHistory) UMUMIY yordamchisi.
 * CLASSIC skript — `window.XenoraSalesHistory` ga ulanadi (product-photo.js
 * naqshi): admin'ning classic core.js i ham, POS moduli ham shu yerdan oladi.
 *
 * Faqat SOF funksiyalar (DOM'ga tegmaydi) — test_sales_history_ui.mjs ularni
 * vm sandbox'da to'g'ridan sinaydi.
 *
 * Kun chegarasi (kalendar / smena) SERVERDA hisoblanadi: `GET /orders/history`
 * har chekka `business_date` va har kunga jami beradi. Bu yerda faqat
 * ko'rsatish — frontend kun chegarasini O'ZI hisoblamaydi (aks holda smena
 * rejimida ekran va hisobot boshqa-boshqa narsa ko'rsatardi).
 */
(function (root) {
  'use strict';

  /** 'YYYY-MM-DD' ± kun (UTC arifmetika — zona/DST siljishisiz). */
  function addDays(iso, n) {
    const [y, m, d] = String(iso).split('-').map(Number);
    const t = new Date(Date.UTC(y, m - 1, d + n));
    return t.toISOString().slice(0, 10);
  }

  /** Brauzerning mahalliy bugungi sanasi 'YYYY-MM-DD' (toISOString UTC beradi — ishlatilmaydi). */
  function localToday(now) {
    const t = now || new Date();
    const p = n => String(n).padStart(2, '0');
    return `${t.getFullYear()}-${p(t.getMonth() + 1)}-${p(t.getDate())}`;
  }

  /** Tayyor davrlar: 'today' | 'yesterday' | 'week' (7 kun) | 'month' (30 kun). */
  function presetRange(key, todayIso) {
    const t = todayIso;
    switch (key) {
      case 'today':     return { from: t, to: t };
      case 'yesterday': { const y = addDays(t, -1); return { from: y, to: y }; }
      case 'week':      return { from: addDays(t, -6),  to: t };
      case 'month':     return { from: addDays(t, -29), to: t };
      default:          return null;
    }
  }

  /** Cheklarni KELGAN TARTIBDA (yangisi birinchi) kunlarga bo'ladi. */
  function groupByDay(items) {
    const out = [];
    let cur = null;
    for (const it of items || []) {
      const d = it.business_date || null;
      if (!cur || cur.date !== d) { cur = { date: d, items: [] }; out.push(cur); }
      cur.items.push(it);
    }
    return out;
  }

  const _WD = ['yakshanba', 'dushanba', 'seshanba', 'chorshanba', 'payshanba', 'juma', 'shanba'];

  /** '2026-10-10' → '10.10.2026, shanba' */
  function dayLabel(iso) {
    if (!iso) return '—';
    const [y, m, d] = iso.split('-').map(Number);
    const wd = _WD[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
    return `${String(d).padStart(2, '0')}.${String(m).padStart(2, '0')}.${y}, ${wd}`;
  }

  /** {date → {count,total,other}} — sarlavhada kunning TO'LIQ jami (sahifadan mustaqil). */
  function dayMap(days) {
    const m = {};
    for (const d of days || []) m[d.date] = d;
    return m;
  }

  /** Davr sarlavhasi: '08.10.2026 — 12.10.2026' (bir kun bo'lsa bitta sana). */
  function rangeLabel(from, to) {
    const f = iso => { const [y, m, d] = iso.split('-'); return `${d}.${m}.${y}`; };
    if (!from) return '';
    return from === to || !to ? f(from) : `${f(from)} — ${f(to)}`;
  }

  root.XenoraSalesHistory = { addDays, localToday, presetRange, groupByDay, dayLabel, dayMap, rangeLabel };
})(typeof window !== 'undefined' ? window : globalThis);
