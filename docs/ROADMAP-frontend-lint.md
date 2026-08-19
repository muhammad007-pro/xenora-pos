# Frontend lint — ta'riflanmagan funksiya chaqiruvlari

Holat: **BAJARILDI** (2026-08-19, branch `chore/eslint-setup`) — sozlama va
skaner tayyor. Topilgan xatolar HALI TUZATILMAGAN (qaror keyin).

## Natija (birinchi to'liq skaner, 2026-08-19)

`npm run lint` → **3 ta haqiqiy xato** (75 fayl):

| Fayl | Xato | Turi | Holat |
|---|---|---|---|
| `js/payments.js:22` | `?.value = ...` — ixtiyoriy zanjir chap tomonda | **Sintaksis** — fayl umuman yuklanmaydi | ✅ tuzatildi |
| `js/promo.js:169` | fayl IKKI MARTA nusxalangan, `API` ikki marta e'lon | **Sintaksis** — fayl umuman yuklanmaydi | ✅ tuzatildi |
| `js/modules/admin.js:422` | `formatTime` import qilinmagan | `no-undef` — `showAlert` bilan bir sinf | ✅ fayl o'chirildi (o'lik kod) |

`js/modules/admin.js` — **o'lik kod** ekani tasdiqlandi va fayl o'chirildi:
hech bir HTML uni yuklamasdi, hech bir JS import qilmasdi (yagona havola —
service-worker keshlash ro'yxati); 6 ta import yo'lining hammasi mavjud
bo'lmagan papkaga qarardi (`'../../core/api.js'` -> `frontend/core/...`);
oxirgi o'zgarish 2026-07-09, jonli admin kodi esa `js/admin/*.js`
(2026-08-16). `CHANGELOG` v1.8.2 auditi ham uni o'lik deb belgilagan edi.
Shu sabab `formatTime` ni qo'shish ma'nosiz bo'lardi — u faylni tiriltirmasdi.

Boshlang'ich skaner 538 ta bergan edi; 535 tasi **konfiguratsiya teshigi** edi
(classic `<script src>` to'plamining fayllararo global'lari, Playwright
testlaridagi `page.evaluate` brauzer kodi, `Chart`). Sozlama tuzatilgach faqat
haqiqiylari qoldi — roadmapdagi "shovqin bo'lsa hech kim ishlatmaydi" sharti
bajarildi.

## Isbot: `showAlert` ushlanadimi?

`8cf8b14` dan OLDINGI `store.js` ni shu sozlama bilan tekshirdik:

```
$ git show 8cf8b14^:frontend/js/admin/store.js | npx eslint --stdin \
    --stdin-filename frontend/js/admin/store.js
  546:17  error  'showAlert' is not defined  no-undef
  ... (12 ta)
```

Ya'ni bu qo'riqchi o'rnatilgan bo'lsa, nasiya 7 kun buzuq turmasdi.

## Qaysi xato sinfini USHLAYDI, qaysinisini YO'Q

| Holat | Ushlanadimi | Nima bilan |
|---|---|---|
| `showAlert is not defined` (nom hech qayerda yo'q) | ✅ HA | `no-undef` (12 ta belgilandi) |
| `quickSellAdd is not defined` (modul funksiyasi, inline `onclick`) | ❌ YO'Q | Chaqiruv **satr ichida** (`\`<button onclick="...">\``) — ESLint uni kod deb ko'rmaydi. Buni mavjud `tests/test_module_inline_onclick.js` ushlaydi |
| `js/core/toast.js` fayli yo'q edi (4 sahifa import qiladi) | ❌ YO'Q | Import yo'lini tekshirish yadro ESLintda yo'q (`eslint-plugin-import` + HTML linting kerak); importlar HTML ichida edi |
| `features.has(...)` — metod nomi noto'g'ri (`isEnabled`) | ❌ YO'Q | Bu **tur** xatosi, doira xatosi emas — JSDoc/TS `checkJs` kerak |
| `res.items` / `res.id` — API shartnomasi | ❌ YO'Q | Xuddi shu sabab (roadmapda ilgari ham yozilgan) — shartnoma testi yoki JSDoc/TS |

Xulosa: `no-undef` 5 holatning **1 tasini** ushlaydi, ammo aynan o'sha eng
uzoq yashiringani (7 kun) edi. Qolgan 4 tasi uchun keyingi qatlamlar kerak
(pastdagi ro'yxat).

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
