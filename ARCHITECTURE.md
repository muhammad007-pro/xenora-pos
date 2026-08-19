# XENORA — Arxitektura

> **XENORA** — universal, ko'p-ijarali (multi-tenant) SaaS POS. Bitta dastur — har xil biznes turi
> (restoran, kafe, magazin, dorixona, salon...). Funksiyalar feature-flag bilan yoqiladi.
> (Kod ichida eski nom `RestoPOS` va `restopos_*` prefikslari saqlanib qolgan — bir xil tizim.
> Native app / brend nomi: **XENORA**, `appId com.xenora.app`, zumrad-tilla premium dizayn, girih yulduz logo.)
>
> Bu hujjat tizimning **kanonik arxitektura ma'lumotnomasi**. Bosqichma-bosqich qurilish
> tarixi va funksiyalar holati uchun → `BUILD.md`.

---

## 1. Umumiy ko'rinish

| Qatlam | Texnologiya |
|---|---|
| Backend | FastAPI (Python 3.11), sinxron SQLAlchemy 2.0 |
| Ma'lumotlar bazasi | PostgreSQL, Alembic migratsiya (head: `d4e5f6a7b9c0`) |
| Auth | JWT (access 12s + refresh 30 kun, auto-refresh); kirish: **do'kon kodi + PIN**, parol, PIN |
| Realtime | WebSocket (oshxona KDS, ofitsiant chaqirish) |
| Frontend | Vanilla HTML/CSS/JS, PWA (Service Worker, IndexedDB `restopos_db` offline) |
| Desktop/Mobil | Electron (asosiy, `com.xenora.app`), Capacitor (Android/iOS), Tauri |
| Deploy | Docker Compose (nginx + backend + postgres); toza baza + super-admin env'dan |

**Asosiy oqim:** brauzer/PWA → `nginx` (HTTPS) → FastAPI (`/api/v1/...`) → PostgreSQL. Statik frontend
backend orqali `/frontend` ostida ham xizmat qilinadi (`main.py`).

**4 ustun:** Universal (feature-flag) · Offline-first (IndexedDB + sync) · Multi-tenant (tenant_id) · Multi-platform.

**Xavfsizlik ustunlari:** SECRET_KEY env + production_checks · rate limit (auth 20/min, umumiy 600/min) ·
bcrypt parol/PIN · JWT RBAC · tenant izolyatsiya (`apply_tenant_filter`) · audit log · tenant-scoped backup/restore.

---

## 2. Asosiy modellar va bog'lanishlar

`backend/models.py` (yagona fayl). Deyarli har bir jadvalda `tenant_id` (→ `cafes.id`) bor.

```
Cafe (tenant)  ─1─*─ Branch ─1─*─ CashRegister
  │                                   │
  │ enabled_features / disabled_features (JSON override)
  │ business_type, subscription_plan (free/pro)
  │ access_code (100.200.N — do'kon KIRISH kodi, unique)
  │
  ├─*─ User ──*─1── Role ──*─*── Permission
  │       │ (role_id, tenant_id, branch_id, hashed_pin)
  │
  ├─*─ Station (oshxona bo'linma) ──*── Product/OrderItem.station_id
  ├─*─ AuditLog (tenant_id, xodim harakati: order/product/shift/return/login)
  │       └─1─*─ Shift (register_id, user_id, starting_cash, counted_cash, shortage)
  │                 │
  │                 └─1─*─ Order (shift_id)  ← Z-hisobot shift_id bo'yicha yig'adi
  │
  ├─*─ Category ─1─*─ Product (barcode, category_id MAJBURIY, image_url, sale_unit, cost_price)
  │                      │   ├─*─ ProductBarcode (multi-barcode; tarozi PLU = weight_variable=True)
  │                      │   └─*─ ProductBatch (partiya: batch_number, expiry_date, manufacture_date,
  │                      │                       quantity, initial_quantity, cost_price)  ← Inventory'ga PARALLEL
  │                      └─1─1─ Inventory (quantity, min_threshold)  ← yagona to'g'ri "stock" manbai
  │
  ├─*─ Order ─1─*─ OrderItem ──*─1── Product
  │       └─1─*─ Payment (method: cash/card/click/credit, status)
  │
  ├─*─ Supplier ─1─*─ PurchaseReceipt ─1─*─ PurchaseReceiptItem (batch_number, expiry_date, manufacture_date)
  │                  │   (priyomka: draft → confirm → Inventory.quantity += , Product.cost_price,
  │                  │    StockMovement [in/purchase], ProductBatch [expiry bo'lsa, duplicate=merge])
  │                  └─*─ SupplierReturn / SupplierPayment  (qarz DINAMIK: debt-summary = priyomka − to'lov − vozvrat)
  ├─*─ Return / ReturnItem (qaytarish)
  ├─*─ CustomerDebt / DebtPayment (nasiya)
  └─*─ Recipe / WasteLog / ... (biznesga xos)
```

