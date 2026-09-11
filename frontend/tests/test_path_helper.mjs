/**
 * YO'L YORDAMCHISI (`js/core/paths.js`) — HAQIQIY BRAUZERDA sinov.
 *
 * NEGA BRAUZER: `api.js` dagi yo'naltirish butun ilovaga tegadi — token
 * muddati tugaganda HAR QANDAY sahifadan login'ga o'tiladi. Statik grep
 * buni tekshira olmaydi: modul importi, `location.pathname` va haqiqiy
 * navigatsiya kerak.
 *
 * JONLI HODISA (1001 BARAKA, 2026-09-10): mutlaq yo'l (`/shared/login.html`,
 * `/app/pos.html`) Electron `file://` da DISK ILDIZIGA ishora qiladi →
 * qora ekran. Brauzerda esa ishlayveradi — shuning uchun nuqson `.exe` da
 * ko'rinardi, sinovda emas.
 *
 * BU TEST IKKALA KONTEKSTNI HAM QAMRAYDI:
 *   • http(s) — oddiy brauzer (mahalliy server)
 *   • file:// — Electron aynan shunday ishlaydi (`loadFile`)
 *
 * Ishga tushirish:  node frontend/tests/test_path_helper.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { resolve, extname, join } from 'path';
import { pathToFileURL } from 'url';

const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
               '.css': 'text/css', '.json': 'application/json' };
// ⚠️ `.html` so'rovlariga MINIMAL stub beriladi, haqiqiy sahifa EMAS.
// Sabab: `pos.html`/`shift.html` og'ir (SW, o'nlab modul, tenant-backup) va
// ular bu yerda TEKSHIRILMAYDI — tekshirilayotgani `paths.js` ning
// `location.pathname` ga qarab yo'l hisoblashi. Stub bilan test tez va
// barqaror bo'ladi. `.js` fayllar HAQIQIY (paths.js, api.js, config.js).
const STUB = '<!doctype html><meta charset="utf-8"><title>stub</title><body>stub</body>';
const server = createServer(async (req, res) => {
  const rel = decodeURIComponent(req.url.split('?')[0]);
  if (rel.endsWith('.html')) {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(STUB);
    return;
  }
  try {
    const p = join(ROOT, rel);
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

const browser = await chromium.launch();

/** `paths.js` ni berilgan sahifadan import qilib, hisoblangan yo'llarni oladi. */
async function yollar(pageUrl, modUrl) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(pageUrl, { waitUntil: 'domcontentloaded' });
  const out = await page.evaluate(async (u) => {
    const m = await import(u);
    return { login: m.PATHS.login(), pos: m.PATHS.pos(),
             admin: m.PATHS.admin(), sub: m.PATHS.subscriptionBlocked() };
  }, modUrl);
  await ctx.close();
  return out;
}

// ══════════════════════════════════════════════════════════════════════════
// 1) http(s) — oddiy brauzer, uch joylashuv
// ══════════════════════════════════════════════════════════════════════════
{
  const a = await yollar(`${BASE}/app/pos.html`, `${BASE}/js/core/paths.js`);
  check('1_app_login', a.login, '../shared/login.html');
  check('1_app_pos',   a.pos,   '../app/pos.html');

  const s = await yollar(`${BASE}/shared/login.html`, `${BASE}/js/core/paths.js`);
  check('1_shared_login', s.login, '../shared/login.html');
  check('1_shared_pos',   s.pos,   '../app/pos.html');

  const o = await yollar(`${BASE}/owner/cafes.html`, `${BASE}/js/core/paths.js`);
  check('1_owner_login', o.login, '../shared/login.html');
  check('1_owner_admin', o.admin, '../app/admin.html');

  // Hech birida MUTLAQ yo'l bo'lmasin
  const hammasi = [...Object.values(a), ...Object.values(s), ...Object.values(o)];
  check('1_mutlaq_yol_yoq', hammasi.filter(x => x.startsWith('/')), []);
}

