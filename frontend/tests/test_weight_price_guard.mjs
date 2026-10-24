/**
 * OG'IRLIK × MIQDOR (#4094) + NARX CHEGARASI — frontend (fix/weight-qty-and-price-limit).
 *
 * Kod fayllardan AJRATIB olinadi (nusxa emas) — kod o'zgarsa test ham u bilan.
 *   A) qty-guard.js guardPrice/priceError: > 1 mlrd rad, 8+ xona tasdiq, oddiy narx jim
 *   B) pos.js _lineQty: qty 1 = _weight AYNAN (GOLDEN), qty 2 × 1 kg = 2 kg,
 *      summa rejimida summadan (server ±0.0005 oralig'i)
 *   C) pos.js _commitPrice: shtrix-kod qo'shilgan narx rad, 8 xona → confirm,
 *      "Yo'q" → narx o'zgarmaydi, oddiy oshirish so'ramaydi
 *   D) ulanish: kirim oynasi, ombor sahifasi, priyomka (2 sahifa), admin mahsulot
 *
 * Ishga tushirish:  node frontend/tests/test_weight_price_guard.mjs
 */
import fs from 'fs';
import path from 'path';
import vm from 'vm';
import assert from 'assert/strict';
import { fileURLToPath } from 'url';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = p => fs.readFileSync(path.join(ROOT, p), 'utf8').replace(/\r\n/g, '\n');

let pass = 0, fail = 0;
function t(name, fn) {
  try { fn(); pass++; console.log('  ok  ' + name); }
  catch (e) { fail++; console.log('  XATO ' + name + '\n       ' + e.message); }
}

// ── A) qty-guard.js ─────────────────────────────────────────────────────────
const calls = { alert: [], confirm: [] };
let confirmAnswer = true;
const g = {
  alert:   m => { calls.alert.push(m); },
  confirm: m => { calls.confirm.push(m); return confirmAnswer; },
};
g.window = g;
vm.createContext(g);
vm.runInContext(read('js/core/qty-guard.js'), g);
const reset = () => { calls.alert = []; calls.confirm = []; confirmAnswer = true; };

console.log('A) guardPrice');
t('PRICE_MAX = 1 mlrd (server price_guard.MAX_PRICE bilan bir)', () => {
  assert.equal(g.PRICE_MAX, 1_000_000_000);
  assert.match(read('../backend/services/price_guard.py'), /MAX_PRICE = 1_000_000_000/);
});
t('RIZQ naqshi "12000"+shtrix-kod → rad, alert, confirm YO\'Q', () => {
  reset();
  assert.equal(g.guardPrice('12000' + '4780019480030', 'Tan narx'), false);
  assert.equal(calls.alert.length, 1);
  assert.equal(calls.confirm.length, 0);
  assert.match(calls.alert[0], /^Tan narx: Narx juda katta/);
});
t('1 000 000 001 → rad; 1 000 000 000 → o\'tadi (tasdiq bilan)', () => {
  reset();
  assert.equal(g.guardPrice('1000000001'), false);
  reset();
  assert.equal(g.guardPrice('1000000000'), true);
  assert.equal(calls.confirm.length, 1);
});
t('EAN-8 "47800194" → "shtrix-kodga o\'xshaydi" tasdig\'i; Yo\'q → false', () => {
  reset(); confirmAnswer = false;
  assert.equal(g.guardPrice('47800194', 'Narx'), false);
  assert.equal(calls.confirm.length, 1);
  assert.match(calls.confirm[0], /shtrix-kodga o'xshaydi/);
  reset(); confirmAnswer = true;
  assert.equal(g.guardPrice('47800194', 'Narx'), true);
});
t('oddiy narxlar jim: 7 xona, formatlangan, kasr, bo\'sh', () => {
  for (const v of ['9999999', '5 500 000', '7,000', '12500.50', '', null, undefined, 0]) {
    reset();
    assert.equal(g.guardPrice(v), true, String(v));
    assert.equal(calls.alert.length + calls.confirm.length, 0, String(v));
  }
});
t('formatlangan 8 xona "15 000 000" ham so\'raladi (to\'smaydi)', () => {
  reset();
  assert.equal(g.guardPrice('15 000 000'), true);
  assert.equal(calls.confirm.length, 1);
});

// ── B) pos.js _lineQty ──────────────────────────────────────────────────────
const POS = read('js/modules/pos.js');
function grab(src, re, what) {
  const m = src.match(re);
  if (!m) throw new Error(`"${what}" topilmadi — test eskirgan`);
  return m[0];
}
const ctx = {}; vm.createContext(ctx);
vm.runInContext(grab(POS, /function _lineQty\(i\)[\s\S]*?\n}\n/, '_lineQty'), ctx);
const { _lineQty } = ctx;

console.log('B) _lineQty');
t('oddiy dona qatori: qty AYNAN', () => assert.equal(_lineQty({ qty: 3 }), 3));
t('GOLDEN qty 1: _weight AYNAN (0.656)', () => assert.equal(_lineQty({ qty: 1, _weight: 0.656 }), 0.656));
t('#4094: qty 2 × 1 kg → 2 kg (eski klient 1 kg yuborardi)', () =>
  assert.equal(_lineQty({ qty: 2, _weight: 1, _unitPrice: 70000 }), 2));
t('qty 3 × 0.35 → 1.05 (float axlatsiz)', () =>
  assert.equal(_lineQty({ qty: 3, _weight: 0.35, _unitPrice: 26500 }), 1.05));
