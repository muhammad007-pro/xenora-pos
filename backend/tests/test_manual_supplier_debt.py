"""QO'LDA QARZ (priyomkasiz firma qarzi) — GOLDEN + xatti-harakat testlari.

TALAB (Fazza Parfum): do'kon tovar hisobini yuritmaydi, faqat pul oldi-berdi.
Kerak bo'lgani — "falon firmadan 500 000 qarz oldim" deb yozib qo'yish va
keyin to'lovlarni shu qarzga yozish.

YECHIM: `is_manual_debt=True` bilan belgilangan, tasdiqlangan `PurchaseReceipt`
(tovar qatorlarisiz). Ya'ni "summasi bor, tovar taqsimoti yo'q nasiya xarid" —
iqtisodiy ma'noda aynan shu. `compute_supplier_debt()` ga BITTA QATOR ham
qo'shilmadi.

MARKER TARIXI: dastlab "qatori yo'q" deb TAXMIN qilingan edi va u
`test_supplier_debt.py::test_oborot_varagi_xronologik_va_qoldiq` ni buzdi —
o'sha testning fixture'i qatorsiz nakladnoy yaratadi va u jimgina "qo'lda qarz"
bo'lib ko'rindi. Shu sababli aniq ustunga o'tildi (migratsiya 3f7a2c9e1b04).

Shu sababli bu fayldagi BIRINCHI blok — GOLDEN: mavjud qarz mantig'i
(nakladnoy + to'lov + vozvrat + boshlang'ich qarz) o'zgarmaganini qotiradi.

Ishga tushirish:  cd backend && py -m pytest tests/test_manual_supplier_debt.py -v
"""
import asyncio
import os
import sys
from datetime import date as Date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Category, Product, PurchaseReceipt, PurchaseReceiptItem,
    Supplier, SupplierPayment, SupplierReturn,
)
from schemas import ManualDebtCreate, ManualDebtUpdate
from services.supplier_debt import compute_debts, is_manual_debt, supplier_ledger, total_debt

import routers.suppliers as sup

TODAY = Date(2026, 8, 29)


class _User:
    is_superuser = False
    tenant_id = 1
    id = 1
    role = None


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Category(id=1, name="Parfum", tenant_id=1))
    s.add(Product(id=1, name="Ayva", price=45000, cost_price=30000, category_id=1, tenant_id=1))
    s.commit()
    yield s
    s.close()


# ── Yordamchilar ─────────────────────────────────────────────────────────────
def _supplier(db, name="KERASYS", sid=1, delay=0, opening=0):
    s = Supplier(id=sid, tenant_id=1, name=name, is_active=True,
                 payment_delay_days=delay, opening_debt=opening)
    db.add(s); db.commit()
    return s


def _receipt(db, supplier, amount, days_ago=0, status="confirmed", with_item=True):
    """HAQIQIY nakladnoy: `is_manual_debt` qo'yilmaydi (default False)."""
    rec = PurchaseReceipt(
        tenant_id=1, supplier_id=supplier.id,
        receipt_date=TODAY - timedelta(days=days_ago),
        total_amount=amount, discount_amount=0, net_amount=amount, status=status,
    )
    db.add(rec); db.flush()
    if with_item:
        db.add(PurchaseReceiptItem(receipt_id=rec.id, product_id=1, quantity=1,
                                   unit_price=amount, total_price=amount))
    db.commit()
    return rec


def _payment(db, supplier, amount, receipt=None, days_ago=0):
    p = SupplierPayment(tenant_id=1, supplier_id=supplier.id,
                        receipt_id=receipt.id if receipt else None,
                        amount=amount, payment_date=TODAY - timedelta(days=days_ago),
                        payment_method="cash")
    db.add(p); db.commit()
    return p


def _vozvrat(db, supplier, amount, days_ago=0):
    r = SupplierReturn(tenant_id=1, supplier_id=supplier.id, product_id=1, quantity=1,
                       unit_price=amount, total_amount=amount,
                       return_date=TODAY - timedelta(days=days_ago))
    db.add(r); db.commit()
    return r


def _debt(db, s):
    return compute_debts(db, [s], today=TODAY)[s.id]


