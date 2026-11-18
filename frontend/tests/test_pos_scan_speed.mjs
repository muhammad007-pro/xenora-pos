/**
 * POS SKANER TEZLIGI — har skanerda nechta tarmoq so'rovi (2026-11-18).
 *
 * ═══ NEGA BU TEST BOR ═══
 *
 * FAZZA (26) "skanerlasa mahsulot kech chiqadi" deb shikoyat qildi. O'lchov:
 * server 5–10 ms, tarmoq (do'kon → Amsterdam) ~200 ms, ba'zan 1 s. Sabab —
 * har skanerda KUTILADIGAN so'rovlar:
 *   • `addToCart` → `GET /modifiers/groups?product_id=X` (HAR mahsulotda,
 *     atirda modifikator umuman yo'q bo'lsa ham);
 *   • xotirada yo'q kod → `/barcodes/lookup` + `/products/?search` KETMA-KET
 *     (ikkinchisi qisman moslik bilan tasodifiy mahsulot qaytarardi);
 *   • qadoqdagi QR (t.me, sayt) ham serverga borardi.
 *
 * Endi: modifikatorlar POS ochilganda BIR marta keshlanadi; xotirada topilsa
 * 0 so'rov; topilmasa 1 so'rov; URL 0 so'rov.
 *
 * ═══ USLUB ═══
 * `addToCart`, `handleBarcodeScan` va kesh funksiyalari pos.js dan AJRATIB
 * olinadi va HAQIQATAN ishga tushiriladi; atrofdagi (modal, savat) stub.
 *
 * Ishga tushirish:  node frontend/tests/test_pos_scan_speed.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const ROOT = resolve('frontend');
const POS = readFileSync(resolve(ROOT, 'js/modules/pos.js'), 'utf8').replace(/\r\n/g, '\n');

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

function grab(re, what) {
  const m = POS.match(re);
  if (!m) { console.error(`XATO: "${what}" topilmadi — test eskirgan.`); process.exit(2); }
  return m[0];
}

const SRC = {
  addToCart:   grab(/async function addToCart\(productId[\s\S]*?\n}/, 'addToCart'),
  unwrap:      grab(/function _unwrapGroups\(res\) \{[\s\S]*?\n}/, '_unwrapGroups'),
  load:        grab(/async function loadModifierGroups\(\) \{[\s\S]*?\n}/, 'loadModifierGroups'),
  groupsFor:   grab(/function _modGroupsFor\(productId\) \{[\s\S]*?\n}/, '_modGroupsFor'),
  urlRe:       grab(/const _URL_LIKE = .*;/, '_URL_LIKE'),
  isUrl:       grab(/function _isUrlLikeCode\(code\) \{.*\}/, '_isUrlLikeCode'),
  scan:        grab(/async function handleBarcodeScan\(code\) \{[\s\S]*?\n}/, 'handleBarcodeScan'),
  loadData:    grab(/async function loadData\(\) \{[\s\S]*?\n}/, 'loadData'),
  stockMap:    grab(/async function refreshStockMap\(\) \{[\s\S]*?\n}/, 'refreshStockMap'),
};

// ══════════════════════════════════════════════════════════════════════════════
// Sandbox
// ══════════════════════════════════════════════════════════════════════════════
function makeSandbox() {
  const el = () => ({ textContent: '', className: '', style: {} });
  const els = {};
  const sb = {
    console,
    calls: [],            // har api.get yo'li
    routes: {},           // path-prefix -> javob
    added: [],            // doAddToCart(p.id)
    modal: [],            // showModifierModal(p.id, groups.length)
    toasts: [],
    state: { products: [] },
    MODE: {},
    document: {
      getElementById: id => (els[id] ||= el()),
      querySelector: () => null,
    },
    setTimeout: () => 0, clearTimeout: () => {},
  };
  sb.api = {
    get: async (path) => {
      sb.calls.push(path);
      const key = Object.keys(sb.routes).find(k => path.startsWith(k));
      return key ? sb.routes[key] : { success: false, status: 404, data: null };
    },
  };
  vm.createContext(sb);
  vm.runInContext([
    'let _bcTimer = null; let _modUnitMode = null; let _membershipDates = null;',
    'function isPackProduct(p) { return !!(p.pack_size && p.pack_size >= 2); }',
    'function isFractionalUnit(u) { return u === "kg"; }',
    'function showPackChoiceModal() {} function showWeightModal() {}',
    'function showAnalogsPanel() {} function showMembershipModal() {}',
    'function openModal() {} function beep() {}',
    'function toast(m) { globalThis.toasts.push(m); }',
    'function doAddToCart(p) { globalThis.added.push(p.id); }',
    'function showModifierModal(p, g) { globalThis.modal.push([p.id, g.length]); }',
    'let _modGroupsCache = null;',
    SRC.unwrap, SRC.load, SRC.groupsFor, SRC.urlRe, SRC.isUrl,
    SRC.addToCart, SRC.scan,
    'globalThis.addToCart = addToCart;',
    'globalThis.handleBarcodeScan = handleBarcodeScan;',
    'globalThis.loadModifierGroups = loadModifierGroups;',
    'globalThis.isUrl = _isUrlLikeCode;',
    'globalThis.cacheIsNull = () => _modGroupsCache === null;',
  ].join('\n'), sb);
  return sb;
}

const ATIR  = { id: 1, name: 'ATIR', price: 50000, barcode: '4780019310302', sale_unit: 'pcs' };
const LAVASH = { id: 2, name: 'LAVASH', price: 30000, barcode: '111', sale_unit: 'pcs' };
const GROUPS_OK = { success: true, data: [
  { id: 10, product_id: 2, name: 'O\'lcham', display_order: 0, modifiers: [] },
] };

async function ready(routes = {}) {
  const sb = makeSandbox();
  sb.state.products = [ { ...ATIR }, { ...LAVASH } ];
  sb.routes = { '/modifiers/groups': GROUPS_OK, ...routes };
  await sb.loadModifierGroups();
  sb.calls.length = 0;          // POS ochilishi hisoblanmaydi — faqat skaner
  return sb;
}

// ══════════════════════════════════════════════════════════════════════════════
// 1) Modifikatorsiz mahsulot — TARMOQSIZ qo'shiladi
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 1) Modifikatorsiz mahsulot ──');
{
  const sb = await ready();
  await sb.addToCart(1);
  check('1_qoshildi', sb.added, [1]);
  check('1_tarmoq_sorovi_0', sb.calls, []);
  check('1_modal_yoq', sb.modal, []);
}
{
  // Skaner yo'li: xotirada topiladi → jami 0 so'rov
  const sb = await ready();
  await sb.handleBarcodeScan('4780019310302');
  await new Promise(r => setImmediate(r));
  check('1_skaner_xotiradan_0_sorov', sb.calls, []);
  check('1_skaner_qoshdi', sb.added, [1]);
}

// ══════════════════════════════════════════════════════════════════════════════
// 2) Modifikatorli mahsulot — oldingidek modal
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 2) Modifikatorli mahsulot ──');
{
  const sb = await ready();
  await sb.addToCart(2);
  check('2_modal_ochildi', sb.modal, [[2, 1]]);
  check('2_savatga_togridan_tushmadi', sb.added, []);
  check('2_tarmoq_sorovi_0', sb.calls, []);
}
{
  // Umumiy guruh (product_id NULL) — server filtri kabi HAMMA mahsulotga
  const sb = await ready({ '/modifiers/groups': { success: true, data: [
    { id: 11, product_id: null, name: 'Paket', display_order: 0, modifiers: [] },
  ] } });
  await sb.addToCart(1);
  check('2_umumiy_guruh_hammaga', sb.modal, [[1, 1]]);
}
{
  // Kesh yuklanmagan (xato/offline) → ESKI yo'l: mahsulot bo'yicha so'rov.
  // Bo'sh deb keshlansa modifikatorli taom jimgina modalsiz sotilardi.
  const sb = makeSandbox();
  sb.state.products = [ { ...ATIR }, { ...LAVASH } ];
  sb.routes = { '/modifiers/groups': { success: false, status: 500, data: null } };
  await sb.loadModifierGroups();
  check('2_xato_keshlanmaydi', sb.cacheIsNull(), true);
  sb.calls.length = 0;
  sb.routes = { '/modifiers/groups?product_id=2': GROUPS_OK };
  await sb.addToCart(2);
  check('2_fallback_sorov', sb.calls, ['/modifiers/groups?product_id=2']);
  check('2_fallback_modal', sb.modal, [[2, 1]]);
}

// ══════════════════════════════════════════════════════════════════════════════
// 3) URL/QR — serverga KETMAYDI
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 3) URL/QR kod ──');
// Prod loglaridan olingan haqiqiy "kodlar"
for (const code of ['://t.me/fazzaperfum', '://www.perla.uz/intro', 'http://www.elma.uz',
                    'https://me-qr.com/xkQnqKc5', 'www.bavi.uz', 't.me/fazzaperfum']) {
  const sb = await ready();
  await sb.handleBarcodeScan(code);
  check(`3_serverga_ketmadi ${code}`, sb.calls, []);
  check(`3_topilmadi ${code}`, sb.toasts.length === 1 && /topilmadi/.test(sb.toasts[0]), true);
}
// Haqiqiy kodlar URL deb ADASHMAYDI
for (const code of ['4780019310302', 'M300006', 'COLA4870240018990', '46260888', 'WJFEBWUB']) {
  check(`3_url_emas ${code}`, makeSandbox().isUrl(code), false);
}

// ══════════════════════════════════════════════════════════════════════════════
// 4) Xotirada yo'q kod — BITTA so'rov
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 4) Topilmagan kod ──');
{
  const sb = await ready();          // lookup → 404 (route yo'q)
  await sb.handleBarcodeScan('4780076533225');
  check('4_bitta_sorov', sb.calls, ['/barcodes/lookup/4780076533225']);
  check('4_products_search_yoq', sb.calls.some(c => c.startsWith('/products/')), false);
  check('4_qoshilmadi', sb.added, []);
}
{
  // Lookup topdi → xotiraga qo'shiladi, keyingi skan 0 so'rov
  const NEW = { id: 7, name: 'YANGI', price: 9000, barcode: '6903072335916',
                unit: 'pcs', sale_unit: 'pcs' };
  const sb = await ready({ '/barcodes/lookup/': { success: true, data: NEW } });
  await sb.handleBarcodeScan('6903072335916');
  await new Promise(r => setImmediate(r));
  check('4_lookup_topdi_bitta_sorov', sb.calls, ['/barcodes/lookup/6903072335916']);
  check('4_lookup_topdi_qoshildi', sb.added, [7]);
  sb.calls.length = 0;
  await sb.handleBarcodeScan('6903072335916');
  await new Promise(r => setImmediate(r));
  check('4_ikkinchi_skan_0_sorov', sb.calls, []);
}

// ══════════════════════════════════════════════════════════════════════════════
// 5) Manba qoidalari
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 5) Manba ──');
check('5_loadData_keshni_yuklaydi', /^\s*loadModifierGroups\(\);/m.test(SRC.loadData), true);
check('5_skanerda_products_search_yoq', /api\.get\(\s*[`'"]\/products\//.test(SRC.scan), false);
check('5_addToCart_fallback_faqat_kesh_yoqda', /if \(groups === null\)/.test(SRC.addToCart), true);
const lim = (SRC.stockMap.match(/pos-stock\?limit=(\d+)/) || [])[1];
check('5_pos_stock_butun_katalog', Number(lim) >= 10000, true);

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
