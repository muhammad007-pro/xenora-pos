"""
Yetkazib beruvchilar (Suppliers) router — BOSQICH 24 (B2B)
Firma kartochkasi: INN (tax_id), telefon, manzil, shartnoma, otsrochka, mas'ul shaxs.
Qarz summary hisoblash: priyomkalar - to'lovlar - vozvratlар.
FAZA 1: hisobning O'ZI services/supplier_debt.py ga ko'chirildi (yagona manba).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date as Date
from typing import Optional

from database import get_db
from models import PurchaseReceipt, Supplier, User
from schemas import (
    SupplierCreate, SupplierUpdate, SupplierInDB,
    SupplierDebtSummary, SupplierLedgerEntry, PaginatedResponse, MessageResponse,
    ManualDebtCreate, ManualDebtUpdate, ManualDebtInDB,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission
from core.audit import log_audit
from services.supplier_debt import compute_debts, is_manual_debt, supplier_ledger

router = APIRouter()


@router.get("/", response_model=PaginatedResponse)
async def list_suppliers(
    search:    Optional[str] = None,
    is_active: Optional[bool] = True,
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(Supplier), Supplier, current_user)
    if is_active is not None:
        q = q.filter(Supplier.is_active == is_active)
    if search:
        q = q.filter(Supplier.name.ilike(f"%{search}%"))
    total = q.count()
    rows  = q.order_by(Supplier.name).offset((page - 1) * page_size).limit(page_size).all()
    items = [SupplierInDB.model_validate(r) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size,
                             total_pages=(total + page_size - 1) // page_size)


@router.post("/", response_model=SupplierInDB)
async def create_supplier(
    data: SupplierCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    s = Supplier(tenant_id=resolve_tenant_id(db, current_user), **data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return SupplierInDB.model_validate(s)


@router.get("/debt-summary", response_model=list)
async def debt_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Barcha firmalar qarz holati (qizil = muddati o'tgan)

    Hisob services/supplier_debt.py da — /store-dashboard ham SHU servisni
    chaqiradi, ya'ni ikki ekran endi bir xil son ko'rsatadi.
    """
    suppliers = (
        apply_tenant_filter(db.query(Supplier), Supplier, current_user)
        .filter(Supplier.is_active == True)
        .order_by(Supplier.name)
        .all()
    )
    debts = compute_debts(db, suppliers)
    result = []
    for s in suppliers:
        d = debts[s.id]
        result.append(SupplierDebtSummary(
            supplier_id=d.supplier_id,
            supplier_name=d.supplier_name,
            phone=d.phone,
            total_purchases=d.total_purchases,
            total_paid=d.total_paid,
            total_returned=d.total_returned,
            debt=d.debt,
            advance=d.advance,
            balance=d.balance,
            opening_debt=d.opening_debt,
            overdue_amount=d.overdue_amount,
            last_purchase=str(d.last_purchase) if d.last_purchase else None,
        ).model_dump())
    return result


