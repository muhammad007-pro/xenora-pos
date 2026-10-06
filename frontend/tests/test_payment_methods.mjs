/**
 * POS TO'LOV USULLARI — Click/Payme yashirilishi va sozlamaning ta'siri.
 *
 * ═══ NEGA BU TEST BOR ═══
 *
 * Click/Payme tugmalari POS'da HAR DOIM ko'rinardi, lekin shlyuz
 * integratsiyasi YO'Q (`payment_service._process_online_payment` — TODO
 * stub). Kassir bossa to'lov MANGU "kutilmoqda" qolardi.
 * PRODDA: 24 ta pending CLICK, HAMMASI (24/24) BEKOR QILINGAN buyurtmada —
 * ya'ni tugma yo'qotilgan sotuv keltirardi.
 *
 * Sozlamalar sahifasida toggle'lar bor edi va saqlanardi, lekin POS ularni
 * UMUMAN O'QIMASDI.
 *
 * ⚠️ IKKI KIRISH NUQTASI: yagona usul tugmalari VA aralash to'lov (split)
 * qatorlari. Faqat tugmani yashirish yetmaydi — split orqali baribir pending
 * Click yaratish mumkin bo'lardi. 3-blok shuni qulflaydi.
 *
 * ⚠️ GOLDEN: `credit` (nasiya) va `room_charge` bu ro'yxatga KIRMAYDI —
 * ular biznes turi bo'yicha ko'rinadi va mantiq TEGILMAGAN.
 *
 * ═══ USLUB ═══
 * `applyPayMethods` pos.js dan AJRATIB olinadi va SOXTA DOM bilan HAQIQATAN
 * ishga tushiriladi — ya'ni qaysi element yashirilishi rostmana o'lchanadi.
 *
 * Ishga tushirish:  node frontend/tests/test_payment_methods.mjs
 */
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'node:vm';

const ROOT = resolve('frontend');
const rd = p => readFileSync(resolve(ROOT, p), 'utf8').replace(/\r\n/g, '\n');

const POS  = rd('js/modules/pos.js');
const POSH = rd('app/pos.html');
const SETH = rd('app/settings.html');

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
// SOXTA DOM — .pay-method tugmalari + split qatorlari
// ══════════════════════════════════════════════════════════════════════════════
const BARCHA = ['cash', 'card', 'click', 'payme', 'qr', 'credit', 'room_charge'];

function makeDom({ tugmalar = ['cash', 'card', 'click', 'payme'], faol = 'cash' } = {}) {
  const nodes = {};
  const btns = tugmalar.map(m => ({
    dataset: { method: m },
    style: { display: '' },
    _cls: new Set(m === faol ? ['pay-method', 'active'] : ['pay-method']),
    classList: {
      add(c) { this._o._cls.add(c); },
      remove(c) { this._o._cls.delete(c); },
      contains(c) { return this._o._cls.has(c); },
      toggle(c, v) { v ? this._o._cls.add(c) : this._o._cls.delete(c); },
    },
  }));
  btns.forEach(b => { b.classList._o = b; });

  for (const m of BARCHA) {
    nodes[`split_${m}`] = { value: '7000', style: {} };
    nodes[`splitRow_${m}`] = { style: { display: '' } };
  }
  nodes.cashSection = { style: { display: 'none' } };

  const payMethods = {
    style: {},
    querySelectorAll: () => btns,
  };

  return {
    btns, nodes, payMethods,
    document: {
      getElementById: id => nodes[id] || null,
      querySelector: sel => {
        if (sel === '.pay-methods') return payMethods;
        if (sel === '.pay-method.active') return btns.find(b => b.classList.contains('active')) || null;
        const m = sel.match(/\.pay-method\[data-method="([^"]+)"\]/);
        if (m) return btns.find(b => b.dataset.method === m[1]) || null;
        return null;
      },
      querySelectorAll: sel => (sel === '.pay-method' ? btns : []),
    },
  };
}

const SRC = [
  grab(POS, /const _PM_SOZLAMA_USULLAR = \[[^\]]*\];/,      '_PM_SOZLAMA_USULLAR'),
  grab(POS, /let _enabledPayMethods = \[[^\]]*\];/,          '_enabledPayMethods'),
  grab(POS, /function applyPayMethods\(\) \{[\s\S]*?\n}/,    'applyPayMethods'),
].join('\n');

