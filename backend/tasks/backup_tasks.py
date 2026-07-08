"""
PostgreSQL zaxira nusxa vazifalar.

pg_dump yordamida kompressiyalangan .sql.gz fayl yaratadi.
SQLite pos.db ga tayanmaydi — PostgreSQL DATABASE_URL ishlatiladi.
"""
import os
import gzip
import shutil
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BACKUP_DIR = Path("backup/auto")
MEDIA_BACKUP_DIR = Path("backup/media")


def _pg_from_url(url: str) -> dict:
    """DATABASE_URL ni psql parametrlariga ajratadi."""
    p = urlparse(url)
    return {
        "host":   p.hostname or "localhost",
        "port":   str(p.port or 5432),
        "user":   p.username or "pos_user",
        "dbname": p.path.lstrip("/"),
    }


async def backup_database() -> dict:
    """pg_dump orqali PostgreSQL ma'lumotlar bazasini zaxiralaydi."""
    from config import settings

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"backup_{ts}.sql.gz"

    pg = _pg_from_url(settings.DATABASE_URL)
    db_url = settings.DATABASE_URL

    env = os.environ.copy()
    # psycopg2 / pg_dump password ni PGPASSWORD orqali oladi
    p = urlparse(db_url)
    if p.password:
        env["PGPASSWORD"] = p.password

    cmd = [
        "pg_dump",
        "-h", pg["host"],
        "-p", pg["port"],
        "-U", pg["user"],
        "-d", pg["dbname"],
        "--no-password",
        "-F", "p",          # plain SQL
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")
            logger.error("pg_dump xatosi: %s", err)
            return {"success": False, "error": err}

        # Gzip kompressiyalash
        with gzip.open(dest, "wb") as gz:
            gz.write(stdout)

        size_mb = dest.stat().st_size / (1024 * 1024)
        logger.info("Zaxira yaratildi: %s  (%.2f MB)", dest.name, size_mb)

        await _cleanup_old_backups()
        return {"success": True, "file": str(dest), "size_mb": round(size_mb, 2)}

    except FileNotFoundError:
        # pg_dump o'rnatilmagan (masalan, dev muhit)
        logger.warning("pg_dump topilmadi — zaxira o'tkazib yuborildi")
        return {"success": False, "error": "pg_dump not found"}
    except asyncio.TimeoutError:
        logger.error("pg_dump 300s da tugamadi")
        return {"success": False, "error": "pg_dump timeout"}
    except Exception as exc:
        logger.exception("Backup xatosi")
        return {"success": False, "error": str(exc)}


async def _cleanup_old_backups(keep_days: int = 30) -> None:
    """keep_days dan eski zaxiralarni o'chiradi."""
    cutoff = datetime.now() - timedelta(days=keep_days)
    for f in BACKUP_DIR.glob("backup_*.sql.gz"):
        if datetime.fromtimestamp(f.stat().st_ctime) < cutoff:
            f.unlink()
            logger.info("Eski zaxira o'chirildi: %s", f.name)


async def backup_media_files() -> dict:
    """static/uploads va static/receipts papkalarini zaxiralaydi."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    media_dirs = [Path("static/uploads"), Path("static/receipts")]
    dest_root  = MEDIA_BACKUP_DIR / ts

    try:
        for src in media_dirs:
            if not src.exists():
                continue
            dest = dest_root / src
            dest.mkdir(parents=True, exist_ok=True)
            for item in src.rglob("*"):
                if item.is_file():
                    rel   = item.relative_to(src)
                    dst   = dest / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dst)

        logger.info("Media fayllari zaxiralandi: %s", ts)
        return {"success": True, "timestamp": ts}

    except Exception as exc:
        logger.exception("Media backup xatosi")
        return {"success": False, "error": str(exc)}


async def restore_database(backup_file: str) -> dict:
    """
    Zaxira fayldan ma'lumotlar bazasini tiklaydi.
    Hozirgi holatni avval 'pre_restore_' prefiksi bilan saqlaydi.
    """
    from config import settings

    src = BACKUP_DIR / backup_file
    if not src.exists():
        return {"success": False, "error": "Backup fayl topilmadi"}

    pg  = _pg_from_url(settings.DATABASE_URL)
    env = os.environ.copy()
    p   = urlparse(settings.DATABASE_URL)
    if p.password:
        env["PGPASSWORD"] = p.password

    # Joriy holatni saqlash
    await backup_database()

    # Gzip ochib psql ga uzatish
    cmd = [
        "psql",
        "-h", pg["host"],
        "-p", pg["port"],
        "-U", pg["user"],
        "-d", pg["dbname"],
        "--no-password",
    ]

    try:
        with gzip.open(src, "rb") as gz:
            sql_data = gz.read()

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(input=sql_data), timeout=300)

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")
            logger.error("Restore xatosi: %s", err)
            return {"success": False, "error": err}

        logger.info("Ma'lumotlar bazasi tiklandi: %s", backup_file)
        return {"success": True, "message": "Tiklash muvaffaqiyatli"}

    except Exception as exc:
        logger.exception("Restore xatosi")
        return {"success": False, "error": str(exc)}


async def get_backup_list() -> list:
    """Mavjud zaxiralar ro'yxatini qaytaradi."""
    if not BACKUP_DIR.exists():
        return []

    result = []
    for f in sorted(BACKUP_DIR.glob("backup_*.sql.gz"), reverse=True):
        stat = f.stat()
        result.append({
            "name":            f.name,
            "size":            stat.st_size,
            "size_mb":         round(stat.st_size / (1024 * 1024), 2),
            "created":         datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "created_display": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return result
