"""XODIM BO'YICHA SAVDO VA BONUS — `/profit/staff-sales` + `/settings/staff-bonus`.

MANHATTAN (2026-10): bonus har 1 mln sof savdoga 50 000, faqat bonusli
kategoriyalardan (kiyim ha, atir yo'q). Qulflanadigan qoidalar:

  • sotuvchi — `Order.waiter_id` (to'lovni olgan kassir EMAS)
  • qator sof tushumi — `_REVENUE_EXPR` (chegirma proporsional)
  • vozvrat QAYTARILGAN kunda, o'sha tovarni SOTGAN xodimdan ayiriladi
  • sozlama bo'sh → hammasi bonusli; ichki kategoriya ham bonusli
  • Σ xodimlar sof savdosi = `/profit/summary` revenue (GOLDEN)
  • `/analytics/cashier-report` o'zgarmagan (Payment.cashier_id bo'yicha)

Seed vaqti `tenant_now()` — sababi test_receipt_profit.py boshidagi izohda.

Ishga tushirish:  cd backend && py -m pytest tests/test_staff_sales.py -v
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
from core.timeutils import tenant_now
from database import Base, get_db
from main import app
from models import (
    Cafe, Category, Order, OrderItem, Payment, Permission,
    Product, Return, ReturnItem, Role, User,
)

ADMIN_PW,  ADMIN_PHONE  = "AdminBonus8", "+998900000081"
KASSIR_PW, KASSIR_PHONE = "KassirBon8",  "+998900000082"

NOW = tenant_now()
YESTERDAY = NOW - timedelta(days=1)


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


def _perm(db, code):
    p = db.query(Permission).filter(Permission.code == code).first()
    if not p:
        p = Permission(code=code, description=code)
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
    """Kiyim do'koni: admin (view_finance) + 2 sotuvchi + kassir (moliyasiz).

    Kategoriyalar: KIYIM → KO'YLAK (ichki), ATIR. Boshqa do'kon — izolyatsiya.
    """
    db = db_session
    p_fin, p_an, p_pay = _perm(db, "view_finance"), _perm(db, "view_analytics"), _perm(db, "process_payments")
    r_admin  = _role(db, "admin",   [p_fin, p_an, p_pay])
    r_kassir = _role(db, "cashier", [p_pay])

    cafe  = Cafe(name="Kiyim", code="kiy81", access_code="100.200.81",
                 business_type="store", subscription_plan="pro", is_active=True)
    other = Cafe(name="Begona", code="beg81", access_code="100.200.82",
                 business_type="store", subscription_plan="pro", is_active=True)
    db.add_all([cafe, other])
    db.flush()

    def _u(name, phone, pw, role):
        u = User(username=name, email=f"{name}@x.uz", full_name=name.upper(), phone=phone,
                 hashed_password=get_password_hash(pw), is_active=True, is_superuser=False,
                 tenant_id=cafe.id, role_id=role.id)
        db.add(u)
        db.flush()
        return u

    admin  = _u("egasi",  ADMIN_PHONE,  ADMIN_PW,  r_admin)
    kassir = _u("kassir", KASSIR_PHONE, KASSIR_PW, r_kassir)
    ali    = _u("ali",    "+998900000083", "Sotuvchi1", r_kassir)
    vali   = _u("vali",   "+998900000084", "Sotuvchi2", r_kassir)

    kiyim = Category(tenant_id=cafe.id, name="KIYIM")
    atir  = Category(tenant_id=cafe.id, name="ATIR")
    db.add_all([kiyim, atir])
    db.flush()
    koylak = Category(tenant_id=cafe.id, name="KO'YLAK", parent_id=kiyim.id)
    begona_cat = Category(tenant_id=other.id, name="BEGONA")
    db.add_all([koylak, begona_cat])
    db.flush()

    shim = Product(tenant_id=cafe.id, category_id=kiyim.id,  name="SHIM",    price=500_000.0, cost_price=300_000.0)
    kyl  = Product(tenant_id=cafe.id, category_id=koylak.id, name="KO'YLAK", price=200_000.0, cost_price=100_000.0)
    parf = Product(tenant_id=cafe.id, category_id=atir.id,   name="ATIR",    price=300_000.0, cost_price=150_000.0)
    nocat = Product(tenant_id=cafe.id, category_id=None,     name="PAKET",   price=1_000.0,   cost_price=0.0)
    db.add_all([shim, kyl, parf, nocat])
    db.commit()

    return {"db": db, "cafe": cafe.id, "admin": admin.id, "kassir": kassir.id,
            "ali": ali.id, "vali": vali.id,
            "kiyim": kiyim.id, "koylak": koylak.id, "atir": atir.id, "begona_cat": begona_cat.id,
            "shim": shim.id, "kyl": kyl.id, "parf": parf.id, "nocat": nocat.id}


_SEQ = {"n": 0}


def _sale(shop, seller, lines, *, discount=0.0, when=None, cashier=None):
    """`lines` — [(product_id, qty, unit_price)]. To'lovni `cashier` oladi
    (berilmasa sotuvchining o'zi)."""
    db = shop["db"]
    _SEQ["n"] += 1
    n = _SEQ["n"]
    sub = sum(q * p for _, q, p in lines)
    o = Order(tenant_id=shop["cafe"], order_number=f"S-81{n:04d}", daily_number=n,
              status="completed", total_amount=sub, discount_amount=discount,
              final_amount=sub - discount, waiter_id=seller, created_at=when or NOW)
    db.add(o)
    db.flush()
    for pid, q, p in lines:
        db.add(OrderItem(tenant_id=shop["cafe"], order_id=o.id, product_id=pid,
                         quantity=q, unit_price=p, total_price=q * p, unit_cost=0.0))
    db.add(Payment(tenant_id=shop["cafe"], order_id=o.id, cashier_id=cashier or seller,
                   amount=o.final_amount, method="cash", status="paid", created_at=when or NOW))
    db.commit()
    return o.id


def _ret(shop, order_id, product_id, qty, total, *, when=None, status="approved"):
    db = shop["db"]
    _SEQ["n"] += 1
    oi = (db.query(OrderItem.id)
          .filter(OrderItem.order_id == order_id, OrderItem.product_id == product_id).scalar())
    r = Return(tenant_id=shop["cafe"], return_number=f"RET81{_SEQ['n']:04d}", order_id=order_id,
               reason="dislike", total_amount=total, refund_method="cash", status=status,
               user_id=shop["kassir"], approved_at=(when or NOW) if status == "approved" else None,
               created_at=when or NOW)
    db.add(r)
    db.flush()
    db.add(ReturnItem(return_id=r.id, product_id=product_id, order_item_id=oi, quantity=qty,
                      unit_price=total / qty, total=total))
    db.commit()
    return r.id


def _login(client, phone, pw):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _report(client, hdr, **kw):
    qs = "&".join(f"{k}={v}" for k, v in (kw or {"period": "today"}).items())
    r = client.get(f"/api/v1/profit/staff-sales?{qs}", headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


def _row(d, seller_id):
    rows = [i for i in d["items"] if i["seller_id"] == seller_id]
    assert len(rows) == 1, d["items"]
    return rows[0]


def _set_bonus(client, hdr, ids, rate=50_000):
    r = client.patch("/api/v1/settings/staff-bonus", headers=hdr,
                     json={"category_ids": ids, "rate_per_million": rate})
    assert r.status_code == 200, r.text
    return r.json()


# ══════════════════════════════════════════════════════════════════════════════
# 1) ISHCHI SAVDOSI
# ══════════════════════════════════════════════════════════════════════════════

def test_xodim_savdosi_waiter_id_boyicha_chegirma_bilan(client, shop):
    """Ali: 500k + 300k − 80k chegirma = 720k. Vali: 200k. Sotuvchi — waiter_id."""
    _sale(shop, shop["ali"], [(shop["shim"], 1, 500_000.0), (shop["parf"], 1, 300_000.0)], discount=80_000.0)
    _sale(shop, shop["vali"], [(shop["kyl"], 1, 200_000.0)])
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)

    d = _report(client, hdr)
    ali, vali = _row(d, shop["ali"]), _row(d, shop["vali"])
    assert ali["name"] == "ALI"
    assert ali["sales"] == 720_000 and ali["net"] == 720_000 and ali["orders_count"] == 1
    assert vali["net"] == 200_000
    assert d["totals"]["net"] == 920_000
    assert d["items"][0]["seller_id"] == shop["ali"]          # ko'p sotgan birinchi


def test_tolovni_boshqa_kassir_olsa_ham_savdo_sotuvchiga(client, shop):
    """GOLDEN: kassir hisoboti Payment.cashier_id bo'yicha O'ZGARMAGAN,
    yangi hisobot esa savdoni SOTUVCHIGA yozadi."""
    _sale(shop, shop["ali"], [(shop["shim"], 1, 500_000.0)], cashier=shop["kassir"])
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)

    d = _report(client, hdr)
    assert [i["seller_id"] for i in d["items"]] == [shop["ali"]]

    r = client.get("/api/v1/analytics/cashier-report?period=today", headers=hdr)
    assert r.status_code == 200, r.text
    ca = r.json()
    assert [c["cashier_id"] for c in ca] == [shop["kassir"]]
    assert ca[0]["total"] == 500_000 and ca[0]["cash"] == 500_000 and ca[0]["transactions"] == 1


