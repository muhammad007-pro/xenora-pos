"""
Mijozdan vozvrat (kengaytirilgan) — BOSQICH 25
Mavjud returns'ni store/supermarket uchun kengaytiradi:
- Chek raqami bo'yicha buyurtma qidirish
- Har item uchun: omborgami yoki brakkami yo'naltirish
- Qaytarish yoki almashtirish tanlash
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import date, datetime
from typing import Optional, List

from database import get_db
from models import Return, ReturnItem, Order, OrderItem, Product, Inventory, StockMovement, User
from schemas import MessageResponse, PaginatedResponse
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission
from routers.returns import _return_base_qty  # BOSQICH B-returns: pachka → dona miqdori
from pydantic import BaseModel
from typing import Optional

from deps import require_feature  # funksiya-flag himoyasi (O'ZGARISH 3)
router = APIRouter(dependencies=[Depends(require_feature("customer_return_ext"))])


# ── Schemas (local, kengaytirilgan) ──────────────────────────────────────────

class ExtReturnItemCreate(BaseModel):
    product_id:           int
    order_item_id:        Optional[int] = None
    quantity:             float
    unit_price:           float
    restore_to_inventory: bool = True
    goes_to_brak:         bool = False
    notes:                Optional[str] = None

class ExtReturnCreate(BaseModel):
    order_id:      Optional[int] = None
    customer_id:   Optional[int] = None
    reason:        str = "other"        # broken/dislike/expired/wrong_item/other
    refund_method: str = "cash"         # cash/card/credit/exchange
    notes:         Optional[str] = None
    items:         List[ExtReturnItemCreate]

class OrderSearchResult(BaseModel):
    id:            int
    order_number:  Optional[str] = None
    total_amount:  float
    created_at:    datetime
    items: List[dict] = []


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/search-order")
async def search_order(
    q:  str = Query(..., min_length=1, description="Buyurtma raqami yoki ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Chek raqami bo'yicha buyurtma qidirish — vozvrat uchun tovarlarni oldindan to'ldirish"""
    orders = apply_tenant_filter(db.query(Order), Order, current_user) \
                 .filter(or_(
                     Order.order_number.ilike(f"%{q}%"),
                     Order.id == int(q) if q.isdigit() else Order.id == -1,
                 )).limit(5).all()
    result = []
    for o in orders:
        items = []
        for oi in o.items:
            items.append({
                "id":         oi.id,
                "product_id": oi.product_id,
                "product_name": oi.product.name if oi.product else f"#{oi.product_id}",
                "quantity":   oi.quantity,
                "unit_price": oi.unit_price,
                "total":      oi.total_price,
            })
        result.append({
            "id":           o.id,
            "order_number": getattr(o, "order_number", None),
            "total_amount": o.total_amount,
            "created_at":   o.created_at.isoformat() if o.created_at else None,
            "items":        items,
        })
    return result


@router.post("/")
async def create_extended_return(
    data: ExtReturnCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("process_payments")),
):
    """Kengaytirilgan qaytarish: brak/ombor tanlash bilan"""
    if not data.items:
        raise HTTPException(status_code=400, detail="Kamida 1 ta tovar kiritilsin")

    tid = resolve_tenant_id(db, current_user)
    total = sum(i.quantity * i.unit_price for i in data.items)

    # Return number
    today = date.today()
    prefix = f"REXT{today.strftime('%y%m%d')}"
    count  = db.query(Return).filter(Return.return_number.like(f"{prefix}%")).count()
    rnum   = f"{prefix}{count+1:03d}"

    ret = Return(
        tenant_id     = tid,
        return_number = rnum,
        order_id      = data.order_id,
        customer_id   = data.customer_id,
        reason        = data.reason,
        total_amount  = total,
        refund_method = data.refund_method,
        status        = "approved",   # store: avtomatik tasdiqlash
        notes         = data.notes,
        user_id       = current_user.id,
        approved_by   = current_user.id,
        approved_at   = datetime.utcnow(),
    )
    db.add(ret)
    db.flush()

    for it in data.items:
        # BOSQICH B-returns: omborga qaytariladigan DONA miqdori (pachka: pack_size×qty)
        base_qty = _return_base_qty(db, it.order_item_id, it.quantity)
        db.add(ReturnItem(
            return_id            = ret.id,
            product_id           = it.product_id,
            order_item_id        = it.order_item_id,
            quantity             = it.quantity,
            base_qty             = base_qty,
            unit_price           = it.unit_price,
            total                = it.quantity * it.unit_price,
            restore_to_inventory = it.restore_to_inventory and not it.goes_to_brak,
            goes_to_brak         = it.goes_to_brak,
        ))

        # Ombor harakati — base_qty (dona) bilan
        if it.restore_to_inventory and not it.goes_to_brak:
            inv = apply_tenant_filter(db.query(Inventory), Inventory, current_user) \
                      .filter(Inventory.product_id == it.product_id).with_for_update().first()   # ROW-LOCK
            if inv:
                inv.quantity += base_qty
            else:
                db.add(Inventory(tenant_id=tid, product_id=it.product_id, quantity=base_qty))
        # goes_to_brak=True bo'lsa omborga qaytarilmaydi — faqat yoziladi

    db.commit()
    db.refresh(ret)
    return {"id": ret.id, "return_number": ret.return_number, "total_amount": ret.total_amount,
            "status": ret.status, "message": "Qaytarish saqlandi"}


@router.get("/")
async def list_extended_returns(
    reason:    Optional[str] = None,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Extended vozvrat ro'yxati (REXT... raqamli)"""
    q = apply_tenant_filter(db.query(Return), Return, current_user) \
            .filter(Return.return_number.like("REXT%"))
    if reason:    q = q.filter(Return.reason == reason)
    if date_from: q = q.filter(Return.created_at >= date_from)
    if date_to:   q = q.filter(Return.created_at <= date_to + "T23:59:59")
    total = q.count()
    rows  = q.order_by(Return.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    items = []
    for r in rows:
        items.append({
            "id":            r.id,
            "return_number": r.return_number,
            "reason":        r.reason,
            "refund_method": r.refund_method,
            "total_amount":  r.total_amount,
            "status":        r.status,
            "created_at":    r.created_at.isoformat() if r.created_at else None,
            "items": [{
                "product_id":   i.product_id,
                "product_name": i.product.name if i.product else None,
                "quantity":     i.quantity,
                "unit_price":   i.unit_price,
                "goes_to_brak": i.goes_to_brak,
                "restore_to_inventory": i.restore_to_inventory,
            } for i in r.items],
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": (total+page_size-1)//page_size}
