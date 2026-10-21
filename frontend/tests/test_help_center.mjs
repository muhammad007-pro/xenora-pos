/**
 * YORDAM BO'LIMI — "? Yordam" oynasi (feature/help-center).
 *
 * Qotiriladi:
 *   1) Matn: docs/help/*.md == js/core/help-content.js (build_help.py --check);
 *      7 bo'lim, 30 savol — egasi bergan ro'yxat bilan AYNAN; HTML ekranlangan
 *   2) Ulanish: admin.html (sidebar pasti) va pos.html (header) da `data-help-open`
 *      tugma; skriptlar tartibi (content → center); SW keshida; .exe ichida
 *      (electron extraResources `../frontend/**`)
 *   3) Admin (haqiqiy admin.html): tugma ko'rinadi → modal ochiladi → HAMMA bo'lim
 *      ochiladi (savollar soni mos) → qidiruv (apostrofsiz ham) → topilmasa
 *      telefon → Esc yopadi → sahifa xatosiz
 *   4) POS (haqiqiy pos.html, monoblok 1024): tugma header'da to'liq ko'rinadi,
 *      header gorizontal toshmaydi; oyna ichidagi klaviatura POS global
 *      tinglovchilariga CHIQMAYDI (F4 to'lov oynasini ochmaydi, skaner buferi yo'q)
 *   5) Telefon (375px): oyna ekranga sig'adi, gorizontal surilish yo'q
 *
 * Ishga tushirish:  node frontend/tests/test_help_center.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { readFileSync } from 'fs';
import { resolve, extname, join } from 'path';
import { spawnSync } from 'child_process';
import vm from 'node:vm';

const ROOT = resolve('frontend');
const rd = p => readFileSync(resolve(p), 'utf8').replace(/\r\n/g, '\n');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

// ── 1) Matn ─────────────────────────────────────────────────────────────────
console.log('\n── 1) Matn ──');
let py = null;
for (const cmd of ['py', 'python3', 'python']) {
  const r = spawnSync(cmd, ['scripts/build_help.py', '--check'], { encoding: 'utf8' });
  if (r.error) continue;
  py = { code: r.status, out: (r.stdout || '') + (r.stderr || '') };
  break;
}
check('1_build_help_check', py && py.code, 0);
if (py && py.code) console.log(py.out);

const hctx = { window: {} };
vm.createContext(hctx);
vm.runInContext(rd('frontend/js/core/help-content.js'), hctx);
const HELP = hctx.window.XENORA_HELP;
const SECS = HELP.sections;

// Egasi bergan ro'yxat (2026-10-19). Savol qo'shilsa/o'zgarsa — shu yerni ham yangilang.
const EXPECT = {
  'Sotuv': ['Kg/metr mahsulotni qanday sotaman?', 'Pachka va dona farqi nima?', 'Chegirma qanday beraman?',
            'Nasiyaga qanday sotaman?', 'Aralash to\'lov (naqd + nasiya)'],
  'Qaytarish': ['Vozvrat qanday qilinadi?', 'Chek raqamini qayerdan topaman?', 'Nega "tasdiqlash kerak" deydi?',
                'Brak tovarni qanday qaytaraman?'],
  'Printer': ['Chek chiqmayapti', 'Chek kichik chiqyapti (57mm o\'rniga 80mm)', 'Etiketka printeridan chek chiqdi',
              'Printer qog\'ozi tugasa nima bo\'ladi?'],
  'Ombor': ['Yangi mahsulot qanday qo\'shaman?', 'Kirim qanday kiritaman?', 'Qoldiq noto\'g\'ri — nima qilay?',
            'Hisobdan chiqarish qachon kerak?', 'Etiketka qanday chop etaman?'],
  'Hisobot': ['Bugun qancha sotdim?', 'Foyda qayerda ko\'rinadi?', 'Dashboard va hisobot nega farq qiladi?',
              'Xarajat qanday kiritaman?', 'Sana oralig\'ini qanday tanlayman?'],
  'Smena': ['Smena nima uchun kerak?', 'Z-hisobot nima?', 'Kamomad chiqdi — nega?', 'Kassadan pul olsam nima qilaman?'],
  'Mijoz va nasiya': ['Mijoz qanday qo\'shaman?', 'Qarzni qanday to\'layman?', 'Qarz kartochkasi nima?'],
};
check('1_bolimlar', SECS.map(s => s.title), Object.keys(EXPECT));
for (const s of SECS) check(`1_savollar_${s.id}`, s.items.map(i => i.q), EXPECT[s.title] || []);
const ALL = SECS.flatMap(s => s.items);
check('1_jami_30_savol', ALL.length, 30);
check('1_id_takrorlanmaydi', new Set(ALL.map(i => i.id)).size, ALL.length);
// Ekranlash: faqat ruxsat etilgan teglar (p, ol, ul, li, b, code, div.xh-note)
const tags = new Set(ALL.flatMap(i => [...i.html.matchAll(/<\/?([a-z0-9]+)/g)].map(m => m[1])));
check('1_faqat_ruxsat_etilgan_teglar', [...tags].filter(t => !['p', 'ol', 'ul', 'li', 'b', 'code', 'div'].includes(t)), []);
check('1_har_javob_bosh_emas', ALL.filter(i => i.text.length < 80).map(i => i.id), []);
check('1_telefon_hujjatda_emas_modulda', /\+998 94 997 47 70/.test(rd('frontend/js/core/help-center.js')), true);

// ── 2) Ulanish ──────────────────────────────────────────────────────────────
console.log('\n── 2) Ulanish ──');
const ADMIN = rd('frontend/app/admin.html'), POSH = rd('frontend/app/pos.html');
for (const [nm, src] of [['admin', ADMIN], ['pos', POSH]]) {
  check(`2_${nm}_tugma`, /<button[^>]*id="helpBtn"[^>]*data-help-open/.test(src), true);
  const a = src.indexOf('<script src="../js/core/help-content.js">'), b = src.indexOf('<script src="../js/core/help-center.js">');
  check(`2_${nm}_skript_tartibi`, a > 0 && b > a, true);
}
check('2_admin_tugma_sidebar_pastida', /<\/nav>\s*<!--[^>]*-->\s*<button[^>]*class="sb-help"[\s\S]*?<\/button>\s*<div class="sb-user">/.test(ADMIN), true);
check('2_admin_tugma_data_page_yoq', /id="helpBtn"[^>]*data-page/.test(ADMIN), false);
check('2_pos_tugma_headerda', /<header class="pos-header">[\s\S]*id="helpBtn"[\s\S]*<\/header>/.test(POSH), true);
const SW = rd('frontend/service-worker.js');
check('2_sw_keshida', ["'/js/core/help-content.js'", "'/js/core/help-center.js'"].map(x => SW.includes(x)), [true, true]);
const EPKG = JSON.parse(rd('electron/package.json'));
const fe = (EPKG.build.extraResources || []).find(x => x.from === '../frontend');
check('2_exe_frontend_toliq', !!fe && fe.filter.includes('**/*') && !fe.filter.some(f => /help|\.js/.test(f)), true);

