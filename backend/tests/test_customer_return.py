"""MIJOZ VOZVRATI — BOSQICH A (pul harakati) GOLDEN testlari.

MUAMMO (audit): `POST /returns/{id}/approve` faqat OMBORNI tiklardi va statusni
o'zgartirardi. `refund_method` shunchaki YORLIQ bo'lib qolardi:
  • naqd/karta qaytarishning hech qanday izi yo'q edi (Payment yozilmasdi)
  • nasiyaga (credit) olgan mijozning QARZI kamaymasdi — tovar qaytdi, qarz qoldi

IKKI PARALLEL YO'L: `POST /payments/{id}/refund` ham vozvratni bajaradi va
OMBORNI TIKLAYDI. Ikkalasi bir-biridan bexabar edi -> bir vozvrat ikki yo'ldan
o'tkazilsa ombor IKKI MARTA oshardi. Endi ikkala tomonda ham qo'riqchi bor.

QAROR (egasi tasdiqladi):
  - credit vozvratda qarzdan OSHGAN summa AVANS bo'lib qoladi (naqd qaytarilmaydi)
  - `exchange` UI'dan olib qo'yiladi — alohida kelajakdagi ish

Ishga tushirish:  cd backend && py -m pytest tests/test_customer_return.py -v
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Category, Customer, CustomerDebt, Inventory, Order, OrderItem,
    Payment, Product, Return, StockMovement, User,
)
from schemas import ReturnCreate, ReturnItemCreate

import routers.returns as ret_router
import routers.payment as pay_router


class _User:
    is_superuser = False
    tenant_id = 1
    id = 5
    role = None
    _active_branch_id = None


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Category(id=1, name="Parfum", tenant_id=1))
    s.add(Product(id=1, name="Ayva", price=45000, cost_price=30000,
                  category_id=1, tenant_id=1))
    s.add(Inventory(id=1, tenant_id=1, product_id=1, quantity=10, unit="dona"))
    s.add(User(id=5, tenant_id=1, full_name="Kassir", phone="+998900000005",
               hashed_password="x"))
    s.add(Customer(id=1, tenant_id=1, name="Dilnoza", phone="+998901112233",
                   total_debt=0))
    s.commit()
    yield s
    s.close()


# ── Yordamchilar: 2 dona × 45 000 = 90 000 sotuv ────────────────────────────
def _sale(db, paid_method="cash", qty=2, price=45000.0, oid=1):
    o = Order(id=oid, order_number=f"S{oid}", tenant_id=1, status="completed",
              total_amount=qty * price, discount_amount=0, final_amount=qty * price,
              customer_id=1, created_at=datetime.now(), ingredients_deducted=True)
    db.add(o)
    db.add(OrderItem(order_id=oid, product_id=1, tenant_id=1, quantity=qty,
                     unit_price=price, unit_cost=30000, total_price=qty * price))
    if paid_method:
        db.add(Payment(id=oid * 10, tenant_id=1, order_id=oid, cashier_id=5,
                       amount=qty * price, method=paid_method, status="paid",
                       transaction_id=f"TRX{oid}"))
    db.commit()
    return o


def _debt(db, amount, order_id=1, did=1):
    d = CustomerDebt(id=did, tenant_id=1, customer_id=1, order_id=order_id,
                     amount=amount, paid_amount=0.0, remaining=amount, status="open")
    db.add(d)
    db.query(Customer).filter(Customer.id == 1).update({"total_debt": amount})
    db.commit()
    return d


def _make_return(db, method="cash", qty=1, price=45000.0, order_id=1):
    return ret_router.create_return(
        data=ReturnCreate(
            order_id=order_id, customer_id=1, reason="dislike", refund_method=method,
            items=[ReturnItemCreate(product_id=1, quantity=qty, unit_price=price,
                                    restore_to_inventory=True)],
        ),
        db=db, current_user=_User(),
    )


def _approve(db, ret_id):
    return ret_router.approve_return(return_id=ret_id, db=db, current_user=_User())


def _inv(db):
    return db.query(Inventory).filter(Inventory.id == 1).one().quantity


# ── NAQD/KARTA: refund Payment yoziladi ─────────────────────────────────────
def test_naqd_vozvrat_refund_payment_yozadi(db):
    """Ilgari pul qaytganining hech qanday izi qolmasdi."""
    _sale(db)
    r = _make_return(db, "cash")
    assert db.query(Payment).filter(Payment.amount < 0).count() == 0   # tasdiqlashdan OLDIN

    _approve(db, r.id)

    refunds = db.query(Payment).filter(Payment.amount < 0).all()
    assert len(refunds) == 1
    assert refunds[0].amount == -45000
    assert refunds[0].status == "refunded"
    assert _inv(db) == 11                      # ombor tiklandi (10 + 1)


def test_karta_vozvrati_ham_ishlaydi(db):
    _sale(db, paid_method="card")
    r = _make_return(db, "card")
    _approve(db, r.id)

    ref = db.query(Payment).filter(Payment.amount < 0).one()
    assert ref.amount == -45000
    assert ref.method == "card"                # usul saqlanadi


def test_qisman_vozvratda_asl_tolov_paid_qoladi(db):
    """90 000 dan 45 000 qaytdi -> asl to'lov hamon 'paid' (to'liq emas)."""
    _sale(db)
    r = _make_return(db, "cash")
    _approve(db, r.id)

    asl = db.query(Payment).filter(Payment.id == 10).one()
    assert asl.status == "paid"


# ── NASIYA (credit): mijoz qarzi kamayadi ───────────────────────────────────
def test_nasiya_vozvrati_qarzni_kamaytiradi(db):
    """GOLDEN: tovar qaytdi -> qarz ham kamayishi SHART (ilgari qolib ketardi)."""
    _sale(db, paid_method=None)
    _debt(db, 90000)

    r = _make_return(db, "credit")
    _approve(db, r.id)

    d = db.query(CustomerDebt).filter(CustomerDebt.id == 1).one()
    assert d.remaining == 45000
    assert d.status == "partial"
    assert db.query(Customer).filter(Customer.id == 1).one().total_debt == 45000
    assert _inv(db) == 11


def test_nasiya_vozvrati_qarzdan_oshsa_AVANS(db):
    """Qarz 20 000, vozvrat 45 000 -> qarz 0, 25 000 AVANS (naqd qaytarilmaydi)."""
    _sale(db, paid_method=None)
    _debt(db, 20000)

    r = _make_return(db, "credit")
    _approve(db, r.id)

    yopilgan = db.query(CustomerDebt).filter(CustomerDebt.id == 1).one()
    assert yopilgan.remaining == 0
    assert yopilgan.status == "paid"

    avans = db.query(CustomerDebt).filter(CustomerDebt.remaining < 0).one()
    assert avans.remaining == -25000
    assert "avans" in (avans.notes or "").lower()
    # total_debt MANFIY = avans (firma qarzidagi ishorali qoldiq naqshi)
    assert db.query(Customer).filter(Customer.id == 1).one().total_debt == -25000
    # Naqd qaytarilmadi
    assert db.query(Payment).filter(Payment.amount < 0).count() == 0


def test_nasiya_vozvrati_shu_buyurtma_qarzini_tanlaydi(db):
    """Ikki qarz bor: shu buyurtmaniki AVVAL kamayadi (taxmin qilinmaydi)."""
    _sale(db, paid_method=None, oid=1)
    _debt(db, 50000, order_id=99, did=1)     # boshqa buyurtma (eskiroq)
    _debt(db, 50000, order_id=1,  did=2)     # SHU buyurtma

    r = _make_return(db, "credit")
    _approve(db, r.id)

    boshqa = db.query(CustomerDebt).filter(CustomerDebt.id == 1).one()
    shu    = db.query(CustomerDebt).filter(CustomerDebt.id == 2).one()
    assert shu.remaining == 5000        # 50 000 - 45 000
    assert boshqa.remaining == 50000    # tegilmadi


# ── IKKI PARALLEL YO'L: ombor ikki marta tiklanmasin ────────────────────────
def test_ikki_marta_ombor_tiklanmaydi_payments_avval(db):
    """To'lov qaytarilgan -> Return hujjatini tasdiqlash BLOKLANADI (409)."""
    from fastapi import HTTPException
    _sale(db)
    r = _make_return(db, "cash")

    # 1-yo'l: to'lovni qaytarish (ombor shu yerda tiklanadi)
    pay_router.PaymentService(db)   # import ishlashini tasdiqlash
    p = db.query(Payment).filter(Payment.id == 10).one()
    p.status = "refunded"
    db.commit()

    with pytest.raises(HTTPException) as e:
        _approve(db, r.id)
    assert e.value.status_code == 409
    assert "qaytarilgan" in e.value.detail.lower()
    assert _inv(db) == 10           # ombor IKKI MARTA oshmadi


