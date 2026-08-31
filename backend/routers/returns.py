"""
Qaytarish / Almashtirish router — BOSQICH 19

Endpointlar:
  POST /returns/              — yangi qaytarish yaratish
  GET  /returns/              — ro'yxat (filter bilan)
  GET  /returns/report        — hisobot (sabab, usul bo'yicha)
  GET  /returns/{id}          — bitta tafsilot
  POST /returns/{id}/approve  — tasdiqlash (pul + ombor)
  POST /returns/{id}/reject   — rad etish
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timezone
from typing import Optional, List

from database import get_db
from models import (
    Return, ReturnItem, Product, Order, OrderItem, Inventory, StockMovement,
    Payment, CustomerDebt, Customer,
)
from services.payment_service import PaymentService
from schemas import ReturnCreate, ReturnInDB, ReturnReport, MessageResponse
from deps import get_current_active_user, apply_tenant_filter, has_permission
from core.audit import log_audit  # xodim harakatlarini yozish (audit)

router = APIRouter()


def _next_return_number(db: Session, tenant_id: Optional[int]) -> str:
    today = date.today()
    prefix = f"RET{today.strftime('%y%m%d')}"
    count = (
        db.query(func.count(Return.id))
        .filter(Return.return_number.like(f"{prefix}%"))
        .scalar()
        or 0
    )
    return f"{prefix}{count + 1:03d}"


def _restore_inventory(db: Session, product_id: int, quantity: float, tenant_id, branch_id, user_id):
    """Omborga tovarni qaytarish — Inventory miqdorini oshirish + StockMovement yozish"""
    inv = (
        db.query(Inventory)
        .filter(
            Inventory.product_id == product_id,
            Inventory.tenant_id == tenant_id,
        )
        .with_for_update()   # ROW-LOCK: qaytarishda ombor oshirilishi atomik
        .first()
    )
    if inv:
        inv.quantity += quantity

    product = db.query(Product).filter(Product.id == product_id).first()
    unit_cost = product.cost_price if product else 0.0

    movement = StockMovement(
        tenant_id=tenant_id,
        branch_id=branch_id,
        product_id=product_id,
        inventory_id=inv.id if inv else None,
        movement_type="return",
        quantity=quantity,
        unit_cost=unit_cost,
        total_cost=quantity * unit_cost,
        reason="customer_return",
        reference_type="return",
        user_id=user_id,
    )
    db.add(movement)


def _return_base_qty(db: Session, order_item_id, quantity: float) -> float:
    """BOSQICH B-returns: omborga qaytariladigan DONA miqdori.

    order_item_id bo'lsa — asl sotuv nisbati bilan: pachka sotilgan bo'lsa
    OrderItem.base_qty/quantity = pack_size → base_qty = pack_size × quantity.
    Bog'lanmagan yoki eski sotuv (base_qty NULL) → quantity (dona).
    """
    if order_item_id:
        oi = db.query(OrderItem).filter(OrderItem.id == order_item_id).first()
        if oi and oi.base_qty is not None and oi.quantity:
            return (oi.base_qty / oi.quantity) * quantity
    return quantity


# ── POST /returns/ ───────────────────────────────────────────────────────────
@router.post("/", response_model=ReturnInDB)
def create_return(
    data: ReturnCreate,
    db: Session = Depends(get_db),
    # RBAC: qaytarish = to'lov amali → admin + kassir. Ofitsiant/oshpaz QILA OLMAYDI.
    current_user=Depends(has_permission("process_payments")),
):
    if not data.items:
        raise HTTPException(400, "Kamida bitta mahsulot ko'rsatilishi kerak")

    # Original buyurtmani tekshirish (ixtiyoriy)
    if data.order_id:
        order = (
            apply_tenant_filter(db.query(Order), Order, current_user)
            .filter(Order.id == data.order_id)
            .first()
        )
        if not order:
            raise HTTPException(404, "Buyurtma topilmadi")

    total_amount = sum(item.quantity * item.unit_price for item in data.items)

    ret = Return(
        tenant_id=current_user.tenant_id,
        branch_id=getattr(current_user, "_active_branch_id", None),
        return_number=_next_return_number(db, current_user.tenant_id),
        order_id=data.order_id,
        customer_id=data.customer_id,
        reason=data.reason,
        total_amount=total_amount,
        refund_method=data.refund_method,
        status="pending",
        notes=data.notes,
        user_id=current_user.id,
    )
    db.add(ret)
    db.flush()

    for item_data in data.items:
        product = db.query(Product).filter(Product.id == item_data.product_id).first()
        if not product:
            raise HTTPException(404, f"Mahsulot {item_data.product_id} topilmadi")

        ri = ReturnItem(
            return_id=ret.id,
            product_id=item_data.product_id,
            order_item_id=item_data.order_item_id,
            quantity=item_data.quantity,
            # BOSQICH B-returns: pachka qaytarilsa dona miqdori (pack_size×qty)
            base_qty=_return_base_qty(db, item_data.order_item_id, item_data.quantity),
            unit_price=item_data.unit_price,
            total=item_data.quantity * item_data.unit_price,
            restore_to_inventory=item_data.restore_to_inventory,
        )
        db.add(ri)

    db.commit()
    db.refresh(ret)

    # Audit: KIM qaytarish qildi — summa, sabab, mahsulot soni
    log_audit(current_user, "returns", "RETURN", ret.id, tenant_id=ret.tenant_id, detail={
        "return_number": ret.return_number,
        "total_amount": total_amount,
        "reason": data.reason,
        "refund_method": data.refund_method,
        "order_id": data.order_id,
        "items_count": len(data.items),
    })
    return ret


# ── GET /returns/ ────────────────────────────────────────────────────────────
@router.get("/", response_model=List[ReturnInDB])
def list_returns(
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(Return), Return, current_user)

    if status:
        q = q.filter(Return.status == status)
    if customer_id:
        q = q.filter(Return.customer_id == customer_id)
    if date_from:
        q = q.filter(Return.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(Return.created_at <= datetime.combine(date_to, datetime.max.time()))

    q = q.order_by(Return.created_at.desc())
    return q.offset((page - 1) * page_size).limit(page_size).all()


# ── GET /returns/report ──────────────────────────────────────────────────────
@router.get("/report", response_model=ReturnReport)
def returns_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user=Depends(has_permission("view_reports")),
):
    q = apply_tenant_filter(db.query(Return), Return, current_user).filter(
        Return.status == "approved"
    )
    if date_from:
        q = q.filter(Return.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(Return.created_at <= datetime.combine(date_to, datetime.max.time()))

    returns = q.all()
    total_amount = sum(r.total_amount for r in returns)

    by_reason: dict = {}
    by_refund: dict = {}
    for r in returns:
        by_reason[r.reason] = by_reason.get(r.reason, 0) + 1
        by_refund[r.refund_method] = by_refund.get(r.refund_method, 0.0) + r.total_amount

    return ReturnReport(
        total_returns=len(returns),
        total_amount=total_amount,
        by_reason=by_reason,
        by_refund_method=by_refund,
    )


# ── GET /returns/{id} ────────────────────────────────────────────────────────
@router.get("/{return_id}", response_model=ReturnInDB)
def get_return(
    return_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    ret = (
        apply_tenant_filter(db.query(Return), Return, current_user)
        .filter(Return.id == return_id)
        .first()
    )
    if not ret:
        raise HTTPException(404, "Qaytarish topilmadi")
    return ret


# ── POST /returns/{id}/approve ───────────────────────────────────────────────
def _refund_money(db: Session, ret: Return, current_user) -> dict:
    """Vozvrat TASDIQLANGANDA pulni qaytarish. Ilgari bu UMUMAN yo'q edi —
    `refund_method` shunchaki YORLIQ bo'lib qolardi: naqd/karta qaytarishning
    izi yo'q, nasiyaga olgan mijozning QARZI ham kamaymasdi.

    Uch xil usul (`exchange` BOSQICH D da butunlay olib tashlandi: UI'da ham yo'q,
    `ReturnCreate` ham uni rad etadi — aks holda pul harakatisiz "tasdiqlangan"
    vozvrat qolardi; almashtirish alohida kelajakdagi ish):
      cash/card -> mavjud `payment_service.refund_payment()` QAYTA ISHLATILADI
                   (manfiy Payment + status="refunded"). Yangi mexanizm o'ylab
                   topilmaydi — aks holda ikki xil formula paydo bo'lardi.
      credit    -> mijoz QARZI kamayadi: avval SHU buyurtmaning qarzi
                   (CustomerDebt.order_id), keyin eng eski ochiq qarzlar (FIFO).
                   Qarzdan oshgani AVANS bo'lib qoladi (naqd qaytarilmaydi) —
                   firma qarzidagi avans naqshiga izchil.
    """
    out = {"refund_payments": [], "debt_reduced": 0.0, "advance": 0.0}
    amount = float(ret.total_amount or 0)
    if amount <= 0:
        return out

    method = (ret.refund_method or "cash").lower()

    # ── NAQD / KARTA ────────────────────────────────────────────────────────
    if method in ("cash", "card"):
        if not ret.order_id:
            return out          # buyurtmasiz vozvrat — qaytariladigan to'lov yo'q
        svc = PaymentService(db)
        qoldiq = amount
        paids = (
            db.query(Payment)
            .filter(Payment.order_id == ret.order_id, Payment.status == "paid")
            .order_by(Payment.id)
            .all()
        )
        for pay in paids:
            if qoldiq <= 0.009:
                break
            ulush = min(qoldiq, float(pay.amount or 0))
            svc.refund_payment(pay, ulush, f"Vozvrat {ret.return_number}", commit=False)
            out["refund_payments"].append({"payment_id": pay.id, "amount": ulush})
            qoldiq -= ulush
        return out

    # ── NASIYA (balansga) ───────────────────────────────────────────────────
    if method == "credit":
        if not ret.customer_id:
            return out
        qoldiq = amount

        # 1) shu buyurtmaning qarzi — aniq bog'lanish, taxmin qilmaymiz
        q = db.query(CustomerDebt).filter(
            CustomerDebt.customer_id == ret.customer_id,
            CustomerDebt.status.in_(["open", "partial"]),
        )
        debts = []
        if ret.order_id:
            debts = q.filter(CustomerDebt.order_id == ret.order_id).all()
        # 2) qolgani — eng eski ochiq qarzlardan (FIFO)
        debts += [d for d in q.order_by(CustomerDebt.created_at, CustomerDebt.id).all()
                  if d not in debts]

        for d in debts:
            if qoldiq <= 0.009:
                break
            ulush = min(qoldiq, float(d.remaining or 0))
            if ulush <= 0:
                continue
            d.remaining = round(float(d.remaining) - ulush, 2)
            d.paid_amount = round(float(d.paid_amount or 0) + ulush, 2)
            if d.remaining < 0.01:
                d.remaining = 0.0
                d.status = "paid"
            elif d.paid_amount > 0:
                d.status = "partial"
            qoldiq -= ulush
            out["debt_reduced"] = round(out["debt_reduced"] + ulush, 2)

        # 3) qarzdan OSHGANI — avans (manfiy qoldiqli yozuv). Naqd qaytarilmaydi.
        if qoldiq > 0.009:
            db.add(CustomerDebt(
                tenant_id=ret.tenant_id,
                branch_id=ret.branch_id,
                customer_id=ret.customer_id,
                order_id=ret.order_id,
                amount=-qoldiq,
                paid_amount=0.0,
                remaining=-qoldiq,      # manfiy qoldiq = AVANS (total_debt kamayadi)
                status="open",
                notes=f"Vozvrat avansi ({ret.return_number}) — qarzdan oshgan summa",
                user_id=current_user.id,
            ))
            out["advance"] = round(qoldiq, 2)

        db.flush()
        _recalc_customer_debt(db, ret.customer_id)
    return out


def _recalc_customer_debt(db: Session, customer_id: int) -> None:
    """`customers.total_debt` ni ochiq qarzlardan qayta hisoblaydi.
    (routers/debt.py dagi bilan bir xil qoida — manfiy qoldiq avansni bildiradi.)"""
    total = (
        db.query(func.coalesce(func.sum(CustomerDebt.remaining), 0.0))
        .filter(
            CustomerDebt.customer_id == customer_id,
            CustomerDebt.status.in_(["open", "partial"]),
        )
        .scalar()
    )
    db.query(Customer).filter(Customer.id == customer_id).update({"total_debt": total})


@router.post("/{return_id}/approve", response_model=ReturnInDB)
def approve_return(
    return_id: int,
    db: Session = Depends(get_db),
    # RBAC: tasdiqlash ham admin + kassir (ofitsiant/oshpaz emas)
    current_user=Depends(has_permission("process_payments")),
):
    ret = (
        apply_tenant_filter(db.query(Return), Return, current_user)
        .filter(Return.id == return_id)
        .first()
    )
    if not ret:
        raise HTTPException(404, "Qaytarish topilmadi")
    if ret.status != "pending":
        raise HTTPException(400, f"Bu qaytarish allaqachon '{ret.status}' holatida")

    # ── IKKI PARALLEL YO'L QO'RIQCHISI ──────────────────────────────────────
    # Tizimda vozvratning ikki yo'li bor: (1) shu Return hujjati,
    # (2) `POST /payments/{id}/refund`. Ikkalasi bir-biridan BEXABAR edi va
    # ikkalasi ham OMBORNI TIKLAYDI -> bir vozvrat ikki marta o'tkazilsa
    # qoldiq ikki marta oshib ketardi (pul ham ikki marta qaytardi).
    # Qoida: QAYTARISH HUJJATI — yagona manba. To'lov allaqachon qaytarilgan
    # bo'lsa, bu hujjatni tasdiqlash BLOKLANADI (tushunarli sabab bilan).
    if ret.order_id:
        _pays = db.query(Payment).filter(Payment.order_id == ret.order_id).all()
        if _pays and all(p.status == "refunded" for p in _pays):
            raise HTTPException(
                409,
                "Bu buyurtma allaqachon TO'LIQ qaytarilgan (to'lovni qaytarish orqali). "
                "Ombor va pul o'sha yo'lda tiklangan — bu hujjatni tasdiqlash ikki "
                "marta hisoblanishiga olib keladi.",
            )

    # Omborga qaytarish (faqat restore_to_inventory=True bo'lganlar)
    for item in ret.items:
        if item.restore_to_inventory:
            _restore_inventory(
                db,
                item.product_id,
                # BOSQICH B-returns: base_qty (dona) bilan tiklash; NULL → quantity (fallback)
                item.base_qty if item.base_qty is not None else item.quantity,
                ret.tenant_id,
                ret.branch_id,
                current_user.id,
            )

    # ── PUL HARAKATI (ilgari UMUMAN yo'q edi) ───────────────────────────────
    money = _refund_money(db, ret, current_user)

    ret.status = "approved"
    ret.approved_by = current_user.id
    # AWARE UTC (`utcnow()` NAIVE qaytaradi). Ustun `timestamptz` bo'lgani uchun
    # naive qiymatni PostgreSQL SESSIYA ZONASIDA talqin qiladi — hozir u UTC,
    # shuning uchun natija TO'G'RI edi. Ammo bu sozlamaga bog'liqlik: sessiya
    # zonasi o'zgarsa vozvrat sanasi jimgina 5 soatga siljigan bo'lardi.
    # Aware qiymat bu bog'liqlikni butunlay olib tashlaydi.
    # ⚠️ XATTI-HARAKAT O'ZGARMAYDI — bu mustahkamlash, xato tuzatish emas
    #    (tekshirildi: hisobot chegarasi ham tz-aware, solishtirish to'g'ri).
    ret.approved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(ret)

    log_audit(current_user, "returns", "UPDATE", ret.id, tenant_id=ret.tenant_id, detail={
        "action": "approve",
        "return_number": ret.return_number,
        "total_amount": float(ret.total_amount or 0),
        "refund_method": ret.refund_method,
        "refund_payments": money["refund_payments"],
        "debt_reduced": money["debt_reduced"],
        "advance": money["advance"],
    })
    return ret


# ── POST /returns/{id}/reject ────────────────────────────────────────────────
@router.post("/{return_id}/reject", response_model=ReturnInDB)
def reject_return(
    return_id: int,
    db: Session = Depends(get_db),
    # RBAC: rad etish ham admin + kassir (ofitsiant/oshpaz emas)
    current_user=Depends(has_permission("process_payments")),
):
    ret = (
        apply_tenant_filter(db.query(Return), Return, current_user)
        .filter(Return.id == return_id)
        .first()
    )
    if not ret:
        raise HTTPException(404, "Qaytarish topilmadi")
    if ret.status != "pending":
        raise HTTPException(400, f"Bu qaytarish allaqachon '{ret.status}' holatida")

    ret.status = "rejected"
    ret.approved_by = current_user.id
    ret.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(ret)
    return ret
