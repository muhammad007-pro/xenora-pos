/**
 * REGRESSIYA QO'RIQCHISI: <script type="module"> ichidagi funksiyaga inline
 * onclick/onchange orqali murojaat.
 *
 * MUAMMO (mijozda topildi, Fazza Parfum): POS "TEZ SOTUV" tugmasi bosilganda
 *   Uncaught ReferenceError: quickSellAdd is not defined
 * Sabab: pos.js `<script type="module">` bilan yuklanadi. Modul ichidagi
 * `function foo(){}` GLOBAL EMAS — u modul doirasida qoladi. Inline `onclick`
 * esa nomni window'dan qidiradi. Kod "to'g'ri ko'rinadi", lekin ishlamaydi va
 * XATO FAQAT TUGMA BOSILGANDA chiqadi — shu sabab sinovdan o'tib ketgan.
 *
 * Shu tuzoqqa BIR VAQTDA ikkita funksiya tushgan edi (quickSellAdd, filterByDept
 * — ikkalasi ham BOSQICH 20/21). Demak bu bir martalik xato emas, TAKRORLANADIGAN
 * naqsh. Bu test uni kelajakda avtomatik ushlaydi.
 *
 * Ishga tushirish:  node frontend/tests/test_module_inline_onclick.js
 */
'use strict';
const fs   = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');

// Brauzer/global nomlar — bular window'da allaqachon bor, eksport talab qilinmaydi.
const KNOWN_GLOBALS = new Set([
  'document', 'window', 'alert', 'confirm', 'history', 'location', 'console',
  'event', 'this', 'return', 'if', 'localStorage', 'sessionStorage',
]);

// 1) Qaysi JS fayllar <script type="module"> bilan yuklanadi?
function htmlFiles(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (!['node_modules', '.git'].includes(e.name)) out.push(...htmlFiles(p)); }
    else if (e.name.endsWith('.html')) out.push(p);
  }
  return out;
}

const moduleScripts = new Set();
for (const h of htmlFiles(ROOT)) {
  const src = fs.readFileSync(h, 'utf8');
  for (const m of src.matchAll(/<script[^>]*type=["']module["'][^>]*src=["']([^"']+)["']/g)) {
    const resolved = path.resolve(path.dirname(h), m[1]);
    if (fs.existsSync(resolved)) moduleScripts.add(resolved);
  }
}

if (!moduleScripts.size) {
  console.error("XATO: birorta ham module skript topilmadi — test eskirgan bo'lishi mumkin.");
  process.exit(2);
}

// 2) Har bir modulda inline onclick/onchange/oninput ichidagi funksiya nomlarini top,
//    keyin o'sha nom window'ga eksport qilinganini tekshir.
const findings = [];
let scanned = 0, checked = 0;

// IZOHGA OLINGAN kod eksport HAM, chaqiruv HAM emas. Buni hisobga olmaslik
// qo'riqchining o'zini yaroqsiz qilardi: `// window.foo = foo;` qatorini ham
// eksport deb o'qib, xatoni o'tkazib yuborardi (sinovda aynan shunday bo'ldi).
function isCommentLine(src, index) {
  const start = src.lastIndexOf('\n', index) + 1;
  const before = src.slice(start, index);
  const trimmed = src.slice(start).split('\n')[0].trimStart();
  return trimmed.startsWith('//') || trimmed.startsWith('*') || before.includes('//');
}

for (const file of [...moduleScripts].sort()) {
  const raw = fs.readFileSync(file, 'utf8');
  // Blok izohlarini olib tashlaymiz (o'rniga bo'sh joy — qator raqamlari saqlanadi)
  const src = raw.replace(/\/\*[\s\S]*?\*\//g, c => c.replace(/[^\n]/g, ' '));
  scanned++;

  // window.foo = ... | window['foo'] = ... (izohdagilar hisobga olinmaydi)
  const exported = new Set();
  for (const m of src.matchAll(/window\.([A-Za-z_$][\w$]*)\s*=/g)) {
    if (!isCommentLine(src, m.index)) exported.add(m[1]);
  }
  for (const m of src.matchAll(/window\[["']([^"']+)["']\]\s*=/g)) {
    if (!isCommentLine(src, m.index)) exported.add(m[1]);
  }

  // Shablon satri ichidagi inline hodisa: onclick="foo(...)" yoki onclick=\"foo(...)\"
  const re = /\bon(?:click|change|input|submit|focus|blur|keyup|keydown)\s*=\s*\\?["']\s*([A-Za-z_$][\w$]*)\s*\(/g;
  for (const m of src.matchAll(re)) {
    const name = m[1];
    if (KNOWN_GLOBALS.has(name)) continue;
    if (isCommentLine(src, m.index)) continue;
    checked++;
    if (!exported.has(name)) {
      const line = src.slice(0, m.index).split('\n').length;
      findings.push({ file: path.relative(ROOT, file).replace(/\\/g, '/'), line, name });
    }
  }
}

console.log(`Tekshirildi: ${scanned} ta module skript, ${checked} ta inline hodisa chaqiruvi.`);

if (findings.length) {
  console.log('\nXATO — modul funksiyasi window\'ga eksport qilinmagan (inline onclick ISHLAMAYDI):');
  for (const f of findings) {
    console.log(`  ${f.file}:${f.line}  ${f.name}()  ->  yechim: window.${f.name} = ${f.name};`);
  }
  console.log(`\n${checked - findings.length}/${checked} PASS`);
  process.exit(1);
}
console.log(`\n${checked}/${checked} PASS — barcha inline hodisa funksiyalari window'da mavjud`);
