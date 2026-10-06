/**
 * POS sidebar: "Ombor" bandi olib tashlandi + shablon-izoh sintaksis tuzog'i.
 *
 * ═══ MUAMMO (v1.13.0, jonli) ═══
 * POS sidebar'idagi "Ombor" (`inventory.html`) ochilmasdi — abadiy skeleton.
 * Sabab: sahifa skriptidagi JS SHABLON (`...`) ICHIGA `<!-- -->` izoh
 * yozilgan va izohdagi backtick shablonni yopib, BUTUN skriptni sintaksis
 * xatosiga tushirgan (v1.12.10 dan). `customers.html` (Mijozlar) da AYNAN
 * shu xato v1.12.14 dan beri bor edi.
 *
 * `scripts/check_syntax.py` buni ushlamagan: HTML izohlarini skriptni
 * ajratishdan OLDIN butun fayldan o'chirardi — ya'ni buzuq qismni o'zi
 * olib tashlab, toza kodni tekshirardi.
 *
 * Ishga tushirish:  node frontend/tests/test_pos_sidebar_ombor.mjs
 */
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'fs';
import { resolve, join } from 'path';
import { tmpdir } from 'os';
import { spawnSync } from 'child_process';
import vm from 'node:vm';

const rd = p => readFileSync(resolve(p), 'utf8');
let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

// ── 1) POS sidebar ─────────────────────────────────────────────────────────
console.log('\n── 1) POS sidebar ──');
const POS = rd('frontend/app/pos.html');
const sidebar = POS.match(/<aside class="sidebar"[\s\S]*?<\/aside>/)?.[0] || '';
check('1_sidebar_topildi', sidebar.length > 0, true);
check('1_Ombor_havolasi_YOQ', /<a[^>]*href="inventory\.html"/.test(sidebar), false);
check('1_Ombor_yorligi_YOQ', /nav-label">Ombor</.test(sidebar), false);
// GOLDEN: qolgan bandlar joyida
check('1_GOLDEN_Qoldiq_modali_bor', /id="posStockBtn"/.test(sidebar), true);
for (const href of ['pos.html', 'customers.html', 'returns.html', 'shift.html', 'admin.html']) {
  check(`1_GOLDEN_${href}`, new RegExp(`<a[^>]*href="${href.replace('.', '\\.')}"`).test(sidebar), true);
}

// ── 2) Sahifalar skripti HAQIQATAN parse bo'ladi ───────────────────────────
// (check_syntax.py dan MUSTAQIL — xom manba, izohlar o'chirilmaydi)
console.log('\n── 2) inventory.html / customers.html skripti ──');
function classicErrors(path) {
  const src = rd(path);
  const re = /<!--[\s\S]*?-->|<script([^>]*)>([\s\S]*?)<\/script>/g;
  const errs = []; let m;
  while ((m = re.exec(src))) {
    if (m[0].startsWith('<!--') || !m[2].trim() || /src=|type=["']module/.test(m[1])) continue;
    try { new vm.Script(m[2]); } catch (e) { errs.push(e.message); }
  }
  return errs;
}
check('2_inventory_parse', classicErrors('frontend/app/inventory.html'), []);
check('2_customers_parse', classicErrors('frontend/app/customers.html'), []);

// ── 3) check_syntax.py endi shablon ichidagi izohni ushlaydi ───────────────
console.log('\n── 3) check_syntax.py regressiyasi ──');
const dir = mkdtempSync(join(tmpdir(), 'xen-syntax-'));
const bad  = join(dir, 'bad.html');
const good = join(dir, 'good.html');
writeFileSync(bad,  '<html><body><script>\nconst x = 1;\nconst h = `<td>\n  <!-- izoh `kod` bilan -->\n</td>`;\n</script></body></html>\n');
writeFileSync(good, '<html><body><!-- <script>bu kod emas</script> `x` -->\n<script>\nconst h = `<td><!-- oddiy izoh --></td>`;\n</script></body></html>\n');
function runCheck(file) {
  for (const py of ['py', 'python3', 'python']) {
    const r = spawnSync(py, ['scripts/check_syntax.py', file], { encoding: 'utf8' });
    if (!r.error) return { status: r.status, out: r.stdout + r.stderr };
  }
  return null;
}
const rBad = runCheck(bad), rGood = runCheck(good);
rmSync(dir, { recursive: true, force: true });
if (rBad === null) {
  console.log('[SKIP] python topilmadi — 3-bo\'lim o\'tkazib yuborildi');
} else {
  check('3_shablon_ichidagi_backtick_izoh_USHLANADI', rBad.status, 1);
  // Crash (Traceback) bilan 1 EMAS — haqiqiy topilma bilan
  check('3_topilma_SyntaxError', /BUZUQ[\s\S]*SyntaxError/.test(rBad.out) && !/Traceback/.test(rBad.out), true);
  check('3_GOLDEN_skriptdan_tashqari_izoh_e_tiborsiz', rGood.status, 0);
}

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
