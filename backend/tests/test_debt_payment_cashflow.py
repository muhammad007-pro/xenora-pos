"""NASIYA QARZI TO'LOVI — kassa oqimi (cash flow) GOLDEN testlari.

MUAMMO: mijoz nasiya qarzini NAQD to'laganda pul kassa yashigiga jismonan
tushardi, lekin `routers/debt.py` faqat `DebtPayment` yozadi — `Payment` EMAS.
Z-hisobotdagi `cash_sales` esa `Payment` dan hisoblanadi, ya'ni bu pul
`expected_cash` ga umuman kirmasdi:

    shortage = counted_cash − expected_cash  ->  MUSBAT "ortiqcha"

Ya'ni bu "ko'rinmaydi" emas — kassa farqini FAOL buzadigan xato edi.

ENG MUHIM QOIDA (ikki marta hisoblashning oldini olish):
qarz to'lovi SOTUV EMAS. Tovar o'z kunida sotilgan va accrual hisobotlarda
(`utils/revenue.py`, store-dashboard `today_revenue`) allaqachon hisoblangan.
Shu sabab qarz to'lovi FAQAT kassa oqimiga qo'shiladi, `total_sales` ga EMAS.

Ishga tushirish:  cd backend && py -m pytest tests/test_debt_payment_cashflow.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Customer, CustomerDebt, DebtPayment, Order, OrderItem,
    Payment, Product, Category, Shift, User,
)
import routers.shift as shift_router
from utils.cashflow import debt_payments_totals, expected_cash


class _User:
    """Tenant 1 kassiri (superuser EMAS — tenant filtri haqiqatan ishlasin)."""
    is_superuser = False
    tenant_id = 1
    id = 5
    role = None
    _active_branch_id = None


class _OtherTenantUser(_User):
    tenant_id = 2
    id = 9


NOW   = datetime.now()
START = NOW - timedelta(hours=8)


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    # `Cafe` yozuvi ATAYLAB yaratilmaydi: `close_shift` uni `if cafe else None`
    # bilan o'qiydi, tenant filtri esa faqat `tenant_id` sonini solishtiradi.
    # (SQLite'da FK majburlanmaydi — testni ortiqcha ustunlarga bog'lamaymiz.)
    s.add(Category(id=1, name="Parfum", tenant_id=1))
    s.add(Product(id=1, name="Ayva", price=50000, cost_price=30000, category_id=1, tenant_id=1))
    s.add(User(id=5, tenant_id=1, full_name="Kassir", phone="+998900000005", hashed_password="x"))
    s.add(Customer(id=1, tenant_id=1, name="Dilnoza", phone="+998901112233", total_debt=0))
    s.add(Customer(id=2, tenant_id=2, name="Begona", phone="+998905556677", total_debt=0))
    s.commit()
    yield s
    s.close()


def _shift(db, starting_cash=0.0):
    sh = Shift(id=1, tenant_id=1, user_id=5, start_time=START, starting_cash=starting_cash)
    db.add(sh)
    db.commit()
    return sh


def _cash_sale(db, shift_id, amount=100000.0, oid=1):
    """Naqd sotuv: Order + paid Payment (Z-hisobot `cash_sales` shu yerdan)."""
    db.add(Order(id=oid, order_number=f"S{oid}", tenant_id=1, status="completed",
                 shift_id=shift_id, total_amount=amount, discount_amount=0,
                 final_amount=amount, created_at=NOW - timedelta(hours=2)))
    db.add(OrderItem(order_id=oid, product_id=1, tenant_id=1, quantity=2,
                     unit_price=amount / 2, unit_cost=30000, total_price=amount))
    db.add(Payment(id=oid * 10, tenant_id=1, order_id=oid, cashier_id=5, amount=amount,
                   method="cash", status="paid", transaction_id=f"TRX{oid}",
                   created_at=NOW - timedelta(hours=2)))
    db.commit()


def _debt_payment(db, amount, method="cash", tenant_id=1, customer_id=1,
                  did=1, pid=1, when=None):
    """Nasiya qarzi + unga to'lov. `when` — to'lov vaqti (smena ichida/tashqarisida)."""
    if not db.query(CustomerDebt).filter(CustomerDebt.id == did).first():
        db.add(CustomerDebt(id=did, tenant_id=tenant_id, customer_id=customer_id,
                            amount=amount, paid_amount=0.0, remaining=amount,
                            status="open", created_at=START - timedelta(days=3)))
        db.commit()
    db.add(DebtPayment(id=pid, debt_id=did, amount=amount, payment_method=method,
                       user_id=5, created_at=when or (NOW - timedelta(hours=1))))
    db.commit()


def _close(db, counted_cash, user=None):
    return asyncio.run(shift_router.close_shift(
        shift_id=1, counted_cash=counted_cash, notes=None,
        db=db, current_user=user or _User(),
    ))


# ── GOLDEN: naqd sotuv 100 000 + naqd qarz to'lovi 5 000 -> 105 000 ─────────
def test_GOLDEN_naqd_qarz_tolovi_expected_cash_ga_qoshiladi(db):
    _shift(db)
    _cash_sale(db, shift_id=1, amount=100000)
    _debt_payment(db, 5000, method="cash")

    z = _close(db, counted_cash=105000)

    # ILGARI: 100 000 chiqardi va 5 000 "ortiqcha" bo'lib ko'rinardi
    assert z["expected_cash"] == 105000
    assert z["shortage"] == 0
    assert z["shortage_type"] == "mos"
    assert z["debt_paid_cash"] == 5000
    assert z["debt_paid_count"] == 1


def test_GOLDEN_qarz_tolovi_SOTUVGA_qoshilmaydi(db):
    """Ikki marta hisoblashning oldi: tovar o'z kunida sotilgan."""
    _shift(db)
    _cash_sale(db, shift_id=1, amount=100000)
    _debt_payment(db, 5000, method="cash")

    z = _close(db, counted_cash=105000)

    assert z["cash_sales"] == 100000      # sotuv o'zgarmadi
    assert z["total_sales"] == 100000     # qarz to'lovi JAMI SAVDOga kirmadi
    assert z["expected_cash"] == 105000   # lekin kassaga tushdi