def _add_manual(db, s, amount, days_ago=0, notes=None):
    return asyncio.run(sup.create_manual_debt(
        supplier_id=s.id,
        data=ManualDebtCreate(amount=amount,
                              debt_date=str(TODAY - timedelta(days=days_ago)),
                              notes=notes),
        db=db, current_user=_User(),
    ))


# ═══════════════════════════════════════════════════════════════════════════
# GOLDEN — mavjud mantiq O'ZGARMAGANI
# ═══════════════════════════════════════════════════════════════════════════
def test_golden_nakladnoy_mantigi_ozgarmadi(db):
    """test_supplier_debt.py dagi ikki ssenariy AYNAN o'sha raqamni beradi."""
    s = _supplier(db)
    _receipt(db, s, 1_500_000, days_ago=30)
    yangi = _receipt(db, s, 1_000_000, days_ago=0)
    _payment(db, s, 500_000, receipt=yangi)

    d = _debt(db, s)
    assert d.debt == 2_000_000
    assert d.total_purchases == 2_500_000
    assert d.total_paid == 500_000
    assert d.advance == 0

    _payment(db, s, 600_000)                      # nakladnoysiz ("umumiy") to'lov
    assert _debt(db, s).debt == 1_400_000


def test_golden_boshlangich_qarz_va_vozvrat_ozgarmadi(db):
    s = _supplier(db, opening=1_000_000, delay=10)
    _receipt(db, s, 400_000, days_ago=2)
    _vozvrat(db, s, 150_000, days_ago=1)
    _payment(db, s, 300_000)

    d = _debt(db, s)
    # 1 000 000 + 400 000 − 150 000 − 300 000 = 950 000
    assert d.debt == 950_000
    assert d.opening_debt == 1_000_000
    assert d.total_returned == 150_000


def test_golden_qolda_qarz_yoq_bolsa_hech_narsa_ozgarmaydi(db):
    """Qo'lda qarz ISHLATILMASA — jami qarz avvalgidek."""
    s = _supplier(db, opening=500_000)
    _receipt(db, s, 250_000, days_ago=3)
    assert total_debt(db, [s], today=TODAY) == 750_000


# ═══════════════════════════════════════════════════════════════════════════
# MARKER
# ═══════════════════════════════════════════════════════════════════════════
def test_marker_oddiy_priyomka_qolda_qarz_emas(db):
    """Qatorli ham, QATORSIZ ham nakladnoy — ustun qo'yilmagan bo'lsa oddiy."""
    s = _supplier(db)
    assert is_manual_debt(_receipt(db, s, 100_000)) is False
    # qatorsiz eski/import yozuv ham JIMGINA qo'lda qarzga aylanmaydi
    assert is_manual_debt(_receipt(db, s, 50_000, with_item=False)) is False


def test_marker_ustun_bilan_belgilanadi(db):
    s = _supplier(db)
    out = _add_manual(db, s, 500_000, notes="Kerasys dan tovar oldim")
    rec = db.query(PurchaseReceipt).filter(PurchaseReceipt.id == out["id"]).first()
    assert rec.is_manual_debt is True       # ANIQ ustun, taxmin emas
    assert is_manual_debt(rec) is True
    assert rec.status == "confirmed"        # darhol qarzga kiradi
    assert rec.items == []                  # ombor tegilmaydi
    assert out["amount"] == 500_000
    assert out["notes"] == "Kerasys dan tovar oldim"


# ═══════════════════════════════════════════════════════════════════════════
# QARZ OSHISHI / FIFO / OBOROT VARAG'I
# ═══════════════════════════════════════════════════════════════════════════
def test_qolda_qarz_qarzni_oshiradi(db):
    s = _supplier(db)
    assert _debt(db, s).debt == 0
    _add_manual(db, s, 500_000)
    assert _debt(db, s).debt == 500_000
    _add_manual(db, s, 300_000)
    assert _debt(db, s).debt == 800_000


