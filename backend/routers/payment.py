from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime
import logging

from database import get_db
from models import Payment, Order, User, Table, Cafe, Shift, PaymentMethod, PaymentStatus
from schemas import PaymentCreate, PaymentInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, has_permission, apply_tenant_filter
from core.feature_flags import Feature, is_feature_enabled
from services.payment_service import PaymentService
from services.ofd_service import send_to_ofd
from websocket.manager import manager
from core.config_loader import config_loader
from core.tenant_config import get_tenant_config

log = logging.getLogger(__name__)

router = APIRouter()


def _require_open_shift(db: Session, current_user: User) -> None:
    """Smena majburiy — ochiq smena bo'lmasa savdoni bloklaydi (409).

    Faqat "kassa bor" bizneslarda (cash_register YOKI z_report feature yoqilgan):
    food + retail + dorixona. Bron bizneslari (salon/fitnes/...) da smena talab
    qilinmaydi. Super-admin bypass. Smena foydalanuvchi (kassir) bo'yicha.
    """
    if current_user.is_superuser or not current_user.tenant_id:
        return
    cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
    if not cafe:
        return
    needs_shift = (
        is_feature_enabled(cafe.business_type, Feature.CASH_REGISTER,
                           cafe.enabled_features, cafe.disabled_features, cafe.subscription_plan)
        or is_feature_enabled(cafe.business_type, Feature.Z_REPORT,
                              cafe.enabled_features, cafe.disabled_features, cafe.subscription_plan)
    )
    if not needs_shift:
        return
    active = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.end_time.is_(None),
    ).first()
    if not active:
        raise HTTPException(
            status_code=409,
            detail="Avval smena oching — savdo uchun ochiq smena kerak",
        )


@router.get("/", response_model=PaginatedResponse)
async def get_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    order_id: Optional[int] = None,
    method: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """Barcha to'lovlarni olish"""
    query = db.query(Payment)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Payment, current_user)

    if order_id:
        query = query.filter(Payment.order_id == order_id)
    
    if method:
        query = query.filter(Payment.method == method)
    
    if status:
        query = query.filter(Payment.status == status)
    
    if date_from:
        query = query.filter(Payment.created_at >= date_from)
    
    if date_to:
        query = query.filter(Payment.created_at <= date_to)
    
    total = query.count()
    payments = query.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[PaymentInDB.model_validate(p) for p in payments],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.post("/", response_model=PaymentInDB)
