from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from database import get_db
from models import Order, OrderItem, Product, Table, User, Cafe, ReceiptSettings
from schemas import OrderCreate, OrderUpdate, OrderInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, apply_tenant_filter
from services.order_service import OrderService
from services.kitchen_service import KitchenService
from services.printer_service import PrinterService, print_receipt as escpos_print_receipt
from websocket.manager import manager
from core.subscription import is_within_order_limit, get_plan_limits
from core.tenant_config import get_tenant_config  # BOSQICH 40 (3b): printer tenant-scoped
from core.feature_flags import Feature, is_feature_enabled  # kitchen_display gate
from core.audit import log_audit  # xodim harakatlarini yozish (audit)

router = APIRouter()


def _enrich_order(o):
    """Order ORM obyektiga ko'rinadigan maydonlarni qo'shadi: kassir nomi, kassa nomi
    (Shift.register orqali), to'lov usuli (Payment). Yo'q bo'lsa null — eski cheklar
    xato bermaydi. OrderInDB.model_validate shu transient atributlarni o'qiydi."""
    o.waiter_name = o.waiter.full_name if o.waiter else None
    o.register_name = o.shift.register.name if (o.shift and o.shift.register) else None
    paid = next((p for p in o.payments if p.status == "paid"), None)
    _pm = paid.method if paid else (o.payments[0].method if o.payments else None)
    o.payment_method = getattr(_pm, "value", _pm)
    return o

@router.get("/", response_model=PaginatedResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: Optional[str] = None,
    table_id: Optional[int] = None,
    order_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    cashier_id: Optional[int] = None,
    register_id: Optional[int] = None,
    has_rx: Optional[bool] = None,
    has_student: Optional[bool] = None,
    student_group: Optional[str] = None,
    has_cleaning: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Sotuvlar/buyurtmalar tarixi — filtrlar bilan (sana, kassir, kassa, status)."""
    order_service = OrderService(db)
    orders, total = order_service.get_orders(
        page=page,
        page_size=page_size,
        current_user=current_user,
        status=status,
        table_id=table_id,
        order_type=order_type,
        date_from=date_from,
        date_to=date_to,
        cashier_id=cashier_id,
        register_id=register_id,
        has_rx=has_rx,
        has_student=has_student,
        student_group=student_group,
        has_cleaning=has_cleaning,
        search=search,
    )

    # Enrichment: kassir/kassa/to'lov (eski cheklar uchun null — xato bermaydi)
    items = [OrderInDB.model_validate(_enrich_order(o)) for o in orders]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.post("/", response_model=OrderInDB)
async def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Yangi buyurtma yaratish"""
    order_service = OrderService(db)
    kitchen_service = KitchenService(db)

    # Stolni tekshirish вЂ” delivery/takeaway da stol shart emas
    table = None
    if order_data.table_id:
        table = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == order_data.table_id).first()
        if not table:
            raise HTTPException(status_code=404, detail="Stol topilmadi")

    # BOSQICH 2.2: oylik buyurtma limiti tekshirish (FREE tarif: 100/oy)
    if not current_user.is_superuser and current_user.tenant_id is not None:
        from sqlalchemy import func as sqlfunc
        cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
        if cafe:
            now = datetime.now()
            monthly_count = db.query(Order).filter(
                Order.tenant_id == current_user.tenant_id,
                sqlfunc.extract('year', Order.created_at) == now.year,
                sqlfunc.extract('month', Order.created_at) == now.month
            ).count()
            if not is_within_order_limit(monthly_count, cafe.subscription_plan):
                limits = get_plan_limits(cafe.subscription_plan)
                raise HTTPException(
                    status_code=402,
                    detail=f"'{cafe.subscription_plan}' tarifi oyiga faqat {limits.max_orders_month} ta buyurtmaga ruxsat beradi. "
                           f"Tarifni yangilang."
                )

    # Buyurtmani yaratish — tenant_id servisga uzatiladi (kunlik chek raqami shu bo'yicha)
    tenant_id = resolve_tenant_id(db, current_user)
    order = order_service.create_order(
        order_data=order_data,
        waiter_id=current_user.id,
        tenant_id=tenant_id,
    )

    # Stol statusini yangilash (faqat stol bor bo'lsa)
    if table:
        table.status = "occupied"
        db.commit()

    # ── Oshxona integratsiyasi — FAQAT kitchen_display feature yoniq turlarda ──
    # restaurant/cafe → ishlaydi. store/dorixona/xizmat (kitchen_display o'chiq) →
    # oshxona cheki ham, kitchen queue/WS ham o'tkazib yuboriladi (ortiqcha
    # "OSHXONA" cheki chiqmaydi). Mijoz cheki bunга bog'liq emas — har turда ishlaydi.
    _cafe = db.query(Cafe).filter(Cafe.id == order.tenant_id).first() if order.tenant_id else None
    _kitchen_on = bool(_cafe) and is_feature_enabled(
        _cafe.business_type, Feature.KITCHEN_DISPLAY,
        _cafe.enabled_features, _cafe.disabled_features,
        _cafe.subscription_plan,
    )

    if _kitchen_on:
        # Oshxonaga yuborish (kitchen queue)
        kitchen_service.send_order_to_kitchen(order)

        # WebSocket orqali oshxonaga yangi buyurtma xabari (BOSQICH 2.5: tenant-izolyatsiyalangan)
        await manager.broadcast_to_kitchen({
            "type": "new_order",
            "order_id": order.id,
            "order_number": order.order_number,
            "table": table.number if table else None,
            "items": [{"name": item.product.name, "quantity": item.quantity} for item in order.items]
        }, tenant_id=resolve_tenant_id(db, current_user))

        # Oshxona cheki — ikki himoya: kitchen_display feature YONIQ (yuqorida) VA
        # printer cfg'da kitchen_print=true bo'lsa (BOSQICH 40: tenant printer config).
        _printer_cfg = get_tenant_config(db, order.tenant_id or resolve_tenant_id(db, current_user), "printer")
        if PrinterService.is_available() and (_printer_cfg or {}).get("kitchen_print"):
            PrinterService.print_kitchen_receipt(order, cfg=_printer_cfg)

    # Audit: kim buyurtma qabul qildi (asosiy amalni buzmaydi)
    log_audit(current_user, "orders", "CREATE", order.id, tenant_id=order.tenant_id, detail={
        "order_number": order.order_number,
        "total": order.final_amount,
        "table": (table.number if table else None),
        "items_count": len(order.items or []),
    })
    return OrderInDB.model_validate(order)

