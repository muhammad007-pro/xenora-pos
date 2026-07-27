#!/usr/bin/env python3
"""XENORA backup — MUSTAQIL (cron orqali, app'ga bog'liq EMAS).

pg_dump (gzip) + media (uploads) arxivi → backup/auto va backup/media. Eski nusxalar
tozalanadi (14 kundan eski, LEKIN kamida MIN_KEEP nusxa doim qoladi). Har ish log'ga
(muvaffaqiyat/xato, hajm, davomiylik). Xato → Telegram alert (scripts/_notify.py — monitor
bilan bir xil mexanizm). App scheduler taymeri restart'da nollanardi → shuning uchun cron.

Cron: 03:00 (do'kon yopiq). O'rnatish: DEPLOY.md §10.
"""
import os
import sys
import gzip
import time
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # _notify.py yonida
from _notify import read_env, send_telegram   # noqa: E402

BASE       = Path(os.environ.get("XENORA_BASE", "/opt/xenora"))
BACKEND    = BASE / "backend"
ENV_FILE   = BACKEND / ".env"
AUTO_DIR   = BACKEND / "backup" / "auto"
MEDIA_DIR  = BACKEND / "backup" / "media"
UPLOADS    = BACKEND / "static" / "uploads"    # config UPLOAD_DIR
LOG_FILE   = BASE / "logs" / "backup.log"

MIN_KEEP    = int(os.environ.get("BK_MIN_KEEP", "7"))    # doim saqlanadigan eng yangi nusxa soni
MAX_AGE_DAYS = int(os.environ.get("BK_MAX_AGE_DAYS", "14"))


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} [backup] {msg}"
    print(line, file=sys.stderr)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def alert(msg: str) -> None:
    ok, why = send_telegram(f"🔴 <b>XENORA backup XATO</b>\n{msg}", str(ENV_FILE))
    if not ok:
        log(f"alert yuborilmadi ({why})")


def cleanup(folder: Path, pattern: str) -> None:
    """14 kundan eski fayllarni o'chiradi, LEKIN eng yangi MIN_KEEP nusxa doim qoladi."""
    try:
        files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime)  # eski→yangi
        keep_newest = set(files[-MIN_KEEP:])   # oxirgi MIN_KEEP — hech qachon o'chirilmaydi
        now = time.time()
        removed = 0
        for f in files:
            if f in keep_newest:
                continue
            if (now - f.stat().st_mtime) > MAX_AGE_DAYS * 86400:
                f.unlink()
                removed += 1
        if removed:
            log(f"tozalash: {folder.name}'dan {removed} eski nusxa o'chirildi (>{MAX_AGE_DAYS}k, {MIN_KEEP} saqlandi)")
    except Exception as e:
        log(f"tozalash xato ({folder}): {e}")


def dump_db() -> Path:
    """pg_dump → gzip (oqim, xotira tejaydi). Muvaffaqiyat: fayl yo'li; aks holda Exception."""
    dburl = read_env("DATABASE_URL", str(ENV_FILE))
    if not dburl:
        raise RuntimeError("DATABASE_URL topilmadi (.env)")
    AUTO_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = AUTO_DIR / f"backup_{ts}.sql.gz"
    p = subprocess.Popen(["pg_dump", dburl], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with gzip.open(dest, "wb") as gz:
        for chunk in iter(lambda: p.stdout.read(65536), b""):
            gz.write(chunk)
    _, err = p.communicate()
    if p.returncode != 0:
        try:
            dest.unlink()
        except Exception:
            pass
        raise RuntimeError(f"pg_dump rc={p.returncode}: {(err or b'').decode(errors='ignore')[:200]}")
    # butunlik
    r = subprocess.run(["gzip", "-t", str(dest)], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"gzip -t muvaffaqiyatsiz: {dest.name}")
    return dest


def dump_media() -> Path:
    """uploads papkasini tar.gz (bo'lmasa/bo'sh bo'lsa — o'tkazib yuboriladi, xato emas)."""
    if not UPLOADS.is_dir():
        log("media: uploads papkasi yo'q — o'tkazib yuborildi")
        return None
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d")
    dest = MEDIA_DIR / f"media_{ts}.tar.gz"
    r = subprocess.run(["tar", "czf", str(dest), "-C", str(BACKEND), "static/uploads"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"media tar rc={r.returncode}: {r.stderr.decode(errors='ignore')[:150]}")
    return dest


def main() -> int:
    t0 = time.time()
    try:
        db = dump_db()
        db_mb = db.stat().st_size / 1024 / 1024
        media = None
        try:
            media = dump_media()
        except Exception as e:
            log(f"media backup xato (DB backup saqlandi): {e}")   # DB muhimroq — media xatosi jarayonni to'xtatmaydi
        cleanup(AUTO_DIR, "backup_*.sql.gz")
        cleanup(MEDIA_DIR, "media_*.tar.gz")
        dur = time.time() - t0
        mtxt = f", media {media.name}" if media else ""
        log(f"OK — {db.name} ({db_mb:.2f} MB){mtxt}, {dur:.1f}s")
        return 0
    except Exception as e:
        log(f"XATO: {e}")
        alert(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