@router.get("/{supplier_id}/ledger", response_model=list[SupplierLedgerEntry])
async def supplier_ledger_view(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """FAZA 4 — OBOROT VARAG'I: bitta firma bo'yicha xronologik harakat.

    Do'konchi agent bilan hisob-kitob qilganda ochadigan ekran: nakladnoy /
    to'lov / vozvrat, har qatorda yugurib boruvchi qoldiq. Hisob services/
    supplier_debt.py da — /debt-summary bilan BIR XIL manba (oxirgi qatordagi
    qoldiq `balance` bilan mos, test bilan qotirilgan).
    """
    s = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
          .filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Firma topilmadi")

    return [
        SupplierLedgerEntry(
            date=str(e.date) if e.date else None,
            kind=e.kind, label=e.label,
            amount=e.amount, balance=e.balance, ref_id=e.ref_id,
        )
        for e in supplier_ledger(db, s)
    ]


# ═══════════════════════════════════════════════════════════════════════════
# QO'LDA QARZ (priyomkasiz) — "firmadan qarz oldim"
#
# Do'kon tovar hisobini yuritmasa ham nasiyani yozib borishi kerak. Bu yerda
# yaratilgan yozuv — qatorlari YO'Q, TASDIQLANGAN priyomka. Shu sababli u
# FIFO, oborot varag'i, /debt-summary va /store-dashboard ga O'Z-O'ZIDAN
# tushadi: qarz hisobining birorta qatori o'zgartirilmagan.
# Batafsil (nega yangi jadval emas, marker nima): services/supplier_debt.py
#
# ⚠️ MARSHRUT TARTIBI: `/debts/{debt_id}` `/{supplier_id}` DAN OLDIN turishi
# shart — aks holda FastAPI "debts" ni supplier_id deb o'qib 422 qaytaradi.
# ═══════════════════════════════════════════════════════════════════════════

def _manual_debt_or_404(db: Session, current_user: User, debt_id: int) -> PurchaseReceipt:
    """Qo'lda qarz yozuvini oladi. ODDIY PRIYOMKAGA TEGISHNI RAD ETADI.

    Bu qo'riqcha muhim: `debt_id` o'rniga haqiqiy nakladnoy id'si yuborilsa,
    tahrirlash/o'chirish ombor kirimi bo'lgan hujjatni buzgan bo'lardi.
    """
    rec = (
        apply_tenant_filter(db.query(PurchaseReceipt), PurchaseReceipt, current_user)
        .filter(PurchaseReceipt.id == debt_id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Qarz yozuvi topilmadi")
    if not is_manual_debt(rec):
        raise HTTPException(
            status_code=400,
            detail="Bu — tovarli nakladnoy, qo'lda qarz emas. Uni Priyomkalar bo'limidan boshqaring.",
        )
    return rec


def _parse_date(value, field: str) -> Date:
    if isinstance(value, Date):
        return value
    try:
        return Date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field}: sana formati noto'g'ri (YYYY-MM-DD)")


def _manual_debt_out(rec: PurchaseReceipt, paid: float = 0.0, remaining: float = 0.0) -> dict:
    return ManualDebtInDB(
        id=rec.id,
        supplier_id=rec.supplier_id,
        supplier_name=rec.supplier.name if rec.supplier else None,
        amount=float(rec.net_amount or 0),
        debt_date=str(rec.receipt_date),
        notes=rec.notes,
        paid=paid,
        remaining=remaining,
        created_at=rec.created_at,
    ).model_dump()


@router.get("/{supplier_id}/debts", response_model=list)
async def list_manual_debts(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Firmaning qo'lda kiritilgan qarzlari (FIFO qoldig'i bilan)."""
    s = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
          .filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Firma topilmadi")

    d = compute_debts(db, [s])[s.id]
    # FIFO natijasi receipt_id bo'yicha — qo'lda qarz ham shu ro'yxatda
    by_id = {r.receipt_id: r for r in d.receipts}

    rows = (
        db.query(PurchaseReceipt)
        .filter(PurchaseReceipt.supplier_id == supplier_id,
                PurchaseReceipt.is_manual_debt == True)   # noqa: E712
        .order_by(PurchaseReceipt.receipt_date.desc(), PurchaseReceipt.id.desc())
        .all()
    )
    out = []
    for r in rows:
        fifo = by_id.get(r.id)
        out.append(_manual_debt_out(
            r,
            paid=fifo.paid if fifo else 0.0,
            remaining=fifo.remaining if fifo else float(r.net_amount or 0),
        ))
    return out


@router.post("/{supplier_id}/debts", response_model=ManualDebtInDB)
async def create_manual_debt(
    supplier_id: int,
    data: ManualDebtCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """"Firmadan qarz oldim" — priyomkasiz qarz qo'shish."""
    s = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
          .filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Firma topilmadi")

    tid = resolve_tenant_id(db, current_user)
    rec = PurchaseReceipt(
        tenant_id=tid,
        supplier_id=s.id,
        invoice_number=None,          # hujjat yo'q — shuning uchun bo'sh
        receipt_date=_parse_date(data.debt_date, "debt_date"),
        total_amount=data.amount,
        discount_amount=0.0,
        net_amount=data.amount,
        notes=(data.notes or None),
        # `confirmed` — qarz DARHOL kuchga kiradi. `draft` bo'lsa
        # DEBT_STATUSES ga kirmasdi va qarz ko'rinmasdi. Ombor esa
        # baribir tegilmaydi: qatorlar yo'q, confirm endpointi chaqirilmaydi.
        status="confirmed",
        confirmed_by=current_user.id,
        created_by=current_user.id,
        paid_now=0,
        is_manual_debt=True,       # MARKER (migratsiya 3f7a2c9e1b04)
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    log_audit(current_user, "supplier_debt", "CREATE", rec.id, tenant_id=tid, detail={
        "supplier_id": s.id, "supplier_name": s.name,
        "amount": float(data.amount), "debt_date": str(rec.receipt_date),
        "notes": data.notes,
    })
    return _manual_debt_out(rec, paid=0.0, remaining=float(data.amount))


@router.patch("/debts/{debt_id}", response_model=ManualDebtInDB)
async def update_manual_debt(
    debt_id: int,
    data: ManualDebtUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Xato kiritilgan qarzni tuzatish (summa / sana / izoh)."""
    rec = _manual_debt_or_404(db, current_user, debt_id)
    before = {"amount": float(rec.net_amount or 0), "debt_date": str(rec.receipt_date), "notes": rec.notes}

    if data.amount is not None:
        rec.total_amount = data.amount
        rec.net_amount   = data.amount
    if data.debt_date is not None:
        rec.receipt_date = _parse_date(data.debt_date, "debt_date")
    if data.notes is not None:
        rec.notes = data.notes or None

    db.commit()
    db.refresh(rec)

    log_audit(current_user, "supplier_debt", "UPDATE", rec.id, tenant_id=rec.tenant_id, detail={
        "supplier_id": rec.supplier_id,
        "oldin": before,
        "keyin": {"amount": float(rec.net_amount or 0), "debt_date": str(rec.receipt_date), "notes": rec.notes},
    })
    return _manual_debt_out(rec)


@router.delete("/debts/{debt_id}", response_model=MessageResponse)
async def delete_manual_debt(
    debt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Qo'lda qarzni butunlay o'chirish (noto'g'ri kiritilgan bo'lsa).

    ⚠️ Unga BOG'LANGAN to'lov bo'lsa o'chirish TO'SILADI: aks holda to'lov
    "bog'lanmagan" bo'lib qolib, FIFO orqali boshqa qarzga o'tib ketardi va
    do'konchi buni sezmasdi. Avval to'lovni o'chirish kerak.
    """
    from models import SupplierPayment

    rec = _manual_debt_or_404(db, current_user, debt_id)
    linked = db.query(SupplierPayment).filter(SupplierPayment.receipt_id == rec.id).count()
    if linked:
        raise HTTPException(
            status_code=400,
            detail=f"Bu qarzga {linked} ta to'lov bog'langan. Avval o'sha to'lovlarni o'chiring.",
        )

    snapshot = {
        "supplier_id": rec.supplier_id,
        "amount": float(rec.net_amount or 0),
        "debt_date": str(rec.receipt_date),
        "notes": rec.notes,
    }
    tid = rec.tenant_id
    db.delete(rec)
    db.commit()

    log_audit(current_user, "supplier_debt", "DELETE", debt_id, tenant_id=tid, detail=snapshot)
    return MessageResponse(message="Qarz yozuvi o'chirildi")


@router.get("/{supplier_id}", response_model=SupplierInDB)
async def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    s = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
          .filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Firma topilmadi")
    return SupplierInDB.model_validate(s)


@router.patch("/{supplier_id}", response_model=SupplierInDB)
async def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    s = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
          .filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Firma topilmadi")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return SupplierInDB.model_validate(s)


@router.delete("/{supplier_id}", response_model=MessageResponse)
async def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    s = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
          .filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Firma topilmadi")
    s.is_active = False
    db.commit()
    return MessageResponse(message="Firma arxivlandi")
