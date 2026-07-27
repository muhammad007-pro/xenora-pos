#!/usr/bin/env python3
"""XENORA server monitoring — cron orqali (masalan har 15 daqiqa).

Kuzatadi: disk band %, RAM bo'sh, xenora xizmati, oxirgi avto-backup yoshi.
Muammoда → Telegram alert (mavjud bot). Spam himoyasi: bir muammo SUPPRESS_HOURS'da
1 marta; muammo tuzalganda "✅ Tuzaldi" xabari. Telegram sozlanmagan (token/chat yo'q)
→ JIM (xato bermaydi, faqat lokal log). O'zi yiqilsa — stderr + log (jim qolmaydi).

Tashqi kutubxona YO'Q (stdlib) — serverda ortiqcha o'rnatishsiz ishlaydi.

Sozlash (.env, /opt/xenora/backend/.env):
  TELEGRAM_BOT_TOKEN=123456:ABC...   (BotFather; telegram.py bilan bir xil)
  ALERT_CHAT_ID=123456789            (superadmin chat id — @userinfobot dan)
Sozlanmasa monitoring jim ishlaydi (log yoziladi, alert yuborilmaydi).

Chegaralar env orqali o'zgartiriladi (sinov/moslash uchun): MON_DISK_PCT, MON_RAM_MIN_MB,
MON_BACKUP_MAX_H, MON_SUPPRESS_H.
"""
import os
import sys
import json
import time
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # _notify.py yonida (umumiy Telegram)
from _notify import read_env as _env_read, send_telegram as _tg_send   # noqa: E402

BASE       = Path(os.environ.get("XENORA_BASE", "/opt/xenora"))
ENV_FILE   = BASE / "backend" / ".env"
STATE_FILE = Path(os.environ.get("MON_STATE", "/tmp/xenora_monitor_state.json"))
LOG_FILE   = BASE / "logs" / "monitor.log"
SERVICE    = os.environ.get("MON_SERVICE", "xenora")

DISK_PCT_WARN   = int(os.environ.get("MON_DISK_PCT", "85"))      # disk band % chegarasi
RAM_FREE_MIN_MB = int(os.environ.get("MON_RAM_MIN_MB", "100"))   # bo'sh RAM (MB) chegarasi
BACKUP_MAX_AGE_H = int(os.environ.get("MON_BACKUP_MAX_H", "26"))  # kunlik backup → 26s eski = muammo
SUPPRESS_HOURS   = int(os.environ.get("MON_SUPPRESS_H", "6"))    # spam himoya (soat)

# Avto-backup papkasining ehtimoliy joylari (backup_tasks.py: backup/auto CWD'ga nisbatan)
BACKUP_DIRS = [
    BASE / "backend" / "backup" / "auto",
    BASE / "backup" / "auto",
]


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} [monitor] {msg}"
    print(line, file=sys.stderr)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_env(key: str):
    return _env_read(key, str(ENV_FILE))


def send_telegram(text: str) -> bool:
    """UMUMIY _notify orqali (backup.py bilan bir xil). Sozlanmasa/xatoda log + False."""
    ok, why = _tg_send(text, str(ENV_FILE))
    if not ok:
        log(f"Telegram alert yuborilmadi ({why}).")
    return ok


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(s: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(s), encoding="utf-8")
    except Exception as e:
        log(f"State saqlashда xato: {e}")


def run_checks() -> list:
    """(key, message) muammolar ro'yxati. Har check o'z xatosini yutadi (biri yiqilsa boshqasi ishlaydi)."""
    problems = []
    # ── Disk ──
    try:
        u = shutil.disk_usage("/")
        pct = round(u.used / u.total * 100)
        if pct >= DISK_PCT_WARN:
            problems.append(("disk", f"💾 Disk {pct}% band (chegara {DISK_PCT_WARN}%)"))
    except Exception as e:
        log(f"disk check xato: {e}")
    # ── RAM (MemAvailable) ──
    try:
        mi = {}
        for ln in Path("/proc/meminfo").read_text().splitlines():
            k, _, v = ln.partition(":")
            if v.strip():
                mi[k] = int(v.strip().split()[0])   # kB
        free_mb = mi.get("MemAvailable", mi.get("MemFree", 0)) // 1024
        if free_mb < RAM_FREE_MIN_MB:
            problems.append(("ram", f"🧠 Bo'sh RAM {free_mb}MB (chegara {RAM_FREE_MIN_MB}MB)"))
    except Exception as e:
        log(f"ram check xato: {e}")
    # ── Xizmat ──
    try:
        r = subprocess.run(["systemctl", "is-active", SERVICE],
                           capture_output=True, text=True, timeout=10)
        st = (r.stdout or "").strip()
        if st != "active":
            problems.append(("service", f"🔴 '{SERVICE}' xizmati ishlamayapti (holat: {st or 'nomalum'})"))
    except Exception as e:
        log(f"service check xato: {e}")
    # ── Backup yoshi ──
    try:
        files = []
        for d in BACKUP_DIRS:
            if d.is_dir():
                files += list(d.glob("*.sql.gz"))
        if not files:
            problems.append(("backup", "🗄 Avto-backup fayli topilmadi"))
        else:
            newest = max(files, key=lambda p: p.stat().st_mtime)
            age_h = (time.time() - newest.stat().st_mtime) / 3600
            if age_h > BACKUP_MAX_AGE_H:
                problems.append(("backup",
                    f"🗄 Oxirgi backup {age_h:.0f} soat oldin ({newest.name}) — kutilgan <{BACKUP_MAX_AGE_H}s"))
    except Exception as e:
        log(f"backup check xato: {e}")
    return problems


def main() -> None:
    state = load_state()
    now = time.time()
    problems = run_checks()
    active = {k for k, _ in problems}

    # Tuzalgan muammolar (oldin alert bo'lgan, endi yo'q) → xabar + state'dan olib tashlash
    for k in list(state.keys()):
        if k not in active:
            send_telegram(f"✅ Tuzaldi: <b>{k}</b>")
            state.pop(k, None)

    # Yangi/davom etayotgan muammolar (SUPPRESS_HOURS spam himoyasi)
    for k, msg in problems:
        last = state.get(k, 0)
        if now - last >= SUPPRESS_HOURS * 3600:
            if send_telegram(f"⚠️ <b>XENORA server</b>\n{msg}"):
                state[k] = now
        else:
            log(f"suppress (yaqinda yuborilgan): {k}")

    save_state(state)
    log("Muammolar: " + "; ".join(m for _, m in problems) if problems else "OK — muammo yo'q")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"MONITOR CRASH: {e}")
        sys.exit(1)
