# XENORA — O'zgarishlar tarixi (CHANGELOG)

Versiya raqami har build'da oshiriladi. Manba: `electron/package.json` (version),
`android/android/app/build.gradle` (versionName/versionCode), `frontend/shared/version.js` (APP_VERSION).

## [1.10.5] — 2026-09-03 — Sentry uchun alohida bot

v1.10.4 da kanal ajratilgandi, lekin bot BITTA edi — texnik va biznes
xabarlar Telegram'da bir xil bot nomi ostida kelardi. Endi:

  TELEGRAM_BOT_TOKEN + ALERT_CHAT_ID        → obuna (biznes)
  SENTRY_BOT_TOKEN   + SENTRY_ALERT_CHAT_ID → 5xx xatolar (texnika)

`SENTRY_BOT_TOKEN` bo'sh bo'lsa `TELEGRAM_BOT_TOKEN` ishlatiladi (orqaga
moslik: kalitni qo'shmagan o'rnatma avvalgidek ishlaydi). Obuna yo'li
(`send_to_chat`) yangi kalitni umuman bilmaydi.

3 yangi test. To'plam: 332 passed, 2 skipped (avval 329).

⚠️ **MIGRATSIYA YO'Q.** Deploy: `git pull` + `systemctl restart xenora`.
⚠️ Bu relizda `SUBSCRIPTION_ALERTS_ENABLED=True` QILINDI — obuna
ogohlantirishlari YOQILDI. `ENFORCE_SUBSCRIPTION` hamon `False`
(hech kim bloklanmaydi).
Rollback: kod `804ada8` (v1.10.4).
Client `.exe`/`.apk` **kerak emas**.

## [1.10.4] — 2026-09-03 — Sentry xato xabarlari alohida kanalga

v1.10.3 da Telegram boti birinchi marta ulandi va shu bilan eski nuqson
AMALDA ko'rindi: `core/alert.send_alert` `ALERT_CHAT_ID` ga QATTIQ
bog'langan edi, uning yagona chaqiruvchisi esa Sentry
(`core/observability._maybe_alert`). Ya'ni har 5xx xato uchun
"🔴 XENORA xato" xabari OBUNA ogohlantirishlari keladigan chatga tushardi
va egasi o'qishi kerak bo'lgan "obuna 7 kundan keyin tugaydi" xabarini
texnik shovqin orasida ko'mib qo'yardi.

Endi bitta bot, ikki ayrim kanal:

  ALERT_CHAT_ID         — BIZNES: obuna ogohlantirishlari (7/3/1 kun,
                          muddat tugashi, blok). Egasi o'qiydigan kanal.
  SENTRY_ALERT_CHAT_ID  — TEXNIKA: 5xx xatolar. **BO'SH bo'lsa Telegram
                          xabari UMUMAN yuborilmaydi** (Sentry'ning o'zi
                          odatdagidek ishlayveradi).

`send_alert` endi chat'ni ANIQ oladi (`chat_id`), standarti bo'sh. Standart
ATAYLAB `ALERT_CHAT_ID` EMAS: aynan o'sha qattiq bog'lanish shu muammoni
keltirgan edi, kelajakdagi yangi chaqiruvchi e'tiborsizlik bilan biznes
kanaliga yozib yubormasin. Obuna yo'li (`send_to_chat`) tegilmadi va Sentry
sozlamasidan mustaqil.

7 ta yangi test (`backend/tests/test_alert_channels.py`): Sentry texnik
kanalga ketishi, bo'sh kanalda umuman yuborilmasligi (biznes kanaliga ham
tushmasligi), chat berilmasa jim qolishi, 4xx istisnosi saqlangani, obuna
yo'lining mustaqilligi. To'plam: 329 passed, 2 skipped (avval 322).

⚠️ **MIGRATSIYA YO'Q.** Deploy: `git pull` + `systemctl restart xenora`.
⚠️ Server `.env` ga `SENTRY_ALERT_CHAT_ID=` (BO'SH) qo'shiladi — ya'ni Sentry
Telegram xabari o'chiq. Qo'shilmasa ham standart bo'sh, xavfsiz tomonga
tushadi. Texnik xabar kerak bo'lsa alohida chat/guruh id kiritiladi.
⚠️ `ENFORCE_SUBSCRIPTION` va `SUBSCRIPTION_ALERTS_ENABLED` — o'zgarishsiz
(ikkalasi ham o'chiq).
Rollback: kod `34fbcd4` (v1.10.3).
Client `.exe`/`.apk` **kerak emas** (faqat backend).

## [1.10.3] — 2026-09-03 — obuna muddati haqida Telegram ogohlantirish

Mijoz ekranga qaramasa muddat tugayotganini bilmasdi: obuna bannerini faqat
ilovaga KIRGAN odam ko'radi, do'kon egasi bir hafta kirmasa muddat jimgina
tugardi va birinchi signal kassirning "nega ishlamayapti?" qo'ng'irog'i
bo'lardi. Endi bot xabar beradi.

**Kimga va qachon.** Super-admin kanaliga (`ALERT_CHAT_ID`) barcha tenantlar
bo'yicha besh bosqich: 7/3/1 kun qolganda, muddat tugagan kuni, muhlat tugab
bloklangan kuni. Do'kon egasiga (`cafes.telegram_chat_id`) faqat 7/3/1 kun —
"bloklandingiz" xabarini bot emas, odam aytgani ma'qul, qolaversa o'sha
paytda u allaqachon ilovada blok ekranini ko'radi. Qo'lda bloklangan
do'konga umuman xabar ketmaydi (super-admin buni ataylab qilgan).

Xabar namunasi:

    ⚠️ FAZZA PERFUM — obuna 7 kundan keyin tugaydi (17.09.2026)
    Tarif: Pro · 749 000 so'm/oy
    To'lov: +998 94 997 47 70

Narx va tarif nomi `core/subscription.py` dagi yagona manbadan olinadi.

**Takrorlanmaslik.** Yangi `subscription_alerts` jadvali,
UNIQUE(tenant_id, stage, expiry_date, audience). Kalitga MUDDAT SANASI
ataylab kiritilgan: obuna uzaytirilsa yangi tsikl o'z-o'zidan ochiladi va
hech qanday "flagni nollash" qadami kerak emas — `cafes` ga ustun qo'yilsa
aynan v1.10.2 da tuzatilgan `renew_subscription` tuzog'i qaytadan tug'ilardi.
Scheduler soatda ishlaydi, ya'ni kuniga 24 urinishdan ko'pi bilan bittasi
xabar bo'ladi.

**Bosqich `<=` bilan tanlanadi, `==` bilan emas.** Server bir kun o'chib
qolsa `days_left` 7 dan 2 ga sakraydi; `==` bo'lganda ogohlantirish butunlay
tushib qolardi. Endi eng shoshilinch mos bosqich yuboriladi.

**Yuborish sinxron.** Mavjud `send_alert` fon oqumida ishlaydi va natija
yo'qoladi. Bu yerda "yuborildi" bazaga yozilgani uchun belgilashdan oldin
haqiqatan yetganini bilish shart: aks holda Telegram o'chgan paytda xabar
"yuborilgan" deb yozilib, mijoz hech narsa olmasdan qolardi. Yuborilmasa
yozuv yozilmaydi va keyingi soatda qayta uriniladi.

**Super-admin panelida `telegram_chat_id` maydoni** ("Do'konni boshqarish"
modali). Egasi Telegram'da @userinfobot dan o'z id'sini oladi. ⚠️ Egasi
botimizga bir marta `/start` yozmasa, Telegram xabarni o'tkazmaydi — bot
birinchi bo'lib yoza olmaydi. Bo'sh qoldirish = o'chirish.

**Xavfsizlik:** xabarda parol/token/mijoz ma'lumoti yo'q — faqat do'kon nomi,
id (adminga), tarif, narx, sana, aloqa telefoni. Do'kon nomi `html.escape`
bilan qochiriladi (`parse_mode=HTML`, nomdagi `<` xabarni buzishi mumkin edi).
Telegram xatosi dasturni to'xtatmaydi: har tenant alohida `try` ichida.

27 ta yangi test (`backend/tests/test_subscription_alerts.py`). Jonli
mijozlarga xabar ketmasligi ikki qatlam bilan kafolatlangan. To'plam:
322 passed, 2 skipped (avval 295 — regressiya yo'q).

⚠️ **MIGRATSIYA BOR:** `d9e4f1a2b3c5` — `cafes.telegram_chat_id` +
`subscription_alerts` jadvali. Idempotent, downgrade bilan. Serverda prod
nusxasida mashq qilindi: upgrade → downgrade (ma'lumot yo'qolmadi) → upgrade.
Deploy: `git pull` + `venv/bin/alembic upgrade head` + `systemctl restart xenora`.
⚠️ **IKKALA KALIT HAM O'CHIQ:** `ENFORCE_SUBSCRIPTION=False` va
`SUBSCRIPTION_ALERTS_ENABLED=False` — hech kimga xabar ketmaydi, hech kim
bloklanmaydi. Ogohlantirishni yoqish alohida qaror.
Rollback: kod `51bfbc0` (v1.10.2) + `alembic downgrade c8b3e5d90a17`.
Client `.exe`/`.apk` **kerak emas** (backend + serverdan yuklanadigan panel).

## [1.10.2] — 2026-09-02 — obuna tizimi tuzatishlari

Obuna enforcement'ida to'rtta nuqson bor edi. Ular hozir zarar keltirmagan,
chunki `ENFORCE_SUBSCRIPTION` serverda **o'chiq**; lekin yoqilganda birinchi
muddati tugagan do'konda portlar edi.

**Scheduler endi `is_active` ga tegmaydi.** `tasks/scheduler.check_expired_tenants`
muddat tugagan tenantga `is_active = False` qo'yardi. Ammo bu maydon "do'kon
O'CHIRILGAN" degani (super-admin qo'lda amali), obuna holati emas — va u
`routers/auth.py` dagi `resolve-code` hamda `pin-login` filtrida qatnashadi.
Natijada obuna tugashi bilan kassir kirish ekranida do'konini umuman topa
olmasdi ("Do'kon topilmadi"). Endi faqat `tenant_status='expired'` belgisi
qo'yiladi, kirish yo'li ochiq qoladi.

**Kill-switch to'liq bo'ldi.** O'sha vazifa `ENFORCE_SUBSCRIPTION=False` bo'lsa
ham bazani o'zgartirardi — ya'ni "o'chirgich" yarim edi. Endi o'chiq bo'lsa
funksiya bazaga umuman tegmaydi.

**Muhlat (grace, 2 kun) endi haqiqatan ishlaydi.** Ikki sabab bilan o'lik edi:
scheduler muddat o'tishi bilan (≤1 soat) `expired` qo'yardi, va
`core/subscription.subscription_state` da `status == 'expired'` tekshiruvi
muhlat shoxidan OLDIN turib darhol qattiq blok qaytarardi. Endi SANA asosiy
manba, `expired` esa faqat belgi: ikkisi zid bo'lsa sana yutadi. Qo'lda
qo'yilgan bloklar (`is_active=False`, `tenant_status='blocked'`) sanadan
qat'iy nazar qattiq qoladi — aks holda "do'konni o'chirish" ma'nosini
yo'qotardi.

**Blok ekranida "Ma'lumotni yuklab olish" tugmasi.** Ma'lumot mijozniki —
obuna tugagani uni ma'lumotidan ayirmaydi. `/backups/my-tenant` ataylab
enforcement'siz edi (`get_current_active_user_no_sub`), ammo unga olib
boradigan tugma yo'q edi va boshqa sahifalar bloklangan foydalanuvchini shu
ekranga uloqtirgani uchun amalda unga yetib bo'lmasdi. Electron'da diskka,
brauzerda Yuklamalar papkasiga saqlaydi.

**`renew_subscription` do'konni to'liq tiklaydi.** Ilgari faqat sanani
uzaytirardi; `tenant_status` `expired` bo'lib qolar va to'lagan mijoz
bloklangan turaverardi. Endi `super_admin.add_payment` bilan bir xil holat
tiklanadi (status `active`, `blocked_at`/`blocked_reason` tozalanadi,
`is_active=True`).

23 ta yangi test qo'shildi (`backend/tests/test_subscription_enforcement.py`,
`test_subscription_login_path.py`), jumladan 5 ta jonli tenantning holati
o'zgarmasligini qotirib qo'yadigan GOLDEN tekshiruv. To'plam: 295 passed,
2 skipped (avval 272 — regressiya yo'q).

⚠️ **MIGRATSIYA YO'Q.** Deploy: `git pull` + `systemctl restart xenora`.
⚠️ `ENFORCE_SUBSCRIPTION` **FALSE bo'lib qoladi** — enforcement hali yoqilmaydi.
Rollback: kod `9735ac6` (v1.10.1).
Client `.exe`/`.apk` **kerak emas** (o'zgarish backend + serverdan yuklanadigan sahifa).

## [1.10.1] — 2026-09-01 — SHOSHILINCH: Sozlamalar sahifasi tuzatildi

🔴 **v1.10.0 da Sozlamalar sahifasi butunlay ishlamay qolgan edi.**
`app/settings.html:887` da bitta qo'shtirnoq ichida apostrof bor edi
(`'[TARIF] Noma'lum tarif:'`) — bu 840–1403 qatorlardagi BUTUN inline
skriptning parse bo'lishini to'xtatardi. Natijada `renderBtypes`,
`loadCafeInfo`, `loadPrinterSettings`, `loadStockGuard`, `detectPlanAndLock`
va boshqa hamma funksiya `undefined` bo'lardi: ombor qo'riqchisi toggle'i,
printer sozlamalari, tarif ko'rinishi — hech biri ishlamasdi.
Kiritgan commit: `03e49a8` (uch tarif), v1.10.0 bilan chiqqan.

Xuddi shu sinf xatosi `app/loyalty.html:288` da ham bor edi
(`.replace(/'/g,'\'')`) — sodiqlik sahifasi skripti ham parse bo'lmasdi.
Bu esa ANCHA eski (`b7e529c`).

Butun frontend (barcha `.js` fayllar + HTML ichidagi har bir `<script>` bloki)
`node --check` bilan skanerlandi — boshqa sintaksis xatosi yo'q. Skaner
`scripts/check_syntax.py` sifatida saqlandi va CI'ga qo'shildi.

**Brauzer rejimi ogohlantirishlari.** Brauzerdan (app.xenora.uz) kirilganda
Electron'ga bog'liq to'rt joy JIMGINA ishlamay qo'yardi; endi sabab aytiladi:
POS kassa yashigi (toast), POS tasmasi (sessiyada bir marta), printer ro'yxati
(ikkala sozlama sahifasida izoh), avtomatik zaxira (panelda ogohlantirish).
Tekshiruv `electronAPI.isElectron` ustidan — Electron'da hech narsa
o'zgarmaydi (Playwright bilan ikki rejimda sinaldi).

Login'dagi "Platforma administratori" tugmasining bosish maydoni 29px edi →
44px (iOS/Android tavsiyasi); ko'rinish o'zgarmadi.

⚠️ **MIGRATSIYA YO'Q.** Deploy: `git pull` + `systemctl restart xenora`.
Rollback: kod `30a011e` (v1.10.0) — lekin unda Sozlamalar sahifasi buzuq.
Client `.exe`/`.apk` **kerak emas** (sahifalar serverdan yuklanadi).

## [1.10.0] — 2026-09-01 — uch tarif tizimi

**Uch tarif: Boshlang'ich 249 000 / Standart 449 000 / Pro 749 000 (so'm/oy).
Filial limiti endi TEKSHIRILADI** (ilgari `max_branches` e'lon qilingan-u hech
qayerda tekshirilmasdi — "1 filial" va'dasi bo'sh gap edi; endi 402).

⚠️ **MIGRATSIYA YO'Q** (`subscription_plan` — `varchar(50)`, enum emas).
Deploy: `git pull` + `systemctl restart xenora`. Rollback: kod `227db30` (v1.9.9).

Frontend o'zgardi (`owner/*`, `app/cafes.html`, `app/settings.html`,
`js/core/plans.js`) — serverdan yuklanadi, yangi `.exe`/`.apk` **shart emas**.

Branch `feature/three-tier-plans`. **MIGRATSIYA YO'Q** (`subscription_plan` —
oddiy `varchar(50)`, PostgreSQL enum emas). Backend + frontend tegilgan →
`systemctl restart xenora`. Client `.exe`/`.apk` **kerak emas** (sahifalar
serverdan yuklanadi).

