/**
 * BLOKLANGAN DO'KON — OCHIQ SESSIYA UZILADI (frontend qismi, 2026-10-13).
 *
 * Backend endi ochiq sessiyaga ham 403 {"detail": "<matn>", "code": "STORE_INACTIVE"}
 * beradi (code — YUQORI darajada, detail ichida emas). api.js uni ushlab:
 *   · tokenlarni o'chiradi, login'ga yo'naltiradi (bir marta, parallel 403 larda ham)
 *   · login ekranida serverning neytral matni chiqadi (sessionStorage orqali)
 *   · offline navbat (IndexedDB) ga TEGMAYDI
 * Refresh 403 STORE_INACTIVE bersa ham xuddi shu matn ko'rinadi.
 * Boshqa 403 (ruxsat yo'q) — sessiya UZILMAYDI.
 *
 * Ishga tushirish:  node frontend/tests/test_store_inactive_session.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { resolve, extname, join } from 'path';

const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
               '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const MSG = "Do'kon vaqtincha faol emas. Bog'laning: +998 94 997 47 70";

// Sinov sahifasi /app/ ostida (PATHS.login() nisbiy yo'li haqiqiy holatdagidek).
const PAGE = `<!doctype html><meta charset="utf-8"><body>
<script type="module">
  import { API } from '/js/core/api.js';
  window.__api = new API();
  document.title = 'ready';
</script></body>`;

let mode = 'inactive';           // /api/v1/* javobini boshqaradi
const server = createServer(async (req, res) => {
  const url = req.url.split('?')[0];
  const json = (st, obj) => { res.writeHead(st, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
  if (url === '/app/_t.html') { res.writeHead(200, { 'Content-Type': 'text/html' }); return res.end(PAGE); }
  // login.html saqlangan kod bilan do'konni o'zi aniqlaydi — bloklangan do'kon (server kabi)
  if (url === '/api/v1/auth/resolve-code') return json(403, { detail: MSG, code: 'STORE_INACTIVE' });
  if (url === '/api/v1/auth/refresh') {
    return mode === 'refresh_inactive'
      ? json(403, { detail: MSG, code: 'STORE_INACTIVE' })
      : json(200, { access_token: 'yangi', refresh_token: 'yangi_r', token_type: 'bearer' });
  }
  if (url.startsWith('/api/v1/')) {
    if (mode === 'inactive') return json(403, { detail: MSG, code: 'STORE_INACTIVE' });
    if (mode === 'forbidden') return json(403, { detail: "'manage_users' ruxsati yo'q" });
    if (mode === 'refresh_inactive') return json(401, { detail: 'Autentifikatsiya talab qilinadi' });
    return json(404, { detail: 'yoq' });
  }
  try {
    const p = join(ROOT, decodeURIComponent(url));
    const buf = await readFile(p);
    res.writeHead(200, { 'Content-Type': MIME[extname(p)] || 'application/octet-stream' });
    res.end(buf);
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

const browser = await chromium.launch({ headless: true });

async function fresh() {
  const ctx = await browser.newContext();
  await ctx.route(/fonts\.(googleapis|gstatic)\.com|cdn/, r => r.abort());
  const page = await ctx.newPage();
  await page.goto(`${BASE}/app/_t.html`);
  await page.waitForFunction(() => document.title === 'ready');
  await page.evaluate(() => {
    localStorage.setItem('access_token', 'eski');
    localStorage.setItem('refresh_token', 'eski_r');
    localStorage.setItem('store_access_code', '100.200.6');
    window.__api.token = 'eski';
  });
  return { ctx, page };
}

// ── T1: ochiq sessiya 403 STORE_INACTIVE → login, matn ko'rinadi ─────────────
{
  mode = 'inactive';
  const { ctx, page } = await fresh();
  const nav = page.waitForURL(/shared\/login\.html/, { timeout: 15000 }).then(() => true).catch(() => false);
  // parallel so'rovlar (POS shunday) — bitta redirect
  const r = await page.evaluate(() => Promise.all([
    window.__api.get('/products/'), window.__api.get('/orders/'), window.__api.get('/shifts/active'),
  ]).then(rs => rs[0]));
  check('T1_code_yuqori_darajadan_oqildi', r.code, 'STORE_INACTIVE');
  check('T1_login_ga_yonaltirildi', await nav, true);
  await page.waitForFunction(() => document.getElementById('codeError')?.style.display === 'block',
                             null, { timeout: 15000 }).catch(() => {});
  const st = await page.evaluate(() => ({
    acc: localStorage.getItem('access_token'),
    ref: localStorage.getItem('refresh_token'),
    msg: document.getElementById('codeError')?.textContent || '',
    left: sessionStorage.getItem('store_inactive_msg'),
  }));
  check('T1_access_tozalandi', st.acc, null);
  check('T1_refresh_tozalandi', st.ref, null);
  check('T1_login_ekranida_matn', st.msg, MSG);
  check('T1_xabar_bir_martalik', st.left, null);
  await ctx.close();
}

// ── T2: boshqa 403 (ruxsat yo'q) — sessiya UZILMAYDI ─────────────────────────
{
  mode = 'forbidden';
  const { ctx, page } = await fresh();
  const r = await page.evaluate(() => window.__api.get('/users/'));
  await page.waitForTimeout(500);
  check('T2_xato_qaytdi', [r.success, r.status], [false, 403]);
  check('T2_sahifada_qoldi', page.url().endsWith('/app/_t.html'), true);
  check('T2_token_saqlandi', await page.evaluate(() => localStorage.getItem('access_token')), 'eski');
  await ctx.close();
}

// ── T3: access tugagan, refresh 403 STORE_INACTIVE → login + matn ────────────
{
  mode = 'refresh_inactive';
  const { ctx, page } = await fresh();
  const nav = page.waitForURL(/shared\/login\.html/, { timeout: 15000 }).then(() => true).catch(() => false);
  await page.evaluate(() => window.__api.get('/products/')).catch(() => {});
  check('T3_login_ga_yonaltirildi', await nav, true);
  await page.waitForFunction(() => document.getElementById('codeError')?.style.display === 'block',
                             null, { timeout: 15000 }).catch(() => {});
  check('T3_login_ekranida_matn',
        await page.evaluate(() => document.getElementById('codeError')?.textContent || ''), MSG);
  await ctx.close();
}

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
