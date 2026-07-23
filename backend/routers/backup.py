"""Zaxira nusxa boshqaruvi.

- Superuser: server pg_dump (butun baza) — /, /restore.
- Do'kon admin: FAQAT o'z tenant ma'lumoti (tenant-scoped) — /my-tenant.
"""
import os
import gzip
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File
from sqlalchemy.orm import Session

from database import get_db
from models import User
# get_current_active_user_no_sub — obuna ENFORCEMENT'siz: bloklangan do'kon ham
# O'Z ma'lumotini eksport/tiklay olsin (tenant-scoped, xavfsiz). Egasi xohlasa
# oddiy get_current_active_user'ga o'zgartirib yopiladi.
from deps import get_current_superuser, get_current_active_user_no_sub
from tasks.backup_tasks import backup_database, get_backup_list, restore_database
from services.tenant_backup import build_tenant_backup, restore_tenant_backup

router = APIRouter()


def _require_store_admin(current_user: User):
    """Do'kon admin/manager/ega + tenant aniqlangan bo'lishi. Super-admin — bu yerда emas."""
    if current_user.is_superuser or not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Bu amal faqat do'kon hisobidan bajariladi (tenant aniqlanmadi)")
    role = (current_user.role.name if current_user.role else "").lower()
    if not any(x in role for x in ("admin", "manager", "menej", "ega")):
        raise HTTPException(status_code=403, detail="Faqat do'kon administratori bajara oladi")


@router.get("/my-tenant", summary="Do'konning o'z zaxirasi (tenant-scoped, gzip JSON)")
async def my_tenant_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_no_sub),
):
    """Joriy do'kon (current_user.tenant_id) ma'lumotini gzip'langan JSON qilib qaytaradi.

    IZOLYATSIYA: tenant URL'dan EMAS, current_user'dan olinadi (spoofing yo'q).
    Faqat o'z tenant qatorlari; boshqa do'kon yoki global jadvallar chiqmaydi.
    """
    _require_store_admin(current_user)   # super-admin emas; admin/manager/ega only
    tenant_id = current_user.tenant_id   # ← MANBA: current_user (URL emas)
    gz, meta = build_tenant_backup(db, tenant_id)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    code = (meta.get("access_code") or str(tenant_id)).replace(".", "-").replace("/", "-")
    fname = f"backup_{code}_{ts}.json.gz"
    return Response(
        content=gz,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Backup-Tenant": str(tenant_id),
            "X-Backup-Rows": str(meta.get("total_rows", 0)),
        },
    )


@router.post("/my-tenant/restore", summary="Do'kon o'z zaxirasidan tiklash (tenant-scoped)")
async def my_tenant_restore(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_no_sub),
):
    """Do'kon o'z backup faylini (JSON.gz) yuborib, o'z ma'lumotini tiklaydi.

    XAVFSIZLIK: (1) tenant current_user'дан; (2) backup._meta.tenant_id MOS kelishi shart
    (boshqa do'kon zaxirасини tiklаб bo'lmaydi → 400); (3) tiklaш oldidan joriy holат
    avtomatik zaxiralanadi; (4) hammasi BIR TRANZAKSIYA — xato bo'lса rollback (ma'lumot buzilmaydi);
    (5) INSERT'да tenant_id majburan = o'z tenant. Identity/platforma (users/cafe/obuna/audit) saqlanadi.
    """
    _require_store_admin(current_user)
    tenant_id = current_user.tenant_id

    # 1) Faylни o'qish → gunzip → JSON
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Fayl bo'sh")
    try:
        text = gzip.decompress(raw)
    except (OSError, EOFError):
        text = raw   # gzip bo'lmasa — oddiy JSON
    try:
        payload = json.loads(text.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Zaxira fayli buzuq yoki noto'g'ri (JSON emas)")

    meta = payload.get("_meta") or {}
    if meta.get("format") != "xenora-tenant-backup":
        raise HTTPException(status_code=400, detail="Noto'g'ri zaxira fayli (XENORA formati emas)")
    # KRITIK: faqat O'Z do'kon zaxirasi
    if meta.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=400, detail="Bu zaxira boshqa do'konга tegишли — tiklab bo'lmaydi")

    # 2) XAVFSIZLIK ZAXIRASI — tiklaшдан oldin joriy holат (regret/xato uchun)
    try:
        gz, _m = build_tenant_backup(db, tenant_id, meta_extra={"kind": "pre-restore-safety"})
        safe_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backup", "tenant_safety")
        os.makedirs(safe_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_path = os.path.join(safe_dir, f"pre_restore_{tenant_id}_{ts}.json.gz")
        with open(safe_path, "wb") as f:
            f.write(gz)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Xavfsizlik zaxirasi yaratilmadi — tiklash bekor qilindi: {e}")

    # 3) TRANZAKSIYA ичida tiklash (xato → rollback, ma'lumot buzilmaydi)
    try:
        result = restore_tenant_backup(db, tenant_id, payload)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Tiklashда xato — o'zgarishlar bekor qilindi (ma'lumot saqlandi): {e}")

    return {
        "success": True,
        "message": "Ma'lumot tiklandi",
        "restored": result,
        "safety_backup": os.path.basename(safe_path),
        "source_generated_at": meta.get("generated_at"),
    }


@router.get("/", summary="Zaxiralar ro'yxati")
async def list_backups(current_user=Depends(get_current_superuser)):
    return await get_backup_list()


@router.post("/", summary="Zaxira yaratish", status_code=202)
async def create_backup(current_user=Depends(get_current_superuser)):
    result = await backup_database()
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Backup muvaffaqiyatsiz"))
    return result


@router.post("/restore/{backup_file}", summary="Zaxiradan tiklash", status_code=202)
async def restore_backup(
    backup_file: str,
    current_user=Depends(get_current_superuser),
):
    if ".." in backup_file or "/" in backup_file or "\\" in backup_file:
        raise HTTPException(status_code=400, detail="Noto'g'ri fayl nomi")
    result = await restore_database(backup_file)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Tiklash muvaffaqiyatsiz"))
    return result
