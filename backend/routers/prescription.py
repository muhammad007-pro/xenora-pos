"""
Retsept Arxivi — BOSQICH 22 (Dorixona)
Shifokor retseptlarini saqlash, qidirish, rasm yuklash.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import date, datetime
from typing import Optional, List
import os, uuid

from database import get_db
from models import Prescription, User
from schemas import (
    PrescriptionCreate, PrescriptionUpdate, PrescriptionInDB,
    PaginatedResponse, MessageResponse,
)
from deps import (
    get_current_active_user, apply_tenant_filter, apply_branch_filter,
    resolve_tenant_id,
)
from config import settings

from deps import require_feature  # funksiya-flag himoyasi (O'ZGARISH 3)
router = APIRouter(dependencies=[Depends(require_feature("prescription_archive"))])


def _get_rx(db: Session, rx_id: int, current_user: User) -> Prescription:
    rx = (
        apply_tenant_filter(db.query(Prescription), Prescription, current_user)
        .filter(Prescription.id == rx_id)
        .first()
    )
    if not rx:
        raise HTTPException(status_code=404, detail="Retsept topilmadi")
    return rx


@router.get("/", response_model=PaginatedResponse)
async def list_prescriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: Optional[str] = None,
    is_dispensed: Optional[bool] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(Prescription), Prescription, current_user)

    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                Prescription.patient_name.ilike(like),
                Prescription.patient_phone.ilike(like),
                Prescription.doctor_name.ilike(like),
            )
        )
    if is_dispensed is not None:
        q = q.filter(Prescription.is_dispensed == is_dispensed)
    if date_from:
        q = q.filter(Prescription.prescription_date >= date_from)
    if date_to:
        q = q.filter(Prescription.prescription_date <= date_to)

    total = q.count()
    rows = q.order_by(Prescription.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [PrescriptionInDB.model_validate(r) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size,
                             total_pages=(total + page_size - 1) // page_size)


@router.post("/", response_model=PrescriptionInDB, status_code=201)
async def create_prescription(
    data: PrescriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = resolve_tenant_id(db, current_user)
    rx = Prescription(
        tenant_id=tenant_id,
        branch_id=data.branch_id or current_user.branch_id,
        patient_name=data.patient_name,
        patient_phone=data.patient_phone,
        doctor_name=data.doctor_name,
        clinic_name=data.clinic_name,
        prescription_date=data.prescription_date,
        notes=data.notes,
        medicines=[m.model_dump() for m in data.medicines],
        created_by=current_user.id,
    )
    db.add(rx)
    db.commit()
    db.refresh(rx)
    return rx


@router.get("/{rx_id}", response_model=PrescriptionInDB)
async def get_prescription(
    rx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return _get_rx(db, rx_id, current_user)


@router.patch("/{rx_id}", response_model=PrescriptionInDB)
async def update_prescription(
    rx_id: int,
    data: PrescriptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    rx = _get_rx(db, rx_id, current_user)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "medicines" and value is not None:
            value = [m if isinstance(m, dict) else m.model_dump() for m in value]
        setattr(rx, field, value)
    if data.is_dispensed and not rx.dispensed_at:
        rx.dispensed_at = datetime.utcnow()
    db.commit()
    db.refresh(rx)
    return rx


@router.delete("/{rx_id}", response_model=MessageResponse)
async def delete_prescription(
    rx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    rx = _get_rx(db, rx_id, current_user)
    db.delete(rx)
    db.commit()
    return {"message": "Retsept o'chirildi"}


@router.post("/{rx_id}/upload-image", response_model=PrescriptionInDB)
async def upload_prescription_image(
    rx_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    rx = _get_rx(db, rx_id, current_user)

    allowed = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="Faqat rasm yoki PDF fayl yuklang")

    upload_dir = os.path.join(settings.UPLOAD_DIR, "prescriptions")
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"rx_{rx_id}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    rx.image_url = f"/uploads/prescriptions/{filename}"
    db.commit()
    db.refresh(rx)
    return rx
