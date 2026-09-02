# XENORA POS — Deploy qo'llanmasi

> Bu fayl production deploy tafsilotini saqlaydi — **har yangi sessiyada shu yerdan o'qing**, qayta izlamang.
> 🆕 **SERVER ALMASHDI (2026-08-12):** eski droplet `146.190.225.168` yo'q qilingan, yangi server **`178.128.251.218`** (`xenora-2pos`) noldan qurildi va 22.07 zaxirasidan tiklandi. Tafsilot §11.
> Oxirgi tasdiqlangan deploy: **v1.4.0** (2026-07-21) — **PRINT TIZIMI (markaziy servis)**: barcha print (chek, Z-hisobot, kunlik hisobot) bitta `printDocument` (Electron main.js) dan o'tadi; `print_type` (usb/lan/qr) transportni tanlaydi — USB=SumatraPDF (hozirgi), LAN=stub ("tez orada"), QR=stub. Chek sozlamasida "Print turi" + IP/port UI. Z-hisobot to'liq (SOTILGAN MAHSULOTLAR breakdown + kamomad). Kunlik hisobot (report.html) 58mm markaziyga (grafik/panel EMAS). Barcha `window.print()` (butun panel) → markaziy (etiketka/QR/legacy alohida media, tegilmadi).
> ⚠️ **MIGRATSIYA BOR (B0):** `d0e1f2a3b4c5` — `receipt_settings.print_type/printer_ip/printer_port` (nullable, `print_type` default 'usb', idempotent). `c9d0e1f2a3b4`→`d0e1f2a3b4c5`. Android versionCode **20** / 1.4.0.
> ⚠️ **BACKEND DEPLOY SHART:** shift.py (Z-hisobot products/avg_order/store_name), receipt_settings.py (print config), models.py + migratsiya. `alembic upgrade head` MAJBURIY. Backup majburiy.
> ⚠️ **BUILD SHART + SumatraPDF:** Chek Electron .exe'да. Build oldin `electron/vendor/SumatraPDF.exe` (20MB, git'да yo'q — build mashinasida lokal) bo'lishi SHART — `extraResources` uni `resources/`ga nusxalaydi. Busiz GDI fallback (krakozyabra).
> (Oldingi: v1.3.2 Chek chapga surish margin:0; v1.3.1 Chek narx 48mm+shrift o'lchami; v1.3.0 Chek 54mm+QR toggle+atir+POS tarix/ombor; v1.2.8 capturePage raster; v1.2.7 avtomatik chek+HTML GDI; v1.2.6 did-finish-load+pageSize yo'q; v1.2.5 deviceName default+58mm; v1.2.4 Chek lokal silent print; v1.2.3 Sodiqlik [`c9d0e1f2a3b4`]; v1.2.2 Pachka/Dona; v1.2.1 brend ∞; v1.2.0 RBAC audit; v1.0.3 `8800a6d`.)

---

## 1. Server (production)

