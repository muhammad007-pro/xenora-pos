"""QAYTARISHNI YAKUNLASH — tan narx snapshot'i va lookup birligi.

Ikki narsani qulflaydi:

1. ⚠️ TAN NARX SNAPSHOT (`order_item_id` bo'lganda). `return_cost_expr()`
   sotuv PAYTIDAGI `OrderItem.unit_cost` ni ishlatishi SHART, mahsulotning
   BUGUNGI `cost_price` ini EMAS.

   NEGA MUHIM: tan narx vaqt o'tib o'zgaradi (yangi kelim boshqa narxda
   keladi). Agar vozvrat bugungi tan narxga tayansa, foyda hisoboti sotuv va
   vozvratni HAR XIL tan narx bilan ko'rib, farqni "foyda"/"zarar" deb
   ko'rsatardi — pul yo'q joydan paydo bo'lardi. Mavjud testlar
   (`test_profit_p0_fixes.py` P0-2) birlik MOSLIGINI tekshiradi, lekin
   ularda `cost_price` sotuvdagi qiymatga mos — ya'ni snapshot ishlatilgani
   ISBOTLANMAYDI. Bu yerda `cost_price` ATAYLAB o'zgartirilgan.

2. `GET /returns/lookup` javobida `sale_unit` bo'lishi. Frontend "SUMMA
   bo'yicha qaytarish" rejimini FAQAT bo'linadigan birlikda (kg/g/l/litr,
   ml/dl/cl) ko'rsatadi — birlik kelmasa rejim hech qachon chiqmaydi.

Ishga tushirish:  cd backend && py -m pytest tests/test_returns_finalize.py -v
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
    Category, Inventory, Order, OrderItem, Product, Return, ReturnItem, User,
)
from utils.revenue import returns_totals

import routers.returns as ret_router

TID = 1
DAVR = (datetime(2026, 10, 1), datetime(2026, 10, 31))


class _User:
    is_superuser = False
    tenant_id = TID
    id = 5
    role = None
    _active_branch_id = None


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Category(id=1, name="Oziq-ovqat", tenant_id=TID))
    # SHAKAR — kg. Sotuvda 1 kg tan narx 8 000 edi.
    s.add(Product(id=1, name="SHAKAR", price=12000, cost_price=8000,
                  sale_unit="kg", category_id=1, tenant_id=TID))
    # GUPKA — dona + pachka
    s.add(Product(id=2, name="GUPKA", price=3000, cost_price=2000,
                  sale_unit="pcs", pack_size=8, pack_price=20000,
                  category_id=1, tenant_id=TID))
    s.add(Inventory(id=1, tenant_id=TID, product_id=1, quantity=100, unit="kg"))
    s.add(Inventory(id=2, tenant_id=TID, product_id=2, quantity=100, unit="dona"))
    s.add(User(id=5, tenant_id=TID, full_name="Kassir",
               phone="+998900000005", hashed_password="x"))
    s.commit()
    yield s
    s.close()


def _sotuv(db, *, oi_id=1, product_id=1, qty=2.0, unit_price=12000.0,
           unit_cost=8000.0, unit_sold=None, base_qty=None, oid=1):
    db.add(Order(id=oid, order_number=f"CHK{oid:05d}", daily_number=oid,
                 tenant_id=TID, status="completed",
                 total_amount=qty * unit_price, discount_amount=0,
                 final_amount=qty * unit_price,
                 created_at=datetime(2026, 10, 2, 12, 0)))
    db.add(OrderItem(id=oi_id, order_id=oid, product_id=product_id, tenant_id=TID,
                     quantity=qty, unit_price=unit_price, unit_cost=unit_cost,
                     unit_sold=unit_sold,
                     base_qty=base_qty if base_qty is not None else qty,
                     total_price=qty * unit_price))
    db.commit()


def _vozvrat(db, *, oi_id, qty, unit_price, base_qty=None, product_id=1, rid=1):
    db.add(Return(id=rid, return_number=f"RET{rid}", tenant_id=TID, order_id=1,
                  status="approved", total_amount=qty * unit_price,
                  refund_method="cash",
                  created_at=datetime(2026, 10, 3, 12, 0),
                  approved_at=datetime(2026, 10, 3, 12, 0)))
    db.flush()
    db.add(ReturnItem(return_id=rid, product_id=product_id, order_item_id=oi_id,
                      quantity=qty,
                      base_qty=base_qty if base_qty is not None else qty,
                      unit_price=unit_price, total=qty * unit_price))
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# 1. TAN NARX SNAPSHOT — sotuvdagi `unit_cost`, bugungi `cost_price` EMAS
# ═══════════════════════════════════════════════════════════════════════════
def test_tan_narx_SOTUVDAGI_snapshot_dan(db):
    """Sotuvda 1 kg tan narx 8 000 edi; keyin 15 000 ga ko'tarildi.

    2 kg qaytarilsa tan narx 2 × 8 000 = 16 000 bo'lishi SHART.
    Bugungi narx bilan 2 × 15 000 = 30 000 chiqardi — 14 000 "zarar"
    yo'q joydan paydo bo'lardi."""
    _sotuv(db, qty=2.0, unit_price=12000.0, unit_cost=8000.0)

    # Tan narx SOTUVDAN KEYIN o'zgardi (yangi kelim qimmat keldi)
    db.query(Product).filter(Product.id == 1).first().cost_price = 15000
    db.commit()

    _vozvrat(db, oi_id=1, qty=2.0, unit_price=12000.0)

    ret = returns_totals(db, _User(), *DAVR)
    assert ret["revenue"] == 24000
    assert ret["cost"] == 16000, "sotuvdagi unit_cost (8 000) ishlatilishi shart"
    assert ret["cost"] != 30000, "bugungi cost_price ishlatilgan — XATO"


def test_tan_narx_snapshot_tan_narx_TUSHGANDA_ham(db):
    """Teskari yo'nalish: tan narx TUSHSA ham sotuvdagi qiymat ishlatiladi."""
    _sotuv(db, qty=1.0, unit_price=12000.0, unit_cost=8000.0)
    db.query(Product).filter(Product.id == 1).first().cost_price = 3000
    db.commit()
    _vozvrat(db, oi_id=1, qty=1.0, unit_price=12000.0)

    ret = returns_totals(db, _User(), *DAVR)
    assert ret["cost"] == 8000
    assert ret["cost"] != 3000


