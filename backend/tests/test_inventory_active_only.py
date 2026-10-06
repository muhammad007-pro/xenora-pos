"""⛔ O'CHIRILGAN MAHSULOT OMBORDA QOLMASIN.

NUQSON (2026-10-05 topildi): `delete_product` (`routers/product.py`)
SOFT-DELETE qiladi — `is_active = False`, `is_available = False` — lekin
`inventory` QATORI TEGILMAYDI. Natijada o'chirilgan mahsulot:
  • ombor ro'yxatida (`GET /inventory/`) ko'rinib turardi
  • POS ombor ko'rinishida (`/inventory/pos-stock`) ham
  • qoldig'i ombor QIYMATIGA (`/inventory/value`) qo'shilardi
  • "kam qoldi" ogohlantirishini (`/inventory/low-stock`) berardi
  • "o'lik tovar" ro'yxatiga tushardi (`/inventory/report/summary`)
  • AVTO-ZAKAZ ogohlantirishida qolardi (`/analytics/reorder-alerts`) —
    ya'ni o'chirilgan tovar uchun "zakaz bering" deb turardi

JONLI O'LCHOV (prod, 2026-10-05): 35 qator / 4 do'kon (FAZZA 10, 1001 BARAKA
11, NICE SHOPPING 11, MANHATTAN 3); 10 tasida qoldiq bor; ombor qiymatiga
noto'g'ri qo'shilgani 1 859 001 so'm.

⚠️ YECHIM — FAQAT KO'RINISH filtri. `Inventory` qatori O'CHIRILMAYDI:
mahsulot qayta faollashtirilsa (`PATCH /products/{id}` → `is_active=True`)
qoldiq JOYIDA bo'lishi kerak. Oxirgi blok aynan shuni qulflaydi.

Ishga tushirish:  cd backend && py -m pytest tests/test_inventory_active_only.py -v
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Cafe, Category, Inventory, Product, ProductReorderSetting, User

import routers.analytics as an_router
import routers.inventory as inv_router

TID = 1


class _User:
    """view_finance/view_reports BOR (tannarx va qiymat ko'rinadi)."""
    is_superuser = True
    tenant_id = TID
    id = 5
    role = None
    _active_branch_id = None


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Cafe(id=TID, name="FAZZA", code="FAZZA"))
    s.add(Category(id=1, name="Parfum", tenant_id=TID))
    # FAOL mahsulot
    s.add(Product(id=1, name="AKTIV ATIR", price=100000, cost_price=60000,
                  sale_unit="pcs", category_id=1, tenant_id=TID,
                  is_active=True, is_available=True))
    s.add(Inventory(id=1, tenant_id=TID, product_id=1, quantity=10,
                    unit="dona", min_threshold=3))
    # O'CHIRILGAN mahsulot — qoldiq bilan (jonli holat: 10 qator shunday)
    s.add(Product(id=2, name="OCHIRILGAN ATIR", price=200000, cost_price=120000,
                  sale_unit="pcs", category_id=1, tenant_id=TID,
                  is_active=False, is_available=False))
    s.add(Inventory(id=2, tenant_id=TID, product_id=2, quantity=7,
                    unit="dona", min_threshold=5))
    # O'CHIRILGAN va qoldiqsiz (prodda 25 qator shunday)
    s.add(Product(id=3, name="OCHIRILGAN NOL", price=50000, cost_price=30000,
                  sale_unit="pcs", category_id=1, tenant_id=TID,
                  is_active=False, is_available=False))
    s.add(Inventory(id=3, tenant_id=TID, product_id=3, quantity=0,
                    unit="dona", min_threshold=2))
    s.add(User(id=5, tenant_id=TID, full_name="Admin",
               phone="+998900000005", hashed_password="x"))
    s.commit()
    yield s
    s.close()


def _nomlar(items):
    return sorted(getattr(i, "product", None) and i.product.name or "" for i in items)


