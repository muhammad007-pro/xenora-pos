# XENORA POS — Deploy qo'llanmasi

> Bu fayl production deploy tafsilotini saqlaydi — **har yangi sessiyada shu yerdan o'qing**, qayta izlamang.
> Oxirgi tasdiqlangan deploy: **v1.4.0** (2026-07-21) — **PRINT TIZIMI (markaziy servis)**: barcha print (chek, Z-hisobot, kunlik hisobot) bitta `printDocument` (Electron main.js) dan o'tadi; `print_type` (usb/lan/qr) transportni tanlaydi — USB=SumatraPDF (hozirgi), LAN=stub ("tez orada"), QR=stub. Chek sozlamasida "Print turi" + IP/port UI. Z-hisobot to'liq (SOTILGAN MAHSULOTLAR breakdown + kamomad). Kunlik hisobot (report.html) 58mm markaziyga (grafik/panel EMAS). Barcha `window.print()` (butun panel) → markaziy (etiketka/QR/legacy alohida media, tegilmadi).
> ⚠️ **MIGRATSIYA BOR (B0):** `d0e1f2a3b4c5` — `receipt_settings.print_type/printer_ip/printer_port` (nullable, `print_type` default 'usb', idempotent). `c9d0e1f2a3b4`→`d0e1f2a3b4c5`. Android versionCode **20** / 1.4.0.
> ⚠️ **BACKEND DEPLOY SHART:** shift.py (Z-hisobot products/avg_order/store_name), receipt_settings.py (print config), models.py + migratsiya. `alembic upgrade head` MAJBURIY. Backup majburiy.
> ⚠️ **BUILD SHART + SumatraPDF:** Chek Electron .exe'да. Build oldin `electron/vendor/SumatraPDF.exe` (20MB, git'да yo'q — build mashinasida lokal) bo'lishi SHART — `extraResources` uni `resources/`ga nusxalaydi. Busiz GDI fallback (krakozyabra).
> (Oldingi: v1.3.2 Chek chapga surish margin:0; v1.3.1 Chek narx 48mm+shrift o'lchami; v1.3.0 Chek 54mm+QR toggle+atir+POS tarix/ombor; v1.2.8 capturePage raster; v1.2.7 avtomatik chek+HTML GDI; v1.2.6 did-finish-load+pageSize yo'q; v1.2.5 deviceName default+58mm; v1.2.4 Chek lokal silent print; v1.2.3 Sodiqlik [`c9d0e1f2a3b4`]; v1.2.2 Pachka/Dona; v1.2.1 brend ∞; v1.2.0 RBAC audit; v1.0.3 `8800a6d`.)

---

## 1. Server (production)

| | |
|---|---|
| **Provayder** | DigitalOcean droplet, region AMS3 |
| **IP** | `146.190.225.168` |
| **Host / user** | `root@xenora-saas` (Ubuntu 24.04) |
| **Kod joyi** | `/opt/xenora` (git `main` branch) |
| **Backend xizmati** | **systemd** — `xenora.service` (⚠️ **DOCKER EMAS**) |
| **Backend runtime** | venv uvicorn → `127.0.0.1:8000` (1 worker, WebSocket uchun) |
| **Web server** | nginx — `/opt/xenora/frontend` ni serve qiladi + `/api` `/ws` `/health` `/uploads` `/static` `/docs` → `127.0.0.1:8000` proxy |
| **DB** | PostgreSQL (native), migratsiya venv alembic bilan |

Muhim yo'llar:
- venv: `/opt/xenora/backend/venv`
- alembic: `/opt/xenora/backend/venv/bin/alembic` (WorkingDirectory = `/opt/xenora/backend`)
- `.env`: `/opt/xenora/backend/.env` (ruxsat 600, **faqat serverda**, git'da yo'q)
- nginx config: `/etc/nginx/sites-available/xenora` (default_server)

> **Repoda `docker-compose.yml` bor** — bu production'da ISHLATILMAYDI. Production = systemd. Deploy'da doim systemd usulini qo'llang.

---

## 2. SSH ulanish

```bash
ssh -i ~/.ssh/xenora_deploy root@146.190.225.168
```

- Kalit: `~/.ssh/xenora_deploy` (parolsiz, serverga o'rnatilgan).
- ⚠️ **Git Bash ishlat** (Claude Code'da Bash tool). **PowerShell'ning `ssh`'i OSILADI** — hech qachon PowerShell'dan ssh qilma.
- Birinchi ulanishda: `-o StrictHostKeyChecking=accept-new` qo'shish mumkin.

Tez tekshir:
```bash
ssh -i ~/.ssh/xenora_deploy -o BatchMode=yes root@146.190.225.168 "echo SSH_OK; hostname"
```

---

## 3. Deploy qadamlari (ketma-ket)

Barchasi serverda (`ssh` ichida) bajariladi.

```bash
# ── 0) SSH ichiga kir ──
ssh -i ~/.ssh/xenora_deploy root@146.190.225.168
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
- **Serverda pull** deploy key bilan: `git@github.com` orqali, `~/.ssh/github_deploy`.
  - Server `.git/config` da doimiy: `core.sshCommand = ssh -i ~/.ssh/github_deploy -o StrictHostKeyChecking=no`.
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
