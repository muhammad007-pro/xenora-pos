"""FOYDA MARJASI KPI — `.limit(50)` jamini kesib qo'yardi (2026-09-11).

MUAMMO (jonli, 1001 BARAKA): ikki ekran turli "jami savdo" ko'rsatardi —
"Foyda tahlili" 4 406 005, "Foyda marjasi" 2 699 445. Tekshiruvda aniqlandi:
`/analytics/store-margin` BITTA so'rov qilardi va KPI'larni (jami tushum,
brutto foyda, marja %) `.limit(50)` dan KEYINGI qatorlar ustidan yig'ardi.
Tenant 27 da 172 mahsulot sotilgan → tushumning 43% i jamiga umuman
kirmasdi. Katalog o'sgani sari farq kattalashardi.

Ikkinchi farq: `profit.py` vozvratni ayiradi, bu ekran ayirmasdi.
Uchinchi: yuqori vaqt chegarasi yo'q edi — kelajak sanali buyurtma kirardi.

QOIDA:
  • KPI — BUTUN davr (GROUP BY yo'q, LIMIT yo'q), vozvrat ayirilgan.
  • Jadval — top-50 (uzun ro'yxat kesiladi), `items_limited` bilan belgilanadi.
  • `/profit/summary` va `/analytics/store-margin` bir xil davrda AYNAN bir
    xil jami tushum berishi shart.

Ishga tushirish:
    cd backend && py -m pytest tests/test_store_margin_kpi.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

from core.timeutils import tenant_now

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import (
    Cafe, Category, Order, OrderItem, Product, Return, ReturnItem,
    Role, Permission, User,
)
from core.security import get_password_hash

PW = "MarjaTest9x"
PHONE = "+998900000101"

# 60 mahsulot — `.limit(50)` chegarasidan 10 ta ko'p (nuqsonni ushlaydi)
MAHSULOT_SONI = 60


@pytest.fixture()
def db_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture()
def seeded(db_session):
    """60 mahsulot, har biri bitta buyurtmada sotilgan.

    Narxlar KAMAYIB boradi (1000-i, 990-i, ...) — top-50 aniq bo'lsin va
    kesilgan 10 ta ENG ARZONI bo'lsin.
    """
    db = db_session
    perms = [Permission(code=c, description=c) for c in ("view_analytics", "view_finance")]
    db.add_all(perms); db.flush()
    role = Role(name="admin", description="Administrator"); role.permissions = perms
    db.add(role); db.flush()

    cafe = Cafe(name="SINOV", code="a", access_code="100.200.101",
                business_type="supermarket", subscription_plan="pro", is_active=True)
    db.add(cafe); db.flush()
    kat = Category(name="KAT", tenant_id=cafe.id); db.add(kat); db.flush()

    db.add(User(username="u101", email="101@x.uz", full_name="ADMIN", phone=PHONE,
                hashed_password=get_password_hash(PW), is_active=True,
                is_superuser=False, tenant_id=cafe.id, role_id=role.id))

    # Sotuv vaqti — BUGUN, HOZIRDAN OLDIN. `tenant_now()` dan olinadi (server
    # zonasi boshqa bo'lishi mumkin), 2 soat orqaga suriladi: yangi YUQORI
    # chegara (`end = now`) uni chiqarib tashlamasin. Kun boshiga ham tushib
    # ketmasligi uchun kamida 03:00.
    _now = tenant_now()
    _now = _now.replace(tzinfo=None) if _now.tzinfo else _now
    sotuv_vaqti = _now - timedelta(hours=2)
    if sotuv_vaqti.date() != _now.date():
        sotuv_vaqti = _now.replace(hour=3, minute=0, second=0, microsecond=0)

    prods, kutilgan_tushum, kutilgan_tannarx = [], 0.0, 0.0
    for i in range(MAHSULOT_SONI):
        narx = 1000.0 - i * 10          # 1000, 990, ... 410
        tan  = narx * 0.6
        p = Product(name=f"M{i:03d}", price=narx, cost_price=tan, sale_unit="pcs",
                    category_id=kat.id, tenant_id=cafe.id, is_active=True)
        db.add(p); db.flush()
        prods.append(p)

        o = Order(order_number=f"T{i:04d}", tenant_id=cafe.id, status="completed",
                  total_amount=narx, final_amount=narx, discount_amount=0,
                  created_at=sotuv_vaqti)
        db.add(o); db.flush()
        db.add(OrderItem(order_id=o.id, product_id=p.id, quantity=1,
                         unit_price=narx, total_price=narx, unit_cost=tan))
        kutilgan_tushum  += narx
        kutilgan_tannarx += tan

    db.commit()
    return {
        "db": db, "cafe": cafe.id, "prods": [p.id for p in prods],
        "tushum": kutilgan_tushum, "tannarx": kutilgan_tannarx,
        "vaqt": sotuv_vaqti, "kat": kat.id,
    }


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client):
    r = client.post("/api/v1/auth/login", data={"username": PHONE, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _margin(client, hdr, period="week"):
    r = client.get(f"/api/v1/analytics/store-margin?period={period}", headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


def _profit(client, hdr, period="week"):
    r = client.get(f"/api/v1/profit/summary?period={period}", headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


# ══════════════════════════════════════════════════════════════════════════════
# 1) KPI kesilmaydi, jadval kesiladi
# ══════════════════════════════════════════════════════════════════════════════

def test_kpi_hamma_mahsulotni_hisoblaydi(seeded, client):
    """⚠️ ASOSIY: 60 mahsulot sotilgan — KPI 60 tasini ham hisoblasin.

    ILGARI: faqat top-50 yig'ilardi va 10 ta eng arzoni tushib qolardi.
    """
    d = _margin(client, _login(client))
    assert d["total_revenue"] == pytest.approx(seeded["tushum"], abs=1)
    assert d["total_profit"] == pytest.approx(
        seeded["tushum"] - seeded["tannarx"], abs=1)


def test_jadval_50_ta_bilan_cheklangan(seeded, client):
    """Jadval AVVALGIDEK top-50 — uzun ro'yxat kesiladi."""
    d = _margin(client, _login(client))
    assert len(d["items"]) == 50
    assert d["items_limited"] is True