# ── KARTA bilan to'langan qarz kassa yashigiga tushmaydi ───────────────────
def test_karta_qarz_tolovi_expected_cash_ga_KIRMAYDI(db):
    _shift(db)
    _cash_sale(db, shift_id=1, amount=100000)
    _debt_payment(db, 7000, method="card")

    z = _close(db, counted_cash=100000)

    assert z["expected_cash"] == 100000   # yashikda o'zgarish yo'q
    assert z["shortage"] == 0
    assert z["debt_paid_card"] == 7000    # lekin hisobotda ko'rinadi
    assert z["debt_paid_cash"] == 0


# ── TENANT IZOLYATSIYASI: boshqa do'konning puli qo'shilmasin ──────────────
def test_GOLDEN_boshqa_tenant_qarz_tolovi_QOSHILMAYDI(db):
    """`DebtPayment` da `tenant_id` YO'Q — himoya CustomerDebt join'iga bog'liq."""
    _shift(db)
    _cash_sale(db, shift_id=1, amount=100000)
    _debt_payment(db, 5000, method="cash")                                    # bizniki
    _debt_payment(db, 999000, method="cash", tenant_id=2, customer_id=2,
                  did=2, pid=2)                                               # BEGONA

    z = _close(db, counted_cash=105000)

    assert z["debt_paid_cash"] == 5000        # begona 999 000 kirmadi
    assert z["expected_cash"] == 105000
    assert z["shortage"] == 0

    # Boshqa tenant o'zinikini ko'radi, biznikini emas
    other = debt_payments_totals(db, _OtherTenantUser(), START, NOW)
    assert other["cash"] == 999000
    assert other["count"] == 1


# ── VAQT: smenadan TASHQARIDAGI to'lov kirmasin ────────────────────────────
def test_smenadan_tashqaridagi_tolov_kirmaydi(db):
    _shift(db)
    _cash_sale(db, shift_id=1, amount=100000)
    _debt_payment(db, 5000, method="cash", when=START - timedelta(days=1))

    z = _close(db, counted_cash=100000)

    assert z["debt_paid_cash"] == 0
    assert z["expected_cash"] == 100000


# ── ACCRUAL REGRESSIYA: sotuv hisobotlari o'zgarmasin ──────────────────────
def test_REGRESSIYA_accrual_sotuv_ozgarmaydi(db):
    """Qarz to'lovi accrual (sotuv/foyda) tomoniga TEGMASLIGI kerak."""
    _shift(db)
    _cash_sale(db, shift_id=1, amount=100000)

    # store-dashboard `today_revenue` naqshi: Order.final_amount (completed)
    def accrual_revenue():
        return sum(o.final_amount or 0 for o in db.query(Order)
                   .filter(Order.tenant_id == 1, Order.status == "completed").all())

    before = accrual_revenue()
    _debt_payment(db, 5000, method="cash")
    after = accrual_revenue()

    assert before == after == 100000     # qarz to'lovi accrual'ga TEGMADI


# ── Sof funksiya: formula ──────────────────────────────────────────────────
@pytest.mark.parametrize("start,sales,refunds,debt,kutilgan", [
    (0,      100000, 0,     5000, 105000),   # golden holat
    (50000,  100000, 0,     5000, 155000),   # boshlang'ich naqd bilan
    (0,      100000, 20000, 5000,  85000),   # naqd qaytarish ayiriladi
    (0,      0,      0,     5000,   5000),   # faqat qarz to'lovi
    (0,      100000, 0,     0,    100000),   # qarz to'lovi yo'q — eski xatti-harakat
])
def test_expected_cash_formulasi(start, sales, refunds, debt, kutilgan):
    assert expected_cash(start, sales, refunds, debt) == kutilgan


# ── Kirish validatsiyasi (2-bosqich) ───────────────────────────────────────
def test_qarz_tolovi_usuli_validatsiyasi():
    from pydantic import ValidationError
    from schemas import DebtPaymentCreate

    assert DebtPaymentCreate(amount=1, payment_method="  CASH ").payment_method == "cash"
    for bad in ("credit", "bank", ""):
        with pytest.raises(ValidationError):
            DebtPaymentCreate(amount=1, payment_method=bad)
