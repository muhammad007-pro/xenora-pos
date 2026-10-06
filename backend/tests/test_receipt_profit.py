"""CHEK BO'YICHA FOYDA paneli — `/profit/by-receipt` (2026-10-06).

Panel FAQAT KO'RSATADI: yozmaydi va yangi formula kiritmaydi. Shu sabab bu
testlarning asosiy vazifasi — **mavjud hisobotlar bilan MOSLIK**:

  • chek qatorlari yig'indisi = `/profit/summary` sotuv tushumi/tan narxi
  • `totals.net_*`            = `/profit/summary` revenue/cost/gross_profit
  • chegirma PROPORSIONAL taqsimlanadi: Σ(discount_share) = Order.discount_amount
  • vozvrat QAYTARILGAN sana bo'yicha ayiriladi — chek qatoriga TARQATILMAYDI
  • tan narx SNAPSHOT (`OrderItem.unit_cost`), bugungi `cost_price` EMAS
  • `view_finance` yo'q xodim (kassir) — 403

⚠️ VAQT: buyurtmalar `utc_now()` bilan seed qilinadi. "Bugun" chegarasi
   `tenant_now()` dan quriladi (Toshkent), ya'ni HOZIR har doim "bugun"
   ichida — yarim tun chegarasida ham test tebranmaydi.

Ishga tushirish:  cd backend && py -m pytest tests/test_receipt_profit.py -v
"""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from core.security import get_password_hash
from core.timeutils import utc_now
from database import Base, get_db
from main import app
from models import (
    Cafe, Category, Inventory, Order, OrderItem, Payment, Permission,
    Product, Return, ReturnItem, Role, Shift, User,
)

ADMIN_PW,  ADMIN_PHONE  = "AdminFoyda7", "+998900000071"
KASSIR_PW, KASSIR_PHONE = "KassirYuz7",  "+998900000072"

NOW = utc_now()


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE'LAR
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def eng():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)
    e.dispose()


@pytest.fixture()
def db_session(eng, monkeypatch):
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    monkeypatch.setattr(database, "SessionLocal", Session)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _perm(db, code, desc):
    p = db.query(Permission).filter(Permission.code == code).first()
    if not p:
        p = Permission(code=code, description=desc)
        db.add(p)
        db.flush()
    return p


def _role(db, name, perms):
    r = db.query(Role).filter(Role.name == name).first()
    if not r:
        r = Role(name=name, description=name)
        db.add(r)
        db.flush()
    r.permissions = perms
    db.flush()
    return r


@pytest.fixture()
def shop(db_session):
    """Magazin (store) + admin (`view_finance` BOR) + kassir (ATAYIN YO'Q)."""
    db = db_session

    p_fin    = _perm(db, "view_finance",     "Moliya")
    p_report = _perm(db, "view_reports",     "Hisobotlar")
    p_pay    = _perm(db, "process_payments", "To'lovlar")

    r_admin  = _role(db, "admin",   [p_fin, p_report, p_pay])
    # Kassirda `view_finance` YO'Q — tan narx uning ishi emas (database.py urug'i).
    r_kassir = _role(db, "cashier", [p_report, p_pay])

    cafe = Cafe(name="Do'kon F", code="dkf", access_code="100.200.71",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe)
    db.flush()

    admin = User(username="bosh71", email="a71@x.uz", full_name="Rahbar Azizbek",
                 phone=ADMIN_PHONE, hashed_password=get_password_hash(ADMIN_PW),
                 is_active=True, is_superuser=False,
                 tenant_id=cafe.id, role_id=r_admin.id)
    kassir = User(username="kassa71", email="k71@x.uz", full_name="Kassir Diyorbek",
                  phone=KASSIR_PHONE, hashed_password=get_password_hash(KASSIR_PW),
                  is_active=True, is_superuser=False,
                  tenant_id=cafe.id, role_id=r_kassir.id)
    db.add_all([admin, kassir])
    db.flush()

    cat = Category(tenant_id=cafe.id, name="Kimyo")
    db.add(cat)
    db.flush()
    # Narx 20 000 / tan narx 12 000 → marja 40%
    p1 = Product(tenant_id=cafe.id, category_id=cat.id, name="SHAMPUN 500ml",
                 price=20_000.0, cost_price=12_000.0)
    # Narx 5 000 / tan narx 4 000 → marja 20%
    p2 = Product(tenant_id=cafe.id, category_id=cat.id, name="SOVUN",
                 price=5_000.0, cost_price=4_000.0)
    db.add_all([p1, p2])
    db.flush()
    db.add_all([
        Inventory(tenant_id=cafe.id, product_id=p1.id, quantity=100.0, unit="dona"),
        Inventory(tenant_id=cafe.id, product_id=p2.id, quantity=100.0, unit="dona"),
    ])

    shift = Shift(tenant_id=cafe.id, user_id=kassir.id,
                  start_time=NOW - timedelta(hours=5), starting_cash=0.0)
    db.add(shift)
    db.flush()
    db.commit()

    return {"db": db, "cafe": cafe.id, "admin": admin.id, "kassir": kassir.id,
            "shift": shift.id, "p1": p1.id, "p2": p2.id}


