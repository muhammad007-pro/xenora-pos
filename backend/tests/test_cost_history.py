"""Tan narx (cost_price) o'zgarishi `price_history` ga yoziladimi.

2026-09-07 gacha tarix FAQAT qo'lda tahrirlashda yozilardi. Prod o'lchovi:
tan narxi ombor kirimi orqali o'zgargan 60 ta mahsulotdan atigi 4 tasining
izi bor edi — ya'ni "bu mahsulotning tan narxi qachon va nega 7000 dan 7500
ga chiqdi" degan savolga bazadan javob yo'q edi.

Bu testlar to'rt narsani qulflaydi:
  1. Avtomatik oqim (ombor kirimi) tan narxni o'zgartirsa — tarixga yoziladi;
  2. O'zgartirmasa — YOZILMAYDI (ortiqcha shovqin bo'lmasin);
  3. FAQAT tan narx o'zgargan holat ham yoziladi (eski shart aynan shuni
     bloklardi — regressiya qaytmasin);
  4. Tarix tenantlar orasida sizmaydi.

Ishga tushirish:
    cd backend && py -m pytest tests/test_cost_history.py -v
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Cafe, Category, Inventory, PriceHistory, Product
from routers.price_history import (
    REASON_MANUAL, REASON_RECIPE, REASON_STOCK_IN, record_price_change,
)
from schemas import StockInCreate


class _User:
    """Minimal foydalanuvchi — endpointni to'g'ridan chaqirish uchun."""
    id = 7
    tenant_id = 1
    is_superuser = False
    _active_branch_id = None


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, autocommit=False, autoflush=False)()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(eng)
        eng.dispose()


def _seed(db, cost=7000.0, price=10000.0, tenant_id=1, pid=1, inv_id=1):
    db.add(Cafe(id=tenant_id, name=f"Do'kon {tenant_id}", code=f"d{tenant_id}",
                business_type="store", is_active=True))
    db.add(Category(id=pid, name="Umumiy", tenant_id=tenant_id))
    db.add(Product(id=pid, name="VERITA 3 TALIK", price=price, cost_price=cost,
                   category_id=pid, tenant_id=tenant_id, is_active=True))
    db.add(Inventory(id=inv_id, tenant_id=tenant_id, product_id=pid,
                     quantity=2, unit="dona"))
    db.commit()


def _add_stock(db, inv_id=1, qty=10, unit_cost=None, user=None):
    import routers.inventory as inv_router
    # `unit_cost` sxemada Optional EMAS — narxsiz kirimni ifodalash uchun
    # maydonni umuman uzatmaymiz (standart qiymati 0 bo'ladi).
    kwargs = {"quantity": qty}
    if unit_cost is not None:
        kwargs["unit_cost"] = unit_cost
    return asyncio.run(inv_router.add_stock(
        inventory_id=inv_id,
        data=StockInCreate(**kwargs),
        db=db, current_user=user or _User(),
    ))


def _hist(db, tenant_id=None):
    q = db.query(PriceHistory)
    if tenant_id is not None:
        q = q.filter(PriceHistory.tenant_id == tenant_id)
    return q.order_by(PriceHistory.id).all()


# ══════════════════════════════════════════════════════════════════════════════
# 1) OMBOR KIRIMI — asosiy yo'l
# ══════════════════════════════════════════════════════════════════════════════

def test_kirim_tan_narxni_ozgartirsa_tarixga_yoziladi(db):
    """7000 -> 7500: bitta yozuv, reason='stock_in', eski/yangi qiymat to'g'ri."""
    _seed(db, cost=7000.0, price=10000.0)
    _add_stock(db, unit_cost=7500.0)

    rows = _hist(db)
    assert len(rows) == 1, f"kutilgan 1 yozuv, bor {len(rows)}"
    r = rows[0]
    assert r.reason == REASON_STOCK_IN
    assert r.old_cost == 7000.0
    assert r.new_cost == 7500.0
    # Sotuv narxi o'zgarmagan — ikkala ustunda ham JORIY narx (NOT NULL)
    assert r.old_price == 10000.0
    assert r.new_price == 10000.0
    assert r.product_id == 1
    assert r.tenant_id == 1
    assert r.changed_by == _User.id
    # Va tan narxning o'zi ham yangilangan (mavjud xulq)
    assert db.query(Product).get(1).cost_price == 7500.0


def test_kirim_tan_narxni_ozgartirmasa_yozuv_yoq(db):
    """Ayni narxda kirim — tarixda shovqin bo'lmasin."""
    _seed(db, cost=7000.0)
    _add_stock(db, unit_cost=7000.0)
    assert _hist(db) == []
    assert db.query(Product).get(1).cost_price == 7000.0


def test_narxsiz_kirim_yozuv_ham_qoldirmaydi(db):
    """unit_cost berilmasa tan narx tegilmaydi → tarix ham bo'sh."""
    _seed(db, cost=7000.0)
    _add_stock(db, unit_cost=None)
    assert _hist(db) == []
    assert db.query(Product).get(1).cost_price == 7000.0


