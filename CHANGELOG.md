# XENORA — O'zgarishlar tarixi (CHANGELOG)

Versiya raqami har build'da oshiriladi. Manba: `electron/package.json` (version),
`android/android/app/build.gradle` (versionName/versionCode), `frontend/shared/version.js` (APP_VERSION).

## [1.0.4] — 2026-07-11

PRO qulf + super-admin username takroriy xatolari ILDIZDAN, va kassa smenasi majburiy qilindi.

### Tuzatildi
- **PRO funksiyalar qulfi (ILDIZ, takroriy):** tarif (`subscription_plan`) va feature-flag'lar
  bog'lanmagan edi — PRO tarif olingan bo'lsa ham PRO funksiyalar ochilmasdi. Endi
  `resolve_enabled_features` tarifni hisobga oladi: PRO tarif → barcha PRO flaglar avtomatik
  ochiq (backend gate/JWT + `/cafes/my/features`). Frontend `detectPlanAndLock` endi tenant-scoped
  `/cafes/my/features` dan tarifni oladi (ilgari `/cafes/` ro'yxatidan noto'g'ri kafe olinardi).
- **`/cafes/` tenant izolyatsiya:** tenant-admin endi FAQAT o'z kafesini ko'radi (ilgari barcha
  kafelar qaytardi — izolyatsiya tuynugi + noto'g'ri "joriy kafe").
- **Super-admin mijoz qo'shish — username (ILDIZ, takroriy):** yangi tenant admin username
  tekshiruvi GLOBAL edi → "admin" band chiqardi. Endi tenant-scoped (har do'konda "admin" mumkin).
- **Mijoz qo'shish formasi qotib qolishi:** bloklovchi `alert()` o'rniga toast + `try/finally`
  (tugma doim faol) + forma har ochilganda tozalanadi. Input endi qotmaydi.

### Qo'shildi
- **Kassa smenasi MAJBURIY:** ochiq smena bo'lmasa savdo (to'lov) bloklanadi (kassa bor biznes:
  food/retail/dorixona). POS to'lovdan oldin smena ochish oynasini majburlaydi (kassa ixtiyoriy,
  registrsiz ham ochiladi); backend ham talab qiladi (409). Offline navbat replay bundan mustasno.
- **Smena yopilish cheki (Z-hisobot):** yopilganda to'liq professional chek ko'rsatiladi —
  jami savdo, naqd, karta/Click/Payme, nasiya, chegirma, qaytarish, sotuvlar soni, ochilish/yopilish
  vaqti, kutilgan/haqiqiy naqd, kamomad/ortiqcha. Ekrandan chop etish + fizik Z-chek.

## [1.0.3] — 2026-07-11

To'liq audit tozalash — 14 muammo (A1-A2 kritik, B1-B6 o'rta, C1-C6 kichik). Batafsil: commit `8800a6d`.

### Tuzatildi
- **Rol izolyatsiya (A1):** rol yozish amallari faqat super-admin (rollar global).
- **Refund ombor tiklash (A2):** to'liq qaytarishda ombor tiklanadi (`ingredients_restored` idempotent).
- **Tezlik (B3/B4):** order N+1 → selectin/joined load; composite indekslar (tenant_id+created_at/status/category).
- **Dark mode ildiz (B1) + summa formati (B2):** reset.css tuzatish + umumiy `money.js`.
- **Upload tenant izolyatsiya (B5) + o'lik kod (B6):** tenant bucket + path-traversal; cross-tenant chiqim olib tashlandi.
- **Kichik (C1-C6):** held reopen snapshot, dublikat pending, stock tarix, /health versiya, /products/all limit, username 400.

## [1.0.2] — 2026-07-10

Sotuv/ombor yaxlitligi va POS chalkashliklari tuzatildi (deploy oldi sinov, 4 xato).

