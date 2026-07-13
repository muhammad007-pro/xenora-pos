"""
Nasiya / Qarz Daftar router — BOSQICH 19

Endpointlar:
  POST /debts/                  — yangi qarz yozuvi yaratish
  GET  /debts/                  — qarzlar ro'yxati (filter bilan)
  GET  /debts/summary           — jami statistika
  GET  /debts/{id}              — bitta qarz tafsiloti
  POST /debts/{id}/pay          — qarzni qisman/to'liq to'lash
  GET  /customers/{cid}/debts   — mijoz qarz tarixi
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, date
from typing import Optional, List

from database import get_db
from models import CustomerDebt, DebtPayment, Customer, Order, Inventory, StockMovement
from schemas import (
    DebtCreate, DebtInDB, DebtPaymentCreate, DebtPaymentInDB, DebtSummary,
    MessageResponse,
)
from deps import get_current_active_user, apply_tenant_filter, apply_branch_filter, has_permission

router = APIRouter()


def _recalc_customer_debt(db: Session, customer_id: int):
    """Mijozning total_debt ni barcha ochiq qarzlardan qayta hisoblaydi"""
    total = (
        db.query(func.coalesce(func.sum(CustomerDebt.remaining), 0.0))
        .filter(
            CustomerDebt.customer_id == customer_id,
            CustomerDebt.status.in_(["open", "partial"]),
        )
        .scalar()
    )
    db.query(Customer).filter(Customer.id == customer_id).update({"total_debt": total})


# ── POST /debts/ ─────────────────────────────────────────────────────────────
@router.post("/", response_model=DebtInDB)
def create_debt(
    data: DebtCreate,
    db: Session = Depends(get_db),
    current_user=Depends(has_permission("process_payments")),
):
    customer = (
        apply_tenant_filter(db.query(Customer), Customer, current_user)
        .filter(Customer.id == data.customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(404, "Mijoz topilmadi")

    # Qarz limitini tekshirish
    if customer.credit_limit is not None:
        new_total = customer.total_debt + data.amount
        if new_total > customer.credit_limit:
            raise HTTPException(
                400,
                f"Qarz limiti ({customer.credit_limit:,.0f}) oshib ketdi. "
                f"Joriy qarz: {customer.total_debt:,.0f}",
            )

    debt = CustomerDebt(
        tenant_id=current_user.tenant_id,
        branch_id=getattr(current_user, "_active_branch_id", None),
        customer_id=data.customer_id,
        order_id=data.order_id,
        amount=data.amount,
        paid_amount=0.0,
        remaining=data.amount,
        due_date=data.due_date,
        status="open",
        notes=data.notes,
        user_id=current_user.id,
    )
    db.add(debt)
    db.flush()

    _recalc_customer_debt(db, data.customer_id)
    db.commit()
    db.refresh(debt)
    return debt


# ── GET /debts/ ──────────────────────────────────────────────────────────────
@router.get("/", response_model=List[DebtInDB])
def list_debts(
    customer_id: Optional[int] = None,
    status: Optional[str] = None,        # open|partial|paid
    overdue_only: bool = False,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(has_permission("view_reports")),
):
    q = apply_tenant_filter(db.query(CustomerDebt), CustomerDebt, current_user)

    if customer_id:
        q = q.filter(CustomerDebt.customer_id == customer_id)
    if status:
        q = q.filter(CustomerDebt.status == status)
    if overdue_only:
        q = q.filter(
            CustomerDebt.due_date < date.today(),
            CustomerDebt.status.in_(["open", "partial"]),
        )
    if date_from:
        q = q.filter(CustomerDebt.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(CustomerDebt.created_at <= datetime.combine(date_to, datetime.max.time()))

    q = q.order_by(CustomerDebt.created_at.desc())
    offset = (page - 1) * page_size
    return q.offset(offset).limit(page_size).all()


# ── GET /debts/summary ───────────────────────────────────────────────────────
@router.get("/summary", response_model=DebtSummary)
def debt_summary(
    db: Session = Depends(get_db),
    current_user=Depends(has_permission("view_reports")),
):
    q = apply_tenant_filter(db.query(CustomerDebt), CustomerDebt, current_user)

    open_q = q.filter(CustomerDebt.status.in_(["open", "partial"]))
    total_debt = open_q.with_entities(func.coalesce(func.sum(CustomerDebt.remaining), 0.0)).scalar()

    overdue = (
        q.filter(
            CustomerDebt.due_date < date.today(),
            CustomerDebt.status.in_(["open", "partial"]),
        )
        .with_entities(func.coalesce(func.sum(CustomerDebt.remaining), 0.0))
        .scalar()
    )

    debtors = (
        q.filter(CustomerDebt.status.in_(["open", "partial"]))
        .with_entities(func.count(CustomerDebt.customer_id.distinct()))
        .scalar()
    )

    open_count = q.filter(CustomerDebt.status == "open").count()
    partial_count = q.filter(CustomerDebt.status == "partial").count()

    return DebtSummary(
        total_debtors=debtors or 0,
        total_debt=total_debt or 0.0,
        total_overdue=overdue or 0.0,
        open_count=open_count,
        partial_count=partial_count,
    )


# ── GET /debts/{id} ──────────────────────────────────────────────────────────
@router.get("/{debt_id}", response_model=DebtInDB)
def get_debt(
    debt_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(has_permission("view_reports")),
):
    debt = (
        apply_tenant_filter(db.query(CustomerDebt), CustomerDebt, current_user)
        .filter(CustomerDebt.id == debt_id)
        .first()
    )
    if not debt:
        raise HTTPException(404, "Qarz topilmadi")
    return debt


# ── POST /debts/{id}/pay ─────────────────────────────────────────────────────
@router.post("/{debt_id}/pay", response_model=DebtInDB)
def pay_debt(
    debt_id: int,
    data: DebtPaymentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(has_permission("view_finance")),
):
    debt = (
        apply_tenant_filter(db.query(CustomerDebt), CustomerDebt, current_user)
        .filter(CustomerDebt.id == debt_id)
        .first()
    )
    if not debt:
        raise HTTPException(404, "Qarz topilmadi")
    if debt.status == "paid":
        raise HTTPException(400, "Bu qarz allaqachon to'liq yopilgan")
    if data.amount > debt.remaining + 0.01:
        raise HTTPException(
            400,
            f"To'lov miqdori ({data.amount:,.0f}) qolgan qarzdan "
            f"({debt.remaining:,.0f}) ko'p",
        )

    payment = DebtPayment(
        debt_id=debt_id,
        amount=data.amount,
        payment_method=data.payment_method,
        notes=data.notes,
        user_id=current_user.id,
    )
    db.add(payment)

    debt.paid_amount += data.amount
    debt.remaining = max(0.0, debt.remaining - data.amount)
    if debt.remaining < 0.01:
        debt.remaining = 0.0
        debt.status = "paid"
    elif debt.paid_amount > 0:
        debt.status = "partial"

    _recalc_customer_debt(db, debt.customer_id)
    db.commit()
    db.refresh(debt)
    return debt


# ── GET /customers/{cid}/debts ───────────────────────────────────────────────
@router.get("/customer/{customer_id}", response_model=List[DebtInDB])
def customer_debts(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(has_permission("view_reports")),
):
    customer = (
        apply_tenant_filter(db.query(Customer), Customer, current_user)
        .filter(Customer.id == customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(404, "Mijoz topilmadi")

    return (
        db.query(CustomerDebt)
        .filter(CustomerDebt.customer_id == customer_id)
        .order_by(CustomerDebt.created_at.desc())
        .all()
    )
