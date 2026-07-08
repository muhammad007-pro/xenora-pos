from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from database import get_db
from models import Order, OrderItem, User, Product
from schemas import OrderInDB, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, has_permission, apply_tenant_filter
from services.kitchen_service import KitchenService
from websocket.manager import manager

router = APIRouter()

def _build_other_stations(order, current_station_id: Optional[int]) -> list:
    """Bir xil buyurtmada boshqa stansiyalarning tayyorlik holati."""
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for item in order.items:
        sid = item.product.station_id  # None yoki int
        groups[sid].append(item)

    result = []
    for sid, sitems in groups.items():
        if sid == current_station_id:
            continue
        if sid is None and current_station_id is None:
            continue
        sname = (sitems[0].product.station.name
                 if sid and sitems[0].product.station else "Oshxona")
        ready = sum(1 for i in sitems if i.status in ("ready", "served"))
        result.append({
            "station_id":   sid,
            "station_name": sname,
            "items_count":  len(sitems),
            "ready_count":  ready,
            "all_ready":    ready == len(sitems),
        })
    return result


@router.get("/orders")
async def get_kitchen_orders(
    station_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Oshxona uchun buyurtmalarni olish.
    station_id=None → barcha, station_id=N → faqat shu stansiya itemlari.
    """
    kitchen_service = KitchenService(db)
    rows = kitchen_service.get_kitchen_orders(
        station_id=station_id, status=status, current_user=current_user
    )

    pending = []
    preparing = []
    ready = []

    for row in rows:
        order = row["order"]
        items = row["filtered_items"]

        # Tayyorlash vaqti: bu stansiya uchun max preparation_time
        expected_prep = max(
            (item.product.preparation_time or 10) for item in items
        ) if items else 15

        order_data = {
            "id":                   order.id,
            "order_number":         order.order_number,
            "table_number":         order.table.number if order.table else None,
            "order_type":           order.order_type if hasattr(order, "order_type") else ("dine-in" if order.table else "takeaway"),
            "waiter_name":          order.waiter.full_name if order.waiter else None,
            "customer_name":        order.customer.name if order.customer else None,
            "created_at":           order.created_at,
            "updated_at":           order.updated_at,   # "tayyor bo'lган vaqti" (ready holatда) uchun
            "preparing_started_at": order.preparing_started_at,
            "status":               order.status,
            "notes":                order.notes,
            "urgent":               "tez" in (order.notes or "").lower(),
            # Tayyorlash vaqti (daqiqa) — timer rang hisoblash uchun
            "expected_prep_time":   expected_prep,
            # Boshqa stansiyalar holati — stansiyalararo muvofiqlik uchun
            "other_stations":       _build_other_stations(order, station_id),
            "items": [
                {
                    "id":               item.id,
                    "product_id":       item.product_id,
                    "product_name":     item.product.name,
                    "quantity":         item.quantity,
                    "notes":            item.notes,
                    "status":           item.status,
                    "station_id":       item.product.station_id,
                    "preparation_time": item.product.preparation_time or 10,
                }
                for item in items
            ],
        }

        if order.status in ("pending", "confirmed"):
            pending.append(order_data)
        elif order.status == "preparing":
            preparing.append(order_data)
        elif order.status == "ready":
            ready.append(order_data)

    return {"pending": pending, "preparing": preparing, "ready": ready, "completed": []}

@router.patch("/orders/{order_id}/start")
async def start_preparing_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtmani tayyorlashni boshlash"""
    kitchen_service = KitchenService(db)

    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    
    if order.status not in ["pending", "confirmed"]:
        raise HTTPException(status_code=400, detail="Bu buyurtmani tayyorlashni boshlab bo'lmaydi")
    
    order.status = "preparing"
    order.preparing_started_at = datetime.now()
    db.commit()

    # WebSocket orqali xabar yuborish
    await manager.broadcast_to_pos({
        "type": "order_status_changed",
        "order_id": order_id,
        "order_number": order.order_number,
        "status": "preparing"
    }, tenant_id=resolve_tenant_id(db, current_user))

    return MessageResponse(message="Buyurtma tayyorlash boshlandi")

@router.patch("/orders/{order_id}/ready")
async def mark_order_ready(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtmani tayyor deb belgilash"""
    kitchen_service = KitchenService(db)

    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    
    # OSHXONA 1-bosqich: 1 bosishда tayyor — pending/confirmed/preparing holatidan qabul qilamiz
    # (oraliq "preparing" bosqichi majburiy emas). ready/completed/cancelled — rad etiladi (qayta chiqim yo'q).
    if order.status not in ("pending", "confirmed", "preparing"):
        raise HTTPException(status_code=400, detail="Bu buyurtmani tayyor deb belgilab bo'lmaydi")

    if not order.preparing_started_at:
        order.preparing_started_at = datetime.now()
    order.status = "ready"
    db.commit()

    # BOSQICH 5.4 + Oshxona 2: retsept inventar chiqimi FAQAT BIR MARTA
    # (reopen → qayta-ready ikki marta chiqim qilmasligi uchun ingredients_deducted guard).
    if not order.ingredients_deducted:
        try:
            from services.recipe_inventory_service import deduct_order_ingredients
            deduct_order_ingredients(db, order_id, tenant_id=resolve_tenant_id(db, current_user))
            order.ingredients_deducted = True
            db.commit()
        except Exception:
            pass  # inventory xatoligi buyurtma holatini bloklamas

    # WebSocket orqali xabar yuborish
    await manager.broadcast_to_pos({
        "type": "order_ready",
        "order_id": order_id,
        "order_number": order.order_number,
        "table_number": order.table.number if order.table else None
    }, tenant_id=resolve_tenant_id(db, current_user))

    # Ofitsiantga bildirishnoma
    if order.waiter_id:
        await manager.send_to_user(order.waiter_id, {
            "type": "notification",
            "title": "Buyurtma tayyor",
            "message": f"#{order.order_number} buyurtma tayyor",
            "order_id": order_id
        })
    
    return MessageResponse(message="Buyurtma tayyor")

@router.patch("/orders/{order_id}/served")
async def mark_order_served(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Ofitsiant buyurtmani oldi — completed ga o'tkazish"""
    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if order.status != "ready":
        raise HTTPException(status_code=400, detail="Bu buyurtma tayyor holatida emas")

    order.status = "completed"
    order.completed_at = datetime.now()
    db.commit()

    await manager.broadcast_to_pos({
        "type":         "order_served",
        "order_id":     order_id,
        "order_number": order.order_number,
        "table_number": order.table.number if order.table else None,
    }, tenant_id=resolve_tenant_id(db, current_user))

    return MessageResponse(message="Buyurtma berildi")


@router.patch("/orders/{order_id}/reopen")
async def reopen_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Tayyor zakazni FAOL holatga qaytarish (povar xato bosса — tuzatish).

    FAQAT 'ready' holatidagini qaytarish mumkin. completed/cancelled/served (sotuv yopilган)
    — HIMOYALANGAN, qaytarib bo'lmaydi. Inventar chiqimi ORQAGA QAYTARILMAYDI
    (ingredients_deducted saqlanadi — qayta-ready ikki marta chiqim qilmaydi)."""
    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    if order.status != "ready":
        raise HTTPException(status_code=400, detail="Faqat 'tayyor' holatidagi zakazni qaytarish mumkin")

    order.status = "preparing"
    # Tayyor belgilangan taomlarni ham qaytarish (povar qayta belgilashi uchun)
    for it in order.items:
        if it.status in ("ready", "served"):
            it.status = "preparing"
    order.updated_at = datetime.now()
    db.commit()

    await manager.broadcast_to_pos({
        "type": "order_status_changed",
        "order_id": order_id,
        "order_number": order.order_number,
        "status": "preparing",
    }, tenant_id=resolve_tenant_id(db, current_user))

    return MessageResponse(message="Zakaz faol holatga qaytarildi")


@router.patch("/items/{item_id}/status")
async def update_item_status(
    item_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtma elementi holatini yangilash"""
    # BOSQICH 1.5: tenant bo'yicha cheklash (Order orqali)
    item = db.query(OrderItem).join(Order).filter(OrderItem.id == item_id)
    item = apply_tenant_filter(item, Order, current_user).first()
    if not item:
        raise HTTPException(status_code=404, detail="Buyurtma elementi topilmadi")
    
    valid_statuses = ["pending", "preparing", "ready", "served"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Noto'g'ri holat. Ruxsat etilgan: {valid_statuses}")
    
    item.status = status
    db.commit()
    
    # Agar barcha itemlar tayyor bo'lsa, buyurtmani tayyor deb belgilash
    order = item.order
    all_ready = all(i.status == "ready" for i in order.items)

    # OSHXONA 1-bosqich: barcha taomlar tayyor bo'lsa zakaz avtomatik "ready" (pending/preparing dan ham).
    if all_ready and order.status in ("pending", "confirmed", "preparing"):
        if not order.preparing_started_at:
            order.preparing_started_at = datetime.now()
        order.status = "ready"
        db.commit()

        # Retsept inventar chiqimi (mark_order_ready bilan bir xil — FAQAT bir marta)
        if not order.ingredients_deducted:
            try:
                from services.recipe_inventory_service import deduct_order_ingredients
                deduct_order_ingredients(db, order.id, tenant_id=resolve_tenant_id(db, current_user))
                order.ingredients_deducted = True
                db.commit()
            except Exception:
                pass  # inventory xatoligi holatni bloklamas

        await manager.broadcast_to_pos({
            "type": "order_ready",
            "order_id": order.id,
            "order_number": order.order_number
        }, tenant_id=resolve_tenant_id(db, current_user))

    return MessageResponse(message=f"Element holati yangilandi: {status}")

@router.get("/history")
async def get_kitchen_history(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    station: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Oshxona tarixini olish"""
    query = db.query(Order).filter(Order.status.in_(["completed", "cancelled"]))
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Order, current_user)

    if date_from:
        query = query.filter(Order.created_at >= date_from)
    
    if date_to:
        query = query.filter(Order.created_at <= date_to)
    
    total = query.count()
    orders = query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    items = []
    for order in orders:
        preparation_time = None
        if order.completed_at and order.created_at:
            delta = order.completed_at - order.created_at
            preparation_time = delta.total_seconds() // 60
        
        items.append({
            "id": order.id,
            "order_number": order.order_number,
            "table_number": order.table.number if order.table else None,
            "order_type": "dine-in" if order.table else "takeaway",
            "status": order.status,
            "created_at": order.created_at,
            "completed_at": order.completed_at,
            "preparation_time": preparation_time,
            "items_count": len(order.items)
        })
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }

@router.get("/stats")
async def get_kitchen_stats(
    date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Oshxona statistikasi"""
    from sqlalchemy import func

    target_date = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now().date()

    query = db.query(Order).filter(
        func.date(Order.created_at) == target_date
    )
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Order, current_user)

    total_orders = query.count()
    completed_orders = query.filter(Order.status == "completed").count()
    cancelled_orders = query.filter(Order.status == "cancelled").count()
    
    # O'rtacha tayyorlash vaqti
    completed = query.filter(Order.status == "completed").all()
    prep_times = []
    
    for order in completed:
        if order.completed_at and order.created_at:
            delta = order.completed_at - order.created_at
            prep_times.append(delta.total_seconds() // 60)
    
    avg_prep_time = sum(prep_times) / len(prep_times) if prep_times else 0
    
    return {
        "date": target_date.isoformat(),
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "cancelled_orders": cancelled_orders,
        "completion_rate": (completed_orders / total_orders * 100) if total_orders > 0 else 0,
        "average_preparation_time": round(avg_prep_time, 1)
    }
