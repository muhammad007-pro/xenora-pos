"""
Qaytarish / Almashtirish router — BOSQICH 19

Endpointlar:
  POST /returns/              — yangi qaytarish yaratish
  GET  /returns/              — ro'yxat (filter bilan)
  GET  /returns/report        — hisobot (sabab, usul bo'yicha)
  GET  /returns/lookup        — CHEK RAQAMI bo'yicha buyurtmani topish (qatorlari bilan)
  GET  /returns/{id}          — bitta tafsilot
  POST /returns/{id}/approve  — tasdiqlash (pul + ombor)
  POST /returns/{id}/reject   — rad etish
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, case
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
# Davr ta'rifi YAGONA manbadan — routers/report.py bilan bir xil qoida
# (tenant mahalliy zonasi, tugash kuni to'liq qamraladi).
from core.timeutils import report_bounds

router = APIRouter()


def _attach_names(ret: Return) -> Return:
    """`created_by_name` / `approved_by_name` ni ORM obyektiga qo'yadi.

    `ReturnInDB` bu ikkisini `from_attributes` orqali o'qiydi — mapped ustun
    EMAS (`warnings` bilan bir xil naqsh). Vozvrat ro'yxatida "kim yaratdi" va
    "kim tasdiqladi" ALOHIDA ustun bo'lib chiqishi uchun kerak: ilgari ikkisi
    ham UI'da umuman ko'rinmasdi, ya'ni ikkinchi ko'z bor-yo'qligini
    do'konchi ko'ra olmasdi.
    """
    u, a = ret.user, ret.approver
    ret.created_by_name  = (u.full_name or u.username) if u else None
    ret.approved_by_name = (a.full_name or a.username) if a else None
    return ret


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
        # 3 XONAGACHA (2026-09-08): kasrli qaytarishda suzuvchi nuqta axlati
        # qoldiqqa qaytmasin — 9.26 + 0.740 aynan 10.0 bo'lsin.
        # Butun songa ta'siri yo'q: round(97.0, 3) == 97.0.
        inv.quantity = round(inv.quantity + quantity, 3)

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


# ═══════════════════════════════════════════════════════════════════════════
# SOTILGANIDAN KO'P QAYTARISHNI TO'SISH
#
# MUAMMO (2026-10-01 auditi): `POST /returns/` miqdorni HECH QANDAY tekshirmasdi.
# 10 dona sotib 50 dona qaytarish mumkin edi:
#   • ombor 40 dona YO'Q tovarga to'ladi (keyin inventarizatsiya "kamomad" deydi)
#   • foyda hisobidan asossiz summa ayriladi (`utils/revenue.py` vozvratni
#     so'zsiz ayiradi — u miqdor to'g'riligini tekshirmaydi, tekshira ham olmaydi)
# Bu xato emas, NIYAT bilan ham ishlatiladigan yo'l edi.
#
# QOIDA: cheklov FAQAT `order_item_id` bog'langan qatorga qo'llanadi —
#   qaytariladigan ≤ sotilgan − allaqachon qaytarilgan
# `order_item_id` yo'q bo'lsa tekshirish MUMKIN EMAS (qaysi sotuv qatori
# ekani noma'lum) -> vozvrat o'tadi, lekin javobda OGOHLANTIRISH qaytadi.
#
# NEGA `pending` HAM SANALADI: tasdiqlanmagan vozvrat miqdorni BAND qiladi.
# Aks holda ikki kassir bir sotuvga 10 talik ikkita pending vozvrat yozib,
# ikkalasi tasdiqlanganda 20 dona qaytardi.
# ═══════════════════════════════════════════════════════════════════════════

# 3 xonali yaxlitlashdan kichik farq — "teng" deb qaraladi (float qoldig'i).
_QTY_EPS = 0.0005

# Summa bo'yicha qidiruvda TAXMINIY moslik oynasi (so'm). Kassir chek
# summasini yaqinlashtirib eslaydi ("360 mingga yaqin") — aniq moslik
# baribir BIRINCHI turadi (order_by dagi `case`).
_AMOUNT_EPS = 1000.0


def _fq(x: float) -> str:
    """Miqdorni o'qishga qulay ko'rsatadi: 3.0 -> "3", 0.740 -> "0.74"."""
    t = f"{float(x):.3f}".rstrip("0").rstrip(".")
    return t or "0"


def _returned_qty_map(db: Session, order_item_ids) -> dict:
    """`order_item_id` -> ALLAQACHON qaytarilgan miqdor.

    `rejected` sanalmaydi (u bekor qilingan), `pending` va `approved` sanaladi.
    """
    ids = [i for i in order_item_ids if i]
    if not ids:
        return {}
    rows = (
        db.query(
            ReturnItem.order_item_id,
            func.coalesce(func.sum(ReturnItem.quantity), 0.0),
        )
        .join(Return, Return.id == ReturnItem.return_id)
        .filter(
            ReturnItem.order_item_id.in_(ids),
            Return.status != "rejected",
        )
        .group_by(ReturnItem.order_item_id)
        .all()
    )
    return {oid: float(q or 0) for oid, q in rows}


def _validate_return_items(db: Session, data, current_user) -> list:
    """Miqdor cheklovini tekshiradi. Buzilsa 400, aks holda ogohlantirishlar.

    Qaytaradi: ogohlantirishlar ro'yxati (bo'sh bo'lishi mumkin).
    """
    warnings: list = []

    # Bir so'rovda BIR XIL qator ikki marta kelishi mumkin — jamlab tekshiramiz,
    # aks holda 2 × 6 dona = 12 dona 10 talik sotuvdan o'tib ketardi.
    talab: dict = {}
    for it in data.items:
        if it.order_item_id:
            talab[it.order_item_id] = talab.get(it.order_item_id, 0.0) + float(it.quantity)

    bogsiz = sum(1 for it in data.items if not it.order_item_id)
    if bogsiz:
        warnings.append(
            f"{bogsiz} qator sotuvga bog'lanmagan (buyurtma qatori tanlanmagan) — "
            "sotilgan miqdordan oshib ketmaganini tizim TEKSHIRA OLMADI."
        )

    if not talab:
        return warnings

    items = (
        apply_tenant_filter(db.query(OrderItem), OrderItem, current_user)
        .filter(OrderItem.id.in_(list(talab.keys())))
        .all()
    )
    by_id = {oi.id: oi for oi in items}
    qaytarilgan = _returned_qty_map(db, talab.keys())

    for oi_id, soralgan in talab.items():
        oi = by_id.get(oi_id)
        if oi is None:
            raise HTTPException(400, f"Sotuv qatori #{oi_id} topilmadi")
        # Buyurtma ko'rsatilgan bo'lsa — qator SHU buyurtmaga tegishli bo'lishi shart.
        # Aks holda boshqa buyurtmaning qatoriga suyanib cheklov aylanib o'tilardi.
        if data.order_id and oi.order_id != data.order_id:
            raise HTTPException(
                400,
                f"Sotuv qatori #{oi_id} bu buyurtmaga tegishli emas "
                f"(u #{oi.order_id} buyurtmada)",
            )

        sotilgan = float(oi.quantity or 0)
        allaqachon = qaytarilgan.get(oi_id, 0.0)
        mumkin = sotilgan - allaqachon

        if soralgan > mumkin + _QTY_EPS:
            nomi = oi.product.name if oi.product else f"Mahsulot #{oi.product_id}"
            if allaqachon > 0:
                raise HTTPException(
                    400,
                    f"{nomi}: bu buyurtmada faqat {_fq(sotilgan)} ta sotilgan, "
                    f"{_fq(allaqachon)} tasi allaqachon qaytarilgan — "
                    f"ko'pi bilan {_fq(mumkin)} ta qaytarish mumkin "
                    f"(so'ralgan: {_fq(soralgan)}).",
                )
            raise HTTPException(
                400,
                f"{nomi}: bu buyurtmada faqat {_fq(sotilgan)} ta sotilgan — "
                f"{_fq(soralgan)} ta qaytarib bo'lmaydi.",
            )

    return warnings


def _validate_refund_method(db: Session, data, current_user) -> list:
    """To'lov usuli mosligi. NASIYA sotuvga naqd/karta tanlansa — TO'SADI.

    NEGA TO'SIQ (ogohlantirish emas): nasiya to'lovi `pending` holatda turadi,
    `_refund_money()` esa naqd/kartada FAQAT `status="paid"` to'lovlarni qidiradi.
    Ya'ni nasiyaga sotilgan tovarga "Naqd" tanlansa:
      • hech qanday `Payment` yozuvi yaratilmaydi (pul qaytganining izi yo'q)
      • mijoz QARZI kamaymaydi (tovar qaytdi, qarz qoldi)
      • Z-hisobot esa `refund_method="cash"` ni ko'rib kutilgan naqdni kamaytiradi
    Uchtasi birga — to'g'ridan-to'g'ri pul yo'qotish. Shuning uchun 400.
    """
    warnings: list = []
    if not data.order_id:
        return warnings

    pays = db.query(Payment).filter(Payment.order_id == data.order_id).all()
    if not pays:
        return warnings          # to'lovsiz buyurtma — taqqoslashga asos yo'q

    def _m(p):
        return str(getattr(p.method, "value", p.method) or "").lower()

    def _st(p):
        return str(getattr(p.status, "value", p.status) or "").lower()

    tolangan = [p for p in pays if _st(p) == "paid"]
    nasiya   = [p for p in pays if _m(p) == "credit" and _st(p) == "pending"]
    usul     = (data.refund_method or "cash").lower()

    if nasiya and not tolangan and usul != "credit":
        raise HTTPException(
            400,
            "Bu buyurtma NASIYAGA sotilgan (pul hali kelmagan) — naqd yoki karta "
            "qaytarib bo'lmaydi. 'Balansga' (nasiya) usulini tanlang: mijozning "
            "qarzi kamayadi.",
        )

    if usul in ("cash", "card") and tolangan:
        haqiqiy = {_m(p) for p in tolangan}
        if usul not in haqiqiy:
            warnings.append(
                "Buyurtma " + ", ".join(sorted(haqiqiy)) + " usulida to'langan, "
                "qaytarish esa " + usul + " tanlangan."
            )

    return warnings


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

    # ── TEKSHIRUVLAR (yozishdan OLDIN) ──────────────────────────────────────
    # Miqdor cheklovi va to'lov usuli mosligi. Ikkisi ham hech narsa yozilmagan
    # holatda ishlaydi -> 400 da baza toza qoladi (rollback kerak emas).
    warnings = _validate_return_items(db, data, current_user)
    warnings += _validate_refund_method(db, data, current_user)

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
    # OGOHLANTIRISHLAR javobga qo'shiladi (mapped ustun emas — oddiy atribut,
    # `ReturnInDB.warnings` uni from_attributes orqali o'qiydi).
    ret.warnings = warnings
    _attach_names(ret)
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
    return [_attach_names(r) for r in q.offset((page - 1) * page_size).limit(page_size).all()]


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


# ── GET /returns/lookup ──────────────────────────────────────────────────────
# ⚠️ MARSHRUT TARTIBI: `/lookup` `/{return_id}` DAN OLDIN turishi SHART —
# aks holda FastAPI "lookup" ni return_id deb o'qib 422 qaytaradi
# (`/report` ham shu sababdan yuqorida).
@router.get("/lookup")
def lookup_order(
    q: str = Query(..., min_length=1, description="Chek raqami, kunlik raqam yoki buyurtma ID"),
    db: Session = Depends(get_db),
    current_user=Depends(has_permission("process_payments")),
):
    """CHEK RAQAMI bo'yicha sotuvni topadi va QAYTARILADIGAN qatorlarni qaytaradi.

    NEGA KERAK: ilgari kassir vozvratda mahsulotni qo'lda tanlab, miqdor va
    narxni qo'lda yozardi. Natijada:
      • `order_item_id` HECH QACHON yuborilmasdi -> miqdor cheklovini tekshirib
        bo'lmasdi va `utils/revenue.py` dagi snapshot tan narx shoxi o'lik edi
      • pachka sotuvi omborga "1 pachka = 1 dona" bo'lib qaytardi
        (`_return_base_qty` nisbatni `order_item_id` orqali topadi)
      • buyurtmani topish uchun ichki DB `id` kerak edi — kassir uni bilmaydi

    Qidiruv tartibi: `order_number` (aniq) -> `daily_number` -> `id`.
    Faqat `completed` sotuvlar (bekor qilingani qaytarilmaydi).
    """
    term = (q or "").strip()
    if not term:
        raise HTTPException(400, "Qidiruv so'zi bo'sh")

    base = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.status == "completed"
    )

    order = base.filter(Order.order_number == term).first()
    if not order and term.isdigit():
        n = int(term)
        # Kunlik raqam — kassir/mijoz ko'radigan son. Bir necha kun bir xil
        # bo'lishi mumkin, shuning uchun ENG YANGISI olinadi.
        order = base.filter(Order.daily_number == n).order_by(Order.id.desc()).first()
        if not order:
            order = base.filter(Order.id == n).first()
    if not order:
        # Aniq topilmadi — qismli moslik (kassir chek raqamining oxirini yozgan)
        order = (
            base.filter(Order.order_number.ilike(f"%{term}%"))
            .order_by(Order.id.desc())
            .first()
        )
    if not order:
        raise HTTPException(404, f"'{term}' bo'yicha tugallangan sotuv topilmadi")

    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    qaytarilgan = _returned_qty_map(db, [oi.id for oi in items])

    rows = []
    for oi in items:
        sotilgan   = float(oi.quantity or 0)
        allaqachon = qaytarilgan.get(oi.id, 0.0)
        qoldi      = round(max(0.0, sotilgan - allaqachon), 3)
        rows.append({
            "order_item_id": oi.id,
            "product_id":    oi.product_id,
            "product_name":  oi.product.name if oi.product else f"Mahsulot #{oi.product_id}",
            "unit_sold":     oi.unit_sold,
            "sold_qty":      round(sotilgan, 3),
            "returned_qty":  round(allaqachon, 3),
            "returnable_qty": qoldi,
            "unit_price":    float(oi.unit_price or 0),
            # SUMMA BO'YICHA QAYTARISH uchun: kassir "9500 so'mlik qaytaraman"
            # deydi va tizim miqdorni SOTUVDAGI narxga bo'lib topadi. Frontend
            # bu rejimni FAQAT og'irlik birliklarida (kg/g/l/litr) ko'rsatadi,
            # shuning uchun birlik kerak. `unit_sold == "pachka"` bo'lsa
            # `unit_price` — QOP narxi, ya'ni bo'linma qop sonini beradi
            # (`quantity` shu qatorda aynan qop soni).
            "sale_unit":     (getattr(oi.product, "sale_unit", None) or None),
        })

    # To'lov usuli — kassirga TAKLIF qilish uchun (nasiya sotuvga naqd tanlansa
    # `_validate_refund_method` 400 beradi; UI'ni oldindan to'g'ri qo'yamiz).
    pays = db.query(Payment).filter(Payment.order_id == order.id).all()

    def _m(pp):
        return str(getattr(pp.method, "value", pp.method) or "").lower()

    def _st(pp):
        return str(getattr(pp.status, "value", pp.status) or "").lower()

    tolangan = [p for p in pays if _st(p) == "paid"]
    nasiya   = [p for p in pays if _m(p) == "credit" and _st(p) == "pending"]
    if nasiya and not tolangan:
        taklif = "credit"
    elif tolangan:
        taklif = _m(tolangan[0]) if _m(tolangan[0]) in ("cash", "card") else "card"
    else:
        taklif = "cash"

    return {
        "order_id":       order.id,
        "order_number":   order.order_number,
        "daily_number":   order.daily_number,
        "created_at":     order.created_at,
        "final_amount":   float(order.final_amount or 0),
        "customer_id":    order.customer_id,
        "customer_name":  order.customer.name if order.customer else None,
        "payment_methods": sorted({_m(p) for p in pays if _m(p)}),
        "suggested_refund_method": taklif,
        "is_credit_sale": bool(nasiya and not tolangan),
        "items":          rows,
    }




# ── GET /returns/orders ──────────────────────────────────────────────────────
# ⚠️ `/{return_id}` DAN OLDIN turishi SHART — aks holda FastAPI "orders" ni
# `return_id` deb o'qib 422 qaytaradi (`/lookup` va `/report` ham shu sababdan
# yuqorida).
@router.get("/orders")
def list_returnable_orders(
    search: Optional[str] = Query(None, description="Chek raqami, summa yoki mijoz ismi"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(has_permission("process_payments")),
):
    """Vozvrat uchun SOTUVLAR RO'YXATI — kassir chekni ro'yxatdan tanlaydi.

    NEGA KERAK: `GET /returns/lookup` chek raqamini BILISHNI talab qiladi.
    Mijoz chekni yo'qotgan bo'lsa yoki raqamni eslamasa, kassir yana qo'lda
    kiritishga qaytadi — `order_item_id` yuborilmaydi, miqdor cheklovi
    tekshirilmaydi (XOZMAG `RET261002001` aynan shunday paydo bo'lgan).
    Bu endpoint oxirgi sotuvlarni ko'rsatadi; tanlangandan keyin UI
    AVVALGIDEK `/lookup` ga boradi — ya'ni qaytarish oqimi O'ZGARMAYDI.

    Davr: standart oxirgi **30 kun** (`report_bounds` — tenant mahalliy zonasi,
    `routers/report.py` bilan BIR XIL qoida). Faqat `completed` sotuvlar.

    BELGILAR (kassir bilib turishi uchun):
      • `has_returns`     — bu sotuvga vozvrat BOR (pending yoki approved)
      • `fully_returned`  — qaytarish uchun qolgani YO'Q (hammasi qaytarilgan)
    `rejected` vozvrat sanalmaydi (`_returned_qty_map` bilan bir xil qoida).
    """
    start, end = report_bounds(date_from, date_to, default_days=30)

    q = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.status == "completed",
        Order.created_at >= start,
        Order.created_at <= end,
    )

    term = (search or "").strip()
    tartib = [Order.created_at.desc(), Order.id.desc()]
    if term:
        like = f"%{term}%"
        shartlar = [
            Order.order_number.ilike(like),
            Order.customer.has(Customer.name.ilike(like)),
        ]
        son = None
        try:
            son = float(term.replace(" ", "").replace(",", "."))
        except ValueError:
            son = None

        if son is not None:
            # SUMMA bo'yicha qidiruv. ANIQ moslik BIRINCHI turadi, keyin
            # taxminiy (±1000 so'm) — kassir "360000" yozib 359 500 lik chekni
            # ham ko'rsin, lekin aniq mos kelgani tepada bo'lsin.
            shartlar.append(Order.final_amount == son)
            shartlar.append(Order.final_amount.between(son - _AMOUNT_EPS, son + _AMOUNT_EPS))
            # Kunlik raqam ham son bilan izlanadi (kassir "3" yozsa)
            if term.isdigit():
                shartlar.append(Order.daily_number == int(term))
            tartib = [
                case((Order.final_amount == son, 0), else_=1).asc(),
                Order.created_at.desc(),
                Order.id.desc(),
            ]
        q = q.filter(or_(*shartlar))

    orders = q.order_by(*tartib).limit(limit).all()
    if not orders:
        return []

    # ── Qaytarish holati: BIR so'rovda (N+1 bo'lmasin) ─────────────────────
    order_ids = [o.id for o in orders]
    items = db.query(OrderItem).filter(OrderItem.order_id.in_(order_ids)).all()
    qaytarilgan = _returned_qty_map(db, [oi.id for oi in items])

    sotilgan_jami: dict = {}
    qaytgan_jami:  dict = {}
    for oi in items:
        sotilgan_jami[oi.order_id] = sotilgan_jami.get(oi.order_id, 0.0) + float(oi.quantity or 0)
        qaytgan_jami[oi.order_id]  = qaytgan_jami.get(oi.order_id, 0.0) + qaytarilgan.get(oi.id, 0.0)

    # To'lov usullari — bitta so'rovda
    pays = db.query(Payment).filter(Payment.order_id.in_(order_ids)).all()
    usullar: dict = {}
    for p in pays:
        m = str(getattr(p.method, "value", p.method) or "").lower()
        if m:
            usullar.setdefault(p.order_id, set()).add(m)

    natija = []
    for o in orders:
        sotilgan = sotilgan_jami.get(o.id, 0.0)
        qaytgan  = qaytgan_jami.get(o.id, 0.0)
        natija.append({
            "order_id":       o.id,
            "order_number":   o.order_number,
            "daily_number":   o.daily_number,
            "created_at":     o.created_at,
            "final_amount":   float(o.final_amount or 0),
            "customer_id":    o.customer_id,
            "customer_name":  o.customer.name if o.customer else None,
            "payment_methods": sorted(usullar.get(o.id, set())),
            "has_returns":    qaytgan > _QTY_EPS,
            # Hammasi qaytarilgan — bu chekni tanlash FOYDASIZ (qator qolmagan).
            # `sotilgan == 0` (qatorsiz sotuv) "to'liq qaytarilgan" DEB SANALMAYDI.
            "fully_returned": bool(sotilgan > 0 and (sotilgan - qaytgan) <= _QTY_EPS),
        })
    return natija


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
    return _attach_names(ret)


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
    # ═══ IKKINCHI KO'Z (2026-10-03) ═══════════════════════════════════════
    # ILGARI: yaratish ham, tasdiqlash ham `process_payments` edi — ya'ni
    # kassir o'z vozvratini o'zi tasdiqlab, kassadan pul chiqarib yuborardi.
    # Nazorat yo'q edi: XOZMAG'da `RET261002001` 12 SEKUND ichida yozilgan
    # va tasdiqlangan (bir odam, chekka bog'lanmagan).
    #
    # ENDI: tasdiqlash/rad etish `manage_shifts` talab qiladi. Bu ruxsat
    # `admin` va `menejer` rollarida BOR, `cashier` da YO'Q (database.py rol
    # urug'i). Ya'ni kassir vozvrat YOZADI (`pending`), pul va ombor esa
    # rahbar tasdiqlagandan KEYIN harakatlanadi.
    #
    # ⚠️ YANGI RUXSAT KODI ATAYIN QO'SHILMADI: `roles` jadvali GLOBAL
    # (tenant_id ustuni YO'Q), shuning uchun yangi `approve_returns` kodi
    # barcha tenantlar rollariga urug'lantirilishi kerak bo'lardi — jonli
    # bazaga migratsiya/seed = ortiqcha xavf. `manage_shifts` ayni shu
    # "rahbar" chizig'ini allaqachon ajratadi.
    #
    # ⚠️ Admin O'ZI yaratgan vozvratni tasdiqlay OLADI (bir kishilik do'konda
    # boshqa yo'l yo'q — XOZMAG'da faol xodim 1 ta). Bunday hol audit logda
    # `self_approved: true` bo'lib ko'rinadi.
    current_user=Depends(has_permission("manage_shifts")),
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

    # Audit: KIM yaratdi va KIM tasdiqladi — ALOHIDA ko'rinadi. `self_approved`
    # bir odam ikki rolni bajargan holni belgilaydi (bir kishilik do'konda
    # qonuniy, ko'p xodimli do'konda tekshirish signali).
    log_audit(current_user, "returns", "UPDATE", ret.id, tenant_id=ret.tenant_id, detail={
        "action": "approve",
        "return_number": ret.return_number,
        "total_amount": float(ret.total_amount or 0),
        "refund_method": ret.refund_method,
        "refund_payments": money["refund_payments"],
        "debt_reduced": money["debt_reduced"],
        "advance": money["advance"],
        "created_by": ret.user_id,
        "created_by_name": (ret.user.full_name if ret.user else None),
        "approved_by": current_user.id,
        "self_approved": (ret.user_id == current_user.id),
        # Chekka bog'lanmagan vozvrat: "sotilganidan ko'p qaytarish" tekshiruvi
        # MUMKIN EMAS edi — audit shuni yozib qoldiradi.
        "order_linked": ret.order_id is not None,
        "order_id": ret.order_id,
    })
    _attach_names(ret)
    return ret


# ── POST /returns/{id}/reject ────────────────────────────────────────────────
@router.post("/{return_id}/reject", response_model=ReturnInDB)
def reject_return(
    return_id: int,
    db: Session = Depends(get_db),
    # IKKINCHI KO'Z: rad etish ham rahbar ishi — tasdiqlash bilan BIR XIL
    # ruxsat (`manage_shifts`). Aks holda kassir o'z vozvratini rad etib,
    # nazorat izini o'chirib yuborishi mumkin edi.
    current_user=Depends(has_permission("manage_shifts")),
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
    # AWARE UTC — `approve` yo'lida allaqachon tuzatilgan (naive qiymatni
    # PostgreSQL SESSIYA ZONASIDA talqin qiladi). Rad etilgan vozvrat
    # hisobotlarga KIRMAYDI (`RETURN_COUNTED_STATUSES = ("approved",)`),
    # shuning uchun bu izchillik tuzatishi, xatti-harakat o'zgarishi EMAS.
    ret.approved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(ret)

    # Audit: rad etish ham yoziladi (ilgari YOZILMASDI — kim rad etgani
    # hech qayerda qolmasdi).
    log_audit(current_user, "returns", "UPDATE", ret.id, tenant_id=ret.tenant_id, detail={
        "action": "reject",
        "return_number": ret.return_number,
        "total_amount": float(ret.total_amount or 0),
        "created_by": ret.user_id,
        "created_by_name": (ret.user.full_name if ret.user else None),
        "rejected_by": current_user.id,
        "self_rejected": (ret.user_id == current_user.id),
        "order_linked": ret.order_id is not None,
    })
    _attach_names(ret)
    return ret