### PRINSIP
**Standart = kundalik ish. Pro = tahlil va avtomatlashtirish.**

| | Boshlang'ich (`free`) | Standart (`standart`) | Pro (`pro`) |
|---|---|---|---|
| Narx (UZS/oy) | 249 000 | 449 000 | 749 000 |
| Foydalanuvchi | 3 | 10 | 20 |
| Filial | 1 | 2 | 5 |
| Buyurtma/oy | 100 | cheksiz | cheksiz |

⚠️ **DB kodlari ATAYLAB o'zgarmadi** (`free`/`pro` qoldi) — 5 jonli tenantda
`'pro'` matni yozilgan; qayta nomlash ma'lumot migratsiyasi va eski tokenlar
oynasini talab qilardi. Ko'rinadigan nom kod bilan ajratilgan.

### Qo'shilgan
- **`standart` tarifi** — `PLAN_LIMITS`, `VALID_PLANS`, `PUBLIC_PLANS`.
- **`BUSINESS_STANDART_MATRIX`** — har biznes turi uchun Standart funksiyalari.
  ⚠️ U PRO to'plamining **kichik to'plami sifatida HISOBLANADI**, qo'lda
  yozilmaydi. Sabab: `pro = free|standart|pro` va `standart ⊆ pro` bo'lgani uchun
  natija `free|pro` ga teng — ya'ni **mavjud PRO mijozlar uchun AYNAN o'zgarmaydi**.
  Import paytida `assert` bilan qulflangan.
- **`GET /super-admin/plans`** — tarif katalogi (nom, narx, limitlar). Narxning
  yagona manbai; frontend shu yerdan o'qiydi.
- **`frontend/js/core/plans.js`** — nom xaritasi + narxni backenddan yuklash.
- **`is_within_branch_limit()`** va `branch.py` da **402** — filial limiti
  2026-08-27 gacha e'lon qilingan-u **hech qayerda tekshirilmasdi**.
- `backend/tests/test_three_tier_plans.py` — **64 test**.

### Tuzatilgan
- **`is_pro_plan()` IKKILIK edi** (`plan != "free"`) → **daraja (rank)** asosiga:
  free=0, standart=1, pro=2, enterprise=3. Tegilmasa `standart` avtomatik
  to'liq PRO bo'lib qolardi, ya'ni o'rta tarif bekorga.
  Xuddi shu ikkilik tekshiruv **yana ikki joyda** dublikat bo'lib yotgan edi va
  ikkalasi ham tuzatildi: `routers/cafe.py` (funksiya toggle API) va
  `frontend/app/settings.html` (mijozga ko'rinadigan toggle ekrani).
- **Noma'lum tarif JIMGINA `free` ga tushardi** (`get_plan_limits`). Endi
  `WARNING` yoziladi. Xavfi real edi: `"standard"` (imlo xatosi) yozilsa mijoz
  sababsiz 3 foydalanuvchi / 100 buyurtma limitiga tushib qolardi va hech kim
  sezmasdi. `plan_rank()` ham xuddi shunday ogohlantiradi.
- **Narx ikki ZID joyda** edi: `super_admin.py PLAN_PRICES` (USD: free=$10,
  pro=$50) va `owner/subscriptions.html` (UZS: free=0 "bepul"). Ya'ni moliya
  paneli Boshlang'ich mijozni pullik, mijoz ekrani bepul deb ko'rsatardi.
  Endi ikkalasi ham `core/subscription.PLAN_PRICES_UZS` dan o'qiydi.
- `/super-admin/stats` endi `VALID_PLANS` bo'yicha aylanadi (qattiq yozilgan
  ro'yxat o'rniga) — yangi tarif avtomatik statistikaga tushadi.

### Ko'rinadigan nom
`Boshlang'ich` / `Standart` / `Pro` — `owner/cafes.html`, `owner/dashboard.html`,
`owner/subscriptions.html`, `app/cafes.html`, `js/admin/settings.js`.
"LITE" va "bepul" yozuvlari olib tashlandi (Boshlang'ich endi pullik).

### Tasdiqlash kutilmoqda
`fitness` va `school` biznes turlarida PRO to'plamida faqat 2 ta tahlil flagi
bor, shuning uchun umumiy qoida bo'yicha Standart **hech narsa qo'shmasdi**.
Taklif: `peak_hours` shu ikki tur uchun Standart'ga tushirilsin (ular uchun bu
tahlil emas, smena rejalashtirish vositasi). Amalga oshirildi — tasdiqlashingiz
kerak.

