# Frontend lint — ta'riflanmagan funksiya chaqiruvlari (keyingi build)

Holat: **rejalashtirilgan, hali qilinmagan.** Build oldida vaqt yo'q edi
(2026-08-18 qarori), keyingi buildga qoldirildi.

## Nima uchun

Bir xil sinfdagi xato mijozda **ikki marta** jonli chiqdi:

| Sana | Xato | Oqibat |
|---|---|---|
| 2026-08-15 | `quickSellAdd is not defined` (`5d09bbe`) | POS "Tez sotuv" tugmasi savatga qo'shmasdi |
| 2026-08-17 | `showAlert is not defined` (`8cf8b14`) | Mijozga nasiya yozib bo'lmasdi (7 kun davomida `POST /debts/` umuman ketmagan) |
| 2026-08-18 | **`res.id` / `res.items` — noto'g'ri property** (`suppliers.html`) | Firma qo'shilganda ham qizil "Xatolik"; firmalar ro'yxati va dropdownlar bo'sh |

Hammasi **yuklashda xato bermaydi** — kod "to'g'ri ko'rinadi", xato faqat
foydalanuvchi tugmani bosganda chiqadi. Shu sabab qo'lda sinovdan o'tib ketadi.

## ⚠️ ESLint `no-undef` UCHINCHI holatni USHLAMAYDI

3-holat boshqa sinf: funksiya nomi to'g'ri, **obyekt sxemasi** noto'g'ri o'qilgan.
`js/core/api.js` o'ralgan javob qaytaradi (`{success, data, error}`), sahifa esa
xom javob kutgan (`res.id`, `res.items`, `res.detail`). JavaScript'da mavjud
bo'lmagan property `undefined` beradi — xato ham, ogohlantirish ham yo'q.

`no-undef` bunga ko'r. Kerak bo'ladigan qatlamlar:
1. **TypeScript yoki JSDoc + `checkJs`** — `api.get()` qaytish turini e'lon qilib,
   `res.items` ni kompilyatsiya vaqtida xato deb belgilaydi. Eng ishonchli, lekin
   eng katta ish (bosqichma-bosqich: avval `js/core/api.js` ga JSDoc tur).
2. **Shartnoma testi** (arzon, bugun qilindi):
   `frontend/tests/test_suppliers_api_contract.mjs` — Playwright bilan HAQIQIY
   sahifani ochib, tarmoqni mock qilib, oqimni bosib ko'radi. Xuddi shu naqshni
   boshqa yozuv sahifalariga ham qo'llash kerak.
3. `api.*` javobini to'g'ridan-to'g'ri ishlatishni **taqiqlovchi** ESLint qoidasi
   (`no-restricted-syntax`): `await api.get(...)` natijasidan `.items`/`.id`
   o'qilsa ogohlantirsin. Mo'rt, lekin arzon oraliq chora.

**Xulosa:** ESLint `no-undef` — 1 va 2-holat uchun; 3-holat uchun tur tekshiruvi
(JSDoc/TS) yoki shartnoma testi kerak. Ikkalasi ham keyingi buildga.

## Mavjud qo'riqchi va uning chegarasi

`frontend/tests/test_module_inline_onclick.js` (branch: `feature/frequent-products`)
faqat HTML'dagi inline `onclick="fn()"` ni `<script type="module">` ichidagi
`window.fn` eksporti bilan solishtiradi. `showAlert` esa **modul ichidan**
chaqirilgan — boshqa sinf, qo'riqchi ko'rmaydi.

## Regex skaner — YARAMAYDI (sinab ko'rildi)

2026-08-17 da bir martalik regex skaner yozildi (146 fayl): **79 nomzod chiqardi,
faqat 1 tasi haqiqiy** (`showAlert`). Qolganlari — funksiya faylda keyinroq
ta'riflangan, metod parametri (`updater`, `compute`) yoki brauzer API
(`BarcodeDetector`). Bunday nisbat bilan hech kim ishlatmaydi. Skript saqlanmadi.

Sabab: satr/izohlarni regex bilan tozalash katta fayllarda desinxron bo'ladi,
scope tahlili esa umuman yo'q.

## To'g'ri yechim: ESLint `no-undef`

Haqiqiy parser + scope tahlili — `showAlert` ni noto'g'ri signalsiz topadi.

Taxminiy ish (~30 daqiqa):
1. `npm i -D eslint` (repo ildizida `package.json` bor)
2. `eslint.config.js`: `languageOptions.globals` = browser + loyihaning
   global helperlari (`toast`, `apiFetch`, `api`, `fmtMoney`, `showToast`, …)
   — ular `<script src>` orqali global scope'da yuklanadi, import qilinmaydi
3. Qoidalar: `no-undef: error`, qolganlari o'chirilgan (shovqin bo'lmasin —
   maqsad faqat SHU sinf xatosi)
4. `npm run lint` skripti + commit oldidan qo'lda ishga tushirish
5. Ixtiyoriy: GitHub Actions'ga qo'shish (`.github/workflows/` allaqachon bor)

**Kutilgan natija:** `showAlert`/`quickSellAdd` turidagi xato mijozga yetib
bormaydi — u commit paytida ushlanadi.

## Eslatma

HTML fayllar ichidagi inline `<script>` ni ESLint to'g'ridan-to'g'ri o'qimaydi.
Kerak bo'lsa `eslint-plugin-html` qo'shiladi — aks holda faqat `js/` papkasi
tekshiriladi (bu ham ikkala xatoni ushlagan bo'lardi, ikkalasi ham `js/` da edi).
