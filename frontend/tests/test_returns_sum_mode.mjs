/**
 * QAYTARISHDA "SUMMA" REJIMI — pul bo'yicha qaytarish (kg mahsulotlar).
 *
 * ═══ NEGA BU TEST BOR ═══
 *
 * Kg mahsulotda mijoz "9500 so'mlik qaytaraman" deydi, tarozidagi miqdorni
 * emas. Kassir 9500 / narx ni QO'LDA hisoblab yozardi — kalkulyator xatosi
 * to'g'ridan-to'g'ri pulga tegadi.
 *
 * ⚠️ ENG MUHIM QOIDA: bo'luvchi — SOTUVDAGI narx (`ipr{idx}`, lookup'dan
 * keladi, `readonly`), mahsulotning JORIY narxi EMAS. Narx sotuvdan keyin
 * o'zgargan bo'lsa joriy narxga bo'lish boshqa miqdor berardi va mijozga
 * NOTO'G'RI PUL qaytarilardi. 2-blok aynan shuni o'lchaydi.
 *
 * ⚠️ GOLDEN:
 *   · MIQDOR rejimi avvalgidek (summa maydoni hech qayerga yuborilmaydi)
 *   · savat YAGONA MANBADAN o'qiydi — `iq{idx}` (miqdor)
 *   · QO'LDA KIRITISHDA summa rejimi YO'Q (narx ma'lum emas)
 *   · DONA mahsulotda rejim tugmasi ko'rinmaydi
 *
 * ═══ USLUB ═══
 * Funksiyalar `returns.html` dan AJRATIB olinadi (nusxa ko'chirilmaydi) va
 * SOXTA DOM bilan HAQIQATAN ishga tushiriladi — ya'ni test `sumModeInput`
 * qaysi maydonni o'qib, qaysiga yozishini ROSTMANA tekshiradi, izohini emas.
 *
 * Ishga tushirish:  node frontend/tests/test_returns_sum_mode.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const ROOT = resolve('frontend');
const rd = p => readFileSync(resolve(ROOT, p), 'utf8').replace(/\r\n/g, '\n');

const HTML = rd('app/returns.html');
const RCPT = rd('js/core/receipt-print.js');

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
// SOXTA DOM — faqat kerakli qismi
// ══════════════════════════════════════════════════════════════════════════════
function makeDom(els) {
  const nodes = {};
  for (const [id, cfg] of Object.entries(els)) {
    nodes[id] = {
      id,
      value: cfg.value !== undefined ? cfg.value : '',
      hidden: !!cfg.hidden,
      textContent: '',
      dataset: cfg.dataset || {},
      style: {},
      _btns: cfg.btns || null,
      focus() { this._focused = true; },
      querySelectorAll() { return this._btns || []; },
      querySelector() { return (this._btns || [])[0] || null; },
    };
  }
  return {
    nodes,
    document: { getElementById: id => nodes[id] || null },
  };
}

// Ajratib olingan HAQIQIY kod
const src = [
  grab(RCPT, /const _PACK_WEIGHT_UNITS = \[[^\]]*\];/,            '_PACK_WEIGHT_UNITS'),
  grab(RCPT, /const _PACK_VOL_UNITS\s*= \[[^\]]*\];/,             '_PACK_VOL_UNITS'),
  grab(RCPT, /export function packKind\(saleUnit\)[\s\S]*?\n}\n/, 'packKind'),
  grab(HTML, /function _fmtQ\(x\) \{[\s\S]*?\n}/,                 '_fmtQ'),
  grab(HTML, /function qtyFromSum\(sum, unitPrice, maxQty\) \{[\s\S]*?\n}/, 'qtyFromSum'),
  grab(HTML, /function _sumModeAvailable\(saleUnit\) \{[\s\S]*?\n}/, '_sumModeAvailable'),
  grab(HTML, /function _rowUnitWord\(it\) \{[\s\S]*?\n}/,         '_rowUnitWord'),
  grab(HTML, /window\.setRowMode = function\(idx, mode\) \{[\s\S]*?\n};/, 'setRowMode'),
  grab(HTML, /window\.sumModeInput = function\(idx\) \{[\s\S]*?\n};/, 'sumModeInput'),
].join('\n').replace(/^export /gm, '');

/** Sandbox quradi: berilgan DOM bilan haqiqiy funksiyalarni yuklaydi. */
function load(els) {
  const dom = makeDom(els);
  const sandbox = { console };
  sandbox.window = sandbox;
  sandbox.document = dom.document;
  sandbox.calcTotal = () => { sandbox._calcCalls = (sandbox._calcCalls || 0) + 1; };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return { sandbox, nodes: dom.nodes };
}

