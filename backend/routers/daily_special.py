"""Kunlik maxsus taom — restoran/kafe uchun (BOSQICH 14)"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Optional

from database import get_db
from models import DailySpecial, Product, User
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission

router = APIRouter()


@router.get("/today")
async def get_today_specials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bugungi maxsus taomlar (POS va public menyu uchun)"""
    today = date.today()
    q = apply_tenant_filter(db.query(DailySpecial), DailySpecial, current_user)
    specials = q.filter(
        DailySpecial.date == today,
        DailySpecial.is_active == True,
    ).all()
    return [_serialize(s) for s in specials]


@router.get("/")
async def list_specials(
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Kunlik maxsus taomlar ro'yxati (admin uchun)"""
    q = apply_tenant_filter(db.query(DailySpecial), DailySpecial, current_user)
    filter_date = target_date or date.today()
    q = q.filter(DailySpecial.date == filter_date)
    return [_serialize(s) for s in q.order_by(DailySpecial.id).all()]


@router.post("/")
async def create_daily_special(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    product_id = data.get("product_id")
    if not product_id:
        raise HTTPException(status_code=422, detail="product_id majburiy")

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    raw_date = data.get("date")
    try:
        special_date = date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        raise HTTPException(status_code=422, detail="date formati noto'g'ri (YYYY-MM-DD)")

    special = DailySpecial(
        tenant_id=resolve_tenant_id(db, current_user),
        product_id=product_id,
        date=special_date,
        special_price=data.get("special_price") or None,
        special_description=data.get("special_description") or None,
        is_active=True,
    )
    db.add(special)
    db.commit()
    db.refresh(special)
    return {"id": special.id, "message": "Maxsus taom qo'shildi"}


@router.patch("/{special_id}")
async def update_daily_special(
    special_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    q = apply_tenant_filter(db.query(DailySpecial), DailySpecial, current_user)
    special = q.filter(DailySpecial.id == special_id).first()
    if not special:
        raise HTTPException(status_code=404, detail="Topilmadi")

    if "special_price" in data:
        special.special_price = data["special_price"] or None
    if "special_description" in data:
        special.special_description = data["special_description"] or None
    if "is_active" in data:
        special.is_active = bool(data["is_active"])
    db.commit()
    return {"message": "Yangilandi"}


@router.delete("/{special_id}")
async def delete_daily_special(
    special_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    q = apply_tenant_filter(db.query(DailySpecial), DailySpecial, current_user)
    special = q.filter(DailySpecial.id == special_id).first()
    if not special:
        raise HTTPException(status_code=404, detail="Topilmadi")
    db.delete(special)
    db.commit()
    return {"message": "O'chirildi"}


def _serialize(s: DailySpecial) -> dict:
    return {
        "id": s.id,
        "product_id": s.product_id,
        "product_name": s.product.name if s.product else "—",
        "product_image": s.product.image_url if s.product else None,
        "category_name": s.product.category.name if s.product and s.product.category else None,
        "original_price": s.product.price if s.product else 0,
        "special_price": s.special_price,
        "display_price": s.special_price if s.special_price else (s.product.price if s.product else 0),
        "special_description": s.special_description,
        "date": s.date.isoformat(),
        "is_active": s.is_active,
    }