def test_return_hujjati_borida_tolov_qaytarish_bloklanadi(db):
    """Teskari tomon: hujjat bor -> /payments/{id}/refund 409 beradi."""
    import asyncio
    from fastapi import HTTPException
    _sale(db)
    _make_return(db, "cash")        # pending holatda ham qo'riqlaydi

    with pytest.raises(HTTPException) as e:
        asyncio.run(pay_router.refund_payment(
            payment_id=10, amount=None, reason=None, db=db, current_user=_User()))
    assert e.value.status_code == 409
    assert "qaytarish hujjati" in e.value.detail.lower()


def test_ikki_marta_tasdiqlab_bolmaydi(db):
    """Idempotentlik: tasdiqlangan hujjat qayta tasdiqlanmaydi."""
    from fastapi import HTTPException
    _sale(db)
    r = _make_return(db, "cash")
    _approve(db, r.id)
    assert _inv(db) == 11

    with pytest.raises(HTTPException) as e:
        _approve(db, r.id)
    assert e.value.status_code == 400
    assert _inv(db) == 11           # ombor o'zgarmadi


# ── REGRESSIYA: mavjud xulq buzilmasin ──────────────────────────────────────
def test_ombor_va_harakat_yozuvi_avvalgidek(db):
    """StockMovement (B6 naqshi) va ombor tiklash o'zgarmagan."""
    _sale(db)
    r = _make_return(db, "cash")
    _approve(db, r.id)

    mv = db.query(StockMovement).filter(StockMovement.product_id == 1).all()
    assert len(mv) == 1
    assert mv[0].quantity == 1
    assert _inv(db) == 11


def test_buyurtmasiz_naqd_vozvrat_qulamaydi(db):
    """order_id yo'q vozvrat — qaytariladigan to'lov ham yo'q, xato bermasin."""
    r = ret_router.create_return(
        data=ReturnCreate(
            order_id=None, customer_id=1, reason="broken", refund_method="cash",
            items=[ReturnItemCreate(product_id=1, quantity=1, unit_price=45000)],
        ),
        db=db, current_user=_User(),
    )
    out = _approve(db, r.id)

    assert out.status == "approved"
    assert db.query(Payment).count() == 0
    assert _inv(db) == 11


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
