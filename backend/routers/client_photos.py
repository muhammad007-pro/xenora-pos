"""
Mijoz Oldin/Keyin Fotosuratlari — BOSQICH 23 (Salon)
Soch, makiyaj, boshqa xizmatlar uchun before/after gallery.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional, List
import os, uuid

from database import get_db
from models import ClientPhoto, User
from schemas import ClientPhotoCreate, ClientPhotoInDB, PaginatedResponse, MessageResponse
from deps import get_current_active_user, apply_tenant_filter, resolve_tenant_id
from config import settings

from deps import require_feature  # funksiya-flag himoyasi (O'ZGARISH 3)
router = APIRouter(dependencies=[Depends(require_feature("before_after_photo"))])


def _get_photo(db: Session, photo_id: int, current_user: User) -> ClientPhoto:
    p = (
        apply_tenant_filter(db.query(ClientPhoto), ClientPhoto, current_user)
        .filter(ClientPhoto.id == photo_id)
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Foto topilmadi")
    return p


@router.get("/", response_model=PaginatedResponse)
async def list_photos(
    customer_id:    Optional[int] = None,
    appointment_id: Optional[int] = None,
    photo_type:     Optional[str] = None,   # before | after
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Foto gallereya (mijoz yoki bron bo'yicha)"""
    q = apply_tenant_filter(db.query(ClientPhoto), ClientPhoto, current_user)
    if customer_id:
        q = q.filter(ClientPhoto.customer_id == customer_id)
    if appointment_id:
        q = q.filter(ClientPhoto.appointment_id == appointment_id)
    if photo_type:
        q = q.filter(ClientPhoto.photo_type == photo_type)

    total = q.count()
    rows = q.order_by(ClientPhoto.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [ClientPhotoInDB.model_validate(r) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size,
                             total_pages=(total + page_size - 1) // page_size)


@router.post("/upload", response_model=ClientPhotoInDB, status_code=201)
async def upload_photo(
    file:           UploadFile = File(...),
    photo_type:     str = Form(...),              # before | after
    customer_id:    Optional[int] = Form(None),
    appointment_id: Optional[int] = Form(None),
    service_name:   Optional[str] = Form(None),
    notes:          Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Rasm yuklash (multipart/form-data)"""
    if photo_type not in ("before", "after"):
        raise HTTPException(status_code=400, detail="photo_type 'before' yoki 'after' bo'lishi kerak")

    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="Faqat JPG, PNG, WEBP rasmlari qabul qilinadi")

    upload_dir = os.path.join(settings.UPLOAD_DIR, "client_photos")
    os.makedirs(upload_dir, exist_ok=True)
    filename  = f"cp_{photo_type}_{uuid.uuid4().hex}{ext}"
    filepath  = os.path.join(upload_dir, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    photo = ClientPhoto(
        tenant_id      = resolve_tenant_id(db, current_user),
        customer_id    = customer_id,
        appointment_id = appointment_id,
        photo_type     = photo_type,
        image_url      = f"/uploads/client_photos/{filename}",
        service_name   = service_name,
        notes          = notes,
        created_by     = current_user.id,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return ClientPhotoInDB.model_validate(photo)


@router.get("/customer/{customer_id}/pairs")
async def get_before_after_pairs(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bitta mijoz uchun oldin/keyin juftliklari (bron bo'yicha guruhlangan)"""
    photos = (
        apply_tenant_filter(db.query(ClientPhoto), ClientPhoto, current_user)
        .filter(ClientPhoto.customer_id == customer_id)
        .order_by(ClientPhoto.appointment_id, ClientPhoto.photo_type)
        .all()
    )
    pairs: dict[Optional[int], dict] = {}
    for p in photos:
        key = p.appointment_id
        if key not in pairs:
            pairs[key] = {
                "appointment_id": key,
                "service_name":   p.service_name,
                "date":           p.created_at.date().isoformat() if p.created_at else None,
                "before": None,
                "after":  None,
            }
        pairs[key][p.photo_type] = {
            "id":        p.id,
            "image_url": p.image_url,
            "notes":     p.notes,
            "created_at": p.created_at,
        }
    return list(pairs.values())


@router.get("/{photo_id}", response_model=ClientPhotoInDB)
async def get_photo(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return ClientPhotoInDB.model_validate(_get_photo(db, photo_id, current_user))


@router.delete("/{photo_id}", response_model=MessageResponse)
async def delete_photo(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    photo = _get_photo(db, photo_id, current_user)
    filepath = os.path.join(settings.UPLOAD_DIR, "client_photos",
                            os.path.basename(photo.image_url))
    if os.path.exists(filepath):
        os.remove(filepath)
    db.delete(photo)
    db.commit()
    return MessageResponse(message="Foto o'chirildi")
