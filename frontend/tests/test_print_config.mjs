/**
 * PRINTER SOZLAMASI — jimgina "usb" ga tushmaslik (fix/remaining-issues).
 *
 * MUAMMO: POS sozlamani faqat ochilishda o'qirdi; so'rov yiqilsa yoki
 * `{success:false}` qaytsa xato yutilib, standart `print_type:'usb'` + bo'sh
 * printer nomi qolardi → Electron chekni WINDOWS STANDART printeriga (etiketka
 * printeri bo'lishi mumkin) yuborardi.
 *
 * Qotiriladi:
 *   1) Modul: xato / {success:false} → sozlama YO'Q (null), o'ram sozlama deb olinmaydi
 *   2) Muvaffaqiyat → kesh; keyingi ochilishda server yiqilsa — KESHDAGI aniq sozlama
 *   3) Eskirgan sozlamani yangilash yiqilsa — mavjud aniq sozlama QOLADI
 *   4) POS (Electron soxta): server yiqilgan + kesh yo'q → printer CHAQIRILMAYDI,
 *      ogohlantirish chiqadi; "Qayta urinish" server tiklangach AYNAN sozlangan
 *      printerga chiqaradi (deviceName/printType)
 *   5) POS: kesh bor + server yiqilgan → keshdagi printerga chiqadi
 *   6) Brauzer (Electron emas): to'siq yo'q — dialog orqali (avvalgidek)
 *   7) Admin printReceiptDoc ham shu modul orqali (statik)
 *
 * Ishga tushirish:  node frontend/tests/test_print_config.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { readFileSync } from 'fs';
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
const kut = ms => new Promise(r => setTimeout(r, ms));

const STATUS = { enabled: true, auto_print: false, printer_name: 'XP-58 (chek)', open_drawer_enabled: false };
const RECEIPT = { print_type: 'usb', printer_ip: null, printer_port: null, font_size: 'normal', paper_width: 58, store_name: 'DOKON' };
const tok = `x.${Buffer.from(JSON.stringify({ sub: '1', tenant_id: 27, exp: 4102444800, business_type: 'store', features: [] })).toString('base64')}.y`;

const browser = await chromium.launch({ headless: true });

// ── 1–3) Modul — sahifa ichida (localStorage haqiqiy) ──────────────────────────
console.log('\n── 1–3) print-config moduli ──');
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${BASE}/shared/offline.html`);
  const r = await page.evaluate(async () => {
    localStorage.clear();
    localStorage.setItem('user', JSON.stringify({ tenant_id: 27 }));
    const { createPrintConfig } = await import('/js/core/print-config.js');
    const S = { printer_name: 'XP-58 (chek)' }, R = { print_type: 'lan', printer_ip: '10.0.0.5', printer_port: 9100 };
    const out = {};
    // 1) tarmoq xatosi
    let c = createPrintConfig({ fetchStatus: () => Promise.reject(new Error('net')), fetchReceipt: () => Promise.resolve(R) });
    out.xato_ensure = await c.ensure(); out.xato_opts = c.printOpts();
    // 1b) api.js o'rami {success:false} — sozlama deb olinmaydi
    c = createPrintConfig({ fetchStatus: () => ({ success: false, error: '500' }), fetchReceipt: () => ({ success: false, error: '500' }) });
    out.orama_ensure = await c.ensure(); out.orama_opts = c.printOpts();
    // 2) muvaffaqiyat (o'ralgan) → kesh
    c = createPrintConfig({ fetchStatus: () => ({ success: true, data: S }), fetchReceipt: () => ({ success: true, data: R }) });
    out.ok_ensure = await c.ensure(); out.ok_opts = c.printOpts(); out.ok_src = c.source();
    out.kesh_yozildi = !!localStorage.getItem('xenora_print_cfg_v1:27');
    // 2b) yangi sahifa: server yiqilgan → KESH
    c = createPrintConfig({ fetchStatus: () => Promise.reject(new Error('net')), fetchReceipt: () => Promise.reject(new Error('net')) });
    out.kesh_ensure = await c.ensure(); out.kesh_src = c.source(); out.kesh_opts = c.printOpts();
    // 2c) boshqa do'kon — begona kesh ISHLATILMAYDI
    localStorage.setItem('user', JSON.stringify({ tenant_id: 99 }));
    c = createPrintConfig({ fetchStatus: () => Promise.reject(new Error('net')), fetchReceipt: () => Promise.reject(new Error('net')) });
    out.begona_ensure = await c.ensure();
    localStorage.setItem('user', JSON.stringify({ tenant_id: 27 }));
    // 3) eskirgan + yangilash yiqildi → aniq sozlama qoladi
    let fail = false;
    c = createPrintConfig({ fetchStatus: () => fail ? Promise.reject(new Error('net')) : ({ success: true, data: S }),
                            fetchReceipt: () => fail ? Promise.reject(new Error('net')) : ({ success: true, data: R }) });
    await c.ensure(); fail = true;
    out.eski_ensure = await c.ensure(0); out.eski_type = c.printOpts().printType;
    // timeout — osilgan so'rov chop etishni abadiy kuttirmaydi
    c = createPrintConfig({ fetchStatus: () => new Promise(() => {}), fetchReceipt: () => new Promise(() => {}), timeoutMs: 200 });
    localStorage.clear();
    const t0 = Date.now(); out.osilgan_ensure = await c.ensure(); out.osilgan_ms_lt_1s = Date.now() - t0 < 1000;
    return out;
  });
  check('1_xato_ensure_false', r.xato_ensure, false);
  check('1_xato_opts_null', r.xato_opts, null);
  check('1_success_false_orama_sozlama_emas', [r.orama_ensure, r.orama_opts], [false, null]);
  check('2_ok', [r.ok_ensure, r.ok_src], [true, 'server']);
  check('2_ok_opts', r.ok_opts, { deviceName: 'XP-58 (chek)', fontSize: 'normal', printType: 'lan', printerIp: '10.0.0.5', printerPort: 9100, paperWidth: null });
  check('2_kesh_yozildi', r.kesh_yozildi, true);
  check('2_server_yiqilsa_kesh', [r.kesh_ensure, r.kesh_src, r.kesh_opts?.deviceName, r.kesh_opts?.printType], [true, 'cache', 'XP-58 (chek)', 'lan']);
  check('2_begona_dokon_keshi_yoq', r.begona_ensure, false);
  check('3_eskirgan_yangilash_yiqildi_sozlama_qoldi', [r.eski_ensure, r.eski_type], [true, 'lan']);
  check('3_osilgan_sorov_timeout', [r.osilgan_ensure, r.osilgan_ms_lt_1s], [false, true]);
  await ctx.close();
}

// ── 4–6) POS — haqiqiy oqim, Electron soxta ────────────────────────────────────
async function pos({ electron = true, cache = null, serverUp }) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block' });
  await ctx.addInitScript(([t, el, cch]) => {
    if (!sessionStorage.getItem('__s')) {
      sessionStorage.setItem('__s', '1');
      localStorage.clear();
      localStorage.setItem('access_token', t); localStorage.setItem('business_type', 'store');
      localStorage.setItem('user', JSON.stringify({ id: 1, tenant_id: 27, role: { name: 'cashier' }, business_type: 'store' }));
      if (cch) localStorage.setItem('xenora_print_cfg_v1:27', JSON.stringify(cch));
    }
    window.__prints = [];
    if (el) window.electronAPI = { isElectron: true,
      printDocument: async (p) => { window.__prints.push({ deviceName: p.deviceName, printType: p.printType }); return { ok: true }; },
      printReceipt:  async (p) => { window.__prints.push({ deviceName: p.deviceName, printType: p.printType }); return { ok: true }; } };
  }, [tok, electron, cache]);
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  await ctx.route('**/api/**', r => {
    const p = new URL(r.request().url()).pathname.replace(/.*\/api\/v1/, '');
    if (p === '/settings/printer/status' || p === '/receipt-settings/') {
      if (!serverUp()) return r.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Internal server error"}' });
      return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(p === '/receipt-settings/' ? RECEIPT : STATUS) });
    }
    if (p === '/shifts/active') return r.fulfill({ status: 200, contentType: 'application/json', body: '{"id":5}' });
    r.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/app/pos.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.getElementById('loadingScreen')?.classList.contains('hidden'), null, { timeout: 15000 }).catch(() => {});
  await kut(500);
  const printNow = async () => {
    await page.evaluate(() => {
      document.getElementById('receiptBody').innerHTML = '<div>TEST CHEK</div>';
      document.getElementById('printReceiptBtn').click();
    });
    await kut(1600);
  };
  return { page, ctx, printNow };
}

console.log('\n── 4) POS: server yiqilgan, kesh yo\'q (Electron) ──');
{
  let up = false;
  const t = await pos({ serverUp: () => up });
  await t.printNow();
  check('4_printer_chaqirilmadi', await t.page.evaluate(() => window.__prints.length), 0);
  check('4_ogohlantirish', await t.page.isVisible('#xnPrintCfgAlert'), true);
  check('4_matn', /boshqa printerga yuborilmadi/.test(await t.page.textContent('#xnPrintCfgAlert')), true);
  up = true;
  await t.page.click('#xnPrintCfgAlert button[data-a="retry"]');
  await kut(1600);
  check('4_qayta_urinish_sozlangan_printerga', await t.page.evaluate(() => window.__prints), [{ deviceName: 'XP-58 (chek)', printType: 'usb' }]);
  check('4_ogohlantirish_yopildi', await t.page.isVisible('#xnPrintCfgAlert'), false);
  await t.ctx.close();
}

console.log('\n── 5) POS: kesh bor, server yiqilgan ──');
{
  const cache = { at: Date.now() - 3600e3, cfg: { printerName: 'XP-80 (kesh)', printType: 'lan', printerIp: '10.0.0.7', printerPort: 9100,
    fontSize: 'normal', paperWidth: 80, receipt: RECEIPT, status: STATUS } };
  const t = await pos({ cache, serverUp: () => false });
  await t.printNow();
  check('5_keshdagi_printerga', await t.page.evaluate(() => window.__prints), [{ deviceName: 'XP-80 (kesh)', printType: 'lan' }]);
  check('5_ogohlantirish_yoq', await t.page.isVisible('#xnPrintCfgAlert'), false);
  await t.ctx.close();
}

console.log('\n── 5b) POS: server ishlaydi — oddiy oqim (GOLDEN) ──');
{
  const t = await pos({ serverUp: () => true });
  await t.printNow();
  check('5b_sozlangan_printerga', await t.page.evaluate(() => window.__prints), [{ deviceName: 'XP-58 (chek)', printType: 'usb' }]);
  await t.ctx.close();
}

console.log('\n── 6) Brauzer: to\'siq yo\'q ──');
{
  const t = await pos({ electron: false, serverUp: () => false });
  await t.page.evaluate(() => { window.print = () => {}; });
  await t.printNow();
  check('6_brauzerda_ogohlantirish_yoq', await t.page.isVisible('#xnPrintCfgAlert'), false);
  await t.ctx.close();
}

console.log('\n── 7) Statik ──');
const POS = rd('js/modules/pos.js');
const AH = rd('app/admin.html');
check('7_pos_sukut_usb_emas', /font_size: 'normal', print_type: null/.test(POS), true);
check('7_pos_ikkala_yol_ensure', (POS.match(/await _ensurePrintCfg\(/g) || []).length, 2);
check('7_admin_modul', /import \{ createPrintConfig, showPrintConfigAlert \} from '\.\.\/js\/core\/print-config\.js'/.test(AH), true);
check('7_admin_eski_usb_zaxira_yoq', /r\.print_type\s*\|\|\s*'usb'/.test(AH), false);
check('7_sw_precache', /'\/js\/core\/print-config\.js'/.test(rd('service-worker.js')), true);

await browser.close();
server.close();
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