def test_jadval_eng_qimmatini_beradi(seeded, client):
    """Tartib buzilmasin: tushum bo'yicha kamayib boradi."""
    d = _margin(client, _login(client))
    revs = [it["revenue"] for it in d["items"]]
    assert revs == sorted(revs, reverse=True)
    assert d["items"][0]["name"] == "M000"     # eng qimmati
    # Kesilgan 10 ta ENG ARZONI jadvalda YO'Q, lekin KPI'da BOR
    nomlar = {it["name"] for it in d["items"]}
    assert "M059" not in nomlar


def test_kpi_jadval_yigindisidan_KATTA(seeded, client):
    """Nuqson imzosi: ilgari bu ikkisi TENG edi (ikkalasi ham kesilgan)."""
    d = _margin(client, _login(client))
    jadval_jami = sum(it["revenue"] for it in d["items"])
    assert d["total_revenue"] > jadval_jami, (
        "KPI jadval yig'indisiga teng — .limit(50) yana KPI'ga ta'sir qilyapti"
    )


def test_kam_mahsulotda_limited_false(seeded, client, db_session):
    """50 dan kam mahsulot bo'lsa — belgi qo'yilmaydi (ortiqcha shovqin yo'q)."""
    db = db_session
    # 60 dan 40 tasini qoldiramiz: qolganlarining buyurtmalarini bekor qilamiz
    kesiladigan = seeded["prods"][40:]
    ids = [oi.order_id for oi in db.query(OrderItem)
           .filter(OrderItem.product_id.in_(kesiladigan)).all()]
    db.query(Order).filter(Order.id.in_(ids)).update(
        {Order.status: "cancelled"}, synchronize_session=False)
    db.commit()

    d = _margin(client, _login(client))
    assert len(d["items"]) == 40
    assert d["items_limited"] is False


# ══════════════════════════════════════════════════════════════════════════════
# 2) Qaytarish KPI'dan ayiriladi
# ══════════════════════════════════════════════════════════════════════════════