_SEQ = {"n": 0}


def _sale(shop, lines, *, discount=0.0, when=None, status="completed",
          unit_cost=None, tax=0.0, service=0.0):
    """Sotuv yaratadi. `lines` — [(product_id, qty, unit_price), ...].

    `unit_cost` — qator SNAPSHOT tan narxi (None → 0, ya'ni hisobot
    `Product.cost_price` zaxirasiga tushadi: `cost_expr` tartibi).
    """
    db = shop["db"]
    _SEQ["n"] += 1
    n = _SEQ["n"]
    sub = sum(q * pr for _, q, pr in lines)
    o = Order(tenant_id=shop["cafe"], order_number=f"F-71{n:03d}", daily_number=n,
              status=status, total_amount=sub, discount_amount=discount,
              tax_amount=tax, service_charge=service,
              final_amount=sub - discount + tax + service,
              shift_id=shop["shift"], waiter_id=shop["kassir"],
              created_at=when or NOW)
    db.add(o)
    db.flush()
    for pid, qty, price in lines:
        db.add(OrderItem(tenant_id=shop["cafe"], order_id=o.id, product_id=pid,
                         quantity=qty, unit_price=price, total_price=qty * price,
                         unit_cost=(unit_cost if unit_cost is not None else 0.0)))
    db.add(Payment(tenant_id=shop["cafe"], order_id=o.id, cashier_id=shop["kassir"],
                   amount=o.final_amount, method="cash", status="paid",
                   created_at=when or NOW))
    db.commit()
    return o.id


def _ret(shop, order_id, product_id, qty, total, *, status="approved",
         when=None, order_item_id=None, unit_cost=None):
    """Vozvrat hujjati. `order_item_id` berilsa tan narx SNAPSHOT dan olinadi."""
    db = shop["db"]
    _SEQ["n"] += 1
    r = Return(tenant_id=shop["cafe"], return_number=f"RET71{_SEQ['n']:04d}",
               order_id=order_id, reason="dislike", total_amount=total,
               refund_method="cash", status=status, user_id=shop["kassir"],
               approved_at=(when or NOW) if status == "approved" else None,
               created_at=when or NOW)
    db.add(r)
    db.flush()
    if order_item_id is None:
        order_item_id = (db.query(OrderItem.id)
                         .filter(OrderItem.order_id == order_id,
                                 OrderItem.product_id == product_id)
                         .scalar())
    db.add(ReturnItem(return_id=r.id, product_id=product_id,
                      order_item_id=order_item_id, quantity=qty,
                      unit_price=total / qty if qty else 0.0, total=total))
    db.commit()
    return r.id


def _login(client, phone, pw):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": pw})
    assert r.status_code == 200, f"login yiqildi: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _list(client, hdr, **kw):
    qs = "&".join(f"{k}={v}" for k, v in kw.items())
    r = client.get(f"/api/v1/profit/by-receipt?{qs}", headers=hdr)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    return r.json()


def _detail(client, hdr, order_id):
    r = client.get(f"/api/v1/profit/by-receipt/{order_id}", headers=hdr)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    return r.json()


def _summary(client, hdr, period="today"):
    r = client.get(f"/api/v1/profit/summary?period={period}", headers=hdr)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    return r.json()


# ══════════════════════════════════════════════════════════════════════════════
# 1) CHEK FOYDASI TO'G'RI HISOBLANADI
# ══════════════════════════════════════════════════════════════════════════════

