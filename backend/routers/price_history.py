"""Narx tarixi — mahsulot narxi qachon, kim tomonidan o'zgartirildi"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from database import get_db
from models import PriceHistory, Product, User
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()


@router.get("/product/{product_id}")
async def get_product_price_history(
    product_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Mahsulot narxi o'zgarish tarixi"""
    tid = resolve_tenant_id(db, current_user)
    rows = db.query(PriceHistory).filter(
        PriceHistory.product_id == product_id,
        PriceHistory.tenant_id == tid,
    ).order_by(PriceHistory.created_at.desc()).limit(limit).all()

    return [_hist_dict(r) for r in rows]


@router.get("/")
async def get_price_history(
    product_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Narx o'zgarishlar logi (admin uchun)"""
    tid = resolve_tenant_id(db, current_user)
    q = db.query(PriceHistory).filter(PriceHistory.tenant_id == tid)
    if product_id:
        q = q.filter(PriceHistory.product_id == product_id)
    if date_from:
        q = q.filter(PriceHistory.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        q = q.filter(PriceHistory.created_at <= datetime.fromisoformat(date_to))
    total = q.count()
    rows = q.order_by(PriceHistory.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_hist_dict(r) for r in rows], "total": total}


def record_price_change(
    db: Session,
    tenant_id: int,
    product: Product,
    new_price: float,
    new_cost: Optional[float],
    changed_by: int,
    reason: Optional[str] = None,
):
    """Narx o'zgarganda chaqiriladi (product routerdan)"""
    if product.price == new_price and product.cost_price == new_cost:
        return
    ph = PriceHistory(
        tenant_id=tenant_id,
        product_id=product.id,
        old_price=product.price,
        new_price=new_price,
        old_cost=product.cost_price,
        new_cost=new_cost,
        reason=reason,
        changed_by=changed_by,
    )
    db.add(ph)


def _hist_dict(r: PriceHistory) -> dict:
    return {
        "id": r.id,
        "product_id": r.product_id,
        "product_name": r.product.name if r.product else None,
        "old_price": r.old_price,
        "new_price": r.new_price,
        "old_cost": r.old_cost,
        "new_cost": r.new_cost,
        "change_pct": round((r.new_price - r.old_price) / r.old_price * 100, 1) if r.old_price else 0,
        "reason": r.reason,
        "changed_by": r.changer.full_name if r.changer else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
