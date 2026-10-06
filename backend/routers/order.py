from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
# ⚠️ CHEK VAQTI: `created_at` aware UTC — `strftime` zonani TASHLAB YUBORADI va
# UTC devor vaqtini chop etadi (chekda 5 soat orqada). `to_local()` bilan tenant
# zonasiga o'giriladi. Bir xil naqsh: routers/shift.py:_fmt_local.
from core.timeutils import to_local, utc_now

from database import get_db
from models import (
    Order, OrderItem, Product, Table, User, Cafe, ReceiptSettings,
    Payment, Customer, CustomerDebt, DebtPayment, Return, Shift,
)
from schemas import (
    OrderCreate, OrderUpdate, OrderInDB, PaginatedResponse, MessageResponse,
    ConvertPaymentRequest,
)
from deps import (
    resolve_tenant_id, get_current_user, get_current_active_user,
    apply_tenant_filter, has_permission,
)
from services.stock_guard import InsufficientStock
from services.order_service import OrderService
from services.kitchen_service import KitchenService
from services.printer_service import PrinterService, print_receipt as escpos_print_receipt
from services.unit_converter import pack_size_label   # chek pachka yorlig'i (sale_unit bo'yicha)
from websocket.manager import manager
from core.subscription import is_within_order_limit, get_plan_limits
from core.tenant_config import get_tenant_config  # BOSQICH 40 (3b): printer tenant-scoped
from core.feature_flags import Feature, is_feature_enabled  # kitchen_display gate
from core.audit import log_audit  # xodim harakatlarini yozish (audit)

router = APIRouter()


