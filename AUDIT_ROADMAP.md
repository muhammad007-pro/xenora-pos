# XENORA — Audit va Tuzatish Rejasi

**Oxirgi yangilanish:** 2026-07-28
**Sana:** 2026-07-22
**Qamrov:** To'liq loyiha (~90 000 qator, 68 funksiya, 499 endpoint, 68 router)
**Usul:** Read-only audit (grep/kod tekshiruvi) — kod o'zgartirilmadi
**Holat eslatmasi:** Audit `main` branch'da bajarildi (`release/v1.5.0-security` emas)

## ⚠️ 0. JONLI PRODUKSIYA — MA'LUMOT XAVFSIZLIGI (eng ustuvor qoida)

**MUHIM:** "Eco Aroma" parfumeriya do'konida XENORA v1.4.0 JONLI ishlayapti (tenant #20) — real savdo, real ma'lumot. Bu ma'lumot HECH QACHON yo'qolmasligi kerak.

**Joriy holat (2026-07-22):** Server DB butun (555 mahsulot, bugungi savdo). Qo'lda off-site nusxa olindi (DB + media → egasining kompyuteri). LEKIN doimiy off-site avto-backup hali YO'Q, mijoz backup 401'da to'xtagan.

Har qanday tuzatiш/deploy paytida MAJBURIY qoidalar:
1. HAR deploy'dan OLDIN to'liq pg_dump backup olinadi va OFF-SITE nusxa tekshiriladi.
2. Destruktiv migratsiya (drop column/table) — avval alohida tasdiq, avval test nusxada sinov, keyin production.
3. Migratsiya doim orqaga qaytariladigan (downgrade) va idempotent bo'lsin.
4. Deploy tor vaqtda (do'kon yopiq/kam yuk) qilinadi — smena o'rtasida emas.
5. Har deploy'dan keyin browser-test: savdo, to'lov, ombor ishlayaptimi.
6. Shubha bo'lsa — TO'XTA va so'ra, ma'lumot xavfida taxmin qilma.

Bu qoida butun rejaning eng yuqori ustuvorligi — funksiya/daromaddan ham oldin ma'lumot butunligi.

## 1. Umumiy baho

Poydevor professional darajada: 78% funksiya to'liq, tenant izolyatsiya mustahkam, SQL injection yo'q, xato boshqaruvi puxta, backup intizomi bor. Asosiy bo'shliqlar — daromad enforcement, HTTPS, off-site backup, operatsion yetuklik va masshtab.

**3 ta bosh xavf:**
1. HTTPS yo'q → parol/JWT token ochiq matnda tarmoqda (jonli xavf)
2. Billing himoyasiz → hozir hech kim to'lashga majbur emas
3. Off-site backup yo'q → server yiqilsa ma'lumot + backup birga yo'qoladi

## 2. Bosqichma-bosqich topilmalar

### 0. Struktura
~320 fayl / ~90k qator. Backend 68 router + 19 servis. Frontend 65 JS modul. Platformalar: web (PWA), Electron, Android (Capacitor), src-tauri (noaniq). Sirlar git'da YO'Q. Kichik tozalik: ildizda keraksiz .txt/skript fayllar.

### 1. Funksiya to'liqligi — 53 to'liq / 7 qisman / 1 chala / 7 o'lik
- CHALA: Online to'lov (Click/Payme) — stub, "pending"da qotadi
- QISMAN: 5 "arvoh funksiya" (aksiya, happy hour, kunlik taklif, loyalty ballar, bonus karta) — boshqaruv UI bor, POS'ga ULANMAGAN
- QISMAN: Modifikator admin UI yo'q; hotel xona/bron UI stub
- O'LIK: 7 router (order_item, purchase, waste, promo, customer_returns_ext, notification, device)

### 2. Xavfsizlik
- KUCHLI: Tenant izolyatsiya + IDOR himoyasi, SQL injection yo'q, bcrypt, rate limiting, CORS/SECRET guard
- XAVF: SVG upload → stored XSS (token localStorage bilan zanjirli)
- XAVF: RBAC rol-tirqishi — 19 router yozuv endpointida rol tekshirilmaydi (faqat auth+tenant)
- ZAIF: parol siyosati (6 belgi); token localStorage'da (Electron secure storage yo'q)
- XAVF (yangi, 2026-07-24): **Electron `webSecurity:false`** — XSS/SOP himoyasi o'chiq. Sabab: frontend `file://` dan, API `http://` dan → CORS chetlab o'tilgan. To'g'ri yechim: **`app://` custom protocol + `webSecurity:true` + backend CORS allowlist** (offline saqlanadi). Shart: **HTTPS/domen OLDIN** qilinsin (yakuniy origin kerak). Xavf: **O'RTA** (`nodeIntegration:false` + `contextIsolation:true` eng yomonini bloklaydi).

### 3. Ma'lumotlar butunligi
- KUCHLI: Backup tenant-safe, StockMovement audit-trail, idempotent deduct, manfiy stok himoyasi, bitta migratsiya head
- XAVF: Pul maydonlari Float (120 ta) — xalqaroga chiqishdan oldin Decimal/tiyin shart
- XAVF: Race condition — qulf yo'q (bir vaqtda sotuv → lost update)
- O'RTA: Multi-commit atomik emas + get_db rollback yo'q; ombor ayirish "best-effort"; timezone aralash (143 naive now())

