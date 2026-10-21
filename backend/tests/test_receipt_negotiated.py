"""CHEKDA KELISHILGAN NARX — `biz_meta['cart']` snapshot (feature/receipt-negotiated-price).

MANHATTAN (2026-10): kassir deyarli har chekda qator narxini tushiradi
(245 000 → 220 000). Server bu tushirishni UMUMIY chegirma qilib saqlaydi,
qator narxi esa snapshot'da. Qulflanadigan qoidalar:

  • chek qatori = (_priceNew yoki price) × qty, butun so'm
  • "Chegirmasiz" = qatorlar yig'indisi, "Chegirma" = QOLGAN chegirma
  • vozvrat CHEKDA YOZILGAN summa bilan (mijoz chekka qaraydi)
  • zaxira: snapshot yo'q / mos emas / buzuq / kelishuv chegirmadan katta /
    narx tushirilmagan → chek va vozvrat AVVALGIDEK (GOLDEN)
  • hisobotlar TEGILMAYDI (ulush qoidasi, utils/revenue)

Prod namunasi: chek #4804 (MANHATTAN, 2026-10-21) — 245/380/295 ming,
chegirma 70 000, snapshot 220/360/270 ming.

Ishga tushirish:  cd backend && py -m pytest tests/test_receipt_negotiated.py -v
"""
import os
import sys
from datetime import timedelta
from types import SimpleNamespace

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
from models import Cafe, Inventory, Order, OrderItem, Payment, Permission, Product, Role, Shift, User
from routers.returns import net_line_totals, receipt_line_totals, refund_line_totals
from services.escpos_service import _sub_label
from utils.revenue import period_totals

PW, PHONE = "AdminKelish9", "+998900000091"
NOW = utc_now()


# ══════════════════════════════════════════════════════════════════════════════
# 1) FUNKSIYA — bazasiz (SimpleNamespace)
# ══════════════════════════════════════════════════════════════════════════════

def _o(disc, cart):
    return SimpleNamespace(discount_amount=disc, biz_meta=({"cart": cart} if cart is not None else None))


def _i(iid, pid, total, qty=1.0, unit=None):
    return SimpleNamespace(id=iid, product_id=pid, total_price=total, quantity=qty,
                           unit_price=unit if unit is not None else total / qty)


def _s(pid, price, new=None, qty=1, **kw):
    return {"id": pid, "price": price, "qty": qty, "_priceNew": new, **kw}


ITEMS_4804 = [_i(1, 3864, 245_000.0), _i(2, 4115, 380_000.0), _i(3, 4237, 295_000.0)]
CART_4804 = [_s(3864, 245_000, 220_000), _s(4115, 380_000, 360_000), _s(4237, 295_000, 270_000)]


def test_chek_4804_qatorlar_kelishilgan_narxda():
    r = receipt_line_totals(_o(70_000.0, CART_4804), ITEMS_4804)
    assert r["lines"] == {1: 220_000.0, 2: 360_000.0, 3: 270_000.0}
    assert r["subtotal"] == 850_000.0
    assert r["other_discount"] == 0.0            # "Chegirma" qatori chiqmaydi
    assert r["negotiated"] == 70_000.0
    # vozvrat ham chekdagi summa
    assert refund_line_totals(_o(70_000.0, CART_4804), ITEMS_4804) == {1: 220_000.0, 2: 360_000.0, 3: 270_000.0}


def test_snapshot_tartibi_item_id_boyicha():
    """order.items istalgan tartibda kelsa ham — snapshot qatorlari id tartibida."""
    r = receipt_line_totals(_o(70_000.0, CART_4804), list(reversed(ITEMS_4804)))
    assert r["lines"] == {1: 220_000.0, 2: 360_000.0, 3: 270_000.0}


def test_GOLDEN_eski_chek_snapshotsiz():
    o = _o(70_000.0, None)
    assert receipt_line_totals(o, ITEMS_4804) is None
    assert refund_line_totals(o, ITEMS_4804) == net_line_totals(o, ITEMS_4804)   # ulush qoidasi


