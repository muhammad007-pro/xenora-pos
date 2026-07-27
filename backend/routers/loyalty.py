"""
Loyalty (Bonus) dasturi (BOSQICH 5.2)

Qoidalar:
  - Har 1000 UZS xaridda 1 ball yig'iladi (POINTS_PER_AMOUNT)
  - 1 ball = 10 UZS qiymati (POINT_VALUE)
  - Minimal yechish: 100 ball
  - Maksimal chegirma: to'lov summasining 30%
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from pydantic import BaseModel

from database import get_db
from models import Customer, Order, Payment, User
from deps import get_current_active_user, apply_tenant_filter, has_permission, resolve_tenant_id
from core.loyalty_config import get_loyalty_config, DEFAULTS, CONFIG_NAME
from core.tenant_config import set_tenant_config

router = APIRouter()


class LoyaltySettingsBody(BaseModel):
    enabled:            Optional[bool]  = None
    earn_rate:          Optional[int]   = None
    redeem_value:       Optional[float] = None
    min_redeem_points:  Optional[int]   = None
    max_redeem_percent: Optional[float] = None


@router.get("/settings")
async def get_loyalty_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Joriy tenant sodiqlik sozlamalari (default bilan). POS ham shundan o'qiydi."""
    return get_loyalty_config(db, resolve_tenant_id(db, current_user))


@router.patch("/settings")
async def update_loyalty_settings(
    body: LoyaltySettingsBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings")),
):
    """Sodiqlik sozlamalarini yangilash (tenant-scoped, TenantSettings). Faqat sozlama huquqli."""
    tid = current_user.tenant_id
    if not tid:
        raise HTTPException(status_code=400, detail="Bu amal uchun tenant kerak")
    cfg = get_loyalty_config(db, tid)
    cfg.update(body.model_dump(exclude_none=True))
    set_tenant_config(db, tid, CONFIG_NAME, {k: cfg[k] for k in DEFAULTS})
    return get_loyalty_config(db, tid)   # normallashtirilgan qiymatlarni qaytaradi

POINTS_PER_AMOUNT = 1000    # har shu UZS da 1 ball
POINT_VALUE       = 10      # 1 ball necha UZS
MIN_REDEEM        = 100     # minimal yechish (ball)
MAX_DISCOUNT_PCT  = 0.30    # maksimal chegirma foizi


def _calc_earn(amount: float) -> int:
    """To'lov summasidan yig'ilgan ball hisoblash"""
    return max(0, int(amount // POINTS_PER_AMOUNT))


def _calc_redeem_amount(points: int) -> float:
    """Ballar UZS ga o'girish"""
    return points * POINT_VALUE


@router.get("/summary/{customer_id}")
async def get_loyalty_summary(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Mijozning loyalty holati"""
    customer = apply_tenant_filter(db.query(Customer), Customer, current_user) \
        .filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    return {
        "customer_id":    customer.id,
        "name":           customer.name,
        "points":         customer.points,
        "points_value":   _calc_redeem_amount(customer.points),
        "total_spent":    customer.total_spent,
        "total_visits":   customer.total_visits,
        "tier":           _get_tier(customer.total_spent),
        "next_tier":      _get_next_tier(customer.total_spent),
        "earn_rate":      f"Har {POINTS_PER_AMOUNT:,} UZS = 1 ball",
        "redeem_rate":    f"1 ball = {POINT_VALUE} UZS",
        "min_redeem":     MIN_REDEEM,
    }


@router.post("/earn/{customer_id}")
async def earn_points(
    customer_id: int,
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_customers")),
):
    """To'lov yakunida ball yig'ish"""
    customer = apply_tenant_filter(db.query(Customer), Customer, current_user) \
        .filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    order = apply_tenant_filter(db.query(Order), Order, current_user) \
        .filter(Order.id == order_id, Order.customer_id == customer_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    earned = _calc_earn(order.final_amount)
    if earned == 0:
        return {"message": "Ball yig'ilmadi (summa yetarli emas)", "points_earned": 0}

    customer.points       += earned
    customer.total_spent  += order.final_amount
    customer.total_visits += 1
    db.commit()

    return {
        "message":       f"{earned} ball yig'ildi",
        "points_earned": earned,
        "total_points":  customer.points,
        "tier":          _get_tier(customer.total_spent),
    }


@router.post("/redeem/{customer_id}")
async def redeem_points(
    customer_id: int,
    points: int = Query(..., ge=MIN_REDEEM, description=f"Minimal {MIN_REDEEM} ball"),
    order_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_customers")),
):
    """Ballarni chegirmaga aylantirish"""
    customer = apply_tenant_filter(db.query(Customer), Customer, current_user) \
        .filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    if customer.points < points:
        raise HTTPException(
            status_code=400,
            detail=f"Yetarli ball yo'q. Mavjud: {customer.points}, so'ralgan: {points}"
        )

    discount_amount = _calc_redeem_amount(points)

    # Agar order_id berilsa — maksimal chegirmani tekshirish
    if order_id:
        order = apply_tenant_filter(db.query(Order), Order, current_user) \
            .filter(Order.id == order_id).first()
        if order:
            max_discount = order.final_amount * MAX_DISCOUNT_PCT
            if discount_amount > max_discount:
                discount_amount = max_discount
                points = int(discount_amount // POINT_VALUE)

    customer.points -= points
    db.commit()

    return {
        "message":          f"{points} ball ishlatildi",
        "points_used":      points,
        "discount_amount":  discount_amount,
        "remaining_points": customer.points,
    }


@router.post("/adjust/{customer_id}")
async def adjust_points(
    customer_id: int,
    delta: int = Query(..., description="Qo'shish (+) yoki ayirish (-) miqdori"),
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_customers")),
):
    """Admin tomonidan ballarni qo'lda o'zgartirish"""
    customer = apply_tenant_filter(db.query(Customer), Customer, current_user) \
        .filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    new_points = customer.points + delta
    if new_points < 0:
        raise HTTPException(status_code=400, detail="Ball manfiy bo'lishi mumkin emas")

    customer.points = new_points
    db.commit()

    return {
        "message":       f"Ball {'qo\'shildi' if delta > 0 else 'ayirildi'}: {abs(delta)}",
        "delta":         delta,
        "total_points":  customer.points,
        "reason":        reason,
    }


# ── Yordamchi: tier tizimi ────────────────────────────────────────────────────

TIERS = [
    (0,       "Bronze"),
    (500_000, "Silver"),
    (2_000_000,"Gold"),
    (5_000_000,"Platinum"),
]

def _get_tier(total_spent: float) -> str:
    tier = "Bronze"
    for threshold, name in TIERS:
        if total_spent >= threshold:
            tier = name
    return tier

def _get_next_tier(total_spent: float) -> Optional[dict]:
    for threshold, name in TIERS:
        if total_spent < threshold:
            return {"name": name, "required": threshold, "remaining": threshold - total_spent}
    return None