### 4. Masshtablanuvchanlik
- KUCHLI: Indekslar a'lo (tenant_id 37/37 + composite + barcode), pagination keng, pool sozlangan
- XAVF: async def + sync DB → event loop blocking (500+ tenantda birinchi qulaydi; hozir sezilmaydi)
- XAVF (yangi topilma, 2026-07-22): WebSocket manager in-process singleton (Redis yo'q) + rate-limit in-memory per-worker. Bu — gorizontal masshtabning HAQIQIY to'sig'i: bir nechta worker yoki bir nechta serverga chiqib bo'lmaydi. Redis pub/sub (WS) + umumiy rate-limit store bo'lmaguncha, tizim bitta jarayonga qamalgan.
- O'RTA: Analytics Python'da agregat (SQL GROUP BY kerak); lokal disk + rasm siqilmaydi; bulk endpointlar + order-list N+1

### 5. Ishonchlilik
- KUCHLI: Global exception handler (stack-trace sizmaydi), log rotatsiya, health-check, tashqi servis timeout, graceful degradation
- XAVF: Offline sync dublikat order/to'lov — idempotency kaliti yo'q (real pul ta'siri)
- XAVF: Sentry/metrika/alerting yo'q
- O'RTA: AI chaqiruvida timeout yo'q; request-id yo'q

### 6. Billing / Obuna (DAROMAD — eng ustuvor)
- KUCHLI: Model bor (plan/expires/status/trial), feature-gating + usage-limit backend enforce (403/402)
- KRITIK: Tenant o'zini bepul PRO qiladi (/subscription/upgrade — tenant ruxsati, to'lovsiz, IDOR)
- KRITIK: subscription_expires HAR so'rovda tekshirilmaydi → to'lamasa ham abadiy ishlaydi
- KRITIK: Tenant obunani o'zi cho'zadi (/subscription/renew — xuddi shu teshik)
- O'RTA: Blok ta'sirsiz; to'lov tarixi/invoice yo'q, gateway/recurring yo'q

### 7. DevOps / Deploy
- KUCHLI: Backup migratsiyadan oldin, kunlik pg_dump, sirlar 600+git'siz, requirements pinned, security headers (asosiy), tranzaksion migratsiya
- KRITIK: HTTPS/TLS yo'q (nginx 443 bloki komment) — parol/token ochiq matnda
- KRITIK: Off-site backup yo'q (backup o'sha serverda)
- XAVF: Single server (SPOF); monitoring/alerting yo'q
- O'RTA: Qo'lda deploy + rollback protsedura hujjatlanmagan; eski dependency (CVE xavfi)

## 3. TUZATISH REJASI (ustuvorlik bo'yicha)