def test_chek_foydasi_snapshot_tan_narxdan(client, shop):
    """2 × 20 000 = 40 000 tushum; snapshot tan narx 12 000 → foyda 16 000, marja 40%."""
    oid = _sale(shop, [(shop["p1"], 2, 20_000.0)], unit_cost=12_000.0)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)

    d = _list(client, hdr, period="today")
    assert len(d["items"]) == 1
    it = d["items"][0]
    assert it["order_id"]   == oid
    assert it["revenue"]    == 40_000
    assert it["cost"]       == 24_000
    assert it["profit"]     == 16_000
    assert it["margin_pct"] == 40.0
    assert it["lines"]      == 1


def test_bugungi_cost_price_ozgarsa_chek_foydasi_OZGARMAYDI(client, shop):
    """Tan narx SNAPSHOT: priyomka `cost_price` ni qayta yozsa ham eski chek
    foydasi o'zgarmasligi kerak (utils/revenue.py asosiy qoidasi)."""
    oid = _sale(shop, [(shop["p1"], 2, 20_000.0)], unit_cost=12_000.0)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    oldin = _list(client, hdr, period="today")["items"][0]["profit"]

    db = shop["db"]
    db.query(Product).filter(Product.id == shop["p1"]).update({"cost_price": 19_000.0})
    db.commit()

    keyin = _list(client, hdr, period="today")["items"][0]["profit"]
    assert keyin == oldin == 16_000, (
        f"snapshot ishlamadi: {oldin} → {keyin} (bugungi cost_price olingan)")


def test_snapshot_yoq_bolsa_cost_price_zaxirasi(client, shop):
    """`unit_cost` 0/NULL (eski yozuv) → mahsulotning `cost_price` ga tushadi."""
    _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=None)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    it = _list(client, hdr, period="today")["items"][0]
    assert it["cost"]   == 12_000      # Product.cost_price
    assert it["profit"] == 8_000


def test_tafsilot_har_mahsulot_boyicha(client, shop):
    oid = _sale(shop, [(shop["p1"], 2, 20_000.0), (shop["p2"], 3, 5_000.0)],
                unit_cost=None)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _detail(client, hdr, oid)

    assert len(d["items"]) == 2
    by = {i["product_name"]: i for i in d["items"]}
    sh = by["SHAMPUN 500ml"]
    assert (sh["quantity"], sh["unit_price"], sh["revenue"]) == (2.0, 20_000, 40_000)
    assert sh["unit_cost"] == 12_000 and sh["cost"] == 24_000
    assert sh["profit"] == 16_000 and sh["margin_pct"] == 40.0
    sv = by["SOVUN"]
    assert (sv["revenue"], sv["cost"], sv["profit"]) == (15_000, 12_000, 3_000)
    assert sv["margin_pct"] == 20.0

    assert d["totals"]["revenue"] == 55_000
    assert d["totals"]["cost"]    == 36_000
    assert d["totals"]["profit"]  == 19_000
    # Jami = qatorlar yig'indisi (qoldiq yo'q)
    assert d["totals"]["profit"] == sum(i["profit"] for i in d["items"])


def test_soliq_va_xizmat_haqi_daromadga_KIRMAYDI(client, shop):
    """`final_amount` tuzog'i: soliq+xizmat haqi mahsulot daromadi EMAS."""
    oid = _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0,
                tax=2_400.0, service=2_000.0)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _detail(client, hdr, oid)
    assert d["totals"]["revenue"]      == 20_000, "soliq/xizmat haqi tushumga qo'shilgan"
    assert d["totals"]["profit"]       == 8_000
    # Ma'lumot uchun ko'rsatiladi, lekin hisobga kirmaydi
    assert d["totals"]["tax_amount"]     == 2_400
    assert d["totals"]["service_charge"] == 2_000
    assert d["totals"]["final_amount"]   == 24_400


# ══════════════════════════════════════════════════════════════════════════════
# 2) CHEGIRMALI CHEK — proporsional taqsimlash
# ══════════════════════════════════════════════════════════════════════════════

