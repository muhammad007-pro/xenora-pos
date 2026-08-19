/**
 * ESLint — `no-undef` qo'riqchisi (docs/ROADMAP-frontend-lint.md).
 *
 * MAQSAD: aynan bitta xato sinfini ushlash — mijozda IKKI marta jonli chiqqan
 * "X is not defined" (2026-08-15 `quickSellAdd`, 2026-08-17 `showAlert`). Bunday
 * kod yuklashda xato bermaydi; foydalanuvchi tugmani bosgandagina o'ladi.
 *
 * SHUNING UCHUN boshqa hamma qoida O'CHIQ. Shovqin bo'lsa hech kim ishlatmaydi
 * (roadmap: 2026-08-17 regex skaner 79 nomzoddan 1 tasi haqiqiy — tashlab
 * yuborilgan). Bu yerda faqat `no-undef`.
 *
 * IKKI KONTEKST — loyihada ikkalasi ham bor va ularni ARALASHTIRIB bo'lmaydi:
 *   • ES MODUL (`<script type="module">`, import/export bor) — o'z doirasi bor,
 *     top-level `this` yo'q.
 *   • CLASSIC (`<script src>`, import/export yo'q) — `js/admin/*` shu tarzda
 *     yuklanadi va BIR-BIRINING global funksiyalarini chaqiradi (admin.html da
 *     hammasi yonma-yon yuklanadi). Ularni modul deb tekshirish `import`
 *     bo'lmaganda ham noto'g'ri: fayllararo global chaqiruvlar "xato" bo'lib
 *     ko'rinardi. Shu sabab quyida `SHARED_GLOBALS` e'lon qilinadi.
 *
 * ISHLATISH:  npm run lint
 */
import globals from 'globals';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));

/**
 * CLASSIC TO'PLAM GLOBALLARI — avtomatik.
 *
 * `admin.html` `js/core/money.js` + `js/ui/searchable-select.js` + BARCHA
 * `js/admin/*.js` ni yonma-yon `<script src>` bilan yuklaydi. Ular bitta global
 * doirani baham ko'radi: `core.js` dagi `API_BASE`/`token`, `store.js` dagi
 * `escH`, `food.js` dagi `loadTopDishes` — hammasi bir-biridan chaqiriladi.
 * ESLint esa har faylni ALOHIDA ko'radi va bularning hammasini "aniqlanmagan"
 * deb belgilardi (birinchi skanerda 487 ta shunday "xato" chiqdi).
 *
 * Ro'yxatni QO'LDA yozish mo'rt (70+ nom). Shuning uchun to'plamdagi fayllarning
 * TOP-LEVEL e'lonlari shu yerda o'qib olinadi.
 *
 * MUHIM: bu qo'riqchini ko'r QILMAYDI — nom xato yozilgan bo'lsa (`showAlert`
 * kabi) u hech bir faylda e'lon qilinmagan, demak ro'yxatga ham tushmaydi va
 * `no-undef` uni baribir ushlaydi.
 */
function classicBundleGlobals() {
  const dir = path.join(HERE, 'frontend', 'js');
  const files = [
    path.join(dir, 'core', 'money.js'),
    path.join(dir, 'ui', 'searchable-select.js'),
    ...fs.readdirSync(path.join(dir, 'admin'))
         .filter(f => f.endsWith('.js'))
         .map(f => path.join(dir, 'admin', f)),
  ];
  const names = {};
  // Faqat ustun 0 dan boshlangan e'lonlar = TOP-LEVEL (ichki funksiyalar emas)
  const pats = [
    /^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/gm,
    /^(?:const|let|var)\s+([A-Za-z_$][\w$]*)/gm,
    /^\s*(?:window|globalThis)\.([A-Za-z_$][\w$]*)\s*=/gm,
  ];
  for (const f of files) {
    if (!fs.existsSync(f)) continue;
    const src = fs.readFileSync(f, 'utf8');
    for (const p of pats) {
      for (const m of src.matchAll(p)) names[m[1]] = 'readonly';
    }
  }
  return names;
}