def test_tan_narx_kasrli_miqdorda(db):
    """Og'irlik vozvrati: 0.5 kg × 8 000 = 4 000."""
    _sotuv(db, qty=2.0, unit_price=12000.0, unit_cost=8000.0)
    db.query(Product).filter(Product.id == 1).first().cost_price = 15000
    db.commit()
    _vozvrat(db, oi_id=1, qty=0.5, unit_price=12000.0)

    ret = returns_totals(db, _User(), *DAVR)
    assert ret["cost"] == 4000


def test_tan_narx_pachka_snapshot(db):
    """Pachka: `unit_cost` = dona_cost × pack_size (sotuv birligida).

    1 pachka qaytarilsa 1 × 16 000 (= 2 000 × 8). `base_qty` (8 dona) ga
    ko'paytirilsa 128 000 chiqardi — 8 BAROBAR shishgan."""
    _sotuv(db, oi_id=2, product_id=2, qty=1.0, unit_price=20000.0,
           unit_cost=16000.0, unit_sold="pachka", base_qty=8.0)
    db.query(Product).filter(Product.id == 2).first().cost_price = 9999
    db.commit()
    _vozvrat(db, oi_id=2, qty=1.0, unit_price=20000.0, base_qty=8.0, product_id=2)

    ret = returns_totals(db, _User(), *DAVR)
    assert ret["cost"] == 16000


def test_order_item_id_YOQ_bolsa_cost_price_ga_tushadi(db):
    """GOLDEN: qo'lda kiritilgan vozvrat (sotuvga bog'lanmagan) — mavjud
    zaxira yo'l. `cost_price` BAZA birligida → `base_qty` ga ko'paytiriladi."""
    db.add(Return(id=9, return_number="RET9", tenant_id=TID, order_id=None,
                  status="approved", total_amount=12000, refund_method="cash",
                  created_at=datetime(2026, 10, 3, 12, 0),
                  approved_at=datetime(2026, 10, 3, 12, 0)))
    db.flush()
    db.add(ReturnItem(return_id=9, product_id=1, order_item_id=None,
                      quantity=1.0, base_qty=1.0, unit_price=12000, total=12000))
    db.commit()

    ret = returns_totals(db, _User(), *DAVR)
    assert ret["cost"] == 8000      # mahsulotning joriy cost_price


