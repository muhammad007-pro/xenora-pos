/**
 * REGRESSIYA QO'RIQCHISI: js/core/config.js — API manzilini aniqlash.
 *
 * MUAMMO (mijozda, Fazza Parfum v1.9.1): admin panelidagi "Firmalar" bo'limi
 * IFRAME orqali ochiladi (admin.html → suppliers.html?embed=1). Electron'da
 * `preload.js` sukut bo'yicha faqat ASOSIY freymda ishlaydi, ya'ni iframe ichida
 * `window.XENORA_SERVER` UNDEFINED edi. Natijada config.js `file://` ni "dev"
 * deb hisoblab so'rovlarni `http://localhost:8000` ga yuborardi — o'sha manzilda
 * hech narsa yo'q. Har amal "Server bilan aloqa yo'q" bilan tugardi, holbuki
 * asosiy oynadagi POS va nasiya ishlab turardi.
 *
 * Bu test HAQIQIY brauzerda (Playwright) iframe holatini simulyatsiya qiladi.
 *
 * Ishga tushirish:  node frontend/tests/test_iframe_api_base.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { resolve, extname, join } from 'path';

const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
               '.css': 'text/css', '.json': 'application/json' };

// Sinov sahifalari DISKDA emas — server ularni o'zi yasaydi (repo iflos bo'lmasin).
const CHILD = `<!doctype html><meta charset="utf-8"><body>
<script type="module">
  import { API_BASE, WS_BASE } from '/js/core/config.js';
  window.__RESULT__ = { API_BASE, WS_BASE };
  document.title = 'ready';
</script></body>`;

const PARENT_WITH_SERVER = `<!doctype html><meta charset="utf-8"><body>
<script>window.XENORA_SERVER = 'http://178.128.251.218';</script>
<iframe id="f" src="/tests/_child.html" style="width:300px;height:100px"></iframe>
</body>`;

const PARENT_WITHOUT = `<!doctype html><meta charset="utf-8"><body>
<iframe id="f" src="/tests/_child.html" style="width:300px;height:100px"></iframe>
</body>`;

const server = createServer(async (req, res) => {
  const url = req.url.split('?')[0];
  const send = (body, type = 'text/html') => {
    res.writeHead(200, { 'Content-Type': type });
    res.end(body);
  };
  if (url === '/tests/_child.html')          return send(CHILD);
  if (url === '/tests/_parent_server.html')  return send(PARENT_WITH_SERVER);
  if (url === '/tests/_parent_plain.html')   return send(PARENT_WITHOUT);
  try {
    const p = join(ROOT, decodeURIComponent(url));
    send(await readFile(p), MIME[extname(p)] || 'application/octet-stream');
  } catch {
    res.writeHead(404); res.end('not found');
  }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const PORT = server.address().port;
const BASE = `http://127.0.0.1:${PORT}`;

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
const page = await ctx.newPage();

async function childResult(parentUrl) {
  await page.goto(parentUrl);
  const frame = page.frames().find(f => f.url().includes('_child.html'));
  await frame.waitForFunction(() => !!window.__RESULT__);
  return frame.evaluate(() => window.__RESULT__);
}

// ── T1: IFRAME — ota freymda XENORA_SERVER bor (Electron holati) ────────────
{
  const r = await childResult(`${BASE}/tests/_parent_server.html`);
  check('T1_iframe_ota_freymdan_oldi', r.API_BASE, 'http://178.128.251.218/api/v1');
  check('T1_ws_ham_togri',             r.WS_BASE,  'ws://178.128.251.218');
}

// ── T2: IFRAME — hech qayerda XENORA_SERVER yo'q (oddiy brauzer/nginx) ──────
// Nisbiy manzil ishlatilishi kerak; `localhost:8000` ga TAXMINIY tushish YO'Q.
{
  const r = await childResult(`${BASE}/tests/_parent_plain.html`);
  check('T2_nisbiy_manzil',            r.API_BASE, '/api/v1');
  check('T2_localhost_taxmini_yoq',    r.API_BASE.includes('localhost:8000'), false);
}

// ── T3: REGRESSIYA — asosiy oyna (iframe emas) buzilmasin ───────────────────
{
  await page.goto(`${BASE}/tests/_child.html`);          // to'g'ridan-to'g'ri
  await page.waitForFunction(() => !!window.__RESULT__);
  const r = await page.evaluate(() => window.__RESULT__);
  check('T3_asosiy_oyna_nisbiy',       r.API_BASE, '/api/v1');
}

{
  // Asosiy oynada XENORA_SERVER bo'lsa — avvalgidek o'sha ishlatiladi
  await page.addInitScript(() => { window.XENORA_SERVER = 'http://10.0.0.5'; });
  await page.goto(`${BASE}/tests/_child.html`);
  await page.waitForFunction(() => !!window.__RESULT__);
  const r = await page.evaluate(() => window.__RESULT__);
  check('T3_asosiy_oyna_XENORA_SERVER', r.API_BASE, 'http://10.0.0.5/api/v1');
}

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