def _fmt_local(dt):
    """Chek uchun vaqt — TENANT zonasida (Toshkent), "dd.mm.yyyy HH:MM"."""
    return to_local(dt).strftime("%d.%m.%Y %H:%M") if dt else None


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
    try:
        order = order_service.create_order(
            order_data=order_data,
            waiter_id=current_user.id,
            tenant_id=tenant_id,
        )
    except InsufficientStock as e:
        # OMBOR QO'RIQCHISI (services/stock_guard.py). Buyurtma DB ga
        # YOZILMAGAN — tekshiruv Order yaratilishidan OLDIN o'tadi.
        # `shortages` — kassir savatni tuzatishi uchun qator-qator ma'lumot.
        raise HTTPException(
            status_code=400,
            detail=e.message,
            headers={"X-Stock-Shortage": str(len(e.shortages))},
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
    quantity: float = Query(1, gt=0),   # kasrli bo'lishi mumkin (tarozi: 0.740)
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

    try:
        order = order_service.cancel_order(order_id, reason)
    except ValueError as e:
        # Ombordan ayrilgan (to'langan) buyurtma — bekor qilish rad etiladi,
        # qaytarish (refund) yo'lidan o'tilsin. Qarang: OrderService.cancel_order.
        raise HTTPException(status_code=400, detail=str(e))
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


# ══════════════════════════════════════════════════════════════════════════════
# TO'LOV USULINI KEYIN TUZATISH  —  POST /orders/{id}/convert-payment
# ══════════════════════════════════════════════════════════════════════════════
# MUAMMO (jonli): kassir nasiyani naqd qilib yopadi yoki karta o'rniga naqd
# uradi. Chek chiqib ketgan, tovar ketgan — lekin kassa hisobi va qarz daftari
# yolg'on. Shu paytgacha tuzatish yo'li FAQAT qo'lda SQL edi (v1.12.14).
#
# NIMAGA TEGMAYDI:
#   • OMBOR — tovar allaqachon ketgan, miqdor o'zgarmaydi. Faqat TENDER
#     (pul qaysi yo'l bilan keldi/kelmadi) tuzatiladi.
#   • SOTUV SUMMASI — `order.final_amount` va `payment.amount` o'zgarmaydi.
#   • YOPILGAN SMENA — Z-hisoboti bosilib, kassa topshirilgan. Ichidagi
#     tenderni keyin o'zgartirish bosilgan hisobotni yolg'onga chiqaradi.
#
# Z-HISOBOTGA TA'SIRI (kutilgan va KERAKLI):
#   `routers/shift.py` da `cash_sales` faqat `method=="cash" and status=="paid"`
#   dan yig'iladi, `expected_cash` esa undan hisoblanadi. Ya'ni
#   naqd→nasiya → `cash_sales` tushadi → `expected_cash` KAMAYADI (kassada
#   o'sha pul yo'q, chunki haqiqatda qarzga berilgan). Teskarisi — oshadi.
@router.post("/{order_id}/convert-payment")
async def convert_order_payment(
    order_id: int,
    data: ConvertPaymentRequest,
    db: Session = Depends(get_db),
    # Kassir O'ZI xatosini tuzatmaydi — aks holda nazorat yo'qoladi
    # (vozvrat "ikkinchi ko'zi" bilan bir xil qoida, routers/returns.py).
    current_user: User = Depends(has_permission("manage_shifts")),
):
    """To'lov usulini tuzatadi: naqd ↔ karta ↔ nasiya. Omborga tegmaydi."""
    # Aylanma import bo'lmasin: `routers/debt.py` qarz hisobining yagona egasi.
    from routers.debt import _recalc_customer_debt

    # ROW-LOCK: ikki admin bir vaqtda bossa, ikkisi ham "usul naqd" deb o'qib
    # IKKI qarz qatori yaratib qo'yardi. Qulf chek qatorida — qolgan hamma
    # tekshiruv va yozuv shu qulf ostida ketadi (atomic-sale naqshi).
    # SQLite'da (testlar) SQLAlchemy FOR UPDATE ni jimgina tashlab ketadi.
    order = (
        apply_tenant_filter(db.query(Order), Order, current_user)
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    # ── 1) Faqat YAKUNLANGAN sotuv ──────────────────────────────────────────
    _ost = str(getattr(order.status, "value", order.status))
    if _ost != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Faqat yakunlangan sotuv to'lovini tuzatish mumkin "
                   f"(joriy holat: {_ost}).",
        )

    # ── 2) Qaytarish hujjati bo'lsa — TEGMAYMIZ ─────────────────────────────
    # Pul va ombor o'sha hujjat orqali yuriydi (routers/payment.py naqshi).
    # Tenderni ostidan o'zgartirish vozvrat summasini boshqa yo'lga burardi.
    _ret = (
        db.query(Return)
        .filter(Return.order_id == order.id,
                Return.status.in_(["pending", "approved"]))
        .first()
    )
    if _ret:
        raise HTTPException(
            status_code=400,
            detail=f"Bu chekda qaytarish hujjati bor ({_ret.return_number}, "
                   f"holat: {_ret.status}). To'lov usulini o'zgartirish mumkin emas — "
                   f"avval qaytarish masalasi hal qilinsin.",
        )

    # ── 3) To'lov yozuvi AYNAN BITTA bo'lsin ────────────────────────────────
    # ⚠️ `apply_tenant_filter` ATAYIN ISHLATILMAYDI: `Payment.tenant_id`
    # nullable va eski yozuvlarda NULL bo'lishi mumkin. Filtr NULL qatorni
    # YASHIRARDI va aralash to'lovli chek "bitta tender" bo'lib ko'rinardi.
    # Tenant himoyasi yuqorida — `order` allaqachon tenant bo'yicha olingan.
    payments = db.query(Payment).filter(Payment.order_id == order.id).all()

    _refunded = [p for p in payments
                 if str(getattr(p.status, "value", p.status)) == "refunded"]
    if _refunded:
        raise HTTPException(
            status_code=400,
            detail="Bu chek bo'yicha pul qaytarilgan — to'lov usulini "
                   "o'zgartirish mumkin emas.",
        )

    live = [p for p in payments
            if str(getattr(p.status, "value", p.status)) in ("paid", "pending")]
    if not live:
        raise HTTPException(
            status_code=400,
            detail="Bu chekda to'lov yozuvi yo'q — tuzatish uchun hech narsa yo'q.",
        )
    if len(live) > 1:
        _lbl = ", ".join(sorted({str(getattr(p.method, "value", p.method)) for p in live}))
        raise HTTPException(
            status_code=400,
            detail=f"Aralash to'lov (split) qo'llab-quvvatlanmaydi: bu chekda "
                   f"{len(live)} ta tender bor ({_lbl}). Har bir qismni alohida "
                   f"tuzatish hozircha mumkin emas — qo'lda tuzatish uchun "
                   f"administratorga murojaat qiling.",
        )

    payment = live[0]
    old_method = str(getattr(payment.method, "value", payment.method))
    new_method = data.new_method

    # ── 4) O'zgarish bormi ──────────────────────────────────────────────────
    if old_method == new_method:
        raise HTTPException(
            status_code=400,
            detail=f"To'lov usuli allaqachon «{new_method}» — o'zgartirishga hojat yo'q.",
        )
    # Mehmonxona xona hisobi — folio bilan bog'langan, bu yerdan uzilmaydi.
    if old_method == "room_charge":
        raise HTTPException(
            status_code=400,
            detail="Xona hisobiga yozilgan to'lovni bu yerdan o'zgartirish mumkin emas "
                   "(mehmonxona folio hisobi bilan bog'liq).",
        )

    # ── 5) Buyurtmaning O'Z smenasi OCHIQ bo'lsin ───────────────────────────
    # ⚠️ "biror smena ochiq" emas — AYNAN shu chek yozilgan smena. Yopilgan
    # smenaning Z-hisoboti bosilgan, kassa topshirilgan: ichidagi tenderni
    # keyin o'zgartirish o'sha qog'ozni yolg'onga chiqaradi.
    if not order.shift_id:
        raise HTTPException(
            status_code=400,
            detail="Bu chek smenaga bog'lanmagan (eski yozuv) — to'lov usulini "
                   "o'zgartirish mumkin emas, chunki qaysi kassa hisobiga "
                   "tegishi aniqlanmaydi.",
        )
    shift = (
        apply_tenant_filter(db.query(Shift), Shift, current_user)
        .filter(Shift.id == order.shift_id)
        .first()
    )
    if not shift:
        raise HTTPException(status_code=400, detail="Chekning smenasi topilmadi.")
    if shift.end_time is not None:
        raise HTTPException(
            status_code=400,
            detail="Bu chek YOPILGAN smenaga tegishli. Yopilgan smena hisobiga "
                   "tegilmaydi — tuzatishni buxgalteriya orqali qiling.",
        )

    amount = float(payment.amount or 0)

    # Shu chekka bog'langan qarz (bo'lsa). Tenant himoyasi — `order` orqali.
    debt = (
        db.query(CustomerDebt)
        .filter(CustomerDebt.order_id == order.id)
        .order_by(CustomerDebt.id.desc())
        .first()
    )

    # ── 6) NASIYADAN CHIQISH: qarz yopiladi/o'chiriladi ─────────────────────
    _closed_debt_id = None
    if old_method == "credit" and debt:
        _paid_cnt = db.query(DebtPayment).filter(DebtPayment.debt_id == debt.id).count()
        # Yig'ilgan pulni JIMGINA yo'qotmaymiz: qarzga to'lov tushgan bo'lsa
        # uni avval bekor qilish kerak, aks holda `debt_payments` kassaga
        # pulni ikki marta qo'shib yuborardi (utils/cashflow.py).
        if _paid_cnt or float(debt.paid_amount or 0) > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Bu nasiya bo'yicha to'lov qabul qilingan "
                       f"({float(debt.paid_amount or 0):,.0f} so'm, {_paid_cnt} ta to'lov). "
                       f"Avval o'sha to'lov(lar)ni hal qiling — aks holda pul "
                       f"ikki marta hisoblanadi.",
            )
        _closed_debt_id = debt.id
        _debt_customer = debt.customer_id
        db.delete(debt)
        db.flush()
        _recalc_customer_debt(db, _debt_customer)
        debt = None

    # ── 7) NASIYAGA O'TISH: qarz bog'lanadi yoki yaratiladi ─────────────────
    _new_debt_id = None
    if new_method == "credit":
        if not data.customer_id:
            raise HTTPException(
                status_code=400,
                detail="Nasiyaga o'tkazish uchun MIJOZ tanlanishi shart — "
                       "qarz kimga yozilishi kerak?",
            )
        customer = (
            apply_tenant_filter(db.query(Customer), Customer, current_user)
            .filter(Customer.id == data.customer_id)
            .first()
        )
        if not customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")

        # Mavjud qarz qatori (shu chek bo'yicha) — to'lov tushgan bo'lsa tegmaymiz.
        if debt and (float(debt.paid_amount or 0) > 0 or debt.status == "paid"):
            raise HTTPException(
                status_code=400,
                detail="Bu chekda to'langan qarz qatori bor — avtomatik "
                       "qayta bog'lash mumkin emas.",
            )

        # QARZ LIMITI — `routers/debt.py:create_debt` bilan AYNI tekshiruv.
        # Busiz konvertatsiya limitni chetlab o'tadigan yo'l bo'lib qolardi.
        if customer.credit_limit is not None:
            _already = float(debt.remaining or 0) if (debt and debt.customer_id == customer.id) else 0.0
            new_total = float(customer.total_debt or 0) - _already + amount
            if new_total > customer.credit_limit:
                raise HTTPException(
                    status_code=400,
                    detail=f"Qarz limiti ({customer.credit_limit:,.0f}) oshib ketdi. "
                           f"Joriy qarz: {float(customer.total_debt or 0):,.0f}",
                )

        if debt:
            debt.customer_id = customer.id
            debt.amount      = amount
            debt.paid_amount = 0.0
            debt.remaining   = amount
            debt.status      = "open"
        else:
            debt = CustomerDebt(
                tenant_id=order.tenant_id,
                branch_id=order.branch_id,
                customer_id=customer.id,
                order_id=order.id,
                amount=amount,
                paid_amount=0.0,
                remaining=amount,
                status="open",
                notes=f"To'lov usuli tuzatildi ({old_method} → nasiya): {data.reason}",
                user_id=current_user.id,
            )
            db.add(debt)
        db.flush()
        _new_debt_id = debt.id

        # Vozvrat pulni MIJOZ bo'yicha topadi (returns-validation) — chek
        # mijozsiz qolsa nasiya qaytarilganda qarz topilmasdi.
        order.customer_id = customer.id
        _recalc_customer_debt(db, customer.id)

    # ── 8) TENDERNI YOZISH ──────────────────────────────────────────────────
    # Nasiya — pul KELMAGAN: `pending` (services/payment_service.py bilan bir
    # xil qoida). Naqd/karta — pul keldi: `paid`.
    payment.method = new_method
    payment.status = "pending" if new_method == "credit" else "paid"

    # BITTA commit — tender + qarz bir vaqtda o'zgaradi yoki ikkisi ham yo'q.
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    # ── 9) AUDIT ────────────────────────────────────────────────────────────
    log_audit(
        current_user, "orders", "UPDATE", order.id,
        tenant_id=order.tenant_id,
        detail={
            "action":        "convert_payment",
            "order_number":  order.order_number,
            "daily_number":  order.daily_number,
            "old_method":    old_method,
            "new_method":    new_method,
            "amount":        amount,
            "reason":        data.reason,
            "shift_id":      order.shift_id,
            "customer_id":   data.customer_id,
            "debt_created":  _new_debt_id,
            "debt_closed":   _closed_debt_id,
        },
    )

    return {
        "order_id":     order.id,
        "old_method":   old_method,
        "new_method":   new_method,
        "amount":       amount,
        "debt_id":      _new_debt_id,
        "debt_closed":  _closed_debt_id,
        "message":      f"To'lov usuli o'zgartirildi: {old_method} → {new_method}",
    }


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
        "date": _fmt_local(order.created_at),
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
        "datetime":      _fmt_local(utc_now()),
        "cashier":       current_user.full_name or current_user.username,
        "receipt_number": order.order_number,
        "items": [
            {
                # BOSQICH B6: pachka sotilsa nomga yorliq (termal chek).
                #
                # Yorliq `sale_unit` ga qarab: kg → "(qop, 20 kg)",
                # ml → "(butun, 150 ml)", qolgani → "(pachka, 10 dona)"
                # (avvalgidek). Ilgari bu yerda "dona" QOTIB yozilgan va
                # `int()` kasrni kesib tashlagan edi — 20 kg qop chekda
                # "(pachka, 20 dona)" bo'lib chiqardi.
                #
                # Matn frontend bilan BIR XIL manbada emas (backend JS faylini
                # o'qiy olmaydi) — qoida `services/unit_converter.py` da,
                # ikkisining mos kelishi `tests/test_pack_label.py` da
                # qulflangan.
                "name": ((it.product.name if it.product else "")
                         + (f" ({pack_size_label(getattr(it.product, 'sale_unit', None), it.base_qty / it.quantity)})"
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