# ═══════════════════════════════════════════════════════════════════════════
# 1. OMBOR RO'YXATI — o'chirilgan mahsulot YO'Q
# ═══════════════════════════════════════════════════════════════════════════
def test_ombor_royxatida_ochirilgan_YOQ(db):
    r = asyncio.run(inv_router.get_inventory_items(
        page=1, page_size=100, low_stock_only=False, category_id=None,
        search=None, db=db, current_user=_User()))
    nomlar = sorted(i.product.name for i in r.items)
    assert nomlar == ["AKTIV ATIR"]
    assert r.total == 1, "o'chirilganlar `total` dan ham chiqishi shart"


def test_ombor_royxati_qidiruvda_ham_filtrlaydi(db):
    """Qidiruv o'chirilgan mahsulotni ham topib qo'ymasin."""
    r = asyncio.run(inv_router.get_inventory_items(
        page=1, page_size=100, low_stock_only=False, category_id=None,
        search="ATIR", db=db, current_user=_User()))
    assert [i.product.name for i in r.items] == ["AKTIV ATIR"]


def test_low_stock_only_filtrida_ham(db):
    """O'chirilgan #2 (7 <= ... yo'q) va #3 (0 <= 2) tushmasin.
    Faol #1: 10 > 3 → ro'yxat bo'sh bo'ladi."""
    r = asyncio.run(inv_router.get_inventory_items(
        page=1, page_size=100, low_stock_only=True, category_id=None,
        search=None, db=db, current_user=_User()))
    assert r.items == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. POS OMBOR KO'RINISHI
# ═══════════════════════════════════════════════════════════════════════════
def test_pos_stock_ochirilganni_bermaydi(db):
    out = asyncio.run(inv_router.get_pos_stock(
        search=None, limit=400, db=db, current_user=_User()))
    assert [r["name"] for r in out["items"]] == ["AKTIV ATIR"]


def test_pos_stock_total_value_ochirilgani_qoshmaydi(db):
    """Faol: 10 × 60 000 = 600 000. O'chirilgan 7 × 120 000 = 840 000
    QO'SHILMASIN."""
    out = asyncio.run(inv_router.get_pos_stock(
        search=None, limit=400, db=db, current_user=_User()))
    assert out["total_value"] == 600000
    assert out["total_value"] != 1440000


def test_pos_stock_javob_shakli_ozgarmagan(db):
    """GOLDEN: POS klientlari shu kalitlarga tayanadi."""
    out = asyncio.run(inv_router.get_pos_stock(
        search=None, limit=400, db=db, current_user=_User()))
    assert set(out) >= {"items", "can_cost", "block_oversell"}
    row = out["items"][0]
    for k in ("product_id", "name", "price", "sale_unit", "quantity", "unit",
              "min_threshold", "image_url", "pack_size", "pack_price"):
        assert k in row, f"{k} yo'qolgan"


# ═══════════════════════════════════════════════════════════════════════════
# 3. OGOHLANTIRISH va YIG'INDI
# ═══════════════════════════════════════════════════════════════════════════
def test_low_stock_ochirilgan_ogohlantirmaydi(db):
    """O'chirilgan #2 (7 > 5 → kirmaydi) va #3 (0 <= 2 → KIRARDI)."""
    items = asyncio.run(inv_router.get_low_stock_items(db=db, current_user=_User()))
    assert items == []


def test_ombor_qiymati_ochirilgani_hisobga_olmaydi(db):
    """total_cost = 10 × 60 000 = 600 000 (840 000 qo'shilmaydi).
    item_count ham faqat faol qatorlar."""
    out = asyncio.run(inv_router.get_inventory_value(db=db, current_user=_User()))
    assert out["total_cost"] == 600000
    assert out["total_retail"] == 1000000      # 10 × 100 000
    assert out["item_count"] == 1