def test_snapshot_nol_bolsa_cost_price_ga_tushadi(db):
    """`unit_cost = 0` (eski yozuvlar) → `NULLIF` fallback ishlaydi."""
    _sotuv(db, qty=1.0, unit_price=12000.0, unit_cost=0.0)
    _vozvrat(db, oi_id=1, qty=1.0, unit_price=12000.0)

    ret = returns_totals(db, _User(), *DAVR)
    assert ret["cost"] == 8000      # cost_price × base_qty


# ═══════════════════════════════════════════════════════════════════════════
# 2. LOOKUP — `sale_unit` (SUMMA rejimi uchun) va narx SOTUVDAN
# ═══════════════════════════════════════════════════════════════════════════
def test_lookup_sale_unit_qaytaradi(db):
    _sotuv(db, qty=2.0, unit_price=12000.0)
    out = ret_router.lookup_order(q="CHK00001", db=db, current_user=_User())
    it = out["items"][0]
    assert it["sale_unit"] == "kg"


def test_lookup_dona_mahsulotda_ham_birlik_keladi(db):
    """Dona mahsulotda ham maydon bor — frontend shunga qarab SUMMA rejimini
    KO'RSATMAYDI (yo'qligi bilan emas, qiymati bilan qaror qiladi)."""
    _sotuv(db, oi_id=2, product_id=2, qty=3.0, unit_price=3000.0)
    out = ret_router.lookup_order(q="CHK00001", db=db, current_user=_User())
    assert out["items"][0]["sale_unit"] == "pcs"


def test_lookup_narx_SOTUVDAN_joriy_narx_emas(db):
    """SUMMA rejimi shu narxga bo'ladi — u sotuvdagi narx bo'lishi SHART."""
    _sotuv(db, qty=2.0, unit_price=8000.0)       # sotuvda 1 kg = 8 000
    db.query(Product).filter(Product.id == 1).first().price = 12000
    db.commit()

    out = ret_router.lookup_order(q="CHK00001", db=db, current_user=_User())
    it = out["items"][0]
    assert it["unit_price"] == 8000, "lookup sotuvdagi narxni qaytarishi shart"
    assert it["unit_price"] != 12000
    # 9500 / 8000 = 1.1875 -> frontend 1.188 ko'rsatadi
    assert round(9500 / it["unit_price"], 3) == 1.188


def test_lookup_pachka_qatorida_unit_price_QOP_narxi(db):
    """Qop bilan sotilganda `unit_price` — QOP narxi, ya'ni SUMMA rejimi
    bo'linmasi QOP SONINI beradi."""
    _sotuv(db, oi_id=2, product_id=2, qty=2.0, unit_price=20000.0,
           unit_cost=16000.0, unit_sold="pachka", base_qty=16.0)
    out = ret_router.lookup_order(q="CHK00001", db=db, current_user=_User())
    it = out["items"][0]
    assert it["unit_sold"] == "pachka"
    assert it["unit_price"] == 20000          # qop narxi (dona narxi 3 000 emas)
    assert it["sold_qty"] == 2                # 2 qop
    assert 40000 / it["unit_price"] == 2      # 40 000 so'm = 2 qop


def test_lookup_mavjud_maydonlar_saqlangan(db):
    """GOLDEN: `sale_unit` QO'SHILDI — qolgan maydonlar o'z joyida."""
    _sotuv(db, qty=2.0, unit_price=12000.0)
    out = ret_router.lookup_order(q="CHK00001", db=db, current_user=_User())
    it = out["items"][0]
    for kalit in ("order_item_id", "product_id", "product_name", "unit_sold",
                  "sold_qty", "returned_qty", "returnable_qty", "unit_price",
                  "sale_unit"):
        assert kalit in it, f"{kalit} yo'qolgan"
    assert out["order_id"] == 1
    assert out["items"][0]["returnable_qty"] == 2
