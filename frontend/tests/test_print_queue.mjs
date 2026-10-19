/**
 * CHEK NAVBATI TO'XTATILDI (fix/print-queue).
 *
 * MUAMMO (jonli, BARAKA 2026-10-14: "2 kunlik chek navbati"): USB yo'li SumatraPDF
 * ishni Windows spooler'iga topshirgan zahoti `ok:true` qaytarardi. Printer o'chiq/
 * qog'ozsiz bo'lsa Windows ishni CHEKSIZ saqlab, printer qaytganda hammasini bosardi.
 * (Dev mashinada ham XP-58 navbatida 30.07 dan beri xenora_chek_*.pdf turgan edi.)
 *
 * Qotiriladi (electron/spool-guard.js — PowerShell MOCK, real navbatga tegilmaydi):
 *   1) offline / qog'ozsiz → rad, navbatga QO'YILMAYDI, aniq xabar
 *   2) bizning yangi chek hali navbatda → yangisi qo'yilmaydi
 *   3) TTL: 5 daqiqadan eski XENORA cheki o'chiriladi, BEGONA ish (Word) tegilmaydi
 *   4) keyin: chek chiqsa ok; WAIT_MS da chiqmasa → BEKOR qilinadi + xato
 *   5) Windows holati o'qilmasa → avvalgidek (fail-open, chop etish to'silmaydi)
 *   6) printer nomi buyruqqa emas, ATROF-MUHITga (injection yo'q)
 *   7) LAN (haqiqiy TCP): ulanmasa 3 urinish va to'xtaydi; yozilgandan keyin
 *      qayta yuborilmaydi (dublikat chek yo'q)
 *   8) main.js ulanishi + sotuv to'xtamaydi (POS: chop etish sotuvdan KEYIN)
 *
 * Ishga tushirish:  node frontend/tests/test_print_queue.mjs
 */
import { createRequire } from 'module';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import net from 'net';

const require = createRequire(import.meta.url);
const { createSpoolGuard, TTL_MS, NOT_RESPONDING } = require(resolve('electron/spool-guard.js'));
const { sendRawTcpWithRetry, sendRawTcp } = require(resolve('electron/lan-socket.js'));

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};
const quiet = { warn() {} };
const NOW = 1_800_000_000_000;

// Soxta Windows: printer holati + navbat; CANCEL skripti ishlarni olib tashlaydi
function fakeWin({ offline = false, errorState = 0, jobs = [], fail = false, printsAfter = Infinity } = {}) {
  const st = { jobs: [...jobs], calls: [], cancelled: [], polls: 0 };
  st.runPs = async (script, env) => {
    st.calls.push({ script, env });
    if (fail) throw new Error('powershell yo\'q');
    if (/Remove-CimInstance/.test(script) && env.XN_JOBS !== undefined) {
      const ids = env.XN_JOBS.split(',').map(Number);
      st.cancelled.push(...ids);
      st.jobs = st.jobs.filter(j => !ids.includes(j.id));
      return 'ok';
    }
    st.polls++;
    if (st.polls > printsAfter) st.jobs = st.jobs.filter(j => !/xenora_chek_NEW/.test(j.doc));
    return JSON.stringify({ exists: true, name: env.XN_PRINTER || 'XP-58', workOffline: offline,
                            printerStatus: 3, errorState, jobs: st.jobs });
  };
  return st;
}
const guard = (st, extra = {}) => createSpoolGuard({ runPs: st.runPs, now: () => NOW, sleep: async () => {},
                                                     waitMs: 0, log: quiet, ...extra });

console.log('\n── 1) offline / xato ──');
{
  const st = fakeWin({ offline: true });
  const r = await guard(st).before('Xprinter XP-58');
  check('1_offline_rad', [r.ok, r.error], [false, `${NOT_RESPONDING} (printer offline)`]);
  const st2 = fakeWin({ errorState: 4 });
  check('1_qogoz_tugagan', (await guard(st2).before('XP-58')).error, `${NOT_RESPONDING} (qog'oz tugagan)`);
  check('1_normal_ruxsat', (await guard(fakeWin()).before('XP-58')).ok, true);
}

console.log('\n── 2–3) navbatdagi cheklar ──');
{
  const jobs = [
    { id: 1, doc: 'C:\\T\\xenora_chek_1.pdf', submitted: NOW - 2 * 86400e3 },     // 2 kunlik — o'chiriladi
    { id: 2, doc: 'Microsoft Word - hisobot.docx', submitted: NOW - 2 * 86400e3 }, // begona — tegilmaydi
  ];
  const st = fakeWin({ jobs });
  const r = await guard(st).before('XP-58');
  check('3_eski_xenora_ochirildi', st.cancelled, [1]);
  check('3_begona_ish_qoldi', st.jobs.map(j => j.id), [2]);
  check('3_eskidan_keyin_ruxsat', r.ok, true);
  const st2 = fakeWin({ jobs: [{ id: 7, doc: 'xenora_chek_2.pdf', submitted: NOW - 30e3 }] });
  const r2 = await guard(st2).before('XP-58');
  check('2_yangi_chek_hali_navbatda_rad', [r2.ok, r2.error], [false, `${NOT_RESPONDING} (oldingi chek hali chiqmagan)`]);
  check('2_yangisi_ochirilmaydi', st2.cancelled, []);
  check('3_TTL_5_daqiqa', TTL_MS, 300000);
}

