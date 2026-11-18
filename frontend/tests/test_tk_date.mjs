/**
 * TOSHKENT SANASI (fix/small-issues) — js/core/tk-date.js + ishlatuvchi sahifalar.
 *
 * MUAMMO: `new Date().toISOString().slice(0,10)` UTC sana — Toshkent 00:00–05:00
 * da KECHA. Server vaqtini `iso.slice(0,16)` bilan kesish UTC soatni ko'rsatardi
 * (ombor harakatlari, inventarizatsiya, narx tarixi, bonus karta...). Mahalliy
 * yarim tunni `toISOString()` qilish esa oy boshini o'tgan oyning oxirgi kuniga
 * aylantirardi (price_history, food oylik hisobot, salon_analytics).
 *
 * Qotiriladi:
 *   1) tkYmd/tkYmdHm/tkDateTime/tkAddDays/tkMonthStart — zona, chegara, bo'sh qiymat
 *   2) "hozir" Toshkent 03:30 (UTC kecha 22:30) → bugungi Toshkent sanasi
 *   3) tk* ishlatgan har sahifa tk-date.js ni yuklaydi; jonli fayllarda UTC "bugun" yo'q
 *
 * Ishga tushirish:  node frontend/tests/test_tk_date.mjs
 */
import { readFileSync, readdirSync, existsSync } from 'fs';
import { resolve, join } from 'path';
import vm from 'node:vm';

const ROOT = resolve('frontend');
const rd = p => readFileSync(resolve(ROOT, p), 'utf8');
let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

/** tk-date.js ni "hozir" = fixedIso bo'lgan sandbox'da yuklaydi. */
function load(fixedIso) {
  const FIXED = fixedIso ? Date.parse(fixedIso) : null;
  class FakeDate extends Date {
    constructor(...a) { super(...(a.length || FIXED == null ? a : [FIXED])); }
    static now() { return FIXED == null ? Date.now() : FIXED; }
  }
  const ctx = { window: {}, Intl, Date: FIXED == null ? Date : FakeDate };
  vm.createContext(ctx);
  vm.runInContext(rd('js/core/tk-date.js'), ctx);
  return ctx.window;
}

console.log('\n── 1) Funksiyalar ──');
const t = load();
check('1_utc_kechqurun_toshkentda_ertasi', t.tkYmd(new Date('2026-10-23T19:02:09Z')), '2026-10-24');
check('1_zonasiz_satr_UTC', t.tkYmd('2026-10-23T19:02:09.981743'), '2026-10-24');
check('1_offsetli_satr', t.tkYmd('2026-10-24T00:02:09+05:00'), '2026-10-24');
check('1_faqat_sana_siljimaydi', t.tkYmd('2026-10-24'), '2026-10-24');
check('1_bosh_qiymatlar', [t.tkYmd(undefined), t.tkYmd(null), t.tkYmd(''), t.tkDateTime(undefined), t.tkYmd('xato')], ['', '', '', '', '']);
check('1_tkDateTime_89', t.tkDateTime('2026-10-22T18:57:40.232084Z'), '2026-10-22 23:57');
check('1_tkYmdHm', t.tkYmdHm(new Date('2026-10-23T20:30:00Z')), '2026-10-24T01:30');
check('1_addDays_oy_chegarasi', [t.tkAddDays('2026-10-31', 1), t.tkAddDays('2026-03-01', -1), t.tkAddDays('2024-02-28', 1)],
      ['2026-11-01', '2026-02-28', '2024-02-29']);
// food.js oylik hisobot: oyning oxirgi kuni
const lastDay = first => t.tkAddDays(t.tkAddDays(first, 31).slice(0, 8) + '01', -1);
check('1_oy_oxiri', [lastDay('2026-02-01'), lastDay('2026-12-01'), lastDay('2026-10-01')], ['2026-02-28', '2026-12-31', '2026-10-31']);

console.log('\n── 2) "Hozir" = Toshkent 03:30 (UTC 22:30, kecha) ──');
const n = load('2026-10-24T22:30:00Z');
check('2_eski_usul_KECHA_edi', new Date(Date.parse('2026-10-24T22:30:00Z')).toISOString().slice(0, 10), '2026-10-24');
check('2_tkYmd_bugun', n.tkYmd(), '2026-10-25');
check('2_tkYmdHm', n.tkYmdHm(), '2026-10-25T03:30');
check('2_oy_boshi', n.tkMonthStart(), '2026-10-01');
const m = load('2026-10-31T20:00:00Z');   // Toshkent 01.11 01:00
check('2_oy_almashuvida_oy_boshi', m.tkMonthStart(), '2026-11-01');

console.log('\n── 3) Sahifalar ──');
const USES = /\btk(Ymd|YmdHm|DateTime|MonthStart|AddDays)\(/;
// tk* ni ishlatuvchi JS → uni yuklovchi sahifa
const HOSTS = { 'js/admin/': 'app/admin.html', 'js/modules/pos.js': 'app/pos.html',
                'js/modules/attendance.js': 'app/attendance.html', 'js/payments.js': 'payments.html' };
const need = new Set();
for (const [prefix, page] of Object.entries(HOSTS)) {
  const files = prefix.endsWith('/') ? readdirSync(resolve(ROOT, prefix)).map(f => prefix + f) : [prefix];
  if (files.some(f => USES.test(rd(f)))) need.add(page);
}
for (const dir of ['app', 'owner', '.']) {
  for (const f of readdirSync(resolve(ROOT, dir)).filter(f => f.endsWith('.html'))) {
    const p = dir === '.' ? f : `${dir}/${f}`;
    if (USES.test(rd(p))) need.add(p);
  }
}
const missing = [...need].filter(p => !/<script src="(\.\.\/)?js\/core\/tk-date\.js"><\/script>/.test(rd(p)));
check('3_tk_date_yuklanadi', missing, []);
check('3_sahifalar_soni_kamida_20', need.size >= 20, true);
// Yuklash tartibi: tk-date.js birinchi ishlatilishdan OLDIN
const late = [...need].filter(p => {
  const s = rd(p), inc = s.search(/js\/core\/tk-date\.js/);
  const use = s.search(USES);
  return use >= 0 && use < inc;
});
check('3_yuklash_ishlatishdan_oldin', late, []);
// Jonli fayllarda UTC "bugun" qolmagan (o'lik modullar — hech bir sahifa yuklamaydi — tashqarida)
const LIVE = ['js/admin/inventory.js', 'js/admin/drycleaning.js', 'js/admin/school.js', 'js/admin/auto.js',
              'js/admin/store.js', 'js/admin/hotel.js', 'js/admin/food.js', 'js/admin/salon.js',
              'js/payments.js', 'js/modules/pos.js', 'js/modules/attendance.js', ...[...need].filter(p => p.endsWith('.html'))];
const UTC_TODAY = /new Date\(\)\.toISOString\(\)\.(slice|split)|_at\s*\|\|\s*''\)\.slice\(0|_at\.slice\(0,\s*1[06]\)|_at\?\.split\('T'\)/;
check('3_utc_bugun_qolmagan', LIVE.filter(p => existsSync(join(ROOT, p)) && UTC_TODAY.test(rd(p))), []);
check('3_sw_keshda', /'\/js\/core\/tk-date\.js'/.test(rd('service-worker.js')), true);

console.log(`\n${pass} OK, ${fail} FAIL`);
process.exit(fail ? 1 : 0);