def test_kop_qatorli_kirim_faqat_ozgarganlarni_yozadi(db):
    """Uch kirim: o'zgardi / o'zgarmadi / o'zgardi → 2 yozuv."""
    _seed(db, cost=7000.0)
    _add_stock(db, unit_cost=7500.0)   # +1
    _add_stock(db, unit_cost=7500.0)   # o'zgarmadi
    _add_stock(db, unit_cost=8000.0)   # +1

    rows = _hist(db)
    assert [(r.old_cost, r.new_cost) for r in rows] == [(7000.0, 7500.0), (7500.0, 8000.0)]
    assert all(r.reason == REASON_STOCK_IN for r in rows)


# ══════════════════════════════════════════════════════════════════════════════
# 2) record_price_change — shartning o'zi
# ══════════════════════════════════════════════════════════════════════════════

def test_faqat_tan_narx_ozgarsa_yoziladi(db):
    """⚠️ REGRESSIYA QULFI: eski shart aynan shu holatni bloklardi."""
    _seed(db, cost=7000.0, price=10000.0)
    p = db.query(Product).get(1)

    record_price_change(db, 1, p, None, 7500.0, 7, REASON_MANUAL)
    db.commit()

    rows = _hist(db)
    assert len(rows) == 1
    assert (rows[0].old_cost, rows[0].new_cost) == (7000.0, 7500.0)
    assert rows[0].old_price == rows[0].new_price == 10000.0


def test_faqat_sotuv_narxi_ozgarsa_avvalgidek_yoziladi(db):
    """Mavjud xatti-harakat saqlansin — tan narx tegilmaydi."""
    _seed(db, cost=7000.0, price=10000.0)
    p = db.query(Product).get(1)

    record_price_change(db, 1, p, 12000.0, None, 7, REASON_MANUAL)
    db.commit()

    rows = _hist(db)
    assert len(rows) == 1
    assert (rows[0].old_price, rows[0].new_price) == (10000.0, 12000.0)
    assert rows[0].old_cost == rows[0].new_cost == 7000.0


def test_hech_narsa_ozgarmasa_yozuv_yoq(db):
    _seed(db, cost=7000.0, price=10000.0)
    p = db.query(Product).get(1)
    record_price_change(db, 1, p, 10000.0, 7000.0, 7, REASON_MANUAL)
    record_price_change(db, 1, p, None, None, 7, REASON_MANUAL)
    db.commit()
    assert _hist(db) == []


def test_commit_qilmaydi_chaqiruvchi_bekor_qila_oladi(db):
    """⚠️ Funksiya o'z commit'ini qilmasligi SHART: kirim bekor bo'lsa,
    uning tarixi ham bekor bo'lsin (yarim holat bo'lmasin)."""
    _seed(db, cost=7000.0)
    p = db.query(Product).get(1)
    record_price_change(db, 1, p, None, 7500.0, 7, REASON_STOCK_IN)
    db.rollback()
    assert _hist(db) == []


def test_recipe_sababi_yoziladi(db):
    """Retseptdan avtomatik hisob ham tarixga tushadi (changed_by=None bo'lishi mumkin)."""
    _seed(db, cost=7000.0)
    p = db.query(Product).get(1)
    record_price_change(db, 1, p, None, 9100.0, None, REASON_RECIPE)
    db.commit()

    rows = _hist(db)
    assert len(rows) == 1
    assert rows[0].reason == REASON_RECIPE
    assert rows[0].changed_by is None


# ══════════════════════════════════════════════════════════════════════════════
# 3) TENANT IZOLYATSIYASI
# ══════════════════════════════════════════════════════════════════════════════

def test_tenant_izolyatsiyasi(db):
    """A tenant kirimi B tenant tarixiga tushmasin."""
    _seed(db, cost=7000.0, tenant_id=1, pid=1, inv_id=1)
    _seed(db, cost=5000.0, tenant_id=2, pid=2, inv_id=2)

    class _UserB(_User):
        id = 8
        tenant_id = 2

    _add_stock(db, inv_id=1, unit_cost=7500.0, user=_User())
    _add_stock(db, inv_id=2, unit_cost=5500.0, user=_UserB())

    a = _hist(db, tenant_id=1)
    b = _hist(db, tenant_id=2)
    assert len(a) == 1 and len(b) == 1
    assert a[0].product_id == 1 and a[0].new_cost == 7500.0
    assert b[0].product_id == 2 and b[0].new_cost == 5500.0
    # B ning yozuvi A ning ro'yxatida yo'q
    assert all(r.tenant_id == 1 for r in a)
    assert all(r.tenant_id == 2 for r in b)


# ══════════════════════════════════════════════════════════════════════════════
# 4) GOLDEN — kirim natijasi o'zgarmasin
# ══════════════════════════════════════════════════════════════════════════════

def test_kirim_natijasi_ozgarmadi(db):
    """Qoldiq va cost_price avvalgidek — tarix faqat QO'SHIMCHA."""
    _seed(db, cost=7000.0)
    _add_stock(db, qty=10, unit_cost=7500.0)

    inv = db.query(Inventory).get(1)
    assert inv.quantity == 12          # 2 + 10
    assert db.query(Product).get(1).cost_price == 7500.0
    assert len(_hist(db)) == 1