console.log('\n── 4) yuborgandan keyin ──');
{
  const job = { id: 9, doc: 'C:\\T\\xenora_chek_NEW.pdf', submitted: NOW };
  const st = fakeWin({ jobs: [job], printsAfter: 2 });
  const ok = await createSpoolGuard({ runPs: st.runPs, now: () => NOW, sleep: async () => {}, waitMs: 60e3, log: quiet })
    .after('XP-58', 'xenora_chek_NEW.pdf');
  check('4_chiqdi_ok', [ok.ok, st.cancelled], [true, []]);
  let t = NOW;
  const st2 = fakeWin({ jobs: [{ ...job }] });
  const bad = await createSpoolGuard({ runPs: st2.runPs, now: () => (t += 1000), sleep: async () => {}, waitMs: 10e3, log: quiet })
    .after('XP-58', 'xenora_chek_NEW.pdf');
  check('4_chiqmadi_bekor', [bad.ok, bad.cancelled, st2.cancelled], [false, true, [9]]);
  check('4_xabar', bad.error.startsWith(NOT_RESPONDING) && /navbatga qo'yilmadi/.test(bad.error), true);
}

console.log('\n── 5–6) fail-open, injection ──');
{
  const st = fakeWin({ fail: true });
  check('5_before_failopen', (await guard(st).before('XP-58')).ok, true);
  check('5_after_failopen', (await guard(st).after('XP-58', 'x.pdf')).ok, true);
  const st2 = fakeWin();
  const evil = "XP\"'; Remove-Item C:\\ -Recurse";
  await guard(st2).before(evil);
  check('6_nom_env_da', st2.calls[0].env.XN_PRINTER, evil);
  check('6_nom_skriptda_yoq', st2.calls.some(c => c.script.includes('Remove-Item C:')), false);
}

console.log('\n── 7) LAN qayta urinish (haqiqiy TCP) ──');
{
  // a) hech kim tinglamaydigan port → 3 urinish, keyin xato
  const dead = net.createServer(); await new Promise(r => dead.listen(0, '127.0.0.1', r));
  const port = dead.address().port; await new Promise(r => dead.close(r));
  const t0 = Date.now();
  const r = await sendRawTcpWithRetry('127.0.0.1', port, Buffer.from('X'), { timeoutMs: 800, gapMs: 50 });
  check('7_3_urinish_toxtadi', [r.ok, r.attempts, r.sent], [false, 3, false]);
  check('7_xabar', /3 marta urinildi.*Printer javob bermayapti/.test(r.error), true);
  check('7_tez_tugadi', Date.now() - t0 < 5000, true);
  // b) ishlayotgan "printer" — 1-urinishda, baytlar yetib bordi
  let got = Buffer.alloc(0);
  const srv = net.createServer(s => s.on('data', d => { got = Buffer.concat([got, d]); }));
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const ok = await sendRawTcpWithRetry('127.0.0.1', srv.address().port, Buffer.from('CHEK'), { timeoutMs: 2000 });
  await new Promise(r => setTimeout(r, 100));
  check('7_ishlayotgan_printer', [ok.ok, ok.attempts, got.toString()], [true, 1, 'CHEK']);
  srv.close();
  // c) yozilgandan keyin xato → qayta YUBORILMAYDI (dublikat chek bo'lmasin)
  let n = 0;
  const sentFail = await sendRawTcpWithRetry('1.2.3.4', 9100, Buffer.from('X'), {
    sender: async () => { n++; return { ok: false, sent: true, error: 'vaqt tugadi' }; }, sleep: async () => {} });
  check('7_yozilgandan_keyin_qayta_yoq', [sentFail.ok, n], [false, 1]);
  check('7_sendRawTcp_sent_maydoni', 'sent' in (await sendRawTcp('127.0.0.1', port, Buffer.from('X'), 300)), true);
}

console.log('\n── 8) main.js ulanishi + sotuv to\'xtamaydi ──');
{
  const MAIN = readFileSync(resolve('electron/main.js'), 'utf8');
  check('8_before_sumatradan_oldin', MAIN.indexOf('spoolGuard.before(dev)') < MAIN.indexOf('await _runExe(sumatra, args)'), true);
  check('8_after_sumatradan_keyin', MAIN.indexOf('spoolGuard.after(dev') > MAIN.indexOf('await _runExe(sumatra, args)'), true);
  check('8_ishga_tushishda_tozalash', /spoolGuard\.purgeStaleAll\(\)/.test(MAIN), true);
  check('8_lan_retry', /return sendRawTcpWithRetry\(ip, port, bytes\)/.test(MAIN), true);
  check('8_pdf_sarlavha_fayl_nomi', /document\.title='\s*\+\s*JSON\.stringify\(pdfName\)/.test(MAIN), true);
  // .exe qadoqlash: build.files fayllarni ANIQ sanaydi — main.js require qilgan
  // har modul ro'yxatda bo'lmasa .exe ishga tushishda yiqiladi (spool-guard.js deyarli shunday bo'ldi)
  const PKG = JSON.parse(readFileSync(resolve('electron/package.json'), 'utf8'));
  const reqs = [...MAIN.matchAll(/require\('\.\/([\w-]+)'\)/g)].map(m => m[1] + '.js');
  check('8_har_modul_exe_ichida', reqs.filter(f => !PKG.build.files.includes(f)), []);
  const POS = readFileSync(resolve('frontend/js/modules/pos.js'), 'utf8');
  // Chop etish TO'LOV yozilgandan KEYIN chaqiriladi; xato faqat toast (sotuv qaytarilmaydi)
  const pay = POS.indexOf("toast(payMethod === 'credit' ? 'Nasiya yozildi!'");
  const rcpt = POS.indexOf('showReceiptLocal(orderId, { loyalty: lastLoyalty });');
  check('8_chek_tolovdan_keyin', rcpt > 0 && pay > rcpt - 400 && rcpt > POS.indexOf("api.post('/payments/'"), true);
  check('8_chop_xatosi_faqat_toast', /toast\('Chek chiqmadi: ' \+ \(\(res && res\.error\)/.test(POS), true);
}

console.log(`\n${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