function run(yoqilgan, domOpts) {
  const dom = makeDom(domOpts);
  const sandbox = { console, document: dom.document, Set, Map };
  sandbox.payMethod = 'cash';
  vm.createContext(sandbox);
  vm.runInContext(SRC + '\n_enabledPayMethods = ' + JSON.stringify(yoqilgan) + ';\napplyPayMethods();', sandbox);
  return { dom, sandbox };
}

const ko = (dom, m) => {
  const b = dom.btns.find(x => x.dataset.method === m);
  return b ? b.style.display !== 'none' : null;
};

// ══════════════════════════════════════════════════════════════════════════════
// 1) STANDART — Click/Payme YASHIRIN
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 1) Standart (naqd + karta) ──');

check('1_standart_qiymat', /let _enabledPayMethods = \['cash', 'card'\];/.test(POS), true);
{
  const { dom } = run(['cash', 'card']);
  check('1_naqd_korinadi',  ko(dom, 'cash'), true);
  check('1_karta_korinadi', ko(dom, 'card'), true);
  check('1_CLICK_yashirin', ko(dom, 'click'), false);
  check('1_PAYME_yashirin', ko(dom, 'payme'), false);
  check('1_ustun_soni', dom.payMethods.style.gridTemplateColumns, 'repeat(2,1fr)');
}

// ══════════════════════════════════════════════════════════════════════════════
// 2) SOZLAMA BILAN YOQISH
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 2) Sozlama bilan yoqish ──');
{
  const { dom } = run(['cash', 'card', 'click']);
  check('2_click_yoqildi',  ko(dom, 'click'), true);
  check('2_payme_hali_yoq', ko(dom, 'payme'), false);
  check('2_ustun_uch',      dom.payMethods.style.gridTemplateColumns, 'repeat(3,1fr)');
}
{
  const { dom } = run(['cash']);
  check('2_faqat_naqd_karta_yashirin', ko(dom, 'card'), false);
  check('2_ustun_bir', dom.payMethods.style.gridTemplateColumns, 'repeat(1,1fr)');
}

// ══════════════════════════════════════════════════════════════════════════════
// 3) ⚠️ IKKINCHI KIRISH NUQTASI — aralash to'lov (split)
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 3) Aralash to\'lov qatorlari ──');
{
  const { dom } = run(['cash', 'card']);
  check('3_split_click_yashirin', dom.nodes.splitRow_click.style.display, 'none');
  check('3_split_payme_yashirin', dom.nodes.splitRow_payme.style.display, 'none');
  check('3_split_cash_korinadi',  dom.nodes.splitRow_cash.style.display, '');
  check('3_split_card_korinadi',  dom.nodes.splitRow_card.style.display, '');
  // Yashiringan maydon TOZALANADI — eski qiymat `buildSplitPayments()` ga
  // qo'shilib, pending Click yaratib ketmasin
  check('3_split_click_qiymati_tozalandi', dom.nodes.split_click.value, '');
  check('3_split_payme_qiymati_tozalandi', dom.nodes.split_payme.value, '');
  check('3_split_cash_qiymati_saqlandi',   dom.nodes.split_cash.value, '7000');
}
{
  const { dom } = run(['cash', 'card', 'click']);
  check('3_yoqilganda_split_qatori_qaytadi', dom.nodes.splitRow_click.style.display, '');
  check('3_yoqilganda_qiymat_tegilmaydi',    dom.nodes.split_click.value, '7000');
}

// ══════════════════════════════════════════════════════════════════════════════
// 4) FAOL TUGMA yashirilsa — naqdga qaytadi
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 4) Faol tugma yashirilganda ──');
{
  // Kassir Click'ni tanlab turgan, keyin sozlama o'chirildi
  const { dom, sandbox } = run(['cash', 'card'], { faol: 'click' });
  const cashBtn = dom.btns.find(b => b.dataset.method === 'cash');
  check('4_naqd_faol_boldi', cashBtn.classList.contains('active'), true);
  check('4_payMethod_cash',  sandbox.payMethod, 'cash');
  check('4_cashSection_ochildi', dom.nodes.cashSection.style.display, '');
  const clickBtn = dom.btns.find(b => b.dataset.method === 'click');
  check('4_click_faol_emas', clickBtn.classList.contains('active'), false);
}
{
  // Faol tugma ko'rinadigan bo'lsa TEGILMAYDI
  const { dom, sandbox } = run(['cash', 'card'], { faol: 'card' });
  const cardBtn = dom.btns.find(b => b.dataset.method === 'card');
  check('4_korinadigan_faol_tegilmaydi', cardBtn.classList.contains('active'), true);
  check('4_payMethod_ozgarmadi', sandbox.payMethod, 'cash');   // boshlang'ich
}