// ── 3–5) Brauzer ────────────────────────────────────────────────────────────
const server = createServer(async (req, res) => {
  try {
    const p = join(ROOT, decodeURIComponent(req.url.split('?')[0]));
    const body = await readFile(p);
    res.writeHead(200, { 'Content-Type': MIME[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch { res.writeHead(404); res.end('not found'); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${server.address().port}`;
const tok = `x.${Buffer.from(JSON.stringify({ sub: '1', user_id: 1, tenant_id: 27, business_type: 'store', features: [], exp: 4102444800 })).toString('base64')}.y`;

const browser = await chromium.launch({ headless: true });
async function openPage(path, { w = 1280, h = 800, role = 'admin' } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, serviceWorkers: 'block' });
  await ctx.addInitScript(([t, r]) => {
    if (sessionStorage.getItem('__s')) return; sessionStorage.setItem('__s', '1');
    localStorage.clear();
    localStorage.setItem('access_token', t); localStorage.setItem('business_type', 'store');
    localStorage.setItem('user', JSON.stringify({ id: 1, tenant_id: 27, role: { name: r }, business_type: 'store' }));
  }, [tok, role]);
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  await ctx.route('**/api/**', r => {
    const p = new URL(r.request().url()).pathname.replace(/.*\/api\/v1/, '');
    if (p === '/shifts/active') return r.fulfill({ status: 200, contentType: 'application/json', body: '{"id":5}' });
    r.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded', timeout: 40000 });
  await page.waitForFunction(() => !!window.XenoraHelp, null, { timeout: 15000 });
  return { ctx, page, errors };
}
const isOpen = page => page.evaluate(() => window.XenoraHelp.isOpen());
const searchFor = async (page, q) => {
  await page.fill('#xhSearch', q);
  await page.waitForTimeout(250);
  return page.evaluate(() => ({
    ids: [...document.querySelectorAll('#xhMain [data-xh-item]')].map(e => e.dataset.xhItem),
    notFound: !!document.getElementById('xhNotFound'),
    notFoundText: document.getElementById('xhNotFound')?.textContent || '',
    tel: document.querySelector('#xhNotFound a[href^="tel:"]')?.getAttribute('href') || null,
  }));
};

console.log('\n── 3) Admin panel ──');
{
  const { ctx, page, errors } = await openPage('/app/admin.html', { w: 1366, h: 768 });
  await page.waitForFunction(() => typeof window.switchPage === 'function', null, { timeout: 15000 });
  const vis = await page.evaluate(() => {
    const b = document.getElementById('helpBtn'), rc = b.getBoundingClientRect();
    const hit = document.elementFromPoint(rc.left + rc.width / 2, rc.top + rc.height / 2);
    return { inSidebar: !!b.closest('.admin-sidebar'), visible: rc.width > 0 && rc.bottom <= innerHeight && rc.top >= 0,
             clickable: !!hit && (hit === b || b.contains(hit)), text: b.textContent.trim() };
  });
  check('3_tugma_sidebarda_korinadi_bosiladi', vis, { inSidebar: true, visible: true, clickable: true, text: 'Yordam' });
  const pageBefore = await page.textContent('#pageTitle');
  await page.click('#helpBtn');
  check('3_modal_ochildi', await isOpen(page), true);
  check('3_spa_sahifa_almashmadi', await page.textContent('#pageTitle'), pageBefore);
  check('3_qidiruvga_fokus', await page.evaluate(() => document.activeElement?.id), 'xhSearch');

  // Har bir bo'lim ochiladi va savollar soni mos
  const navCount = await page.locator('[data-xh-sec]').count();
  check('3_bolim_tugmalari', navCount, SECS.length);
  for (const s of SECS) {
    await page.click(`[data-xh-sec="${s.id}"]`);
    const r = await page.evaluate(() => ({
      h: document.querySelector('#xhMain .xh-h')?.textContent,
      n: document.querySelectorAll('#xhMain [data-xh-item]').length,
      active: document.querySelector('.xh-sec.xh-active')?.dataset.xhSec,
      steps: document.querySelectorAll('#xhMain .xh-a li').length > 0,
    }));
    check(`3_bolim_${s.id}_ochiladi`, r, { h: s.title, n: s.items.length, active: s.id, steps: true });
  }

  // Qidiruv
  let r = await searchFor(page, 'vozvrat');
  check('3_qidiruv_vozvrat', r.ids.includes('qaytarish-1') && !r.notFound, true);
  r = await searchFor(page, 'ogirlik');                       // apostrofsiz
  check('3_qidiruv_apostrofsiz', r.ids.includes('sotuv-1'), true);
  r = await searchFor(page, 'o‘g‘irlik');                     // o‘ (U+2018) bilan
  check('3_qidiruv_boshqa_apostrof', r.ids.includes('sotuv-1'), true);
  r = await searchFor(page, 'CHEK CHIQMAYAPTI');               // katta harf + ikki so'z
  check('3_qidiruv_savol_birinchi', r.ids[0], 'printer-1');
  r = await searchFor(page, 'zakaz qilish uchun kosmik kema');
  check('3_topilmadi_telefon', [r.notFound, /Topolmadingizmi\? Qo'ng'iroq qiling:/.test(r.notFoundText),
                                /\+998 94 997 47 70/.test(r.notFoundText), r.tel], [true, true, true, 'tel:+998949974770']);
  r = await searchFor(page, '');
  check('3_bosh_qidiruv_bolimga_qaytadi', [r.notFound, r.ids.length > 0], [false, true]);
  check('3_pastda_doim_telefon', /\+998 94 997 47 70/.test(await page.textContent('.xh-foot')), true);

  await page.keyboard.press('Escape');
  check('3_esc_yopadi', await isOpen(page), false);
  check('3_fokus_tugmaga_qaytdi', await page.evaluate(() => document.activeElement?.id), 'helpBtn');
  await page.click('#helpBtn');
  await page.mouse.click(5, 5);                                // fon ustiga
  check('3_fon_bosilsa_yopiladi', await isOpen(page), false);

  // Oq tema — fon va matn rangi almashadi (o'qiladigan)
  const dark = await page.evaluate(() => { window.XenoraHelp.open(); return getComputedStyle(document.querySelector('.xh-dialog')).backgroundColor; });
  const light = await page.evaluate(() => { document.documentElement.setAttribute('data-theme', 'light'); return getComputedStyle(document.querySelector('.xh-dialog')).backgroundColor; });
  check('3_oq_tema_fon', [dark !== light, light], [true, 'rgb(255, 255, 255)']);
  check('3_xatosiz', errors, []);
  await ctx.close();
}

console.log('\n── 4) POS (monoblok 1024) ──');
for (const [w, h] of [[1024, 768], [1280, 800]]) {
  const { ctx, page, errors } = await openPage('/app/pos.html', { w, h, role: 'cashier' });
  await page.waitForFunction(() => document.getElementById('loadingScreen')?.classList.contains('hidden'), null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(500);
  const g = await page.evaluate(() => {
    const b = document.getElementById('helpBtn'), rc = b.getBoundingClientRect();
    const hdr = document.querySelector('.pos-header');
    const hit = document.elementFromPoint(rc.left + rc.width / 2, rc.top + rc.height / 2);
    return { toliqKorinadi: rc.width > 0 && rc.left >= 0 && rc.right <= innerWidth && rc.top >= 0,
             bosiladi: !!hit && (hit === b || b.contains(hit)),
             headerToshmaydi: hdr.scrollWidth <= hdr.clientWidth + 1,
             sahifaSurilmaydi: document.documentElement.scrollWidth <= innerWidth + 1 };
  });
  check(`4_${w}_tugma_header`, g, { toliqKorinadi: true, bosiladi: true, headerToshmaydi: true, sahifaSurilmaydi: true });
  if (w === 1024) await page.screenshot({ path: `${process.env.TEMP || '.'}/help_pos_1024.png` });

  await page.click('#helpBtn');
  check(`4_${w}_modal_ochildi`, await isOpen(page), true);
  // POS'ning umumiy input uslubi qidiruv matnini qorong'i fonda ko'rinmas qilgan edi
  check(`4_${w}_qidiruv_matni_korinadi`, await page.evaluate(() =>
    getComputedStyle(document.getElementById('xhSearch')).color === getComputedStyle(document.querySelector('.xh-dialog')).color), true);
  // POS global tinglovchilari: hujjat darajasida keydown sanagich
  await page.evaluate(() => { window.__kd = 0; document.addEventListener('keydown', () => { window.__kd++; }); });
  // POS o'zi shtrix-kod maydoniga fokus beradi (yuklanishdan 800ms keyin) — oyna
  // ochiq paytda shunday bo'lsa ham fokus oynada qolishi kerak.
  const stolen = await page.evaluate(() => { document.getElementById('barcodeInput')?.focus(); return document.activeElement?.id; });
  check(`4_${w}_fokus_oynadan_chiqmaydi`, stolen, 'xhSearch');
  await page.keyboard.type('chek 4780000000017');
  await page.keyboard.press('Enter');
  await page.keyboard.press('F4');
  await page.keyboard.press('F9');
  const iso = await page.evaluate(() => ({ kd: window.__kd, tolov: document.getElementById('paymentModal').classList.contains('open') }));
  check(`4_${w}_klaviatura_POSga_chiqmaydi`, iso, { kd: 0, tolov: false });
  check(`4_${w}_qidiruv_ishlaydi`, (await searchFor(page, 'nasiya')).ids.includes('sotuv-4'), true);
  await page.keyboard.press('Escape');
  check(`4_${w}_esc_yopadi`, await isOpen(page), false);
  check(`4_${w}_xatosiz`, errors, []);
  await ctx.close();
}

console.log('\n── 5) Telefon 375px ──');
{
  const { ctx, page, errors } = await openPage('/app/admin.html', { w: 375, h: 740 });
  await page.evaluate(() => window.XenoraHelp.open());
  await page.waitForTimeout(200);
  const m = await page.evaluate(() => {
    const d = document.querySelector('.xh-dialog').getBoundingClientRect();
    const main = document.getElementById('xhMain');
    return { sigadi: d.left >= 0 && d.right <= innerWidth + 0.5 && d.bottom <= innerHeight + 0.5,
             matnSurilmaydi: main.scrollWidth <= main.clientWidth + 1,
             bolimlarGorizontal: getComputedStyle(document.getElementById('xhNav')).display === 'flex' };
  });
  check('5_telefonda_sigadi', m, { sigadi: true, matnSurilmaydi: true, bolimlarGorizontal: true });
  check('5_xatosiz', errors, []);
  await ctx.close();
}

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
