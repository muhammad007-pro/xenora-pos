/**
 * Tarif katalogi — FRONTEND TOMONDAGI YAGONA MANBA (2026-08-27, uch tarif).
 *
 * MUAMMO (bungacha): tarif nomi va NARXI to'rt-besh joyda qo'lda yozilgan edi va
 * bir-biriga ZID edi:
 *     backend  routers/super_admin.py PLAN_PRICES : free=$10,  pro=$50   (USD)
 *     frontend owner/subscriptions.html            : free=0,    pro=990000 (UZS)
 * Ya'ni moliya paneli Boshlang'ich mijozni pullik, mijoz ekrani "bepul" deb
 * ko'rsatardi. Narxni o'zgartirish uchun 5 faylni qidirib chiqish kerak edi.
 *
 * ENDI:
 *   • NOM   — shu fayldagi statik xarita (tez, tarmoqqa bog'liq emas; nom kamdan-kam
 *             o'zgaradi va badge chizish uchun so'rov kutib turish mantiqsiz).
 *   • NARX  — HAR DOIM backenddan: GET /super-admin/plans (core/subscription.PLAN_PRICES_UZS).
 *             Bu yerda narx QATTIQ YOZILMAYDI — zid bo'lib qolmasin.
 *
 * <script src="../js/core/plans.js"></script> — modul EMAS, oddiy skript
 * (owner sahifalari inline skript ishlatadi).
 */
(function () {
  'use strict';

  // Kod (DB qiymati) -> ko'rinadigan nom. Kodlar ATAYLAB o'zgartirilmaydi:
  // 'free' bazada qoladi, ekranda "Boshlang'ich" deb ko'rinadi.
  var NAMES = {
    free:       "Boshlang'ich",
    standart:   'Standart',
    pro:        'Pro',
    enterprise: 'Enterprise',
  };

  var TARTIB = ['free', 'standart', 'pro'];   // ko'rsatish tartibi (arzondan qimmatga)

  var _prices = null;   // backenddan keladi; null = hali yuklanmagan

  function planName(code) {
    if (!code) return NAMES.free;
    return NAMES[String(code).toLowerCase()] || String(code);
  }

  function fmtSom(n) {
    if (n == null) return '—';
    return Number(n).toLocaleString('en-US') + ' UZS';
  }

  /** Narx (UZS). Yuklanmagan bo'lsa null — chaqiruvchi "—" ko'rsatadi. */
  function planPrice(code) {
    if (!_prices) return null;
    var v = _prices[String(code).toLowerCase()];
    return (v === undefined) ? null : v;
  }

  /** "Standart — 449,000 UZS/oy" ko'rinishidagi yorliq (dropdown uchun). */
  function planLabel(code) {
    var p = planPrice(code);
    return planName(code) + (p == null ? '' : ' — ' + fmtSom(p) + '/oy');
  }

  /**
   * Backenddan narx/limitlarni yuklaydi. `apiGet` — sahifaning o'z helperi
   * (masalan `api.get`), `/super-admin/plans` ni chaqiradi.
   * Xato bo'lsa jim o'tadi: nom baribir ko'rinadi, narx "—" bo'lib qoladi.
   */
  async function loadPlans(apiGet) {
    try {
      var res = await apiGet('/super-admin/plans');
      var d = (res && res.data) ? res.data : res;
      if (!d || !Array.isArray(d.plans)) return null;
      _prices = {};
      d.plans.forEach(function (p) { _prices[p.code] = p.price_uzs; });
      return d.plans;
    } catch (e) {
      return null;
    }
  }

  window.XENORA_PLANS = {
    NAMES: NAMES,
    ORDER: TARTIB,
    planName: planName,
    planPrice: planPrice,
    planLabel: planLabel,
    loadPlans: loadPlans,
    fmtSom: fmtSom,
  };
  // Qisqa yo'l — inline skriptlarda qulay
  window.planName = planName;
})();