def test_chegirma_proporsional_taqsimlanadi(client, shop):
    """subtotal 55 000, chegirma 11 000 → koef 0.8.
    SHAMPUN 40 000 → 32 000 (ulush 8 000); SOVUN 15 000 → 12 000 (ulush 3 000)."""
    oid = _sale(shop, [(shop["p1"], 2, 20_000.0), (shop["p2"], 3, 5_000.0)],
                discount=11_000.0, unit_cost=None)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _detail(client, hdr, oid)

    by = {i["product_name"]: i for i in d["items"]}
    assert by["SHAMPUN 500ml"]["gross_total"]    == 40_000
    assert by["SHAMPUN 500ml"]["discount_share"] == 8_000
    assert by["SHAMPUN 500ml"]["revenue"]        == 32_000
    assert by["SOVUN"]["discount_share"]         == 3_000
    assert by["SOVUN"]["revenue"]                == 12_000

    # ⚠️ KAFOLAT: chegirma ANIQ BIR MARTA ayiriladi — qoldiq ham, ortiqcha ham yo'q
    assert d["discount"]["order_discount"]  == 11_000
    assert d["discount"]["allocated_total"] == 11_000
    assert d["discount"]["factor"]          == 0.8

    assert d["totals"]["revenue"] == 44_000      # 55 000 − 11 000
    assert d["totals"]["cost"]    == 36_000
    assert d["totals"]["profit"]  == 8_000


def test_chegirma_royxatda_ham_ayirilgan(client, shop):
    """Ro'yxat qatori ham SOF tushumni ko'rsatsin (katalog summasini emas)."""
    _sale(shop, [(shop["p1"], 2, 20_000.0)], discount=10_000.0, unit_cost=12_000.0)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    it = _list(client, hdr, period="today")["items"][0]
    assert it["revenue"] == 30_000, "chegirma ayirilmagan (katalog summasi olingan)"
    assert it["cost"]    == 24_000
    assert it["profit"]  == 6_000
    assert it["discount_amount"] == 10_000


def test_bepul_aksiya_qatori_chegirma_OLMAYDI(client, shop):
    """`total_price = 0` qator 0 chegirma oladi (utils/revenue.py kafolati)."""
    oid = _sale(shop, [(shop["p1"], 2, 20_000.0), (shop["p2"], 1, 0.0)],
                discount=8_000.0, unit_cost=None)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _detail(client, hdr, oid)
    by = {i["product_name"]: i for i in d["items"]}
    assert by["SOVUN"]["gross_total"]    == 0
    assert by["SOVUN"]["discount_share"] == 0
    assert by["SOVUN"]["revenue"]        == 0
    assert d["discount"]["allocated_total"] == 8_000


# ══════════════════════════════════════════════════════════════════════════════
# 3) QAYTARILGAN CHEK
# ══════════════════════════════════════════════════════════════════════════════

def test_vozvrat_alohida_qator_chek_qatoriga_TARQALMAYDI(client, shop):
    """Vozvrat QAYTARILGAN sanaga yoziladi → chek qatori YALPI qoladi,
    jami esa alohida "vozvrat" qatori bilan sofga keltiriladi."""
    oid = _sale(shop, [(shop["p1"], 2, 20_000.0)], unit_cost=12_000.0)
    _ret(shop, oid, shop["p1"], 1, 20_000.0)      # 1 dona qaytdi

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _list(client, hdr, period="today")

    it = d["items"][0]
    assert it["profit"] == 16_000, "chek qatori YALPI qolishi kerak"

    t = d["totals"]
    assert t["returns_count"]   == 1
    assert t["returns_revenue"] == 20_000
    assert t["returns_cost"]    == 12_000      # snapshot unit_cost × 1
    assert t["returns_profit"]  == 8_000
    # Sof = sotuv − vozvrat
    assert t["sales_profit"] == 16_000
    assert t["net_profit"]   == 8_000
    assert t["net_revenue"]  == 20_000
    assert t["net_cost"]     == 12_000


def test_vozvrat_tafsilotda_sanasi_bilan_korinadi(client, shop):
    oid = _sale(shop, [(shop["p1"], 2, 20_000.0)], unit_cost=12_000.0)
    _ret(shop, oid, shop["p1"], 1, 20_000.0)

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _detail(client, hdr, oid)
    assert len(d["returns"]) == 1
    r = d["returns"][0]
    assert r["status"]       == "approved"
    assert r["quantity"]     == 1.0
    assert r["revenue"]      == 20_000
    assert r["cost"]         == 12_000
    assert r["profit"]       == 8_000
    assert r["counted_at"],  "qaysi sanada foydadan ayrilgani ko'rinishi kerak"
    assert d["returns_totals"]["profit"] == 8_000
    # Chek qatorlari O'ZGARMAYDI — vozvrat alohida blok
    assert d["totals"]["profit"] == 16_000