// ── Fayllararo global'lar (classic <script src> bilan yuklanadi, import EMAS) ──
// DIQQAT: bu ro'yxatga faqat HAQIQATAN mavjud va global sifatida yuklanadigan
// nomlar qo'shilsin. Ortiqcha nom qo'shish — qo'riqchini ko'r qilish demak
// (aynan `showAlert` shu tarzda 7 kun yashiringan bo'lardi).
const SHARED_GLOBALS = {
  // frontend/js/ui/searchable-select.js -> window.searchableSelect
  searchableSelect: 'readonly',
  // frontend/shared/version.js -> window.APP_VERSION
  APP_VERSION: 'readonly',
  // frontend/js/core/config.js Electron/Capacitor uchun oynaga qo'yadigan qiymat
  XENORA_SERVER: 'readonly',
  Capacitor: 'readonly',
  // Chart.js — analytics/profit/report sahifalarida <script src> bilan yuklanadi
  Chart: 'readonly',
  // frontend/js/core/money.js (classic) -> g.fmtMoney / g.fmtNum.
  // Avtomatik yig'uvchi ularni ko'rmaydi: IIFE ichida `g.fmtMoney = ...` shaklida
  // berilgan (`window.` emas), shuning uchun ATAYLAB shu yerda e'lon qilinadi.
  fmtMoney: 'readonly',
  fmtNum: 'readonly',
};

// `js/admin/*.js` + money.js + searchable-select.js — admin.html da birga
// yuklanadigan classic to'plam (yuqoridagi izohga qara).
const CLASSIC_GLOBALS = { ...SHARED_GLOBALS, ...classicBundleGlobals() };

export default [
  {
    ignores: [
      'node_modules/**',
      'electron/node_modules/**',
      'electron/dist/**',
      'android/**',
      'src-tauri/**',
      'dist_artifacts/**',
      'frontend/js/**/*.min.js',
    ],
  },

  // ── ES MODUL fayllar (import/export bor) ───────────────────────────────────
  {
    files: ['frontend/js/**/*.js', 'frontend/pwa/offline-cache.js'],
    ignores: [
      'frontend/js/admin/**',
      'frontend/js/core/money.js',
      'frontend/js/ui/searchable-select.js',
    ],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser, ...SHARED_GLOBALS },
    },
    rules: { 'no-undef': 'error' },
  },

  // ── CLASSIC skriptlar (<script src>, import/export YO'Q) ───────────────────
  {
    files: ['frontend/js/core/money.js', 'frontend/js/ui/searchable-select.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: { ...globals.browser, ...SHARED_GLOBALS },
    },
    rules: { 'no-undef': 'error' },
  },

  // ── CLASSIC admin to'plami (fayllararo global chaqiruvlar bor) ─────────────
  {
    files: ['frontend/js/admin/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: { ...globals.browser, ...CLASSIC_GLOBALS },
    },
    rules: { 'no-undef': 'error' },
  },

  // ── Service worker (window yo'q, o'z global to'plami bor) ──────────────────
  {
    files: ['frontend/pwa/service-worker.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: globals.serviceworker,
    },
    rules: { 'no-undef': 'error' },
  },

  // ── shared/version.js — oddiy classic ──────────────────────────────────────
  {
    files: ['frontend/shared/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: globals.browser,
    },
    rules: { 'no-undef': 'error' },
  },

  // ── Playwright testlari ────────────────────────────────────────────────────
  // Node'da ishlaydi, LEKIN `page.evaluate(() => document...)` ichidagi kod
  // BRAUZERDA bajariladi va u ham shu faylda yozilgan. Shu sabab ikkala global
  // to'plami ham kerak — aks holda har `evaluate` "xato" bo'lib ko'rinardi.
  {
    files: ['frontend/tests/**/*.{js,mjs}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.node, ...globals.browser },
    },
    rules: { 'no-undef': 'error' },
  },
];