const bare = load({}).sandbox;   // toza funksiyalar uchun

// ══════════════════════════════════════════════════════════════════════════════
// 1) HISOB — summa ÷ narx = miqdor, 3 xona
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 1) Hisob ──');

const q = (s, p, m) => bare.qtyFromSum(s, p, m);

// Vazifadagi aniq misol
check('1_9500_8000',        q(9500, 8000).qty, 1.188);     // 1.1875 → 1.188
check('1_9500_8000_clamp',  q(9500, 8000).clamped, false);
check('1_butun_bolinma',    q(20000, 10000).qty, 2);
check('1_uch_xona',         q(10000, 7000).qty, 1.429);    // 1.42857 → 1.429
check('1_kichik_summa',     q(500, 8000).qty, 0.063);      // 0.0625 → 0.063

// Buzuq kiritishlar — chek/savat yiqilmaydi
check('2_bosh_summa',   q('', 8000).qty, 0);
check('2_nol_summa',    q(0, 8000).qty, 0);
check('2_manfiy_summa', q(-100, 8000).qty, 0);
check('2_narx_nol',     q(9500, 0).qty, 0);
check('2_narx_bosh',    q(9500, '').qty, 0);
check('2_matn',         q('abc', 8000).qty, 0);
check('2_narx_matn',    q(9500, 'abc').qty, 0);

// ══════════════════════════════════════════════════════════════════════════════
// 2) ⚠️ SOTUVDAGI NARX ishlatiladi — joriy narx boshqa bo'lsa ham
//    Haqiqiy `sumModeInput` ishga tushadi: u `ipr{idx}` ni O'QIYDI.
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 2) Sotuvdagi narx (joriy narx EMAS) ──');

{
  // Sotuvda 1 kg = 8000. Mahsulotning BUGUNGI narxi 12000 (oshgan).
  const { sandbox, nodes } = load({
    isum0: { value: '9500' },
    iq0:   { value: '' },
    ipr0:  { value: '8000' },                      // SOTUVDAGI narx (readonly)
    ioi0:  { dataset: { max: '5', unit: 'kg' } },
    ihint0: {},
  });
  sandbox.sumModeInput(0);
  check('2_miqdor_sotuv_narxidan', nodes.iq0.value, '1.188');
  check('2_hint_matni', nodes.ihint0.textContent, '≈ 1.188 kg');
  // Joriy narx (12000) bilan bo'lingan bo'lsa 0.792 chiqardi — ya'ni mijozga
  // 0.396 kg kam qaytarilardi.
  check('2_joriy_narx_ISHLATILMADI', nodes.iq0.value !== '0.792', true);
  check('2_joriy_narx_qiymati_boshqa', q(9500, 12000).qty, 0.792);
  check('2_calcTotal_chaqirildi', sandbox._calcCalls, 1);
}

{
  // Narx TUSHGAN holat: sotuvda 8000, bugun 5000
  const { sandbox, nodes } = load({
    isum0: { value: '9500' }, iq0: { value: '' }, ipr0: { value: '8000' },
    ioi0: { dataset: { max: '10', unit: 'kg' } }, ihint0: {},
  });
  sandbox.sumModeInput(0);
  check('2_narx_tushganda_ham_sotuvdagi', nodes.iq0.value, '1.188');
  check('2_joriy_5000_bolsa_boshqa', q(9500, 5000).qty, 1.9);
}

