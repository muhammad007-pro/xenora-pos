/**
 * PREMIUM OVERLAY sahifaning O'Z pozitsiyasini bosib ketmasin.
 *
 * ═══ MUAMMO (v1.13.0, jonli — returns.html) ═══
 * "Qaytarish sahifasida pastki yarmi qora fon, forma fonsiz."
 * Sabab `styles/premium-overlay.css`:
 *     body > *:not(.xa-atmos){position:relative;z-index:1}     → (0,1,1)
 * sahifaning `.modal-overlay{position:fixed;z-index:100}`      → (0,1,0)
 * qoidasini YUTARDI. Modal overlay bo'lmay, sahifa OXIRIGA oddiy blok bo'lib
 * tushardi — ostida `rgba(0,0,0,.7)` qora fon. 42 sahifaning 30+ tasida
 * 73 element (barcha modallar + sticky sarlavhalar) shunday edi.
 *
 * Tuzatish: `body > :where(:not(.xa-atmos))` — spetsifiklik (0,0,1).
 *
 * ⚠️ GOLDEN: pozitsiyasiz bloklar (`.pc`) hamon `relative / z 1` —
 * atmosfera (`.xa-atmos`, fixed z0) ustida qoladi.
 *
 * Ishga tushirish:  node frontend/tests/test_overlay_modal_position.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { readFileSync } from 'fs';
import { resolve, extname, join } from 'path';

const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };
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

// ── 0) Manba: eski yuqori spetsifikli qoida qaytmasin ───────────────────────
// Izohlar olib tashlanadi — ularda eski qoida TARIX sifatida tilga olingan
const CSS = readFileSync(resolve(ROOT, 'styles/premium-overlay.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
check('0_where_bilan', /body > :where\(:not\(\.xa-atmos\)\)\{position:relative;z-index:1\}/.test(CSS), true);
check('0_eski_qoida_YOQ', /body > \*:not\(\.xa-atmos\)/.test(CSS), false);

// ── Brauzer ────────────────────────────────────────────────────────────────
const jwt = 'x.' + Buffer.from(JSON.stringify({ sub: 'admin', features: [], business_type: 'store' })).toString('base64') + '.y';
const browser = await chromium.launch({ headless: true });

async function open(path) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, serviceWorkers: 'block' });
  await ctx.addInitScript(([t]) => {
    localStorage.setItem('access_token', t); localStorage.setItem('business_type', 'store');
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'admin', is_superuser: true, role: { name: 'admin' }, tenant_id: 26 }));
  }, [jwt]);
  const page = await ctx.newPage();
  await page.route('**/api/**', r => r.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
  await page.route(/fonts\.(googleapis|gstatic)\.com/, r => r.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  await page.goto(`${BASE}/${path}`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(400);
  return { ctx, page };
}
const pos = (page, sel) => page.evaluate(s => {
  const e = document.querySelector(s); if (!e) return null;
  const cs = getComputedStyle(e); return `${cs.position}/${cs.zIndex}`;
}, sel);

// ── 1) returns.html — asosiy shikoyat ──────────────────────────────────────
{
  const { ctx, page } = await open('app/returns.html');
  check('1_createModal_fixed', await pos(page, '#createModal'),       'fixed/100');
  check('1_picker_fixed',      await pos(page, '#orderPickerModal'),  'fixed/100');
  check('1_detail_fixed',      await pos(page, '#detailModal'),       'fixed/100');
  check('1_sarlavha_sticky',   await pos(page, 'body > .ph'),         'sticky/20');
  check('1_GOLDEN_pc_atmos_ustida', await pos(page, 'body > .pc'),    'relative/1');
  check('1_GOLDEN_atmos',      await pos(page, '.xa-atmos'),          'fixed/0');

  await page.evaluate(() => window.openCreateModal());
  await page.waitForTimeout(300);
  const g = await page.evaluate(() => {
    const r = document.getElementById('createModal').getBoundingClientRect();
    return { top: Math.round(r.top), h: Math.round(r.height), vh: innerHeight,
             scroll: document.documentElement.scrollHeight <= innerHeight };
  });
  // Overlay butun ekranni yopadi va sahifa PASTGA cho'zilmaydi
  check('1_modal_ekranni_yopadi', [g.top, g.h], [0, g.vh]);
  check('1_sahifa_chozilmadi', g.scroll, true);
  await ctx.close();
}

// ── 2) Boshqa modal naqshlari (har xil klass nomlari) ──────────────────────
for (const [page_, sel, want] of [
  ['app/bonus_cards.html', '#modalCreate', 'fixed/999'],   // .modal-overlay
  ['app/shift.html',       '#closeShiftModal', 'fixed/200'], // .modal-wrap
  ['app/employees.html',   '#empMo', 'fixed/100'],          // .mo
  ['app/cafes.html',       '#cafeModal', 'fixed/100'],      // .modal
]) {
  const { ctx, page } = await open(page_);
  check(`2_${page_}_${sel}`, await pos(page, sel), want);
  await ctx.close();
}

await browser.close(); server.close();
console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
