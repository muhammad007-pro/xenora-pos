"""KG MAHSULOTDA QOP (pachka) NARXI — server hisobi.

NEGA BU TEST BOR
────────────────
"20 kg qop" ni sotish imkoniyati FRONTENDDA ikki joyda to'silgan edi
(`pos.js` pachka tanlov sharti va `admin/core.js` `togglePack`), backend esa
BUNI ALLAQACHON QO'LLAB-QUVVATLARDI. Bu test aynan shu da'voni qulflaydi:
`services/order_service.py` dagi `pack_enabled` FAQAT

    pack_size >= 2  AND  pack_price > 0

ga qaraydi — `sale_unit` ga EMAS. Ya'ni kg mahsulot uchun migratsiya ham,
backend o'zgarishi ham KERAK EMAS. Agar kelajakda u yerga birlik cheklovi
qo'shilsa (masalan "faqat dona/ml"), bu testlar YIQILADI va sabab darhol
ko'rinadi.

Nimani tekshiradi:
  1. base_qty  = pack_size × quantity   (ombordan ayiriladigan KG)
  2. unit_cost = cost_price × pack_size (COGS — 1 kg tannarx × qopdagi kg)
  3. unit_price = pack_price            (client narxiga ishonilmaydi)
  4. kg mahsulot QOPSIZ (dona rejimi) sotilsa — avvalgidek, base_qty=quantity
  5. kasrli miqdor (og'irlik sotuvi) buzilmaydi — GOLDEN

⚠️ `_next_daily_number()` PostgreSQL `timezone()` funksiyasini ishlatadi va
SQLite'da yo'q (qarang `tests/test_orders.py` izohi). Shu sabab u SHU TESTDA
stub qilinadi — tekshirilayotgan narsa kunlik raqam emas, NARX/MIQDOR bloki.

Ishga tushirish:  cd backend && py -m pytest tests/test_weight_pack_price.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Cafe, Category, Inventory, Product, User
from schemas import OrderCreate, OrderItemCreate
from services.order_service import OrderService

TID = 1
KASSIR = 21

# Jonli raqamlar (1001 BARAKA shakli): 1 kg = 25 000, qop 20 kg = 450 000
KG_PRICE = 25000.0
KG_COST = 18000.0
PACK_SIZE = 20
PACK_PRICE = 450000.0


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Cafe(id=TID, name="BARAKA", code="BARAKA"))
    s.add(Category(id=1, name="Oziq-ovqat", tenant_id=TID))
    # 1 — KG + QOP (yangi holat): shakar, 1 kg narxi + 20 kg qop narxi
    s.add(Product(id=1, name="SHAKAR", price=KG_PRICE, cost_price=KG_COST,
                  sale_unit="kg", pack_size=PACK_SIZE, pack_price=PACK_PRICE,
                  category_id=1, tenant_id=TID, is_available=True))
    s.add(Inventory(id=1, tenant_id=TID, product_id=1, quantity=500, unit="kg"))
    # 2 — KG, QOPSIZ (regressiya): og'irlik sotuvi avvalgidek
    s.add(Product(id=2, name="GO'SHT", price=90000, cost_price=70000,
                  sale_unit="kg", category_id=1, tenant_id=TID, is_available=True))
    s.add(Inventory(id=2, tenant_id=TID, product_id=2, quantity=50, unit="kg"))
    # 3 — DONA + PACHKA (regressiya): mavjud xatti-harakat o'zgarmasin
    s.add(Product(id=3, name="GUPKA", price=3000, cost_price=2000,
                  sale_unit="pcs", pack_size=8, pack_price=20000,
                  category_id=1, tenant_id=TID, is_available=True))
    s.add(Inventory(id=3, tenant_id=TID, product_id=3, quantity=800, unit="dona"))
    s.add(User(id=KASSIR, tenant_id=TID, full_name="Kassir",
               phone="+998900000021", hashed_password="x"))
    s.commit()
    yield s
    s.close()


def _sot(db, product_id, quantity, unit_sold=None):
    """Buyurtma yaratadi va YAGONA qatorini qaytaradi."""
    svc = OrderService(db)
    # SQLite'da PG `timezone()` yo'q — kunlik raqam bu testning predmeti emas.
    svc._next_daily_number = lambda tenant_id: 1
    order = svc.create_order(
        OrderCreate(items=[OrderItemCreate(
            product_id=product_id, quantity=quantity, unit_sold=unit_sold)],
            order_type="pos"),
        waiter_id=KASSIR, tenant_id=TID)
    assert len(order.items) == 1
    return order.items[0]


# ═══════════════════════════════════════════════════════════════════════════
# 1. KG + QOP — yangi imkoniyat (backend o'zgarishisiz ishlashi SHART)
# ═══════════════════════════════════════════════════════════════════════════
def test_kg_qop_base_qty_pack_size_karra_quantity(db):
    """1 qop = 20 kg → ombordan 20 kg ayiriladi (1 emas)."""
    it = _sot(db, 1, 1, unit_sold="pachka")
    assert it.base_qty == PACK_SIZE * 1
    assert it.unit_sold == "pachka"


def test_kg_qop_ikki_qop(db):
    it = _sot(db, 1, 2, unit_sold="pachka")
    assert it.base_qty == PACK_SIZE * 2      # 40 kg
    assert it.quantity == 2                  # 2 qop


def test_kg_qop_narxi_pack_price(db):
    """Narx SERVERDAN — client yuborgan narxga ishonilmaydi."""
    it = _sot(db, 1, 1, unit_sold="pachka")
    assert it.unit_price == PACK_PRICE
    assert it.total_price == PACK_PRICE


def test_kg_qop_tannarx_cost_price_karra_pack_size(db):
    """unit_cost = 1 kg tannarx × qopdagi kg — COGS to'g'ri bo'lishi uchun.

    Bu buzilsa foyda hisoboti qopni 18 000 ga tushgan deb ko'rsatadi
    (haqiqatda 360 000) va marja 96% bo'lib ko'rinadi."""
    it = _sot(db, 1, 1, unit_sold="pachka")
    assert it.unit_cost == KG_COST * PACK_SIZE      # 360 000


def test_kg_qop_pack_enabled_sale_unit_ga_bogliq_EMAS(db):
    """Da'voning o'zi: kg mahsulotda `pack_enabled` ishlaydi.

    Agar `order_service` ga birlik cheklovi qo'shilsa, bu yerda `base_qty`
    1 ga tushadi (dona fallback) va test YIQILADI."""
    p = db.query(Product).filter(Product.id == 1).first()
    assert p.sale_unit == "kg"
    it = _sot(db, 1, 1, unit_sold="pachka")
    assert it.base_qty != it.quantity        # fallback'ga tushmadi
    assert it.base_qty == 20


# ═══════════════════════════════════════════════════════════════════════════
# 2. GOLDEN — og'irlik sotuvi (425 qator) BUZILMASIN
# ═══════════════════════════════════════════════════════════════════════════
def test_kg_qopsiz_ogirlik_sotuvi_avvalgidek(db):
    """Qopsiz kg mahsulot: base_qty = quantity, narx = 1 kg narxi."""
    it = _sot(db, 2, 1.5)
    assert it.quantity == 1.5
    assert it.base_qty == 1.5
    assert it.unit_price == 90000
    assert it.unit_cost == 70000
    assert it.unit_sold is None


def test_kg_QOPLI_mahsulot_ogirlik_bilan_ham_sotiladi(db):
    """Qop narxi KIRITILGAN kg mahsulot kg bo'yicha ham sotilishi kerak —
    `unit_sold` yuborilmasa 1 kg narxi va base_qty = kg."""
    it = _sot(db, 1, 0.740)
    assert it.quantity == 0.740
    assert it.base_qty == 0.740
    assert it.unit_price == KG_PRICE         # qop narxi EMAS
    assert it.unit_cost == KG_COST
    assert it.unit_sold is None


def test_kg_kasrli_miqdor_yaxlitlash_saqlanadi(db):
    """3 xona yaxlitlash (schemas `_yaxlitla_miqdor`) tegilmagan."""
    it = _sot(db, 1, 0.7405882)
    assert it.quantity == 0.741
    assert it.base_qty == 0.741


# ═══════════════════════════════════════════════════════════════════════════
# 3. GOLDEN — mavjud pachkali mahsulotlar (dona) o'zgarmasin
# ═══════════════════════════════════════════════════════════════════════════
def test_dona_pachka_avvalgidek(db):
    it = _sot(db, 3, 1, unit_sold="pachka")
    assert it.base_qty == 8
    assert it.unit_price == 20000
    assert it.unit_cost == 2000 * 8
    assert it.unit_sold == "pachka"


def test_dona_rejimi_avvalgidek(db):
    it = _sot(db, 3, 3, unit_sold="dona")
    assert it.base_qty == 3
    assert it.unit_price == 3000
    assert it.unit_cost == 2000
    assert it.unit_sold == "dona"


def test_pachkasiz_mahsulotga_pachka_desa_xavfsiz_fallback(db):
    """Client "pachka" yuborsa-yu mahsulot qopsiz bo'lsa — oddiy sotuv
    (xato EMAS). Mavjud himoya; o'zgarmaganini qulflaymiz."""
    it = _sot(db, 2, 2, unit_sold="pachka")
    assert it.base_qty == 2
    assert it.unit_price == 90000
    assert it.unit_sold is None