### Tuzatildi
- **Ombor chiqimi (KRITIK):** sotuv yakunlanganda mahsulot ombordan kamayadi (retseptli →
  ingredientlar, retseptsiz chakana tovar → o'zi). `ingredients_deducted` guard bilan idempotent
  (ikki marta ayirilmaydi). Har sotuvga `StockMovement(type="sale")` yoziladi — qaytarish bilan
  izchil. Ilgari `update_inventory_from_orders` bo'sh stub edi → magazin sotuvi omborni kamaytirmasdi.
- **Saqlash (hold) — KRITIK:** "Saqlash" endi zakazni yo'qotmaydi. Noto'g'ri "Sotuv yakunlandi"
  xabari "Buyurtma kutishga saqlandi" ga o'zgardi. Yangi **"Kutilayotgan"** paneli — saqlangan
  buyurtmalar ro'yxati + qayta ochib to'lov qilish (badge bilan soni ko'rinadi).
- **Summa formati:** butun POS'da bir xil vergulli format (770,000). Pul input'lari jonli
  formatlanadi (yozayotganda 770000 → 770,000). Yagona `fmtNum`/`parseMoney`/`attachMoneyInput`.
- **Dark mode matn (ILDIZ):** `reset.css` `[data-theme=dark] body` (spetsifiklik 0,1,1) inline
  `body{color:var(--text)}` ni bosib `--gray-50` ishlatardi → matn ko'rinmasdi. Yuqori spetsifiklik
  bilan tema rangi majburlandi — barcha POS matni (sarlavha/tugma/label) ikkala temada ko'rinadi.

## [1.0.1] — 2026-07-10

Magazin (do'kon) tenant sinovida topilgan xatolar tuzatildi + biznes turi moslashuvi.

### Tuzatildi
- **POS savatcha (KRITIK):** 2-mahsulot qo'shilganda "Cannot read properties of null (reading 'style')"
  xatosi. `#cartEmpty` node `cartItems` ichida edi va `innerHTML` uni o'chirar edi → referensiya
  cache qilinib, kerakda qayta qo'yiladi.
- **POS dark mode:** mahsulot nomlari qorong'i fonda ko'rinmasdi → `.prod-name` ga aniq `color:var(--text)`.
- **Xodim PIN:** xodim endi faqat ISM + PIN bilan qo'shiladi (telefon/login/parol ixtiyoriy).
  Kassir/ofitsiant access_code + 4-xonali PIN bilan tez kiradi.
- **Username "band" xatosi:** username unikalligi endi TENANT ICHIDA (global emas) — har do'konda
  "admin"/"cashier" takrorlanishi mumkin. Tenant izolyatsiya buzilmadi.
- **PRO funksiyalar qulfi:** tenant tarifi PRO bo'lsa PRO feature-flag'lar ochiladi (Sozlamalarda).
  FREE tarifda qulf. Super-admin baribir override qiladi.
- **Ombor:** kirim modalidan to'g'ridan yangi mahsulot qo'shish mumkin (barkodsiz ham),
  boshlang'ich qoldiq bilan birga ombor kirimi yoziladi.

### Biznes turi moslashuvi (magazin vs restoran)
- Magazin/do'konda "Buyurtma" → "Savatcha" atamasi.
- Magazin/xizmatda "Bronlar" (stol bandlash) navi yashiriladi (faqat restoran/kafe).
- Xodim rol ro'yxati biznes turiga qarab: magazin — admin/cashier; restoran — + kitchen/waiter.
- Sotuv yakunlanganda magazinda "Sotuv yakunlandi" (restoranda "Buyurtma saqlandi").

### Versiya boshqaruvi
- Versiya 1.0.0 → 1.0.1 (Electron + Android + app ichida ko'rinadi).
- .exe nomida versiya: `XENORA Setup 1.0.1.exe`, `XENORA-Portable-1.0.1.exe`.
- Login sahifada versiya yorlig'i dinamik (`version.js`).

## [1.0.0]
- XENORA POS tizimi — dastlabki relizlar (server rejimi, Electron/Android, tenant izolyatsiya).