def test_tolov_fifo_eng_eski_qarzdan_yopadi(db):
    s = _supplier(db)
    eski = _add_manual(db, s, 500_000, days_ago=10, notes="eski")
    yangi = _add_manual(db, s, 400_000, days_ago=1, notes="yangi")

    _payment(db, s, 600_000)                    # umumiy to'lov
    d = _debt(db, s)
    assert d.debt == 300_000                    # 900 000 − 600 000

    by_id = {r.receipt_id: r for r in d.receipts}
    assert by_id[eski["id"]].remaining == 0          # eskisi TO'LIQ yopildi
    assert by_id[yangi["id"]].remaining == 300_000   # qolgani yangisiga


def test_aralash_nakladnoy_va_qolda_qarz_tartibi(db):
    """Sana bo'yicha FIFO — hujjat turi ahamiyatsiz."""
    s = _supplier(db, opening=200_000)
    qolda_eski = _add_manual(db, s, 300_000, days_ago=20)
    nakladnoy  = _receipt(db, s, 400_000, days_ago=10)
    qolda_yangi = _add_manual(db, s, 100_000, days_ago=1)

    # 200k (opening) + 300k + 400k + 100k = 1 000 000
    assert _debt(db, s).debt == 1_000_000

    _payment(db, s, 550_000)
    d = _debt(db, s)
    assert d.debt == 450_000
    by_id = {r.receipt_id: r for r in d.receipts}
    # opening 200k → qolda_eski 300k → nakladnoyga 50k qoldi
    assert by_id[qolda_eski["id"]].remaining == 0
    assert by_id[nakladnoy.id].remaining == 350_000
    assert by_id[qolda_yangi["id"]].remaining == 100_000


def test_ortiqcha_tolov_avans_boladi(db):
    s = _supplier(db)
    _add_manual(db, s, 200_000)
    _payment(db, s, 350_000)
    d = _debt(db, s)
    assert d.debt == 0
    assert d.advance == 150_000
    assert d.balance == -150_000


def test_oborot_varagida_korinadi(db):
    s = _supplier(db)
    _add_manual(db, s, 500_000, days_ago=5, notes="Kerasys dan tovar oldim")
    _payment(db, s, 200_000, days_ago=2)

    led = supplier_ledger(db, s)
    kinds = [e.kind for e in led]
    assert "manual_debt" in kinds
    row = next(e for e in led if e.kind == "manual_debt")
    assert row.amount == 500_000
    assert "Qo'lda qarz" in row.label
    assert "Kerasys dan tovar oldim" in row.label
    assert row.date is not None                  # opening'dan farqli — sanasi bor


def test_invariant_ledger_oxirgi_balans_debt_summary_bilan_mos(db):
    """Avval sinalgan kafolat: oxirgi qator balansi == d.balance."""
    s = _supplier(db, opening=150_000)
    _add_manual(db, s, 500_000, days_ago=7)
    _receipt(db, s, 250_000, days_ago=4)
    _payment(db, s, 300_000, days_ago=2)
    _vozvrat(db, s, 50_000, days_ago=1)

    led = supplier_ledger(db, s)
    d = _debt(db, s)
    assert led[-1].balance == d.balance
    # 150k + 500k + 250k − 300k − 50k = 550 000
    assert d.balance == 550_000


# ═══════════════════════════════════════════════════════════════════════════
# TAHRIRLASH / O'CHIRISH
# ═══════════════════════════════════════════════════════════════════════════
def test_tahrirlash_summani_ozgartiradi(db):
    s = _supplier(db)
    out = _add_manual(db, s, 500_000, notes="xato")
    asyncio.run(sup.update_manual_debt(
        debt_id=out["id"],
        data=ManualDebtUpdate(amount=250_000, notes="to'g'irlandi"),
        db=db, current_user=_User(),
    ))
    assert _debt(db, s).debt == 250_000
    rec = db.query(PurchaseReceipt).filter(PurchaseReceipt.id == out["id"]).first()
    assert rec.notes == "to'g'irlandi"
    assert rec.total_amount == 250_000        # net va total birga yangilanadi


def test_ochirish_qarzni_kamaytiradi(db):
    s = _supplier(db)
    out = _add_manual(db, s, 500_000)
    _add_manual(db, s, 100_000)
    assert _debt(db, s).debt == 600_000

    asyncio.run(sup.delete_manual_debt(debt_id=out["id"], db=db, current_user=_User()))
    assert _debt(db, s).debt == 100_000
    assert db.query(PurchaseReceipt).filter(PurchaseReceipt.id == out["id"]).first() is None