def test_pending_vozvrat_SANALMAYDI(client, shop):
    """Faqat `approved` hisobga olinadi (ombor ham o'shanda tiklanadi)."""
    oid = _sale(shop, [(shop["p1"], 2, 20_000.0)], unit_cost=12_000.0)
    _ret(shop, oid, shop["p1"], 1, 20_000.0, status="pending")

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _list(client, hdr, period="today")
    assert d["totals"]["returns_count"] == 0
    assert d["totals"]["net_profit"]    == 16_000
    assert _detail(client, hdr, oid)["returns"] == []


# ══════════════════════════════════════════════════════════════════════════════
# 4) GOLDEN — `/profit/summary` bilan MOSLIK
# ══════════════════════════════════════════════════════════════════════════════

def _assert_mos(client, hdr, period="today"):
    """Panel jamisi `/profit/summary` bilan AYNI bo'lishi kerak."""
    d = _list(client, hdr, period=period)["totals"]
    s = _summary(client, hdr, period)
    assert d["net_revenue"] == s["revenue"], \
        f"tushum farq: panel {d['net_revenue']} vs summary {s['revenue']}"
    assert d["net_cost"] == s["cost"], \
        f"tan narx farq: panel {d['net_cost']} vs summary {s['cost']}"
    assert d["net_profit"] == s["gross_profit"], \
        f"foyda farq: panel {d['net_profit']} vs summary {s['gross_profit']}"
    return d, s


def test_golden_oddiy_sotuvlar_mos(client, shop):
    _sale(shop, [(shop["p1"], 2, 20_000.0)], unit_cost=12_000.0)
    _sale(shop, [(shop["p2"], 5, 5_000.0)],  unit_cost=4_000.0)
    _sale(shop, [(shop["p1"], 1, 20_000.0), (shop["p2"], 2, 5_000.0)], unit_cost=None)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    _assert_mos(client, hdr)


def test_golden_chegirmali_va_vozvratli_mos(client, shop):
    """Eng xatarli kombinatsiya: chegirma + vozvrat + snapshotsiz qator."""
    o1 = _sale(shop, [(shop["p1"], 3, 20_000.0), (shop["p2"], 4, 5_000.0)],
               discount=16_000.0, unit_cost=12_000.0)
    _sale(shop, [(shop["p2"], 10, 5_000.0)], discount=2_500.0, unit_cost=None)
    _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0)
    _ret(shop, o1, shop["p1"], 1, 20_000.0)

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d, s = _assert_mos(client, hdr)
    assert d["returns_count"] == 1
    # Sotuv − vozvrat = sof (yaxlitlashda ham mos)
    assert d["sales_profit"] - d["returns_profit"] == d["net_profit"]


def test_golden_chek_qatorlari_yigindisi_sotuv_jamisiga_TENG(client, shop):
    """Σ(sahifadagi chek foydasi) = totals.sales_profit (bir sahifaga sig'ganda).

    Bu panelning o'z ichki izchilligi: ro'yxat va jami bir xil manbadan
    kelishi kerak, aks holda ekranda qo'shilmaydigan jadval chiqadi.
    """
    _sale(shop, [(shop["p1"], 2, 20_000.0)], discount=5_000.0, unit_cost=12_000.0)
    _sale(shop, [(shop["p2"], 7, 5_000.0)],  unit_cost=4_000.0)
    _sale(shop, [(shop["p1"], 1, 20_000.0), (shop["p2"], 1, 5_000.0)],
          discount=1_000.0, unit_cost=None)

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _list(client, hdr, period="today", page_size=200)
    assert d["total"] == 3 and len(d["items"]) == 3
    assert sum(i["revenue"] for i in d["items"]) == d["totals"]["sales_revenue"]
    assert sum(i["cost"]    for i in d["items"]) == d["totals"]["sales_cost"]
    assert sum(i["profit"]  for i in d["items"]) == d["totals"]["sales_profit"]


