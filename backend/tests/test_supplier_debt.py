"""Firma (yetkazib beruvchi) qarzi — GOLDEN testlar. FAZA 1.

MIJOZ ISH OQIMI (Fazza Parfum, 5-6 firma bilan nasiya):

  SSENARIY 1 — tovar + qisman to'lov
    Eski qarz 1 500 000, yangi nakladnoy 1 000 000 keldi, do'konchi 500 000 berdi.
    Qolgan 500 000 eski qarzga qo'shilib, JAMI 2 000 000 bo'lishi kerak.

  SSENARIY 2 — tovarsiz to'lov
    Firma agenti keladi, nakladnoysiz 600 000 olib ketadi.
    2 000 000 - 600 000 = 1 400 000 bo'lishi kerak.

SSENARIY 2 ILGARI BUZUQ EDI (mijozda topildi):
    SupplierPayment.receipt_id.isnot(None)      # suppliers.py:80
Bu filtr nakladnoysiz to'lovni hisobdan TASHLAB YUBORARDI. To'lov saqlanardi va
tarixda ko'rinardi, lekin qarz 2 000 000 bo'lib qolaverardi — do'konchi ikki marta
to'lash xavfi ostida edi. UI esa aynan shu oqimni taklif qiladi
(to'lov oynasidagi birinchi variant — "Umumiy to'lov").

Ishga tushirish:  cd backend && py -m pytest tests/test_supplier_debt.py -v
"""
import asyncio
import os
import sys
from datetime import date as Date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Category, Product, PurchaseReceipt, Supplier, SupplierPayment, SupplierReturn, User,
)
from services.supplier_debt import compute_debts, total_debt

import routers.suppliers as sup_router
import routers.supplier_payments as pay_router

TODAY = Date(2026, 8, 16)


class _User:
    is_superuser = False
    tenant_id = 1
    id = 1
    role = None


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    session = sessionmaker(bind=eng)()
    session.add(Category(id=1, name="Parfum", tenant_id=1))
    session.add(Product(id=1, name="Ayva", price=45000, cost_price=30000,
                        category_id=1, tenant_id=1))
    session.commit()
    yield session
    session.close()


# ── Yordamchilar ─────────────────────────────────────────────────────────────
def _supplier(db, name="Fazza ta'minot", delay=0, sid=1):
    s = Supplier(id=sid, tenant_id=1, name=name, phone="+998901112233",
                 is_active=True, payment_delay_days=delay)
    db.add(s)
    db.commit()
    return s


def _receipt(db, supplier, amount, days_ago=0, status="confirmed", invoice=None):
    rec = PurchaseReceipt(
        tenant_id=1, supplier_id=supplier.id, invoice_number=invoice,
        receipt_date=TODAY - timedelta(days=days_ago),
        total_amount=amount, discount_amount=0, net_amount=amount, status=status,
    )
    db.add(rec)
    db.commit()
    return rec


def _payment(db, supplier, amount, receipt=None, days_ago=0):
    p = SupplierPayment(
        tenant_id=1, supplier_id=supplier.id,
        receipt_id=receipt.id if receipt else None,
        amount=amount, payment_date=TODAY - timedelta(days=days_ago),
        payment_method="cash",
    )
    db.add(p)
    db.commit()
    return p


def _vozvrat(db, supplier, amount, days_ago=0):
    r = SupplierReturn(
        tenant_id=1, supplier_id=supplier.id, product_id=1,
        quantity=1, unit_price=amount, total_amount=amount,
        return_date=TODAY - timedelta(days=days_ago),
    )
    db.add(r)
    db.commit()
    return r


def _debt(db, supplier):
    return compute_debts(db, [supplier], today=TODAY)[supplier.id]


def _summary(db):
    return asyncio.run(sup_router.debt_summary(db=db, current_user=_User()))


# ── GOLDEN: mijozning ikki ssenariysi ────────────────────────────────────────
def test_ssenariy1_tovar_plus_qisman_tolov(db):
    """Eski qarz 1.5M + yangi nakladnoy 1M - 500k to'lov = 2 000 000."""
    s = _supplier(db)
    _receipt(db, s, 1_500_000, days_ago=30)            # eski qarz
    yangi = _receipt(db, s, 1_000_000, days_ago=0)     # yangi nakladnoy
    _payment(db, s, 500_000, receipt=yangi)            # nakladnoyga bog'langan to'lov

    d = _debt(db, s)

    assert d.debt == 2_000_000
    assert d.total_purchases == 2_500_000
    assert d.total_paid == 500_000
    assert d.advance == 0


