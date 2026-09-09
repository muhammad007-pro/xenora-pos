/**
 * CHEK KENGLIGI — 80mm sozlamasi USB yo'liga yetib boradimi.
 *
 * MUAMMO (mijozda, 1001 BARAKA / XP-Q80AS): sozlamada 80mm qo'yilgan, lekin chek
 * ~50mm ga siqilib chiqardi. Sabab IKKITA qattiq yozilgan qiymat edi:
 *   · `receipt-print.js` CSS:  .r58{width:48mm}          — 58mm rolik uchun
 *   · `electron/main.js`:      @page{size:58mm ...}      — 58mm qattiq
 * `paperWidth` sozlamasi FAQAT LAN/ESC-POS yo'liga ulangan edi (main.js:287),
 * USB (SumatraPDF) yo'li uni umuman o'qimasdi.
 *
 * Ustiga `-print-settings fit` uzun chekni BALANDLIK bo'yicha kichraytirardi
 * (58mm → ~50mm). U `noscale` ga o'zgartirildi.
 *
 * ⚠️ GOLDEN QOIDA — FAZZA (58mm printer) BUZILMASIN:
 * `paperWidth` kelmasa, null bo'lsa yoki noma'lum qiymat bo'lsa → 58mm/48mm.
 * Bu test aynan shu zaxira yo'lni qulflaydi.
 *
 * PDF sahifa o'lchami Electron bilan alohida o'lchandi (2026-09-10):
 *   58 → 57.83mm · 80 → 80.09mm · null → 57.83mm · noma'lum → 57.83mm
 *
 * Ishga tushirish:  node frontend/tests/test_receipt_paper_width.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { resolve, extname, join } from 'path';

const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
               '.css': 'text/css', '.json': 'application/json' };
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

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
// Modulni brauzer kontekstida yuklaymiz (ES modul, DOM'siz ishlamaydi)
await page.goto(`${BASE}/shared/login.html`, { waitUntil: 'domcontentloaded' });
await page.addScriptTag({ type: 'module', content: `
  import { paperSpec, wrapDoc } from '${BASE}/js/core/receipt-print.js';
  window.__paperSpec = paperSpec;
  window.__wrapDoc = wrapDoc;
`});
await page.waitForFunction(() => typeof window.__paperSpec === 'function');

const spec = (w) => page.evaluate((v) => window.__paperSpec(v), w);
/** wrapDoc chiqishidan .r58 kengligini (mm) ajratadi */
const cssWidth = async (w) => page.evaluate((v) => {
  const html = window.__wrapDoc('<p>test</p>', 'Chek', { paperWidth: v });
  const m = html.match(/\.r58\{width:([\d.]+)mm;max-width:([\d.]+)mm/);
  return m ? [Number(m[1]), Number(m[2])] : null;
}, w);

// ══════════════════════════════════════════════════════════════════════════════
// 1) KENGLIK JADVALI
// ══════════════════════════════════════════════════════════════════════════════
check('1_58mm',        await spec(58), { page: 58, content: 48 });
check('1_57mm_ham_58', await spec(57), { page: 58, content: 48 });
check('1_80mm',        await spec(80), { page: 80, content: 72 });
check('1_matn_80',     await spec('80'), { page: 80, content: 72 });   // select qiymati matn bo'lishi mumkin

// ══════════════════════════════════════════════════════════════════════════════
// 2) ZAXIRA YO'L — FAZZA KAFOLATI (noma'lum → 58mm)
// ══════════════════════════════════════════════════════════════════════════════
for (const [nom, qiymat] of [
  ['null', null], ['undefined', undefined], ['bosh_satr', ''],
  ['nol', 0], ['xato_matn', 'xato'], ['notogri_son', 999],
]) {
  check(`2_zaxira_${nom}`, await spec(qiymat), { page: 58, content: 48 });
}

// ══════════════════════════════════════════════════════════════════════════════
// 3) CSS KONTENT KENGLIGI hujjatga tushadimi
// ══════════════════════════════════════════════════════════════════════════════
check('3_css_58mm', await cssWidth(58), [48, 48]);
check('3_css_80mm', await cssWidth(80), [72, 72]);
check('3_css_null_58ga_qaytadi', await cssWidth(null), [48, 48]);
check('3_css_opts_yoq', await page.evaluate(() => {
  const html = window.__wrapDoc('<p>t</p>', 'Chek');       // opts UMUMAN yo'q
  const m = html.match(/\.r58\{width:([\d.]+)mm/);
  return m ? Number(m[1]) : null;
}), 48);

// ══════════════════════════════════════════════════════════════════════════════
// 4) HUJJAT TUZILMASI buzilmagan (LAN yo'li DOM'dan o'qiydi)
// ══════════════════════════════════════════════════════════════════════════════
const doc = await page.evaluate(() => window.__wrapDoc('<p id="x">salom</p>', 'Chek', { paperWidth: 80 }));
check('4_r58_klassi_saqlandi', doc.includes('<div class="r58">'), true);
check('4_kontent_ichida',      doc.includes('<p id="x">salom</p>'), true);
check('4_page_margin_nol',     doc.includes('@page{margin:0}'), true);
check('4_doctype',             doc.startsWith('<!DOCTYPE html>'), true);

await browser.close();
server.close();
console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
