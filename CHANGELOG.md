# XENORA — O'zgarishlar tarixi (CHANGELOG)

Versiya raqami har build'da oshiriladi. Manba: `electron/package.json` (version),
`android/android/app/build.gradle` (versionName/versionCode), `frontend/shared/version.js` (APP_VERSION).

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