async def create_payment(
    payment_data: PaymentCreate,
    offline_sync: bool = Query(False, description="Offline navbatdan replay — smena gate'ini o'tkazib yubor"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("process_payments"))
):
    """Yangi to'lov yaratish"""
    payment_service = PaymentService(db)

    # SMENA MAJBURIY: ochiq smena bo'lmasa savdo bloklanadi (kassa bor biznes).
    # offline_sync=True — offline navbat replay (sotuv allaqachon bo'lgan) → bypass,
    # aks holda tarmoq tiklanganda navbatdagi to'lovlar yo'qolardi (sync catch{}).
    if not offline_sync:
        _require_open_shift(db, current_user)

    # Buyurtmani tekshirish (BOSQICH 1.5: tenant bo'yicha cheklash)
    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == payment_data.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    tenant_id = resolve_tenant_id(db, current_user)
    order_completed = False
    _loyalty = {"earned": 0, "redeemed": 0}

    # ── SODIQLIK (loyalty) — redeem OLDINDAN, SERVER tomonда tekshiriladi ──
    # (client yuborgan redeem_points'ga ishonmaymiz). Yaroqsiz bo'lsa 400 (rollback'siz —
    # hali hech narsa yozilmagan). redeem = to'lov tenderi (final_amount o'zgarmaydi).
    from core.loyalty_config import (
        get_loyalty_config, validate_redeem, apply_redeem, apply_earn,
    )
    _loy_cfg = get_loyalty_config(db, tenant_id)
    _redeem_points = int(getattr(payment_data, "redeem_points", 0) or 0)
    _redeem_amount = validate_redeem(db, order, _loy_cfg, _redeem_points) if _redeem_points > 0 else 0.0

    # ── ATOMIK SOTUV ─────────────────────────────────────────────────────────
    # To'lov + order.status + ombor chiqimi + StockMovement + ingredients_deducted —
    # HAMMASI BITTA TRANZAKSIYA, BITTA commit. Xato bo'lsa BUTUN sotuv rollback
    # (to'lov ham yozilmaydi) → yarim holat / ombor drifti bo'lmaydi.
    try:
        payment = payment_service.process_payment(
            order=order,
            amount=payment_data.amount,
            method=payment_data.method,
            cashier_id=current_user.id,
            reference=payment_data.reference,
            commit=False,                       # commit — pastda, bir marta
        )
        # BOSQICH 1.5: to'lov yaratuvchi tenant'iga biriktiriladi
        payment.tenant_id = tenant_id
        db.flush()                              # payment INSERT → total_paid so'rovi ko'radi

        # To'liq to'langanmi? (flush qilingan joriy to'lovni ham hisoblaydi — order.payments
        # relationship keshiga bog'liq emas, DB'dan aniq sum).
        total_paid = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
            Payment.order_id == order.id, Payment.status == "paid"
        ).scalar() or 0.0

        # NASIYA TENDERI: pul kelmagan, lekin TOVAR SOTILDI. Buyurtma yakunlanishi
        # SHART — aks holda ombordan chiqim bo'lmaydi, stol bo'shamaydi va sotuv
        # hisobotlarga (Order.status == "completed") umuman tushmaydi.
        # Nasiya to'lovi PENDING bo'lgani uchun yuqoridagi `total_paid` uni
        # ko'rmaydi — shu sabab alohida qo'shamiz.
        credit_tender = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
            Payment.order_id == order.id,
            Payment.method == PaymentMethod.CREDIT,
            Payment.status == PaymentStatus.PENDING,
        ).scalar() or 0.0

        # Redeem = to'lov tenderi: naqd + ball + nasiya qoplagan summa >= final bo'lsa yakunlanadi.
        if total_paid + _redeem_amount + credit_tender >= order.final_amount:
            order_completed = True
            # TOCTOU: Order qatorini QULFLAB, ingredients_deducted ni DB'dan YANGI o'qiymiz.
            # Ikki qurilma bir vaqtda split-payment yakunlasa — biri qulfda kutadi, ombor
            # FAQAT BIR MARTA ayiriladi (flag qulf ostida tekshiriladi).
            db.refresh(order, with_for_update=True)
            if order.status != "completed":
                order.status = "completed"
                order.completed_at = datetime.now()
                if order.table:
                    order.table.status = "free"
                # ── SODIQLIK: redeem (tender) + earn (netdan) — YAKUNДА BIR MARTA ──
                # `status != completed` gate → split-payment'да faqat yakunlovchi to'lovда
                # bir marta ishlaydi (idempotent). Mijozsiz (walk-in) → ball yo'q.
                if order.customer_id and _loy_cfg["enabled"]:
                    if _redeem_points > 0 and _redeem_amount > 0:
                        apply_redeem(db, order, _redeem_points, _redeem_amount, tenant_id)
                        _loyalty["redeemed"] = _redeem_points
                    _loyalty["earned"] = apply_earn(db, order, _loy_cfg, tenant_id)
            # Ombor chiqimi (sotuv = chiqim). Retseptli → ingredientlar; retseptsiz → o'zi.
            # kitchen-ready'da allaqachon chiqargan bo'lsa (ingredients_deducted) — qayta ayirmaydi.
            if not order.ingredients_deducted:
                from services.recipe_inventory_service import deduct_order_ingredients
                deduct_order_ingredients(
                    db, order.id, tenant_id=tenant_id, user_id=current_user.id, commit=False,
                )
                order.ingredients_deducted = True

        db.commit()                             # ← YAGONA commit (butun sotuv atomik)
        db.refresh(payment)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        log.error("[SALE] order=%s sotuv rollback (hech narsa yozilmadi): %s",
                  payment_data.order_id, exc)
        raise HTTPException(status_code=500,
                            detail="Sotuvni saqlashda xatolik — hech narsa yozilmadi, qayta urinib ko'ring")

    # ── OFD Fiskal integratsiya ───────────────────────────────────────────────
    if order_completed:
        # BOSQICH 40: fiskal sozlama tenant-scoped (INN/kassa_id/operator/api_key)
        # payment.tenant_id yuqorida resolve_tenant_id orqali aniqlangan.
        fiscal_config = get_tenant_config(db, payment.tenant_id, "fiscal") or {}
        if fiscal_config.get("enabled"):
            try:
                # payment metodini payload ga qo'shish
                fiscal_config = dict(fiscal_config)
                fiscal_config["payment_type"] = str(payment_data.method)

                ofd = send_to_ofd(order, fiscal_config)
                if ofd.success:
                    order.fiscal_number  = ofd.fiscal_number
                    order.fiscal_qr_url  = ofd.qr_url
                    order.fiscal_sent_at = datetime.now()
                    db.commit()
                    log.info(
                        "[OFD] order=%s fn=%s qr=%s",
                        order.id, ofd.fiscal_number, (ofd.qr_url or "")[:60]
                    )
                else:
                    # To'lov bekor bo'lmaydi — faqat loglash
                    log.warning("[OFD] order=%s yuborilmadi: %s", order.id, ofd.error)
            except Exception as exc:
                log.exception("[OFD] kutilmagan xato order=%s: %s", order.id, exc)

    # BOSQICH 2.6: to'lov haqida WebSocket xabari
    ws_payload = {
        "type": "payment_received",
        "order_id": order.id,
        "order_number": order.order_number,
        "table": order.table.number if order.table else None,
        "amount": payment_data.amount,
        "method": payment_data.method,
        "order_completed": order_completed,
    }
    await manager.broadcast_to_pos(ws_payload, tenant_id=resolve_tenant_id(db, current_user))
    if order_completed:
        # Oshxonaga ham xabar: bu buyurtma tugadi
        await manager.broadcast_to_kitchen({
            "type": "order_completed",
            "order_id": order.id,
            "order_number": order.order_number,
        }, tenant_id=resolve_tenant_id(db, current_user))

    # Sodiqlik natijasini javobga qo'shamiz (chek: yig'ilgan/ishlatilgan/qolgan balans)
    payment.earned_points   = _loyalty["earned"] or None
    payment.redeemed_points = _loyalty["redeemed"] or None
    if order_completed and order.customer_id and (_loyalty["earned"] or _loyalty["redeemed"]):
        from models import Customer
        _c = db.query(Customer).filter(Customer.id == order.customer_id).first()
        payment.customer_points = (_c.points if _c else None)
    return PaymentInDB.model_validate(payment)

