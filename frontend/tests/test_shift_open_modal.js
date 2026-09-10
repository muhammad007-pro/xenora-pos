/**
 * REGRESSIYA QO'RIQCHISI: admin "Smena ochish" oynasida xodim TANLANMAYDI.
 *
 * MUAMMO: `create_shift` (v1.12.9 dan) smenani har doim so'rov yuborgan
 * xodimga ochadi — boshqa `user_id` yuborilsa 403. Admin panelidagi xodim
 * tanlash `<select id="shiftUser">` esa qolgan edi: admin kassirni tanlab
 * "Ochish" bosardi va 403 olardi. Ya'ni UI bajarib bo'lmaydigan va'da
 * berardi.
 *
 * Endi o'sha joyda faqat JORIY foydalanuvchi nomi ko'rsatiladi.
 *
 * Bu test STATIK (brauzersiz) — `node --check` kabi arzon, CI'da tez.
 *
 * Ishga tushirish:  node frontend/tests/test_shift_open_modal.js
 */
'use strict';
const fs   = require('fs');
const path = require('path');

const ROOT     = path.resolve(__dirname, '..');
const adminHtml = fs.readFileSync(path.join(ROOT, 'app', 'admin.html'), 'utf8');
const shiftJs   = fs.readFileSync(path.join(ROOT, 'js', 'admin', 'shift.js'), 'utf8');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

// `#shiftUser` hali ham bor (yorliq joyida qoladi), LEKIN <select> emas.
check('shiftUser_mavjud', /id="shiftUser"/.test(adminHtml), true);
check('shiftUser_select_EMAS', /<select[^>]*id="shiftUser"/.test(adminHtml), false);

// Foydalanuvchiga smena kimga ochilishi tushuntiriladi.
check('tushuntirish_matni', /Smena o'zingizga ochiladi/.test(adminHtml), true);

// `openShiftModal` endi xodim ro'yxatini TORTMAYDI.
const modalFn = shiftJs.slice(
  shiftJs.indexOf('async function openShiftModal'),
  shiftJs.indexOf('async function openShift(')
);
check('modal_funksiya_topildi', modalFn.length > 0, true);
check('users_sorovi_yoq', /['"]\/users\//.test(modalFn), false);
check('joriy_user_korsatiladi', /getUser\(\)/.test(modalFn), true);

// `openShift` boshqa xodim id sini YUBORMAYDI — select .value o'qilmaydi.
const openFn = shiftJs.slice(
  shiftJs.indexOf('async function openShift('),
  shiftJs.indexOf('async function openCloseShiftModal')
);
check('select_value_oqilmaydi', /getElementById\('shiftUser'\)\.value/.test(openFn), false);
check('oz_id_yuboriladi', /user_id:\s*getUser\(\)\.id/.test(openFn), true);

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