## [1.9.9] — 2026-09-01 — foyda hisobi birlashtirildi, ombor qo'riqchisi, xarajat amortizatsiyasi

⚠️ **IKKI MIGRATSIYA** — deploy'da `alembic upgrade head` SHART:
`3f7a2c9e1b04` → `9c4e1a7b30df` (xarajat) → `c8b3e5d90a17` (ombor qo'riqchisi).
Rollback: kod `42e6fae` (v1.9.8), alembic `3f7a2c9e1b04`.

Frontend ham o'zgardi (`profit.html`, `settings.html`, `pos.js`, `admin.html`,
`report.html`) — ular serverdan yuklanadi, yangi `.exe`/`.apk` **shart emas**.

### Qo'shilgan — xarajatni kunlarga taqsimlash (amortizatsiya)

Fazza Parfum 22-avgustda ARENDA+ISHCHI+UJN = 5 800 000 kiritdi va uchalasi
BITTA kunga tushib, o'sha kun sof foydasi −5 268 070 bo'lib ko'rindi. Endi
`amortize_from`/`amortize_to` belgilangan xarajat kunlarga proporsional
taqsimlanadi (kümülativ — bir tiyin ham yo'qolmaydi/qo'shilmaydi).
`is_recurring` ATAYIN ishlatilmadi — u boshqa savolga javob beradi.
Davr = KALENDAR OY (takrorlanuvchi xarajatlar ustma-ust tushmasin);
`amortize_from` do'kon ochilgan sanadan oldinga o'tmaydi.
UI: checkbox + izoh, ro'yxatda 🗓 belgisi, karta ostida "bu davrga X (jami Y dan)",
ℹ️ tugmasi — foyda hisobi va to'lovlar reyestri farqi tushuntirilgan.

### Qo'shilgan — ombor qo'riqchisi (qoldiq tugasa sotilmaydi)

POS sotuvda ombor UMUMAN tekshirilmasdi: sotuv o'tar, ombor 0 da to'xtatilib
kamomad JIMGINA yo'qolardi. Fazza'da 15–31 avgustda 24 ta shunday sotuv
(297 dona). Endi `Cafe.block_oversell` yoqilgan bo'lsa `create_order` 400
qaytaradi. MAVJUD do'konlarga migratsiya FALSE yozadi (Fazza'da 98,
Eco Aroma'da 7 mahsulot qoldig'i 0 — bir kechada savdo to'xtamasin), YANGI
do'konlar TRUE bilan boshlaydi. Istisno: retseptli taom, ombor nazorati yo'q
xizmat, va INVENTARIZATSIYA davomida (sanoq tasdiqlangach o'zi qayta yoqiladi).

### Tuzatilgan — foyda 6 ekranda bir xil qoidada

Tan narx endi HAMMA JOYDA sotuv paytidagi `unit_cost` SNAPSHOT (`cost_expr`),
BUGUNGI `Product.cost_price` emas. Yangi yagona manba:
`utils/revenue.py:period_totals()`.

- `/analytics/store-dashboard` — 503 970 o'rniga 405 320 (Fazza 28-avg),
  endi boshqa ekranlar bilan mos; vozvrat ham ayiriladi
- `/analytics/store-margin`, `/analytics/abc-analysis` — snapshot tan narx.
  Jonli farq Fazza'da 4 931 570 so'm; sababi PACHKA sotuvlari: 100 ml BVLGARI
  flakoni 1 000 000 o'rniga 10 000 deb sanalardi (`pack_size` marta kam).
  ⚠️ Bu ekranlarda marja SEZILARLI tushadi — bu regressiya emas, soxta yuqori
  marja olib tashlandi. Eco Aroma'da farq 0 (pachka sotuvi yo'q).
- `/departments/report/sales` — ikki eski xato: daromadda chegirma
  ayirilmasdi (v1.9.0 tuzatishini olmagan) va tan narx `cost_price` edi.
  Jonli ta'sir 0 (department yozuvi yo'q), mina qoldirmaslik uchun tuzatildi.
