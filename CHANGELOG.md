# XENORA — O'zgarishlar tarixi (CHANGELOG)

Versiya raqami har build'da oshiriladi. Manba: `electron/package.json` (version),
`android/android/app/build.gradle` (versionName/versionCode), `frontend/shared/version.js` (APP_VERSION).

## [1.2.7] — 2026-07-20

Chek: avtomatik chiqarish + HTML GDI print (encoding). **Migratsiya YO'Q** (kod).

### Qo'shildi
- **Avtomatik chek:** to'lov muvaffaqiyatli tugagach chek **har doim bir marta** avtomatik chiqadi
  (kassir "Chop etish" bosmaydi) — online (`showReceipt`) va offline checkout ikkalasida. "Chop etish"
  tugmasi qayta bosish (reprint) uchun qoladi. Ikki nusxa chiqmaydi.

### Tasdiqlandi (arxitektura)
- POS chek oqimi backend RAW ESC/POS (`/orders/{id}/print`) ni **chaqirmaydi** — `sendEscposPrint →
  printReceiptHTML → webContents.print` = **HTML GDI** (v1.2.4'dan beri). Chek HTML: `<meta charset=UTF-8>`,
  Courier New monospace, 58mm, pageSize yo'q. Reprint (POS + Sotuvlar tarixi) shu HTML GDI yo'lini ishlatadi.

> ⚠️ Eslatma: agar chek matni buzuq (krakozyabra) chiqsa — bu DRAYVER muammosi (XP-58 "matnli/ESC-POS"
> rejimда), dastur to'g'ri HTML GDI yuboradi. Yechim: XP-58 ni "Grafik/Raster" drayver bilan o'rnatish.

## [1.2.6] — 2026-07-20

Chek silent print — did-finish-load + pageSize olib tashlash. **Migratsiya YO'Q** (kod).

### Tuzatildi
- **Chek chiqmasligi (success=true, lekin qog'oz yo'q):** XP-58C tanlangan/default bo'lsa ham chek
  chiqmadi. Sabab: (1) chek HTML to'liq render bo'lishidan oldin o'lchov → `scrollHeight=0` →
  `pageSize.height=0` → printer bo'sh job oldi; (2) custom `pageSize` (58mm micron) ni termal
  drayver o'z formiga moslay olmadi. Yechim (`electron/main.js`): `did-finish-load` kutiladi (loadURL
  await) + 250ms render kechikish; **`pageSize` umuman berilmaydi** — XP-58C drayveri o'z 58mm formini
  ishlatadi (Windows sinov cheki ham pageSize'siz chiqadi). Height=0 bug'i butunlay yo'qoldi.
- deviceName mantiqi (printer_name yoki bo'sh→OS default) va toast halolligi (success faqat haqiqiy
  print callback'da) saqlandi. Reprint (POS + Sotuvlar tarixi) shu yo'lni ishlatadi.

## [1.2.5] — 2026-07-20

Chek silent print jonli sinov tuzatish. **Migratsiya YO'Q** (kod).

### Tuzatildi
- **Chek chiqmasligi (silent print, KRITIK):** XP-58C Windows default bo'lsa ham chek chiqmadi va
  "Chek chiqarildi" yolg'on toast ko'rsatilardi. Sabab: `webContents.print` ga `deviceName:''`
  (bo'sh satr) berilardi — bu OS default'ga tushmaydi (kalitni butunlay tushirish kerak), job
  hech qayerga ketib baribir `success=true` qaytarardi. Endi deviceName bo'sh bo'lsa **kalit
  berilmaydi** → Windows standart printeri (XP-58C) ishlatiladi.
- **58mm pageSize:** print A4 emas, `pageSize {width:58000, height: kontent}` (mikронда) — termal
  rolikga mos, ortiqcha bo'sh qog'oz yo'q.
- **Toast halolligi:** "Chek chiqarildi" faqat print callback muvaffaqiyatida; xatoда aniq
  "Chek chiqmadi: printer topilmadi/…".

### Qo'shildi
- **Chek printeri tanlash:** "Chek sozlamalari" sahifasida printer datalist (Electron mavjud
  printerlar ro'yxati; XP-58C tanlanadi, `printer_name` tenant config'ga saqlanadi). Bo'sh = OS default.

## [1.2.4] — 2026-07-20

Chek LOKAL silent print + reprint. **Migratsiya YO'Q** (kod, DB emas).

### Tuzatildi
- **Chek printerga chiqmasligi (KRITIK):** backend SERVERda (146.190.225.168) ishlaydi va
  do'kondagi USB printer (XP-58) ga yeta olmasdi; ustiga `mode=mock` yolg'on "yuborildi" toast
  ko'rsatib `window.print()` fallback'ni bloklardi. Endi chek **do'kon kompyuterida LOKAL**
  chiqadi: Electron'da yashirin oyna orqali **silent** (dialogsiz) print, brauzerda iframe dialog.
  Server ESC/POS yo'li POS'dan bypass qilindi; mock yolg'on-muvaffaqiyat olib tashlandi (xatoda aniq toast).

### Qo'shildi
- **Chek reprint (qayta chop):** POS "Chop etish" tugmasi oxirgi chekni qayta bosadi; Sotuvlar
  tarixida har sotuv yonida 🖨 tugma + sotuv detali modalida "Chekni chop etish". Bir xil LOKAL silent yo'l.
- **Chek printeri sozlamasi:** Sozlamalar → Printer → "Chek printeri (Windows nomi)" (`printer_name`,
  bo'sh = OS standart printeri) + Electron mavjud printerlar ro'yxati (datalist).

### Texnik
- `electron/main.js` `print-receipt`/`list-printers` IPC (silent `webContents.print`); `preload.js` ko'prigi.
- `frontend/js/core/receipt-print.js` (yangi) — `printReceiptHTML` + `buildReceipt58` (58mm); global scope tegmaydi.
- `backend/routers/settings.py` — `/settings/printer/status` endi `printer_name` qaytaradi.

## [1.2.3] — 2026-07-19

Sodiqlik (mijoz % chegirma), nasiya tez mijoz, Firmalar iframe, yangi grafik + bug fixlar.
**1 migratsiya:** `c9d0e1f2a3b4` (customers.discount_percent).

### Qo'shildi
- **Sodiqlik dasturi (S0–S3):** doimiy mijozga avtomatik % chegirma. `customers.discount_percent`
  (0–100). Kiritish: #13 tez qo'shish (debt+POS) + Admin Mijozlar tahrir/qo'shish modali. POS: mijoz
  tanlanганda chegirма avtomatик (variant A — qo'lда chegирма ustun, stack yo'q). Chek: "Chegirma −10% (mijoz)".
- **Nasiyada tez mijoz qo'shish (#13):** admin debt modal + POS customerModal — ism+telefon (majburiy)
  bilan inline yangi mijoz. Mijozlar sahifasi endi to'liq (qo'shish/tahrir; "tez orada" olib tashlandi).
- **Firmalar iframe (#16):** suppliers.html admin panel ICHIDA ochiladi (yangi oyna emas) — `data-page` + iframe.
- **Sotuv dinamikasi grafik (#18):** eski div-bar → toza SVG area (silliq egri, emerald gradient,
  avtomatik Y masshtab, "Ma'lumot yo'q" holati). Kutubxonasiz (Electron file:// mos).
- **Ombor narx ustuni (#12):** ombor jadvalida sotuv narxi (+ tannarx sub-qator).

### Tuzatildi
- **`getApiBase` oilasi (#14/15/19):** Aksiyalar/Tez sotuv/Etiketka/Chek sozlamalari — mavjud bo'lmagan
  `getApiBase()` → API_BASE/apiFetch/apiFetchPost. Admin nasiya (saveDebt/payDebt) yashirin GET→POST
  (nasiya haqiqatan saqlanadi).

## [1.2.2] — 2026-07-18

Pachka/Dona to'liq tizim + mahsulot/ombor bug tuzatishlari + ombor qiymati (deploy; build keyinroq).
**2 migratsiya:** `a7b8c9d0e1f2` (pack ustunlar), `b8c9d0e1f2a3` (return base_qty).

### Qo'shildi
- **Pachka/Dona (B0–B7):** bitta mahsulot ham pachka, ham dona sotiladi (mustaqil narx: pachka=`pack_price`,
  dona=`price`). Ombor **base=dona** (pachka sotilsa `pack_size` dona kamayadi). Mahsulot formasida pachka
  narxi/o'lchami (weight bilan ziddiyat bloklangan). POS: skan/bosishда "Pachka yoki Dona?" tanlov + savat
  yorlig'i + `unit_sold` server tomonда narx/`base_qty` hisoblaydi. Kirim pachka bilan (5 pachka=+50 dona).
  Chek "Pachka (10 dona)". Qaytarish pachका (return `base_qty`). Eski ma'lumot guided tuzatish ("Pachka sozlash").
  Yangi maydonlar: `products.pack_size/pack_price`, `order_items.base_qty/unit_sold`, `return_items.base_qty`.
- **Ombor umumiy qiymati (#10):** Ombor sahifasида KPI kartalar — tannarx/sotuv/potensial foyda
  (`SUM(qty×cost_price)`, backend SQL, tenant-scoped, `view_reports`).
- **Bulk kategoriya (BUG 4):** mahsulotlar jadvalида checkbox + "Tanlanganlarga kategoriya berish"
  (`PATCH /products/bulk-category`). Mahsulotlar `page_size` 20→500.
- **POS grid/list (BUG 3):** mahsulot ko'rinishini grid ⊞ / list ☰ almashtirish (default list — ko'p mahsulotда).

### Tuzatildi
- **Mahsulot CRUD (BUG 1/8/9):** o'chirilgan mahsulot barkodi band qolardi → soft-delete barkod/sku'ni bo'shatadi
  (faol mahsulot band hisoblanadi). O'chirishdan keyin forma qotishi (=BUG 8) hal. Soni kiritilmagan mahsulot
  omborда ko'rinмасди → yaratishда doim 0 qoldiqli inventory qatori. Boshlang'ich qoldiq add-stock orqali.
- **Ombor kirim (BUG 5/6):** "+ Kirim" berk toast o'rniga mahsulot tanlab kirim modali. Pagination 20→500
  (uzun ro'yxat, mahsulotlar sahifasidek).

### Skript
- `backend/scripts/cleanup_deleted_barcodes.py` — eski soft-delete mahsulotlar barkodini bo'shatish (bir martalik,
  dry-run + `--apply`, idempotent, tenant-safe).

## [1.2.1] — 2026-07-14

Brend yakuni + operatsion bug tuzatishlari (deploy; Windows/Android build keyinroq).

### Tuzatildi
- **Brend ∞ (splash/logo):** Android `splash.png` (26 variant — portrait/landscape/night) eski yulduz →
  navy + emerald→tilla ∞ (PIL). POS logotip (`pos.html` 2 joy: yuklanish + sidebar) yulduz → `logo.svg` (∞).
- **Kutilayotgan buyurtmalar:** (BUG 7) reopen qilingan held sotilганда dublikat qolardi → sotuvда eski held
  cancel qilinadi (`holdBtn` dedup kabi). (BUG 5) har kutilayotgan qatorга **🗑 o'chirish** tugmasi (cancel).
- **Mahsulot o'lchov birligi:** `store`/`fast_food`/`pharmacy` formasiga `sale_unit` dropdown (Dona default,
  ro'yxat: Dona/Kg/Gramm/Litr/Ml/Metr/Sm/Quti/Upakovka/Porsiya). Ombor `Inventory.unit` endi
  mahsulot sotuv birligidan olinadi (kg hardcode yo'q; pcs→dona). Migratsiya yo'q.
- **Mahsulot rasmi (POS):** `image_url` root-relative (`/uploads/...`) Electron `file://` da ishlamasdi →
  POS `imgSrc()`/`_uplBase` bilan to'liq server URL (admin bilan izchil). Brauzер/PWA/Electron'да ko'rinadi.
- **Dashboard grafik:** `visibilitychange` auto-refresh — POS'da savdo qilib qaytganda KPI+grafik yangilanadi.

### Migratsiya
Yo'q (barcha maydonlar mavjud).

## [1.2.0] — 2026-07-13

Xavfsizlik va tarif relizi: to'liq RBAC audit tuzatishlari, tarif qayta ishlashi (Free→Lite),
biznes-turi bo'yicha funksiya filtri, dizayn qoldiqlari va menejer roli.

### Qo'shildi
- **Menejer roli** — admin va kassir orasidagi rol (8 ruxsat: view_finance, process_payments,
  view_analytics, view_reports, manage_menu, manage_inventory, manage_customers, manage_shifts).
  Nozik joylar yo'q (manage_settings/users/roles bermaydi). Global rol, `init_db()` seed.
- **`manage_products` ruxsati** — ilgari yo'q edi, vehicle/service DELETE uni ishlatardi (doim 403).
  Endi seedда bor, admin oladi (service/vehicle boshqaruvi tiklandi).
- **Biznes-turi PRO funksiya filtri** — `BUSINESS_PRO_MATRIX`: har biznes turi faqat o'ziga tegishli
  PRO funksiyalarni oladi (restoran markirovka ko'rmaydi). Begona funksiya UI'da umuman ko'rinmaydi.
- **Ilova ichida versiya** — admin sozlamalarida "XENORA — versiya vX.Y.Z" (Windows+Android bir manba).

### O'zgartirildi
- **Tarif Free → Lite** (faqat nom; kalit "free" saqlandi). Tenant UZS, superadmin SaaS daromadi $ ($10/$50).
- **Pro funksiyalar toggle** — Pro tenant funksiyalarni o'zi yoqib/o'chiradi (majburiy qulf emas).
- **RBAC audit (6 bosqich):** moliya yozish (debt/supplier/priyomka)→view_finance/process_payments;
  imtiyoz (cafe features/branches)→manage_settings; settings global→tenant izolyatsiya;
  analitika sub-endpoint (14)→view_analytics(+feature); hotel xona→manage_settings;
  menyu-config (18 yozish)→manage_menu. Operatsion oqim (order/kitchen/table) saqlandi.
- **Backend feature enforcement** — 14 pro/biznes router + 14 analitika endpointга `require_feature`.

### Tuzatildi
- **Dizayn qoldiqlari** — splash (yulduz→∞ infinity, navy fon), login yashil→navy, ai_warehouse/qr/qr-table
  eski palitra→navy; Electron/Android ikonka ∞; koshin/animatsiya barcha ekranда.
- **Sotuv dinamikasi grafigi** — "Hafta" bo'sh edi (period filtri xatosi), tuzatildi; tugmalar ishlaydi.
- **Android header sana** — mobil siqilish (responsiv qisqa sana + nowrap).

## [1.1.0] — 2026-07-13

KATTA yangilanish: yangi XENORA brend dizayni, admin refaktoring va AI-ombor (rasmdan mahsulot o'qish) bir relizda.

### Qo'shildi
- **AI-ombor (rasmdan mahsulot o'qish):** qog'oz mahsulot ro'yxati rasmini AI (Claude vision, Haiku)
  o'qib, omborga kirim qiladi. 3 bosqich: (1) backend — rasm siqish + Claude API + xavfsiz JSON parse;
  (2) frontend — kamera/galereya, tahrirlanadigan jadval, ishonch (confidence) rangli, dublikat aniqlash;
  (3) integratsiya — omborga qo'shish (yangi mahsulot + shtrix-kod avto/qo'lda) yoki mavjudni to'ldirish,
  kirim (StockMovement 'in', manba='ai_warehouse'), sotish narxi (ustama % yoki qo'lda), tranzaksiya.
  Ruxsat: `manage_inventory` (kassirda yo'q). Tenant izolyatsiya + audit. Endpoint: `/api/v1/ai-warehouse/`.
  **API kalitsiz ishlaydi:** `ANTHROPIC_API_KEY` qo'yilmaguncha 503 "sozlanmagan" (crash emas).
- **Ombor sahifasida "AI bilan qo'shish" tugmasi** (emerald urg'u) → AI-ombor sahifasi.

### O'zgartirildi
- **Yangi XENORA brend dizayni (butun tizim):** tilla-asosdan → navy asos + emerald urg'u + tilla milliy
  detal. Koshin (o'zbek naqsh) fon, Sora/Inter/JetBrains shrift, dark/light (WCAG AA), animatsiya
  (count-up/stagger/hover). Admin SPA + 58 standalone sahifa bir xil brend.
- **Admin refaktoring:** monolit admin.js → 14 modul (`js/admin/*.js`: core/food/settings/reports/shift/…).

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