// ══════════════════════════════════════════════════════════════════════════════
// 5) ⚠️ GOLDEN — nasiya/xonaga TEGILMAYDI
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 5) GOLDEN: nasiya / xonaga ──');
{
  const { dom } = run(['cash', 'card'],
    { tugmalar: ['cash', 'card', 'click', 'payme', 'credit', 'room_charge'], faol: 'cash' });
  // `applyPayMethods` bu ikkisiga TEGMAYDI (biznes turi boshqaradi)
  check('5_credit_tegilmadi',      ko(dom, 'credit'), true);
  check('5_room_charge_tegilmadi', ko(dom, 'room_charge'), true);
  check('5_split_credit_tegilmadi', dom.nodes.splitRow_credit.style.display, '');
}
check('5_royxatda_credit_yoq',
      /_PM_SOZLAMA_USULLAR = \['cash', 'card', 'click', 'payme', 'qr'\]/.test(POS), true);
// Biznes turi mantig'i joyida
check('5_creditMethod_mode_bilan', /creditMethod[\s\S]{0,400}businessType === 'store'/.test(POS), true);
check('5_roomCharge_mode_bilan',   /MODE\.isHotel[\s\S]{0,2000}roomChargeMethod/.test(POS), true);

// ══════════════════════════════════════════════════════════════════════════════
// 6) SOZLAMA O'QILISHI va chaqiruv tartibi
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 6) Sozlamani o\'qish ──');

const loadFn = grab(POS, /async function loadPayMethods\(\)[\s\S]*?\n}/, 'loadPayMethods');
check('6_pos_endpointini_oqiydi', /\/settings\/payment-methods/.test(loadFn), true);
// ⚠️ admin-only endpoint ISHLATILMAYDI (maxfiy kalitlar + kassirda ruxsat yo'q)
check('6_admin_endpoint_ishlatilmaydi', /settings\/payment['"`]/.test(loadFn), false);
check('6_xato_bolsa_standart_qoladi', /catch \{/.test(loadFn), true);
check('6_cash_majburan_qoshiladi', /unshift\('cash'\)/.test(loadFn), true);

// Chaqiruv TARTIBI: applyBusinessMode() DAN KEYIN (grid ustunlari uchun)
const init = grab(POS, /await loadData\(\);[\s\S]*?renderCategories\(state\.categories\);/, 'init');
check('6_applyBusinessMode_oldin',
      init.indexOf('applyBusinessMode()') < init.indexOf('applyPayMethods()'), true);
check('6_darhol_bir_marta', /applyPayMethods\(\);/.test(init), true);
check('6_keyin_server_bilan', /loadPayMethods\(\);/.test(init), true);
// `await` QILINMAYDI — POS ochilishi kechikmasin
check('6_await_qilinmaydi', /await loadPayMethods/.test(init), false);

// ══════════════════════════════════════════════════════════════════════════════
// 7) ⛔ transfer — SOZLAMALAR UI'sidan OLIB TASHLANDI
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 7) transfer nuqsoni ──');

check('7_toggle_olib_tashlandi', /paymentTransfer/.test(SETH), false);
check('7_saqlashda_yoq', /\['cash','card','payme','click'\]/.test(SETH), true);
check('7_pos_royxatida_yoq', /transfer/.test(grab(POS, /const _PM_SOZLAMA_USULLAR = \[[^\]]*\];/, 'ro\'yxat')), false);

// ══════════════════════════════════════════════════════════════════════════════
// 8) YORLIQLAR — Terminal karta tugmasida
// ══════════════════════════════════════════════════════════════════════════════
console.log('\n── 8) Yorliqlar ──');

check('8_pos_karta_terminal', /<span>Karta \/ Terminal<\/span>/.test(POSH), true);
check('8_sozlamada_karta_terminal', /Karta \/ Terminal/.test(SETH), true);
check('8_shlyuz_eslatmasi', /Shlyuz ULANMAGAN/.test(SETH), true);
check('8_naqd_ochirilmaydi', /id="paymentCash" checked disabled/.test(SETH), true);
// Alohida `terminal` tugmasi/qiymati QO'SHILMAGAN (enum tegilmadi)
check('8_terminal_data_method_yoq', /data-method="terminal"/.test(POSH), false);

console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