@router.get("/{payment_id}", response_model=PaymentInDB)
async def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """To'lov ma'lumotlarini olish"""
    payment = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")
    
    return PaymentInDB.model_validate(payment)

@router.post("/{payment_id}/refund", response_model=MessageResponse)
async def refund_payment(
    payment_id: int,
    amount: Optional[float] = None,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("process_payments"))
):
    """To'lovni qaytarish"""
    payment_service = PaymentService(db)

    payment = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")
    
    if payment.status != "paid":
        raise HTTPException(status_code=400, detail="Faqat to'langan to'lovlarni qaytarish mumkin")
    
    # ── IKKI PARALLEL YO'L QO'RIQCHISI ──────────────────────────────────────
    # Vozvratning ikkinchi yo'li — `POST /returns/` hujjati (u ham omborni
    # tiklaydi va endi pulni ham qaytaradi). Ikkalasi bir buyurtmaga
    # qo'llanilsa ombor IKKI MARTA oshib ketardi.
    # Qoida: qaytarish hujjati bo'lsa — pul va ombor SHU hujjat orqali yuriydi.
    from models import Return as _Return
    _ret = (
        db.query(_Return)
        .filter(_Return.order_id == payment.order_id,
                _Return.status.in_(["pending", "approved"]))
        .first()
    )
    if _ret:
        raise HTTPException(
            status_code=409,
            detail=(f"Bu buyurtma uchun qaytarish hujjati bor ({_ret.return_number}, "
                    f"holat: {_ret.status}). Pul va ombor o'sha hujjat orqali yuritiladi — "
                    f"bu yerda qaytarish ikki marta hisoblanishiga olib keladi."),
        )

    refund_amount = amount or payment.amount
    
    if refund_amount > payment.amount:
        raise HTTPException(status_code=400, detail="Qaytarish summasi to'lov summasidan ko'p bo'lishi mumkin emas")
    
    # ── ATOMIK REFUND ────────────────────────────────────────────────────────
    # Refund yozuvi + order.status + ombor TIKLASH — bitta tranzaksiya, bitta commit.
    # Xato bo'lsa BUTUN qaytarish rollback (pul ham tiklanmaydi) → yarim holat yo'q.
    try:
        # commit=False → xato yuqoriga uzatiladi, quyidagi except rollback qiladi.
        payment_service.refund_payment(payment, refund_amount, reason, commit=False)

        order = payment.order
        if refund_amount == payment.amount:
            payment.status = "refunded"
        db.flush()

        # Barcha to'lovlar qaytarilganmi? (flush qilingan yozuvlarni ham ko'radi)
        paids = db.query(Payment).filter(Payment.order_id == order.id).all()
        all_refunded = bool(paids) and all(p.status == "refunded" for p in paids)

        do_restore = False
        if all_refunded and order.ingredients_deducted:
            # TOCTOU: order qatorini QULFLAB ingredients_restored ni DB'dan yangi o'qiymiz.
            # Ikki marta (parallel) refund bir xil zaxirani IKKI MARTA qaytarib qo'ymaydi.
            db.refresh(order, with_for_update=True)
            if not order.ingredients_restored:
                do_restore = True
        if all_refunded and order.status == "completed":
            order.status = "cancelled"
        if do_restore:
            from services.recipe_inventory_service import restore_order_ingredients
            # deduct bilan bir xil barqaror qulf tartibi (Inventory.id) — deadlock yo'q.
            restore_order_ingredients(
                db, order.id, tenant_id=order.tenant_id, user_id=current_user.id, commit=False,
            )
            order.ingredients_restored = True

        # ── SODIQLIK teskari: to'liq refund'да yig'ilgan ball olinadi, ishlatilgan qaytadi.
        # Ombordan mustaqil (xizmat/retseptsiz uchun ham) — idempotent (adjust yozuvi bilan).
        if all_refunded:
            from core.loyalty_config import reverse_on_refund
            reverse_on_refund(db, order, order.tenant_id)

        db.commit()                             # ← YAGONA commit (butun refund atomik)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        log.error("[REFUND] payment=%s qaytarish rollback (hech narsa yozilmadi): %s",
                  payment_id, exc)
        raise HTTPException(status_code=500,
                            detail="Qaytarishda xatolik — hech narsa yozilmadi, qayta urinib ko'ring")

    return MessageResponse(message="To'lov qaytarildi")

