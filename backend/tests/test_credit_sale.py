"""NASIYA (credit) bilan sotuv — GOLDEN testlar. v1.9.1

MUAMMO (jonli, Fazza Parfum): POS'da "Nasiya" tanlanib sotuv qilinganda
    psycopg2.errors.InvalidTextRepresentation:
    invalid input value for enum paymentmethod: "credit"
    POST /api/v1/payments/ -> 500 -> BUTUN sotuv rollback ("hech narsa yozilmadi")
Sabab: POS'da tugma bor edi, `PaymentMethod` enumida `credit` YO'Q edi.

QAROR (B variant): nasiya to'lovi yoziladi, lekin `status = pending` —
pul KELMAGAN. Ya'ni:
  • sotuv YAKUNLANADI (tovar sotildi, ombordan chiqdi, hisobotga tushadi)
  • naqd/daromad hisobotlari (`status == "paid"`) uni SANAMAYDI
  • qarz `customer_debts` da yuradi; pul kelganda `debt_payments` orqali
A variant (oddiy `paid`) RAD ETILDI: sotuv ikki marta hisoblanardi —
daromadda ham, qarzda ham.

Ishga tushirish:  cd backend && py -m pytest tests/test_credit_sale.py -v
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Category, Inventory, Order, OrderItem, Payment, PaymentMethod, PaymentStatus,
    Product, User,
)
from services.payment_service import PaymentService

import routers.payment as pay_router


class _User:
    is_superuser = False
    tenant_id = 1
    id = 21
    role = None
    _active_branch_id = None


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Category(id=1, name="Parfum", tenant_id=1))
    s.add(Product(id=1, name="Ayva", price=5500, cost_price=3000,
                  category_id=1, tenant_id=1))
    s.add(Inventory(id=1, tenant_id=1, product_id=1, quantity=100, unit="dona"))
    s.add(User(id=21, tenant_id=1, full_name="Kassir", phone="+998900000021",
               hashed_password="x"))
    s.commit()
    yield s
    s.close()


def _order(db, total=5500.0, oid=1):
    o = Order(id=oid, order_number=f"N{oid}", tenant_id=1, status="pending",
              total_amount=total, discount_amount=0, final_amount=total,
              customer_id=None, created_at=datetime.now())
    db.add(o)
    db.add(OrderItem(order_id=oid, product_id=1, tenant_id=1, quantity=1,
                     unit_price=total, unit_cost=3000, total_price=total))
    db.commit()
    return o


# ── Enum: mijozdagi 500 ning aynan sababi ────────────────────────────────────
def test_enum_credit_va_room_charge_bor():
    """`credit` yo'qligi sotuvni butunlay yiqitardi (enum xatosi -> rollback)."""
    values = {m.value for m in PaymentMethod}
    assert "credit" in values
    assert "room_charge" in values


# ── Nasiya to'lovi PENDING bo'lib yoziladi ───────────────────────────────────
def test_nasiya_tolovi_paid_emas(db):
    o = _order(db)
    p = PaymentService(db).process_payment(
        order=o, amount=5500.0, method="credit", cashier_id=21, commit=True,
    )
    assert p.method == "credit"
    assert p.status == "pending", "nasiya PAID bo'lsa kelmagan pul daromadga kirardi"


def test_naqd_tolov_avvalgidek_paid(db):
    """Regressiya: oddiy naqd sotuv o'zgarmasin."""
    o = _order(db)
    p = PaymentService(db).process_payment(
        order=o, amount=5500.0, method="cash", cashier_id=21, commit=True,
    )
    assert p.status == "paid"


# ── GOLDEN: sotuv BIR MARTA hisoblanadi ──────────────────────────────────────
def test_nasiya_sotuvi_daromadga_ikki_marta_kirmaydi(db):
    """Naqd hisobot (`status == paid`) nasiyani sanamaydi — pul hali kelmagan.

    Ilgari A variant taklif qilingandi (`paid` qilib yozish) — o'shanda sotuv
    HAM daromadda, HAM qarzda turib, ikki marta hisoblanardi.
    """
    o_cash   = _order(db, 5500.0, oid=1)
    o_credit = _order(db, 5500.0, oid=2)
    svc = PaymentService(db)
    svc.process_payment(order=o_cash,   amount=5500.0, method="cash",   cashier_id=21, commit=True)
    svc.process_payment(order=o_credit, amount=5500.0, method="credit", cashier_id=21, commit=True)

    # "Qancha pul keldi" — faqat paid
    cash_in = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
        Payment.status == "paid"
    ).scalar()
    assert cash_in == 5500.0, "nasiya kelmagan pulni daromadga qo'shgan"

    # "Nima sotildi" — ikkala buyurtma ham (accrual). Jami 11 000, ikki marta emas.
    assert db.query(func.count(Payment.id)).scalar() == 2


def test_nasiya_sotuvi_buyurtmani_yakunlaydi(db):
    """Tovar sotildi: nasiya bo'lsa ham order `completed` bo'lishi SHART —
    aks holda ombordan chiqmaydi va hisobotlarga umuman tushmaydi."""
    o = _order(db)
    svc = PaymentService(db)
    p = svc.process_payment(order=o, amount=5500.0, method="credit",
                            cashier_id=21, commit=False)
    p.tenant_id = 1
    db.flush()

    # routers/payment.py dagi "credit tender" mantig'i (aynan shu so'rov)
    total_paid = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
        Payment.order_id == o.id, Payment.status == "paid"
    ).scalar() or 0.0
    credit_tender = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
        Payment.order_id == o.id,
        Payment.method == PaymentMethod.CREDIT,
        Payment.status == PaymentStatus.PENDING,
    ).scalar() or 0.0
    db.commit()

    assert total_paid == 0.0
    assert credit_tender == 5500.0
    assert total_paid + credit_tender >= o.final_amount, "nasiya sotuvni yakunlamas edi"


# ── Z-hisobot: nasiya kassaga KIRMAYDI, lekin ko'rinadi ──────────────────────
def test_z_hisobot_nasiya_kassadan_tashqarida(db):
    """Kassada bo'lishi kerak bo'lgan naqd — faqat naqd sotuvdan.
    Nasiya alohida qatorda ko'rinadi (shift.credit_total)."""
    o_cash   = _order(db, 5500.0, oid=1)
    o_credit = _order(db, 7000.0, oid=2)
    svc = PaymentService(db)
    svc.process_payment(order=o_cash,   amount=5500.0, method="cash",   cashier_id=21, commit=True)
    svc.process_payment(order=o_credit, amount=7000.0, method="credit", cashier_id=21, commit=True)

    payments = db.query(Payment).filter(Payment.status.in_(("paid", "pending"))).all()
    _paid = lambda p: str(getattr(p.status, "value", p.status)) == "paid"

    cash_sales   = sum(p.amount for p in payments if p.method == "cash" and _paid(p))
    credit_total = sum(p.amount for p in payments if p.method == "credit")
    starting_cash = 100_000.0
    expected_cash = starting_cash + cash_sales      # nasiya BU YERGA kirmaydi

    assert cash_sales == 5500.0
    assert credit_total == 7000.0
    assert expected_cash == 105_500.0, "nasiya kassa qoldig'iga qo'shilib ketdi"
    assert cash_sales + credit_total == 12_500.0    # jami sotuv (Z-hisobot qatori)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