def test_ssenariy2_tovarsiz_umumiy_tolov(db):
    """1-ssenariy holatidan keyin nakladnoysiz 600k = 1 400 000.

    ILGARI shu yerda 2 000 000 chiqardi — umumiy to'lov hisobga olinmasdi.
    """
    s = _supplier(db)
    _receipt(db, s, 1_500_000, days_ago=30)
    yangi = _receipt(db, s, 1_000_000, days_ago=0)
    _payment(db, s, 500_000, receipt=yangi)
    _payment(db, s, 600_000, receipt=None)             # ← agent tovarsiz keldi

    d = _debt(db, s)

    assert d.debt == 1_400_000
    assert d.total_paid == 1_100_000
    assert d.advance == 0


def test_ssenariy2_endpoint_orqali(db):
    """Xuddi shu son HAQIQIY /debt-summary javobida ham chiqsin (UI shuni o'qiydi)."""
    s = _supplier(db)
    _receipt(db, s, 1_500_000, days_ago=30)
    yangi = _receipt(db, s, 1_000_000, days_ago=0)
    _payment(db, s, 500_000, receipt=yangi)
    _payment(db, s, 600_000, receipt=None)

    rows = _summary(db)

    assert len(rows) == 1
    assert rows[0]["debt"] == 1_400_000
    assert rows[0]["total_paid"] == 1_100_000


# ── FIFO taqsimot ────────────────────────────────────────────────────────────
def test_umumiy_tolov_eng_eski_qarzga_tushadi(db):
    """Bog'lanmagan pul FIFO: avval eng eski nakladnoy yopiladi."""
    s = _supplier(db)
    eski  = _receipt(db, s, 1_500_000, days_ago=30)
    yangi = _receipt(db, s, 1_000_000, days_ago=0)
    _payment(db, s, 500_000, receipt=yangi)
    _payment(db, s, 600_000, receipt=None)

    d = _debt(db, s)
    rows = {r.receipt_id: r for r in d.receipts}

    assert rows[eski.id].remaining == 900_000      # 1.5M - 600k (umumiy to'lov)
    assert rows[yangi.id].remaining == 500_000     # 1M - 500k (bog'langan to'lov)
    assert rows[eski.id].paid == 600_000
    assert rows[yangi.id].paid == 500_000


def test_nakladnoyga_ortiqcha_tolov_boshqasiga_otadi(db):
    """Bitta nakladnoyga ortiqcha to'lansa, ortiqchasi yo'qolmaydi."""
    s = _supplier(db)
    eski  = _receipt(db, s, 1_000_000, days_ago=30)
    yangi = _receipt(db, s, 1_000_000, days_ago=0)
    _payment(db, s, 1_400_000, receipt=yangi)      # 400k ortiqcha

    d = _debt(db, s)
    rows = {r.receipt_id: r for r in d.receipts}

    assert rows[yangi.id].remaining == 0
    assert rows[eski.id].remaining == 600_000      # ortiqcha 400k eskisiga tushdi
    assert d.debt == 600_000


# ── Avans (ortiqcha to'lov) ──────────────────────────────────────────────────
def test_avans_korinadi(db):
    """Jami to'lov xariddan ko'p bo'lsa: debt=0, advance=farq.

    ILGARI `max(0, ...)` avansni jimgina 0 qilardi — pul ko'rinmay ketardi.
    """
    s = _supplier(db)
    _receipt(db, s, 1_000_000, days_ago=10)
    _payment(db, s, 1_600_000, receipt=None)

    d = _debt(db, s)

    assert d.debt == 0
    assert d.advance == 600_000
    assert d.balance == -600_000       # ISHORALI qoldiq


def test_jami_qarz_avansni_boshqa_firmaga_yozmaydi(db):
    """A firmada avans, B firmada qarz — jami qarz B ning qarzi bo'lib qolsin."""
    a = _supplier(db, name="A firma", sid=1)
    b = _supplier(db, name="B firma", sid=2)
    _receipt(db, a, 1_000_000, days_ago=10)
    _payment(db, a, 1_500_000, receipt=None)       # A: 500k avans
    _receipt(db, b, 2_000_000, days_ago=10)        # B: 2M qarz

    assert total_debt(db, [a, b], today=TODAY) == 2_000_000


# ── Draft / vozvrat / muddat ─────────────────────────────────────────────────
def test_draft_nakladnoy_qarzga_kirmaydi(db):
    """Tasdiqlanmagan nakladnoy — tovar omborga kirmagan, qarz ham yo'q."""
    s = _supplier(db)
    _receipt(db, s, 1_000_000, days_ago=5)
    _receipt(db, s, 9_000_000, days_ago=1, status="draft")

    d = _debt(db, s)

    assert d.debt == 1_000_000
    assert d.total_purchases == 1_000_000


def test_vozvrat_qarzni_kamaytiradi(db):
    s = _supplier(db)
    _receipt(db, s, 1_000_000, days_ago=5)
    _vozvrat(db, s, 250_000)

    d = _debt(db, s)

    assert d.debt == 750_000
    assert d.total_returned == 250_000