def test_golden_tafsilot_royxat_qatori_bilan_mos(client, shop):
    oid = _sale(shop, [(shop["p1"], 3, 20_000.0), (shop["p2"], 2, 5_000.0)],
                discount=7_000.0, unit_cost=12_000.0)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    row = _list(client, hdr, period="today")["items"][0]
    det = _detail(client, hdr, oid)["totals"]
    assert (row["revenue"], row["cost"], row["profit"]) == \
           (det["revenue"], det["cost"], det["profit"])


def test_bekor_qilingan_chek_SANALMAYDI(client, shop):
    """`_sales_query` faqat `completed` ni sanaydi — panel ham shunday."""
    _sale(shop, [(shop["p1"], 2, 20_000.0)], unit_cost=12_000.0)
    _sale(shop, [(shop["p1"], 5, 20_000.0)], unit_cost=12_000.0, status="cancelled")
    _sale(shop, [(shop["p1"], 5, 20_000.0)], unit_cost=12_000.0, status="pending")

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _list(client, hdr, period="today")
    assert d["total"] == 1, "faqat completed sanalishi kerak"
    _assert_mos(client, hdr)


# ══════════════════════════════════════════════════════════════════════════════
# 5) DAVR, SARALASH, SAHIFALASH
# ══════════════════════════════════════════════════════════════════════════════

def test_davr_bugun_7kun_30kun(client, shop):
    _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0)                      # bugun
    _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0,
          when=NOW - timedelta(days=3))                                               # 7 kun
    _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0,
          when=NOW - timedelta(days=20))                                              # 30 kun
    _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0,
          when=NOW - timedelta(days=200))                                             # tashqarida

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _list(client, hdr, period="today")["total"] == 1
    assert _list(client, hdr, period="week")["total"]  == 2
    assert _list(client, hdr, period="month")["total"] == 3


def test_sana_oraligi(client, shop):
    _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0,
          when=NOW - timedelta(days=5))
    _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0,
          when=NOW - timedelta(days=40))

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d_from = (NOW - timedelta(days=7)).date().isoformat()
    d = _list(client, hdr, date_from=d_from)
    assert d["total"] == 1
    assert d["period"]["from"] == d_from


def test_saralash_foyda_marja_sana(client, shop):
    # kichik foyda, YUQORI marja (50%)
    _sale(shop, [(shop["p2"], 1, 8_000.0)], unit_cost=4_000.0)
    # katta foyda, past marja (20%)
    _sale(shop, [(shop["p1"], 5, 20_000.0)], unit_cost=16_000.0)

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)

    best = _list(client, hdr, period="today", sort="profit", order="desc")["items"]
    assert best[0]["profit"] > best[1]["profit"]
    assert best[0]["profit"] == 20_000

    worst = _list(client, hdr, period="today", sort="profit", order="asc")["items"]
    assert worst[0]["profit"] == 4_000

    marja = _list(client, hdr, period="today", sort="margin", order="desc")["items"]
    assert marja[0]["margin_pct"] == 50.0, f"marja saralash ishlamadi: {marja}"
    assert marja[1]["margin_pct"] == 20.0

    sana = _list(client, hdr, period="today", sort="date", order="desc")["items"]
    assert [i["order_id"] for i in sana] == sorted(
        (i["order_id"] for i in sana), reverse=True)


def test_notogri_saralash_400(client, shop):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = client.get("/api/v1/profit/by-receipt?sort=qweqwe", headers=hdr)
    assert r.status_code == 400, f"{r.status_code} {r.text}"


def test_sahifalash_jami_butun_davr_boyicha(client, shop):
    """Sahifa 2 ta chek ko'rsatsa ham JAMI butun davr bo'yicha bo'lishi kerak."""
    for _ in range(5):
        _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0)

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _list(client, hdr, period="today", page_size=2, page=1)
    assert len(d["items"]) == 2
    assert d["total"] == 5 and d["total_pages"] == 3
    assert d["totals"]["sales_profit"] == 5 * 8_000, "jami faqat sahifadan hisoblangan"
    # Sahifalar o'zaro TAKRORLANMASIN (barqaror tartib)
    ids = []
    for pg in (1, 2, 3):
        ids += [i["order_id"] for i in
                _list(client, hdr, period="today", page_size=2, page=pg)["items"]]
    assert len(ids) == len(set(ids)) == 5, f"sahifalar takrorlandi: {ids}"


