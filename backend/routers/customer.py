from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import Customer, CustomerDebt, DebtPayment, User, Order
from schemas import (
    CustomerCreate, CustomerUpdate, CustomerInDB, PaginatedResponse,
    MessageResponse, CustomerDebtPayRequest,
)
from deps import resolve_tenant_id, get_current_user, get_current_active_user, has_permission, apply_tenant_filter
from core.audit import log_audit
# Mijoz qarzi — FIFO/qoldiq/avans hisobining YAGONA manbasi. Vozvrat yo'li
# (`routers/returns.py`) ham AYNAN shu funksiyalarni ishlatadi.
from services.customer_debt import (
    add_advance, apply_payment_to_debts, pick_debts_fifo,
    preview_allocation, recalc_customer_debt, record_debt_payment,
)

router = APIRouter()

@router.get("/", response_model=PaginatedResponse)
async def get_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha mijozlarni olish"""
    query = db.query(Customer)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Customer, current_user)

    if search:
        query = query.filter(
            Customer.name.ilike(f"%{search}%") | 
            Customer.phone.ilike(f"%{search}%") |
            Customer.email.ilike(f"%{search}%")
        )
    
    total = query.count()
    customers = query.order_by(Customer.name).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[CustomerInDB.model_validate(c) for c in customers],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.get("/all", response_model=list[CustomerInDB])
async def get_all_customers(
    limit: int = Query(500, ge=1, le=2000),   # cheklovsiz .all() XAVFLI edi (50k+ → sekin/OOM)
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mijozlar ro'yxati (nom bo'yicha, cheklangan). Ko'p mijozli do'kon uchun default 500,
    maksimum 2000. Ko'proq kerak bo'lsa — /customers/?search=... (paginatsiyalangan) ishlatilsin."""
    query = apply_tenant_filter(db.query(Customer), Customer, current_user)
    customers = query.order_by(Customer.name).limit(limit).all()
    return [CustomerInDB.model_validate(c) for c in customers]

