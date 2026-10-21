/**
 * MOLIYA → "XODIMLAR" yorlig'i (feature/staff-sales-report), soxta API bilan.
 *
 * Qotiriladi:
 *   1) #staff bilan ochiladi, JS xatosi yo'q, kartalar va jadval to'ladi
 *   2) Alohida kategoriya tanlanmagan → Asosiy/Alohida ustunlari yashirin + izoh
 *   3) Tanlangan → ustunlar ko'rinadi, kategoriya nomi kartada
 *   4) Xodim qatori bosilsa kunlar ochiladi, yana bosilsa yopiladi
 *   5) ⚙️ panel ochiladi, belgilar serverdagidek, Saqlash → PATCH + qayta yuklash
 *   6) Davr almashsa yorliq qayta yuklanadi; "bonus" so'zi sahifada yo'q
 *   7) Telefon kengligida sahifa gorizontal surilmaydi
 *
 * Ishga tushirish:  node frontend/tests/test_staff_sales_ui.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { resolve, extname, join } from 'path';

const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
               '.svg': 'image/svg+xml', '.json': 'application/json' };
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
const kut = ms => new Promise(r => setTimeout(r, ms));
const TOKEN = `x.${Buffer.from(JSON.stringify({ sub: '1', user_id: 1, tenant_id: 30,
  business_type: 'store', exp: 4102444800, type: 'access' })).toString('base64')}.y`;
const CHART_STUB = 'window.Chart=function(){return{destroy(){},update(){}}};Chart.defaults={font:{}};';

const CATS = [{ id: 51, name: 'SHIM', parent_id: null }, { id: 56, name: 'OBUV', parent_id: null },
              { id: 67, name: 'atirlar', parent_id: null }];

function staffResp(split, q) {
  const sep = split ? 26_000_000 : 0;
  return {
    period: { from: q.get('date_from') || '2026-09-22', to: '2026-10-21' },
    config: { split: !!split, category_ids: split ? [51, 56] : [],
              categories: split ? [{ id: 51, name: 'SHIM' }, { id: 56, name: 'OBUV' }] : [] },
    items: [
      { seller_id: 28, name: 'AZIZBEK', orders_count: 195, returns_count: 4, sales: 107_000_000,
        returns: 1_690_000, net: 105_310_000, main_net: 105_310_000 - sep, separate_net: sep,
        days: [{ date: '2026-10-20', net: 3_200_000, separate_net: split ? 1_000_000 : 0 },
               { date: '2026-10-21', net: -150_000, separate_net: split ? -150_000 : 0 }] },
      { seller_id: null, name: 'Belgilanmagan', orders_count: 0, returns_count: 1, sales: 0,
        returns: 50_000, net: -50_000, main_net: -50_000, separate_net: 0, days: [] },
    ],
    totals: { sales: 107_000_000, returns: 1_740_000, net: 105_260_000,
              main_net: 105_260_000 - sep, separate_net: sep },
  };
}

async function ochish(browser, { width = 1280, split = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, serviceWorkers: 'block' });
  await ctx.addInitScript(t => {
    localStorage.setItem('access_token', t);
    localStorage.setItem('business_type', 'store');
  }, TOKEN);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, r =>
    r.request().url().includes('chart')
      ? r.fulfill({ status: 200, contentType: 'text/javascript', body: CHART_STUB })
      : r.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  const state = { split, saved: null };
  const calls = [];
  await page.route('**/api/v1/**', async r => {
    const u = new URL(r.request().url());
    const path = u.pathname.replace(/.*\/api\/v1/, '');
    const m = r.request().method();
    calls.push({ m, path, q: u.search });
    let out = {};
    if (path === '/profit/summary') out = { business_type: 'store', revenue: 105_260_000, cost: 0,
      gross_profit: 0, expenses: 0, net_profit: 0, orders_count: 195 };
    else if (path === '/profit/timeline') out = { points: [] };
    else if (path === '/profit/staff-sales') out = staffResp(state.split, u.searchParams);
    else if (path === '/settings/staff-split' && m === 'GET')
      out = { category_ids: state.split ? [51, 56] : [], categories: CATS };
    else if (path === '/settings/staff-split' && m === 'PATCH') {
      state.saved = JSON.parse(r.request().postData());
      state.split = state.saved.category_ids.length > 0;
      out = { category_ids: state.saved.category_ids, message: 'Sozlama saqlandi' };
    } else out = { items: [] };
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(out) });
  });
  await page.goto(`${BASE}/app/profit.html#staff`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => /AZIZBEK/.test(document.getElementById('stBody')?.textContent || ''),
    null, { timeout: 15000 });
  return { page, ctx, calls, errors, state };
}

const visibleCols = page => page.$$eval('#stTbl thead th', ths =>
  ths.filter(th => getComputedStyle(th).display !== 'none').map(th => th.textContent.trim()));
const num = s => Number(String(s).replace(/[^\d-]/g, ''));

const browser = await chromium.launch({ headless: true });

// ═══ 1–2) Ajratishsiz ══════════════════════════════════════════════════════════
console.log('\n── 1–2) Ajratish sozlanmagan ──');
{
  const t = await ochish(browser);
  const p = t.page;
  check('1_yorliq_faol', await p.$eval('.tab.active', b => b.dataset.tab), 'staff');
  check('1_pane_korinadi', await p.isVisible('#tab-staff'), true);
  check('1_sof_savdo_karta', num(await p.textContent('#stNet')), 105_260_000);
  check('1_vozvrat_izohi', (await p.textContent('#stNetSub')).includes('vozvrat'), true);
  check('1_jadval_qatorlari', await p.$$eval('#stBody > tr', trs => trs.length), 2);
  check('1_belgilanmagan_oxirida', (await p.textContent('#stBody tr:last-child td')).includes('Belgilanmagan'), true);
  check('1_jami_qatori', num(await p.textContent('#stFoot td:nth-child(5)')), 105_260_000);
  check('2_ustunlar_yashirin', await visibleCols(p), ['Xodim', 'Chek', 'Savdo', 'Vozvrat', 'Sof savdo']);
  check('2_izoh_korinadi', await p.isVisible('#stNoSplit'), true);
  check('2_alohida_karta_yashirin', await p.isVisible('#stSepNet'), false);
  check('6_bonus_sozi_yoq', /bonus/i.test(await p.textContent('body')), false);
  await p.screenshot({ path: 'frontend/tests/_staff_nosplit.png', fullPage: true });

  // ═══ 5) Sozlama paneli → saqlash ═══
  console.log('\n── 5) ⚙️ sozlama ──');
  check('5_panel_yopiq', await p.isVisible('#stCfg'), false);
  await p.click('#stCfgBtn');
  await p.waitForFunction(() => document.querySelectorAll('#stCats input').length === 3, null, { timeout: 5000 });
  check('5_panel_ochildi', await p.isVisible('#stCfg'), true);
  check('5_belgilanmagan', await p.$$eval('#stCats input:checked', x => x.length), 0);
  await p.check('#stCats input[value="51"]');
  await p.check('#stCats input[value="56"]');
  t.calls.length = 0;
  await p.click('#stSave');
  await p.waitForFunction(() => !document.getElementById('tab-staff').classList.contains('no-split'), null, { timeout: 5000 });
  check('5_patch_yuborildi', t.state.saved, { category_ids: [51, 56] });
  check('5_qayta_yuklandi', t.calls.some(c => c.path === '/profit/staff-sales'), true);
  check('5_panel_yopildi', await p.isVisible('#stCfg'), false);
  check('3_ustunlar_korinadi', await visibleCols(p),
        ['Xodim', 'Chek', 'Savdo', 'Vozvrat', 'Sof savdo', 'Asosiy', 'Alohida']);
  check('3_alohida_karta', num(await p.textContent('#stSepNet')), 26_000_000);
  check('3_kategoriya_nomlari', await p.textContent('#stSepCats'), 'SHIM, OBUV');
  check('3_izoh_yashirin', await p.isVisible('#stNoSplit'), false);
  await p.click('#stCfgBtn');
  await p.waitForFunction(() => document.querySelectorAll('#stCats input:checked').length === 2, null, { timeout: 5000 });
  check('5_qayta_ochilganda_belgilar', await p.$$eval('#stCats input:checked', x => x.map(i => i.value)), ['51', '56']);
  await p.click('#stCfgBtn');

  // ═══ 4) Kunlar ═══
  console.log('\n── 4) Kunlar ──');
  await p.click('#stBody tr:first-child');
  await p.waitForFunction(() => document.querySelectorAll('#stBody > tr').length === 4, null, { timeout: 5000 });
  const days = await p.$$eval('#stBody > tr', trs => trs.slice(1, 3).map(tr =>
    [...tr.querySelectorAll('td')].filter(td => getComputedStyle(td).display !== 'none').map(td => td.textContent.trim())));
  check('4_kun_sanalari', days.map(d => d[0]), ['20.10.2026', '21.10.2026']);
  check('4_kun_ustunlar_soni', days[0].length, 7);
  check('4_kun_asosiy_alohida', [num(days[0][5]), num(days[0][6])], [2_200_000, 1_000_000]);
  check('4_manfiy_kun_qizil', await p.$eval('#stBody > tr:nth-child(3) td:nth-child(5)', td => td.classList.contains('neg')), true);
  check('4_belgi_ochiq', (await p.textContent('#stBody tr:first-child td')).trim().startsWith('▾'), true);
  await p.click('#stBody tr:first-child');
  await p.waitForFunction(() => document.querySelectorAll('#stBody > tr').length === 2, null, { timeout: 5000 });
  check('4_yopildi', await p.$$eval('#stBody > tr', trs => trs.length), 2);
  await p.click('#stBody tr:first-child');
  await p.waitForFunction(() => document.querySelectorAll('#stBody > tr').length === 4, null, { timeout: 5000 });
  await p.screenshot({ path: 'frontend/tests/_staff_split.png', fullPage: true });

  // ═══ 6) Davr ═══
  console.log('\n── 6) Davr ──');
  t.calls.length = 0;
  await p.click('.pb[data-p="month"]');
  await kut(500);
  check('6_davr_qayta_yuklandi', t.calls.filter(c => c.path === '/profit/staff-sales').map(c => c.q), ['?period=month']);
  t.calls.length = 0;
  await p.fill('#pFrom', '2026-10-01');
  await p.fill('#pTo', '2026-10-21');
  await p.click('#pApply');
  await kut(500);
  check('6_oraliq', t.calls.some(c => c.path === '/profit/staff-sales' && c.q.includes('date_from=2026-10-01')
                                      && c.q.includes('date_to=2026-10-21')), true);
  check('1_xatosiz', t.errors, []);
  await t.ctx.close();
}

// ═══ 7) Telefon kengligi ═══════════════════════════════════════════════════════
console.log('\n── 7) Telefon (390px) ──');
{
  const t = await ochish(browser, { width: 390, split: true });
  const over = await t.page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check('7_gorizontal_surilmaydi', over <= 0, true);
  check('7_yorliq_korinadi', await t.page.isVisible('.tab[data-tab="staff"]'), true);
  await t.page.screenshot({ path: 'frontend/tests/_staff_mobile.png', fullPage: true });
  check('7_xatosiz', t.errors, []);
  await t.ctx.close();
}

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