def test_javob_vaqti_olchanadi(client, shop):
    for _ in range(10):
        _sale(shop, [(shop["p1"], 1, 20_000.0), (shop["p2"], 2, 5_000.0)],
              unit_cost=12_000.0)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _list(client, hdr, period="month")
    assert isinstance(d["elapsed_ms"], (int, float)) and d["elapsed_ms"] >= 0
    assert _detail(client, hdr, d["items"][0]["order_id"])["elapsed_ms"] >= 0


# ══════════════════════════════════════════════════════════════════════════════
# 6) RUXSAT va TENANT
# ══════════════════════════════════════════════════════════════════════════════

def test_kassir_403(client, shop):
    """Tan narx kassirning ishi emas — `view_finance` yo'q → 403."""
    oid = _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0)
    hdr = _login(client, KASSIR_PHONE, KASSIR_PW)

    r1 = client.get("/api/v1/profit/by-receipt?period=today", headers=hdr)
    assert r1.status_code == 403, f"kassir chek foydasini ko'rdi: {r1.status_code} {r1.text}"
    r2 = client.get(f"/api/v1/profit/by-receipt/{oid}", headers=hdr)
    assert r2.status_code == 403, f"kassir tan narxni ko'rdi: {r2.status_code} {r2.text}"


def test_begona_tenant_korolmaydi(client, shop, db_session):
    """Boshqa do'kon admini na ro'yxatda, na tafsilotda ko'rmasligi kerak."""
    oid = _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0)

    db = db_session
    other = Cafe(name="Begona", code="bgn71", access_code="100.200.72",
                 business_type="store", subscription_plan="pro", is_active=True)
    db.add(other)
    db.flush()
    r_admin = db.query(Role).filter(Role.name == "admin").first()
    db.add(User(username="bgn71", email="b71@x.uz", full_name="Begona Admin",
                phone="+998900000073", hashed_password=get_password_hash(ADMIN_PW),
                is_active=True, is_superuser=False,
                tenant_id=other.id, role_id=r_admin.id))
    db.commit()

    hdr = _login(client, "+998900000073", ADMIN_PW)
    assert _list(client, hdr, period="month")["total"] == 0
    r = client.get(f"/api/v1/profit/by-receipt/{oid}", headers=hdr)
    assert r.status_code == 404, f"{r.status_code} {r.text}"


def test_bosh_davr_nol_qaytaradi(client, shop):
    """Sotuv yo'q davr — 0 bilan javob bersin (bo'linish xatosi bo'lmasin)."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _list(client, hdr, period="today")
    assert d["items"] == [] and d["total"] == 0
    t = d["totals"]
    assert t["sales_revenue"] == 0 and t["net_profit"] == 0
    assert t["sales_margin_pct"] == 0 and t["net_margin_pct"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# 7) UNUMDORLIK — N+1 YO'Q va javob vaqti
# ══════════════════════════════════════════════════════════════════════════════

def _count_queries(eng, fn):
    """`fn()` bajarilganda bazaga ketgan SQL so'rovlari sonini qaytaradi."""
    from sqlalchemy import event
    box = {"n": 0}

    def _before(conn, cursor, statement, params, ctx, many):
        box["n"] += 1

    event.listen(eng, "before_cursor_execute", _before)
    try:
        out = fn()
    finally:
        event.remove(eng, "before_cursor_execute", _before)
    return box["n"], out


def test_n_plus_1_yoq_sorov_soni_chek_soniga_BOGLIQ_EMAS(client, shop, eng):
    """ASOSIY UNUMDORLIK QULFI: 10 chek va 110 chek uchun SQL so'rov soni AYNI.

    Agar biror joyda lazy yuklash (Order/Product obyekti) paydo bo'lsa, so'rov
    soni chek soni bilan birga o'sadi — shu test darhol yiqiladi. 30 kunlik
    davrda yuzlab chek bo'lishi mumkin, N+1 esa sahifani o'ldiradi.
    """
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)

    for _ in range(10):
        _sale(shop, [(shop["p1"], 1, 20_000.0), (shop["p2"], 2, 5_000.0)],
              unit_cost=12_000.0)
    n_kichik, d1 = _count_queries(eng, lambda: _list(client, hdr, period="month", page_size=200))
    assert d1["total"] == 10

    for _ in range(100):
        _sale(shop, [(shop["p1"], 1, 20_000.0), (shop["p2"], 2, 5_000.0)],
              unit_cost=12_000.0)
    n_katta, d2 = _count_queries(eng, lambda: _list(client, hdr, period="month", page_size=200))
    assert d2["total"] == 110

    assert n_kichik == n_katta, (
        f"N+1 BOR: 10 chekda {n_kichik} so'rov, 110 chekda {n_katta} so'rov "
        f"(chek soniga bog'liq bo'lmasligi kerak)")
    # Yuqori chegara — endpoint 3 ta asosiy so'rov qiladi (ro'yxat, count,
    # `_product_summary`) + vozvrat + auth/feature tekshiruvlari.
    assert n_katta <= 25, f"so'rov soni kutilmaganda ko'p: {n_katta}"