@router.get("/{order_id}", response_model=OrderInDB)
async def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtma ma'lumotlarini olish"""
    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    return OrderInDB.model_validate(_enrich_order(order))

@router.patch("/{order_id}", response_model=OrderInDB)
async def update_order(
    order_id: int,
    order_data: OrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtmani yangilash"""
    order_service = OrderService(db)

    # BOSQICH 1.5: tenant bo'yicha cheklash вЂ” boshqa tenant buyurtmasi topilmaydi
    existing = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    order = order_service.update_order(order_id, order_data)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    
    # Agar buyurtma yakunlangan bo'lsa, stolni bo'shatish
    if order_data.status in ("completed", "cancelled") and order.table:
        order.table.status = "free"
        db.commit()

        await manager.broadcast({
            "type": "table_freed",
            "table_id": order.table.id,
            "table_number": order.table.number
        })
    
    return OrderInDB.model_validate(order)

@router.post("/{order_id}/items")
async def add_item_to_order(
    order_id: int,
    product_id: int,
    quantity: int = 1,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtmaga mahsulot qo'shish"""
    order_service = OrderService(db)

    # BOSQICH 1.5: tenant bo'yicha cheklash вЂ” boshqa tenant buyurtmasi topilmaydi
    existing = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Buyurtma yoki mahsulot topilmadi")

    order = order_service.add_item(order_id, product_id, quantity, notes)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma yoki mahsulot topilmadi")
    
    # Oshxonaga yangi item haqida xabar yuborish
    product = db.query(Product).filter(Product.id == product_id).first()
    await manager.broadcast_to_kitchen({
        "type": "item_added",
        "order_id": order_id,
        "order_number": order.order_number,
        "item": {
            "product_id": product_id,
            "product_name": product.name,
            "quantity": quantity,
            "notes": notes
        }
    }, tenant_id=resolve_tenant_id(db, current_user))
    
    return MessageResponse(message="Mahsulot qo'shildi")

@router.delete("/{order_id}/items/{item_id}")
async def remove_item_from_order(
    order_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtmadan mahsulotni o'chirish"""
    order_service = OrderService(db)

    # BOSQICH 1.5: tenant bo'yicha cheklash вЂ” boshqa tenant buyurtmasi topilmaydi
    existing = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Buyurtma elementi topilmadi")

    success = order_service.remove_item(order_id, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Buyurtma elementi topilmadi")
    
    return MessageResponse(message="Mahsulot o'chirildi")

@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtmani bekor qilish"""
    order_service = OrderService(db)

    # BOSQICH 1.5: tenant bo'yicha cheklash вЂ” boshqa tenant buyurtmasi topilmaydi
    existing = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    order = order_service.cancel_order(order_id, reason)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    
    # Stolnni bo'shatish
    if order.table:
        order.table.status = "free"
        db.commit()
    
    # Oshxonaga xabar
    await manager.broadcast_to_kitchen({
        "type": "order_cancelled",
        "order_id": order_id,
        "order_number": order.order_number,
        "reason": reason
    }, tenant_id=resolve_tenant_id(db, current_user))

    # Audit: KIM buyurtmani bekor qildi + summa + sabab
    log_audit(current_user, "orders", "DELETE", order_id, tenant_id=order.tenant_id, detail={
        "order_number": order.order_number,
        "total": order.final_amount,
        "reason": reason,
    })
    return MessageResponse(message="Buyurtma bekor qilindi")

@router.get("/{order_id}/receipt")
async def get_order_receipt(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtma cheki вЂ” JSON formatda (BOSQICH 2.6)"""
    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    paid_payments = [p for p in order.payments if p.status == "paid"]
    total_paid = sum(p.amount for p in paid_payments)

    # Chek QR/fiskal blok — faqat tenant "qr_enabled" (soliq/kassa integratsiyasi)
    # YOQIQ bo'lsa chekda ko'rinadi. Default O'CHIQ (ko'p do'kon ulanmagan) → QR/fiskal yo'q.
    tid = order.tenant_id or resolve_tenant_id(db, current_user)
    rs = db.query(ReceiptSettings).filter(ReceiptSettings.tenant_id == tid).first()
    qr_on = bool(rs and rs.qr_enabled)

    # ── Sodiqlik (loyalty) bloki — FAQAT mijoz tanlangan + shu order'da ball harakati bo'lsa.
    # Manba: LoyaltyTransaction (reprint'да ham to'g'ri). Walk-in / ballsiz → None (chekda chiqmaydi).
    loyalty = None
    if order.customer_id:
        from models import LoyaltyTransaction, Customer
        ltx = db.query(LoyaltyTransaction).filter(
            LoyaltyTransaction.order_id == order.id,
            LoyaltyTransaction.type.in_(("earn", "redeem"))).all()
        earned   = sum(t.points for t in ltx if t.type == "earn")
        redeemed = sum(-t.points for t in ltx if t.type == "redeem")
        if earned or redeemed:
            from core.loyalty_config import get_loyalty_config
            _lc = get_loyalty_config(db, tid)
            cust = db.query(Customer).filter(Customer.id == order.customer_id).first()
            loyalty = {
                "earned":          earned,
                "redeemed":        redeemed,
                "redeemed_amount": round(redeemed * _lc["redeem_value"], 2),
                "balance":         (cust.points if cust else None),
            }

    return {
        "receipt_number": order.order_number,
        "date": order.created_at.strftime("%d.%m.%Y %H:%M"),
        "table": order.table.number if order.table else None,
        "waiter": order.waiter.full_name if order.waiter else None,
        "customer": order.customer.name if order.customer else None,
        "items": [
            {
                "name": item.product.name,
                "quantity": item.quantity,
                "sale_unit": item.product.sale_unit,
                "unit_price": item.unit_price,
                "total": item.total_price,
                "notes": item.notes,
                # BOSQICH B6 (pachka/dona): chek yorlig'i uchun
                "unit_sold": item.unit_sold,
                "base_qty": item.base_qty,
            }
            for item in order.items
        ],
        "subtotal": order.total_amount,
        "discount": order.discount_amount,
        "tax": order.tax_amount,
        "total": order.final_amount,
        "paid": total_paid,
        "change": round(max(0.0, total_paid - order.final_amount), 2),
        "payment_methods": [
            {"method": p.method, "amount": p.amount}
            for p in paid_payments
        ],
        "status":          order.status,
        "notes":           order.notes,
        # OFD fiskal — faqat qr_enabled (soliq integratsiyasi) YOQIQ bo'lsa chekda ko'rinadi
        "fiscal_number":   order.fiscal_number if qr_on else None,
        "fiscal_qr_url":   order.fiscal_qr_url if qr_on else None,
        "fiscal_sent_at":  order.fiscal_sent_at.isoformat() if order.fiscal_sent_at else None,
        "qr_enabled":      qr_on,
        # pos.js renderReceiptData uchun
        "order_id":        order.id,
        "order_number":    order.order_number,
        "cafe_name":       order.cafe.name if hasattr(order, 'cafe') and order.cafe else None,
        "subtotal":        order.total_amount,
        "discount_amount": order.discount_amount,
        "tax_amount":      order.tax_amount,
        "service_amount":  order.service_charge or 0,
        "final_amount":    order.final_amount,
        "loyalty":         loyalty,
    }


@router.post("/{order_id}/print")
async def print_order_receipt(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Chekni ESC/POS printerga chiqarish (BOSQICH 30 — universal printer).

    Printer o'chiq (`enabled=false`) bo'lsa → `{ok:false, reason:'disabled'}`
    qaytaradi va POS brauzer chop etishga (window.print) qaytadi.
    """
    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    cafe = order.cafe if hasattr(order, "cafe") and order.cafe else None
    paid = [p for p in order.payments if p.status == "paid"]
    method = paid[0].method if paid else None

    # ── Chek ma'lumoti tenant-scoped manbalardan ──
    # Do'kon nomi/manzil/telefon/footer — ReceiptSettings (tenant), bo'lmasa cafe.
    # Fiskal/QQS qism — tenant fiscal cfg enabled bo'lsagina (hozir do'konда o'chiq).
    tid = order.tenant_id or resolve_tenant_id(db, current_user)
    rs = db.query(ReceiptSettings).filter(ReceiptSettings.tenant_id == tid).first()
    fiscal_cfg = get_tenant_config(db, tid, "fiscal") or {}
    fiscal_on = bool(fiscal_cfg.get("enabled"))

    store_name = (rs.store_name if rs and rs.store_name else (cafe.name if cafe else None)) or "Do'kon"
    store_address = (rs.address if rs and rs.address else (getattr(cafe, "address", None) if cafe else None))

    data = {
        "store_name":    store_name,
        "store_address": store_address,
        "phone":         rs.phone if rs else None,
        "header_text":   rs.header_text if rs else None,
        "footer_text":   (rs.footer_text if rs and rs.footer_text else None),
        "qr_url":        (rs.qr_url if rs and rs.qr_enabled else None),
        "datetime":      datetime.now().strftime("%d.%m.%Y %H:%M"),
        "cashier":       current_user.full_name or current_user.username,
        "receipt_number": order.order_number,
        "items": [
            {
                # BOSQICH B6: pachka sotilsa nomga yorliq (termal chek) — 1 pachka = N dona
                "name": ((it.product.name if it.product else "")
                         + (f" (pachka, {int(it.base_qty / it.quantity)} dona)"
                            if it.unit_sold == "pachka" and it.base_qty and it.quantity else "")),
                "quantity": it.quantity,
                "unit_price": it.unit_price,
                "total": it.total_price,
            }
            for it in order.items
        ],
        "subtotal": order.total_amount,
        "discount": order.discount_amount or 0,
        "tax":      order.tax_amount or 0,
        "service":  order.service_charge or 0,
        "total":    order.final_amount,
        "payment_method": method,
        # ── Fiskal/QQS (faqat fiscal cfg enabled bo'lsa to'ladi) ──
        "fiscal_enabled": fiscal_on,
        "tax_id":        (rs.tax_id if rs and rs.tax_id else fiscal_cfg.get("inn")) if fiscal_on else None,
        "fiscal_number": order.fiscal_number if fiscal_on else None,
        "fiscal_qr_url": order.fiscal_qr_url if fiscal_on else None,
    }
    # BOSQICH 40: tenant printer config bilan chop etish
    _printer_cfg = get_tenant_config(db, tid, "printer")
    result = escpos_print_receipt(data, cfg=_printer_cfg)
    return result


@router.post("/{order_id}/split")
async def split_bill(
    order_id: int,
    ways: int = Query(2, ge=2, le=20, description="Nechta kishiga bo'linadi"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Hisobni bo'lish вЂ” split bill (BOSQICH 2.6)"""
    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    if order.status == "completed":
        raise HTTPException(status_code=400, detail="Yakunlangan buyurtmani bo'lib bo'lmaydi")

    per_person = round(order.final_amount / ways, 0)

    return {
        "order_id": order_id,
        "order_number": order.order_number,
        "total": order.final_amount,
        "ways": ways,
        "per_person": per_person,
        "parts": [{"part": i + 1, "amount": per_person} for i in range(ways)],
    }


@router.get("/table/{table_id}/active")
async def get_active_order_for_table(
    table_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Stolning faol buyurtmasini olish"""
    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.table_id == table_id,
        Order.status.in_(["pending", "confirmed", "preparing", "ready", "served"])
    ).first()
    
    if not order:
        return None
    
    return OrderInDB.model_validate(order)
