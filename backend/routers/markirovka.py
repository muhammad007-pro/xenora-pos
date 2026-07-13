"""
Markirovka (Asl belgisi) router — BOSQICH 26
O'zbekiston "Asl belgisi" tizimiga mos DataMatrix/QR kod nazorati.
Tovar skanerlananda status=sold bo'ladi, qaytarilsa status=returned.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from database import get_db
from models import ProductMark, Product, User
from schemas import (
    ProductMarkCreate, ProductMarkInDB, MarkScanRequest,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter

from deps import require_feature  # funksiya-flag himoyasi (O'ZGARISH 3)
router = APIRouter(dependencies=[Depends(require_feature("markirovka"))])


def _enrich(m: ProductMark) -> ProductMarkInDB:
    d = ProductMarkInDB.model_validate(m)
    d.product_name = m.product.name if m.product else None
    return d


@router.get("/", response_model=PaginatedResponse)
async def list_marks(
    product_id: Optional[int] = None,
    status:     Optional[str] = None,
    mark_type:  Optional[str] = None,
    search:     Optional[str] = None,
    page:       int = Query(1, ge=1),
    page_size:  int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(ProductMark), ProductMark, current_user)
    if product_id: q = q.filter(ProductMark.product_id == product_id)
    if status:     q = q.filter(ProductMark.status == status)
    if mark_type:  q = q.filter(ProductMark.mark_type == mark_type)
    if search:     q = q.filter(ProductMark.mark_code.ilike(f"%{search}%"))
    total = q.count()
    rows  = q.order_by(ProductMark.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return PaginatedResponse(items=[_enrich(r) for r in rows], total=total,
                             page=page, page_size=page_size,
                             total_pages=(total+page_size-1)//page_size)


@router.post("/", response_model=ProductMarkInDB)
async def create_mark(
    data: ProductMarkCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Yangi markirovka kodi ro'yxatdan o'tkazish"""
    existing = db.query(ProductMark).filter(ProductMark.mark_code == data.mark_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu kod allaqachon ro'yxatdan o'tgan")

    prod = apply_tenant_filter(db.query(Product), Product, current_user) \
               .filter(Product.id == data.product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Tovar topilmadi")

    m = ProductMark(
        tenant_id  = resolve_tenant_id(db, current_user),
        product_id = data.product_id,
        batch_id   = data.batch_id,
        mark_code  = data.mark_code,
        mark_type  = data.mark_type,
        created_by = current_user.id,
    )
    db.add(m); db.commit(); db.refresh(m)
    return _enrich(m)


@router.post("/bulk", response_model=MessageResponse)
async def bulk_create(
    product_id: int,
    codes:      list[str],
    mark_type:  str = "datamatrix",
    batch_id:   Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Ko'p kod bir vaqtda ro'yxatdan o'tkazish"""
    tid = resolve_tenant_id(db, current_user)
    added = 0
    for code in codes:
        code = code.strip()
        if not code: continue
        if db.query(ProductMark).filter(ProductMark.mark_code == code).first():
            continue
        db.add(ProductMark(
            tenant_id=tid, product_id=product_id, mark_code=code,
            mark_type=mark_type, batch_id=batch_id, created_by=current_user.id,
        ))
        added += 1
    db.commit()
    return MessageResponse(message=f"{added} ta kod ro'yxatga qo'shildi")


@router.get("/verify/{mark_code}")
async def verify_mark(
    mark_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Kod haqiqiyligini tekshirish (Asl belgisi)"""
    m = apply_tenant_filter(db.query(ProductMark), ProductMark, current_user) \
            .filter(ProductMark.mark_code == mark_code).first()
    if not m:
        return {
            "valid": False,
            "status": "not_found",
            "message": "Kod tizimda topilmadi — mahsulot soxta bo'lishi mumkin",
        }
    return {
        "valid":        m.status == "active",
        "status":       m.status,
        "product_name": m.product.name if m.product else None,
        "product_id":   m.product_id,
        "scanned_at":   m.scanned_at.isoformat() if m.scanned_at else None,
        "message": {
            "active":   "Haqiqiy mahsulot — sotishga ruxsat",
            "sold":     "Bu kod allaqachon skanerlangan",
            "returned": "Qaytarilgan mahsulot kodi",
            "invalid":  "Yaroqsiz kod",
        }.get(m.status, "Noma'lum holat"),
    }


@router.post("/scan", response_model=dict)
async def scan_mark(
    data: MarkScanRequest,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """POS'da sotish paytida kod skanerlash — status=sold bo'ladi"""
    m = apply_tenant_filter(db.query(ProductMark), ProductMark, current_user) \
            .filter(ProductMark.mark_code == data.mark_code).first()
    if not m:
        raise HTTPException(status_code=404, detail="Kod tizimda topilmadi")
    if m.status == "sold":
        raise HTTPException(status_code=400, detail="Bu kod allaqachon skanerlangan (sotilgan)")
    if m.status == "invalid":
        raise HTTPException(status_code=400, detail="Yaroqsiz kod")

    m.status     = "sold"
    m.order_id   = data.order_id
    m.scanned_at = datetime.utcnow()
    db.commit()
    return {
        "id":           m.id,
        "mark_code":    m.mark_code,
        "product_name": m.product.name if m.product else None,
        "status":       "sold",
        "message":      "Muvaffaqiyatli skanerlandi",
    }


@router.post("/{mark_id}/return", response_model=ProductMarkInDB)
async def return_mark(
    mark_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Mahsulot qaytarilganda kod statusini returned ga o'tkazish"""
    m = apply_tenant_filter(db.query(ProductMark), ProductMark, current_user) \
            .filter(ProductMark.id == mark_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Kod topilmadi")
    m.status   = "returned"
    m.order_id = None
    db.commit(); db.refresh(m)
    return _enrich(m)


@router.delete("/{mark_id}", response_model=MessageResponse)
async def delete_mark(
    mark_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    m = apply_tenant_filter(db.query(ProductMark), ProductMark, current_user) \
            .filter(ProductMark.id == mark_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Kod topilmadi")
    if m.status == "sold":
        raise HTTPException(status_code=400, detail="Sotilgan kodlarni o'chirish mumkin emas")
    db.delete(m); db.commit()
    return MessageResponse(message="Kod o'chirildi")
