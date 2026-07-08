# XENORA — Build, Funksiyalar va Deploy

> Arxitektura uchun → `ARCHITECTURE.md`. Bu hujjat: qurilgan funksiyalar holati,
> ishga tushirish, **deploy qadamlari (toza baza)** va ma'lum muammolar.
> (Brend: **XENORA** · native `com.xenora.app` · kod ichida `RestoPOS`/`restopos_*` legacy nomlar.)

---

## 1. Qurilgan funksiyalar (holat + fayllar)

| Funksiya | Holat | Sana | Asosiy fayllar |
|---|---|---|---|
| **Auth — parol + PIN** | ✅ | — | `routers/auth.py`, `services/auth_service.py`, `core/security.py` |
| **Rol tizimi + RBAC redirect** | ✅ | — | `routers/role.py`, `frontend/js/core/auth-guard.js` (`PAGE_ROLES`, `canonicalRole`) |
| **Multi-tenant izolyatsiya** | ✅ | — | `deps.py` (`resolve_tenant_id`, `apply_tenant_filter`); `employee.py` + `cafe.py` teshiklari yopildi (2026-06-21) |
| **Feature-flag (FREE/PRO tier)** | ✅ | — | `core/feature_flags.py`, `routers/cafe.py`, `frontend/js/core/features.js` |
| **Feature-flag UI gating** | ✅ | — | `frontend/js/core/features.js` (`features.has`) |
| **POS sotuv + bo'lib to'lov** | ✅ | — | `routers/order.py`, `payment.py`, `frontend/js/modules/pos.js` |
| **Oshxona ekrani (KDS) + WebSocket** | ✅ | — | `routers/kitchen.py`, `websocket/`, `frontend/app/kitchen.html` |
| **Biznes-turi POS rejimlari** | ✅ | 2026-06 | `frontend/js/modules/pos.js` (store/pharmacy/salon/fitness/auto/hotel) |
| **Fiskal OFD QR (mock/live)** | ✅ | Bosqich 28 | `services/escpos_service.py`, `routers/settings.py`, `Order.fiscal_*` |
| **ESC/POS printer (mock/network/usb/spooler + fallback)** | ✅ | Bosqich 2 | `services/escpos_service.py`, `services/printer_service.py` |
| **Multi-kassa (cash register)** | ✅ | Bosqich 30 | `routers/cash_register.py`, `Shift.register_id` |
| **Smena ochish/yopish + kassa farqi** | ✅ | Bosqich 30 | `routers/shift.py`, `frontend/app/shift.html`, `admin.html` |
| **Z-hisobot (kun yakuni) + shift_id yig'ish** | ✅ | Bosqich 31 (2026-06-21) | `routers/shift.py`, `services/escpos_service.py` (`build_z_report`), `Order.shift_id` |
| **Barkod-kirim (skaner → bor/yo'q → yangi tovar)** | ✅ | 2026-06-21 | `frontend/app/inventory.html`, `purchase_receipts.html`, `routers/barcodes.py` |
| → yangi tovar: barkod avto + kategoriya majburiy + rasm + boshlang'ich qoldiq | ✅ | 2026-06-21 | yuqoridagi + `routers/product.py`, `category.py`, `inventory.py` |
| **Multi-barcode + tarozi PLU** | ✅ | Bosqich 20 | `routers/barcodes.py`, `models.ProductBarcode` |
| **Ombor: kirim, inventarizatsiya, kam-qoldiq** | ✅ | Bosqich 16 | `routers/inventory.py`, `frontend/app/inventory.html` |
| **Priyomka (B2B qabul akti)** | ✅ | Bosqich 24 | `routers/purchase_receipts.py`, `suppliers.py` |
| **Qaytarish / Nasiya** | ✅ | Bosqich 19 | `routers/returns.py`, `debt.py` |
| **Sodiqlik / bonus karta** | ✅ | Bosqich 5/26 | `routers/loyalty.py`, `bonus_cards.py` |
| **Retsept → ombordan avto kamaytirish + poteriya** | ✅ | Bosqich 17 | `services/recipe_inventory_service.py`, `routers/waste.py` |
| **Dorixona / Salon / Auto / Hotel maxsus** | ✅ | Bosqich 22–23 | `prescription.py`, `batches.py`, `staff_schedule.py`, `vehicle.py`, `hotel.py` |
| **Backup (pg_dump) + Audit log** | ✅ | Bosqich 13 | `tasks/backup_tasks.py`, `routers/backup.py`, `core/audit.py` |
| **PWA offline (SW + IndexedDB sync)** | ✅ | Bosqich 3 | `frontend/pwa/`, `frontend/js/core/{db,sync}.js` |
| **Desktop/Mobil (Electron/Tauri/Capacitor)** | ✅ | Bosqich 7/12 | `electron/`, `src-tauri/`, `android/` |
| **Settings biznes-turiga moslash (begona funksiya kulrang)** | ✅ | 2026-06-22 | `admin.html` (`loadSettings`, `in_business`), `cafe.py` |
| **Feature guruhlash (FOOD/RETAIL frozenset, DRY)** | ✅ | 2026-06-22 | `core/feature_flags.py` (`FOOD_FEATURES`, `RETAIL_FEATURES`) |
| **PRO monetizatsiya (retail/pharmacy default'idan PRO olib tashlandi)** | ✅ | 2026-06-22 | `core/feature_flags.py`, `frontend/js/core/features.js` |
| **Nav-feature gating + orders food-only** | ✅ | 2026-06-22 | `admin.html` (`showNavGroup`), `sidebar.js` |
| **Barcode skaner ovozi (beep add/error)** | ✅ | 2026-06-22 | `frontend/js/modules/pos.js` (`beep`) |
| **Tan narxi confirm'da (cost_price + StockMovement + last_restock)** | ✅ | 2026-06-23 | `routers/purchase_receipts.py` (confirm) |
| **Firmalar Tizim B to'liq** (confirm→Inventory/cost/StockMovement/ProductBatch+expiry; UI navga ulash; features.js teshigi) | ✅ | 2026-06-23 | `purchase_receipts.py`, `models.ProductBatch`, `suppliers.html`/`purchase_receipts.html`/`supplier_debt.html`, `admin.html` |
| **Tizim A (eski supplier) to'liq olib tashlash** (router/model/frontend/jadval; reorder → `/suppliers-b2b/`) | ✅ | 2026-06-23 | o'chirildi: `supplier.py`, `purchase_orders.py`, `PurchaseOrder*`; migration `b5c6d7e8f9a0` |
| **Tarozi to'liq oqimi (wiring bug fix + PLU UI)** | ✅ | 2026-06-23 | `frontend/js/modules/pos.js` (`handleBarcodeScan`), `admin.html` (PLU), `routers/barcodes.py` |
| **Kirish: do'kon kodi (100.200.N) + PIN (tenant-scoped)** | ✅ | 2026-07 | `routers/auth.py` (`resolve-code`, `pin-login`), `Cafe.access_code`, migration `c3d4e5f6a7b9` |
| **Super-admin alohida login yo'li** | ✅ | 2026-07 | `frontend/shared/login.html` ("Platforma administratori" → telefon+parol → `owner/cafes.html`) |
| **Uzoq sessiya (access 12s / refresh 30 kun, auto-refresh)** | ✅ | 2026-07 | `config.py`, `routers/auth.py` (`refresh`), frontend auto-refresh; xodim faolsizlantirilsa 401 |
| **Xavfsizlik: SECRET_KEY env + production_checks + rate limit** | ✅ | 2026-07 | `config.py` (`production_checks`), `core/middleware` (auth 20/min, umumiy 600/min) |
| **Super-admin login env'dan (hardcode olib tashlandi)** | ✅ | 2026-07-03 | `config.py` (`FIRST_SUPERUSER_*`), `database.py` (`init_db`); production standart parolni bloklaydi |
| **Tenant backup + restore (izolyatsiyalangan, JSON.gz)** | ✅ | 2026-07 | `routers/backup.py` (`/my-tenant`, `/my-tenant/restore`), `frontend/js/core/tenant-backup.js` |
| **Electron avtomatik kunlik backup (14:00/22:00)** | ✅ | 2026-07 | `electron/main.js` (`backup:save`), `Documents/XENORA-Backup/` |
| **Oshxona sodda oqim (1-bosish tayyor, 15min timer, reopen)** | ✅ | 2026-07 | `frontend/app/kitchen.html`, `routers/kitchen.py` |
| **Oshxona stansiya tizimi (Station, station_id filtr, displeysiz)** | ✅ | 2026-07 | `routers/station.py`, `models.Station`, `kitchen.html` (gear + localStorage) |
| **Audit log (order/product/shift/return/login + ko'rish paneli)** | ✅ | 2026-07 | `models.AuditLog`, `core/audit.py`, `routers/audit.py`, migration `b2c3d4e5f6a8`; admin.html "Xodimlar faoliyati" |
| **Tariflar FREE/PRO (Enterprise olib tashlandi)** | ✅ | 2026-07 | `core/feature_flags.py` (`FeatureTier`), `core/subscription.py` (`PLAN_LIMITS`) |
| **Super-admin do'kon boshqaruvi (tarif, access_code, parol/telefon reset)** | ✅ | 2026-07 | `routers/super_admin.py`, `owner/cafes.html` |
| **Offline contract fix ({success,data}, sync res.data.id)** | ✅ | 2026-07 | `frontend/js/core/api.js`, `sync.js`, `js/modules/pos.js` |
| **XENORA brend + native app (Electron/Capacitor com.xenora.app)** | ✅ | 2026-07 | `electron/electron-builder.json`, `capacitor.config.json`, girih yulduz logo, zumrad-tilla dizayn |
| **Premium UI overlay (barcha app/ sahifalar)** | ✅ | 2026-07 | `frontend/styles/premium-overlay.css` (shared qatlam) |

> To'liq bosqichma-bosqich tarix git tarixida va eski hujjat versiyalarida.

---

## 2. Ishga tushirish

### Lokal dev
```bash
cd backend
py -m venv .venv && .venv\Scripts\activate          # Windows
py -m pip install -r requirements.txt
copy .env.example .env                               # SECRET_KEY, DATABASE_URL ni to'g'rilang
py -m alembic upgrade head                           # migratsiyalar (joriy head: d4e5f6a7b9c0)
py -m uvicorn main:app --reload --port 8000
```
- API: `http://localhost:8000/api/v1` · Swagger: `/docs` · Health: `/health`
- Frontend: `http://localhost:8000/frontend/shared/login.html` (yoki Live Server :5500, API :8000 — CORS ochiq)
- PostgreSQL avval: `CREATE USER pos_user ...; CREATE DATABASE restaurant_pos OWNER pos_user;`
- **Dev super-admin:** telefon `+998949974770` / parol `admin4770` (env yo'q bo'lsa default — `config.py`).
- Kirish: do'kon kodi + PIN, yoki super-admin uchun login.html'da "Platforma administratori".

### Migratsiya
```bash
py -m alembic heads      # joriy head
py -m alembic current    # DB holati
py -m alembic upgrade head
py -m alembic revision -m "tavsif"   # yangi migratsiya
```
Joriy head: **`d4e5f6a7b9c0`** (`order_ingredients_deducted`). So'nggi zanjir:
`a1b2c3d4e5f7` (tenant_settings) → `b2c3d4e5f6a8` (audit_log tenant_id) → `c3d4e5f6a7b9` (cafe access_code) → `d4e5f6a7b9c0` (head).

---

## 2A. DEPLOY — toza baza (production, birinchi o'rnatish)

Deploy'da **yangi toza PostgreSQL** ko'tariladi. Test ma'lumot **YO'Q** — migratsiya sxemani
yaratadi, startup esa super-admin + rollar + default kategoriya/stolni seed qiladi (`init_db`).

**Qadamlar:**
1. **Server talablari:** PostgreSQL 15, Python 3.11, `pg_dump` (server backup uchun — `postgresql-client`), nginx (HTTPS reverse proxy). Docker'da hammasi Compose ichida.
2. **`.env` to'ldirish** (`.env.example` dan nusxa) — MAJBURIY o'zgaruvchilar quyida (§2B).
3. **Baza yaratish:** yangi PostgreSQL DB + user (yoki Docker `db` servisi avtomatik).
4. **Sxema:** `py -m alembic upgrade head` (Docker entrypoint buni avtomatik bajaradi).
5. **Super-admin:** birinchi startup'da `settings.FIRST_SUPERUSER_*` (env) dan **avtomatik** yaratiladi. Hardcode YO'Q. Production'da standart/kuchsiz parol (`admin4770`, <8 belgi) → server **ishga tushmaydi** (`production_checks`).
6. **Ishga tushirish:** `uvicorn main:app` (Docker: `docker-compose up -d`).
7. **Birinchi kirish:** super-admin telefon+parol (env'dagi) → `owner/cafes.html` → birinchi do'kon (tenant) yaratiladi → do'konga `access_code` (100.200.N) beriladi → xodimlar kod+PIN bilan kiradi.

> **Muhim:** mavjud super-admin (bazada bor bo'lsa) buzilmaydi — `init_db` faqat telefon topilmasa yaratadi. Deploy'dan keyin super-admin parolini ilova ichidan yana almashtirish tavsiya etiladi.

### Docker (production)
```bash
cp backend/.env.docker backend/.env     # SECRET_KEY + FIRST_SUPERUSER_PASSWORD ni O'ZGARTIRING!
docker-compose up -d
# Makefile: make up / down / logs / migrate / shell / db / test / ssl-init / ssl-enable
```
3 servis: `restopos_nginx` (80/443) + `restopos_backend` (8000) + `restopos_db` (PostgreSQL 15).
Entrypoint: DB kutadi → `alembic upgrade head` → super-admin seed → `uvicorn`.

### HTTPS / nginx (deploy'da qo'shiladi)
- `nginx/` reverse proxy: `:80` → `:443` redirect, `/api` → backend `:8000`, statik frontend.
- SSL: Let's Encrypt (`make ssl-init` tayyor — domen + sertifikat olinadi, keyin `make ssl-enable`).
- `.env`da `BACKEND_CORS_ORIGINS` faqat o'z domeningga (`["https://xenora.uz","https://www.xenora.uz"]`), `ENVIRONMENT=production`, `DEBUG=False`.

---

## 2B. `.env` o'zgaruvchilari (deploy uchun)

`.env.example` (dev namunasi) va `.env.docker` (production namunasi) — barcha o'zgaruvchilar ro'yxati.

| O'zgaruvchi | Vazifa | Deploy |
|---|---|---|
| `ENVIRONMENT` | `development` / `production` | **`production`** |
| `DEBUG` | debug rejim | **`False`** |
| `SECRET_KEY` | JWT imzo kaliti | **MAJBUR** — `python -c "import secrets; print(secrets.token_hex(32))"` (kuchsiz → server ishga tushmaydi) |
| `DATABASE_URL` | PostgreSQL ulanishi | `postgresql://user:pass@host:5432/db` |
| `BACKEND_CORS_ORIGINS` | ruxsat domenlari | **faqat o'z domening** (`["https://xenora.uz"]`); `"*"` taqiqlangan |
| `FIRST_SUPERUSER_PHONE` | super-admin telefon (login kaliti) | o'z raqamingiz |
| `FIRST_SUPERUSER_PASSWORD` | super-admin parol | **MAJBUR** — kuchli (standart `admin4770` → server ishga tushmaydi) |
| `FIRST_SUPERUSER_EMAIL` / `_NAME` / `_USERNAME` | super-admin profil | ixtiyoriy |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | sessiya (720 / 30) | odatda standart |
| `RATE_LIMIT_*` | brute-force himoya (auth 20 / umumiy 600 per-min) | standart yetarli |
| `CLICK_*` / `PAYME_*` | onlayn to'lov kalitlari (maxfiy) | to'lov yoqilsa merchant kabinetdan |
| `SMS_*` / `SMTP_*` | SMS / email | ixtiyoriy |
| `BACKUP_*` | zaxira konfiguratsiyasi | standart |

---

## 2C. Native app build

**Windows desktop (Electron):**
- `electron/electron-builder.json` — `appId: com.xenora.app`, `productName: XENORA`.
- Build: `cd electron && npm install && npm run build` (yoki `electron-builder`). Girih yulduz splash/logo.
- Xususiyat: kunlik avtomatik tenant backup (14:00, 22:00 → `Documents/XENORA-Backup/`).

**Android / iOS (Capacitor):**
- `capacitor.config.json` — `appId: com.xenora.app`, `appName: XENORA`, `webDir: frontend`.
- Android: `npx cap sync android && npx cap open android` → Android Studio'da build (keystore: `xenora.keystore`).
- Splash `#07070f`, tilla urg'u (`#d4af37`).

---

## 3. Ma'lum muammolar

> Audit: 2026-06-21. Deploy-blokerlar **tuzatildi** (quyida ✅).

### ✅ Tuzatilgan (2026-06-21)
- **`employee.py` cross-tenant teshigi** — barcha 10 endpoint `apply_tenant_filter` + `_assert_cafe_access` bilan tenant'ga cheklandi; boshqa tenant so'rovi 403; `by-pin` ga auth+scope qo'shildi. Jonli sinov: tenant user faqat o'z tenantini ko'radi, super-admin bypass saqlandi.
- **`Product.stock_quantity` fantom-maydon** — `departments.py` (`_stock_qty`/`_min_threshold` Inventory'dan), `quick_sell.py` (Inventory + `sale_unit`), `purchase_orders.py` (qabul endi `Inventory.quantity` ni yangilaydi). `StockMovement.unit`/`Inventory.unit` o'zgartirilmadi.
- **`cafe.py /all` va `/{id}`** — tenant izolyatsiya: oddiy user `/all`'da faqat o'z kafesini, `/{id}`'da boshqa tenant → 403 (super-admin bypass). UI buzilmadi.
- **`GET /auth/me` 500** — `RoleInDB`/`PermissionInDB.created_at` `Optional` qilindi (eski/edge NULL yozuvda ResponseValidationError bermasin).
- **`barcodes.py lookup` 500** — `p.unit`→`p.sale_unit`, `stock_quantity` olib tashlandi (oldingi turda).

### ✅ Tuzatilgan (2026-06-23)
- **Tarozi shtrix-kod wiring bug** — `handleBarcodeScan` `addToCart`'ga OBYEKT uzatardi (`presetWeight` RAQAM kutadi) → `parseFloat(obyekt)=NaN→0`, og'irlik/narx 0. Endi `addToCart(found.id, weightKg)` (raqam); lookup `unit`→`sale_unit` ham moslandi. Dona oqimi buzilmadi.

### ✅ Tuzatilgan (2026-07)
- **Offline sync** — `api.js` javob `{success,data,offline}` shaklida wrap qilindi; `sync.js` `res.data.id` ga moslandi; tarmoq xatosi vs server xatosi farqlandi (offline buyurtma yo'qolmaydi).
- **Xodim faolsizlantirish** — `User.is_active=False` bo'lsa keyingi so'rov/refresh 401 (jonli chiqarish) — auto-refresh oqimida ham tekshiriladi.
- **Inventar ikki marta chiqim** — retsept/sotuv ombordan ikki marta kamaytirar edi; `Order.ingredients_deducted` bayrog'i qo'shildi (migration `d4e5f6a7b9c0`) — idempotent.
- **Refresh token** — auto-refresh JSON body bilan to'g'rilandi (avval xato format edi).
- **Smena / kassa TypeError**, **skaner lookup**, **main.css 404** (self-contained tema), **PIN dublikat** (tenant ichida noyoblik) — barchasi tuzatildi.
- **Super-admin login hardcode** — `database.py` dan `+998949974770`/`admin4770` olib tashlanib env'ga (`FIRST_SUPERUSER_*`) ko'chirildi (2026-07-03).

### 🟡 Qolgan (past prioritet)
- **`TELEGRAM_BOT_TOKEN`** `config.py`'da yo'q (`extra=ignore`) → telegram bot token o'qilmaydi.
- **PRO endpointlar backendda flag-gate qilinmagan** (faqat `z_report print-z` da). API orqali PRO funksiya chaqirilishi mumkin (UI yashiradi, backend bloklamaydi).
- **Test qoplamasi past** — faqat 4 fayl (`test_auth/health/orders/products`).

### Arxitektura qarzi (chalkashlik)
- **Ikki xil "xodim" tizimi:** `User` (rol, tenant-filtrli) vs `Employee` (alohida jadval, tenant-filtrsiz) — yuqoridagi teshikning sababi.
- **Ikki smena UI:** `shift.html` (mustaqil) + `admin.html` "Kassa Smena" — mantiq takrori.
- **Ikki "stock" modeli:** `Inventory` (to'g'ri) vs `Product.stock_quantity` (fantom).
- ~~**Firma ikki tizim (A/B):**~~ ✅ Hal qilindi (Bosqich 6, 2026-06-23) — Tizim A to'liq olib tashlandi, yagona B2B tizim qoldi (`ARCHITECTURE.md §2.1`).

---

## 4. Hali qilinmagan / kelajak

- Backend feature-flag gating (PRO endpointlarni `is_pro_feature` bilan himoyalash).
- Redis (cache/queue) — hali rejada.
- Test qoplamasini kengaytirish (75+ router uchun).
- `employee.py` ni `user.py` ga konsolidatsiya (ikki xodim tizimini birlashtirish).
- **Pharmacy formaga `sale_unit`/PLU qo'shish** — dorixona kg mahsulotlari uchun tarozi PLU.
- SSL sertifikat (Let's Encrypt) — `make ssl-init` tayyor, sertifikat olinishi kerak.
- **DEPLOY:** VPS, `.uz` domen, SSL, birinchi mijoz.