// ══════════════════════════════════════════════════════════════════════════
// 2) ⚠️ HAQIQIY NAVIGATSIYA — hisoblangan yo'l ochiladimi
//    (mutlaq yo'l bo'lganda aynan shu qadam sinardi)
// ══════════════════════════════════════════════════════════════════════════
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${BASE}/app/shift.html`, { waitUntil: 'domcontentloaded' });
  const target = await page.evaluate(async (u) => {
    const m = await import(u);
    return new URL(m.PATHS.login(), location.href).href;   // brauzer qanday hal qiladi
  }, `${BASE}/js/core/paths.js`);
  check('2_hal_qilingan_url', target, `${BASE}/shared/login.html`);

  const res = await page.goto(target, { waitUntil: 'domcontentloaded' });
  check('2_login_ochildi', res.status(), 200);
  check('2_login_sahifasi', /login\.html$/.test(page.url()), true);
  await ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════
// 3) ⚠️ file:// — ELEKTRON AYNAN SHUNDAY ISHLAYDI (loadFile)
//    Mutlaq yo'l bu yerda DISK ILDIZIGA ketardi va qora ekran berardi.
//
//    BRAUZERSIZ tekshiriladi: `file://` da ES modul import qilishni Chromium
//    CORS bilan bloklaydi. Electron'da esa ishlaydi, chunki u `webSecurity:
//    false` bilan ochadi (electron/main.js:645). URL HAL QILISH qoidasi
//    ikkalasida bir xil standart, shuning uchun `new URL()` aynan o'sha
//    natijani beradi va sinov ishonchli qoladi.
// ══════════════════════════════════════════════════════════════════════════
{
  const { pathTo } = await import(pathToFileURL(join(ROOT, 'js', 'core', 'paths.js')).href);

  const shiftFile = pathToFileURL(join(ROOT, 'app', 'shift.html')).href;
  const hisob = pathTo('shared/login.html', new URL(shiftFile).pathname);
  check('3_file_hisoblangan', hisob, '../shared/login.html');

  const hal = new URL(hisob, shiftFile).href;
  const kutilgan = pathToFileURL(join(ROOT, 'shared', 'login.html')).href;
  check('3_file_url_togri', hal, kutilgan);

  // ESKI XATTI-HARAKAT: mutlaq yo'l `file://` da DISK ILDIZIGA ketardi —
  // aynan shu qora ekran sababi edi. Regressiya qaytsa test aytadi.
  const eski = new URL('/shared/login.html', shiftFile).href;
  check('3_mutlaq_yol_disk_ildiziga', eski !== kutilgan, true);
  check('3_eski_yol_loyihadan_tashqarida', eski.includes('/frontend/'), false);

  // owner/ dan ham
  const ownerFile = pathToFileURL(join(ROOT, 'owner', 'cafes.html')).href;
  check('3_file_owner',
        new URL(pathTo('app/pos.html', new URL(ownerFile).pathname), ownerFile).href,
        pathToFileURL(join(ROOT, 'app', 'pos.html')).href);
}

// ══════════════════════════════════════════════════════════════════════════
// 4) ⚠️ MAVJUD LOGIN OQIMI BUZILMASIN — eng katta xavf
//    Token buzuq → api.js refresh yiqiladi → login'ga o'tishi KERAK
// ══════════════════════════════════════════════════════════════════════════
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const xatolar = [];
  page.on('pageerror', e => xatolar.push(String(e.message)));

  // Buzuq token qo'yamiz
  await ctx.addInitScript(() => {
    localStorage.setItem('access_token', 'buzuq.token.qiymat');
    localStorage.setItem('refresh_token', 'buzuq.refresh');
    localStorage.setItem('user', JSON.stringify({ id: 1, role: { name: 'cashier' } }));
  });
  // Refresh so'rovi HAR DOIM yiqilsin (401)
  await page.route('**/auth/refresh**', r =>
    r.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"invalid"}' }));

  await page.goto(`${BASE}/app/shift.html`, { waitUntil: 'domcontentloaded' });
  // `api.js` ni import qilib, refresh'ni majburan chaqiramiz
  const natija = await page.evaluate(async (b) => {
    const m = await import(b + '/js/core/api.js');
    const api = m.api || m.default || new (m.API || Object)();
    try { await api.refreshAccessToken(true); } catch {}
    return location.href;
  }, BASE).catch(e => 'XATO: ' + e.message);

  await page.waitForTimeout(600);
  check('4_login_ga_otdi', /login\.html$/.test(page.url()), true);
  check('4_js_xato_yoq', xatolar, []);
  await ctx.close();
}

await browser.close();
server.close();
console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
