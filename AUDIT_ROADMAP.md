# XENORA — Audit va Tuzatish Rejasi

**Oxirgi yangilanish:** 2026-07-24
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
- [ ] Obuna to'lov/invoice jadvali

### TIER 2 — Pul/ma'lumot to'g'riligi
- [ ] Offline idempotency kaliti (dublikat order/to'lov oldini oladi)
- [x] Race condition qulfi (14 Inventory SELECT, with_for_update) — DEPLOY QILINDI (2026-07-23)
- [x] get_db rollback — DEPLOY QILINDI (2026-07-23)
- [x] Ombor ayirishni transaction ichiga olish (atomik) — BAJARILDI, deploy KUTMOQDA (branch: feature/atomic-payment)
- [x] Multi-commit atomiklik — BAJARILDI, deploy KUTMOQDA (branch: feature/atomic-payment)
- [ ] Timezone standartlashtirish (UTC izchil)

### TIER 3 — Xavfsizlik qatlami
- [ ] Token secure storage (Electron safeStorage + preload IPC)
- [ ] RBAC rol cheklovlari (19 router)
- [ ] Parol siyosati (uzunlik + murakkablik)
- [ ] HSTS/CSP header + ufw firewall (5432 yopiq)

### TIER 4 — Halollik / "arvoh funksiyalar" (AI smell yo'q qilish)
- [ ] 5 promo tizimini POS'ga ulash yoki vaqtincha yashirish (happy hour, kunlik taklif, loyalty, bonus, aksiya)
- [ ] Modifikator admin UI
- [ ] Hotel xona/bron UI
- [ ] Online to'lov (Click/Payme) — yakunlash yoki UI'dan olish
- [ ] 7 o'lik routerni tozalash

### TIER 5 — Operatsion yetuklik
- [ ] Sentry + monitoring (disk/RAM/CPU alert)
- [ ] AI chaqiruvida timeout
- [ ] Deploy skript + rollback protsedura (DEPLOY.md)
- [ ] Request-id middleware
- [ ] Dependency yangilash (CVE tekshiruvi)

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

## 6. Branch holati (2026-07-24)

- **main = `3549f95`** — prod bilan bir xil (server shu commit'da). Faqat deploy qilingan backend.
- **feature/frontend-discount-wip = `d732a43`** — frontend (obuna blok ekrani, ogohlantirish banner, backup 401 fix, premium dizayn ~30 fayl) + **#34 avto-chegirma** (`discount.py`, `order_service.py`). Deploy KUTMOQDA (frontend → .exe).
- **feature/atomic-payment = `f448154`** — to'lov atomikligi (`payment.py`, `payment_service.py`, `recipe_inventory_service.py`). Deploy KUTMOQDA.

⚠️ **OGOHLANTIRISH:** ikkala branch ham SOTUV oqimiga tegadi (`order_service.py` va `payment.py`). Birlashtirishda **BIRGA emas, KETMA-KET** merge qilinsin va **har biridan keyin test** (regressiya + atomiklik + avto-chegirma hisobi). Konflikt ehtimoli: order/payment yaratish oqimi.

## 7. Deploy tarixi

- **2026-07-23 — commit `3549f95`:** 17 backend fayl (SVG filter, /customers/all limit, billing 1+2 faza [enforcement o'chiq], Inventory row-lock ×14, get_db rollback). Backup: `~/xenora-backups/pre_deploy_20260723_2111.sql.gz` (58K, gzip -t OK). Rollback hash: `1c8b74c`. Migratsiya YO'Q. Natija: toza deploy, /health OK, Eco Aroma ma'lumoti O'ZGARMAGAN (mahsulot 555 / buyurtma 17 / to'lov 16), telefondan tekshirildi (mahsulot/ombor OK). ⚠️ Sozlamalar sahifasi HALI TEKSHIRILMAGAN.