t('summa rejimi qty 2: round3(summa×2/narx), server oralig\'ida', () => {
  const P = 26500, T = 15010;
  const q = _lineQty({ qty: 2, _weight: Math.round(T / P * 1000) / 1000, _lineTotal: T, _unitPrice: P });
  assert.equal(q, Math.round(T * 2 / P * 1000) / 1000);
  assert.ok(Math.abs(q - (T * 2) / P) <= 0.0005);
});
t('narx kelishuvli og\'irlik qatori summa rejimiga tushmaydi', () =>
  assert.equal(_lineQty({ qty: 2, _weight: 0.5, _lineTotal: 9000, _priceNew: 20000, _unitPrice: 18000 }), 1));
t('payload: quantity va gift-suggestions IKKALASI _lineQty dan', () => {
  assert.match(POS, /quantity\s*: _lineQty\(i\)/);
  assert.match(POS, /product_id: i\.id, quantity: _lineQty\(i\)/);
  assert.doesNotMatch(POS, /quantity\s*:\s*i\._weight != null \? i\._weight : i\.qty/);
});

// ── C) pos.js _commitPrice ──────────────────────────────────────────────────
console.log('C) POS narx kelishuvi');
function posCtx(item, answer) {
  const c = {
    state: { cart: [item] }, toasts: [], asked: [],
    parseMoney: s => Number(String(s).replace(/[\s,]/g, '')),
    fmtNum: n => String(n), beep: () => {}, renderCart: () => {},
  };
  c.toast = m => c.toasts.push(m);
  c.window = { confirm: m => { c.asked.push(m); return answer; } };
  vm.createContext(c);
  vm.runInContext(
    grab(POS, /const PRICE_MAX = \d+;/, 'PRICE_MAX') + '\nlet _priceCommitting = false;\n' +
    grab(POS, /function _commitPrice\(inp\)[\s\S]*?\n}\n/, '_commitPrice'), c);
  return c;
}
t('POS PRICE_MAX = 1 mlrd', () => assert.match(POS, /const PRICE_MAX = 1000000000;/));
t('shtrix-kod qo\'shilgan narx → rad, narx o\'zgarmaydi', () => {
  const item = { price: 12000, _priceNew: null, qty: 1 };
  const c = posCtx(item, true);
  const el = { dataset: { idx: '0' }, value: '120004780019480030' };
  c._commitPrice(el);
  assert.equal(item._priceNew, null);
  assert.match(c.toasts[0], /shtrix-kod/);
  assert.equal(c.asked.length, 0);
});
t('8 xona → confirm; Yo\'q → narx o\'zgarmaydi', () => {
  const item = { price: 12000, _priceNew: null, qty: 1 };
  const c = posCtx(item, false);
  c._commitPrice({ dataset: { idx: '0' }, value: '47800194' });
  assert.equal(c.asked.length, 1);
  assert.match(c.asked[0], /shtrix-kodga o'xshaydi/);
  assert.equal(item._priceNew, null);
});
t('8 xona → confirm; Ha → qabul', () => {
  const item = { price: 12000000, _priceNew: null, qty: 1 };
  const c = posCtx(item, true);
  c._commitPrice({ dataset: { idx: '0' }, value: '15000000' });
  assert.equal(item._priceNew, 15000000);
});
t('oddiy oshirish so\'ramaydi', () => {
  const item = { price: 12000, _priceNew: null, qty: 1 };
  const c = posCtx(item, false);
  c._commitPrice({ dataset: { idx: '0' }, value: '14000' });
  assert.equal(c.asked.length, 0);
  assert.equal(item._priceNew, 14000);
});

// ── D) ulanish ──────────────────────────────────────────────────────────────
console.log('D) ulanish');
const fnBody = (src, re, what) => grab(src, re, what);
t('admin kirim oynasi (inventory.js saveRestock) rmUnitPrice', () => {
  const b = fnBody(read('js/admin/inventory.js'), /async function saveRestock\(\)[\s\S]*?\n}\n/, 'saveRestock');
  assert.match(b, /guardPrice\(document\.getElementById\('rmUnitPrice'\)\.value/);
  assert.ok(b.indexOf('guardPrice') < b.indexOf('fetch('), 'tekshiruv yuborishdan OLDIN');
});
t('ombor sahifasi (inventory.html saveNewProduct) narx + tan narx', () => {
  const b = fnBody(read('app/inventory.html'), /async function saveNewProduct\(\)[\s\S]*?\n}\n/, 'saveNewProduct');
  assert.match(b, /guardPrice\(document\.getElementById\('npPrice'\)/);
  assert.match(b, /guardPrice\(document\.getElementById\('npCost'\)/);
  assert.ok(b.indexOf('guardPrice') < b.indexOf("api.post('/products/'"));
});
for (const [page, fn] of [['app/suppliers.html', 'recCreate'], ['app/purchase_receipts.html', 'createReceipt']]) {
  t(`priyomka ${page}: qatorlar narxi + yangi mahsulot`, () => {
    const s = read(page);
    assert.match(s, /<script src="\.\.\/js\/core\/qty-guard\.js"><\/script>/);
    const create = fnBody(s, new RegExp(`window\\.${fn} = async \\(\\) => \\{[\\s\\S]*?\\n};\\n`), fn);
    assert.match(create, /guardPrice\(items\[i\]\.unit_price/);
    assert.ok(create.indexOf('guardPrice') < create.indexOf("api.post('/purchase-receipts/'"));
    assert.match(s, /guardPrice\(document\.getElementById\('npCost'\)\.value, 'Tan narx'\)/);
  });
}
t('admin mahsulot oynasi (core.js saveProduct) 4 narx maydoni', () => {
  const b = fnBody(read('js/admin/core.js'), /async function saveProduct\(\)[\s\S]*?\n}\n/, 'saveProduct');
  for (const k of ['price', 'cost_price', 'wholesale_price', 'pack_price']) assert.match(b, new RegExp(`\\['${k}'`));
});

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