def test_olik_tovar_royxatida_ochirilgan_YOQ(db):
    out = asyncio.run(inv_router.get_report_summary(
        days=30, db=db, current_user=_User()))
    nomlar = [d["product_name"] for d in out["dead_stock"]]
    assert "OCHIRILGAN ATIR" not in nomlar
    assert nomlar == ["AKTIV ATIR"]            # faol, harakatsiz, qoldiqli


# ═══════════════════════════════════════════════════════════════════════════
# 4. ⚠️ QAYTA FAOLLASHTIRILSA QOLDIQ JOYIDA (qator o'chirilmagan)
# ═══════════════════════════════════════════════════════════════════════════
def test_inventory_qatori_OCHIRILMAGAN(db):
    """Filtr faqat KO'RINISHGA ta'sir qiladi — qator bazada turibdi."""
    inv = db.query(Inventory).filter(Inventory.product_id == 2).first()
    assert inv is not None
    assert inv.quantity == 7
    assert inv.min_threshold == 5


def test_qayta_faollashtirilsa_qoldiq_joyida(db):
    """Mahsulot qayta yoqilsa ombor qatori AVVALGI qoldiq bilan qaytadi."""
    p = db.query(Product).filter(Product.id == 2).first()
    p.is_active = True
    p.is_available = True
    db.commit()

    r = asyncio.run(inv_router.get_inventory_items(
        page=1, page_size=100, low_stock_only=False, category_id=None,
        search=None, db=db, current_user=_User()))
    qaytgan = next(i for i in r.items if i.product.name == "OCHIRILGAN ATIR")
    assert qaytgan.quantity == 7, "qoldiq yo'qolmagan bo'lishi shart"
    assert r.total == 2

    # Yig'indi ham qaytadi: 600 000 + 7 × 120 000
    val = asyncio.run(inv_router.get_inventory_value(db=db, current_user=_User()))
    assert val["total_cost"] == 600000 + 840000


def test_is_active_NULL_FAOL_deb_qaraladi(db):
    """`isnot(False)` ataylab: NULL (xom SQL bilan yaratilgan qator) FAOL.

    Xato yo'nalishi xavfsiz — haqiqiy mahsulotni YASHIRIB qo'yishdan ko'ra
    ortiqcha ko'rsatish yaxshi. (Prodda NULL yo'q, lekin qoida yozilgan.)"""
    db.add(Product(id=4, name="NULL HOLAT", price=1000, cost_price=500,
                   sale_unit="pcs", category_id=1, tenant_id=TID,
                   is_active=None, is_available=True))
    db.add(Inventory(id=4, tenant_id=TID, product_id=4, quantity=5,
                     unit="dona", min_threshold=1))
    db.commit()

    r = asyncio.run(inv_router.get_inventory_items(
        page=1, page_size=100, low_stock_only=False, category_id=None,
        search=None, db=db, current_user=_User()))
    assert "NULL HOLAT" in [i.product.name for i in r.items]


# ═══════════════════════════════════════════════════════════════════════════
# 5. AVTO-ZAKAZ OGOHLANTIRISHI (`/analytics/reorder-alerts`)
#
# Bu yo'l `product_reorder_settings` qatorlari bo'yicha yuradi — `inventory`
# bo'yicha EMAS — shuning uchun `_faqat_faol()` unga ta'sir qilmaydi va
# ALOHIDA filtr kerak bo'ldi.
#
# PRODDA (2026-10-06 o'lchandi): reorder sozlamasi 0 ta — xususiyat
# `require_feature("auto_reorder")` bilan yopilgan va hali ishlatilmaydi.
# Ya'ni bu PROFILAKTIK tuzatish: jonli ta'sir yo'q, lekin xususiyat
# yoqilganda o'chirilgan tovar ro'yxatga tushib qolmasin.
# ═══════════════════════════════════════════════════════════════════════════