### TIER 0 — Shu hafta (jonli xavf, arzon, katta ta'sir)
- [ ] HTTPS: domen + certbot (Let's Encrypt), nginx 443 + HSTS + HTTP→HTTPS redirect
- [ ] Off-site AVTO-backup: server cron (rclone/s3cmd) → DigitalOcean Spaces yoki Google Drive (kunlik DB + media)
- [x] Mijoz/web backup 401 tuzatish — BAJARILDI (api.js fetchBinary + refresh, tenant-backup.js ulandi, oxirgi backup sanasi + 48h ogohlantirish). Deploy KUTMOQDA (frontend — yangi .exe kerak, branch: feature/frontend-discount-wip).
- [ ] Media (rasm) backup — pg_dump'ga qo'shimcha, uploads papkasi ham zaxiralanadi
- [x] SVG upload'ni o'chirish — BAJARILDI va DEPLOY QILINDI (2026-07-23, commit 3549f95) (.svg va .gif rad, PIL magic-byte tekshiruvi).
- ~~uvicorn worker sonini oshirish~~ — RAD ETILDI (2026-07-22, o'lchovdan keyin). Sabab: server 1 CPU / 961 MB RAM / swap yo'q; WebSocket in-process (2+ worker real-vaqt broadcast'ni buzadi — oshxona ekrani ishlamay qoladi); rate-limit per-worker (login himoyasi zaiflashadi). Worker oshirish faqat Redis + kattaroq droplet'dan KEYIN mumkin.
- [x] /customers/all ni cheklash — BAJARILDI va DEPLOY QILINDI (2026-07-23) (default 500, max 2000, frontend buzilmadi).

### TIER 1 — Daromad himoyasi (biznes-kritik)
- [x] /subscription/upgrade + /renew + PATCH /cafes teshiklari yopildi — faqat superadmin, IDOR yopildi — DEPLOY QILINDI (2026-07-23)
- [x] Per-request obuna enforcement — BAJARILDI va DEPLOY QILINDI, lekin **ENFORCE_SUBSCRIPTION=False (kill-switch o'chiq)**. Yoqishdan OLDIN: (1) yangi .exe do'konga tarqatilsin (blok ekrani/banner frontend), (2) tenant muddatlari uzaytirilsin (8–15 avgust)
- [x] To'liq blok + 2 kun grace — egasi qarori (enforcement shu tarzda quriladi)
- [ ] Blokni kuchga kiritish (cafe.is_active pipeline'da tekshirish + token bekor)
- [x] Obuna to'lov/invoice jadvali — **BAJARILDI va DEPLOY QILINDI (2026-07-28 batch, `251c6e6`):** `TenantPayment` model + to'lov qo'shish/tarix endpoint + superadmin UI (`owner/subscriptions.html`) mavjud edi; **idempotent migratsiya** (`tenant_payments` IF NOT EXISTS — jonli jadvalда no-op) qo'shildi + `/renew` endi **TenantPayment izi** qoldiradi (ilgari to'lovsiz uzaytirardi). Oylik daromad stats'да allaqachon bor.

### TIER 2 — Pul/ma'lumot to'g'riligi
- [ ] Offline idempotency kaliti (dublikat order/to'lov oldini oladi)
- [x] Race condition qulfi (14 Inventory SELECT, with_for_update) — DEPLOY QILINDI (2026-07-23)
- [x] get_db rollback — DEPLOY QILINDI (2026-07-23)
- [x] Ombor ayirishni transaction ichiga olish (atomik) — BAJARILDI, deploy KUTMOQDA (branch: feature/atomic-payment)
- [x] Multi-commit atomiklik — BAJARILDI, deploy KUTMOQDA (branch: feature/atomic-payment)
- [ ] Timezone standartlashtirish (UTC izchil)

### TIER 3 — Xavfsizlik qatlami
- [x] RBAC rol cheklovlari — BAJARILDI (40 yozuv endpoint, 13 router, yangi ruxsatsiz) va DEPLOY QILINDI (2026-07-24, commit `877dd8e`)
- [x] Parol siyosati — BAJARILDI (8+ belgi, harf+raqam, zaif rad, PIN 4-6), deploy KUTMOQDA (branch: feature/password-policy). **Login yo'liga tegilmagan — eski parollar ishlaydi**
- [ ] Token secure storage — **TIER 5 GA KO'CHIRILDI** (sabab quyida)
- [ ] HSTS/CSP header + ufw firewall (5432 yopiq) — domen kutmoqda

> ⚠️ **Token secure storage nega Tier 5 ga ko'chirildi (2026-07-24):** 65 ta joyda sinxron `localStorage.getItem`, safeStorage esa async → katta refaktoring. Va Electron'da `webSecurity:false` bo'lgani uchun XSS'dan himoya bermaydi (faqat disk o'g'irligidan). HTTPS va webSecurity muhimroq — shulardan KEYIN.

### TIER 4 — Halollik / "arvoh funksiyalar" (AI smell yo'q qilish)
- [x] **Loyalty (ballar)** — QURILDI va POS'ga ULANDI (auto-earn netdan, redeem server-authoritative, tenant sozlamalari, chekda ko'rsatish). Deploy KUTMOQDA (branch: feature/loyalty-pos)
- [x] **Bonus karta** — YASHIRILDI (loyalty bilan ustma-ust tushardi; kod saqlangan, keyin sovg'a-kartasi funksiyasi sifatida alohida qurilishi mumkin)
- [x] **Aksiya (promotions) POS'ga ulash** — **BACKEND DEPLOY QILINDI (2026-07-28 batch, `251c6e6`).** Discount + Promotion **bitta narx-yechish pipeline** (`_resolve_pricing`); **4 aksiya turi:** flash narx, summa, miqdor, 2 ol 1 ol (bir xil + boshqa mahsulot Y bepul). Arvoh muammosi yopildi (forma qayta yozildi). Migratsiya (`free_product_id`) qo'llandi. Golden **27/27** (Eco Aroma #34 byte-identical). ⚠️ **POS qismi (kassir aksiya taklifi) `.exe` v1.6.0 kutadi** — gated, oddiy sotuv buzilmaydi (§10).
- [x] **Happy hour, kunlik taklif** — `flash_price`/`min_amount` turlariga + vaqt/kun filtriga qamrab olindi (aksiya har turga time_from/to + days_of_week).
- [ ] Modifikator admin UI — qoldi
- [ ] Hotel xona/bron UI — qoldi
- [ ] Online to'lov (Click/Payme) — domen/bank API kutmoqda
- [x] O'lik router tozalash — `promos` router **uzildi va DEPLOY QILINDI** (`/discounts` dublikat; fayl+`Discount` jadval saqlandi, faqat endpoint uzildi → /promos 404). ⚠️ Qolganlari **o'lik EMAS ekan** (status-check): `returns` (returns.html ishlatadi), `purchase` (frontend ishlatadi), `waste`/`staff_meal` (dublikat emas — poteriya vs xodim ovqati), `order_item`/`notification`/`device`/`customer_returns_ext` — **hammasi SAQLANDI**.

**Chegirma+Aksiya birlashtirish dizayn qarorlari (egasi, 2026-07-28):**
- **Ikки tizim → bitta pipeline:** `Discount` (jonli) + `Promotion` (arvoh) resolver'да **ikки manba** sifatida o'qiladi; modellar birlashtirilmadi → **ma'lumot yo'qolmadi**.
- **Best-only (stacking YO'Q):** bir mahsulotга bir necha aksiya/chegirma tushsa — **eng yaxshi bittasi** (mijozга foydali); teng bo'lsa Discount ustun.
- **buy_x_get_y bepul mahsulot** → ombordan ayriladi (payment.py atomik) + chekда "🎁 BEPUL (aksiya)".
- **"2 ol 1 ol" ikки tur:** bir xil mahsulot (get_qty) + boshqa mahsulot Y bepul (`free_product_id` + `free_qty_per_set`).
- Y omборда yo'q → **kassir ogohlantiriladi** (aksiya qo'llanmaydi, sotuv davom etadi); Y **avtomatik EMAS** → kassir tasdiqlaydi; ko'p to'plam (4X→2Y).
- **Server-authoritative:** client soxta aksiya/bepul Y yubora olmaydi (server X'ni savatdan, Y ombor'ni DB'dan, promo haqiqiyligini qayta tekshiradi).

**Loyalty dizayn qarorlari (egasi tanlagan, 2026-07-24):**
- Keshbek stavkasi: **tenant sozlaydigan** (default 1000 so'm = 1 ball)
- Redeem: 1 ball = 10 so'm, min 100 ball, maks 30% (sozlanadigan)
- Ball muddati: **abadiy**
- Walk-in (mijozsiz) sotuvda ball **yig'ilmaydi**
- Ustuvorlik: chegirmalar avval → net summa → ball **netdan** → redeem to'lovda (tender)
- `customer.discount_percent` qoladi (doimiy VIP maqomi), ball undan **alohida**
- Ma'lum bo'shliq: **offline sotuvda chekda ball ko'rinmaydi** (sync'dan keyin yig'iladi)

### TIER 5 — Operatsion yetuklik
- [ ] **Token secure storage** (Electron safeStorage + 65 joyni markazlashtirish) — HTTPS va webSecurity'dan KEYIN (Tier 3 dan ko'chirildi)
- [x] **Sentry** — YOQILDI (2026-07-28, server `.env` DSN; xatolar sentry.io panelida). Telegram alert HALI ulanmagan (bot to'liq sozlanmagan).
- [x] **Monitoring skript + backup cron** — o'rnatildi, ishlayapti (kunlik 22:00 UTC backup, monitor */15).
- [x] **AI chaqiruvida timeout** — bajarildi, deploy qilindi.
- [ ] Deploy skript + rollback protsedura (DEPLOY.md)
- [x] **Request-id middleware** — allaqachon bor edi.
- [ ] Dependency yangilash (CVE tekshiruvi) — qoldi.

### TIER 6 — Masshtab (500+ tenant / xalqaro — kelajak)
- [ ] Redis: WebSocket pub/sub + umumiy rate-limit store — ko'p worker/ko'p serverga chiqish uchun MAJBURIY shart
- [ ] async DB (asyncpg yoki def+threadpool)
- [ ] Analytics SQL agregat + background task
- [ ] Rasm bucket (S3) + thumbnail/resize
- [ ] Managed PostgreSQL / DB ajratish (SPOF kamaytirish)
- [ ] Pul turini Decimal/tiyin (xalqaroga chiqishdan OLDIN shart)

## 4. Yangi funksiyalar (tuzatishdan KEYIN)

**Muhim bog'liqlik:** premium funksiyani sotish uchun avval billing (Tier 1) ishlashi shart.

1. **Egasi mobil dashboardi** — retention №1 quroli (real-vaqt savdo, bugun vs kecha, top mahsulot, ombor alert)
2. **To'lov terminali (Uzcard/Humo/Click/Payme)** — qabul qilinishning eng katta bloki (bank API tasdiqlangach)
3. **1C integratsiyasi** — enterprise/tarmoq mijozlari uchun (UZ/CIS buxgalteriya)
4. **AI qatlamini kengaytirish** — AI savdo tahlili, qayta-buyurtma tavsiyasi, talab bashorati (∞ brend farqi)
5. **Telegram-birinchi bildirishnomalar** — kunlik hisobot, kam-ombor, katta-sotuv (Pro upsell)
6. **To'liq ruscha/o'zbekcha + ko'p valyuta** — xalqaroga chiqish uchun (Tier 6 Decimal bilan bog'liq)

**Ustuvorlik:** egasi dashboardi + to'lov terminali (daromadga bevosita) → 1C + AI tahlil (enterprise/farq).

## 5. Ish uslubi
- Bosqichma-bosqich, har bosqich tasdiqlangach keyingisi
- Source-only, "one build at the end"
- Har o'zgarishdan oldin status-check, keyin browser-test
- Chala poydevor ustiga yangi funksiya QURILMAYDI
- Jonli do'kon (Eco Aroma) ma'lumoti — har amalda birinchi o'rinda
- Har taklif serverga tegsa — avval O'LCHA (CPU/RAM/ulanish/arxitektura), keyin qaror. Taxminga asoslangan "arzon yutuq" jonli tizimni buzishi mumkin (worker misoli, 2026-07-22).

## 6. Branch holati (2026-07-28)

- **main = `251c6e6`** — barcha branchlar birlashtirilgan (batch deploy). (Bu hujjat commit'i ustiga qo'shiladi.)
- **prod (server) = `251c6e6`** — deploy qilingan backend (main = prod).
- **DEPLOY KUTAYOTGAN backend: YO'Q ✅** — hammasi deploy qilindi.
- **FRONTEND `.exe` v1.6.0 kutmoqda:** sotuvchi almashish UI + aksiya taklifi POS (runtime sinovi — §10). Backend tayyor, frontend gated (buzmaydi).

**Arxiv (main'ga birlashtirilgan, deploy qilingan):** `feature/atomic-payment`, `feature/loyalty-pos`, `feature/password-policy`, `feature/observability`, `feature/frontend-discount-wip`, `feature/printer-hotfix` (2026-07-28 katta deploy → `444b85b`) + `feature/cleanup-deadrouter`, `feature/subscription-invoice`, `feature/pricing-resolver`, `feature/seller-switch` (2026-07-28 batch → `251c6e6`) + alembic merge revision `b9c8d7e6f5a4`. Hammasi main'да — ARXIV.

## 7. Deploy tarixi

- **2026-07-23 — commit `3549f95`:** 17 backend fayl (SVG filter, /customers/all limit, billing 1+2 faza [enforcement o'chiq], Inventory row-lock ×14, get_db rollback). Backup: `~/xenora-backups/pre_deploy_20260723_2111.sql.gz` (58K, gzip -t OK). Rollback hash: `1c8b74c`. Migratsiya YO'Q. Natija: toza deploy, /health OK, Eco Aroma ma'lumoti O'ZGARMAGAN (mahsulot 555 / buyurtma 17 / to'lov 16), telefondan tekshirildi (mahsulot/ombor OK). ⚠️ Sozlamalar sahifasi HALI TEKSHIRILMAGAN.
- **2026-07-24 — commit `877dd8e` (Deploy 2):** RBAC (40 yozuv endpoint, 13 router) + timezone (`tenant_day_bounds` — kunlik chegara Toshkent yarim tuni). Backup: `~/xenora-backups/pre_deploy_20260724_0921.sql.gz`. Rollback hash: `3549f95`. Migratsiya YO'Q. Natija: toza, merge konfliktsiz, /health OK, Eco Aroma **555/17/16 o'zgarmagan**, admin RBAC bloklanmadi.
- **2026-07-28 — `2257061` → `444b85b` (Katta deploy — v1.5.0):** Barcha feature branch main'ga BIRLASHTIRILDI (atomic-payment, loyalty-pos, password-policy, observability, frontend-discount-wip, printer-hotfix + 3 sessiya-izolyatsiya tuzatiш). Backend deploy qilindi. Backuplar: `pre_bigdeploy_20260728_0802.sql.gz` + `pre_hotfix_20260728_0850.sql.gz` (58K, gzip OK). Rollback: `877dd8e`→`2257061`. Migratsiya YO'Q. Natija: toza, /health OK, Eco Aroma **555/17/16 o'zgarmagan**.
- **2026-07-28 — Sentry YOQILDI:** server `.env`'ga `SENTRY_DSN`+`SENTRY_ENVIRONMENT=production` qo'shildi, `sentry-sdk`+`jinja2` venv'ga o'rnatildi. Xatolar sentry.io panelida ko'rinadi. **Telegram alert HALI ulanmagan** (bot to'liq sozlanmagan). Test 500 (auth/me) panelga yetdi.
- **2026-07-28 — commit `444b85b` (opsional-auth hotfix):** 13 endpoint `get_current_user`(opsional, token'siz None→500/crash) → `get_current_active_user` (majburiy auth → toza 401): /me, change_password, employee×4, upload×5, attendance×2. Deploy qilindi. Runtime tekshirildi (token'siz 401, valid token 200, upload rasm 200). Migratsiya YO'Q.
- **2026-07-28 — v1.5.0 `.exe` BUILD:** `dist_artifacts/` (Setup + Portable, 80MB har biri; SumatraPDF+frontend bundle). Kamoldinga (Eco Aroma) Telegram orqali yuborildi, o'rnatish yo'riqnomasi bilan. **HALI o'rnatilmagan/tasdiqlanmagan.**
- **2026-07-28 — `444b85b` → `251c6e6` (BATCH deploy — 4 branch + alembic merge):** cleanup-deadrouter (promos router uzildi), subscription-invoice, pricing-resolver, seller-switch main'ga birlashtirildi + **alembic merge revision `b9c8d7e6f5a4`** (2 parallel head → yagona). test/integration2'да avval sinaldi (merge toza, golden 27/27). **3 migratsiya:** `tenant_payments` (IF NOT EXISTS — jonli no-op), `free_product_id`+`free_qty_per_set` (ADD COLUMN IF NOT EXISTS), merge (no-op) — **idempotent, xatosiz**. Backup: `pre_deploy_batch_20260728_1916.sql.gz`. Rollback: `444b85b` + alembic downgrade. Natija: toza, /health OK, startup xato 0, Eco Aroma **555/17/16 o'zgarmagan**, golden 27/27, /promos 404 (uzildi), /discounts+/promotions 200, alembic current `b9c8d7e6f5a4`. **Eski .exe ishlaydi** (backend additiv/gated).

## 8. Tayyor, build kutayotgan ishlar

**BACKEND HAMMASI DEPLOY QILINDI (2026-07-28 batch → `251c6e6`).** Faqat **FRONTEND qismlari `.exe` v1.6.0** kutmoqda (backend tayyor + gated → jonli sotuv buzilmaydi):

- **Sotuvchi almashish UI** (seller-switch) — POS header qulf → PIN pad → faol sotuvchi + savat guard + avto-qulf; sotuvchi hisoboti backend'да tayyor. Runtime sinovi kerak (§10).
- **Aksiya taklifi POS** (pricing POS qismi) — kassir aksiya taklifi (buy X get Y bepul mahsulot), chek yorlig'i "🎁 BEPUL (aksiya)". Backend + endpoint tayyor, POS UI runtime sinovi kerak (§10).
- **Premium dizayn** — allaqachon v1.5.0 `.exe`da (frontend-discount-wip).

**v1.6.0 build:** seller-switch UI + pricing POS qismi (+ kelasi frontend ishlari) — bitta build'ga. Do'kon jihozi/vaqti bilan.

## 9. Deploy rejasi (BAJARILDI — 2026-07-28 batch)

> ✅ **BAJARILDI:** quyidagi reja o'rniga — 4 branch bitta **batch deploy**да birlashtirildi (test/integration2'да avval sinaldi, 2 alembic head merge revision bilan hал qilindi). Natija `251c6e6` (§7). Quyi — tarixiy reja.

**Deploy kutayotgan branchlar KO'P yig'ildi (3 ta).** Ular ARALASHTIRILMASIN — har biri **alohida, ketma-ket** deploy qilinadi. Har biri: **backup → deploy → runtime test → keyingisi**.

Tavsiya etilgan tartib (kichikdan kattaga, xavfni kamaytirish):
1. **`feature/subscription-invoice`** — eng kichik, faqat backend. Backup → merge → `git pull` → `alembic upgrade head` (tenant_payments idempotent, jonli no-op) → restart → /renew tarix yozishini tekshir.
2. **`feature/pricing-resolver`** — katta, MIGRATSIYALI. Backup → merge → pull → `alembic upgrade head` (free_product_id) → restart → **runtime sinov:** har 4 aksiya turini admin'da yaratish, POS'da chegirma+aksiya to'g'ri hisoblanishini, #34 buzilmaganini (golden 27/27 kafolat), bepul Y ombor/chek/refund'ni tekshir.
3. **`feature/seller-switch`** — frontend, migratsiyasiz. Merge → **v1.6.0 `.exe` build** (pricing POS qismi ham shu build'ga tushsin) → qurilmada sinov.

**Muhim eslatmalar:**
- **.exe build kerak** bo'lganlar (seller-switch + pricing POS qismi) do'kon jihozi/vaqti bilan bog'liq — bitta v1.6.0 build'ga birlashtirilishi mumkin (2+3 birga).
- Har migratsiyали deploy'да **backup MAJBURIY** (`pg_dump` + gzip -t).
- Har deploy'dan keyin **Eco Aroma 555/17/16** (mahsulot/buyurtma/to'lov) o'zgarmaganini tasdiqla.
- Rollback: `git checkout <oldingi> + alembic downgrade + restart` (migratsiyали branchlar uchun downgrade tayyor).

## 10. Runtime sinovi kutayotgan (v1.6.0 build'da tekshiriladi)

Backend deploy qilingan + golden/unit testlardan o'tgan, LEKIN **jonli POS'da hali sinalmagan** — v1.6.0 `.exe` build'да haqiqiy qurilma + 2 sotuvchi + aksiya bilan sinaladi:

- **Sotuvchi almashish:** qulf → PIN → faol sotuvchi almashishi; savat guard (tovar bo'lsa ogohlantirish+tozalash); avto-qulf (harakatsizlik, sozlamada); sotuv/premiya aniq sotuvchiga yozilishi; sotuvchi hisoboti (kim qancha sotdi).
- **Aksiya POS:** kassir aksiya taklifi ("X oldingiz → Y bepul, qo'shilsinmi?"); bepul mahsulot ombordan ayrilishi (atomik); Y ombor yo'q → ogohlantirish; chekда "🎁 BEPUL (aksiya)" yorlig'i; refundда bepul Y qaytishi.
- **Chegirma+aksiya birga:** oddiy #34 chegirma + yangi aksiyalar jonli savatда to'g'ri hisoblanishi (best-only, stacking yo'q) — golden 27/27 kafolat, lekin jonli tasdiq kerak.

**Muhim:** bular **gated/additiv** — eski `.exe` (v1.5.0) yangi backend bilan oddiy sotuvni buzmaydi; yangi funksiyalar faqat v1.6.0 frontend bilan faollashadi.

## 11. Ombor aniqligi va cancel ruxsati (2026-09-08, kasrli sotuv ishidan)

Kasrli (kg) sotuv qo'shilganda ikki nuqson topildi va tuzatildi
(`feature/weight-sales`): ombor chiqimi/tiklashda suzuvchi nuqta axlati va
`cancel_order` da ombor himoyasining yo'qligi. Quyidagilar esa **ataylab
keyinga qoldirildi** — bugun xavf yo'q, lekin qarz sifatida yozib qo'yildi.

### 11.1 Ombor yaxlitlash: 15 joyda `round(..., 3)` yo'q

Yaxlitlash faqat **sotuv chiqimi** va **ikki qaytarish yo'lida** qo'shildi
(`recipe_inventory_service.py:202` va `:407`, `routers/returns.py:56`).
Qolgan joylarda `inventory.quantity` yaxlitlanmasdan o'zgaradi:

    routers/inventory.py:427, 509, 545      kirim / chiqim / writeoff
    routers/purchase_receipts.py:223        priyomka tasdiqlash
    routers/purchase.py:63                  xarid
    routers/ai_warehouse.py:349             AI-ombor kirimi
    routers/waste.py:119                    chiqindi
    routers/write_offs.py:128               hisobdan chiqarish
    routers/supplier_returns.py:94, 177     firmaga qaytarish / bekor qilish
    routers/internal_transfers.py:138, 147  filiallar aro ko'chirish
    routers/goods_regrade.py:123, 129       qayta saralash
    services/inventory_service.py:64        adjust_stock
    recipe_inventory_service.py:121, 350    retsept ingredientlari (6 xona —
                                            ATAYLAB tegilmagan)

**Bugun xavfsiz:** bu yo'llarga miqdorni ODAM kiritadi (50, 10.5) — kasr
to'planmaydi. Xavf faqat mashina hisoblagan kasr ketma-ket qo'shilganda
paydo bo'ladi.

**Qilinishi kerak:** yagona yordamchiga yig'ilsin, masalan
`core/inventory_math.py: apply_delta(inv, delta)` — har joyda takrorlangan
`round(..., 3)` o'rniga bitta manba. Shunda yangi yo'l qo'shgan odam
yaxlitlashni unuta olmaydi.

**Vaqtinchalik himoya:** `services/stock_guard.py:135` dagi `1e-6` dopusk
eski axlatli qoldiqlarni qoplaydi (`available + 1e-6 < qty`).

### 11.2 `cancel_order` endpointi maxsus ruxsat talab qilmaydi

`POST /orders/{order_id}/cancel` (`routers/order.py:285`) —
`Depends(get_current_active_user)`, ya'ni **istalgan tizimga kirgan faol
xodim** (ofitsiant ham) buyurtmani bekor qila oladi. Tenant izolyatsiyasi
bor, lekin rol tekshiruvi YO'Q.

2026-09-08 da ombor himoyasi qo'shildi (`ingredients_deducted=True` bo'lsa
400 qaytadi), ya'ni ombor endi buzilmaydi. Ammo **ruxsat masalasi ochiq**:
to'lanmagan buyurtmani ham har kim bekor qila olishi to'g'rimi?
Solishtirish uchun: qaytarish (returns) `process_payments` talab qiladi
(faqat admin/kassir).

**Qilinishi kerak:** `cancel` uchun ham mos permission tanlansin
(`process_orders` yoki `process_payments`) — POS oqimini buzmasligi
tekshirilib.

## 12. Frontend test to'plami (2026-09-10, v1.12.7 relizidan)

### 12.1 `test_searchable_select_stage_b.mjs` main'da yiqiladi

`node frontend/tests/test_searchable_select_stage_b.mjs` →

```
[FAIL] B7_qidiruv_inputi_qoshildi: 0 (kutilgan 1)
page.evaluate: TypeError: window.openAdd is not a function
    at frontend/tests/test_searchable_select_stage_b.mjs:165
```

**OLDINDAN MAVJUD** — v1.12.7 o'zgarishlaridan EMAS. `main` (fa172f4) da
stash bilan tekshirildi: o'sha xato, o'sha qator. B1–B6 o'tadi, B7 dan
keyin test uzulib qoladi (`process.exit` gacha yetmaydi).

**Ma'nosi:** `window.openAdd` global emas yoki nomi o'zgargan. Bu aynan
`test_module_inline_onclick.js` ushlaydigan sinf xatosiga o'xshaydi
(modul ichidagi funksiya `window` ga chiqmaydi), lekin u test o'tadi —
demak `openAdd` inline `onclick` da emas, faqat testda chaqiriladi.

**Xavf:** noma'lum. Ikki ehtimol:
1. Test eskirgan (funksiya qayta nomlangan) → testni tuzatish kerak.
2. Priyomka/kirim oynasidagi "qo'shish" haqiqatan sinsan → MIJOZGA TEGADI.

**Qilinishi kerak:** qaysi ekan — aniqlansin. Ikkinchi holatda tez
tuzatish, birinchisida test yangilansin. Shu holatda to'plam "yashil"
emas va yangi regressiya ko'rinmay qolishi mumkin.

## 13. Smena oqimi (2026-09-10, 1001 BARAKA auditidan)

### 13.1 Smenasiz sotuv: `shift_id = NULL` hech qaysi Z-hisobotga tushmaydi

`services/order_service.py:418` buyurtmani SOTUVCHINING o'z ochiq smenasiga
bog'laydi:

```python
active_shift = self.db.query(Shift).filter(
    Shift.user_id == waiter_id, Shift.end_time.is_(None)).first()
shift_id = active_shift.id if active_shift else None
```

Xodimda ochiq smena bo'lmasa `shift_id = None`. `close_shift` esa buyurtmalarni
`Order.shift_id == shift.id` bo'yicha topadi — NULL'lar HECH QAYERGA tushmaydi.
Pul sotilgan, lekin kun yakunida ko'rinmaydi.

**Hozir nega portlamayapti:** POS gate (`ensureShiftGate`) `cash_register` yoki
`z_report` yoqilgan biznesda savdoni bloklaydi, ya'ni smenasiz sotib bo'lmaydi.
Prodda tenant 27 da NULL yo'q (144/144 buyurtma smena 11 da). LEKIN gate FAQAT
FRONTEND — `POST /orders/` serverda ochiq smena TALAB QILMAYDI. Offline sync,
eski `.exe`, boshqa klient yoki to'g'ridan-to'g'ri API chaqiruvi teshikdan
o'tadi.

### 13.2 `legacy_fallback` boshqa kassir sotuvini yutib yuboradi

`routers/shift.py` (close va report, ikkalasida ham):

```python
if not orders:                      # shift_id bo'yicha bitta ham topilmadi
    legacy_fallback = True
    orders = ...filter(Order.created_at >= shift.start_time,
                       Order.created_at <= now).all()   # BUTUN TENANT
```

Fallback tenant bo'yicha, kassir bo'yicha EMAS. Ya'ni bo'sh smenani yopgan
kassir o'sha vaqt oralig'idagi **boshqa kassirlarning** sotuvini ham o'z
Z-hisobotiga yig'ib oladi. Ikki kassir parallel ishlaganda bu real xavf:
navbatchi hech narsa sotmagan bo'lsa, hamkasbining butun kuni uning
kamomadiga aylanadi.

Fallback `shift_id` biriktirilmagan ESKI smenalar uchun yozilgan (orqaga
moslik). Endi `shift_id` har buyurtmaga yoziladi, ya'ni fallback deyarli
faqat NOTO'G'RI holatda ishga tushadi.

**Qilinishi kerak (bitta ish sifatida):**
1. `POST /orders/` serverda ochiq smena talab qilsin (smena majburiy
   biznes turlarida) — 409 bilan. Frontend gate qolaveradi, lekin u yagona
   himoya bo'lmasin.
2. `legacy_fallback` kassir bo'yicha ham cheklansin
   (`Order.waiter_id == shift.user_id`), yoki umuman olib tashlansin —
   avval bazada `shift_id IS NULL` buyurtmalar bor-yo'qligi tekshirilib.
3. `shift_id IS NULL` buyurtmalar uchun admin ko'radigan hisobot
   ("smenasiz sotuvlar") — jimgina yo'qolmasin.

⚠️ v1.12.9 da TEGILMADI (ataylab): u faqat ruxsat qatlamini yopdi
(`fix/shift-pos-access`). Bu — alohida ish, chunki `POST /orders/` ga
tegish jonli sotuv yo'li.

### 13.3 Admin boshqa xodimga smena ocholmaydi — alohida endpoint kerak

`create_shift` (v1.12.9 dan) smenani HAR DOIM so'rov yuborgan xodimga ochadi;
boshqa `user_id` yuborilsa 403. Admin paneldagi xodim tanlash ro'yxati ham
shu sabab olib tashlandi (`js/admin/shift.js: openShiftModal`) — u
bajarib bo'lmaydigan va'da berardi.

Amalda bu kerak bo'lishi mumkin: kassir smenani ochishni unutib savdoni
boshlab yuborsa, yoki yangi xodim tizimga hali kirmagan bo'lsa, admin uning
nomiga smena ochishi kerak bo'ladi.

**Qilinishi kerak:** alohida, aniq niyatli endpoint —
`POST /shifts/for-user` (yoki `create_shift` ga `on_behalf_of` maydoni),
`Depends(has_permission("manage_shifts"))` bilan. Talablar:
- maqsad xodim AYNI tenant'da bo'lsin;
- audit'da "kim ochdi" va "kimga ochildi" ikkalasi ham yozilsin
  (hozir `log_audit` da `user_id` faqat smena egasi);
- admin UI'da xodim tanlash ro'yxati o'sha endpointga ulansin.

Prod audit'i: 11 smenadan faqat 1 tasi (tenant 5, iyul 2026) shu yo'l bilan
ochilgan — ya'ni shoshilinch emas, lekin butunlay yo'q qilish ham to'g'ri emas.

### 13.4 Playwright testlari ketma-ket yugurtirilganda tasodifiy yiqiladi

`frontend/tests/*.mjs` ni bitta tsiklda ketma-ket yugurtirganda testlar
tasodifiy yiqiladi — brauzer ishga tushish raqobati. Belgilari:

```
page.goto: Timeout 30000ms exceeded
  - navigating to "http://127.0.0.1:PORT/app/admin.html"
```

Aynan bir test alohida yugurtirilganda TO'LIQ o'tadi. 2026-09-10 da bu
kamida to'rt marta uchradi: bir yugurishda `test_product_list_stock`,
`test_blocked_store_login_message`, `test_supplier_dropdown_refresh`,
`test_fast_product_entry` "XATO" bergan, keyin alohida yugurtirilganda
52/52, 12/12, 5/5, 54/54 o'tgan. `sleep 3` qo'shish ham yetarli emas;
fonda og'ir jarayon (pytest) ketayotganda ehtimol ortadi.

**NEGA XAVFLI:** "yana o'sha flaky" deb o'tkazib yuborish odat bo'lib
qoladi va HAQIQIY nuqson ham shu niqob ostida o'tib ketadi. Hozircha har
"XATO" alohida qayta yugurtirilib tekshirilmoqda — bu qo'lda va
ishonchsiz.

**Qilinishi kerak:**
- yagona runner skript (`scripts/run_frontend_tests.mjs`): testlarni BITTA
  `chromium.launch()` bilan ketma-ket yugursin (har test o'z brauzerini
  ko'tarmasin) yoki kamida qayta urinish (retry) bilan;
- yagona yakuniy hisobot (nechta o'tdi/yiqildi) — hozir har fayl o'zicha
  chop etadi, jami son qo'lda sanaladi;
- CI'da shu runner ishlatilsin, `stage_b` esa 12.1 hal bo'lgunча aniq
  "ma'lum yiqilish" deb belgilansin (jimgina o'tkazib yuborilmasin).
