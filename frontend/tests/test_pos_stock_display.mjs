/**
 * POS'DA QOLDIQ KO'RINISHI + sidebar tartibi.
 *
 * ═══ NEGA BU TEST BOR ═══
 *
 * Kassir mijozga "bor/yo'q, qancha qoldi" deb ayta olishi kerak. Ilgari
 * qoldiq FAQAT savatga qo'shilgandan KEYIN ogohlantirish bo'lib chiqardi
 * (`_warnIfShort`) — ya'ni kassir avval qo'shib, keyin bilardi.
 *
 * ⚠️ GOLDEN 1 — CHEKKA TUSHMASIN. Qoldiq faqat EKRANDA (mahsulot kartasi).
 * Chek `renderReceiptData` / `buildReceipt58` dan quriladi — ular savat yoki
 * server qatorlarini o'qiydi, qoldiq esa alohida `_stockMap` da. 3-blok
 * buni manbadan tasdiqlaydi.
 *
 * ⚠️ GOLDEN 2 — QIDIRUVDA QAYTA SO'ROV KETMASIN. v1.12.8 da admin mahsulot
 * ro'yxatida har harf bosilganda qoldiq QAYTA tortilardi (1001 BARAKA da
 * 524 qator). Shu xato POS'da takrorlanmasin: `_stockMap` POS ochilganda va
 * sotuvdan keyin BIR MARTA to'ldiriladi, `renderProducts` esa faqat
 * xotiradan o'qiydi. 4-blok shuni qulflaydi.
 *
 * ═══ USLUB ═══
 * `_stockBadge` / `_stockNum` pos.js dan AJRATIB olinadi va HAQIQATAN ishga
 * tushiriladi (nusxa ko'chirilmaydi). Qolgan qoidalar manba ustida.
 *
 * Ishga tushirish:  node frontend/tests/test_pos_stock_display.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const ROOT = resolve('frontend');
const rd = p => readFileSync(resolve(ROOT, p), 'utf8').replace(/\r\n/g, '\n');

const POS   = rd('js/modules/pos.js');
const POSH  = rd('app/pos.html');
const ADMIN = rd('app/admin.html');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

function grab(src, re, what) {
  const m = src.match(re);
  if (!m) { console.error(`XATO: "${what}" topilmadi — test eskirgan.`); process.exit(2); }
  return m[0];
}

// ══════════════════════════════════════════════════════════════════════════════
// Sandbox — HAQIQIY `_stockBadge` + `_stockNum`
// ══════════════════════════════════════════════════════════════════════════════
const sandbox = { console };
vm.createContext(sandbox);
vm.runInContext([
  'const _stockMap = new Map();',
  grab(POS, /function _stockNum\(n\) \{[\s\S]*?\n}/,            '_stockNum'),
  grab(POS, /function _stockBadge\(productId\) \{[\s\S]*?\n}/,  '_stockBadge'),
  'globalThis.__set = (id, v) => _stockMap.set(id, v);',
  'globalThis.__clear = () => _stockMap.clear();',
].join('\n'), sandbox);

const { _stockBadge, __set, __clear } = sandbox;
const badge = (id, st) => { __clear(); if (st) __set(id, st); return _stockBadge(id); };

// ══════════════════════════════════════════════════════════════════════════════
// 1) QOLDIQ KO'RINADI — "12 dona", "4.5 kg"
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 1) Qoldiq yorlig\'i ──');

check('1_dona',  badge(1, { quantity: 12, unit: 'dona', min_threshold: 3 }),
      '<div class="prod-stock">12 dona</div>');
check('1_kg',    badge(1, { quantity: 4.5, unit: 'kg', min_threshold: 1 }),
      '<div class="prod-stock">4.5 kg</div>');
check('1_butun_kg_kasrsiz', badge(1, { quantity: 7, unit: 'kg', min_threshold: 1 }),
      '<div class="prod-stock">7 kg</div>');
check('1_uzun_kasr_qisqaradi', badge(1, { quantity: 0.740, unit: 'kg', min_threshold: 0 }),
      '<div class="prod-stock">0.74 kg</div>');
check('1_birliksiz', badge(1, { quantity: 5, unit: null, min_threshold: 1 }),
      '<div class="prod-stock">5</div>');

// ══════════════════════════════════════════════════════════════════════════════
// 2) RANG — min_threshold bo'yicha
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 2) Ogohlantirish rangi ──');

const cls = (st) => (badge(1, st).match(/class="prod-stock( \w+)?"/) || [])[1] || '';
check('2_yetarli_rangsiz',  cls({ quantity: 12, unit: 'dona', min_threshold: 3 }), '');
check('2_chegarada_low',    cls({ quantity: 3,  unit: 'dona', min_threshold: 3 }), ' low');
check('2_chegaradan_past',  cls({ quantity: 1,  unit: 'dona', min_threshold: 3 }), ' low');
check('2_nol_zero',         cls({ quantity: 0,  unit: 'dona', min_threshold: 3 }), ' zero');
check('2_manfiy_zero',      cls({ quantity: -2, unit: 'dona', min_threshold: 3 }), ' zero');
// Chegara 0/yo'q bo'lsa "low" bo'lmaydi (har mahsulot sariq bo'lib ketmasin)
check('2_chegara_nol_rangsiz', cls({ quantity: 5, unit: 'dona', min_threshold: 0 }), '');
check('2_chegara_null_rangsiz', cls({ quantity: 5, unit: 'dona', min_threshold: null }), '');

// Xarita bo'sh / buzuq qiymat → yorliq CHIQMAYDI ("0" ko'rsatish yolg'on)
check('3_xarita_bosh_yorliq_yoq',  badge(1, null), '');
check('3_quantity_null_yorliq_yoq', badge(1, { quantity: null, unit: 'dona' }), '');
check('3_quantity_matn_yorliq_yoq', badge(1, { quantity: 'x', unit: 'dona' }), '');

// CSS klasslari pos.html da bor
check('2_css_prod_stock',      /\.prod-stock\{/.test(POSH), true);
check('2_css_low',             /\.prod-stock\.low\{/.test(POSH), true);
check('2_css_zero',            /\.prod-stock\.zero\{/.test(POSH), true);
check('2_css_list_view',       /list-view \.prod-stock/.test(POSH), true);

// ══════════════════════════════════════════════════════════════════════════════
// 3) ⚠️ GOLDEN — CHEKDA YO'Q
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 3) GOLDEN: chekda yo\'q ──');

// Kartada BOR
const cards = grab(POS, /function renderProducts\(catId = null\)[\s\S]*?\n}/, 'renderProducts');
check('3_kartada_bor', /_stockBadge\(p\.id\)/.test(cards), true);

// POS chekida (`renderReceiptData`) YO'Q
const rcpt = grab(POS, /function renderReceiptData\(rec\)[\s\S]*?\n}/, 'renderReceiptData');
check('3_pos_chekida_stockBadge_yoq', /_stockBadge/.test(rcpt), false);
check('3_pos_chekida_stockMap_yoq',   /_stockMap/.test(rcpt), false);
check('3_pos_chekida_prod_stock_yoq', /prod-stock/.test(rcpt), false);

// Bosiladigan chek moduli (receipt-print.js) qoldiq haqida BILMAYDI
const RCPTJS = rd('js/core/receipt-print.js');
check('3_bosma_chekda_stock_yoq',  /prod-stock|_stockMap|min_threshold/.test(RCPTJS), false);

// Serverga yuborilgan savat snapshot'ida ham qoldiq yo'q
const snap = grab(POS, /cart_snapshot\s*: state\.cart\.map\(i => \(\{[\s\S]*?\}\)\),/, 'cart_snapshot');
check('3_snapshotda_stock_yoq', /stock|min_threshold/i.test(snap), false);

// ══════════════════════════════════════════════════════════════════════════════
// 4) ⚠️ GOLDEN — QIDIRUVDA QAYTA SO'ROV YO'Q
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 4) GOLDEN: qidiruvda so\'rov yo\'q ──');

// `renderProducts` tarmoqqa CHIQMAYDI
check('4_render_api_chaqirmaydi',  /api\.get|fetch\(/.test(cards), false);
check('4_render_refreshStockMap_chaqirmaydi', /refreshStockMap/.test(cards), false);

// Qidiruv ishlov beruvchisi faqat qayta render qiladi
const srch = grab(POS,
  /document\.getElementById\('searchInput'\)\.addEventListener\('input'[\s\S]*?\n}\);/,
  'qidiruv handleri');
check('4_qidiruv_faqat_render', /renderProducts\(\)/.test(srch), true);
check('4_qidiruvda_sorov_yoq',  /refreshStockMap|api\.get|fetch\(/.test(srch), false);

// `refreshStockMap()` chaqiruvlari — FAQAT ikki joy (yuklash + sotuvdan keyin)
const chaqiruvlar = (POS.match(/^\s*refreshStockMap\(\);/gm) || []).length;
check('4_chaqiruv_soni_ikki', chaqiruvlar, 2);

// `_stockBadge` / `_repaintStockBadges` ham tarmoqqa chiqmaydi
const bdg = grab(POS, /function _stockBadge\(productId\) \{[\s\S]*?\n}/, '_stockBadge');
const rep = grab(POS, /function _repaintStockBadges\(\) \{[\s\S]*?\n}/, '_repaintStockBadges');
check('4_badge_sorov_yoq',   /api\.get|fetch\(/.test(bdg), false);
check('4_repaint_sorov_yoq', /api\.get|fetch\(/.test(rep), false);

// Xarita yuklangach JOYIDA yangilanadi (qayta render EMAS — kategoriya
// filtri DOM'da saqlanadi va argumentsiz `renderProducts()` uni yo'qotardi)
const refresh = grab(POS, /async function refreshStockMap\(\) \{[\s\S]*?\n}/, 'refreshStockMap');
check('4_xarita_repaint_chaqiradi',   /_repaintStockBadges\(\)/.test(refresh), true);
check('4_xarita_renderProducts_chaqirmaydi', /renderProducts/.test(refresh), false);
check('4_min_threshold_xaritada', /min_threshold: r\.min_threshold/.test(refresh), true);

// ══════════════════════════════════════════════════════════════════════════════
// 5) SIDEBAR TARTIBI — "Ombor" "Mahsulotlar" dan OLDIN
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 5) Sidebar tartibi ──');

const nav = grab(ADMIN, /<nav[\s\S]*?<\/nav>/, 'admin nav');
const bandlar = [...nav.matchAll(/data-page="([^"]+)"/g)].map(m => m[1]);

const iOmbor = bandlar.indexOf('inventory');
const iMahs  = bandlar.indexOf('products');
check('5_ikkisi_ham_bor', iOmbor >= 0 && iMahs >= 0, true);
check('5_OMBOR_OLDIN', iOmbor < iMahs, true);

// Ombor bolalari PARENT bilan birga va Mahsulotlardan oldin
for (const sub of ['stockIn', 'stockOut', 'invCount', 'invReport']) {
  const i = bandlar.indexOf(sub);
  check(`5_${sub}_ombordan_keyin`, i > iOmbor && i < iMahs, true);
}

// Qolgan tartib TEGILMAGAN: dashboard → orders → salesHistory, va
// products → categories → customers → shifts
const ketma = (a, b) => bandlar.indexOf(a) < bandlar.indexOf(b);
check('5_dashboard_orders_oldin',   ketma('dashboard', 'orders'), true);
check('5_orders_salesHistory_oldin', ketma('orders', 'salesHistory'), true);
check('5_salesHistory_ombor_oldin',  ketma('salesHistory', 'inventory'), true);
check('5_products_categories_oldin', ketma('products', 'categories'), true);
check('5_categories_customers_oldin', ketma('categories', 'customers'), true);
check('5_customers_shifts_oldin',    ketma('customers', 'shifts'), true);
check('5_staff_settings_oldin',      ketma('staff', 'settings'), true);

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