// ══════════════════════════════════════════════════════════════════════════════
// 3) QOP (pachka) bilan sotilgan — bo'luvchi QOP narxi
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 3) Qop narxi ──');

{
  // 20 kg qop = 450 000. Mijoz 900 000 so'mlik qaytaradi → 2 QOP.
  const { sandbox, nodes } = load({
    isum0: { value: '900000' }, iq0: { value: '' }, ipr0: { value: '450000' },
    ioi0: { dataset: { max: '3', unit: 'qop' } }, ihint0: {},
  });
  sandbox.sumModeInput(0);
  check('3_qop_soni', nodes.iq0.value, '2');
  check('3_qop_hint', nodes.ihint0.textContent, '≈ 2 qop');
}

// Birlik so'zi: qop bilan sotilgan qatorda "qop", aks holda birlik
check('3_unit_word_pachka', bare._rowUnitWord({ sale_unit: 'kg', unit_sold: 'pachka' }), 'qop');
check('3_unit_word_kg',     bare._rowUnitWord({ sale_unit: 'kg', unit_sold: null }), 'kg');
check('3_unit_word_ml',     bare._rowUnitWord({ sale_unit: 'ml', unit_sold: null }), 'ml');
check('3_unit_word_dona',   bare._rowUnitWord({ sale_unit: 'pcs', unit_sold: null }), 'dona');
check('3_unit_word_ml_butun', bare._rowUnitWord({ sale_unit: 'ml', unit_sold: 'pachka' }), 'butun');

// ══════════════════════════════════════════════════════════════════════════════
// 4) CHEGARA — hisoblangan miqdor qaytarish mumkin bo'lganidan oshmaydi
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 4) Chegara ──');

check('4_oshsa_tushiriladi',  q(100000, 8000, 1.5).qty, 1.5);
check('4_clamped_bayrogi',    q(100000, 8000, 1.5).clamped, true);
check('4_oshmasa_tegilmaydi', q(9500, 8000, 5).qty, 1.188);
check('4_oshmasa_clamped_yoq', q(9500, 8000, 5).clamped, false);
check('4_aniq_chegarada',     q(12000, 8000, 1.5).qty, 1.5);
check('4_chegarada_clamped_yoq', q(12000, 8000, 1.5).clamped, false);
check('4_max_yoq_tegilmaydi', q(100000, 8000).qty, 12.5);

{
  // Haqiqiy oqimda ham: max 1.5, summa 100 000
  const { sandbox, nodes } = load({
    isum0: { value: '100000' }, iq0: { value: '' }, ipr0: { value: '8000' },
    ioi0: { dataset: { max: '1.5', unit: 'kg' } }, ihint0: {},
  });
  sandbox.sumModeInput(0);
  check('4_oqimda_chegara', nodes.iq0.value, '1.5');
  check('4_oqimda_ogohlantirish', /ko'pi bilan/.test(nodes.ihint0.textContent), true);
}

// ══════════════════════════════════════════════════════════════════════════════
// 5) REJIM KO'RINISHI — dona mahsulotda YO'Q
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 5) Rejim ko\'rinishi ──');

check('5_kg_bor',    bare._sumModeAvailable('kg'), true);
check('5_g_bor',     bare._sumModeAvailable('g'), true);
check('5_litr_bor',  bare._sumModeAvailable('litr'), true);
check('5_l_bor',     bare._sumModeAvailable('l'), true);
check('5_ml_bor',    bare._sumModeAvailable('ml'), true);
// ⚠️ DONA — rejim YO'Q (yarim dona qaytarish ma'nosiz)
check('5_DONA_YOQ',  bare._sumModeAvailable('pcs'), false);
check('5_dona_YOQ',  bare._sumModeAvailable('dona'), false);
check('5_m_YOQ',     bare._sumModeAvailable('m'), false);
check('5_quti_YOQ',  bare._sumModeAvailable('quti'), false);
check('5_bosh_YOQ',  bare._sumModeAvailable(null), false);
check('5_bosh_satr_YOQ', bare._sumModeAvailable(''), false);