@router.post("/", response_model=CustomerInDB)
async def create_customer(
    customer_data: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Yangi mijoz yaratish"""
    # Telefon raqam tekshirish
    if customer_data.phone:
        existing = db.query(Customer).filter(Customer.phone == customer_data.phone).first()
        if existing:
            raise HTTPException(status_code=400, detail="Bu telefon raqam band")
    
    # Email tekshirish
    if customer_data.email:
        existing = db.query(Customer).filter(Customer.email == customer_data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Bu email band")
    
    # BOSQICH 1.5: yangi yozuv yaratuvchi tenant'iga biriktiriladi
    customer = Customer(**customer_data.model_dump(), tenant_id=resolve_tenant_id(db, current_user))
    db.add(customer)
    db.commit()
    db.refresh(customer)
    
    return CustomerInDB.model_validate(customer)

@router.get("/{customer_id}", response_model=CustomerInDB)
async def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mijoz ma'lumotlarini olish"""
    customer = apply_tenant_filter(db.query(Customer), Customer, current_user).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    
    return CustomerInDB.model_validate(customer)

@router.patch("/{customer_id}", response_model=CustomerInDB)
async def update_customer(
    customer_id: int,
    customer_data: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mijozni yangilash"""
    customer = apply_tenant_filter(db.query(Customer), Customer, current_user).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    
    update_data = customer_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)
    
    db.commit()
    db.refresh(customer)
    
    return CustomerInDB.model_validate(customer)

@router.delete("/{customer_id}", response_model=MessageResponse)
async def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_customers"))
):
    """Mijozni o'chirish"""
    customer = apply_tenant_filter(db.query(Customer), Customer, current_user).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    
    # Buyurtmalar mavjudligini tekshirish
    if customer.orders:
        raise HTTPException(status_code=400, detail="Bu mijozda buyurtmalar mavjud, o'chirib bo'lmaydi")
    
    db.delete(customer)
    db.commit()
    
    return MessageResponse(message="Mijoz o'chirildi")

@router.get("/{customer_id}/orders")
async def get_customer_orders(
    customer_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mijozning buyurtmalarini olish"""
    from schemas import OrderInDB, PaginatedResponse

    customer = apply_tenant_filter(db.query(Customer), Customer, current_user).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    query = db.query(Order).filter(Order.customer_id == customer_id)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Order, current_user)
    total = query.count()
    orders = query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[OrderInDB.model_validate(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.get("/{customer_id}/stats")
async def get_customer_stats(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mijoz statistikasi"""
    customer = apply_tenant_filter(db.query(Customer), Customer, current_user).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    
    orders = customer.orders
    
    total_spent = sum(o.final_amount for o in orders if o.status == "completed")
    total_visits = len([o for o in orders if o.status == "completed"])
    average_check = total_spent / total_visits if total_visits > 0 else 0
    last_visit = max([o.created_at for o in orders]) if orders else None
    
    return {
        "customer_id": customer_id,
        "customer_name": customer.name,
        "total_spent": total_spent,
        "total_visits": total_visits,
        "average_check": average_check,
        "points": customer.points,
        "last_visit": last_visit
    }

@router.post("/search")
async def search_customers(
    query: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mijozlarni qidirish"""
    customers = apply_tenant_filter(db.query(Customer), Customer, current_user).filter(
        Customer.name.ilike(f"%{query}%") |
        Customer.phone.ilike(f"%{query}%")
    ).limit(10).all()

    return [CustomerInDB.model_validate(c) for c in customers]


@router.get("/{customer_id}/favorites")
async def get_customer_favorites(
    customer_id: int,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Mijozning sevimli taomlari (BOSQICH 9.12).
    OrderItem bo'yicha eng ko'p buyurtma qilingan mahsulotlar.
    """
    from models import Order, OrderItem, Product
    from sqlalchemy import func as sqlfunc

    results = (
        db.query(
            OrderItem.product_id,
            sqlfunc.sum(OrderItem.quantity).label("total_qty"),
            sqlfunc.count(OrderItem.id).label("order_count"),
            sqlfunc.sum(OrderItem.total_price).label("total_spent"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.customer_id == customer_id)
        .group_by(OrderItem.product_id)
        .order_by(sqlfunc.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )

    favorites = []
    for r in results:
        p = db.query(Product).filter(Product.id == r.product_id).first()
        favorites.append({
            "product_id": r.product_id,
            "product_name": p.name if p else "вЂ”",
            "product_price": p.price if p else 0,
            "product_image": p.image_url if p else None,
            "total_qty": int(r.total_qty or 0),
            "order_count": r.order_count,
            "total_spent": float(r.total_spent or 0),
        })
    return favorites


@router.get("/{customer_id}/history")
async def get_customer_history(
    customer_id: int,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Mijozning buyurtma tarixi (BOSQICH 9.12).
    """
    from models import Order, OrderItem, Product

    q = db.query(Order).filter(Order.customer_id == customer_id).order_by(Order.created_at.desc())
    total = q.count()
    orders = q.offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for o in orders:
        items = []
        for i in o.items:
            p = i.product
            items.append({
                "product_name": p.name if p else "вЂ”",
                "quantity": i.quantity,
                "price": i.unit_price,
            })
        result.append({
            "id": o.id,
            "order_number": o.order_number,
            "status": o.status,
            "final_amount": o.final_amount,
            "created_at": o.created_at,
            "items": items,
        })
    return {"items": result, "total": total, "page": page, "page_size": page_size}


# ═══════════════════════════════════════════════════════════════════════════
# QARZ KARTOCHKASI (nasiya) — FAQAT KO'RSATISH
#
# Do'konchi mijoz bilan turganda ochadigan ekran: "qara, hammasi shu yerda".
# Naqsh `routers/suppliers.py` dagi firma OBOROT VARAG'I bilan BIR XIL:
# xronologik harakat + yugurib boruvchi qoldiq.
#
# ⚠️ PUL MANTIG'IGA TEGMAYDI. Bu yerda hech narsa YOZILMAYDI va qoldiq
#    QAYTA HISOBLANMAYDI — `remaining`/`status`/`total_debt` qiymatlari
#    `routers/debt.py` (va vozvratda `routers/returns.py`) yozgan HOLICHA
#    o'qiladi. Shu sababli kartochkadagi "Jami qoldiq" Nasiya ro'yxatidagi
#    raqam bilan aynan bir xil bo'ladi.
#
# TENANT IZOLYATSIYASI — ikki qavat:
#   1) mijoz `apply_tenant_filter` bilan topiladi → begona mijoz 404
#   2) qarzlar va buyurtmalar ham `apply_tenant_filter` bilan o'qiladi
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/{customer_id}/debt-card")
async def get_customer_debt_card(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Mijoz qarz kartochkasi: qarzlar + olingan mahsulotlar + to'lovlar + oborot."""
    from datetime import datetime, timezone
    from models import CustomerDebt, DebtPayment, OrderItem, Product
    from core.timeutils import to_utc

    # Oborotni saralash kaliti. `created_at` NULL bo'lishi kutilmaydi
    # (server_default bor), lekin xom SQL bilan kiritilgan qatorda bo'lishi
    # MUMKIN — unda `None` solishtirishda TypeError berib butun kartochkani
    # 500 qilardi. NULL eng tepaga chiqadi.
    _FAR_PAST = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def _ts(dt):
        return to_utc(dt) or _FAR_PAST

    customer = (
        apply_tenant_filter(db.query(Customer), Customer, current_user)
        .filter(Customer.id == customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    debts = (
        apply_tenant_filter(db.query(CustomerDebt), CustomerDebt, current_user)
        .filter(CustomerDebt.customer_id == customer_id)
        .order_by(CustomerDebt.created_at.asc(), CustomerDebt.id.asc())
        .all()
    )

    # ── Chek raqami + olingan mahsulotlar ──────────────────────────────────
    # `order_id IS NULL` = QO'LDA kiritilgan qarz ("+ Qarz yozish" tugmasi,
    # POS'siz). Bu XATO EMAS: chek raqami o'rniga shunday belgilanadi va
    # mahsulot ro'yxati bo'sh qoladi (frontend buni ko'rsatadi).
    order_ids = [d.order_id for d in debts if d.order_id]
    orders_map: dict = {}
    items_map: dict = {}
    if order_ids:
        for o in (
            apply_tenant_filter(db.query(Order), Order, current_user)
            .filter(Order.id.in_(order_ids))
            .all()
        ):
            orders_map[o.id] = o
        if orders_map:
            rows = (
                db.query(OrderItem, Product.name)
                .outerjoin(Product, Product.id == OrderItem.product_id)
                .filter(OrderItem.order_id.in_(list(orders_map.keys())))
                .order_by(OrderItem.order_id.asc(), OrderItem.id.asc())
                .all()
            )
            for it, pname in rows:
                items_map.setdefault(it.order_id, []).append({
                    "product_id":  it.product_id,
                    "name":        pname or (f"Mahsulot #{it.product_id}" if it.product_id else "—"),
                    "quantity":    it.quantity,
                    "unit_sold":   it.unit_sold,
                    "unit_price":  it.unit_price,
                    "total_price": it.total_price,
                })

    # ── To'lovlar (kim qabul qilgani bilan) ────────────────────────────────
    debt_ids = [d.id for d in debts]
    pay_rows = []
    if debt_ids:
        pay_rows = (
            db.query(DebtPayment, User.full_name, User.username)
            .outerjoin(User, User.id == DebtPayment.user_id)
            .filter(DebtPayment.debt_id.in_(debt_ids))
            .order_by(DebtPayment.created_at.asc(), DebtPayment.id.asc())
            .all()
        )

    payments = [{
        "id":             p.id,
        "debt_id":        p.debt_id,
        "amount":         p.amount,
        "payment_method": p.payment_method,
        "notes":          p.notes,
        "created_at":     p.created_at,
        "user_id":        p.user_id,
        "user_name":      full_name or uname or "—",
    } for p, full_name, uname in pay_rows]

    paid_by_debt: dict = {}
    for p in payments:
        paid_by_debt[p["debt_id"]] = paid_by_debt.get(p["debt_id"], 0.0) + (p["amount"] or 0)

    # ── Qarzlar ro'yxati ───────────────────────────────────────────────────
    debt_list = []
    for d in debts:
        o = orders_map.get(d.order_id) if d.order_id else None
        debt_list.append({
            "id":            d.id,
            "created_at":    d.created_at,
            "order_id":      d.order_id,
            "order_number":  o.order_number if o else None,
            "daily_number":  o.daily_number if o else None,
            # Qarz POS sotuvidan emas, qo'lda kiritilgan (yoki buyurtma
            # boshqa tenantga tegishli) — frontend chek raqami o'rniga shuni
            # ko'rsatadi, xato bermaydi.
            "is_manual":     d.order_id is None,
            # Vozvrat avansi: `amount`/`remaining` MANFIY (returns.py) —
            # qarz emas, mijoz foydasiga qoldiq.
            "is_advance":    (d.amount or 0) < 0,
            "amount":        d.amount,
            "paid_amount":   d.paid_amount,
            "remaining":     d.remaining,
            "status":        d.status,
            "due_date":      d.due_date,
            "notes":         d.notes,
            "items":         items_map.get(d.order_id, []) if d.order_id else [],
        })

    # ── XRONOLOGIK OBOROT (qarz / to'lov aralash, yugurib boruvchi qoldiq) ──
    # KAFOLAT: oxirgi qator `balance` = `customers.total_debt` (ochiq+qisman
    # qarzlar `remaining` yig'indisi). Shuning uchun uchinchi tur yozuv ham
    # kerak: VOZVRAT qarzni `paid_amount` orqali kamaytiradi, lekin
    # `DebtPayment` qatori YARATMAYDI (routers/returns.py:590). Shu farq
    # (`paid_amount` − to'lovlar yig'indisi) "vozvrat bilan yopilgan" qatori
    # bo'lib tushadi, aks holda oborot qoldig'i kartadagi raqamdan oshardi.
    events = []
    for d in debts:
        advance = (d.amount or 0) < 0
        if d.order_id:
            o = orders_map.get(d.order_id)
            label = f"Chek #{o.order_number}" if o else f"Buyurtma #{d.order_id}"
        else:
            label = "Qo'lda kiritilgan qarz"
        if advance:
            label = d.notes or "Vozvrat avansi"
        events.append((_ts(d.created_at), 0, d.id, {
            "date":         d.created_at,
            "kind":         "advance" if advance else "debt",
            "label":        label,
            "amount":       d.amount,
            "debt_id":      d.id,
            "order_id":     d.order_id,
            "order_number": (orders_map.get(d.order_id).order_number
                             if d.order_id and orders_map.get(d.order_id) else None),
        }))

        ret_offset = round((d.paid_amount or 0) - paid_by_debt.get(d.id, 0.0), 2)
        if ret_offset > 0.009:
            events.append((_ts(d.updated_at or d.created_at), 2, d.id, {
                "date":    d.updated_at or d.created_at,
                "kind":    "return",
                "label":   "Vozvrat bilan yopilgan",
                "amount":  -ret_offset,
                "debt_id": d.id,
            }))

    for p in payments:
        usul = {"cash": "naqd", "card": "karta", "click": "Click", "payme": "Payme"}.get(
            p["payment_method"], p["payment_method"] or "—")
        events.append((_ts(p["created_at"]), 1, p["id"], {
            "date":    p["created_at"],
            "kind":    "payment",
            "label":   f"To'lov ({usul}) · {p['user_name']}",
            "amount":  -(p["amount"] or 0),
            "debt_id": p["debt_id"],
        }))

    # Bir kun ichida tartib: qarz → to'lov → vozvrat (o'qishga qulay)
    events.sort(key=lambda t: (t[0], t[1], t[2]))
    ledger = []
    running = 0.0
    for _dt, _ord, _id, e in events:
        running += (e["amount"] or 0)
        e["balance"] = round(running, 2)
        ledger.append(e)

    total_charged = round(sum((d.amount or 0) for d in debts if (d.amount or 0) > 0), 2)
    total_paid    = round(sum((p["amount"] or 0) for p in payments), 2)

    return {
        "customer": {
            "id":           customer.id,
            "name":         customer.name,
            "phone":        customer.phone,
            "total_debt":   customer.total_debt or 0.0,
            "credit_limit": customer.credit_limit,
        },
        "summary": {
            # Manba — `customers.total_debt` (Nasiya ro'yxati bilan bir xil raqam).
            "total_debt":     customer.total_debt or 0.0,
            # Oborotdan hisoblangan qoldiq — yuqoridagi bilan mos bo'lishi shart
            # (test bilan qotirilgan). Farq chiqsa — ma'lumotda nuqson bor.
            "ledger_balance": round(running, 2),
            "total_charged":  total_charged,
            "total_paid":     total_paid,
            "debt_count":     len(debts),
            "open_count":     sum(1 for d in debts if d.status == "open"),
            "partial_count":  sum(1 for d in debts if d.status == "partial"),
            "paid_count":     sum(1 for d in debts if d.status == "paid"),
            "manual_count":   sum(1 for d in debts if d.order_id is None),
        },
        "debts":    debt_list,
        "payments": payments,
        "ledger":   ledger,
    }


# ══════════════════════════════════════════════════════════════════════════════
# UMUMIY QARZ TO'LOVI (FIFO)  —  /customers/{id}/debt-preview va /pay-debt
# ══════════════════════════════════════════════════════════════════════════════
# MUAMMO (jonli, XOZMAG'da 31 ta nasiya): mijoz 500 000 keltirsa va 3 ta qarzi
# bo'lsa, kassir `POST /debts/{id}/pay` ni UCH MARTA, summalarni O'ZI bo'lib
# chaqirishga majbur edi. Firmalarda FIFO bor, mijozlarda yo'q edi.
#
# MANTIQ MANBASI: `services/customer_debt.py` — u vozvrat yo'lidagi
# (`routers/returns.py:_refund_money`) prodda sinalgan FIFO kodining O'ZI.
# Yangi formula yozilmadi.
#
# ⚠️ KASSA BILAN BOG'LANISH: har yopilgan qarz uchun `DebtPayment` yoziladi,
# ORTIQCHA (avans) qism uchun ham. `utils/cashflow.debt_payments_totals`
# aynan `DebtPayment` dan o'qiydi va `routers/shift.py` `expected_cash` ni
# shundan to'ldiradi. Ya'ni QOIDA: qabul qilingan summa = Σ(DebtPayment.amount).
# Avans qismiga yozuv qo'yilmasa, yashikdagi haqiqiy naqd "ortiqcha" bo'lib
# ko'rinardi va kassir asossiz ayblanardi (2026-08-19 xatosining aynan o'zi).


@router.get("/{customer_id}/debt-preview")
async def preview_customer_debt_payment(
    customer_id: int,
    amount: float = Query(..., gt=0, description="Mijoz bergan summa"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("process_payments")),
):
    """Summa qanday taqsimlanishini HECH NARSA YOZMASDAN ko'rsatadi.

    UI shu javobni "500 000 → #5 ga 240 000, #7 ga 260 000" ko'rinishida
    chiqaradi. Hisob frontendda TAKRORLANMAYDI — aks holda ekranda bir xil,
    bazada boshqa taqsimot bo'lib qolardi.
    """
    customer = (
        apply_tenant_filter(db.query(Customer), Customer, current_user)
        .filter(Customer.id == customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    out = preview_allocation(db, customer_id, amount)
    return {
        "customer_id":   customer.id,
        "customer_name": customer.name,
        "total_debt":    round(float(customer.total_debt or 0), 2),
        "amount":        round(float(amount), 2),
        **out,
    }


@router.post("/{customer_id}/pay-debt")
async def pay_customer_debt(
    customer_id: int,
    data: CustomerDebtPayRequest,
    db: Session = Depends(get_db),
    # `process_payments` — KASSIR ham qabul qila olishi kerak (pul olish uning
    # ishi). Taqqoslash: `POST /debts/{id}/pay` `view_finance` talab qiladi va
    # shu sabab kassirga yaramaydi — yangi yo'l aynan shu teshikni yopadi.
    current_user: User = Depends(has_permission("process_payments")),
):
    """Mijozning bir necha qarzini BITTA summa bilan yopadi (eng eskidan, FIFO)."""
    customer = (
        apply_tenant_filter(db.query(Customer), Customer, current_user)
        .filter(Customer.id == customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    amount = round(float(data.amount), 2)
    debts  = pick_debts_fifo(db, customer_id)
    # Ochiq qarz BO'LMASA — jimgina avans yaratmaymiz. Kassir adashib boshqa
    # mijozni tanlagan bo'lishi mumkin, pul esa yashikka tushib ketardi.
    if not any(float(d.remaining or 0) > 0 for d in debts):
        raise HTTPException(
            status_code=400,
            detail=f"«{customer.name}» da yopiladigan ochiq qarz yo'q "
                   f"(joriy qoldiq: {float(customer.total_debt or 0):,.0f}). "
                   f"Avans kiritish uchun boshqa yo'ldan foydalaning.",
        )

    allocations, qoldiq = apply_payment_to_debts(debts, amount)

    # ── DebtPayment yozuvlari — KASSA IZI (yuqoridagi izohga qara) ──────────
    for a in allocations:
        record_debt_payment(
            db,
            debt_id=a["debt_id"],
            amount=a["amount"],
            payment_method=data.payment_method,
            notes=data.notes,
            user_id=current_user.id,
        )

    # ── ORTIQCHA — avans (manfiy qoldiqli qator) ────────────────────────────
    advance_debt_id = None
    advance = 0.0
    if qoldiq > 0.009:
        advance = round(qoldiq, 2)
        adv = add_advance(
            db,
            tenant_id=customer.tenant_id,
            branch_id=getattr(current_user, "_active_branch_id", None),
            customer_id=customer_id,
            order_id=None,
            amount=advance,
            notes=f"Ortiqcha to'lov avansi — qarzdan oshgan summa"
                  + (f" ({data.notes})" if data.notes else ""),
            user_id=current_user.id,
        )
        db.flush()
        advance_debt_id = adv.id
        # ⚠️ Avans qismi ham KASSAGA TUSHGAN: busiz `expected_cash` kam
        # chiqardi. Qator holati (`remaining = -advance`) TEGILMAYDI — bu
        # yozuv faqat pul izi.
        record_debt_payment(
            db,
            debt_id=adv.id,
            amount=advance,
            payment_method=data.payment_method,
            notes="Ortiqcha to'lov (avans) — kassa izi",
            user_id=current_user.id,
        )

    total_debt = recalc_customer_debt(db, customer_id)
    db.commit()

    # Pul yo'li — kim, qancha, qaysi qarzlarga
    log_audit(
        current_user, "customer_debts", "UPDATE", customer_id,
        tenant_id=customer.tenant_id,
        detail={
            "action":          "pay_debt_fifo",
            "customer_name":   customer.name,
            "amount":          amount,
            "payment_method":  data.payment_method,
            "notes":           data.notes,
            "debts_closed":    [a["debt_id"] for a in allocations if a["status"] == "paid"],
            "debts_partial":   [a["debt_id"] for a in allocations if a["status"] == "partial"],
            "allocations":     allocations,
            "advance":         advance,
            "total_debt_after": total_debt,
        },
    )

    _closed = sum(1 for a in allocations if a["status"] == "paid")
    return {
        "customer_id":      customer.id,
        "customer_name":    customer.name,
        "amount":           amount,
        "payment_method":   data.payment_method,
        "applied":          round(amount - qoldiq, 2),
        "advance":          advance,
        "advance_debt_id":  advance_debt_id,
        "allocations":      allocations,
        "debts_closed":     _closed,
        "debts_touched":    len(allocations),
        "total_debt_after": round(total_debt, 2),
        "message": (
            f"{amount:,.0f} so'm qabul qilindi — {len(allocations)} ta qarzga "
            f"taqsimlandi ({_closed} ta to'liq yopildi)"
            + (f", {advance:,.0f} so'm avans" if advance else "")
        ),
    }
