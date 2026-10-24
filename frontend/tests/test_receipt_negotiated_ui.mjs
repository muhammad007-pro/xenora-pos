/**
 * CHEKDA KELISHILGAN NARX — frontend (feature/receipt-negotiated-price).
 *
 * Qotiriladi:
 *   1) JS `negotiatedLines` (jonli POS cheki) == Python `receipt_line_totals`
 *      (qayta chop etish, vozvrat) — bir xil kirishda bir xil natija
 *   2) buildReceipt58 (qayta chop etish): "1 x 245 000 ... 220 000",
 *      "Chegirmasiz:" = qatorlar yig'indisi, qolgan chegirma 0 → qator yo'q
 *   3) GOLDEN: kelishuvsiz chek HTML'i `main` dagi bilan AYNAN bir xil
 *      (chegirmasiz chekda — butunlay; chegirmalida faqat "Jami:" → "Chegirmasiz:")
 *   4) 58mm va 80mm: qator sig'adi, uzun nom o'raladi, summa ustuni kesilmaydi
 *   5) LAN (ESC/POS): main.js DOM'dan o'qigan qator 32/48 belgiga sig'adi
 *   6) pos.js jonli chek negotiatedLines + subtotalLabel ga ulangan
 *
 * Ishga tushirish:  node frontend/tests/test_receipt_negotiated_ui.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { readFileSync, writeFileSync, unlinkSync } from 'fs';
import { resolve, extname, join } from 'path';
import { spawnSync, execSync } from 'child_process';
import { createRequire } from 'module';

const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css' };
let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

// `main` dagi receipt-print.js — GOLDEN solishtirish uchun (o'sha papkaga, importlar ishlasin)
const MAIN_FILE = 'frontend/js/core/_receipt_print_main_tmp.js';
writeFileSync(MAIN_FILE, execSync('git show main:frontend/js/core/receipt-print.js', { encoding: 'utf8', maxBuffer: 1 << 24 }));

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
const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage();
  await page.goto(`${BASE}/shared/login.html`, { waitUntil: 'domcontentloaded' });
  await page.addScriptTag({ type: 'module', content: `
    import * as R from '${BASE}/js/core/receipt-print.js';
    import * as M from '${BASE}/js/core/_receipt_print_main_tmp.js';
    window.__R = R; window.__M = M;
  `});
  await page.waitForFunction(() => window.__R && window.__M);

  // ── 1) JS == Python ────────────────────────────────────────────────────────
  console.log('\n── 1) JS negotiatedLines == Python receipt_line_totals ──');
  const s = (id, price, n = null, qty = 1) => ({ id, price, qty, _priceNew: n });
  const CASES = {
    chek_4804:    { disc: 70000, cart: [s(1, 245000, 220000), s(2, 380000, 360000), s(3, 295000, 270000)] },
    foiz_ustiga:  { disc: 59500, cart: [s(1, 245000, 220000), s(2, 100000)] },
    kg_qatori:    { disc: 999,   cart: [s(1, 14999, 14000), s(2, 50000)] },
    oshirilgan:   { disc: 20000, cart: [s(1, 245000, 260000), s(2, 380000, 360000)] },
    kasr:         { disc: 19999.8, cart: [s(1, 40000, 33333.4, 3)] },
    kelishuvsiz:  { disc: 62500, cart: [s(1, 245000), s(2, 380000)] },
    katta_kelish: { disc: 50000, cart: [s(1, 245000, 220000), s(2, 380000, 360000), s(3, 295000, 270000)] },
    manfiy:       { disc: 70000, cart: [s(1, 245000, -5)] },
  };
  const js = await page.evaluate((C) => Object.fromEntries(Object.entries(C).map(([k, v]) =>
    [k, window.__R.negotiatedLines(v.cart, v.disc)])), CASES);
  const PY = `
import json, sys
from types import SimpleNamespace as N
sys.path.insert(0, '.')
from routers.returns import receipt_line_totals
C = json.loads(sys.stdin.read())
out = {}
for k, v in C.items():
    items = [N(id=i + 1, product_id=c['id'], total_price=round(max(c['price'], c['_priceNew'] if c['_priceNew'] is not None else c['price']) * c['qty'], 2))
             for i, c in enumerate(v['cart'])]
    r = receipt_line_totals(N(discount_amount=v['disc'], biz_meta={'cart': v['cart']}), items)
    out[k] = None if r is None else {'lines': [r['lines'][i + 1] for i in range(len(items))], 'subtotal': r['subtotal'],
                                     'other_discount': r['other_discount'], 'negotiated': r['negotiated']}
print(json.dumps(out))`;
  let py = null;
  for (const cmd of ['py', 'python3', 'python']) {
    const r = spawnSync(cmd, ['-c', PY], { cwd: 'backend', input: JSON.stringify(CASES), encoding: 'utf8' });
    if (r.error) continue;
    py = r.status === 0 ? JSON.parse(r.stdout.trim().split('\n').pop()) : { xato: r.stderr.slice(-500) };
    break;
  }
  for (const k of Object.keys(CASES)) check(`1_${k}`, js[k], py && py[k]);
  check('1_4804_qiymat', js.chek_4804, { lines: [220000, 360000, 270000], subtotal: 850000, other_discount: 0, negotiated: 70000 });
  check('1_foiz_qolgan_chegirma', js.foiz_ustiga && js.foiz_ustiga.other_discount, 34500);
  check('1_zaxira_null', [js.kelishuvsiz, js.katta_kelish, js.manfiy], [null, null, null]);

  // ── 2) Qayta chop etish (server javobi → buildReceipt58) ───────────────────
  console.log('\n── 2) buildReceipt58 ──');
  const REC_4804 = {
    order_number: '2610210051', date: '21.10.2026 15:00', cafe_name: 'MANHATTAN',
    items: [
      { name: 'SHIM KLASSIK', quantity: 1, unit_price: 245000, total: 245000, line_total: 220000 },
      { name: 'KURTKA', quantity: 1, unit_price: 380000, total: 380000, line_total: 360000 },
      { name: 'SVITR', quantity: 1, unit_price: 295000, total: 295000, line_total: 270000 },
    ],
    subtotal: 920000, discount_amount: 70000, discount: 70000, final_amount: 850000,
    receipt_subtotal: 850000, discount_other: 0,
    payment_methods: [{ method: 'cash', amount: 850000 }],
  };
  const REC_FOIZ = {
    ...REC_4804,
    items: [{ name: 'SHIM', quantity: 1, unit_price: 245000, total: 245000, line_total: 220000 },
            { name: 'KEPKA', quantity: 1, unit_price: 100000, total: 100000, line_total: 100000 }],
    subtotal: 345000, discount_amount: 59500, discount: 59500, final_amount: 285500,
    receipt_subtotal: 320000, discount_other: 34500,
  };
  const parse = (html) => page.evaluate((h) => {
    const d = document.createElement('div'); d.innerHTML = h;
    return {
      rows: [...d.querySelectorAll('.receipt-table tbody tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent.trim())),
      totals: [...d.querySelectorAll('.receipt-totals .rt-row')].map(r => [...r.querySelectorAll('span')].map(x => x.textContent.trim())),
    };
  }, html);
  const build = (rec, mod = '__R') => page.evaluate(([r, m]) => window[m].buildReceipt58(r), [rec, mod]);
  let p = await parse(await build(REC_4804));
  check('2_qatorlar', p.rows.map(r => [r[1], r[2]]), [['1 x 245 000', '220 000'], ['1 x 380 000', '360 000'], ['1 x 295 000', '270 000']]);
  check('2_jami_yorliq', p.totals.slice(0, 2), [['Chegirmasiz:', '850 000'], ['UMUMIY:', '850 000 UZS']]);
  p = await parse(await build(REC_FOIZ));
  check('2_foiz_qolgan_chegirma', p.totals.slice(0, 3), [['Chegirmasiz:', '320 000'], ['Chegirma:', '-34 500'], ['UMUMIY:', '285 500 UZS']]);

  // ── 3) GOLDEN — main bilan solishtirish ────────────────────────────────────
  console.log('\n── 3) GOLDEN (main) ──');
  const OLD_NODISC = { order_number: '1', date: 'x', items: [{ name: 'A', quantity: 2, unit_price: 5000, total: 10000 }],
                       subtotal: 10000, discount_amount: 0, final_amount: 10000, payment_methods: [] };
  check('3_chegirmasiz_aynan_main', await build(OLD_NODISC), await build(OLD_NODISC, '__M'));
  const OLD_DISC = { ...OLD_NODISC, discount_amount: 1000, discount: 1000, final_amount: 9000 };
  const nw = await build(OLD_DISC), ol = await build(OLD_DISC, '__M');
  check('3_chegirmali_faqat_yorliq', nw === ol.replace('<span>Jami:</span>', '<span>Chegirmasiz:</span>'), true);
  check('3_chegirmali_qator_ozgarmadi', (await parse(nw)).rows, (await parse(ol)).rows);

  // ── 4) 58mm / 80mm ─────────────────────────────────────────────────────────
  console.log('\n── 4) 58mm / 80mm ──');
  const LONG = { ...REC_4804, items: [{ ...REC_4804.items[0], name: 'ERKAKLAR KLASSIK SHIMI QORA RANG 52-OLCHAM PREMIUM' },
                                       ...REC_4804.items.slice(1)] };
  for (const w of [58, 80]) {
    const inner = await build(LONG);
    const doc = await page.evaluate(([h, pw]) => window.__R.wrapDoc(h, 'Chek', { paperWidth: pw }), [inner, w]);
    const pg = await browser.newPage({ viewport: { width: 400, height: 900 } });
    await pg.setContent(doc);
    const m = await pg.evaluate(() => {
      const box = document.querySelector('.r58') || document.body;
      const br = box.getBoundingClientRect();
      const trs = [...document.querySelectorAll('.receipt-table tbody tr')];
      return {
        boxMm: Math.round(br.width * 25.4 / 96),
        toshmaydi: box.scrollWidth <= box.clientWidth + 1,
        qatorlar: trs.map(tr => {
          const [n, q, s] = tr.querySelectorAll('td');
          const rq = q.getBoundingClientRect(), rs = s.getBoundingClientRect(), rn = n.getBoundingClientRect();
          return { birQatorda: Math.abs(rq.top - rs.top) < 2, ichida: rs.right <= br.right + 1,
                   summa: s.textContent.trim(), nomQatorlari: Math.round(rn.height / parseFloat(getComputedStyle(n).lineHeight)) };
        }),
      };
    });
    await pg.close();
    check(`4_${w}_kenglik`, m.boxMm, w === 58 ? 48 : 72);
    check(`4_${w}_toshmaydi`, m.toshmaydi, true);
    check(`4_${w}_soni_va_summa_bir_qatorda`, m.qatorlar.map(q => [q.birQatorda, q.ichida, q.summa]),
          [[true, true, '220 000'], [true, true, '360 000'], [true, true, '270 000']]);
    check(`4_${w}_uzun_nom_oraladi`, m.qatorlar[0].nomQatorlari >= 2, true);
  }

  // ── 5) LAN (ESC/POS) — main.js DOM ekstraktsiyasi → escpos-builder ─────────
  console.log('\n── 5) LAN ──');
  const require = createRequire(resolve('electron/package.json'));
  const E = require('./escpos-builder.js');
  p = await parse(await build(REC_4804));
  for (const w of [58, 80]) {
    const cols = E.charsForWidth(w);
    const lines = p.rows.map(r => E.row(`  ${E.qtyLabel(r[1])}`, r[r.length - 1], cols));
    check(`5_${w}_qator`, lines[0], E.row('  1 x 245 000', '220 000', cols));
    check(`5_${w}_sigadi_kesilmaydi`, lines.every(l => l.length === cols && /1 x \d/.test(l) && /\d{3} 000$/.test(l)), true);
    check(`5_${w}_jami_qatori`, E.row(p.totals[0][0], p.totals[0][1], cols).startsWith('Chegirmasiz:'), true);
  }

  // ── 6) pos.js ulanishi (statik) ────────────────────────────────────────────
  console.log('\n── 6) pos.js ──');
  const POS = readFileSync('frontend/js/modules/pos.js', 'utf8');
  check('6_import', /negotiatedLines, subtotalLabel/.test(POS), true);
  check('6_savatdan', /const _ng = rec\.items \? null : negotiatedLines\(state\.cart, t\.totalDisc\)/.test(POS), true);
  check('6_qator_summasi', /const line = _ng \? _ng\.lines\[idx\]/.test(POS), true);
  check('6_yorliq', /subtotalLabel\(_ng \? true : _discAll > 0\)/.test(POS), true);
} finally {
  await browser.close();
  server.close();
  try { unlinkSync(MAIN_FILE); } catch { /* yo'q */ }
}
console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