| | |
|---|---|
| **Provayder** | DigitalOcean droplet |
| **IP** | `178.128.251.218` (SSH shu IP orqali — DNS'ga bog'liq emas) |
| **Domen** | **`https://xenora.uz`** + `https://www.xenora.uz` — mijoz/client manzili (2026-08-20 dan) |
| **SSL** | Let's Encrypt, certbot 5.7.0 (snap); avto-yangilanish `snap.certbot.renew.timer` |
| **Host / user** | `root@xenora-2pos` (Ubuntu 24.04.4 LTS) |
| **Resurs** | 1 vCPU, 1 GB RAM (+ **2 GB swap** `/swapfile`, fstab'da), 33 GB disk |
| **Kod joyi** | `/opt/xenora` (git `main` branch) |
| **Backend xizmati** | **systemd** — `xenora.service` (⚠️ **DOCKER EMAS**) |
| **Backend runtime** | venv uvicorn → `127.0.0.1:8000` (**1 worker** — WebSocket in-process broadcast; ko'p worker BUZADI) |
| **Web server** | nginx 1.24 — `/opt/xenora/frontend` ni serve qiladi + `/api` `/ws` `/health` `/uploads` `/static` `/public` `/docs` → `127.0.0.1:8000` proxy |
| **DB** | PostgreSQL **16.14** (native) — baza `xenora_db`, user `xenora_user`; migratsiya venv alembic bilan |
| **Firewall** | UFW **faol** — `22/tcp`, `80/tcp`, `443/tcp` ochiq, qolgani deny |
| **SSH** | **Faqat kalit** (`PasswordAuthentication no`) — parol bilan kirish o'chirilgan |

Muhim yo'llar:
- venv: `/opt/xenora/backend/venv`
- alembic: `/opt/xenora/backend/venv/bin/alembic` (WorkingDirectory = `/opt/xenora/backend`)
- `.env`: `/opt/xenora/backend/.env` (ruxsat 600, **faqat serverda**, git'da yo'q)
- nginx config: `/etc/nginx/sites-available/xenora` — **3 ta server bloki**, umumiy qoidalar
  `/etc/nginx/snippets/xenora-common.conf` ichida:
  1. `listen 80 default_server; server_name _;` — IP va noma'lum Host. **SSL yo'q, redirect YO'Q.**
  2. `listen 80; server_name xenora.uz www.xenora.uz;` — faqat `return 301` HTTPS'ga.
  3. `listen 443 ssl http2;` — asosiy blok + HSTS (`max-age=300`, sinov qiymati).

  > ⚠️ **1-blokka hech qachon `ssl`/`return 301`/HSTS qo'shmang.** Mijozlarning tarqatilgan
  > `.exe` fayllari hali `http://178.128.251.218` ga bog'langan; sertifikat IP uchun yaroqsiz,
  > shuning uchun IP HTTPS'ga majburlansa mijozlar butunlay ulanolmay qoladi.
  > `certbot --nginx` ni **`--no-redirect`** bilan ishlating — aks holda u blokni bo'lib
  > HTTP tomoniga `return 404` qo'yadi va aynan shu nosozlikni keltiradi.
  > nginx 1.24 — `http2 on;` YO'Q, faqat `listen 443 ssl http2;` sintaksisi.
  > Har o'zgarishdan keyin tekshiring: `curl -o /dev/null -w '%{http_code} %{redirect_url}' http://178.128.251.218/` → **200, redirect'siz**.
- systemd unit: `/etc/systemd/system/xenora.service`
- **Maxfiy qiymatlar:** `/root/.xenora/` (700) — `dbpw`, `secret_key`, `su_password`, `root_password` (har biri 600).
  DO web-konsoli uchun root parol shu yerda (SSH orqali parol ishlamaydi).
- sshd qattiqlashtirish: `/etc/ssh/sshd_config.d/00-xenora-hardening.conf`
  (⚠️ `00-` prefiksi SHART — OpenSSH birinchi topilgan qiymatni oladi, `50-cloud-init.conf` `yes` qo'yadi)

> **Repoda `docker-compose.yml` bor** — bu production'da ISHLATILMAYDI. Production = systemd. Deploy'da doim systemd usulini qo'llang.

---

## 2. SSH ulanish

```bash
ssh -i ~/.ssh/xenora_deploy root@178.128.251.218
```

- Kalit: `~/.ssh/xenora_deploy` (parolsiz, serverga o'rnatilgan).
- ⚠️ **Git Bash ishlat** (Claude Code'da Bash tool). **PowerShell'ning `ssh`'i OSILADI** — hech qachon PowerShell'dan ssh qilma.
- Birinchi ulanishda: `-o StrictHostKeyChecking=accept-new` qo'shish mumkin.

Tez tekshir:
```bash
ssh -i ~/.ssh/xenora_deploy -o BatchMode=yes root@178.128.251.218 "echo SSH_OK; hostname"
```

---

## 3. Deploy qadamlari (ketma-ket)

Barchasi serverda (`ssh` ichida) bajariladi.

```bash
# ── 0) SSH ichiga kir ──
ssh -i ~/.ssh/xenora_deploy root@178.128.251.218
cd /opt/xenora

# ── 1) DB BACKUP (migratsiyadan OLDIN — SHART) ──
cd /opt/xenora/backend
DBURL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2- | sed 's/+psycopg2//')
mkdir -p ~/xenora-backups
pg_dump "$DBURL" > ~/xenora-backups/pre_1.0.X_$(date +%F_%H%M).sql
ls -la ~/xenora-backups/ | tail -3      # bo'sh bo'lmasin (size > 0)

# ── 2) Yangi kodni olish ──
cd /opt/xenora
git pull origin main                    # kutilgan yangi HEAD ni tekshir

# ── 3) .env VERSION ni yangila (⚠️ pastdagi eslatmaga qara) ──
sed -i -E 's/^VERSION=.*/VERSION=1.0.X/' /opt/xenora/backend/.env
grep -E '^VERSION=' /opt/xenora/backend/.env

# ── 4) Migratsiya ──
cd /opt/xenora/backend
venv/bin/alembic upgrade head
venv/bin/alembic current                # yangi head ni tasdiqla

# ── 5) Backend restart ──
systemctl restart xenora
systemctl is-active xenora              # "active" bo'lsin
systemctl status xenora --no-pager | head -15

# ── 6) nginx reload (frontend statik — git pull bilan yangilangan) ──
nginx -t && systemctl reload nginx

# ── 7) TEKSHIR ──
curl -s http://127.0.0.1:8000/health    # {"status":"healthy","database":"connected","version":"1.0.X"}
curl -s http://127.0.0.1/health         # nginx orqali ham
journalctl -u xenora --since "2 min ago" --no-pager | grep -iE 'error|traceback|exception' || echo "xato yo'q"
```

Agar `pip` bog'liqliklari o'zgargan bo'lsa (requirements.txt): `venv/bin/pip install -r requirements.txt` (odatda shart emas).

---

## 4. Versiya — HAMMASI bir xil bo'lsin

Har relizda quyidagi **6 joyni bir xil versiyaga** yangilang (masalan `1.0.3`):

| Fayl | Maydon |
|---|---|
| `backend/config.py` | `VERSION` (default) |
| `backend/.env` (serverda) | `VERSION=` ⚠️ pastdagi eslatma |
| `frontend/shared/version.js` | `window.APP_VERSION` |
| `frontend/shared/login.html` | `id="appVersion"` fallback (runtime'da version.js bosadi) |
| `electron/package.json` | `"version"` |
| `android/android/app/build.gradle` | `versionName` + `versionCode` (**+1 oshir**) |

Frontend PWA cache (alohida versiya sxemasi):
- `frontend/pwa/service-worker.js` → `APP_VERSION = 'vX.Y.Z'` ni **oshir** (mijoz eski frontendni ko'rmasin). v1.0.3 = `v1.24.0`.

`CHANGELOG.md` ni ham yangilang.

---

## 5. Native build

> **v1.4.0 build:** Android `versionCode 20` / `versionName 1.4.0`; Electron `1.4.0`.
> Ikkala platforma ilova ichida **1.4.0** ko'rsatadi (version.js/login.html bilan izchil).
> ⚠️ **Electron build oldin:** `electron/vendor/SumatraPDF.exe` (64-bit portable, ~20MB) bo'lishi shart —
> git'da yo'q (`.gitignore`), lokal build mashinasida. Yo'q bo'lsa chek GDI fallback (krakozyabra).
> ⚠️ **Chek fixi (silent print) BUILD'da:** Electron `extraResources` (`from: ../frontend`) build vaqtida
> frontend'ni yangidan nusxalaydi — `receipt-print.js`/`pos.js`/`main.js`/`preload.js` avtomatik kiradi.
> Eski `electron/dist/win-unpacked` build'da qayta yoziladi. Android: `npx cap sync` frontend'ni yangilaydi.

**Android (APK):**
- GitHub Actions workflow: **"Android APK Build"** (`.github/workflows/android.yml`) — `workflow_dispatch` (qo'lda).
- Trigger: `gh workflow run android.yml` (yoki Actions tab → Run workflow). Push AVTOMATIK ishga tushirmaydi.
- `npx cap sync android` frontend (v1.2.2) ni Android assets'ga ko'chiradi → APK yangi frontend bilan.
- APK: Actions run → **Artifacts** (`XENORA-app-debug`) dan yuklab olinadi.
- (Bu mashinada Java/SDK yo'q — Android faqat Actions'da quriladi.)

**Windows (.exe) — Electron:**
```bash
cd electron
npm install            # birinchi marta
npm run build          # electron-builder → dist/ (Setup + Portable)
# yoki: npm run build:win / npm run build:win:portable
```

---

## 6. GitHub

- Repo: **`muhammad007-pro/xenora-pos`** (private).
- Local push: `git push origin main` (HTTPS).
- **Serverda pull** deploy key bilan: `git@github.com` orqali, `/root/.ssh/github_deploy`.
  - Kalit `/root/.ssh/config` da doimiy bog'langan:
    ```
    Host github.com
      HostName github.com
      User git
      IdentityFile /root/.ssh/github_deploy
      IdentitiesOnly yes
    ```
  - GitHub'dagi nomi: **`xenora-server-178.128.251.218`** (read-only deploy key).
    Eski server kaliti (`xenora-server-deploy`) 2026-08-12 da o'chirildi.
  - Busiz `git pull` → `Permission denied (publickey)` (default kalit ishlatiladi).

---

## 7. Muhim eslatmalar / tuzoqlar

1. **⚠️ `.env` VERSION `config.py` ni bosib o'tadi.** pydantic BaseSettings `.env` qiymatini class default'idan ustun qo'yadi. `/health` `.env` dagi VERSION ni qaytaradi — kod default'ini emas. **Har relizda server `.env` VERSION ni ham yangila** (3-bo'lim, 3-qadam), aks holda health eski versiya ko'rsatadi.
2. **⚠️ PowerShell ssh osiladi → Git Bash ishlat.**
3. **⚠️ Migratsiyadan oldin DB backup SHART** (3-bo'lim, 1-qadam).
4. **`.env` faqat serverda** (600, gitignore) — `git pull` uni buzmaydi. Yangi kalit qo'shsang serverda qo'lda yoz.
5. **Server = systemd, docker emas** — `docker-compose` buyruqlarini ishlatma.
6. **Tenant izolyatsiya** — `apply_tenant_filter` (`backend/deps.py`) va `resolve_tenant_id`. Buzma. Rol yozish amallari faqat super-admin (rollar global). Upload tenant bucket (`tenant_<id>`).
7. **Migratsiyalar linear** — yangi migration `down_revision` joriy head'ga to'g'ri kelsin. Deploy oldin `venv/bin/alembic current` bilan server DB head'ini tekshir.
8. **⚠️ Alembic zanjiri haqida ikki fakt** (2026-09-03 da tekshirildi — bu ikkisini bilmasa, yo'q muammo "topiladi"):
   - **HEAD BITTA.** `migrations/versions/` ni qo'lda skanerlash **soxta 3 ta head** ko'rsatadi, chunki `b9c8d7e6f5a4` — MERGE revision va uning `down_revision` i KORTEJ: `('c3d4e5f6a7b8', 'f2a3b4c5d6e7')`. Oddiy regex kortejni o'qiy olmay, ikkala ota-onani "head" deb hisoblaydi. Yagona ishonchli manba — `venv/bin/alembic heads`. Fork 2026-iyulda allaqachon yopilgan, `alembic upgrade head` xavfsiz.
   - **TOZA BAZADA `alembic upgrade head` ISHLAMAYDI — dizayn shunday.** Ildiz migratsiya `ca406934e5dd` BO'SH baseline (`pass`): bazaviy sxema alembic'da emas, `Base.metadata.create_all()` da. Toza o'rnatish yo'li: **`create_all` → `alembic stamp head`**, keyin `upgrade head` no-op bo'ladi (sinaldi: 81 jadval). Mavjud bazada odatdagi `upgrade head` normal ishlaydi.

---

## 8. Oxirgi deploy holati (yozib boriladi)

- **v1.1.0** (2026-07-13, `bdc86f9`): KATTA reliz — yangi XENORA dizayn + admin refaktoring (14 modul) + AI-ombor (rasmdan mahsulot o'qish, 3 bosqich). Uch branch main'ga merge (design + ai-ombor, yagona konflikt inventory.html avto-hal). Migration YO'Q (AI-ombor mavjud ustunlardan foydalanadi — `f6a7b8c9d0e1` head o'zgarmadi, upgrade no-op). `anthropic 0.116.0` venv'ga o'rnatildi. `.env`: `ANTHROPIC_API_KEY=CHANGE_ME` (placeholder — AI 503 "sozlanmagan", crash EMAS; Muhammad haqiqiy kalit qo'yadi) + `AI_WAREHOUSE_MODEL/ENABLED`. SW `v1.26.0`. Health `version:1.1.0`. Backup: `~/xenora-backups/pre_1.1.0_2026-07-12_2346.sql`. **Eslatma:** production super-admin paroli dev'nikidan (`admin4770`) farq qiladi — jonli funksiya testi Muhammad kredi bilan.
- **v1.0.3** (2026-07-11, `8800a6d`): to'liq audit tozalash (14 muammo). Migration `e5f6a7b9c0d1` → `f6a7b8c9d0e1` (ingredients_restored ustun + 3 composite indeks). SW `v1.24.0`. Health `version:1.0.3`. Backup: `~/xenora-backups/pre_1.0.3_2026-07-11_0541.sql`.
- **v1.0.1** (2026-07-10, `557404a`): magazin 10 tuzatish. Migration `e5f6a7b9c0d1`. SW `v1.22.0`.

## 9. Server monitoring (scripts/monitor.py) — cron

Disk/RAM/xizmat/backup kuzatuvi + Telegram alert (spam himoyasi bilan). Stdlib, ortiqcha o'rnatishsiz.

**Sozlash (`/opt/xenora/backend/.env`):**
```
TELEGRAM_BOT_TOKEN=123456:ABC...   # BotFather (telegram.py bilan bir xil bo'lishi mumkin)
ALERT_CHAT_ID=123456789            # superadmin chat id (@userinfobot dan olinadi)
```
Sozlanmasa — monitoring JIM ishlaydi (alert yo'q, faqat `/opt/xenora/logs/monitor.log`).

**O'rnatish (MEN AYTGANDA — hozir emas):**
```
# skript repo'da: /opt/xenora/scripts/monitor.py  (git pull bilan keladi)
crontab -e
# quyidagini qo'sh (har 15 daqiqada):
*/15 * * * * /usr/bin/python3 /opt/xenora/scripts/monitor.py >> /opt/xenora/logs/monitor_cron.log 2>&1
```
Chegaralar (ixtiyoriy, env orqali): `MON_DISK_PCT=85`, `MON_RAM_MIN_MB=100`, `MON_BACKUP_MAX_H=26`, `MON_SUPPRESS_H=6`.
Qo'lda test: `python3 /opt/xenora/scripts/monitor.py` (bir marta ishlaydi, holatni loglaydi).

## 10. Backup — cron (scripts/backup.py) — app scheduler O'RNIGA

App scheduler taymeri xotirada (`next_run = app_start + 24s`) → HAR deploy/restart nollanadi →
backup tushib qolardi. Endi cron (restart'dan mustaqil, belgilangan soat).

**O'rnatish tartibi (MUHIM — backup uzilmasin):**
1. AVVAL cron o'rnatiladi (skript `git pull` bilan `/opt/xenora/scripts/backup.py` ga keladi):
   ```
   crontab -e
   # har kuni Toshkent 03:00 (do'kon yopiq). DIQQAT: cron server UTC'da → 22:00 UTC = Toshkent 03:00.
   0 22 * * * /usr/bin/python3 /opt/xenora/scripts/backup.py >> /opt/xenora/logs/backup_cron.log 2>&1
   ```
2. Qo'lda sinov: `python3 /opt/xenora/scripts/backup.py` → `logs/backup.log` da "OK ... MB", fayl `backend/backup/auto/` da.
3. KEYIN app scheduler'dan backup olib tashlangan kod deploy qilinadi (scheduler.py — bu commit).
   Shundagина ikki marta backup bo'lmaydi va oraliq uzilmaydi.

**Tekshirish:** `tail /opt/xenora/logs/backup.log`; `ls -la /opt/xenora/backend/backup/auto/ | tail`.
Monitoring (§9) backup yoshini kuzatadi — 26 soatdan eski bo'lsa Telegram alert.
**To'xtatish:** `crontab -e` → qatorni o'chir. **Sozlash:** `BK_MIN_KEEP=7` (doim saqlanadigan), `BK_MAX_AGE_DAYS=14`.

---

## 11. Server qayta qurish (2026-08-12) — nima qilindi

Eski droplet `146.190.225.168` **yo'q qilingan** (destroyed) — u bilan birga server `.env` va jonli baza ham
yo'qolgan. Yangi server `178.128.251.218` noldan qurildi va **22.07.2026 zaxirasidan** tiklandi.

**Tiklash manbai (lokal, Muhammad mashinasida):** `C:\Users\user\eco_offsite\`
- `eco_db_20260722_1608.sql.gz` — PostgreSQL 16.14 plain dump (81 jadval)
- `eco_media_20260722.tar.gz` — `static/uploads/products/` (3 rasm)

**Bajarilgan ketma-ketlik:** swap → apt paketlar → `xenora_db`+`xenora_user` → clone+venv →
`.env` (yangi `SECRET_KEY`, yangi DB parol) → restore → `alembic upgrade head` → media →
systemd+nginx → obuna muddatlari → UFW+SSH qattiqlashtirish.

**⚠️ Yo'qolgan va QAYTA sozlanishi kerak bo'lganlar:**

| Qiymat | Holat |
|---|---|
| `SECRET_KEY` | **Yangi** generatsiya qilindi — eski JWT/refresh tokenlar bekor, qurilmalar qayta login qiladi |
| DB parol | **Yangi** (`/root/.xenora/dbpw`) |
| `SENTRY_DSN` | ❌ **BO'SH** — sentry.io panelidan DSN olib `.env` ga qo'yish kerak |
| `ANTHROPIC_API_KEY` | ❌ **BO'SH** — AI-Ombor `/ai-warehouse/scan` 503 qaytaradi (server ishlaydi) |
| `TELEGRAM_BOT_TOKEN` / `ALERT_CHAT_ID` | ❌ bo'sh — monitoring/alert jim |
| Click/Payme/SMS/SMTP | ❌ bo'sh (hech qachon sozlanmagan) |
| HTTPS / domen | ❌ yo'q — hozircha **oddiy HTTP**, certbot domen olingach |
| monitor.py / backup.py cron | ❌ **o'rnatilmagan** (§9, §10 bo'yicha qayta o'rnatiladi) |

**Ma'lumot holati:** 4 tenant, 559 mahsulot (eco aroma tenant 20 → **555**), 7 user, 43 buyurtma.
Obuna muddatlari **2027-08-12** gacha uzaytirildi (zaxira 3 hafta eski edi, muddatlar tugab tenantlar
avtomatik o'chgan edi). Super-admin `admin` / `+998949974770` — parol zaxiradagi eski hash.

**⚠️ APK/Electron:** `window.XENORA_SERVER` va `SERVER_URL` yangi IP ga o'tkazildi (`2a821f6`),
lekin **qayta build qilinmagan** — eski .apk/.exe hali yo'q qilingan serverga urinadi.

**Kirishni yo'qotsangiz:** SSH parol bilan ishlamaydi. DigitalOcean web-konsoli (Recovery Console)
orqali kiring — root parol `/root/.xenora/root_password` da (yoki DO paneldan reset).