**Muhim qoidalar:**
- Ombor qoldig'i **faqat `Inventory` jadvalida**. `Product`da `stock_quantity` ustuni **yo'q** (ba'zi eski endpointlar bunga noto'g'ri tayanadi — `BUILD.md` "Ma'lum muammolar").
- **`ProductBatch` (partiya/seriya, dorixona) `Inventory`'ga PARALLEL:** `Inventory.quantity` = umumiy qoldiq (POS shundan o'qiydi, **haqiqat manbai**), `ProductBatch.quantity` = partiya detali (expiry-report). Ikkalasi **hech qaysi joyda qo'shilmaydi** (aks holda miqdor ikki marta sanaladi).
- `Order.shift_id` — buyurtma yaratilganda kassirning joriy ochiq smenasiga avtomatik bog'lanadi.
- `Product.category_id` — **majburiy** (mahsulot yaratishda kategoriya shart).

### 2.1 Firma tizimi (yagona — B2B)

| Qatlam | Tarkib |
|---|---|
| Router | `suppliers.py` → `/api/suppliers-b2b`, `purchase_receipts.py`, `supplier_payments.py`, `supplier_returns.py` |
| Kirim modeli | `PurchaseReceipt` (+ `PurchaseReceiptItem`: `batch_number`, `expiry_date`, `manufacture_date`) |
| Qarz | DINAMIK hisoblanadi (`/suppliers-b2b/debt-summary` = priyomka − to'lov − vozvrat); `SupplierPayment.receipt_id` |
| Partiya/expiry | ✅ `ProductBatch` (confirm'da, expiry bo'lsa, duplicate=merge) |
| UI | `suppliers.html` / `purchase_receipts.html` / `supplier_debt.html` — admin.html navga ulangan (nav-feature) |

> **Eski Tizim A** (`supplier.py` `/api/suppliers`, `purchase_orders.py`, `PurchaseOrder`/`PurchaseOrderItem`, `SupplierPayment.po_id`) **Bosqich 6'da (2026-06-23) to'liq olib tashlandi** — router/model/frontend/jadval (migration `b5c6d7e8f9a0`). `SupplierPayment` modeli saqlanadi (faqat `receipt_id`). Reorder dropdownlari `/suppliers-b2b/` ga ko'chirildi.

---

## 3. Tenant izolyatsiya mexanizmi

Har bir ijarachi (kafe/do'kon) = bitta `Cafe` yozuvi. `Cafe.id` = `tenant_id`.

- **Stamp (yozish):** yangi yozuv yaratilganda `tenant_id = resolve_tenant_id(db, current_user)` (`deps.py`).
- **Filter (o'qish):** so'rovlar `apply_tenant_filter(query, Model, current_user)` orqali cheklanadi
  (super-admin uchun filtersiz, oddiy user uchun `Model.tenant_id == current_user.tenant_id`).
- **PIN login:** `branch_id → branch.tenant_id` → PIN faqat shu tenant ichida qidiriladi (`auth.py`).
- **Public QR:** `cafe_code → cafe.id` → menyu/buyurtma shu tenantga bog'lanadi (`public.py`).

> ✅ Audit (2026-06-21): `employee.py` va `cafe.py` cross-tenant teshiklari yopildi —
> barcha xodim/kafe endpointlari `apply_tenant_filter` + access-check bilan tenant'ga cheklangan.

---

## 4. Kirish (autentifikatsiya) tizimi

Kirish **do'kon kodi + PIN** ustiga qurilgan — email/username telefon raqamlarini boshqa
tenantlar ko'ra olmaydi. Uch xil kirish yo'li:

**A) Do'kon kodi + PIN (asosiy — kassir/ofitsiant/oshpaz):**
1. Har tenant (`Cafe`) noyob **`access_code`** ga ega — format `100.200.N` (`Cafe.access_code`, unique, index).
2. `GET /auth/resolve-code?code=100.200.N` → kod tekshiriladi, tenant nomi/branch qaytadi (parolsiz, faqat mavjudlikni tasdiqlaydi).
3. `POST /auth/pin-login` → PIN **faqat shu tenant ichida** qidiriladi (`branch_id → branch.tenant_id`); PIN bcrypt (`hashed_pin`). Muvaffaqiyatli → JWT (access + refresh).

**B) Telefon + parol (admin/egasi):** klassik login (`POST /auth/login`), telefon login kaliti (super-admin: `+998949974770`).

**C) Super-admin (platforma egasi) alohida yo'l:** `login.html` kod ekranida "Platforma administratori" → kodsiz telefon+parol → `owner/cafes.html`. Super-admin `settings.FIRST_SUPERUSER_*` (env) orqali toza bazada avtomatik yaratiladi.