def test_bogliq_tolovli_qarz_ochirilmaydi(db):
    """To'lov bog'langan bo'lsa o'chirish TO'SILADI — pul boshqa qarzga sirg'anib
    ketmasin (FIFO uni 'bog'lanmagan' deb qayta taqsimlagan bo'lardi)."""
    s = _supplier(db)
    out = _add_manual(db, s, 500_000)
    rec = db.query(PurchaseReceipt).filter(PurchaseReceipt.id == out["id"]).first()
    _payment(db, s, 200_000, receipt=rec)

    with pytest.raises(HTTPException) as e:
        asyncio.run(sup.delete_manual_debt(debt_id=out["id"], db=db, current_user=_User()))
    assert e.value.status_code == 400
    assert "to'lov" in e.value.detail.lower()


def test_oddiy_nakladnoyni_qarz_endpointi_bilan_ochirib_bolmaydi(db):
    """Qo'riqcha: tovarli hujjatga TEGMAYDI."""
    s = _supplier(db)
    rec = _receipt(db, s, 400_000)
    for fn in (
        lambda: sup.delete_manual_debt(debt_id=rec.id, db=db, current_user=_User()),
        lambda: sup.update_manual_debt(debt_id=rec.id, data=ManualDebtUpdate(amount=1),
                                       db=db, current_user=_User()),
    ):
        with pytest.raises(HTTPException) as e:
            asyncio.run(fn())
        assert e.value.status_code == 400
        assert "nakladnoy" in e.value.detail.lower()
    assert _debt(db, s).debt == 400_000       # tegilmadi


def test_royxat_fifo_qoldigini_qaytaradi(db):
    s = _supplier(db)
    eski = _add_manual(db, s, 500_000, days_ago=5)
    _add_manual(db, s, 200_000, days_ago=1)
    _payment(db, s, 500_000)

    rows = asyncio.run(sup.list_manual_debts(supplier_id=s.id, db=db, current_user=_User()))
    assert len(rows) == 2
    by_id = {r["id"]: r for r in rows}
    assert by_id[eski["id"]]["remaining"] == 0
    assert by_id[eski["id"]]["paid"] == 500_000


def test_begona_tenant_qarziga_tegib_bolmaydi(db):
    """Tenant izolyatsiyasi — boshqa do'konning yozuvi 404."""
    s2 = Supplier(id=99, tenant_id=2, name="Begona", is_active=True, opening_debt=0)
    db.add(s2); db.commit()
    rec = PurchaseReceipt(tenant_id=2, supplier_id=99, receipt_date=TODAY,
                          total_amount=1, discount_amount=0, net_amount=1, status="confirmed")
    db.add(rec); db.commit()

    with pytest.raises(HTTPException) as e:
        asyncio.run(sup.delete_manual_debt(debt_id=rec.id, db=db, current_user=_User()))
    assert e.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Bo'sh priyomka ma'nosiz — oddiy yo'l bilan yaratilmasin
# ═══════════════════════════════════════════════════════════════════════════
def test_qolda_qarz_priyomkalar_royxatida_korinmaydi(db):
    """U nakladnoy EMAS — Priyomkalar ro'yxatida chiqsa do'konchi uni
    "tasdiqlash"/"tahrirlash"ga urinardi. Oddiy nakladnoy esa joyida qoladi."""
    import routers.purchase_receipts as pr

    s = _supplier(db)
    haqiqiy = _receipt(db, s, 400_000)
    qolda   = _add_manual(db, s, 500_000)

    res = asyncio.run(pr.list_receipts(
        supplier_id=None, status=None, date_from=None, date_to=None,
        page=1, page_size=50, db=db, current_user=_User(),
    ))
    ids = [r["id"] for r in res["items"]]
    assert haqiqiy.id in ids
    assert qolda["id"] not in ids
    assert res["total"] == 1
    assert res["items"][0]["is_manual_debt"] is False


def test_bosh_priyomka_rad_etiladi():
    from pydantic import ValidationError
    from schemas import PurchaseReceiptCreate
    with pytest.raises(ValidationError):
        PurchaseReceiptCreate(supplier_id=1, receipt_date="2026-08-29", items=[])