def test_muddati_otgan_umumiy_tolovdan_keyin_kamayadi(db):
    """Otsrochka 10 kun: eski nakladnoy muddati o'tgan, umumiy to'lov uni yopadi."""
    s = _supplier(db, delay=10)
    _receipt(db, s, 1_000_000, days_ago=30)        # muddati o'tgan
    _receipt(db, s, 1_000_000, days_ago=1)         # hali muddati kelmagan

    assert _debt(db, s).overdue_amount == 1_000_000

    _payment(db, s, 400_000, receipt=None)         # umumiy to'lov -> FIFO eskiga

    d = _debt(db, s)
    assert d.overdue_amount == 600_000
    assert d.debt == 1_600_000


def test_tolov_ochirilsa_qarz_qaytadi(db):
    """To'lov o'chirilsa qarz o'z-o'zidan tiklanadi (taqsimot bazada saqlanmaydi)."""
    s = _supplier(db)
    _receipt(db, s, 1_000_000, days_ago=5)
    p = _payment(db, s, 400_000, receipt=None)
    assert _debt(db, s).debt == 600_000

    db.delete(p)
    db.commit()

    assert _debt(db, s).debt == 1_000_000


def test_qarzsiz_firma_nol(db):
    """Hujjatsiz firma — qulamaydi, hamma raqam nol."""
    s = _supplier(db)
    d = _debt(db, s)
    assert (d.debt, d.advance, d.total_purchases, d.overdue_amount) == (0, 0, 0, 0)


# ── B4: ikki ekran bir xil son ko'rsatsin ────────────────────────────────────
def test_store_dashboard_debt_summary_bilan_bir_xil(db):
    """Direktor paneli va Qarzlar tabi endi bitta servisdan o'qiydi.

    ILGARI store-dashboard `status != "paid"` priyomkalar summasini berardi:
    draftni ham qo'shar, to'lov/vozvratni ayirmasdi -> 9.5M ko'rsatardi.
    """
    import routers.analytics as an

    s = _supplier(db)
    _receipt(db, s, 1_500_000, days_ago=30)
    yangi = _receipt(db, s, 1_000_000, days_ago=0)
    _receipt(db, s, 9_000_000, days_ago=1, status="draft")   # eski formulani buzardi
    _payment(db, s, 500_000, receipt=yangi)
    _payment(db, s, 600_000, receipt=None)

    dash = asyncio.run(an.get_store_dashboard(db=db, current_user=_User()))
    rows = _summary(db)

    assert dash["supplier_debt"] == 1_400_000
    assert dash["supplier_debt"] == sum(r["debt"] for r in rows)


# ── FAZA 2: to'lov tarixi — turi va kim kiritgani ────────────────────────────
def test_tolov_tarixida_turi_va_kim_korinadi(db):
    """Do'konchi agent bilan turganda: nakladnoy uchunmi yoki umumiy pulmi + kim."""
    db.add(User(id=7, tenant_id=1, full_name="Aziz Kassir", phone="+998901234567",
                hashed_password="x"))
    db.commit()
    s = _supplier(db)
    rec = _receipt(db, s, 1_000_000, days_ago=3, invoice="INV-77")

    bogliq = _payment(db, s, 400_000, receipt=rec)
    umumiy = _payment(db, s, 300_000, receipt=None)
    for p in (bogliq, umumiy):
        p.created_by = 7
    db.commit()

    # page/page_size ANIQ beriladi: endpoint to'g'ridan-to'g'ri chaqirilganda
    # FastAPI `Query(...)` default'lari int'ga aylanmaydi.
    res = asyncio.run(pay_router.list_payments(page=1, page_size=50, db=db, current_user=_User()))
    rows = {r.id: r for r in res.items}

    assert rows[bogliq.id].payment_type == "receipt"
    assert rows[bogliq.id].receipt_label == f"Nakladnoy #{rec.id} · INV-77"
    assert rows[umumiy.id].payment_type == "general"
    assert rows[umumiy.id].receipt_label is None
    assert rows[bogliq.id].created_by_name == "Aziz Kassir"


def test_tolov_tarixi_kimsiz_ham_qulamaydi(db):
    """Eski yozuvlarda created_by/user_id bo'lmasligi mumkin — 500 bermasin."""
    s = _supplier(db)
    _payment(db, s, 100_000, receipt=None)

    # page/page_size ANIQ beriladi: endpoint to'g'ridan-to'g'ri chaqirilganda
    # FastAPI `Query(...)` default'lari int'ga aylanmaydi.
    res = asyncio.run(pay_router.list_payments(page=1, page_size=50, db=db, current_user=_User()))

    assert res.total == 1
    assert res.items[0].created_by_name is None
    assert res.items[0].payment_type == "general"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