- `/profit/summary` — status filtri `notin(cancelled)` → `completed`
  (PENDING endi daromad sanalmaydi; jonli ta'sir 0), kun chegarasi UTC →
  TOSHKENT (9 buyurtma kunini almashtiradi, DAVR JAMISI o'zgarmaydi).

YALPI ≠ SOF farqi SAQLANDI va yozildi: `/profit/summary` — SOF foyda
(xarajat ayirilgan), qolganlari YALPI. Har javobda `profit_kind`/`profit_label`.
UI yorliqlari chalg'ituvchi edi: admin KPI va report.html "Sof foyda" →
"Yalpi foyda". "Sof foyda" nomi endi faqat "Foyda tahlili" sahifasida.

### Tuzatilgan — boshqa

- `returns.py` `approved_at`: `utcnow()` (naive) → `datetime.now(timezone.utc)`.
  ⚠️ XATTI-HARAKAT O'ZGARMAYDI — jonli PostgreSQL'da tekshirildi, vozvrat sanasi
  to'g'ri edi. Bu sessiya zonasiga bog'liqlikni olib tashlash.
- `test_customer_return::test_vozvrat_QAYTARILGAN_sanaga_yoziladi` — test
  oynani mahalliy soatdan qurardi va Toshkent 00:00–05:00 da yiqilardi.
  Endi `approved_at` ning o'zidan quriladi.

## [1.9.8] — 2026-08-29 — firmalarga qo'lda qarz qo'shish

⚠️ **MIGRATSIYA BOR** (`3f7a2c9e1b04`) — deploy'da `alembic upgrade head` SHART,
keyin `systemctl restart xenora`.
Rollback nuqtalari: kod `e2d5fca` (v1.9.7), alembic `72d684a734c4`.

Frontend ham o'zgardi (`app/suppliers.html`) — u serverdan yuklanadi, shuning
uchun mijozlarga yangi `.exe`/`.apk` **shart emas**. Versiya fayllari baribir
sinxron ko'tarildi (SW keshi v1.52.0 → v1.53.0, Android versionCode 29 → 30).

### Qo'shilgan

- **Firmalarga QO'LDA QARZ qo'shish (priyomkasiz) — "Qarzlar" tabida.**
  Do'kon tovar hisobini yuritmasa ham nasiyani yozib borishi mumkin:
  *"Kerasys dan tovar oldim — 500 000"*. Ilgari qarzni oshirishning yagona
  yo'li tovarli nakladnoy kiritish edi, ya'ni ombor hisobini yuritish
  MAJBURIY bo'lardi. `opening_debt` esa bitta son — sanasi, izohi va tarixi
  yo'q, xato kiritilganini bekor qilib ham bo'lmasdi.

  Qarzlar tabida "+ Qarz qo'shish" tugmasi va har firma kartasida "➕ Qarz".
  Modalda: summa, sana, izoh + kiritilgan qarzlar jadvali (qoldiq bilan),
  tahrirlash va o'chirish. Oborot varag'ida alohida ✍️ "Qo'lda qarz" qatori.

  To'lov qilinganda FIFO uni ham hisobga oladi — eng eski qarzdan boshlab
  (nakladnoy va qo'lda qarz sana bo'yicha aralash tartibda). Ortiqcha to'lov
  avans bo'lib qoladi. Har amal audit logga yoziladi.

### Texnik

- Yangi jadval YARATILMADI: qo'lda qarz — "summasi bor, tovar qatorlari yo'q"
  priyomka (`purchase_receipts.is_manual_debt`). Iqtisodiy ma'noda bu aynan
  nasiyaga xarid, shuning uchun FIFO, oborot varag'i, muddat hisobi,
  `/debt-summary` va `/store-dashboard` o'z-o'zidan ishlaydi.
  **`compute_supplier_debt()` ga bitta qator ham qo'shilmadi** — mavjud qarz
  raqamlari o'zgarishi mumkin emas (golden test bilan qotirilgan).
- Marker ustun, TAXMIN emas. Dastlab "qatori yo'q priyomka = qo'lda qarz"
  qoidasi ishlatilgan edi va u mavjud testni buzdi: test fixture'i qatorsiz
  nakladnoy yaratadi va u jimgina "qo'lda qarz" bo'lib ko'rindi. Semantik
  xossani tasodifiy xossaga bog'lash — shu loyihada takrorlangan xato sinfi.
- Qo'riqchalar: tovarli nakladnoyga tegib bo'lmaydi; bog'langan to'lovi bor
  qarz o'chirilmaydi (aks holda to'lov FIFO orqali boshqa qarzga sirg'anardi);
  tenant izolyatsiyasi.
- Qo'lda qarz **Priyomkalar ro'yxatida ko'rinmaydi** — u nakladnoy emas
  (tovar qatori, invoice va ombor kirimi yo'q).
- `PurchaseReceiptCreate.items` endi `min_length=1` (bo'sh priyomka ma'nosiz).
- Testlar: `tests/test_manual_supplier_debt.py` — 19 ta (GOLDEN bloki mavjud
  mantiqni qotiradi), `test_supplier_debt.py` 37/37 buzilmadi.

### Ma'lum, TUZATILMAGAN (alohida ish sifatida qayd etildi)

- **Xarajat (Expense) yaratish/o'chirish audit logga YOZILMAYDI**
  (`routers/profit.py` da `log_audit` chaqiruvi yo'q). Shu sabab "Xodimlar
  faoliyati" panelida xarajat KO'RINMAYDI, garchi u pulga bevosita ta'sir
  qiladigan amal bo'lsa ham. Fazza Parfum tekshiruvida aniqlandi.
- **Vozvrat `approved_at` UTC'da yoziladi** (`routers/returns.py:406`
  `datetime.utcnow()`), hisobotlar esa Toshkent kunidan foydalanadi. Toshkent
  00:00–05:00 oralig'ida tasdiqlangan vozvrat KECHAgi hisobotga tushadi.

## [1.9.7] — 2026-08-29 — foyda hisobi tuzatishlari (Fazza tashxisi)

⚠️ **MIGRATSIYA YO'Q.** Deploy: `git pull` + `systemctl restart xenora`.
Rollback nuqtasi: kod `491bbe1` (v1.9.6).

**FAQAT BACKEND** o'zgardi (`routers/`, `services/`, `utils/`, `schemas.py`).
Frontendga TEGILMADI → yangi `.exe`/`.apk` **kerak emas**.

### Kelib chiqishi

Fazza Perfum (magazin) "bugun savdo qildik, foyda −4 489 080 ko'rsatyapti"
deb murojaat qildi. Jonli baza tekshirildi. Asosiy sabab kod emas, XATO
MA'LUMOT bo'lib chiqdi: `PCHYOLKA gupka` kartochkasida `pack_size = 7000`
(egasi dona soni o'rniga narx yozgan). Sotuv paytida
`order_service.py:280` uni tekshirmasdan `unit_cost = 700 × 7000 = 4 900 000`
qilib hisoblagan va 8 000 so'mlik bitta sotuvga 4,9 mln tan narx yozgan.
Ma'lumot alohida tuzatildi (kodda emas). Tekshiruv yo'lida esa quyidagi
TO'RT haqiqiy kod xatosi topildi va shu relizda tuzatildi.

### Tuzatilgan

- **Foyda hisobotida tan narx yo'qolardi** (`services/report_service.py`).
  `sum(OrderItem.quantity * OrderItem.unit_cost)` — `COALESCE` yo'q edi, ya'ni
  `unit_cost` NULL bo'lgan qator yig'indidan JIMGINA tushib qolardi (eski va
  import qilingan sotuvlar). Tan narx kam → foyda oshiq ko'rinardi. Vozvrat
  tomonida esa `COALESCE` BOR edi — assimetriya: sotuv tan narxi 0 deb
  olinardi, vozvrat tan narxi to'liq ayirilardi. Endi ikkala tomon ham
  `utils/revenue.py:cost_expr()` dan o'qiydi.

- **Vozvrat tan narxi `pack_size` marta shishardi** (`utils/revenue.py`).
  `COALESCE(base_qty, quantity) * unit_cost` ikki xil birlikni ko'paytirardi:
  `base_qty` — DONA/ml miqdori, `unit_cost` — PACHKA tan narxi. Atir uchun
  (`pack_size = 100`) bu 100 BAROBAR xato. U `cost` dan AYIRILGANI uchun
  foyda haddan tashqari OSHIB ketardi: bitta 1 mln lik flakon qaytarilsa
  hisobot 100 mln tan narx ayirib, ~99 mln soxta "foyda" ko'rsatardi.
  Yangi `return_cost_expr()` birlikni moslaydi: `unit_cost` bo'lsa
  `quantity` ga, `cost_price` ga tushsa `base_qty` ga ko'paytiriladi.
  Fazza va Eco Aroma'da tasdiqlangan vozvrat yo'q edi — xato hali
  portlamagan, oldi olindi.

- **"Bugun" hisoboti har doim 0 so'm chiqardi** (`routers/report.py`).
  `_dates()` ikkala chegarani ham 00:00 qilib qaytarardi, servislar esa
  `created_at <= date_to` bilan filtrlaydi → tugash kunining O'ZI qamralmasdi.
  `report.html` standart holatda `date_from = date_to = bugun` yuboradi, ya'ni
  POS "Hisobotlar → Foyda" sahifasi bo'sh ko'rinardi va buni hech kim xato deb
  o'ylamasdi ("bugun savdo yo'q ekan"). Endi mahalliy zonada to'liq kun
  oralig'i. Bu `/reports/sales`, `/products`, `/staff`, `/tax`, `/customers`
  va `/export` ga ham tegishli — ularda ham oxirgi kun qo'shildi.

- **"Bugun" davrida vozvrat hech qachon ayirilmasdi** (`routers/profit.py`).
  `returns_totals()` ga `date` obyekti uzatilardi; u TIMESTAMP ustuni bilan
  solishtirilganda kun 00:00 ga qisilardi. "Hafta"/"Oy" da esa oxirgi kun
  tushib qolardi.

### Qo'shilgan — himoya

- **`pack_size` qo'riqchisi** (`schemas.py`, 0…1000). Yuqoridagi hodisaning
  ildizi: 1 pachkadagi DONA SONI maydoniga hech qanday tekshiruvsiz NARX
  kiritilishi mumkin edi. Chegara "son"ni "narx"dan ajratadi — eng katta
  haqiqiy qiymatlar atir uchun 100 (ml) va 68 (dona), narx esa ming/o'n
  minglab.
  ⚠️ Qo'riqcha ATAYIN `ProductCreate`/`ProductUpdate` da, `ProductBase` da
  EMAS: `ProductInDB` ham `ProductBase` dan meros oladi va u BAZADAN
  O'QIShda ishlatiladi. Bazada buzuq yozuv qolgan bo'lsa, validator
  `ProductBase` da bo'lganida mahsulot ro'yxati 500 qaytarardi — ya'ni
  tuzatish do'konni ishdan chiqarardi. Qoida: KIRISHni tekshiramiz,
  mavjud ma'lumotni o'qishni bloklamaymiz.

### Testlar

`backend/tests/test_profit_p0_fixes.py` (19 tekshiruv) — har biri jonli
hodisadan kelib chiqqan, jumladan "mavjud buzuq yozuv o'qilishi kerak"
regressiya qulfi. To'liq to'plam: 135 passed, 2 skipped.

## [1.9.6] — 2026-08-27 — audit kuzatuv tuzatishlari

⚠️ **MIGRATSIYA BOR** (`72d684a734c4`) — deploy'da `alembic upgrade head` SHART,
keyin `systemctl restart xenora`.
Rollback nuqtalari: kod `07a52da`, alembic `a9b8c7d6e5f4`.

Frontend o'zgardi (`admin.html`, `js/admin/core.js`, `pos.html`), lekin ular
serverdan yuklanadi → mijozlarga yangi `.exe`/`.apk` **kerak emas**.

### Qo'shilgan — audit paneli
- **"Xodimlar faoliyati" paneliga IP va Qurilma ustunlari.** Avval IP hamma
  qatorda NULL bo'lgani uchun ko'rsatilmasdi; endi ma'lumot bor va panelning
  o'zidan buzilishni tekshirish mumkin. Qurilma `user_agent`dan sodda
  ko'rinishga aylantiriladi (to'liq satr — katak `title`ida):
  `Windows POS` (Electron `.exe`), `Android`, `iOS`, `Brauzer`, va
  **`Skript`** (curl/python/wget/okhttp/Postman) — qizil rangda, chunki bu
  odam emas. Eski yozuvlarda ikkalasi ham bo'sh chiziq ("—"), xato emas.

### Tuzatilgan

- **POS: "To'lov (F9)" yorlig'i noto'g'ri edi — aslida F4.** `pos.js:2839` da
  to'lov F4 ga bog'langan, F9 esa savatdan OXIRGI TOVARNI O'CHIRADI
  (`pos.js:2843`). Kassir yozuvga ishonib F9 bossa — pul olish o'rniga tovar
  savatdan yo'qolardi. **Kod emas, yozuv** to'g'rilandi (kassirlar mavjud
  yorliqlarga o'rganib qolgan bo'lishi mumkin). Barcha yorliqlar tekshirildi —
  boshqa nomuvofiqlik yo'q (Ctrl+K, F2, F3, F8 hammasi mos).
  ⚠️ F9 (savatdan o'chirish) hech qayerda **yozilmagan** — yashirin yorliq.

- **Audit jurnalida `ip_address` HAMMA qatorda NULL edi.** Ustun ham,
  `client_ip()` helper ham bor edi, lekin helper hech qayerda import
  qilinmagan va 18 ta `log_audit()` chaqiruvining birortasi `ip_address=`
  uzatmasdi. 2026-08-27 xavfsizlik tekshiruvida aynan shu ma'lumot kerak
  bo'ldi va yo'q edi. Endi IP + User-Agent `RequestIDMiddleware` orqali
  **avtomatik** yoziladi (ContextVar) — chaqiruv joylari tegilmadi, kelajakdagi
  yangi chaqiruvlar ham avtomatik oladi.

- **`X-Forwarded-For` ni birinchi bo'g'indan olish audit izini soxtalashtirishga
  ochiq edi.** nginx `$proxy_add_x_forwarded_for` ishlatadi — u mijoz yuborgan
  sarlavhaga haqiqiy IP ni *qo'shib qo'yadi*, ya'ni birinchi bo'g'in **mijoz
  nazoratida**. Endi tartib: `X-Real-IP` (nginx qayta yozadi → ishonchli) →
  XFF ning **oxirgi** bo'g'ini → `request.client.host`.

- **Test fixture buzilgan edi → `test_orders` va `test_products` JIMGINA skip
  bo'lardi** (API integratsiya testlari amalda yo'q edi). Uch sabab:
  (1) test bazasi urug'lantirilmasdi — ilovaning `init_db()` esa `SessionLocal`
  ni to'g'ridan-to'g'ri chaqirgani uchun `dependency_overrides` unga ta'sir
  qilmasdi; (2) fixture `username="admin"` bilan kirardi, holbuki login kaliti
  **telefon** (BOSQICH 38); (3) `test_auth.py` `pytest` ni import qilmasdan
  `pytest.skip` chaqirardi (NameError).

- **Testlar DEV BAZASIGA yozardi.** `init_db()` va `log_audit()` `SessionLocal`
  ni to'g'ridan-to'g'ri chaqiradi → har test yugurishi dev ma'lumotini
  o'zgartirardi. Endi conftest uni test bazasiga yo'naltiradi.

### Qo'shilgan
- `audit_logs.user_agent` ustuni (255) — IP o'zgaruvchan (NAT/mobil), UA esa
  qaysi ILOVA ekanini aytadi: Electron `.exe` / Capacitor APK / brauzer /
  `curl` (skript = shubhali). `/audit` javobiga ham qo'shildi.
- `backend/tests/test_audit_client_ip.py` — 14 ta test. Ulardan **ikkitasi
  uchdan-uchgacha**: haqiqiy login yuborib, `audit_logs` qatoriga IP tushganini
  va soxta XFF tushmaganini tekshiradi. (Birlik testlari asl xatoni tutmagan
  bo'lardi — muammo `client_ip()` da emas, uni hech kim chaqirmasligida edi.)

### Ma'lum cheklov
`test_create_order_*` testlari sqlite'da **skip** bo'ladi: kunlik chek raqami
`func.timezone('Asia/Tashkent', ...)` — PostgreSQL funksiyasi
(`order_service.py:38`), sqlite'da yo'q. Bu prod xatosi EMAS. Skip sababi endi
**aniq ko'rinadi** va test bazasi PostgreSQL'ga o'tkazilsa avtomatik yuguradi.

## [1.9.5] — 2026-08-27

🔴 **XAVFSIZLIK RELIZI.** Migratsiya YO'Q. Backend TEGILGAN — `systemctl restart xenora` SHART.

⚠️ **FAQAT BACKEND.** Frontend/Electron/Android tegilmagan — mijozlarga yangi `.exe`/`.apk`
**kerak emas**. Shu sababli faqat `backend/config.py` versiyasi ko'tarildi
(`electron/package.json`, `build.gradle`, `frontend/shared/version.js` — 1.9.4 da qoldi).

**Qisqacha:** Xavfsizlik — `/auth/register` endi autentifikatsiya talab qiladi;
`tenant_id` / `role_id` / `branch_id` server tomonda tekshiriladi.

### Tuzatilgan — KRITIK

- **`POST /api/v1/auth/register` orqali begona do'konni to'liq egallash mumkin edi.**
  Endpoint autentifikatsiyasiz ochiq edi va so'rov tanasidan `tenant_id` bilan
  `role_id` ni to'g'ridan-to'g'ri ishlatardi. Ya'ni internetdagi istalgan odam
  `{"phone":…, "password":…, "tenant_id": <begona>, "role_id": <admin>}` yuborib,
  boshqa mijozning do'koniga **admin** bo'lib qo'shila olardi va telefon+parol bilan
  kirardi (login do'kon kodini so'ramaydi). Rate limit (20/daq) to'siq emas edi.
  `is_superuser` berib bo'lmagani uchun platforma emas, **bitta tenant** to'liq
  egallanardi: sotuvlar, mijozlar, narxlar, hisobotlar.

  **Tekshiruv natijasi: bu teshikdan FOYDALANILMAGAN.** Prod bazadagi 9 ta
  foydalanuvchining hammasi ma'lum qonuniy yo'ldan yaratilgan (tenant adminlari —
  `create_tenant`, avto-email `admin<N>@restopos.uz`, `created_at` do'kon
  yaratilgan soniya bilan bir xil; kassirlar — xodim+PIN oqimi). nginx, backend
  va `journalctl` loglarida `/auth/register` ga **0 ta so'rov** (12.08–27.08;
  undan oldingi loglar server qayta qurilishida yo'qolgan). Audit jurnalidagi
  51 ta `LOGIN` — faqat 5 ta ma'lum foydalanuvchi.

  **Yechim** — yangi `backend/core/role_guard.py` (yagona tekshiruv joyi):
  - `manage_users` ruxsati majburiy → autentifikatsiyasiz **401**, ruxsatsiz **403**;
  - `tenant_id` tanadan **umuman olinmaydi** — server tokendan aniqlaydi
    (super-admin bundan mustasno, lekin unda ham kafe mavjud+faol bo'lishi tekshiriladi);
  - `role_id` yaratuvchining ruxsat darajasidan **oshib keta olmaydi**
    (masalan `menejer` `admin` rolini bera olmaydi);
  - `branch_id` faqat o'sha tenant'ning filiali bo'lishi mumkin;
  - tarif limiti `POST /users/` bilan izchil (FREE cheklovini chetlab o'tish yopildi).

- **Bir xil teshik `POST /users/` da ham qisman bor edi** — filial tekshiruvi yo'q edi;
  endi u ham `role_guard` dan foydalanadi (ikki endpoint bitta mantiq).
- **`PATCH /users/{id}` da rol/filial `setattr` bilan ko'r-ko'rona yozilardi** — rolni
  yangilash orqali imtiyoz oshirish yo'li ham yopildi.
- `/auth/register` da username unikalligi GLOBAL tekshirilardi → boshqa do'konda
  "admin" bor bo'lsa noto'g'ri "band" xatosi berardi. Endi tenant ichida (create/`/users/`
  bilan izchil).

### Qo'shilgan
- `backend/tests/test_register_privilege_escalation.py` — **12 ta xavfsizlik testi**:
  autentifikatsiyasiz/soxta token → 401, tenant sakrash, begona filial, rol ko'tarish
  (create ham, PATCH ham), ruxsatsiz rol. Regressiya kafolati sifatida "mavjud
  foydalanuvchi login qila oladi" va "pin-login buzilmagan" testlari ham bor.
- `docs/PRODUCT-AUDIT-2026-08.md` — to'liq mahsulot auditi (biznes to'siqlari,
  modul to'liqligi, tizim sifati, UX; ish hajmi baholari bilan).

### Ta'sir qilmaydi
Mavjud mijozlarning (Fazza Parfum, Eco Aroma, lux-parfum, qpa) **kirishiga ta'sir yo'q** —
`/auth/login` va `/auth/pin-login` tegilmagan, faqat YANGI hisob yaratish yopildi.
Yangi do'kon ochish yo'li ham o'zgarmadi: `POST /super-admin/tenants` (`owner/cafes.html`).
Frontend `/auth/register` ni hech qayerda chaqirmasdi (`auth.js:91` dagi `register()`
metodi o'lik kod edi) — UI o'zgarishi kerak emas.

## [1.9.4] — 2026-08-20

**Migratsiya YO'Q.** Backend TEGILGAN (nasiya kassa oqimi) — `systemctl restart xenora` SHART.

### Qo'shilgan
- **Domen: `https://xenora.uz`** (+ `www`) — Let's Encrypt SSL, WebSocket `wss://`,
  HTTP→HTTPS majburiy yo'naltirish va HSTS (`max-age=300`, sinov qiymati).
  Client manzili (frontend sahifalar, Electron `SERVER_URL`/`preload`) domenga o'tdi.
  ⚠️ **Eski `.exe`'lar `http://178.128.251.218` da ishlashda davom etadi** — nginx'da
  IP uchun alohida `default_server` bloki HTTP'da qoldirildi (sertifikat IP uchun
  yaroqsiz), CORS'ga domenlar IP yoniga QO'SHILDI, IP olib tashlanmadi.
- **ESLint qo'riqchisi** (`eslint.config.mjs`, `npm run lint`) — frontend JS uchun.

### Tuzatilgan
- ESLint topgan **3 sintaksis/o'lik kod** xatosi (`payments.js`, `promo.js`,
  o'lik `js/modules/admin.js` olib tashlandi).
- **6 sahifada `page_size` va API javob shartnomasi** — ulardan **3 tasi umuman
  ishlamasdi** (ro'yxat bo'sh kelardi). Bonus kartalar, Peresort, Ichki ko'chirish,
  Kombo, Mijozlar, Muddat nazorati.
- **Nasiya (qarz) to'lovi kassa hisobotida ko'rinmasdi** — Z-hisobot va dashboard
  pul oqimida qarz to'lovi endi hisobga olinadi (yagona manba `utils/cashflow.py`,
  golden testlar 12/12).

## [1.9.3] — 2026-08-19

Mijoz vozvrati to'liq tuzatildi (A–D bosqichlari). **Migratsiya YO'Q**, lekin
backend TEGILGAN — `systemctl restart xenora` SHART.

### Tuzatilgan
- **Mijoz vozvratida PUL HARAKATI umuman yo'q edi** — `approve` faqat omborni
  tiklardi va statusni o'zgartirardi, `refund_method` esa shunchaki yorliq bo'lib
  qolardi: naqd/karta qaytarishning hech qanday izi yozilmasdi, nasiyaga olgan
  mijozning QARZI ham kamaymasdi (tovar qaytdi — qarz qoldi). Endi naqd/karta
  mavjud `refund_payment()` orqali (manfiy Payment), nasiya esa qarzni kamaytiradi
  (avval shu buyurtmaning qarzi, keyin eng eski ochiqlari; qarzdan oshgani avans).
  `POST /payments/{id}/refund` bilan ikki marta ombor oshib ketmasligi uchun
  ikkala tomonga qo'riqchi qo'yildi.
- **Vozvrat foyda hisobotidan ayirilmasdi** — qaytarilgan tovar daromadda
  qolaverardi va foyda ko'tarilib ko'rinardi. Endi yagona manbadan
  (`utils/revenue.py`) ayiriladi — analytics, profit va report bir xil raqam
  beradi.
- **Almashtirish (exchange)** olib tashlandi: bu usulda pul harakati umuman
  bo'lmasdi (pul qaytmasdi, qarz kamaymasdi), lekin vozvrat "tasdiqlangan"
  bo'lib turaverardi. Endi UI'da yo'q va backend ham rad etadi.

### Yaxshilangan
- **Mahsulot va mijoz QIDIRUVI** — Vozvrat, Priyomka, Ombor kirimi, Nasiya va
  Narx siyosati oynalarida ro'yxat `page_size=500` bilan yuklanardi: 794 faol
  mahsulotli do'konda 294 tasi dropdownga UMUMAN tushmasdi va uni tanlab
  bo'lmasdi (mijozlarda ham xuddi shunday). Endi ro'yxat 1000 tagacha, undan
  oshgani esa nom/telefon bo'yicha SERVERDAN qidiriladi.

### Tozalangan
- **`/returns-ext` (kengaytirilgan vozvrat) o'chirildi** — u alohida jadval emas,
  o'sha `returns` jadvaliga `REXT...` raqami bilan yozardi, ammo pul harakatini
  QILMASDI va darhol "tasdiqlangan" qo'yardi. UI unga hech qachon ulanmagan edi.
  Jonli bazada bunday yozuv 0 ta — ma'lumot yo'qolmadi.
- Eskirgan funksiya-flag (`customer_return_ext`) barcha joydan olib tashlandi.
  Bazada qolgan eski flag endi ilovani buzmaydi: noma'lum kod e'tiborsiz
  qoldiriladi (ilgari bitta eskirgan yozuv o'sha do'konning butun funksiya
  hisoblashini yiqitardi).

## [1.9.2] — 2026-08-18

Migratsiya YO'Q. Faqat client-side (frontend + Electron) — backend tegilmagan.

### Tuzatilgan
- **Firmalar bo'limi (iframe) serverga ulanmasdi** — admin panelidagi "Firmalar"
  iframe orqali ochiladi, Electron'da esa `preload.js` sukut bo'yicha faqat asosiy
  freymda ishlaydi. Natijada iframe ichida server manzili topilmay, so'rovlar
  `localhost:8000` ga ketardi va har amal "Server bilan aloqa yo'q" berardi —
  holbuki POS, nasiya va qolgan hamma narsa ishlab turardi.
  Uch qatlamli tuzatish: server manzili ota freymdan ham olinadi; `file://` uchun
  `localhost` taxmini olib tashlandi; `nodeIntegrationInSubFrames` yoqildi.

⚠️ Bu tuzatish **yangi .exe** bilan yetadi (frontend ilova ichida ketadi).

## [1.9.1] — 2026-08-18

Uch branch birlashtirildi. **Migratsiya BOR** (3 ta, backup-first deploy).

### Tuzatilgan
- **Nasiya (credit) bilan sotuv umuman saqlanmasdi** — `paymentmethod` enumida
  `credit` yo'q edi (POS'da tugma bor, bazada qiymat yo'q) → har urinish 500 va
  butun sotuv rollback. Enumga `credit` va `room_charge` qo'shildi. Nasiya to'lovi
  endi `pending` holatda yoziladi: sotuv yakunlanadi (tovar chiqadi, hisobotga
  tushadi), lekin kelmagan pul daromadga KIRMAYDI va kassa qoldig'iga qo'shilmaydi.
- **Firma qo'shish va ro'yxati ishlamasdi** — sahifa xom javob kutardi
  (`res.id`/`res.items`), `api.js` esa o'ralgan javob qaytaradi. Muvaffaqiyatli
  qo'shilganda ham qizil "Xatolik" chiqardi, ro'yxat va dropdownlar bo'sh qolardi.
  Endi serverning xato matni TO'LIQ ko'rsatiladi.
- **To'lov o'chirilganda** nakladnoy `paid` bo'lib qolardi — endi holat qayta
  hisoblanadi (`confirmed` ga qaytadi).
- **Vozvrat ombor butunligi** — endi `StockMovement` yoziladi; vozvrat
  o'chirilganda tovar omborga qaytariladi (ilgari abadiy kamomad qolardi).

### Yangi — firma qarzi
- **Boshlang'ich qarz**: tizimga o'tishdan oldingi qarzni hujjatsiz kiritish
  (soxta priyomka yaratish shart emas).
- **Oborot varag'i**: bitta firma bo'yicha xronologik harakat va yugurib boruvchi
  qoldiq — agent bilan hisob-kitob ekrani.
- **Priyomkada "Hozir to'landi"**: nakladnoy bilan birga berilgan pul tasdiqlashda
  avtomatik to'lovga aylanadi (3 ekran → 1 ekran).
- Qarzi bor firmani arxivlashda ogohlantirish; to'lov va vozvrat `audit_log` ga
  yoziladi (kim, qachon, qancha).

### v1.9.0 dan meros (shu relizda ham)
- Chek: mahsulotlar ajratilgan, "miqdor × birlik narx" ko'rinishi
- POS: savatda son va narxni to'g'ridan-to'g'ri tahrirlash
- Tez sotuv paneli, dashboard bo'sh kartalari va timezone tuzatildi
- Mijozga nasiya yozish (admin panel) tuzatildi

### Migratsiyalar
`e7f8a9b0c1d2` (paymentmethod enum) → `d4e5f6a7b8c9` (suppliers.opening_debt) →
`a9b8c7d6e5f4` (purchase_receipts.paid_now). Hammasi idempotent, backfill yo'q.

## [1.9.0] — 2026-08-18

Olti branch birlashtirildi. **Migratsiya YO'Q.**

### Tuzatilgan xatolar (mijozda topilgan)
1. **Nasiya yozib bo'lmasdi** — `showAlert is not defined` (butun frontendda
   ta'riflanmagan funksiya, 12 chaqiruv). Tugma jim o'lardi: na xabar, na so'rov.
   Serverda 7 kun ichida bitta ham `POST /debts/` yo'q edi. → `toast()`.
   Yoniga: POS'da nasiya qarzi yozilmasa endi kassir aniq ogohlantirish oladi
   (ilgari `catch {}` jim yutar, baribir "Nasiya yozildi!" deyilardi).
2. **Firma qarzi: nakladnoysiz to'lov qarzni kamaytirmasdi** — `debt-summary`
   faqat `receipt_id` bor to'lovlarni sanardi, UI esa aynan "Umumiy to'lov"
   variantini taklif qilardi. Qarz endi yagona servisda (`supplier_debt.py`),
   bog'lanmagan pul FIFO bilan eng eski nakladnoydan taqsimlanadi.
   Direktor panelidagi ikkinchi (boshqacha) formula ham shu servisga o'tdi.
3. **Ombor kirimi firma qarzini jimgina yo'qotardi** — `supplier.balance` ga
   yozilardi, uni hech kim ko'rmasdi va hech narsa kamaytirmasdi. Endi yozilmaydi;
   do'konchi "qarz uchun Priyomka" deb ogohlantiriladi.
4. **Dashboard KPI kartalari va grafik BO'SH edi** — aware/naive `datetime`
   solishtiruvi endpointni 500 qilardi, frontend xatoni jim yutardi. Kunlar endi
   Toshkent sanasi bo'yicha guruhlanadi; "qolgan kun" bugunni sanamaydi.
5. **Chek qatorlari** — "11 x 5,000" (miqdor × birlik narx) + ajratuvchi;
   USB va LAN (ESC/POS) bir xil chiqadi.

### Yangi
6. **Savatda miqdorni qo'lda kiritish** — 20 dona uchun "+" ni 20 marta
   bosish shart emas.
7. **Savatda narx kelishuvi** — kassir qatordagi narxni tahrirlaydi; tushirilsa
   chegirma kanalidan ketadi, oshirilsa sotuv narxi sifatida hisoblanadi.
   Chekda kelishilgan narx ko'rinadi.
8. **Firmalar/Qarzlar ekrani** — jami banner (qarz qizil / avans yashil /
   muddati o'tgan sariq), avans endi "0" bo'lib yashirinmaydi, to'lovlar
   tarixida tur ("Nakladnoy #12" / "Umumiy to'lov") va kim kiritgani.
   Dublikat "Firmaga qarz" sahifasi olib tashlandi (yagona ekran).

### Testlar
pytest 34 passed (2 ta eski `test_auth` xatosi — bu relizdan oldin ham bor edi);
skript testlar: narx kelishuvi 53/53 va 20/20, daromad 15/15, timezone 8 ta,
firma qarzi 17 ta, inline onclick qo'riqchisi 3/3.

## [1.8.6] — 2026-08-14

Etiketka sahifasida mahsulotning yo'qolishi. Migratsiya YO'Q.
Faqat `frontend/app/labels.html` (bir endpoint) — backend TEGILMAGAN.

### Muammo
Mahsulot ombor va POS'da bor, etiketka sahifasida esa yo'q — qidiruvda ham
topilmaydi. Nom o'zgartirilsa ba'zan "tuzalardi".

### Sabab — uchta narsa birga
1. `labels.html` `GET /products/?page_size=500` — faqat **1-sahifa**
2. `product.py:71` — `order_by(Product.name)`, ya'ni **alifbo tartibida**
3. `labels.html` qidiruvi **frontendда** (`filterProducts`) — serverga bormaydi

Natija: alifboda 500-o'rindan keyingi mahsulot umuman yuklanmaydi, shuning
uchun qidiruvda ham topilmaydi. Nom o'zgarganda mahsulot alifboda birinchi
500 ichiga **ko'chib o'tardi** — shuning uchun "ba'zan tuzalardi".

Jonli ma'lumot (serverda o'lchandi):
| tenant | faol mahsulot | ko'rinmasdi |
|---|---|---|
| 26 FAZZA PERFUM | 663 | **163** |
| 20 eco aroma | 552 | **52** |

`TAROQ ORTA` alifboda 559-o'rinda, `VIVICN TAROQ` 622-o'rinda edi.

### Tuzatish
`labels.html` endi POS (`pos.js`) va ombor (`inventory.html`) BILAN AYNI
endpoint'ni ishlatadi: **`GET /products/all`** — paginatsiyasiz, limit 5000.

- Farqi: `/products/all` faqat `is_active` VA `is_available` mahsulotlarni
  qaytaradi. Etiketka uchun to'g'ri — sotuvda bo'lmagan tovarga narx
  etiketkasi bosilmaydi. **Yo'qotish yo'q**: bazada `is_active=true` va
  `is_available=false` bo'lgan mahsulot **0 ta** (barcha tenantda).
- 5000 chegarasiga yetilsa endi **ogohlantirish** ko'rsatiladi — jimgina
  kesib tashlamaydi (aynan shu jimlik xatoni oylab sezdirmagan edi).

### Sinov (serverda, endpoint so'rovi aynan takrorlandi)
- tenant 26: eski **500** → yangi **664** mahsulot
- `TAROQ ORTA` (559) va `VIVICN TAROQ` (622) — endi **yuklanadi** ✅
- hech bir tenant 5000 chegarasiga yaqin emas

### Qolgan ish (shoshilinch emas)
`page_size=500` yana 6 sahifada bor va katta katalogda xuddi shu muammoni
beradi: `combo.html`, `expiry.html`, `goods_regrade.html`,
`internal_transfers.html`, `customers.html`, `bonus_cards.html`.

## [1.8.5] — 2026-08-13

Klaviatura o'limining ikkinchi qatlami. Migratsiya YO'Q. Faqat `electron/main.js`.

### Yangi fakt: bu ESKI xato, etiketka faqat uni ko'rsatdi
Mijoz aniqladi — muammo etiketka printeridan OLDIN ham bor edi: Eco Aroma'da
**mahsulot o'chirgandan** keyin aynan shunday bo'lardi. v1.8.4 dan keyingi
holat: **kursor CHIQADI, lekin YOZIB BO'LMAYDI**.

### Sabab: fokusning IKKI qatlami bor
| qatlam | nima qiladi | v1.8.4 tuzatdimi |
|---|---|---|
| Chromium ichidagi holat | kursorni chizadi | ✅ `focusOnWebView()` |
| Windows klaviatura yo'nalishi (qaysi HWND `WM_KEYDOWN` oladi) | belgilarni yetkazadi | ❌ |

Native dialog (`confirm`/`alert`/`prompt`) yoki tashqi jarayon yopilgach,
Windows fokusi o'sha o'lgan oynada qolib ketadi. `focusOnWebView()` sof
Chromium chaqiruvi — Windows qatlamiga tegmaydi. Shuning uchun kursor
qaytdi-yu, klavishlar kelmadi. **Alt+Tab tuzatadi** (do'konda tasdiqlandi),
chunki u haqiqiy OS fokus sikli.

### Tuzatish — Alt+Tab ni avtomatlashtirish
- `_focusCycle()`: `blur()` → 60ms → `focus()` + `focusOnWebView()`, ya'ni
  HAQIQIY OS sikli. `_cycling` bayrog'i qayta kirishni bloklaydi (blur/focus
  o'zlari hodisa uyg'otadi → himoyasiz cheksiz sikl bo'lardi).
- **Trigger — "oyna fokusni yo'qotib, qaytib oldi"**: native dialog ochilganda
  ham, tashqi jarayon ishlaganda ham AYNAN shu bo'ladi. Ya'ni triggerni
  qidirish shart emas, va yangi sabab qo'shilsa ham avtomat qamraladi.
- `restoreAppFocus()` (chop etishdan keyin) ham shu siklni ishlatadi.

**Sinovda tasdiqlangan:** tashqi oyna fokusni oldi → yopildi → sikl **1 marta**
ishga tushdi → klaviatura tirik; +6s da sikllar soni oshmadi (cheksizlik yo'q);
`activeElement` saqlandi (kassir bosgan input fokusda qoladi).

### Rad etilgan (kod tahlili — sizning gipotezalaringiz)
Barcha 12 ta global klaviatura ushlovchisi tekshirildi — **hech biri oddiy
belgilarni to'smaydi**:
- `shortcuts.js:56` — `preventDefault()` faqat ro'yxatdagi kombinatsiyalar
  uchun (F1/F5/Esc/Alt+harf/Ctrl+K/Ctrl+F); yakka harf mos kelmaydi.
- `pos.js:3111` (skaner wedge) — `activeElement` INPUT/TEXTAREA/SELECT bo'lsa
  darrov chiqadi; "tez yozishni skaner deb o'ylash" mumkin emas (≥4 belgi +
  600ms + Enter talab qiladi, va faqat inputdan tashqarida).
- `modal.js:25`, `core.js:239`, `admin.html:4084`, `camera-scanner.js:163`,
  `inventory.html:576,580` — faqat `Escape`/`Enter`/`F2`.

### ⚠️ Tuzatilmagan, alohida ish sifatida qoldi
- **96 ta native dialog chaqiruvi** (`confirm`/`alert`/`prompt`) — ildiz sabab.
  Ilova ichidagi modallarga almashtirilsa trigger butunlay yo'qoladi.
  Eng ko'p: `core.js` (8), `cafes.html` (6), `pos.js` (6), `inventory.js` (4).
- **`modal.js:25` listener leak** — har `new Modal()` `document` ga keydown
  qo'shadi, hech qachon olib tashlamaydi. Faqat `Escape` ni ushlaydi, shuning
  uchun zararsiz, lekin to'planadi.

## [1.8.4] — 2026-08-13

Klaviatura fokusi xatosining HAQIQIY tuzatishi (v1.8.3 ishlamagan edi).
Migratsiya YO'Q. Faqat Electron (`main.js`, `preload.js`).

### v1.8.3 nega ishlamadi — o'lchov bilan
Buzuq holatni laboratoriyada qayta yaratib (`blurWebView()`), har bir tiklash
usuli `document.hasFocus()` bilan o'lchandi:

| Usul | Natija |
|---|---|
| buzuq holat | `false` |
| `win.focus()` + `wc.focus()` — **v1.8.3** | `false` ← **ishlamadi** |
| `app.focus({steal:true})` | `false` |
| `win.blur()` → `win.focus()` | `true` (lekin fullscreen'da miltillaydi) |
| **`win.focusOnWebView()`** | **`true`** ← tanlandi |

Sabab: buzuq holatda `win.isFocused()` ham, `wc.isFocused()` ham `true`
qaytaradi — oyna O'ZINI fokusda deb biladi. Shuning uchun `focus()` NO-OP:
Windows oyna allaqachon foreground bo'lgani uchun `WM_SETFOCUS` yubormaydi.
Buzuq bo'lgan narsa — webview'ning klaviatura fokusi, va uni tiklaydigan
yagona chaqiruv `focusOnWebView()`.

### Tuzatish
- **`preload.js` — asosiy himoya, SABABGA BOG'LIQ EMAS:** `pointerdown`
  (capture) da `document.hasFocus()` tekshiriladi; `false` bo'lsa main'ga
  `xenora:repair-focus` yuboriladi. Fokusni nima o'ldirgan bo'lsa ham,
  kassirning **keyingi bosishi** tiklaydi — u muammoni sezmaydi ham.
  Hodisa to'xtatilmaydi/o'zgartirilmaydi, mavjud bosish mantiqiga ta'sir yo'q.
  Preload har sahifada ishlaydi → 87 frontend fayliga tegilmadi.
- **`main.js`:** `restoreAppFocus()` endi `focusOnWebView()` ishlatadi;
  `mainWindow.on('focus')` ham (kassir Alt+Tab bilan qaytgan holat).
- **Tasdiqlangan:** buzuq → v1.8.3 usuli hamon o'lik → bosish TIKLADI →
  yozish ishladi; takroran 2/2.

### ⚠️ v1.8.3 dagi tashxis NOTO'G'RI edi (yozib qo'yildi)
"PowerShell foreground'ni tortadi" degan taxmin **o'lchov bilan rad etildi**:
haqiqiy `raw-print.js` orqali haqiqiy XP-365B navbatiga TSPL baytlar yuborilib
(fullscreen oyna), fokus **umuman yo'qolmadi** (`ok:true`, 260 bayt).
`windowsHide: true` tufayli konsol oynasi yaratilmaydi, foreground o'zgarmaydi.
Shuningdek rad etilgan: yashirin oyna sizishi (chek oynasi `close()` bilan
3/3 `isDestroyed:true`), `getPrintersAsync()`, pos.js keyboard-wedge va
`labels.html` dagi `disabled`/`blur` (sahifa almashuvi yangi hujjat yaratadi —
renderer holati omon qolmaydi).
**Do'kondagi fokusni nima o'ldirgani hamon noma'lum** — shu sabab tuzatish
sababni emas, HOLATNI tuzatadi.

## [1.8.3] — 2026-08-13

Shoshilinch tuzatish: etiketka bosgandan keyin klaviatura o'lib qolardi.
Migratsiya YO'Q. Faqat Electron (`electron/main.js`) — backend TEGILMAGAN.

### Etiketka chop etilgandan keyin hech qayerga yozib bo'lmasdi (mijozda)
- **Muammo:** etiketka bosilgach ilovada barcha matn maydonlari javob bermay
  qolardi (mahsulot qo'shish, ombor, qidiruv). Sichqoncha ishlardi, klaviatura
  yo'q. Sahifa almashtirish yordam bermasdi — faqat ilovani qayta ochish.
- **Sabab:** oyna fokusi (Windows) va `webContents` fokusi (Chromium) — ikki
  alohida holat. RAW chop etish uchun ishga tushadigan PowerShell jarayoni
  qisqa vaqt foreground'ni oladi; u tugagach Windows oynani fokusga qaytaradi,
  lekin Chromium'ning ichki "fokusdagi webContents" holati eskirib qoladi.
  Natija: oyna fokusda ko'rinadi, klaviatura esa hech qayerga bormaydi. Holat
  oyna darajasida bo'lgani uchun sahifa almashtirish ham tozalamasdi.
- **Tuzatish (ikki qatlam):**
  1. `mainWindow.on('focus')` → `webContents.focus()` — **umumiy to'r**: oyna
     fokus olgan har safar Chromium fokusi ham tiklanadi. Bu printerdan qat'i
     nazar ishlaydi (etiketka USB/LAN, A4 `window.print`, Windows dialoglari).
  2. `restoreAppFocus()` — `label_usb` chop etish tugagach fokusni darrov
     qaytaradi (~200ms da bir marta takrorlanadi, Windows kechikishiga qarshi).
- **PowerShell oynasi:** `raw-print.js` da `windowsHide: true` **allaqachon bor
  edi** — ko'rinadigan oyna sabab EMAS. Fayl umuman o'zgartirilmadi.
- **Regressiya:** chek yo'llari (`usbTransport`/SumatraPDF, `lanTransport`) va
  `labelLanTransport` **bayt-ma-bayt o'zgarmagan** — diffda bor-yo'g'i 1 satr
  o'chgan, u ham `labelUsbTransport` ichida.

## [1.8.2] — 2026-08-13

Shoshilinch tuzatish: etiketka sahifasi ochilmasdi. Migratsiya YO'Q.

### Etiketka sahifasi ishga tushmasdi (mijozda)
- **Muammo:** `labels.html` da "Yuklanmoqda..." qotib qolardi, tugmalar bosilmasdi.
- **Sabab:** `import { getToken } from '../js/core/auth.js'` — auth.js bunday nom
  **eksport qilmaydi**. ES modulda mavjud bo'lmagan nomni import qilish LINK
  xatosi: **modul umuman bajarilmaydi** → `window.*` handlerlar tayinlanmaydi
  (tugmalar o'lik), `loadProducts()` chaqirilmaydi (placeholder qotadi).
  Xato 2026-07-24 (`d732a43`) dan beri bor edi, sahifa yashirin turgani uchun
  sezilmagan; v1.8.0 da menyuda ochilgach yuzaga chiqdi.
- **Tuzatish:** loyihadagi izchil usul — `localStorage.getItem('access_token')`.
- `returns.html` da ayni shu xato bor edi — u ham tuzatildi.
- Xato ishlovi: `loadLabelConfig` va `loadProducts` endi 401/403/server xatosini
  **ko'rinadigan** qilib aytadi (ilgari jim qaytardi).

### ⚠️ Ma'lum, hali tuzatilmagan (keyingi reliz)
- `bonus_cards.html`, `markirovka.html`, `markup_policy.html`, `promotions.html`
  — `../js/core/toast.js` faylini import qiladi, **u fayl yo'q** → ayni shu
  sabab bilan bu 4 sahifa ham ochilmaydi. (`error-handler.js` da `showToast` bor.)
- ~~`js/modules/admin.js` — 7 ta import mavjud bo'lmagan papkalarga (o'lik kod).~~
  **TOZALANDI (2026-08-19):** fayl o'chirildi va service-worker keshlash
  ro'yxatidan olib tashlandi. Uni hech bir sahifa yuklamasdi; jonli admin kodi
  — `js/admin/*.js`.
- `labels.html` JsBarcode'ni CDN'dan yuklaydi — do'konda internet bo'lmasa
  A4 rejimida barcode chizilmaydi (TSPL rejimiga ta'siri yo'q).

## [1.8.1] — 2026-08-13

Chek footer kesilishi tuzatildi. Migratsiya YO'Q.

### Chek (LAN) — kesishdan oldingi feed
- **Muammo (jonli, XP-N160II):** chek pastidagi "Xaridingiz uchun rahmat!"
  pichoq chizig'iga tushib **yarim kesilardi**.
- **Sabab:** termal printerda pichoq bosma kalladan ~20–30mm PASTDA. Oxirgi
  bosilgan qator kallada qolib ketadi va `CUT` darrov yuborilsa pichoq aynan
  o'sha matnni kesadi. `CMD.FEED` atigi 3 qator (~10mm) edi.
- **Tuzatish:** `CMD.FEED_BEFORE_CUT` (8 × LF, ~28mm). `CMD.FEED` 3 qatorligicha
  qoldi (umumiy maqsad uchun).
- **Doira:** FAQAT LAN yo'li (`escpos-builder.js` → `lanTransport`).
  USB/SumatraPDF yo'li HTML→PDF orqali ishlaydi va bu faylga tegmaydi —
  `main.js` bu relizda **umuman ochilmadi** (5/5 transport sha256 bir xil).

## [1.8.0] — 2026-08-13

ETIKETKA PRINTERI relizi. **Migratsiya YO'Q** (sozlama TenantSettings JSON'da).
Chek printeri yo'llari (usb/lan/qr) **TEGILMADI** — sha256 bilan tasdiqlangan.

### Etiketka printeri (TSPL) — yangi
- **`electron/tspl-builder.js`** — TSPL yadro (40×30mm, 203 dpi = 320×240 nuqta).
  Kirill→lotin translitiratsiya, qo'shtirnoq ekranlash, EAN-13/CODE128 avto-tanlov.
- **USB** (`label_usb`) — `electron/raw-print.js`: Windows RAW spooler
  (PowerShell → `winspool.drv` P/Invoke, datatype `RAW`). **Native addon YO'Q**.
  ⚠️ `Add-Type -TypeDefinition` (C#) rad etildi — `csc.exe` sovuq startda 30s+
  ketardi va timeout berardi; `Reflection.Emit` bilan 1.5–5s.
- **LAN** (`label_lan`) — TCP 9100, `lan-socket.js` qayta ishlatildi.
- Ulanish turi sozlamada: `connection_type` = `usb` | `lan`.
- **`labels.html`**: TSPL va A4 **ikki rejim** (A4 = mavjud `window.print()` yo'li,
  o'zgarmadi), har mahsulotga alohida **son 1–999**, 40×30mm o'lcham qo'shildi,
  sahifa menyuda ochildi.

### Jonli qurilmada sozlangan (Xprinter XP-365B)
- Nom **kesilmaydi**: avto-shrift + 2 qator (`FIT_SAFETY`) — firmware shrifti
  nominal jadvaldan keng ekani aniqlandi.
- Mazmun **vertikal markazda** (`V_SAFETY`) — balandlik ham nominal jadvaldan katta.
- Barcode 62 → 88 nuqta (~11mm), ostidagi raqam shrift 1 → 2.
  ⚠️ Barcode KENGLIGI oshirilmadi: EAN-13 = 95 modul × narrow, `narrow=3` → 303
  nuqta, bosiladigan chekka esa <286 — kafolatli kesilardi.

### Ichki EAN-13 generatsiya (parfumeriya uchun)
- `_gen_internal_barcode` AI-Ombor'dan **`core/barcode.py`** ga ko'chirildi
  (AI-Ombor xulqi bayt-ma-bayt o'zgarmadi).
- Yangi: `POST /products/{id}/generate-barcode?force=` va
  `POST /products/generate-barcodes` (to'plam, bitta tranzaksiya).
- `labels.html`: "Kod berish" / "Barchasiga kod berish"; barcode'siz mahsulot
  chop etishga qo'shilmaydi (ilgari soxta kod bosilardi).
- O'lik `utils/helpers.py:generate_barcode()` **o'chirildi** (0 chaqiruvchi,
  unikallikni tekshirmasdi).

### Build
- `tspl-builder.js` va `raw-print.js` electron-builder `files` ro'yxatiga
  qo'shildi. ⚠️ Bu ANIQ ro'yxat — yangi lokal `require` qo'shsangiz shu yerga
  ham yozing, aks holda `.exe` startup'da "Cannot find module" bilan yiqiladi.

## [1.7.0] — 2026-08-12

Server ko'chirish relizi + v1.4–v1.6 branchlarini birlashtirish. **Migratsiya YO'Q** (head `b9c8d7e6f5a4`).

### Server almashdi (KRITIK — build SHART)
- Eski droplet `146.190.225.168` **yo'q qilingan**. Yangi server **`178.128.251.218`** (`xenora-2pos`)
  noldan qurildi, 22.07.2026 zaxirasidan tiklandi (4 tenant, 559 mahsulot, eco aroma 555).
- **`window.XENORA_SERVER`** (72 frontend HTML, Capacitor/APK yo'li) va Electron
  `SERVER_URL`/`XENORA_SERVER` yangi IP ga o'tkazildi (`2a821f6`).
  ⚠️ **Eski .exe/.apk ishlamaydi** — ular yo'q qilingan serverga urinadi. Qayta build SHART.
- `SECRET_KEY` yangi → barcha eski JWT/refresh token bekor, qurilmalar qayta login qiladi.
- Deploy tafsiloti: `DEPLOY.md` §11.

### Versiya birlashtirildi
- Repo aralash holatda edi (backend/android `1.4.0`, electron/frontend `1.6.0`) — hammasi **1.7.0** ga
  keltirildi: `config.py`, `version.js`, `login.html`, `electron/package.json`,
  `build.gradle` (versionName `1.7.0`, versionCode **21**), SW `v1.43.0`.

### Oldingi birlashtirilgan branchlar (1.4.0–1.6.0 oralig'i, alohida yozilmagan edi)
- `feature/lan-printer`, `feature/local-receipt`, `feature/camera-scanner`, `feature/responsive-mobile`
- v1.6.0 integratsiyasi: seller-switch, POS aksiya, modifikator admin, hotel formalari,
  bog'liqlik xavfsizligi (Pillow 10.4.0, python-multipart 0.0.18).

## [1.3.0] — 2026-07-21

Katta reliz: chek 54mm + QR toggle, atir maydalash, POS tarix/ombor, grafik ramka. **Migratsiya YO'Q**.

### Chek
- **Kenglik 54mm** (`receipt-print.js`) — 58mm rolikда o'ng tomon **kesilmaydi** (narx to'liq).
- **QR/fiskal toggle** (`order.py /orders/{id}/receipt`) — QR/fiskal blok faqat `qr_enabled` (Chek
  sozlamalari toggle, soliq integratsiyasi) YOQIQ bo'lsa chiqadi. **Default O'CHIQ** (ko'p do'kon).

### Atir maydalab sotish (#20)
- **POS:** pachka/dona mexanizmi ml uchun — "🧴 Butun (150 ml) 250 000" / "ml 2 000/ml"; ml → "necha ml?"
  (weight modal). Savat/chek yorliqlari: "Butun (150 ml)" / "10 ml". Ombor ml base (flakon −150, ml −N).
- **Admin forma:** `sale_unit="ml"` endi pack maydonlarini bloklamaydi (`_wUnits`dan ml olib tashlandi) —
  atir yaratса bo'ladi. Migratsiya YO'Q (mavjud pack_size/pack_price/price).

### POS (#21/#22/#23)
- **Sotuvlar tarixi + reprint:** sidebar "Sotuvlar tarixi" → bugungi sotuvlar (kassir → o'ziники,
  admin → barchasi; RBAC `cashier_id`). Detal + 🖨 reprint (buildReceipt58 + PDF/SumatraPDF).
- **Ombor qoldig'i:** sidebar "Qoldiq" → mahsulot + sotuv narxi + qoldiq. Yangi `GET /inventory/pos-stock`
  — **TANNARX/ombor qiymati faqat `view_finance` (admin)**; kassir ko'rmaydi. Tenant/branch izolyatsiya.

### Dashboard
- **Sotuv dinamikasi grafik** (`admin.css`) — SVG konteyner ICHIDA qoladi (o'ng "To'lov usullari"
  kartasига tegmaydi). Faqat CSS (grafik funksiyasi tegilmadi).

## [1.2.9] — 2026-07-20

Chek PDF → SumatraPDF raster print (Chrome kabi). **Migratsiya YO'Q** (kod).

### Tuzatildi
- **Chek krakozyabra (yakuniy hal):** oldingi yo'llar (RAW, HTML GDI, capturePage) termal
  drayverda krakozyabra berardi. Chrome Ctrl+P toza chiqardi (PDF/raster). Endi XENORA ham
  AYNAN shunday: `webContents.printToPDF()` (Chromium PDF engine, @page 58mm) → PDF →
  **SumatraPDF** `-print-to -silent -print-settings fit` bilan LOKAL printerga raster print.
  PDF'da matn baytlari yo'q → drayver CP437 talqin qilolmaydi → krakozyabra IMKONSIZ.
  SumatraPDF topilmasa → `webContents.print` (GDI) fallback.

### Texnik
- `electron/main.js`: printToPDF + SumatraPDF (`execFile`); did-finish-load + deviceName omit saqlandi.
- `electron/vendor/SumatraPDF.exe` (20MB, git'da yo'q — `.gitignore`; build mashinasida lokal).
  `extraResources` uni `resources/SumatraPDF.exe` ga nusxalaydi.
- Auto-print (to'lovdan keyin 1×) va reprint shu PDF yo'lini ishlatadi (pos.js tegilmadi).

## [1.2.8] — 2026-07-20

Chek RASTER (rasm) print — krakozyabra ildizdan hal. **Migratsiya YO'Q** (kod).

### Tuzatildi
- **Chek matni buzuq (krakozyabra):** Chrome bilan XP-58C toza chiqardi, XENORA esa CP437 krakozyabra.
  Sabab: `webContents.print` (silent, preview'siz) kontentni rasterga aylantirmay GDI matn/vektor
  yuborardi; XP-58C termal drayveri buni o'z codepage'ida (CP437) talqin qilib buzardi. Yechim
  (`electron/main.js`): chek endi **RASM (raster)** qilib bosiladi — `capturePage()` → PNG → 58mm
  `<img>` bitmap print. Printer sof rasm oladi, matn yo'q → krakozyabra fizik jihatdan imkonsiz
  (Chrome ham raster yuboradi — shu sababли toza). capturePage ishlamasa → HTML fallback.
- `list-printers`: `isDefault` doim boolean; `displayName` fallback.

### Texnik
- did-finish-load kutish + pageSize yo'q + deviceName omit (bo'sh→OS default XP-58C) saqlandi.
- POS chek oqimida RAW ESC/POS umuman yo'q (electron faqat webContents.print + capturePage raster).

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