def test_GOLDEN_narx_tushirilmagan_faqat_foiz():
    """Snapshot bor, lekin kelishuv yo'q (faqat umumiy %) — chek avvalgidek."""
    cart = [_s(3864, 245_000), _s(4115, 380_000)]
    items = ITEMS_4804[:2]
    o = _o(62_500.0, cart)
    assert receipt_line_totals(o, items) is None
    assert refund_line_totals(o, items) == net_line_totals(o, items)


def test_GOLDEN_chegirmasiz_chek():
    cart = [_s(3864, 245_000)]
    assert receipt_line_totals(_o(0.0, cart), ITEMS_4804[:1]) is None


@pytest.mark.parametrize("nom,cart,disc", [
    ("qator_soni_kam",       CART_4804[:2], 70_000.0),
    ("mahsulot_boshqa",      [_s(9999, 245_000, 220_000)] + CART_4804[1:], 70_000.0),
    ("summa_total_dan_farq", [_s(3864, 250_000, 220_000)] + CART_4804[1:], 75_000.0),
    ("kelishuv_chegirmadan_katta", CART_4804, 50_000.0),
    ("matn_narx",            [_s(3864, "abc", 220_000)] + CART_4804[1:], 70_000.0),
    ("manfiy_narx",          [_s(3864, 245_000, -5)] + CART_4804[1:], 70_000.0),
    ("dict_emas",            ["x", CART_4804[1], CART_4804[2]], 70_000.0),
    ("cart_royxat_emas",     {"a": 1}, 70_000.0),
])
def test_buzilgan_snapshot_zaxira(nom, cart, disc):
    o = _o(disc, cart)
    assert receipt_line_totals(o, ITEMS_4804) is None, nom
    assert refund_line_totals(o, ITEMS_4804) == net_line_totals(o, ITEMS_4804), nom


def test_biz_meta_boshqa_kalitlar_bilan():
    o = SimpleNamespace(discount_amount=70_000.0,
                        biz_meta={"applied_promotions": [3], "cart": CART_4804})
    assert receipt_line_totals(o, ITEMS_4804)["subtotal"] == 850_000.0


def test_kg_qatori():
    """Og'irlik: savatda price = qator jami (14 999), qty = 1; serverda
    quantity = 0.566, total_price = round(0.566 × 26 500, 2) = 14 999."""
    items = [_i(1, 10, 14_999.0, qty=0.566, unit=26_500.0), _i(2, 11, 50_000.0)]
    cart = [_s(10, 14_999.0, 14_000.0, qty=1, _weight=0.566, _unit="kg", _unitPrice=26_500.0),
            _s(11, 50_000.0)]
    r = receipt_line_totals(_o(999.0, cart), items)
    assert r["lines"] == {1: 14_000.0, 2: 50_000.0}
    assert r["subtotal"] == 64_000.0 and r["other_discount"] == 0.0


def test_kelishuv_va_qoshimcha_foiz():
    """245 000 → 220 000 + 100 000 lik qator, ustiga 10% qo'lda.
    POS: 10% × 345 000 = 34 500 + kelishuv 25 000 → discount_amount 59 500."""
    items = [_i(1, 3864, 245_000.0), _i(2, 4115, 100_000.0)]
    cart = [_s(3864, 245_000, 220_000), _s(4115, 100_000)]
    o = _o(59_500.0, cart)
    r = receipt_line_totals(o, items)
    assert r["lines"] == {1: 220_000.0, 2: 100_000.0}
    assert r["subtotal"] == 320_000.0
    assert r["other_discount"] == 34_500.0          # "Chegirma: -34 500"
    # Chegirmasiz − Chegirma = to'langan (UMUMIY)
    assert r["subtotal"] - r["other_discount"] == 345_000.0 - 59_500.0
    ref = refund_line_totals(o, items)
    assert round(sum(ref.values()), 2) == 285_500.0  # qaytarilgan pul = to'langan
    assert ref[1] == round(220_000 * 285_500 / 320_000, 2)


def test_oshirilgan_narx_qator():
    """Narx oshirilgan qator: serverda total_price allaqachon yangi narxda."""
    items = [_i(1, 3864, 260_000.0), _i(2, 4115, 380_000.0)]
    cart = [_s(3864, 245_000, 260_000), _s(4115, 380_000, 360_000)]
    r = receipt_line_totals(_o(20_000.0, cart), items)
    assert r["lines"] == {1: 260_000.0, 2: 360_000.0} and r["other_discount"] == 0.0