// Markup: tugma FAQAT `sumOk` bo'lganda chiqadi
check('5_markup_shartli', /const sumOk = _sumModeAvailable\(it\.sale_unit\);/.test(HTML), true);
check('5_markup_modeUI_shartli', /const modeUI = sumOk \? `/.test(HTML), true);

// ══════════════════════════════════════════════════════════════════════════════
// 6) ⚠️ GOLDEN — QO'LDA KIRITISHDA summa rejimi YO'Q
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 6) GOLDEN: qo\'lda kiritish ──');

const addRow = grab(HTML, /window\.addItemRow = function\(\)[\s\S]*?\n};/, 'addItemRow');
check('6_qolda_isum_yoq',  /isum\$\{idx\}/.test(addRow), false);
check('6_qolda_imode_yoq', /imode\$\{idx\}/.test(addRow), false);
check('6_qolda_setRowMode_yoq', /setRowMode/.test(addRow), false);
// Chek qatorida esa BOR
const ordRows = grab(HTML, /function _renderOrderRows\(o\)[\s\S]*?\n}/, '_renderOrderRows');
check('6_chekda_isum_bor',  /isum\$\{idx\}/.test(ordRows), true);
check('6_chekda_imode_bor', /imode\$\{idx\}/.test(ordRows), true);

// ══════════════════════════════════════════════════════════════════════════════
// 7) ⚠️ GOLDEN — SAVAT YAGONA MANBADAN (miqdor) o'qiydi
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 7) GOLDEN: yagona manba ──');

const submit = grab(HTML, /window\.submitReturn = async function\(\)[\s\S]*?\n  const payload = \{/, 'submitReturn');
check('7_payload_iq_dan',    /getElementById\(`iq\$\{id\}`\)/.test(submit), true);
check('7_payload_isum_YOQ',  /isum/.test(submit), false);
const calc = grab(HTML, /window\.calcTotal = function\(\)[\s\S]*?\n};/, 'calcTotal');
check('7_calcTotal_iq_dan',  /iq\$\{id\}/.test(calc), true);
check('7_calcTotal_isum_YOQ', /isum/.test(calc), false);

// Rejim almashganda ikkala maydon tozalanadi (yarim qiymat o'tib ketmasin)
{
  const btns = [{ dataset: { m: 'qty' }, classList: { toggle() {} } },
                { dataset: { m: 'sum' }, classList: { toggle() {} } }];
  const { sandbox, nodes } = load({
    imode0: { btns }, iq0: { value: '7' }, isum0: { value: '9500' },
    ihint0: {},
  });
  nodes.ihint0.textContent = '≈ 1.188 kg';
  sandbox.setRowMode(0, 'sum');
  check('7_rejim_almashdi_iq_tozalandi',   nodes.iq0.value, '');
  check('7_rejim_almashdi_isum_tozalandi', nodes.isum0.value, '');
  check('7_rejim_almashdi_hint_tozalandi', nodes.ihint0.textContent, '');
  check('7_iq_yashirildi',   nodes.iq0.hidden, true);
  check('7_isum_korinadi',   nodes.isum0.hidden, false);
  sandbox.setRowMode(0, 'qty');
  check('7_qaytganda_iq_korinadi', nodes.iq0.hidden, false);
  check('7_qaytganda_isum_yashirin', nodes.isum0.hidden, true);
}

// ══════════════════════════════════════════════════════════════════════════════
// 8) RO'YXAT LIMITI — 50 → 100 → 200, yangi qidiruvda tiklanadi
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 8) Ro\'yxat limiti ──');

check('8_boshlangich_50', /_OP_LIMIT_BOSHLANGICH = 50;/.test(HTML), true);
check('8_chegara_200',    /_OP_LIMIT_MAX = 200;/.test(HTML), true);
check('8_limit_yuboriladi', /p\.set\('limit', String\(_opLimit\)\)/.test(HTML), true);
check('8_ikkilantiradi',  /_opLimit = Math\.min\(_opLimit \* 2, _OP_LIMIT_MAX\)/.test(HTML), true);
// Yangi qidiruv/sana/reset/ochilish — HAR BIRI limitni tiklaydi. Aks holda
// bitta "ko'proq" bosilgandan keyin hamma keyingi qidiruv 200 qator tortardi.
for (const [nom, re] of [
  ['openOrderPicker', /window[.]openOrderPicker = function[(][)][\s\S]*?\n};/],
  ['opSearchInput',   /window[.]opSearchInput = function[(][)][\s\S]*?\n};/],
  ['opDateChange',    /window[.]opDateChange = function[(][)][\s\S]*?\n};/],
  ['opReset',         /window[.]opReset = function[(][)][\s\S]*?\n};/],
]) {
  check(`8_tiklanadi_${nom}`,
        /_opLimit = _OP_LIMIT_BOSHLANGICH/.test(grab(HTML, re, nom)), true);
}
// opLoadMore esa tiklaMAYDI (u ataylab oshiradi)
check('8_opLoadMore_tiklamaydi',
      /_OP_LIMIT_BOSHLANGICH/.test(
        grab(HTML, /window[.]opLoadMore = function[(][)][\s\S]*?\n};/, 'opLoadMore')), false);
check('8_tugma_bor', /onclick="opLoadMore\(\)"/.test(HTML), true);

// ══════════════════════════════════════════════════════════════════════════════
// 9) INLINE HODISA → `window` (returns.html INLINE modul)
//
// `returns.html` skripti `<script type="module">` — undagi `function foo(){}`
// GLOBAL EMAS, inline `onclick` esa nomni `window` dan qidiradi. Xato FAQAT
// TUGMA BOSILGANDA chiqadi (Fazza'da `quickSellAdd` shunday o'tib ketgan).
//
// ⚠️ `test_module_inline_onclick.js` bu sahifani KO'RMAYDI — u faqat
// `<script type="module" src="...">` (tashqi fayl) larni skanerlaydi.
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 9) Inline hodisa → window ──');

// Brauzer global'lari va kalit so'zlar — eksport talab qilinmaydi
// (`test_module_inline_onclick.js` dagi KNOWN_GLOBALS bilan bir xil g'oya).
const BROWSER_GLOBALS = new Set([
  'event', 'confirm', 'alert', 'history', 'location', 'console',
  'if', 'return', 'String', 'Number', 'parseInt', 'parseFloat', 'Boolean',
]);
const nomlar = new Set();
for (const m of HTML.matchAll(/on(?:click|change|input|keydown)="([^"]*)"/g)) {
  // `(?<![.\w$])` — METOD chaqiruvi emas: `event.preventDefault()`,
  // `s.replace()` kabi nomlar `window` dan izlanmaydi.
  for (const f of m[1].matchAll(/(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(/g)) {
    if (!BROWSER_GLOBALS.has(f[1])) nomlar.add(f[1]);
  }
}
check('9_chaqiruvlar_topildi', nomlar.size > 10, true);
const eksportsiz = [...nomlar].filter(n => !new RegExp('window\\.' + n + '\\s*=').test(HTML)).sort();
check('9_hammasi_window_da', eksportsiz, []);
// Yangi qo'shilganlar alohida
for (const n of ['setRowMode', 'sumModeInput', 'opLoadMore', 'opDateChange']) {
  check(`9_${n}_window_da`, new RegExp('window\\.' + n + '\\s*=').test(HTML), true);
}

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
