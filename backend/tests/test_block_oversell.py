"""OMBOR QO'RIQCHISI — tugagan mahsulot sotilmasin.

MUAMMO: POS sotuv yo'lida ombor UMUMAN tekshirilmasdi. Sotuv o'tar, ombor
esa 0 da to'xtatilib kamomad JIMGINA yo'qolardi (manfiy qoldiq ham
qolmasdi — ekranda hech qanday signal yo'q). Fazza Parfum'da 15–31 avgustda
24 ta shunday sotuv topildi (22 buyurtma, 14 mahsulot, 297 dona).

⚠️ DEFAULT — mavjud do'konlar uchun O'CHIQ. Fazza'da 92, Eco Aroma'da 7
mahsulot hozir qoldiq 0; qo'riqchi darhol yoqilsa ular ERTAGA sotolmasdi.
Shu sabab bu fayldagi BIRINCHI blok — REGRESSIYA: o'chiq holatda xatti-harakat
AYNAN avvalgidek.

Ishga tushirish:  cd backend && py -m pytest tests/test_block_oversell.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Cafe, Category, Inventory, InventoryCount, Product, Recipe, RecipeItem,
)
from services.stock_guard import InsufficientStock, check, is_enabled

TID = 1


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Cafe(id=TID, name="Fazza", code="FAZZA", block_oversell=True))
    s.add(Category(id=1, name="Parfum", tenant_id=TID))
    s.commit()
    yield s
    s.close()


def _prod(db, pid, name, stock=None, pack_size=None, unit="dona"):
    db.add(Product(id=pid, name=name, price=10000, cost_price=5000,
                   category_id=1, tenant_id=TID, pack_size=pack_size,
                   pack_price=(80000 if pack_size else None)))
    if stock is not None:
        db.add(Inventory(tenant_id=TID, product_id=pid, quantity=stock, unit=unit))
    db.commit()


def _line(pid, qty, base_qty=None):
    """`order_service.create_order` ichidagi items_data qatori."""
    return {"product_id": pid, "quantity": qty, "base_qty": base_qty if base_qty is not None else qty}


def _cafe(db):
    return db.query(Cafe).filter(Cafe.id == TID).first()


# ═══════════════════════════════════════════════════════════════════════════
# 1. REGRESSIYA — qo'riqchi O'CHIQ bo'lsa hech narsa o'zgarmaydi
# ═══════════════════════════════════════════════════════════════════════════
def test_regressiya_ochiq_bolsa_bloklanmaydi(db):
    """Mavjud do'konlar aynan shu holatda (migratsiya FALSE yozadi)."""
    _cafe(db).block_oversell = False
    db.commit()
    _prod(db, 1, "PCHYOLKA gupka", stock=0)
    check(db, TID, [_line(1, 10)])          # xato ko'tarilmasligi kerak
    assert is_enabled(db, TID) is False


def test_regressiya_tenant_yoq_bolsa_bloklanmaydi(db):
    _prod(db, 1, "X", stock=0)
    check(db, None, [_line(1, 5)])
    assert is_enabled(db, None) is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. BLOKLASH
# ═══════════════════════════════════════════════════════════════════════════
def test_qoldiq_nol_bolsa_bloklanadi(db):
    _prod(db, 1, "PCHYOLKA gupka", stock=0)
    with pytest.raises(InsufficientStock) as e:
        check(db, TID, [_line(1, 1)])
    assert "PCHYOLKA gupka" in e.value.message
    assert "mavjud: 0" in e.value.message
    assert e.value.shortages[0]["needed"] == 1
    assert e.value.shortages[0]["available"] == 0


def test_qoldiq_yetarli_bolsa_otadi(db):
    _prod(db, 1, "Atir", stock=10)
    check(db, TID, [_line(1, 10)])          # AYNAN yetadi — o'tishi kerak
    check(db, TID, [_line(1, 3)])


def test_qoldiqdan_bir_dona_kop_bloklanadi(db):
    _prod(db, 1, "Atir", stock=10)
    with pytest.raises(InsufficientStock):
        check(db, TID, [_line(1, 11)])


def test_bir_mahsulot_ikki_qatorda_qoshiladi(db):
    """Savatda bir tovar ikki marta bo'lsa miqdorlar YIG'ILADI — aks holda
    har qator alohida "yetadi" deb o'tib ketardi."""
    _prod(db, 1, "Atir", stock=10)
    check(db, TID, [_line(1, 5), _line(1, 5)])          # 10 = 10, o'tadi
    with pytest.raises(InsufficientStock) as e:
        check(db, TID, [_line(1, 6), _line(1, 5)])      # 11 > 10
    assert e.value.shortages[0]["needed"] == 11


def test_xato_xabarida_bir_nechta_mahsulot(db):
    _prod(db, 1, "Atir A", stock=0)
    _prod(db, 2, "Atir B", stock=1)
    with pytest.raises(InsufficientStock) as e:
        check(db, TID, [_line(1, 1), _line(2, 5)])
    assert len(e.value.shortages) == 2
    assert "Atir A" in e.value.message and "Atir B" in e.value.message