def test_yaxlitlash_butun_som():
    """Kasr chiqmasin: 3 × 33 333.4 = 100 000.2 → 100 000."""
    items = [_i(1, 1, 120_000.0, qty=3, unit=40_000.0)]
    cart = [_s(1, 40_000, 33_333.4, qty=3)]
    r = receipt_line_totals(_o(19_999.8, cart), items)
    assert r["lines"] == {1: 100_000.0}
    assert r["other_discount"] == 0.0


def test_escpos_yorliq():
    assert _sub_label({"discount": 0}) == "Jami:"                       # GOLDEN
    assert _sub_label({"discount": 5_000}) == "Chegirmasiz:"
    assert _sub_label({"discount": 0, "had_discount": True}) == "Chegirmasiz:"


# ══════════════════════════════════════════════════════════════════════════════
# 2) API — /orders/{id}/receipt, /returns/lookup, vozvrat yaratish
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def eng():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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


@pytest.fixture()
def shop(db_session):
    db = db_session
    perms = []
    for c in ("process_payments", "manage_shifts", "view_reports", "view_finance", "manage_inventory"):
        p = db.query(Permission).filter(Permission.code == c).first()
        if not p:
            p = Permission(code=c, description=c)
            db.add(p)
            db.flush()
        perms.append(p)
    role = db.query(Role).filter(Role.name == "admin").first()
    if not role:
        role = Role(name="admin", description="admin")
        db.add(role)
    role.permissions = perms
    cafe = Cafe(name="MANH", code="manh9", access_code="100.200.91",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe)
    db.flush()
    u = User(username="manh9", email="m9@x.uz", full_name="Admin", phone=PHONE,
             hashed_password=get_password_hash(PW), is_active=True, tenant_id=cafe.id, role_id=role.id)
    db.add(u)
    db.flush()
    db.add(Shift(tenant_id=cafe.id, user_id=u.id, start_time=NOW - timedelta(hours=2), starting_cash=0.0))
    prods = []
    for nm, pr in (("SHIM", 245_000.0), ("KURTKA", 380_000.0), ("SVITR", 295_000.0)):
        p = Product(tenant_id=cafe.id, name=nm, price=pr, cost_price=100_000.0)
        db.add(p)
        db.flush()
        db.add(Inventory(tenant_id=cafe.id, product_id=p.id, quantity=100.0, unit="dona"))
        prods.append(p)
    db.commit()
    return {"db": db, "cafe": cafe.id, "user": u.id, "prods": prods, "n": [0]}


def _sold(shop, lines, discount, cart=True):
    """lines: [(product, qty, catalog, negotiated_or_None)]"""
    db = shop["db"]
    shop["n"][0] += 1
    sub = sum(q * c for _, q, c, _n in lines)
    meta = None
    if cart:
        meta = {"cart": [{"id": p.id, "name": p.name, "price": c, "qty": q, "_priceNew": n}
                         for p, q, c, n in lines]}
    o = Order(tenant_id=shop["cafe"], order_number=f"M-{shop['n'][0]}", daily_number=shop["n"][0],
              status="completed", total_amount=sub, discount_amount=discount,
              final_amount=round(sub - discount, 2), waiter_id=shop["user"], biz_meta=meta,
              created_at=NOW - timedelta(minutes=30))
    db.add(o)
    db.flush()
    ois = []
    for p, q, c, _n in lines:
        oi = OrderItem(tenant_id=shop["cafe"], order_id=o.id, product_id=p.id, quantity=q,
                       unit_price=c, unit_cost=100_000.0, total_price=q * c)
        db.add(oi)
        db.flush()
        ois.append(oi)
    db.add(Payment(tenant_id=shop["cafe"], order_id=o.id, cashier_id=shop["user"],
                   amount=o.final_amount, method="cash", status="paid", transaction_id=f"T{o.id}"))
    db.commit()
    return o, ois


