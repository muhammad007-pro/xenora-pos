/**
 * TEMA (qora/oq) — yagona yuklovchi (fix/remaining-issues).
 *
 * MUAMMO (jonli): oq rejimda ba'zi panellarga o'tganda qora bo'lardi, keyin oq.
 *   • app/ sahifalarining ko'pi temani UMUMAN o'qimasdi;
 *   • admin/pos temani <body> oxirida qo'yardi → avval qora chizilardi;
 *   • A-oila sahifalarida oq palitra yo'q edi (oq karta ustida oq matn).
 *
 * Qotiriladi:
 *   1) Statik: har app/ + owner/ sahifada theme-boot.js <head> da, CSS'dan OLDIN;
 *      o'z oq palitrasi yo'q sahifada theme-light.css sahifa <style> idan KEYIN
 *   2) Oq tanlov CHIZISHDAN oldin: DOMContentLoaded da allaqachon "light"
 *      (admin.html ham — miltillash yo'q)
 *   3) Tugma: o'z tugmasi yo'q sahifaga qo'shiladi, bosilsa saqlanadi;
 *      o'z tugmasi bor sahifaga (pos/admin) ikkinchisi qo'shilmaydi
 *   4) Boshqa oynada almashtirilsa — ochiq sahifa darhol ergashadi (storage)
 *   5) Oq rejimda matn o'qiladi (profit/returns/shift: matn qora, fon oq)
 *   6) Qora rejim sukut — avvalgidek
 *
 * Ishga tushirish:  node frontend/tests/test_theme_boot.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { readFileSync, readdirSync } from 'fs';
import { resolve, extname, join } from 'path';

const ROOT = resolve('frontend');
const rd = p => readFileSync(resolve(ROOT, p), 'utf8').replace(/\r\n/g, '\n');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };
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

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

// ── 1) Statik ─────────────────────────────────────────────────────────────────
console.log('\n── 1) Statik ulanish ──');
const pages = [...readdirSync(join(ROOT, 'app')).filter(f => f.endsWith('.html')).map(f => 'app/' + f),
               ...readdirSync(join(ROOT, 'owner')).filter(f => f.endsWith('.html')).map(f => 'owner/' + f)];
const noBoot = [], late = [], noPalette = [], palBeforeStyle = [];
for (const p of pages) {
  const t = rd(p);
  const head = t.slice(0, t.indexOf('</head>'));
  const b = head.indexOf('theme-boot.js');
  if (b < 0) { noBoot.push(p); continue; }
  const css = head.indexOf('stylesheet');
  if (css >= 0 && css < b) late.push(p);
  // A-oila (--bg2 + --text2) va o'z oq qoidasi yo'q → umumiy palitra shart
  const ownLight = /\[data-theme=["']?light/.test(t.replace(/theme-light\.css/g, ''));
  const famA = /:root\s*\{[^}]*--bg2\s*:/.test(t);
  const pal = head.indexOf('theme-light.css');
  if (famA && !ownLight && pal < 0) noPalette.push(p);
  if (pal >= 0 && head.lastIndexOf('</style>') > pal) palBeforeStyle.push(p);
}
check('1_hamma_sahifada_boot', noBoot, []);
check('1_boot_CSS_dan_oldin', late, []);
check('1_oq_palitrasiz_sahifa_yoq', noPalette, []);
check('1_palitra_style_dan_keyin', palBeforeStyle, []);

// ── Brauzer ───────────────────────────────────────────────────────────────────
const tok = `x.${Buffer.from(JSON.stringify({ sub: '1', exp: 4102444800, business_type: 'store', features: [] })).toString('base64')}.y`;
const browser = await chromium.launch({ headless: true });
async function ctxWith(theme) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, serviceWorkers: 'block' });
  await ctx.addInitScript(([t, th]) => {
    if (sessionStorage.getItem('__s')) return; sessionStorage.setItem('__s', '1');
    localStorage.setItem('access_token', t); localStorage.setItem('business_type', 'store');
    if (th) localStorage.setItem('theme', th); else localStorage.removeItem('theme');
    localStorage.setItem('user', JSON.stringify({ id: 1, role: { name: 'admin' }, business_type: 'store' }));
    // DOMContentLoaded paytidagi tema — "chizishdan oldin" isboti
    document.addEventListener('DOMContentLoaded', () => { window.__themeAtDCL = document.documentElement.getAttribute('data-theme'); });
  }, [tok, theme]);
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  await ctx.route('**/api/**', r => r.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
  return ctx;
}
async function open(ctx, url) {
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`${BASE}/${url}`, { waitUntil: 'domcontentloaded', timeout: 40000 });
  await page.waitForTimeout(400);
  return { page, errors };
}
const lum = c => { const m = c.match(/[\d.]+/g).map(Number); return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255; };

console.log('\n── 2) Chizishdan oldin ──');
{
  const ctx = await ctxWith('light');
  for (const url of ['app/profit.html', 'app/returns.html', 'app/admin.html', 'app/pos.html']) {
    const { page, errors } = await open(ctx, url);
    check(`2_${url}_DCL_da_light`, await page.evaluate(() => window.__themeAtDCL), 'light');
    check(`2_${url}_xatosiz`, errors.filter(e => /theme/i.test(e)), []);
    await page.close();
  }
  await ctx.close();
}

console.log('\n── 3) Tugma ──');
{
  const ctx = await ctxWith('dark');
  const { page } = await open(ctx, 'app/profit.html');
  check('3_tugma_qoshildi', await page.isVisible('#xnThemeBtn'), true);
  check('3_sarlavhada', await page.evaluate(() => !!document.querySelector('.ph #xnThemeBtn')), true);
  await page.click('#xnThemeBtn');
  check('3_bosilgach_light', await page.evaluate(() => document.documentElement.getAttribute('data-theme')), 'light');
  check('3_saqlandi', await page.evaluate(() => localStorage.getItem('theme')), 'light');
  await page.reload({ waitUntil: 'domcontentloaded' });
  check('3_qayta_ochilganda_light', await page.evaluate(() => document.documentElement.getAttribute('data-theme')), 'light');
  await page.close();
  const pos = await open(ctx, 'app/pos.html');
  check('3_pos_ikkinchi_tugma_yoq', await pos.page.evaluate(() => !!document.getElementById('xnThemeBtn')), false);
  await pos.page.close();
  await ctx.close();
}

console.log('\n── 4) Oynalararo sinxron ──');
{
  const ctx = await ctxWith('dark');
  const a = await open(ctx, 'app/returns.html');
  const b = await open(ctx, 'app/shift.html');
  await b.page.evaluate(() => window.XenoraTheme.set('light'));
  await a.page.waitForFunction(() => document.documentElement.getAttribute('data-theme') === 'light', null, { timeout: 3000 }).catch(() => {});
  check('4_boshqa_oyna_ergashdi', await a.page.evaluate(() => document.documentElement.getAttribute('data-theme')), 'light');
  await ctx.close();
}

console.log('\n── 5) Oq rejimda o\'qiladi ──');
{
  const ctx = await ctxWith('light');
  for (const url of ['app/profit.html', 'app/returns.html', 'app/shift.html', 'app/analytics.html']) {
    const { page } = await open(ctx, url);
    const c = await page.evaluate(() => [getComputedStyle(document.body).color,
      getComputedStyle(document.querySelector('.ph-title,.page-title,h1') || document.body).color]);
    // Asosiy matn qora; sarlavha tilla bo'lishi mumkin (inventory palitrasi) — faqat OQ bo'lmasin
    check(`5_${url}_matn_qora`, lum(c[0]) < 0.4, true);
    check(`5_${url}_sarlavha_oq_emas`, lum(c[1]) < 0.75, true);
    await page.close();
  }
  await ctx.close();
}

console.log('\n── 6) Sukut — qora ──');
{
  const ctx = await ctxWith(null);
  const { page } = await open(ctx, 'app/profit.html');
  check('6_sukut_dark', await page.evaluate(() => document.documentElement.getAttribute('data-theme')), 'dark');
  check('6_matn_och', lum(await page.evaluate(() => getComputedStyle(document.body).color)) > 0.6, true);
  await ctx.close();
}

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