@router.get("/methods/summary")
async def get_payment_methods_summary(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """To'lov usullari bo'yicha xulosa"""
    from sqlalchemy import func

    query = db.query(
        Payment.method,
        func.sum(Payment.amount).label('total'),
        func.count(Payment.id).label('count')
    ).filter(Payment.status == "paid")
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Payment, current_user)

    if date_from:
        query = query.filter(Payment.created_at >= date_from)
    
    if date_to:
        query = query.filter(Payment.created_at <= date_to)
    
    results = query.group_by(Payment.method).all()

    return [
        {
            "method": r.method,
            "total": float(r.total or 0),
            "count": r.count
        }
        for r in results
    ]


@router.post("/{payment_id}/tip")
async def add_tip(
    payment_id: int,
    tip_amount: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("process_payments"))
):
    """
    Choy puli (tips) qo'shish (BOSQICH 9.11).
    Ofitsiantga to'lovdan alohida qo'shilgan summa.
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(404, "To'lov topilmadi")
    if tip_amount < 0:
        raise HTTPException(400, "Choy puli manfiy bo'lishi mumkin emas")
    payment.tip_amount = tip_amount
    db.commit()
    return {"success": True, "tip_amount": tip_amount, "payment_id": payment_id}


@router.get("/tips/summary")
async def get_tips_summary(
    date_from: str = None,
    date_to: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """Choy puli umumiy hisoboti вЂ” ofitsiant bo'yicha"""
    from sqlalchemy import func as sqlfunc
    from datetime import datetime as dt
    q = db.query(
        Payment.cashier_id,
        sqlfunc.sum(Payment.tip_amount).label("total_tips"),
        sqlfunc.count(Payment.id).label("payments_count")
    ).filter(Payment.tip_amount > 0)

    if date_from:
        try:
            q = q.filter(Payment.created_at >= dt.fromisoformat(date_from))
        except Exception:
            pass
    if date_to:
        try:
            q = q.filter(Payment.created_at <= dt.fromisoformat(date_to))
        except Exception:
            pass

    results = q.group_by(Payment.cashier_id).all()
    return [{"cashier_id": r.cashier_id, "total_tips": float(r.total_tips or 0), "payments_count": r.payments_count}
            for r in results]
