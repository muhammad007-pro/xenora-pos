/**
 * REGRESSIYA QO'RIQCHISI: POS navigatsiyasi Electron (`file://`) da sinmasin.
 *
 * JONLI HODISA (1001 BARAKA, 2026-09-10): admin qulf ikonkasi orqali kassir
 * PIN'ini terdi → kassirga o'tdi → Smena sahifasiga kirdi → ORQAGA bosdi →
 * "Kirish taqiqlangan" ekrani → undagi "POS ga" tugmasi → EKRAN QORAYDI.
 *
 * Uch nuqson zanjiri edi:
 *   1. `shift.html` orqaga tugmasi DOIM `admin.html` ga borardi — kassir u
 *      yerga kira olmaydi (AuthGuard PAGE_ROLES: admin/manager) → 403.
 *   2. 403 ekranidagi "POS ga" MUTLAQ yo'l (`/app/pos.html`) ishlatardi.
 *      Electron `loadFile()` bilan `file://` da ishlaydi (main.js:610) —
 *      u yerda bu yo'l DISK ILDIZIGA ishora qiladi, fayl topilmaydi.
 *   3. `did-fail-load` ishlovchisi yo'q edi → xato jimgina yutilardi,
 *      foydalanuvchi qora ekran ko'rardi va sababini bilmasdi.
 *
 * Bu test STATIK (brauzersiz) — uchala nuqsonni ham qulflaydi.
 *
 * Ishga tushirish:  node frontend/tests/test_pos_navigation.js
 */
'use strict';
const fs   = require('fs');
const path = require('path');

const ROOT     = path.resolve(__dirname, '..');
const REPO     = path.resolve(ROOT, '..');
const guardJs  = fs.readFileSync(path.join(ROOT, 'js', 'core', 'auth-guard.js'), 'utf8');
const shiftHtml = fs.readFileSync(path.join(ROOT, 'app', 'shift.html'), 'utf8');
const mainJs   = fs.readFileSync(path.join(REPO, 'electron', 'main.js'), 'utf8');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

// ── 1. 403 ekranidagi "POS ga" havolasi NISBIY ───────────────────────────────
const show403 = guardJs.slice(
  guardJs.indexOf('function show403'),
  guardJs.indexOf('const AuthGuard'),
);
check('1_show403_topildi', show403.length > 0, true);
check('1_mutlaq_yol_YOQ', /href="\/app\//.test(show403), false);
check('1_posPath_ishlatiladi', /href="\$\{pos\}"/.test(show403), true);

// `posPath()` mavjud va mutlaq yo'l qaytarmaydi
const posPathFn = guardJs.slice(
  guardJs.indexOf('function posPath'),
  guardJs.indexOf('function show403'),
);
check('1_posPath_mavjud', posPathFn.length > 0, true);
check('1_posPath_mutlaq_emas', /return\s+['"]\//.test(posPathFn), false);

// Funksiyani haqiqatan yugurtiramiz — uch joylashuv uchun
function makePosPath(pathname) {
  // auth-guard.js dagi mantiqning aynan nusxasi emas — FAYLDAN olinadi
  const body = posPathFn.replace('function posPath()', 'function posPath()');
  const fn = new Function('location', body + '; return posPath();');
  return fn({ pathname });
}
check('2_app_ichida',    makePosPath('/app/shift.html'),      'pos.html');
check('2_shared_ichida', makePosPath('/shared/settings.html'), '../app/pos.html');
check('2_owner_ichida',  makePosPath('/owner/cafes.html'),     '../app/pos.html');

// ── 3. shift.html orqaga tugmasi rolga qarab ────────────────────────────────
check('3_backBtn_id_bor', /id="backBtn"/.test(shiftHtml), true);
check('3_qattiq_admin_html_YOQ',
      /<a href="admin\.html" class="back-btn">/.test(shiftHtml), false);

const backBlock = shiftHtml.slice(
  shiftHtml.indexOf("const btn = document.getElementById('backBtn')"),
  shiftHtml.indexOf('const api = {'),
);
check('3_rol_tekshiriladi', /is_superuser|includes\('admin'\)/.test(backBlock), true);
check('3_admin_admin_htmlga', /'admin\.html'/.test(backBlock), true);
check('3_kassir_pos_htmlga',  /'pos\.html'/.test(backBlock), true);
check('3_history_back_bor',   /history\.back\(\)/.test(backBlock), true);

// Rol mantiqini yugurtirib tekshiramiz (markupdan ajratilgan nusxa)
function uy(user) {
  const rn    = (user.role?.name || user.role || '').toLowerCase();
  const admin = user.is_superuser || rn.includes('admin') || rn.includes('manager') || rn.includes('menej');
  return admin ? 'admin.html' : 'pos.html';
}
check('4_admin',      uy({ role: { name: 'admin' } }),     'admin.html');
check('4_menejer',    uy({ role: { name: 'menejer' } }),   'admin.html');
check('4_manager',    uy({ role: { name: 'manager' } }),   'admin.html');
check('4_superuser',  uy({ is_superuser: true, role: null }), 'admin.html');
check('4_kassir',     uy({ role: { name: 'cashier' } }),   'pos.html');
check('4_ofitsiant',  uy({ role: { name: 'waiter' } }),    'pos.html');
check('4_rolsiz',     uy({}),                              'pos.html');
// `role` matn sifatida kelsa ham ishlasin (eski localStorage yozuvlari)
check('4_rol_matn',   uy({ role: 'admin' }),               'admin.html');

// ── 5. Electron did-fail-load ishlovchisi ────────────────────────────────────
check('5_did_fail_load_bor', /did-fail-load/.test(mainJs), true);
const failBlock = mainJs.slice(
  mainJs.indexOf("'did-fail-load'"),
  mainJs.indexOf("// Server health"),
);
check('5_konsolga_yoziladi', /console\.error/.test(failBlock), true);
check('5_aborted_otkazib_yuboriladi', /errorCode === -3/.test(failBlock), true);
check('5_faqat_asosiy_freym', /isMainFrame/.test(failBlock), true);
check('5_xabar_korsatiladi', /Sahifa ochilmadi/.test(failBlock), true);
check('5_xavfsiz_sahifaga', /pos\.html/.test(failBlock), true);

// ── 6. Mavjud navigatsiya buzilmagan ────────────────────────────────────────
// POS sidebar'idagi Smena havolasi (v1.12.9) va rollar joyida
const posHtml = fs.readFileSync(path.join(ROOT, 'app', 'pos.html'), 'utf8');
check('6_pos_smena_havolasi',
      /href="shift\.html"[^>]*data-roles="admin manager cashier"/.test(posHtml), true);
// POS sidebar'ida mutlaq yo'l yo'q (hammasi nisbiy)
check('6_pos_sidebarda_mutlaq_yol_yoq',
      /<a href="\/app\//.test(posHtml), false);
// AuthGuard'da shift sahifasi kassirga ochiq (v1.12.9 oqimi buzilmasin)
check('6_shift_kassirga_ochiq',
      /'shift':\s*\['admin','manager','cashier','kassir'\]/.test(guardJs), true);
check('6_admin_kassirga_yopiq',
      /'admin':\s*\['admin','manager'\]/.test(guardJs), true);

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
