"""
Poteriya (chiqindi) router — BOSQICH 17

Endpointlar:
  GET  /waste/          — poteriya tarixi (filtrlash bilan)
  POST /waste/          — qo'lda utilizatsiya (buzilgan/muddati o'tgan mahsulot)
  GET  /waste/report    — oylik poteriya hisoboti

Faqat oziq-ovqat bizneslari (restaurant/cafe/fast_food) uchun mo'ljallangan,
lekin feature_flags tekshiruvi frontend tomonida amalga oshiriladi.
"""
import calendar
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from deps import apply_tenant_filter, get_current_active_user, has_permission, resolve_tenant_id
from models import Inventory, Product, User, WasteLog

router = APIRouter()


@router.get("/")
async def get_waste_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    waste_type: Optional[str] = Query(None, description="recipe | manual | expired"),
    product_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Poteriya tarixi — barcha yozuvlar"""
    query = apply_tenant_filter(db.query(WasteLog), WasteLog, current_user)

    if waste_type:
        query = query.filter(WasteLog.waste_type == waste_type)
    if product_id:
        query = query.filter(WasteLog.product_id == product_id)
    if date_from:
        query = query.filter(WasteLog.created_at >= date_from)
    if date_to:
        query = query.filter(WasteLog.created_at <= datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59))

    query = query.order_by(WasteLog.created_at.desc())
    total = query.count()
    logs = query.offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for w in logs:
        result.append({
            "id": w.id,
            "product_id": w.product_id,
            "product_name": w.product.name if w.product else None,
            "quantity": w.quantity,
            "unit": w.unit,
            "unit_cost": w.unit_cost,
            "total_cost": w.total_cost,
            "waste_type": w.waste_type,
            "order_id": w.order_id,
            "notes": w.notes,
            "created_by": w.user.full_name if w.user else None,
            "created_at": w.created_at,
        })

    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.post("/")
async def create_waste_log(
    product_id: int,
    quantity: float,
    unit: str = "kg",
    waste_type: str = "manual",
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    """Qo'lda utilizatsiya — buzilgan yoki ishlatib bo'lmaydigan mahsulotni chiqarish.
    Ombordan kamaytiradi va WasteLog ga yozadi.
    waste_type: manual (odatiy) | expired (muddati o'tgan)
    """
    if waste_type not in ("manual", "expired"):
        waste_type = "manual"

    product = apply_tenant_filter(db.query(Product), Product, current_user).filter(
        Product.id == product_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Miqdor musbat bo'lishi kerak")

    tid = resolve_tenant_id(db, current_user)

    # Ombordan kamaytirish (agar ombor yozuvi bo'lsa)
    inventory = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.tenant_id == tid,
    ).first()

    if inventory:
        if inventory.quantity < quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Omborda yetarli emas: {inventory.quantity} {inventory.unit}",
            )
        inventory.quantity -= quantity

    unit_cost = product.cost_price or 0.0
    waste_log = WasteLog(
        tenant_id=tid,
        product_id=product_id,
        quantity=quantity,
        unit=unit,
        unit_cost=unit_cost,
        total_cost=round(unit_cost * quantity, 2),
        waste_type=waste_type,
        notes=notes,
        user_id=current_user.id,
    )
    db.add(waste_log)
    db.commit()
    db.refresh(waste_log)

    return {
        "success": True,
        "waste_log_id": waste_log.id,
        "product_name": product.name,
        "quantity": quantity,
        "unit": unit,
        "total_cost": waste_log.total_cost,
        "message": "Utilizatsiya qayd etildi",
    }


@router.get("/report")
async def get_waste_report(
    month: Optional[str] = Query(None, description="Format: YYYY-MM, bo'lmasa joriy oy"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Oylik poteriya hisoboti — har mahsulot bo'yicha yo'qotilgan miqdor va pul qiymati"""
    if month:
        try:
            year, mon = int(month.split("-")[0]), int(month.split("-")[1])
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Format noto'g'ri: YYYY-MM kerak")
    else:
        now = datetime.now()
        year, mon = now.year, now.month

    _, last_day = calendar.monthrange(year, mon)
    start = datetime(year, mon, 1)
    end   = datetime(year, mon, last_day, 23, 59, 59)

    logs = (
        apply_tenant_filter(db.query(WasteLog), WasteLog, current_user)
        .filter(WasteLog.created_at >= start, WasteLog.created_at <= end)
        .all()
    )

    # Mahsulot bo'yicha guruhlash
    by_product: dict = {}
    total_cost_sum = 0.0

    for w in logs:
        pid   = w.product_id
        pname = w.product.name if w.product else str(pid)
        punit = w.unit

        if pid not in by_product:
            by_product[pid] = {
                "product_id":     pid,
                "product_name":   pname,
                "unit":           punit,
                "total_quantity": 0.0,
                "total_cost":     0.0,
                "recipe_waste":   0.0,
                "manual_waste":   0.0,
                "expired_waste":  0.0,
            }

        by_product[pid]["total_quantity"] += w.quantity
        by_product[pid]["total_cost"]     += w.total_cost

        if w.waste_type == "recipe":
            by_product[pid]["recipe_waste"]  += w.quantity
        elif w.waste_type == "expired":
            by_product[pid]["expired_waste"] += w.quantity
        else:
            by_product[pid]["manual_waste"]  += w.quantity

        total_cost_sum += w.total_cost

    # Yaxlitlash
    rows = list(by_product.values())
    for r in rows:
        r["total_quantity"] = round(r["total_quantity"], 4)
        r["total_cost"]     = round(r["total_cost"], 2)
        r["recipe_waste"]   = round(r["recipe_waste"], 4)
        r["manual_waste"]   = round(r["manual_waste"], 4)
        r["expired_waste"]  = round(r["expired_waste"], 4)

    # Qiymati bo'yicha kamayish tartibida saralash
    rows.sort(key=lambda x: x["total_cost"], reverse=True)

    return {
        "month":            f"{year}-{mon:02d}",
        "total_waste_cost": round(total_cost_sum, 2),
        "total_entries":    len(logs),
        "by_product":       rows,
    }