def test_qaytarish_kpi_dan_ayiriladi(seeded, client, db_session):
    """ILGARI: vozvrat umuman ayirilmasdi — marja o'sha sotuvdan olingandek qolardi."""
    db = db_session
    oldin = _margin(client, _login(client))

    pid = seeded["prods"][0]
    oi  = db.query(OrderItem).filter(OrderItem.product_id == pid).first()
    ret = Return(return_number="R001", order_id=oi.order_id, tenant_id=seeded["cafe"],
                 status="approved", total_amount=1000.0, reason="sinov",
                 refund_method="cash", approved_at=seeded["vaqt"])
    db.add(ret); db.flush()
    db.add(ReturnItem(return_id=ret.id, order_item_id=oi.id, product_id=pid,
                      quantity=1, unit_price=1000.0, total=1000.0))
    db.commit()

    keyin = _margin(client, _login(client))
    assert keyin["total_revenue"] == pytest.approx(oldin["total_revenue"] - 1000, abs=1)
    assert keyin["returns_revenue"] == pytest.approx(1000, abs=1)


# ══════════════════════════════════════════════════════════════════════════════
# 3) IKKI EKRAN BIR XIL RAQAM — asosiy shikoyat shu edi
# ══════════════════════════════════════════════════════════════════════════════

def test_ikki_ekran_bir_xil_tushum(seeded, client):
    """⚠️ ASOSIY: /profit/summary va /analytics/store-margin mos kelsin."""
    hdr = _login(client)
    p = _profit(client, hdr, "week")
    m = _margin(client, hdr, "week")
    assert m["total_revenue"] == pytest.approx(p["revenue"], abs=1), (
        f"ekranlar ajralib qoldi: profit={p['revenue']} margin={m['total_revenue']}"
    )


def test_ikki_ekran_qaytarish_bilan_ham_bir_xil(seeded, client, db_session):
    """Vozvrat qo'shilgach ham ikkalasi bir xil qolsin."""
    db = db_session
    pid = seeded["prods"][1]
    oi  = db.query(OrderItem).filter(OrderItem.product_id == pid).first()
    ret = Return(return_number="R002", order_id=oi.order_id, tenant_id=seeded["cafe"],
                 status="approved", total_amount=990.0, reason="sinov",
                 refund_method="cash", approved_at=seeded["vaqt"])
    db.add(ret); db.flush()
    db.add(ReturnItem(return_id=ret.id, order_item_id=oi.id, product_id=pid,
                      quantity=1, unit_price=990.0, total=990.0))
    db.commit()

    hdr = _login(client)
    p = _profit(client, hdr, "week")
    m = _margin(client, hdr, "week")
    assert m["total_revenue"] == pytest.approx(p["revenue"], abs=1)
    assert m["total_profit"] == pytest.approx(p["gross_profit"], abs=1)


# ══════════════════════════════════════════════════════════════════════════════
# 4) Kelajak sanali buyurtma kirmaydi
# ══════════════════════════════════════════════════════════════════════════════

def test_kelajak_sanali_buyurtma_kirmaydi(seeded, client, db_session):
    """ILGARI yuqori chegara YO'Q edi — soati buzuq qurilma jamini shishirardi."""
    db = db_session
    oldin = _margin(client, _login(client))

    kelajak = datetime.now() + timedelta(days=3)
    o = Order(order_number="KELAJAK", tenant_id=seeded["cafe"], status="completed",
              total_amount=999999, final_amount=999999, discount_amount=0,
              created_at=kelajak)
    db.add(o); db.flush()
    db.add(OrderItem(order_id=o.id, product_id=seeded["prods"][0], quantity=1,
                     unit_price=999999, total_price=999999, unit_cost=0))
    db.commit()

    keyin = _margin(client, _login(client))
    assert keyin["total_revenue"] == pytest.approx(oldin["total_revenue"], abs=1), (
        "kelajak sanali buyurtma jamiga kirib ketdi"
    )
    assert not any(it["revenue"] >= 999999 for it in keyin["items"])


def test_bugun_davri_ham_ishlaydi(seeded, client):
    """`today` — chegara qo'shilgach ham bugungi sotuv yo'qolmasin."""
    d = _margin(client, _login(client), "today")
    assert d["total_revenue"] == pytest.approx(seeded["tushum"], abs=1)