def test_tafsilot_n_plus_1_yoq(client, shop, eng):
    """10 qatorli chek tafsiloti ham mahsulot nomi uchun qator-qator so'rov
    qilmasligi kerak (nom asosiy so'rovda `join(Product)` bilan keladi)."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    oid1 = _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0)
    oid2 = _sale(shop, [(shop["p1"], i + 1, 20_000.0) for i in range(5)]
                       + [(shop["p2"], i + 1, 5_000.0) for i in range(5)],
                 discount=5_000.0, unit_cost=12_000.0)

    n1, _ = _count_queries(eng, lambda: _detail(client, hdr, oid1))   # 1 qator
    n2, d = _count_queries(eng, lambda: _detail(client, hdr, oid2))   # 10 qator
    assert len(d["items"]) == 10
    assert n1 == n2, f"tafsilotda N+1: 1 qatorda {n1}, 10 qatorda {n2} so'rov"


def test_javob_vaqti_30_kun_300_chek(client, shop):
    """30 kunlik davr, 300 chek × 2 qator — javob vaqti o'lchanadi.

    Chegara ATAYIN keng (SQLite + TestClient + CI mashinasi sekin bo'lishi
    mumkin): maqsad "aniq millisekund" emas, UNUMDORLIK REGRESSIYASINI
    (N+1 yoki to'liq jadval skani) ushlash. Aniq son `elapsed_ms` da qaytadi
    va UI'da ko'rsatiladi.
    """
    import time as _t
    for i in range(300):
        _sale(shop, [(shop["p1"], 1, 20_000.0), (shop["p2"], 2, 5_000.0)],
              unit_cost=12_000.0, when=NOW - timedelta(days=i % 29))

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    t0 = _t.perf_counter()
    d = _list(client, hdr, period="month", page_size=50)
    wall_ms = (_t.perf_counter() - t0) * 1000

    assert d["total"] == 300 and len(d["items"]) == 50
    print(f"\n[o'lchov] 300 chek / 30 kun: server {d['elapsed_ms']} ms, "
          f"to'liq so'rov {wall_ms:.0f} ms")
    assert d["elapsed_ms"] < 3000, f"server juda sekin: {d['elapsed_ms']} ms"
    # Jami baribir butun davr bo'yicha (sahifa 50 ta bo'lsa ham)
    assert d["totals"]["receipts_count"] == 300


def test_mahsulot_asosli_turda_izoh_YOQ(client, shop):
    """store/supermarket/restoran — jami `/profit/summary` bilan AYNI, izoh kerak emas."""
    _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _list(client, hdr, period="today")
    assert d["business_type"] == "store"
    assert d["note"] is None


def test_xizmat_asosli_turda_izoh_BOR(client, shop):
    """Salon/fitnes/mehmonxonada `/profit/summary` uchrashuv asosida hisoblaydi.

    Panel esa CHEK bo'yicha ishlaydi — farq NORMAL, lekin ekranda tushuntirilishi
    SHART, aks holda do'konchi raqamni xato deb o'ylaydi.
    """
    _sale(shop, [(shop["p1"], 1, 20_000.0)], unit_cost=12_000.0)
    db = shop["db"]
    db.query(Cafe).filter(Cafe.id == shop["cafe"]).update({"business_type": "salon"})
    db.commit()

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    d = _list(client, hdr, period="today")
    assert d["business_type"] == "salon"
    assert d["note"] and "farq qilishi normal" in d["note"]
    # Chek qatorlari baribir to'g'ri (mahsulot sotuvi bor)
    assert d["items"][0]["profit"] == 8_000
