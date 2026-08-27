# XENORA — MAHSULOT AUDITI (2026-08-27)

**Versiya:** 1.9.4 · **Backend:** ~38k qator Python (207 fayl, 74 router) · **Frontend:** ~57k qator (51 app sahifa + admin SPA ~90 bo'lim)
**Audit turi:** faqat o'qish. Hech narsa o'zgartirilmadi.

---

## 0. BIR QARASHDA

| | |
|---|---|
| **Texnik yetuklik** | Yuqori. Funksional qamrov keng, sotuv oqimi atomik, tenant izolyatsiya asosan mustahkam. |
| **Biznes tayyorligi** | **Past.** Mijoz o'zi kelib sotib ololmaydi — sayt sotmaydi, ro'yxatdan o'tish yo'q, to'lov yo'q. |
| **Asosiy xulosa** | Mahsulot tayyor, **kanal tayyor emas**. Eng katta xavf — kod emas, sotish zanjiri. |
| **Kritik xavfsizlik** | 1 ta 🔴 — `/auth/register` orqali begona do'konni egallash mumkin. |

---

## 1. YANGI MIJOZ YO'LI 🔴 — ENG KUCHSIZ BO'G'IN

| # | Savol | Holat | Topilma |
|---|---|---|---|
| a | Sayt CTA qayerga olib boradi? | 🔴 **Uzilgan** | `index.html:64` → `shared/login.html?register=true`. `login.html` da `register` parametri **umuman ishlanmaydi** (0 ta moslik). Mijoz login ekraniga tushadi va qamalib qoladi. `index.html:97` "Bepul sinab ko'rish" → oddiy `login.html`. |
| a2 | Sayt bo'limlari | 🔴 | Menyu `#pricing`, `#demo`, `#contact`, `#api`, `#help`, `#docs` ga havola qiladi — **bu bo'limlar mavjud emas** (faqat `#features` bor). Saytda **narx yo'q, telefon yo'q, demo yo'q, .exe/.apk yuklab olish yo'q**. |
| b | Self-signup API | 🔴 **Yo'q** | `POST /auth/register` faqat `User` yaratadi, `Cafe` (tenant) yaratmaydi. Ro'yxatdan o'tgan odam bo'sh, tenantsiz akkaunt oladi — POS ishlamaydi. |
| c | Tenant qanday yaratiladi? | 🟠 **Qo'lda** | `POST /super-admin/tenants` — faqat `is_superuser`. UI: `owner/cafes.html`. Egasi qo'lda nom, biznes turi, telefon, tarif, admin username/parol kiritadi → `access_code` (100.200.N) + parol qaytadi va **mijozga qo'lda yetkaziladi**. ~2-3 daqiqa/mijoz + aloqa vaqti. Kod, parol, ilova havolasi — hammasi qo'lda. |
| d | Demo tenant | 🔴 **Yo'q** | Demo/seed skript yo'q (`backend/scripts/` da faqat `cleanup_deleted_barcodes.py`). Odam mahsulotni mustaqil ko'ra olmaydi — faqat siz ekran ulashsangiz. |
| e | Trial mexanizmi | 🟠 **Yarim** | Backend to'liq: `trial_days` → `tenant_status='trial'` + `trial_expires`, `subscription_state()` uni hisoblaydi. UI da maydon bor (`cafes.html:208`), lekin **standart qiymat 0** = sinov yo'q. Avtomatik trial berish oqimi yo'q. |

**Amaldagi zanjir:** Flayer → sayt → **tugma ishlamaydi** → mijoz telefon qiladi → siz qo'lda tenant ochasiz → kod/parolni qo'lda berasiz → ilovani qo'lda yuborasiz.

---

## 2. OBUNA VA TO'LOV

| # | Savol | Holat | Topilma |
|---|---|---|---|
| a | `ENFORCE_SUBSCRIPTION` | 🟠 **O'CHIQ** | `config.py:71` → `False` (kill-switch). Yoqilsa: `deps.py:_enforce_subscription` 227+ endpointda ishlaydi, muddati o'tgan tenant `403 {code: SUBSCRIPTION_EXPIRED}` oladi, frontend `subscription-blocked.html` ga o'tadi. Super-admin va `tenant_id=None` hech qachon bloklanmaydi. Grace = 2 kun. **Hozir hech kim to'lamasa ham ishlayveradi.** |
| b | Muddat qayerda? | ✅ | `Cafe.subscription_expires` / `trial_expires` / `tenant_status` / `is_active` / `blocked_reason`. Yagona haqiqat manbai — `core/subscription.py:subscription_state()`; enforcement ham, UI ham, super-admin paneli ham shuni ishlatadi (kelishmovchilik yo'q). Holatlar: `active/expiring/grace/expired/blocked/inactive`. |
| c | Click / Payme | 🔴 **YO'Q** | `payment_service.py:64` → `# TODO: Click/Payme API integratsiyasi`. Faqat `status="pending"` yozadi. `config.py:131-138` da `CLICK_*`/`PAYME_*` — bo'sh joy egallovchi. **Webhook / callback endpoint yo'q** (routerlarda 0 ta moslik). Bu ikki darajada zarar: (1) mijoz sizga obuna to'lay olmaydi, (2) kassada Click/Payme tugmasi bosilsa pul tasdiqlanmaydi. |
| d | Tarif modeli | ✅ | `PLAN_LIMITS`: free (3 user / 1 filial / 100 buyurtma-oy), pro (20 / 5 / cheksiz), enterprise (cheksiz). `VALID_PLANS = free, pro, enterprise`. **Narx (so'm) modeli yo'q** — `TenantPayment.amount` qo'lda kiritiladi. |
| e | Mijoz to'lovni ko'radimi? | 🟡 **Qisman** | `GET /cafes/my/subscription` bor (bloklangan tenant ham chaqira oladi) + `subscription-banner.js` avtomatik banner. Lekin banner `error-handler.js` orqali kiradi — u **51 ta app sahifadan 32 tasida** ulangan. To'lov tarixini mijoz ko'rmaydi (faqat super-admin). |

---

## 3. FISKAL / OFD

| # | Savol | Holat | Topilma |
|---|---|---|---|
| a | `ofd_service.py` tayyorligi | 🟠 **~70%** | 281 qator. `mock` + `live` rejim; ikki operator (`soliq.uz`, `SoliqPro`) uchun to'liq payload+parser; QR `consumer.invoice.uz/check` formatida; sozlama tenant-scoped (`settings/fiscal` — INN/kassa_id/api_key/endpoint); `Order.fiscal_number/fiscal_qr_url/fiscal_sent_at` ustunlari bor; test endpoint `POST /settings/fiscal/test`. |
| a2 | Nima yetishmaydi? | 🟠 | **1)** Real operator bilan hech qachon sinalmagan — QQS 12% va `Units: 796` (dona) **hardcode**, SPIC kodi `"0"`. Har mahsulotning haqiqiy SPIC/IKPU kodi va birligi kerak (soliq talabi). **2)** Xato bo'lsa faqat `log.warning` — **qayta yuborish navbati yo'q** (`payment.py:229`), OFD tushib qolsa chek yo'qoladi. **3)** Qaytarish (refund) OFD ga **umuman yuborilmaydi** — `send_to_ofd` butun kodda faqat 1 joyda chaqiriladi. **4)** Smena ochish/yopish (X/Z) OFD ga bormaydi. |
| b | Kimga majburiy? | — | O'zbekistonda naqd/karta bilan chakana savdo qiluvchilar (do'kon, kafe, dorixona, xizmat) uchun onlayn-NKM/virtual kassa majburiy — ya'ni **deyarli barcha maqsadli mijozingiz uchun**. Fiskalsiz mijoz sizni rasman ishlata olmaydi, faqat "ichki hisob" sifatida. |
| c | Ishga tushirish uchun aniq nima kerak? | — | (1) Operator tanlash + shartnoma/API kalit; (2) mahsulotga SPIC/IKPU + birlik + QQS stavkasi ustunlari; (3) retry navbati (`fiscal_sent_at IS NULL` bo'yicha cron); (4) refund fiskali; (5) real kassa bilan sinov. |

---

## 4. MAHSULOT TO'LIQLIGI

| Modul | Holat | Izoh |
|---|---|---|
| **POS (sotuv)** | ✅ **TO'LIQ** | Atomik sotuv (bitta tranzaksiya, TOCTOU qulfi, deadlock-safe), offline navbat + sync, hold/reopen, barkod, tarozi, chegirma, tarix/reprint, F-tugmalar. |
| **Ombor** | ✅ **TO'LIQ** | 19 endpoint: kirim/chiqim, retsept bo'yicha yechim (idempotent), partiya, muddat, inventarizatsiya, ichki ko'chirish, qayta saralash, hisobdan chiqarish, AI-ombor (rasmdan o'qish). |
| **Mijozlar** | ✅ TO'LIQ | CRUD, tarix, sodiqlik, bonus karta, foto. |
| **Nasiya (qarz)** | ✅ TO'LIQ | `credit` tender `pending` bo'lib qoladi → daromadga kirmaydi; `debt_payments` orqali kassa oqimi. Testlar bor. |
| **Firmalar (suppliers)** | ✅ TO'LIQ | Qarz, to'lov, qaytarish, kirim hujjati. 37 ta test — eng yaxshi qoplangan modul. |
| **Hisobotlar** | ✅ TO'LIQ | 27 analytics + 11 report + 9 profit endpoint; ABC, aylanma, peak-hours, marja, o'lik tovar, Z-hisobot. |
| **Xodimlar** | ✅ TO'LIQ | Rol, PIN, davomat, oylik, jadval, audit log, xodim ovqati. |
| **Smena / kassa** | ✅ TO'LIQ | Ochish/yopish, kutilgan naqd, Z-hisobot + chop etish, kassa apparati ro'yxati. |
| **Restoran** | ✅ TO'LIQ | Stol (birlashtirish), ofitsiant, oshxona KDS (1-bosish tayyor, timer, stansiya), modifikator, stop-list, kurs. |
| **Mehmonxona** | 🟠 **QISMAN** | Xona + bron CRUD (9 endpoint) + admin SPA'da 7 bo'lim. Yo'q: night audit, folio/xona hisobiga yozish avtomatikasi, mavsumiy tarif, ko'p mehmon. |
| **Filial** | 🟠 QISMAN | Model + `branch_id` hamma joyda + filial almashtirish tokeni bor. Filiallararo konsolidatsiyalangan hisobot va markazlashgan narx boshqaruvi cheklangan. |
| **Promo / bonus** | ✅ TO'LIQ | `buy_x_get_y`, flash narx, min summa, min miqdor, happy hour, kombo, kunlik taklif, sodiqlik darajalari, bonus karta. `routers/promo.py` o'lik (uzilgan, `/discounts` ishlatiladi). |
| **Etiketka** | ✅ TO'LIQ | `labels.html` + barkod generatsiya + chop etish. |
| **Chek** | ✅ TO'LIQ | 54mm/80mm, QR toggle, ESC/POS + Electron PDF→SumatraPDF raster (kirill muammosi hal). |
| **Skaner** | ✅ TO'LIQ | USB (klaviatura), kamera 2 qatlam: Capacitor ML Kit (APK) + `BarcodeDetector` fallback. ⚠️ ML Kit native tomon faqat haqiqiy APK buildda sinaladi. |
| **Ko'p valyuta** | 🔴 **YO'Q** | Faqat UZS. `formatter.js:4` da `currency='UZS'` standart; `Cafe`/`Product` da valyuta ustuni yo'q, kurs modeli yo'q. |
| **Ko'p til** | 🔴 **YO'Q** | i18n kutubxonasi yo'q, lug'at fayli yo'q. Barcha matn HTML/JS ichida qattiq o'zbekcha. Rus tilidagi mijoz (Toshkent bozorining katta qismi) uchun to'siq. |
| **Qurilmalar (printer/tarozi ro'yxati)** | 🔴 **SKELET** | `routers/device.py` — `_devices_store` **oddiy Python ro'yxati xotirada**. Server qayta ishga tushsa ro'yxat yo'qoladi, DB da saqlanmaydi. |

---

## 5. TIZIM SIFATI

| # | Savol | Holat | Topilma |
|---|---|---|---|
| a | Test qamrovi | 🟠 **Yupqa** | **100 test / 96 o'tdi / 3 yiqildi / 7 skip** (2m39s). Yiqilganlar: `test_auth.py::test_login_success` (401≠200), `test_auth.py::test_me_authenticated` (`NameError: pytest` — import yo'q), `test_customer_return.py::test_vozvrat_QAYTARILGAN_sanaga_yoziladi`. **Muhim:** auth fixture buzilgani uchun `test_orders`/`test_products` **skip bo'ladi** — API integratsiya testlari amalda ishlamayapti. Qolgani asosan sof mantiq testlari (supplier_debt 37, customer_return 15). **Tenant izolyatsiya testi yo'q. Obuna enforcement testi yo'q.** Frontend: 10 ta `.mjs` smoke-test. |
| b | Foydalanuvchi xatoni ko'radimi? | 🟡 Qisman | `ErrorHandlingMiddleware` + `error-handler.js` (global catch, offline banner, obuna banneri) + 46 faylda toast. **Ammo `error-handler.js` 51 ta app sahifadan faqat 32 tasida ulangan** — 19 sahifada global xato jim yutiladi. OFD xatosi kassirga **umuman ko'rinmaydi** (faqat log). |
| c | Sekin joylar | 🟠 | **N+1:** `analytics.py` da halqa ichida `db.query(Product).filter(Product.id==...)` — 1202, 1269, 1388, 1402-qatorlar (dashboard va reorder alerts har yuklanishda mahsulot soniga teng so'rov). Jami 21 ta shunday chaqiruv. **Indeks:** modelda atigi 3 ta kompozit indeks (`ix_orders_tenant_created`, `ix_orders_tenant_status`, `ix_products_tenant_category`). PostgreSQL FK ustunga avtomatik indeks **yaratmaydi** → `order_items.order_id`, `payments.order_id`, `inventory.product_id` indekssiz. 35 ta jadvalda `created_at` bor, faqat 3 tasi indeksli. `Inventory` da `(tenant_id, branch_id, product_id)` unikal cheklovi yo'q → dublikat qoldiq xavfi. |
| c2 | Masshtab | 🟠 | Deploy **1 worker** (WebSocket in-process broadcast ko'p workerni buzadi). Rate limit ham in-memory. Ya'ni hozircha gorizontal kengaytirish **imkonsiz** — bitta jarayon shifti. |
| d | Tenant izolyatsiya | 🟠 **Asosan, lekin teshik bor** | `apply_tenant_filter` 74 routerdan 62 tasida. Qolgan 12 tadan 10 tasi qonuniy (auth, super_admin, upload — tenant bucket, settings/staff_meal — `resolve_tenant_id` bilan qo'lda). **Ammo:** begona obyektga havola tekshirilmaydi — masalan `staff_meal.py:35,39` `Employee`/`Product` ni faqat `id` bo'yicha oladi. Client tomon: logout IndexedDB+localStorage tozalaydi. |
| d2 | 🔴 **KRITIK** | 🔴 | **`POST /api/v1/auth/register` ochiq (autentifikatsiyasiz) va tanada `tenant_id` + `role_id` ni qabul qiladi** (`auth.py:49`, `schemas.py:21-23`, `auth_service.py:83-85`). Har qanday odam internetdan `{"phone":…, "password":…, "tenant_id": 5, "role_id": <admin>}` yuborib, **begona do'konning to'liq admini** bo'lib oladi va telefon+parol bilan kiradi (login do'kon kodini talab qilmaydi). Rate limit 20/daqiqa — to'siq emas. `is_superuser` berilmaydi, shuning uchun platforma emas, **bitta tenant to'liq egallanadi**. |
| e | Ma'lumot yo'qolishi | 🟡 | **Yaxshi:** `scripts/backup.py` mustaqil pg_dump+media cron; tenant-level backup/restore (`/backups/my-tenant`) tranzaksiyali; Electron kunda 2× lokal nusxa; offline navbat IndexedDB da (dequeue faqat muvaffaqiyatdan keyin). **Xavfli:** `device.py` xotirada (restartda yo'qoladi); OFD cheki yuborilmasa qayta urinilmaydi; `OrderItemModifier`/og'irlik hech qachon yozilmaydi (per-satr detal `biz_meta` JSON workaround'ida). |
| e2 | Sirlar | ✅ | `SECRET_KEY` production'da zaif bo'lsa ishga tushmaydi (`config.py:163`), `.env` gitignore'da, super-admin login `.env` dan. |

---

## 6. FOYDALANUVCHI TAJRIBASI

| # | Savol | Holat | Topilma |
|---|---|---|---|
| a | Kassir necha daqiqada o'rganadi? | ✅ ~10-15 daq | POS oqimi sodda: qidir/skanerla → savat → F4 to'lov. Mobil savat FAB, katta tugmalar, sensor rejim, beep. |
| b | Ko'p bosiladigan tugmalar qulaymi? | ✅ Qulay | Barkod maydoni doim fokusda, chegirma/mijoz/hold ko'rinadigan joyda, sensor uchun CSS optimallashtirilgan. |
| b2 | 🟠 **F-tugma nomuvofiqligi** | 🟠 | `pos.html:825` tugmada **"To'lov (F9)"** yozilgan, lekin `pos.js:2839` da to'lov **F4**, `pos.js:2843` da **F9 = savatdan oxirgi mahsulotni o'chirish**. Kassir yozuvga ishonib F9 bossa — pul olish o'rniga tovar o'chadi. Real kassa xatosi manbai. |
| b3 | O'lik kod | 🟡 | `frontend/js/shortcuts.js` (F1 yordam, Alt+D/P/K, F2/F3/F4/F9/F12) **hech bir sahifaga ulanmagan** — faqat `footer.html` va `owner/dashboard.html` da eslatiladi. E'lon qilingan qisqa yo'llarning katta qismi ishlamaydi. |
| c | Undo bormi? | 🟡 Qisman | Savatda F9 (oxirgi qatorni olib tashlash). To'lovdan keyin — `returns` moduli (yaratish/tasdiqlash/rad etish, RBAC bilan, ombor qaytadi). Lekin bu 3-4 bosishli **rasmiy qaytarish**, tez "bekor qilish" emas. Smena yopilgach tuzatib bo'lmaydi. |
| d | Yordam / qo'llanma | 🔴 **Yo'q** | `docs/` da faqat 3 ta ichki ROADMAP fayli. Foydalanuvchi qo'llanmasi yo'q, ilova ichida yordam ekrani yo'q (F1 ulanmagan), video yo'q, saytda `#help`/`#docs` bo'sh havola. Har savol sizga telefon qiladi. |

---

## 🔴 BIZNESGA TO'SIQ (mijoz olishga to'g'ridan-to'g'ri xalaqit beradi)

| # | Muammo | Ish hajmi |
|---|---|---|
| **R1** | **`/auth/register` orqali begona do'konni egallash.** `tenant_id`/`role_id` ni tanadan qabul qilmaslik (yoki endpointni butunlay yopish + flag ostiga olish). Bitta mijoz ma'lumoti sizib chiqsa biznes tugaydi. | **2 soat** |
| **R2** | **Sayt sotmaydi.** Narx bo'limi, aloqa (telefon/Telegram), demo, .exe/.apk yuklab olish, skrinshotlar — hech biri yo'q; menyu havolalari bo'sh joyga olib boradi. | **1.5 kun** |
| **R3** | **"Ro'yxatdan o'tish" tugmasi hech narsa qilmaydi.** Minimal: tugmani "Ariza qoldirish" formasiga burish (ism+telefon+biznes turi → Telegram/DB). To'liq: self-signup + avtomatik tenant + 14 kunlik trial. | **Minimal: 1 kun**<br>**To'liq: 4-5 kun** |
| **R4** | **Demo yo'q.** Doimiy demo tenant + seed skript (namuna mahsulot/buyurtma/hisobot) + saytda "Demo'ni ochish" tugmasi. Sotuvdagi eng arzon konversiya vositasi. | **1.5 kun** |
| **R5** | **To'lov qabul qilib bo'lmaydi.** Obuna uchun Click/Payme merchant + webhook + `TenantPayment` avtomatik yozuv + muddat uzaytirish. (Boshlanishi uchun qo'lda o'tkazma + super-admin paneli yetadi, lekin masshtabga to'siq.) | **4-6 kun** |
| **R6** | **Fiskal ishlamaydi (real).** Rasmiy ishlaydigan mijoz uchun majburiy. SPIC/IKPU ustunlari + retry navbati + refund fiskali + real operator sinovi. | **5-7 kun** |

---

## 🟠 MUHIM

| # | Muammo | Ish hajmi |
|---|---|---|
| **O1** | **F9 yorlig'i noto'g'ri** (tugma "To'lov (F9)" — aslida F9 tovarni o'chiradi). Kassada pul xatosi manbai. | **15 daqiqa** |
| **O2** | **3 ta test yiqilgan + auth fixture buzilgan** → `test_orders`/`test_products` skip. Regressiya to'ri amalda ochiq. | **3 soat** |
| **O3** | **`ENFORCE_SUBSCRIPTION` o'chiq.** Pul olishning texnik asosi tayyor-u, ishlamayapti. Yoqishdan oldin: barcha jonli tenantga muddat qo'yish + 2-3 hafta ogohlantirish banneri. | **0.5 kun** (+ nazorat) |
| **O4** | **`error-handler.js` 19 sahifada ulanmagan** — xato ham, obuna banneri ham ko'rinmaydi. | **3 soat** |
| **O5** | **`device.py` xotirada** — printer/tarozi ro'yxati restartda yo'qoladi. DB jadvaliga ko'chirish. | **4 soat** |
| **O6** | **OFD retry navbati yo'q** — operator tushsa chek jim yo'qoladi (yoqilganda soliq muammosi). | **1 kun** |
| **O7** | **Indekslar:** `order_items.order_id`, `payments.order_id`, `inventory.product_id`, `payments(tenant_id, created_at)` + `Inventory` unikal cheklovi. Baza o'sganda hisobotlar sekinlashadi. | **0.5 kun** |
| **O8** | **N+1 (analytics dashboard).** Halqa ichidagi `Product` so'rovlarini bitta `IN (…)` bilan almashtirish. | **0.5 kun** |
| **O9** | **Foydalanuvchi qo'llanmasi yo'q.** Kamida: 1 sahifalik kassir varaqasi + 5 daqiqalik video + admin PDF. Har mijozning har savoli — sizga telefon. | **2 kun** |
| **O10** | **1 worker cheklovi** — WebSocket in-process. 20-30 dan ortiq faol do'konda muammo bo'ladi (Redis pub/sub kerak). | **2-3 kun** (keyinroq) |

---

## 🟡 YAXSHILASH

| # | Muammo | Ish hajmi |
|---|---|---|
| **Y1** | **Rus tili yo'q** — bozorning katta qismi. i18n qatlami + lug'at. | 4-6 kun |
| **Y2** | Ko'p valyuta yo'q (faqat UZS). Hozirgi bozor uchun shart emas. | 3 kun |
| **Y3** | `shortcuts.js` o'lik kod — ulash yoki o'chirish. | 2 soat |
| **Y4** | Begona obyektga havola tekshiruvi (`staff_meal` va shunga o'xshash joylarda `Employee`/`Product` ni tenant bilan olish). | 1 kun |
| **Y5** | Mijoz o'z to'lov tarixini ko'rmaydi (faqat super-admin). | 0.5 kun |
| **Y6** | Mehmonxona: night audit, folio, mavsumiy tarif. | 4-5 kun |
| **Y7** | Trial standart 0 → yangi tenantga avtomatik 14 kun. | 2 soat |
| **Y8** | Tenant izolyatsiya + obuna enforcement uchun avtomatik testlar. | 2 kun |
| **Y9** | Modifikator/og'irlikni `OrderItem` ga to'g'ri saqlash (hozir `biz_meta` JSON workaround). Pul yo'liga tegadi — ehtiyot. | 3 kun |
| **Y10** | Pydantic V1 `class Config` deprecation (57 ogohlantirish). | 0.5 kun |

---

## TAVSIYA ETILGAN TARTIB

| Bosqich | Nima | Muddat | Natija |
|---|---|---|---|
| **0 — Darhol** | R1, O1, O2 | **1 kun** | Xavfsizlik teshigi yopiq, kassa xatosi yo'q, testlar yashil |
| **1 — Sotuv kanali** | R2, R3 (minimal), R4 | **4 kun** | Sayt mijoz oladi: narx + demo + ariza + yuklab olish |
| **2 — Pul** | O3, R5 | **5-7 kun** | Obuna majburiy + onlayn to'lov |
| **3 — Rasmiylik** | R6 | **5-7 kun** | Fiskal ishlaydi → yirik mijozlar ochiladi |
| **4 — Barqarorlik** | O4-O8, O9 | **5 kun** | Qo'llab-quvvatlash yuki tushadi |
| **5 — Kengayish** | Y1, R3 (to'liq), O10 | **10-12 kun** | Rus tili, self-service, masshtab |

**Jami 0-3 bosqich ≈ 15-19 ish kuni** — shundan keyin mahsulot o'zini o'zi sotadigan va o'zini o'zi to'laydigan holatga o'tadi.