def _h(client):
    r = client.post("/api/v1/auth/login", data={"username": PHONE, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _4804(shop):
    a, b, c = shop["prods"]
    return _sold(shop, [(a, 1, 245_000.0, 220_000.0), (b, 1, 380_000.0, 360_000.0),
                        (c, 1, 295_000.0, 270_000.0)], 70_000.0)


def test_api_receipt_4804(client, shop):
    o, ois = _4804(shop)
    r = client.get(f"/api/v1/orders/{o.id}/receipt", headers=_h(client)).json()
    assert [i["line_total"] for i in r["items"]] == [220_000.0, 360_000.0, 270_000.0]
    assert [i["unit_price"] for i in r["items"]] == [245_000.0, 380_000.0, 295_000.0]
    assert r["receipt_subtotal"] == 850_000.0 and r["discount_other"] == 0.0
    # Eski maydonlar O'ZGARMAGAN (boshqa iste'molchilar uchun)
    assert r["subtotal"] == 920_000.0 and r["discount_amount"] == 70_000.0
    assert r["final_amount"] == 850_000.0


def test_api_receipt_GOLDEN_eski_chek(client, shop):
    a, b, _ = shop["prods"]
    o, _ = _sold(shop, [(a, 1, 245_000.0, None), (b, 1, 380_000.0, None)], 25_000.0, cart=False)
    r = client.get(f"/api/v1/orders/{o.id}/receipt", headers=_h(client)).json()
    assert "receipt_subtotal" not in r and "discount_other" not in r
    assert all("line_total" not in i for i in r["items"])


def test_vozvrat_chekdagi_summa(client, shop):
    """245 000 lik SHIM (chekda 220 000) qaytarilsa — 220 000 qaytariladi
    (ulush qoidasida 226 358.70 bo'lardi)."""
    h = _h(client)
    o, ois = _4804(shop)
    lk = client.get(f"/api/v1/returns/lookup?q={o.order_number}", headers=h).json()
    assert [i["sold_total"] for i in lk["items"]] == [220_000.0, 360_000.0, 270_000.0]
    assert [i["sold_total_gross"] for i in lk["items"]] == [245_000.0, 380_000.0, 295_000.0]
    oi = ois[0]
    r = client.post("/api/v1/returns/", headers=h, json={
        "order_id": o.id, "reason": "other", "refund_method": "cash",
        "items": [{"product_id": oi.product_id, "order_item_id": oi.id, "quantity": 1,
                   "unit_price": oi.unit_price, "restore_to_inventory": True}]})
    assert r.status_code == 200, r.text
    assert r.json()["total_amount"] == 220_000.0


def test_vozvrat_butun_chek_tolanganga_teng(client, shop):
    h = _h(client)
    o, ois = _4804(shop)
    r = client.post("/api/v1/returns/", headers=h, json={
        "order_id": o.id, "reason": "other", "refund_method": "cash",
        "items": [{"product_id": oi.product_id, "order_item_id": oi.id, "quantity": 1,
                   "unit_price": oi.unit_price, "restore_to_inventory": True} for oi in ois]})
    assert r.status_code == 200, r.text
    assert r.json()["total_amount"] == 850_000.0


def test_GOLDEN_vozvrat_eski_chek_ulush(client, shop):
    h = _h(client)
    a, b, _ = shop["prods"]
    o, ois = _sold(shop, [(a, 1, 245_000.0, None), (b, 1, 380_000.0, None)], 25_000.0, cart=False)
    oi = ois[0]
    r = client.post("/api/v1/returns/", headers=h, json={
        "order_id": o.id, "reason": "other", "refund_method": "cash",
        "items": [{"product_id": oi.product_id, "order_item_id": oi.id, "quantity": 1,
                   "unit_price": oi.unit_price, "restore_to_inventory": True}]})
    assert r.json()["total_amount"] == round(245_000 * (1 - 25_000 / 625_000), 2)   # 235 200


def test_GOLDEN_hisobot_ulush_qoidasida(client, shop, db_session):
    """Snapshot hisobotga TA'SIR QILMAYDI: davr savdosi snapshot bilan ham,
    snapshotsiz ham aynan bir xil (Σ total_price − chegirma)."""
    o, _ = _4804(shop)
    u = SimpleNamespace(is_superuser=False, tenant_id=shop["cafe"], id=0, role=None, _active_branch_id=None)
    s, e = NOW - timedelta(days=1), NOW + timedelta(days=1)
    with_snap = period_totals(db_session, u, s, e)
    o.biz_meta = None
    db_session.commit()
    without = period_totals(db_session, u, s, e)
    assert with_snap == without and with_snap["revenue"] == 850_000.0