def test_kun_boyicha_ajratiladi(client, shop):
    _sale(shop, shop["ali"], [(shop["shim"], 1, 500_000.0)], when=YESTERDAY)
    _sale(shop, shop["ali"], [(shop["kyl"], 1, 200_000.0)])
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)

    d = _report(client, hdr, period="week")
    days = {x["date"]: x["net"] for x in _row(d, shop["ali"])["days"]}
    assert days == {YESTERDAY.date().isoformat(): 500_000, NOW.date().isoformat(): 200_000}


# ══════════════════════════════════════════════════════════════════════════════
# 2) VOZVRAT — QAYTARILGAN KUNDA, SOTGAN XODIMDAN
# ══════════════════════════════════════════════════════════════════════════════

def test_vozvrat_qaytarilgan_kunda_sotgan_xodimdan_ayriladi(client, shop):
    """Kecha Ali sotdi, bugun Kassir qaytarib oldi → bugun ALI dan −500k,
    kechagi hisobot o'zgarmaydi."""
    oid = _sale(shop, shop["ali"], [(shop["shim"], 1, 500_000.0)], when=YESTERDAY)
    _ret(shop, oid, shop["shim"], 1, 500_000.0, when=NOW)
    _sale(shop, shop["ali"], [(shop["kyl"], 1, 200_000.0)])
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)

    today = _row(_report(client, hdr), shop["ali"])
    assert today["sales"] == 200_000 and today["returns"] == 500_000
    assert today["net"] == -300_000 and today["returns_count"] == 1
    assert today["bonus"] == 0                                # manfiy baza → 0

    yd = YESTERDAY.date().isoformat()
    kecha = _row(_report(client, hdr, date_from=yd, date_to=yd), shop["ali"])
    assert kecha["sales"] == 500_000 and kecha["returns"] == 0 and kecha["net"] == 500_000

    # Kassir (vozvratni rasmiylashtirgan) — ro'yxatda YO'Q
    assert shop["kassir"] not in [i["seller_id"] for i in _report(client, hdr)["items"]]