**Uzoq sessiya (xodim smenasi buferi):**
- Access token **12 soat** (`ACCESS_TOKEN_EXPIRE_MINUTES=720`), refresh token **30 kun**.
- Access tugasa frontend `POST /auth/refresh` (JSON body) bilan **avtomatik yangilaydi** — kassir qayta login qilmaydi.
- Admin xodimni faolsizlantirsa/o'chirsa → `User.is_active=False` → keyingi so'rov/refresh **401** → xodim chiqadi (jonli bloklash).

---

## 5. Xavfsizlik modeli

| Qatlam | Mexanizm |
|---|---|
| **SECRET_KEY** | `.env` (majburiy). `production_checks` (config.py) — production'da kuchsiz/standart kalit (<32 belgi yoki "change/example"...) → server ishga tushmaydi |
| **Super-admin login** | `FIRST_SUPERUSER_PHONE/PASSWORD/EMAIL/NAME/USERNAME` env'dan (hardcode YO'Q). Production'da standart/kuchsiz parol (`admin4770`, <8 belgi) → server ishga tushmaydi |
| **Rate limit** | Middleware (IP boshiga): auth 20/min (login/pin-login/register/change-password), umumiy 600/min. `RATE_LIMIT_*` env |
| **Parol / PIN** | bcrypt hash (`core/security.py get_password_hash`); PIN ham hash (`hashed_pin`) |
| **JWT RBAC** | `deps.has_permission(...)` endpoint himoyasi; `get_current_superuser` super-admin; frontend `auth-guard.js` (403 ekran) |
| **Tenant izolyatsiya** | `apply_tenant_filter` (o'qish) + `resolve_tenant_id` stamp (yozish); `tenant_id` deyarli har jadvalda (~66 jadval) |
| **CORS** | `BACKEND_CORS_ORIGINS` env — production'da faqat o'z domeni (`"*"` taqiqlangan, `allow_credentials=True` bilan xavfli) |
| **Audit** | xodim harakatlari yoziladi (§8) |
| **Register parol** | minimal 6 belgi (deploy xavfsizlik) |

---

## 6. Zaxira / tiklash (backup / restore)

Ikki daraja — **tenant-scoped** (do'kon egasi, izolyatsiyalangan) va **server** (super-admin, to'liq):

**Tenant (do'kon egasi):**
- `GET /backups/my-tenant` — faqat o'z tenant ma'lumotini **JSON.gz** (gzip) qilib beradi (izolyatsiyalangan — boshqa tenant ko'rinmaydi).
- `POST /backups/my-tenant/restore` — o'z zaxirasidan tiklaydi: **tranzaksiya** ichida, safety-guard bilan, `tenant_id` majburlanadi; **users / obuna saqlanadi** (faqat operatsion ma'lumot almashadi).
- **Electron avtomatik:** kunda 2 marta (**14:00 va 22:00**) yuklab, `Documents/XENORA-Backup/` ga saqlaydi (`frontend/js/core/tenant-backup.js` SLOTS, `electron/main.js` `backup:save`). Widget: **Hozir** (qo'lda) / **↺ Tiklash** / **📁** (papkani ochish).

**Server (super-admin):**
- `GET /backups/` ro'yxat · `POST /backups/` yaratish (**pg_dump**) · `POST /backups/restore/{file}` tiklash. Faqat `get_current_superuser`.

---

## 7. Oshxona (KDS) va stansiya tizimi

**Sodda oqim** (kassir/oshpaz uchun tez): `kitchen.html` yagona grid — har zakaz kartochkasi **1 bosishda tayyor** bo'ladi. Har zakazda **vaqt sanagich** (15 daqiqagacha havorang → keyin qizil — kechikkanini ko'rsatadi). "Tayyor" zakazlar alohida panelga o'tadi + **reopen** (qayta ochish) imkoni.

**Stansiya tizimi (`Station` modeli, `station.py`):** oshxona bo'linmalarga bo'linadi (masalan grill, salat, ichimlik). `Product`/`OrderItem` `station_id` bilan bog'lanadi; oshxona ekrani `station_id` bo'yicha **filtrlaydi** (har povar faqat o'z stansiyasini ko'radi). Povar oshxona ekranida gear (⚙) orqali o'z stansiyasini tanlaydi — tanlov `localStorage`da saqlanadi. **Displeysiz stansiya** ham mumkin (jismoniy ekran shart emas). Realtime yangilanish WebSocket orqali.

---

## 8. Audit log

`AuditLog` modeli (`models.py`, `core/audit.py`) — xodim harakatlarini yozadi:
- **Yoziladigan harakatlar:** buyurtma (order), mahsulot (product), smena (shift), qaytarish (return), login.
- Har yozuvda **`tenant_id`** (izolyatsiya) + foydalanuvchi + harakat turi + vaqt + tafsilot.
- **Xavfsiz yozish:** audit alohida DB sessiyada yoziladi (asosiy tranzaksiya rollback bo'lsa ham audit yo'qolmaydi/buzilmaydi).
- **Ko'rish:** `admin.html` → "Xodimlar faoliyati" paneli (`routers/audit.py`, tenant-filtrli).

---

## 9. Feature-flag tizimi (FREE / PRO)

> **Faqat ikki tarif: FREE / PRO.** Enterprise tier UI/`FeatureTier`'dan **olib tashlandi**
> (`FeatureTier` faqat `FREE`/`PRO`). `core/subscription.py PLAN_LIMITS`'da `enterprise` legacy
> fallback sifatida qolgan (ochiq tarif emas — sotilmaydi). `PLAN_LIMITS`: FREE = 3 user / 1 filial /
> 100 buyurtma-oy; PRO = 20 user / 5 filial / cheksiz.

`backend/core/feature_flags.py` — yagona manba. **Ikki alohida struktura** (chalkashtirmaslik kerak):

- **`BUSINESS_FEATURE_MATRIX`** — har biznes turi uchun standart (default) YOQILGAN to'plam.
- **`FEATURE_TIERS`** — har flagning darajasi (FREE/PRO).
- Bu ikkisi mustaqil: flagni **default to'plamdan olib tashlash** ≠ uni **PRO tier** qilish. Flag PRO bo'lsa-da, default'da bo'lishi mumkin emas (monetizatsiya).

**Biznes-guruh frozensetlari (DRY):** bir oilaga kiruvchi turlar bir xil to'plamni oladi:
- **`FOOD_FEATURES`** (~22 flag, union) → `restaurant` + `cafe` + `fast_food`.
- **`RETAIL_FEATURES`** (14 flag, faqat FREE) → `store` + `supermarket`.
- `pharmacy` / `salon` / `hotel` / ... — o'z to'plamlari.

**Monetizatsiya qoidasi:** `retail` va `pharmacy` default'idan PRO flaglar (`supplier_accounting`, `supplier_card`, `purchase_receipt`, `supplier_debt`, `supplier_return`, `write_off`, `goods_regrade`, `markup_policy`, ...) **olib tashlangan** — ular faqat super-admin `enabled_features` orqali qo'lda yoqiladi.

- **`Cafe.enabled_features` / `disabled_features`** — tenant-darajadagi qo'lda override (JSON).
- **`resolve_enabled_features(business_type, enabled, disabled)`** — yakuniy yoqilgan to'plam.
- **Tier xulq-atvori:**
  - **FREE** — tenant egasi `settings`'dan o'zi yoqadi/o'chiradi.
  - **PRO** — faqat super-admin yoqa oladi; tenant o'zi yoqsa **403** (`cafe.py PATCH /my/features`).

| Tier | Misol flaglar |
|---|---|
| **FREE** | `inventory`, `barcode`, `multi_barcode`, `cash_register`, `z_report`, `receipt_settings`, `returns`, `quick_sell`, `loyalty`, `kitchen_display`, `table_management`, `qr_menu`, `modifiers`, `happy_hour`, `recipe`, dorixona/salon flaglari |
| **PRO** | `wholesale_pricing`, `departments`, `supplier_accounting`, `supplier_card`, `purchase_receipt`, `supplier_debt`, `supplier_return`, `write_off`, `goods_regrade`, `internal_transfer`, `markup_policy`, `bonus_card`, `markirovka`, `abc_analysis`, `auto_reorder`, `turnover_analysis`, `peak_hours`, `loss_report` |

**Frontend ↔ backend mosligi:** `frontend/js/core/features.js` (`features.has(...)`) backend `resolve_enabled_features` bilan bir xil enum/mantiqdan foydalanadi; `/cafes/my/features` orqali yuklab, localStorage'da keshlaydi. `FEATURE_MATRIX` (offline/fallback default) backend bilan **sinxron** — supplier PRO flaglar retail/pharmacy default'idan olib tashlangan (monetizatsiya teshigi yopildi).

### 9.1 Frontend nav gating

- **`nav-feature-<flag>` klassi:** nav-item shu klassga ega bo'lsa, faqat flag yoqilgan tenantда ko'rinadi (`admin.html` `showNavGroup`; `sidebar.js` standalone sahifalar uchun). Flag o'chsa — nav yashirin.
- **Biznes-guruh klasslari:** `nav-store`, `nav-pharmacy`, `nav-salon`... `showNavGroup('.nav-store')` faqat tegishli biznes turida (`_storeTypes`, `_restTypes`...) chaqiriladi. Firma navlari (`Firmalar`/`Priyomka`/`Qarzlar`) `nav-store nav-pharmacy nav-feature-supplier_*` bilan ulangan.
- **`orders` navi** (aktiv buyurtma oqimi) faqat food oilasida (`_restTypes`) ko'rinadi; boshqa bizneslarda sotuvlar `salesHistory`'da.
- **Settings biznes-turiga moslash:** `cafes/my/features` `in_business` bayrog'i — tenant biznesiga **begona** funksiya kulrang/disabled ko'rsatiladi; backend ham bunday flagni saqlamaydi (403/skip).

---

## 10. Rol tizimi

`Role` / `Permission` — **global** (tenant_id yo'q), tizim-bo'ylab umumiy ta'riflar. User `role_id` orqali bog'lanadi.

**Frontend RBAC** — `frontend/js/core/auth-guard.js`:
- `canonicalRole(name)` — rol nomini guruhга keltiradi: `admin`, `manager`, `cashier`(=kassir/sotuvchi), `chef`(=oshpaz), `waiter`(=ofitsiant), `pharmacist`(=farmatsevt)...
- `PAGE_ROLES` — har sahifa → ruxsat etilgan rollar:
  - **admin/manager** → hamma sahifa
  - **cashier (kassir)** → POS, smena, mijozlar, loyalty, barkod
  - **chef (oshpaz)** → faqat oshxona ekrani
  - **waiter (ofitsiant)** → POS, stollar
- Ruxsatsiz sahifada **403 ekran** (redirect emas). `AuthGuard.check()` har sahifaga qo'shilgan.

**Backend** — `deps.has_permission("...")` dependency endpointlarni himoyalaydi; `get_current_superuser` super-admin uchun.

---

## 11. Asosiy routerlar (`backend/routers/`, prefix `/api/v1`)

| Router | Vazifa |
|---|---|
| `auth` | login (parol/PIN), `resolve-code` (do'kon kodi), `pin-login` (tenant-scoped), refresh (auto), me, branch almashtirish |
| `user` / `role` | foydalanuvchi (tenant-filtrli) / rol-ruxsat (global) |
| `cafe` | tenant metadata, `/my/features` (FREE/PRO boshqaruv) |
| `super_admin` | platforma egasi — barcha tenantlar; do'kon boshqaruvi (tarif Free↔Pro, `access_code` ko'rsatish, admin parol/telefon reset) |
| `backup` | tenant zaxira/tiklash (`/my-tenant`, `/my-tenant/restore`, JSON.gz) + server pg_dump (super-admin) |
| `audit` | xodim faoliyati logi (tenant-filtrli ko'rish) |
| `station` | oshxona stansiyalari (bo'linma, `station_id` filtri) |
| `category` / `product` | kategoriya / mahsulot (barcode, rasm, narx) |
| `barcodes` | multi-barcode lookup (skaner), tarozi PLU |
| `inventory` | ombor: qoldiq, kirim (add-stock), inventarizatsiya |
| `purchase_receipts` / `suppliers` | priyomka (B2B), firma |
| `order` / `order_item` / `payment` | buyurtma, element, to'lov |
| `kitchen` / `station` | oshxona ekrani (KDS), stansiyalar |
| `table` / `reservation` | stol boshqaruvi / bron |
| `cash_register` / `shift` | multi-kassa / smena + Z-hisobot + kassa farqi |
| `returns` / `debt` | qaytarish / nasiya |
| `loyalty` / `membership` / `bonus_cards` | sodiqlik / abonement / bonus karta |
| `report` / `analytics` / `profit` | hisobotlar, tahlil, foyda |
| `settings` | printer / fiskal / backup konfiguratsiyasi |
| `public` | QR-menyu (autentifikatsiyasiz, cafe_code bo'yicha) |
| biznesga xos | `prescription`, `batches`, `appointment`, `service`, `vehicle`, `hotel`, `staff_schedule`, `write_offs`, `markirovka`, ... |

### 11.1 Tarozi shtrix-kod / PLU oqimi (kg mahsulot)

Tarozi go'sht/sabzavot/meva uchun **og'irlik kodlangan EAN-13** chiqaradi:
- **Format:** `[prefix 2][PLU 5 raqam][og'irlik 5 raqam, gramm][checksum]`. Prefix `20|21|22|23|29`.
  `PLU = barcode[2:7]`, `og'irlik(gramm) = barcode[7:12]`.
- **Backend parse:** `barcodes.py` `lookup_barcode` + `_parse_weight_barcode`. PLU `ProductBarcode.barcode` (5 raqam) + `weight_variable=True` orqali mahsulotga bog'lanadi. Qaytaradi: `weight_kg`, `calculated_price = price × weight_kg`.
- **POS oqimi (`pos.js`):** skaner → `/barcodes/lookup/{code}` → `weightKg` → `addToCart(found.id, weightKg)` (RAQAM) → `doAddToCart` og'irlik narxini (`unitPrice × weightKg`) hisoblaydi, savatga 1 qator (qty=1, `_weight`).
- **PLU biriktirish UI:** `admin.html` mahsulot formasida `sale_unit='kg'` (yoki g/l/ml) tanlansa "Tarozi PLU" maydoni ko'rinadi → `POST /barcodes/ weight_variable=true`.
- **Skaner ovozi:** `beep('add')` (savatga tushdi) / `beep('error')` (topilmadi) — `pos.js`. Elektron tarozi (Web Serial) `connectScale` — alohida.

---

## 12. Fiskal / Printer arxitekturasi

**Yadro va ulanish ajratilgan** (fiskal OFD pattern):

```
escpos_service.py   →  ESC/POS BAYT generatsiyasi (printerga bog'liq emas)
                        build_receipt / build_z_report / render_text / render_z_report
        │
        ▼
printer_service.py  →  baytni YUBORISH (rejimga qarab):
                        mock  | network (IP:9100) | usb (vendor/product id) | spooler (COM/lp0)
                        real rejim xato bersa → MOCK fallback (chek yo'qolmaydi)
```

- Konfiguratsiya: `config/printer.json` (`mode`, `enabled`, `width`, `ip`, ...) — `settings` orqali boshqariladi.
- **Mock rejim** (default): bayt `.bin` + o'qiladigan matn `.txt` `static/receipts/` ga yoziladi — printer bo'lmasa ham butun oqim ishlaydi.
- **Fiskal OFD:** `Order.fiscal_number/fiscal_qr_url/fiscal_sent_at`; chekka `consumer.invoice.uz` QR kod (`escpos d.qr()`). Yoqilmasa — oddiy chek.
- Z-chek (`build_z_report`) shu universal printer qatlamidan foydalanadi.

---

## 13. Offline-first (PWA)

- `frontend/pwa/service-worker.js` — statik kesh, offline sahifa.
- `frontend/js/core/db.js` (IndexedDB `restopos_db`) + `sync.js` — lokal saqlash va serverga sinxronlash.
- **API contract:** `api.js` javobni `{success, data, offline}` shaklida wrap qiladi; `pos.js`/`sync.js` shunga moslangan (`res.data.id`). Bu **tarmoq xatosi** (offline navbatga) va **server xatosi** (ko'rsatiladi) ni farqlaydi — offline buyurtma yo'qolmaydi.
- Offline'da: buyurtma, to'lov (checkout), chek, mahsulot ko'rish, stol boshqaruvi ishlaydi; internet tiklanganda navbat avtomatik yuboriladi.

---

## 14. Katalog tuzilishi

```
cafe/
├── backend/
│   ├── main.py            → FastAPI app, router mount, static mount, rate-limit middleware
│   ├── models.py          → barcha ORM modellar (Cafe.access_code, Station, AuditLog, ...)
│   ├── schemas.py         → Pydantic sxemalar
│   ├── config.py          → Settings (.env) + production_checks (SECRET_KEY, FIRST_SUPERUSER)
│   ├── database.py        → engine, init_db (super-admin env'dan seed)
│   ├── deps.py            → get_current_user, has_permission, resolve_tenant_id, apply_tenant_filter
│   ├── core/              → feature_flags (FREE/PRO), security, middleware (rate-limit), logger, audit, subscription
│   ├── routers/           → API endpointlar (~78 ta; auth, backup, audit, station, super_admin, ...)
│   ├── services/          → biznes mantiq (order, payment, escpos, printer, cost, recipe_inventory)
│   ├── tasks/             → scheduler, backup (pg_dump)
│   ├── websocket/         → realtime (kitchen, waiter)
│   └── migrations/        → Alembic (head: `d4e5f6a7b9c0` order_ingredients_deducted)
├── frontend/
│   ├── app/               → asosiy sahifalar (pos, admin, kitchen, inventory, shift, ...)
│   ├── shared/            → login.html (kod + PIN, super-admin yo'li)
│   ├── js/core/           → api ({success,data} contract), auth-guard, features, sync, db (restopos_db), tenant-backup, config
│   ├── js/modules/        → sahifa mantig'i (pos.js, ...)
│   ├── pwa/               → service-worker, offline-cache
│   └── owner/             → SaaS owner panel (cafes.html)
├── electron/             → Windows desktop app (XENORA, com.xenora.app); kunlik tenant backup (14:00/22:00 → Documents/XENORA-Backup)
├── android/ + capacitor.config.json → Android/iOS (XENORA, com.xenora.app)
└── nginx/               → reverse proxy (HTTPS, deploy)
```
