from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from database import get_db
from models import Discount, User
from schemas import DiscountCreate, DiscountInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()

@router.get("/", response_model=PaginatedResponse)
async def get_promos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha promo/chegirmalarni olish"""
    query = db.query(Discount)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Discount, current_user)

    if is_active is not None:
        query = query.filter(Discount.is_active == is_active)
    
    total = query.count()
    promos = query.order_by(Discount.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[DiscountInDB.model_validate(p) for p in promos],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.post("/", response_model=DiscountInDB)
async def create_promo(
    promo_data: DiscountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_discounts"))
):
    """Yangi promo yaratish"""
    # BOSQICH 1.5: yangi yozuv yaratuvchi tenant'iga biriktiriladi
    promo = Discount(**promo_data.model_dump(), tenant_id=resolve_tenant_id(db, current_user))
    db.add(promo)
    db.commit()
    db.refresh(promo)
    
    return DiscountInDB.model_validate(promo)

@router.get("/validate/{code}")
async def validate_promo_code(
    code: str,
    order_amount: float,
    db: Session = Depends(get_db)
):
    """Promo kodni tekshirish"""
    now = datetime.now()
    
    promo = db.query(Discount).filter(
        Discount.name == code,
        Discount.is_active == True,
        (Discount.valid_from.is_(None) | (Discount.valid_from <= now)),
        (Discount.valid_to.is_(None) | (Discount.valid_to >= now))
    ).first()
    
    if not promo:
        return {"valid": False, "message": "Promo kod topilmadi yoki muddati o'tgan"}
    
    if order_amount < promo.min_order_amount:
        return {
            "valid": False,
            "message": f"Minimal buyurtma summasi {promo.min_order_amount:,.0f} UZS"
        }
    
    # Chegirma hisoblash
    discount_amount = 0
    if promo.type == "percentage":
        discount_amount = order_amount * (promo.value / 100)
    else:
        discount_amount = min(promo.value, order_amount)
    
    return {
        "valid": True,
        "promo_id": promo.id,
        "promo_code": promo.name,
        "discount_amount": discount_amount,
        "final_amount": order_amount - discount_amount
    }

@router.patch("/{promo_id}/toggle")
async def toggle_promo(
    promo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_discounts"))
):
    """Promoni yoqish/o'chirish"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    promo = apply_tenant_filter(db.query(Discount), Discount, current_user).filter(Discount.id == promo_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo topilmadi")
    
    promo.is_active = not promo.is_active
    db.commit()
    
    return MessageResponse(
        message=f"Promo { 'faollashtirildi' if promo.is_active else 'o\'chirildi' }"
    )