# ═══════════════════════════════════════════════════════════════════════════
# 3. PACHKA / DONA — ombor BAZA birligida
# ═══════════════════════════════════════════════════════════════════════════
def test_pachka_base_qty_boyicha_tekshiriladi(db):
    """1 pachka = 8 dona, qoldiq 5 dona -> PACHKA SOTILMASIN.

    `quantity` = 1 (pachka), `base_qty` = 8 (dona). Oddiy `quantity` ni
    ishlatsak 1 <= 5 deb JIMGINA o'tib ketardi — aynan shu xato."""
    _prod(db, 1, "Gupka", stock=5, pack_size=8)
    with pytest.raises(InsufficientStock) as e:
        check(db, TID, [_line(1, 1, base_qty=8)])
    assert e.value.shortages[0]["needed"] == 8
    assert e.value.shortages[0]["available"] == 5


def test_pachka_qoldiq_yetsa_otadi(db):
    _prod(db, 1, "Gupka", stock=16, pack_size=8)
    check(db, TID, [_line(1, 2, base_qty=16)])


def test_atir_ml_100ml_flakon(db):
    """Jonli holat: BVLGARI AQUA, 1 flakon = 100 ml, omborda 80 ml."""
    _prod(db, 1, "BVLGARI AQUA", stock=80, pack_size=100, unit="ml")
    with pytest.raises(InsufficientStock) as e:
        check(db, TID, [_line(1, 1, base_qty=100)])
    assert e.value.shortages[0]["unit"] == "ml"
    assert "mavjud: 80 ml" in e.value.message


# ═══════════════════════════════════════════════════════════════════════════
# 4. ISTISNOLAR
# ═══════════════════════════════════════════════════════════════════════════
def test_inventorysiz_mahsulot_bloklanmaydi(db):
    """Xizmat / ombor nazorati o'chirilgan tovar — Inventory yozuvi YO'Q."""
    _prod(db, 1, "Yetkazib berish xizmati", stock=None)
    check(db, TID, [_line(1, 99)])


def test_retseptli_mahsulot_bloklanmaydi(db):
    """Restoran taomi — ingredientdan tayyorlanadi. kitchen.py ham ataylab
    bloklamaydi, o'sha qarorga ziddiyat qilmaymiz."""
    _prod(db, 1, "Lavash", stock=0)
    _prod(db, 2, "Non", stock=100)
    r = Recipe(id=1, product_id=1, tenant_id=TID, name="Lavash retsepti")
    db.add(r); db.flush()
    db.add(RecipeItem(recipe_id=1, ingredient_id=2, quantity=1, unit="dona"))
    db.commit()
    check(db, TID, [_line(1, 50)])          # retseptli -> o'tadi


def test_inventarizatsiya_davomida_bloklanmaydi(db):
    """Sanoq paytida tizim qoldig'i ataylab noto'g'ri — savdo to'xtamasin."""
    _prod(db, 1, "Atir", stock=0)
    with pytest.raises(InsufficientStock):
        check(db, TID, [_line(1, 1)])       # avval bloklanadi

    ic = InventoryCount(id=1, tenant_id=TID, status="draft")
    db.add(ic); db.commit()
    assert is_enabled(db, TID) is False
    check(db, TID, [_line(1, 1)])           # inventarizatsiya ochiq -> o'tadi


def test_inventarizatsiya_tasdiqlangach_ozi_qayta_yoqiladi(db):
    """Qo'lda tugma YO'Q — yoqishni unutib bo'lmaydi."""
    _prod(db, 1, "Atir", stock=0)
    ic = InventoryCount(id=1, tenant_id=TID, status="draft")
    db.add(ic); db.commit()
    check(db, TID, [_line(1, 1)])           # o'chiq

    ic.status = "confirmed"
    db.commit()
    assert is_enabled(db, TID) is True
    with pytest.raises(InsufficientStock):
        check(db, TID, [_line(1, 1)])       # QAYTA yoqildi


def test_boshqa_tenant_inventarizatsiyasi_tasir_qilmaydi(db):
    """Qo'shni do'konning sanog'i bizning qo'riqchimizni o'chirmasin."""
    db.add(Cafe(id=2, name="Eco", code="ECO", block_oversell=True)); db.commit()
    db.add(InventoryCount(id=1, tenant_id=2, status="draft")); db.commit()
    _prod(db, 1, "Atir", stock=0)
    assert is_enabled(db, TID) is True
    with pytest.raises(InsufficientStock):
        check(db, TID, [_line(1, 1)])


# ═══════════════════════════════════════════════════════════════════════════
# 5. Default qiymat
# ═══════════════════════════════════════════════════════════════════════════
def test_yangi_dokon_default_yoqiq(db):
    """Modeldan yaratilgan YANGI do'kon -> TRUE (to'g'ri standart).
    MAVJUD do'konlarga migratsiya FALSE yozadi (c8b3e5d90a17)."""
    c = Cafe(id=3, name="Yangi", code="YANGI")
    db.add(c); db.commit(); db.refresh(c)
    assert c.block_oversell is True


def test_bosh_savat_xato_bermaydi(db):
    check(db, TID, [])
    check(db, TID, [_line(1, 0)])