def test_tasdiqlanmagan_vozvrat_ayrilmaydi(client, shop):
    oid = _sale(shop, shop["ali"], [(shop["shim"], 1, 500_000.0)])
    _ret(shop, oid, shop["shim"], 1, 500_000.0, status="pending")
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _row(_report(client, hdr), shop["ali"])["net"] == 500_000


# ══════════════════════════════════════════════════════════════════════════════
# 3) BONUSLI / BOSHQA
# ══════════════════════════════════════════════════════════════════════════════

def test_sozlama_bosh_bolsa_hammasi_bonusli(client, shop):
    _sale(shop, shop["ali"], [(shop["shim"], 1, 500_000.0), (shop["parf"], 1, 300_000.0),
                              (shop["nocat"], 2, 1_000.0)])
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)

    d = _report(client, hdr)
    assert d["config"]["all_bonus"] is True and d["config"]["rate_per_million"] == 50_000
    ali = _row(d, shop["ali"])
    assert ali["bonus_net"] == 802_000 and ali["other_net"] == 0
    assert ali["bonus"] == round(802_000 * 0.05)


def test_bonusli_va_boshqa_ajratiladi_ichki_kategoriya_bilan(client, shop):
    """KIYIM tanlandi → KO'YLAK (ichki) ham bonusli; ATIR va kategoriyasiz — boshqa.
    Chegirma qatorlarga proporsional: 1 000 000 subtotal, 100 000 chegirma (10%)."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    _set_bonus(client, hdr, [shop["kiyim"]])
    _sale(shop, shop["ali"], [(shop["shim"], 1, 500_000.0), (shop["kyl"], 1, 200_000.0),
                              (shop["parf"], 1, 300_000.0)], discount=100_000.0)

    d = _report(client, hdr)
    ali = _row(d, shop["ali"])
    assert ali["bonus_net"] == 630_000          # (500k+200k) × 0.9
    assert ali["other_net"] == 270_000          # 300k × 0.9
    assert ali["bonus"] == 31_500               # 630 000 × 50 000 / 1 000 000
    assert d["config"]["all_bonus"] is False
    assert d["config"]["categories"] == [{"id": shop["kiyim"], "name": "KIYIM"}]


def test_bonus_stavkasi_va_vozvrat_kategoriyasi(client, shop):
    """2 mln kiyim sotuvi, 0.5 mln kiyim vozvrati, atir vozvrati boshqadan ayriladi."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    _set_bonus(client, hdr, [shop["kiyim"]], rate=50_000)
    oid = _sale(shop, shop["vali"], [(shop["shim"], 4, 500_000.0), (shop["parf"], 1, 300_000.0)])
    _ret(shop, oid, shop["shim"], 1, 500_000.0)
    _ret(shop, oid, shop["parf"], 1, 300_000.0)

    v = _row(_report(client, hdr), shop["vali"])
    assert v["bonus_net"] == 1_500_000 and v["other_net"] == 0
    assert v["bonus"] == 75_000
    assert v["returns"] == 800_000 and v["returns_count"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# 4) GOLDEN — MOLIYA BILAN MOSLIK
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("period", ["today", "week", "month"])
def test_jami_profit_summary_bilan_teng(client, shop, period):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    _set_bonus(client, hdr, [shop["kiyim"]])
    o1 = _sale(shop, shop["ali"], [(shop["shim"], 1, 500_000.0), (shop["parf"], 1, 300_000.0)],
               discount=33_333.0, when=YESTERDAY)
    _sale(shop, shop["vali"], [(shop["kyl"], 3, 200_000.0)], discount=1_234.0)
    _sale(shop, None, [(shop["nocat"], 5, 1_000.0)])               # sotuvchisiz (QR menyu kabi)
    _ret(shop, o1, shop["parf"], 1, 290_000.0)

    d = _report(client, hdr, period=period)
    s = client.get(f"/api/v1/profit/summary?period={period}", headers=hdr).json()
    assert d["totals"]["net"] == s["revenue"], (d["totals"], s)
    assert d["totals"]["returns"] == s["returns"]
    assert abs(d["totals"]["bonus_net"] + d["totals"]["other_net"] - d["totals"]["net"]) <= 1
    assert sum(i["net"] for i in d["items"]) == pytest.approx(d["totals"]["net"], abs=len(d["items"]))
    assert any(i["seller_id"] is None and i["name"] == "Belgilanmagan" for i in d["items"])


# ══════════════════════════════════════════════════════════════════════════════
# 5) SOZLAMA VA RUXSAT
# ══════════════════════════════════════════════════════════════════════════════

def test_sozlama_saqlanadi_va_oqiladi(client, shop):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    g = client.get("/api/v1/settings/staff-bonus", headers=hdr).json()
    assert g["category_ids"] == [] and g["all_bonus"] is True and g["rate_per_million"] == 50_000
    names = {c["name"] for c in g["categories"]}
    assert names == {"KIYIM", "ATIR", "KO'YLAK"}                    # begona do'kon YO'Q

    _set_bonus(client, hdr, [shop["kiyim"], shop["kiyim"]], rate=40_000)
    g = client.get("/api/v1/settings/staff-bonus", headers=hdr).json()
    assert g["category_ids"] == [shop["kiyim"]] and g["rate_per_million"] == 40_000

    _set_bonus(client, hdr, [])                                     # tozalash → hammasi bonusli
    assert client.get("/api/v1/settings/staff-bonus", headers=hdr).json()["all_bonus"] is True


def test_begona_kategoriya_va_notogri_stavka_rad_etiladi(client, shop):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = client.patch("/api/v1/settings/staff-bonus", headers=hdr,
                     json={"category_ids": [shop["begona_cat"]]})
    assert r.status_code == 400
    r = client.patch("/api/v1/settings/staff-bonus", headers=hdr,
                     json={"category_ids": [], "rate_per_million": -1})
    assert r.status_code == 400


def test_moliyasiz_xodim_403(client, shop):
    hdr = _login(client, KASSIR_PHONE, KASSIR_PW)
    assert client.get("/api/v1/profit/staff-sales?period=today", headers=hdr).status_code == 403
    assert client.get("/api/v1/settings/staff-bonus", headers=hdr).status_code == 403
    assert client.patch("/api/v1/settings/staff-bonus", headers=hdr,
                        json={"category_ids": []}).status_code == 403
