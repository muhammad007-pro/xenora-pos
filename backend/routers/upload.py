from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
import os
import re
import uuid
from datetime import datetime
from typing import Optional

from database import get_db
from models import User
from deps import get_current_user, resolve_tenant_id
from schemas import MessageResponse
from config import settings

router = APIRouter()

ALLOWED_EXTENSIONS = {
    # XAVFSIZLIK: .svg OLIB TASHLANDI — SVG ichida <script> bo'lishi mumkin (stored XSS).
    # Faqat RASTER rasm formatlari (skript bajarmaydi). .gif ham olindi (kerak emas).
    'image': ['.jpg', '.jpeg', '.png', '.webp'],
    'document': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt'],
    'audio': ['.mp3', '.wav', '.ogg']
}

# Magic-byte tekshiruvi uchun — PIL ochib ko'radigan RUXSAT etilgan formatlar.
# (kengaytma/Content-Type YOLG'ON bo'lishi mumkin; bayt darajasida haqiqiy rasmligini tasdiqlaymiz)
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}

# ── Tenant izolyatsiya (B5) ──────────────────────────────────────────────────
# Fayllar tenant bo'yicha alohida bucket'da saqlanadi: uploads/tenant_<id>/<folder>/...
# Bucket prefiksi HAR DOIM tokendan (resolve_tenant_id) olinadi, foydalanuvchi
# kiritgan `folder` dan EMAS. Shu sababli A tenant B tenantning papkasini na
# ko'ra, na o'chira oladi (delete/list ham shu prefiks ichida ishlaydi).
# Super-admin (tenant_id=NULL, yagona kafe emas) → "platform" bucket.
#
# Bundan tashqari `folder`/`filename` path-traversal (`..`, `/`, `\`) dan
# tozalanadi — aks holda `folder=../other_tenant` bilan izolyatsiya buzilardi.

_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]")


def _tenant_bucket(db: Session, current_user: User) -> str:
    """Joriy foydalanuvchi uchun tenant papka nomi (server tomonda aniqlanadi)."""
    tid = resolve_tenant_id(db, current_user)
    return f"tenant_{tid}" if tid is not None else "platform"


def _safe_segment(name: str, default: str = "general") -> str:
    """Bitta yo'l bo'lagini traversal/ajratgichdan tozalaydi (basename, `..` yo'q)."""
    # Faqat oxirgi bo'lakni olamiz (har qanday / yoki \ ni kesib tashlaymiz).
    base = os.path.basename(str(name or "").replace("\\", "/").rstrip("/"))
    base = _SEGMENT_RE.sub("_", base)
    if not base or base in (".", ".."):
        return default
    return base


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    folder: str = "general",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Rasm yuklash"""
    return await save_uploaded_file(db, current_user, file, folder, 'image')

@router.post("/document")
async def upload_document(
    file: UploadFile = File(...),
    folder: str = "documents",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Hujjat yuklash"""
    return await save_uploaded_file(db, current_user, file, folder, 'document')

@router.post("/multiple")
async def upload_multiple(
    files: list[UploadFile] = File(...),
    folder: str = "general",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Bir nechta fayl yuklash"""
    results = []

    for file in files:
        result = await save_uploaded_file(db, current_user, file, folder)
        results.append(result)

    return {"files": results}

async def save_uploaded_file(
    db: Session,
    current_user: User,
    file: UploadFile,
    folder: str = "general",
    file_type: str = 'image'
) -> dict:
    """Faylni tenant bucket ichida saqlash"""

    # Fayl kengaytmasini tekshirish
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_type == 'image' and file_ext not in ALLOWED_EXTENSIONS['image']:
        raise HTTPException(
            status_code=400,
            detail="Ruxsat etilmagan format. Faqat rasm: JPG, JPEG, PNG, WEBP",
        )

    # Tenant bucket + tozalangan papka (traversal himoyasi)
    bucket = _tenant_bucket(db, current_user)
    folder = _safe_segment(folder, "general")

    # Fayl nomini yaratish
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{timestamp}_{unique_id}{file_ext}"

    # Papkani yaratish
    upload_dir = os.path.join(settings.UPLOAD_DIR, bucket, folder)
    os.makedirs(upload_dir, exist_ok=True)

    # Faylni saqlash
    file_path = os.path.join(upload_dir, filename)

    content = await file.read()

    # Fayl hajmini tekshirish
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="Fayl hajmi juda katta")

    # ── MAGIC-BYTE: fayl HAQIQATAN rasmligini bayt darajasida tasdiqlash ──────────
    # Kengaytma yoki Content-Type YOLG'ON bo'lishi mumkin (nomi .png, ichi SVG/skript).
    # PIL faylni ochib formatni aniqlaydi — SVG/skript/buzuq fayl ochilmaydi → rad.
    if file_type == 'image':
        from io import BytesIO
        try:
            from PIL import Image
            probe = Image.open(BytesIO(content))
            fmt = (probe.format or '').upper()   # 'JPEG' | 'PNG' | 'WEBP' | ...
            probe.verify()                        # butunlik: buzuq/rasm-emas → xato tashlaydi
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Fayl haqiqiy rasm emas (buzuq yoki noto'g'ri format). Faqat: JPG, PNG, WEBP",
            )
        if fmt not in ALLOWED_IMAGE_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"'{fmt or 'aniqlanmadi'}' formati ruxsat etilmagan. Faqat: JPG, PNG, WEBP",
            )

    with open(file_path, "wb") as f:
        f.write(content)

    # URL yaratish (tenant bucket bilan)
    file_url = f"/uploads/{bucket}/{folder}/{filename}"

    return {
        "filename": filename,
        "original_name": file.filename,
        "url": file_url,
        "size": len(content),
        "content_type": file.content_type
    }

@router.delete("/{folder}/{filename}")
async def delete_file(
    folder: str,
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Faylni o'chirish (faqat o'z tenant bucket'idan)"""
    bucket = _tenant_bucket(db, current_user)
    folder = _safe_segment(folder, "general")
    filename = _safe_segment(filename, "")
    if not filename:
        raise HTTPException(status_code=400, detail="Fayl nomi noto'g'ri")

    file_path = os.path.join(settings.UPLOAD_DIR, bucket, folder, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Fayl topilmadi")

    try:
        os.remove(file_path)
        return MessageResponse(message="Fayl o'chirildi")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Faylni o'chirishda xatolik: {str(e)}")

@router.get("/list/{folder}")
async def list_files(
    folder: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Papkadagi fayllar ro'yxati (faqat o'z tenant bucket'idan)"""
    bucket = _tenant_bucket(db, current_user)
    folder = _safe_segment(folder, "general")
    folder_path = os.path.join(settings.UPLOAD_DIR, bucket, folder)

    if not os.path.exists(folder_path):
        return []

    files = []
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            stat = os.stat(file_path)
            files.append({
                "name": filename,
                "url": f"/uploads/{bucket}/{folder}/{filename}",
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

    return sorted(files, key=lambda x: x["modified"], reverse=True)