def _reorder(db, product_id, min_qty=20.0, rid=None):
    """Sozlama: joriy qoldiq `min_qty` dan past -> ogohlantirish chiqadi."""
    db.add(ProductReorderSetting(id=rid, tenant_id=TID, product_id=product_id,
                                 min_qty=min_qty, reorder_qty=50.0))
    db.commit()


def test_reorder_faol_mahsulot_ogohlantiradi(db):
    """GOLDEN: faol mahsulot avvalgidek ro'yxatda (10 < 20)."""
    _reorder(db, 1, min_qty=20.0, rid=1)
    out = asyncio.run(an_router.get_reorder_alerts(db=db, current_user=_User()))
    assert out["total"] == 1
    assert out["alerts"][0]["product_name"] == "AKTIV ATIR"
    assert out["alerts"][0]["current_qty"] == 10
    assert out["alerts"][0]["deficit"] == 10


def test_reorder_ochirilgan_mahsulot_OGOHLANTIRMAYDI(db):
    """O'chirilgan #2: qoldiq 7 < 20 -> ilgari ro'yxatga TUSHARDI."""
    _reorder(db, 2, min_qty=20.0, rid=2)
    out = asyncio.run(an_router.get_reorder_alerts(db=db, current_user=_User()))
    assert out["total"] == 0
    assert out["alerts"] == []


def test_reorder_faol_va_ochirilgan_birga(db):
    """Aralash holat: faqat faol qoladi — nom bilan tasdiqlanadi."""
    _reorder(db, 1, min_qty=20.0, rid=1)
    _reorder(db, 2, min_qty=20.0, rid=2)
    _reorder(db, 3, min_qty=20.0, rid=3)      # o'chirilgan, qoldiq 0
    out = asyncio.run(an_router.get_reorder_alerts(db=db, current_user=_User()))
    assert [a["product_name"] for a in out["alerts"]] == ["AKTIV ATIR"]
    assert out["total"] == 1


def test_reorder_qayta_faollashtirilsa_qaytadi(db):
    """Mahsulot qayta yoqilsa ogohlantirish ham qaytadi (qoldiq 7 < 20)."""
    _reorder(db, 2, min_qty=20.0, rid=2)
    p = db.query(Product).filter(Product.id == 2).first()
    p.is_active = True
    db.commit()

    out = asyncio.run(an_router.get_reorder_alerts(db=db, current_user=_User()))
    assert out["total"] == 1
    assert out["alerts"][0]["product_name"] == "OCHIRILGAN ATIR"
    assert out["alerts"][0]["current_qty"] == 7


def test_reorder_is_active_NULL_FAOL(db):
    """`isnot(False)` — NULL FAOL deb qaraladi (boshqa 5 joy bilan bir xil)."""
    db.add(Product(id=5, name="NULL REORDER", price=1000, cost_price=500,
                   sale_unit="pcs", category_id=1, tenant_id=TID,
                   is_active=None, is_available=True))
    db.add(Inventory(id=5, tenant_id=TID, product_id=5, quantity=1,
                     unit="dona", min_threshold=1))
    db.commit()
    _reorder(db, 5, min_qty=20.0, rid=5)

    out = asyncio.run(an_router.get_reorder_alerts(db=db, current_user=_User()))
    assert [a["product_name"] for a in out["alerts"]] == ["NULL REORDER"]


def test_reorder_javob_shakli_ozgarmagan(db):
    """GOLDEN: frontend shu kalitlarga tayanadi."""
    _reorder(db, 1, min_qty=20.0, rid=1)
    out = asyncio.run(an_router.get_reorder_alerts(db=db, current_user=_User()))
    assert set(out) == {"alerts", "total"}
    for k in ("product_id", "product_name", "current_qty", "min_qty",
              "reorder_qty", "deficit", "supplier_id", "supplier_name",
              "supplier_phone", "setting_id", "notes"):
        assert k in out["alerts"][0], f"{k} yo'qolgan"
