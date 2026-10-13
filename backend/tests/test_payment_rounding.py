"""KG SOTUVDAGI TIYIN NUQSONI — chek osilib qolmasin (fix/payment-rounding).

MUAMMO (prod, XOZMAG #3339/#3641): 0.566 kg × 26 500 frontendda
14998.999999999998 bo'lib to'landi, `final_amount` = 14999. Server
`paid >= final` → FALSE → buyurtma yakunlanmadi: pul olindi, tovar ketdi,
ombor ayrilmadi, chek "kutilayotgan"da qoldi va keyin o'chirildi.

QULFLANADI:
  • 0.566 kg × 26 500 (float dumi bilan) → chek YAKUNLANADI, ombor ayriladi
  • 1 tiyin kam → qabul (yakunlanadi); 1 so'm kam → YAKUNLANMAYDI
  • summa rejimi: 15 000 terilsa chek 15 000 (og'irlik 0.566 qoladi)
  • summa og'irlikka mos kelmasa → 400 (client narxni o'zgartira olmaydi)
  • "kutilayotgan" ro'yxatda `paid_amount` (qisman to'langan belgisi)
  • GOLDEN: butun sonli sotuv bit-bitiga avvalgidek

Ishga tushirish:  cd backend && py -m pytest tests/test_payment_rounding.py -v
"""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from core.security import get_password_hash
from core.timeutils import utc_now
from database import Base, get_db
from main import app
from models import (
    Cafe, Category, Inventory, Order, OrderItem, Payment, Permission, Product,
    Role, Shift, StockMovement, User,
)
from services.payment_service import covers

KASSIR_PW, KASSIR_PHONE = "KassirRnd7", "+998900000071"
KG_PRICE  = 26_500.0
DONA_PRICE = 5_000.0


@pytest.fixture()
def eng():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)

    # `_next_daily_number()` PostgreSQL `timezone(tz, ts)` ishlatadi — SQLite'da
    # yo'q (test_weight_sales / test_order_items_tenant bilan bir xil o'rinbosar)
    @event.listens_for(e, "connect")
    def _sqlite_timezone(dbapi_conn, _rec):
        dbapi_conn.create_function(
            "timezone", 2, lambda _tz, ts: str(ts)[:10] if ts else None)

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
    # manage_shifts — vozvratni tasdiqlash (pul harakati) testlari uchun
    for code in ("process_payments", "view_reports", "manage_menu", "manage_shifts"):
        p = db.query(Permission).filter(Permission.code == code).first()
        if not p:
            p = Permission(code=code, description=code)
            db.add(p)
            db.flush()
        perms.append(p)
    role = db.query(Role).filter(Role.name == "cashier").first()
    if not role:
        role = Role(name="cashier", description="cashier")
        db.add(role)
        db.flush()
    role.permissions = perms

    cafe = Cafe(name="XOZMAG tiyin", code="xtn", access_code="100.200.71",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe)
    db.flush()
    kassir = User(username="kassa71", email="k71@x.uz", full_name="DIYORBEK",
                  phone=KASSIR_PHONE, hashed_password=get_password_hash(KASSIR_PW),
                  is_active=True, tenant_id=cafe.id, role_id=role.id)
    db.add(kassir)
    cat = Category(name="SHRUP", tenant_id=cafe.id)
    db.add(cat)
    db.flush()
    kg = Product(tenant_id=cafe.id, name="QORA SHRUP 4", price=KG_PRICE, cost_price=20_000.0,
                 sale_unit="kg", category_id=cat.id)
    dona = Product(tenant_id=cafe.id, name="SOVUN", price=DONA_PRICE, cost_price=3_000.0,
                   sale_unit="pcs", category_id=cat.id)
    db.add_all([kg, dona])
    db.flush()
    db.add_all([
        Inventory(tenant_id=cafe.id, product_id=kg.id, quantity=10.0, unit="kg"),
        Inventory(tenant_id=cafe.id, product_id=dona.id, quantity=50.0, unit="dona"),
        Shift(tenant_id=cafe.id, user_id=kassir.id, start_time=utc_now() - timedelta(hours=2),
              starting_cash=0.0),
    ])
    db.commit()
    return {"db": db, "cafe": cafe.id, "kg": kg.id, "dona": dona.id}


def _h(client):
    r = client.post("/api/v1/auth/login", data={"username": KASSIR_PHONE, "password": KASSIR_PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _order(client, h, items):
    return client.post("/api/v1/orders/", headers=h, json={
        "items": items, "order_type": "takeaway", "source": "pos"})


def _pay(client, h, oid, amount, method="cash"):
    r = client.post("/api/v1/payments/", headers=h,
                    json={"order_id": oid, "amount": amount, "method": method})
    assert r.status_code == 200, r.text
    return r.json()


def _status(db, oid):
    db.expire_all()
    return str(getattr(db.query(Order).get(oid).status, "value", db.query(Order).get(oid).status))


def _stock(db, pid):
    db.expire_all()
    return db.query(Inventory).filter(Inventory.product_id == pid).one().quantity


# ══════════════════════════════════════════════════════════════════════════════
# 1) Ildiz: 1 tiyin dopusk
# ══════════════════════════════════════════════════════════════════════════════

def test_covers_chegaralari():
    assert covers(14998.999999999998, 14999)        # prod holati
    assert covers(14998.99, 14999)                   # 1 tiyin kam — qabul
    assert not covers(14998.98, 14999)               # 2 tiyin kam — yo'q
    assert not covers(14998, 14999)                  # 1 so'm kam — yo'q
    assert covers(15000, 14999)


def test_0566_kg_float_bilan_chek_yakunlanadi(client, shop):
    db, h = shop["db"], _h(client)
    r = _order(client, h, [{"product_id": shop["kg"], "quantity": 0.566}])
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["final_amount"] == 14999.0
    _pay(client, h, o["id"], 0.566 * 26500)          # = 14998.999999999998 (eski frontend)
    assert _status(db, o["id"]) == "completed"
    assert _stock(db, shop["kg"]) == pytest.approx(10.0 - 0.566)
    assert db.query(StockMovement).filter(StockMovement.reference_id == o["id"]).count() == 1


def test_1_tiyin_kam_qabul_qilinadi(client, shop):
    db, h = shop["db"], _h(client)
    o = _order(client, h, [{"product_id": shop["kg"], "quantity": 0.566}]).json()
    _pay(client, h, o["id"], 14998.99)
    assert _status(db, o["id"]) == "completed"


def test_1_som_kam_yakunlanmaydi(client, shop):
    """To'lov yozuvi qabul qilinadi (split uchun qisman to'lov qonuniy), lekin
    chek YOPILMAYDI va ombor ayrilmaydi — 1 so'm haqiqiy qarzdorlik."""
    db, h = shop["db"], _h(client)
    o = _order(client, h, [{"product_id": shop["kg"], "quantity": 0.566}]).json()
    _pay(client, h, o["id"], 14998.0)
    assert _status(db, o["id"]) == "pending"
    assert _stock(db, shop["kg"]) == 10.0
    _pay(client, h, o["id"], 1.0)                    # qolgan 1 so'm — endi yopiladi
    assert _status(db, o["id"]) == "completed"


def test_split_kasrli_chek(client, shop):
    db, h = shop["db"], _h(client)
    o = _order(client, h, [{"product_id": shop["kg"], "quantity": 0.566}]).json()
    _pay(client, h, o["id"], 5_000.0, method="card")
    _pay(client, h, o["id"], 0.566 * 26500 - 5_000)  # float dumi bilan naqd qoldiq
    assert _status(db, o["id"]) == "completed"


# ══════════════════════════════════════════════════════════════════════════════
# 2) Summa rejimi
# ══════════════════════════════════════════════════════════════════════════════

def test_summa_rejimi_15000_chek_15000(client, shop):
    db, h = shop["db"], _h(client)
    w = round(15000 / KG_PRICE, 3)                   # 0.566 — POS _weightFromSum
    r = _order(client, h, [{"product_id": shop["kg"], "quantity": w, "line_total": 15000}])
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["final_amount"] == 15000.0
    it = db.query(OrderItem).filter(OrderItem.order_id == o["id"]).one()
    assert (it.quantity, it.unit_price, it.total_price) == (0.566, KG_PRICE, 15000.0)
    _pay(client, h, o["id"], 15000)
    assert _status(db, o["id"]) == "completed"
    assert _stock(db, shop["kg"]) == pytest.approx(10.0 - 0.566)   # og'irlik 3 xona


@pytest.mark.parametrize("summa", [5000, 7777, 12345, 100000])
def test_summa_rejimi_har_xil_summa(client, shop, summa):
    h = _h(client)
    w = round(summa / KG_PRICE, 3)
    r = _order(client, h, [{"product_id": shop["kg"], "quantity": w, "line_total": summa}])
    assert r.status_code == 200, r.text
    assert r.json()["final_amount"] == float(summa)


def test_summa_ogirlikka_mos_kelmasa_400(client, shop):
    """Client narxni summa orqali o'zgartira olmaydi: 0.566 kg ga 16 000 — rad."""
    db, h = shop["db"], _h(client)
    r = _order(client, h, [{"product_id": shop["kg"], "quantity": 0.566, "line_total": 16000}])
    assert r.status_code == 400
    assert "mos emas" in r.json()["detail"]
    assert db.query(Order).count() == 0


def test_summa_arzonlashtirib_bolmaydi(client, shop):
    """Pastga ham faqat yaxlitlash oralig'i: 0.566 kg ga 14 000 — rad."""
    h = _h(client)
    r = _order(client, h, [{"product_id": shop["kg"], "quantity": 0.566, "line_total": 14000}])
    assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# 3) "Kutilayotgan" — qisman to'langan belgisi
# ══════════════════════════════════════════════════════════════════════════════

def test_kutilayotgan_royxatda_paid_amount(client, shop):
    h = _h(client)
    a = _order(client, h, [{"product_id": shop["kg"], "quantity": 0.566}]).json()
    b = _order(client, h, [{"product_id": shop["dona"], "quantity": 1}]).json()
    _pay(client, h, a["id"], 5_000.0)                # qisman
    r = client.get("/api/v1/orders/?status=pending&page_size=50", headers=h)
    assert r.status_code == 200, r.text
    paid = {o["id"]: o["paid_amount"] for o in r.json()["items"]}
    assert paid == {a["id"]: 5000.0, b["id"]: 0.0}


# ══════════════════════════════════════════════════════════════════════════════
# 4) GOLDEN
# ══════════════════════════════════════════════════════════════════════════════

def test_GOLDEN_butun_sonli_sotuv(client, shop):
    db, h = shop["db"], _h(client)
    o = _order(client, h, [{"product_id": shop["dona"], "quantity": 2}]).json()
    assert o["final_amount"] == 10_000.0
    _pay(client, h, o["id"], 9_999.0)
    assert _status(db, o["id"]) == "pending"         # 1 so'm kam — avvalgidek ochiq
    _pay(client, h, o["id"], 1.0)
    assert _status(db, o["id"]) == "completed"
    assert _stock(db, shop["dona"]) == 48.0


def test_GOLDEN_line_totalsiz_ogirlik_avvalgidek(client, shop):
    """Eski .exe `line_total` yubormaydi — server avvalgidek narx × og'irlik."""
    h = _h(client)
    o = _order(client, h, [{"product_id": shop["kg"], "quantity": 0.74}]).json()
    assert o["final_amount"] == round(KG_PRICE * 0.74, 2)


def test_yoq_mahsulot_400_500_emas(client, shop):
    h = _h(client)
    r = _order(client, h, [{"product_id": 999999, "quantity": 1}])
    assert r.status_code == 400
    assert "topilmadi" in r.json()["detail"]


# ══════════════════════════════════════════════════════════════════════════════
# 5) VOZVRAT — sotuvdagi summa (summa rejimi 15 000 → 15 000 qaytadi)
# ══════════════════════════════════════════════════════════════════════════════

def _sold(client, h, db, items, pay):
    o = _order(client, h, items).json()
    _pay(client, h, o["id"], pay)
    assert _status(db, o["id"]) == "completed"
    ois = db.query(OrderItem).filter(OrderItem.order_id == o["id"]).order_by(OrderItem.id).all()
    return o, ois


def _ret(client, h, oid, rows, *, approve=False):
    r = client.post("/api/v1/returns/", headers=h, json={
        "order_id": oid, "reason": "other", "refund_method": "cash", "items": rows})
    assert r.status_code == 200, r.text
    ret = r.json()
    if approve:
        a = client.post(f"/api/v1/returns/{ret['id']}/approve", headers=h)
        assert a.status_code == 200, a.text
    return ret


def _row(oi, qty, price=None):
    return {"product_id": oi.product_id, "order_item_id": oi.id, "quantity": qty,
            "unit_price": oi.unit_price if price is None else price, "restore_to_inventory": True}


def test_vozvrat_summa_rejimi_toliq_15000(client, shop):
    db, h = shop["db"], _h(client)
    o, (oi,) = _sold(client, h, db, [{"product_id": shop["kg"], "quantity": 0.566,
                                       "line_total": 15000}], 15000)
    ret = _ret(client, h, o["id"], [_row(oi, 0.566)], approve=True)
    assert ret["total_amount"] == 15000.0                 # ilgari 14998.999999999998
    assert ret["items"][0]["total"] == 15000.0
    db.expire_all()
    qaytgan = -sum(p.amount for p in db.query(Payment).filter(
        Payment.order_id == o["id"], Payment.amount < 0))
    assert qaytgan == 15000.0                             # aynan to'langan summa


def test_vozvrat_qisman_proporsional_va_jami_aniq(client, shop):
    db, h = shop["db"], _h(client)
    o, (oi,) = _sold(client, h, db, [{"product_id": shop["kg"], "quantity": 0.566,
                                       "line_total": 15000}], 15000)
    r1 = _ret(client, h, o["id"], [_row(oi, 0.3)])
    assert r1["total_amount"] == round(15000 * 0.3 / 0.566, 2) == 7950.53
    r2 = _ret(client, h, o["id"], [_row(oi, 0.266)])      # oxirgi qism
    assert r2["total_amount"] == 7049.47
    assert r1["total_amount"] + r2["total_amount"] == 15000.0   # 1 so'm farq YO'Q


def test_vozvrat_uch_bolak_dumsiz(client, shop):
    """Yaxlitlash dumi to'planmaydi: 3 bo'lakda ham jami aynan sotuv summasi."""
    db, h = shop["db"], _h(client)
    o, (oi,) = _sold(client, h, db, [{"product_id": shop["kg"], "quantity": 0.566,
                                       "line_total": 15000}], 15000)
    jami = sum(_ret(client, h, o["id"], [_row(oi, q)])["total_amount"]
               for q in (0.1, 0.233, 0.233))
    assert round(jami, 2) == 15000.0


def test_vozvrat_ogirlik_rejimi_dumsiz(client, shop):
    db, h = shop["db"], _h(client)
    o, (oi,) = _sold(client, h, db, [{"product_id": shop["kg"], "quantity": 0.566}], 14999)
    assert _ret(client, h, o["id"], [_row(oi, 0.566)])["total_amount"] == 14999.0


def test_GOLDEN_vozvrat_butun_sonli(client, shop):
    db, h = shop["db"], _h(client)
    o, (oi,) = _sold(client, h, db, [{"product_id": shop["dona"], "quantity": 3}], 15000)
    assert _ret(client, h, o["id"], [_row(oi, 1)])["total_amount"] == DONA_PRICE
    assert _ret(client, h, o["id"], [_row(oi, 2)])["total_amount"] == 2 * DONA_PRICE


def test_GOLDEN_vozvrat_boglanmagan_qator_avvalgidek(client, shop):
    h = _h(client)
    r = client.post("/api/v1/returns/", headers=h, json={
        "reason": "other", "refund_method": "cash",
        "items": [{"product_id": shop["kg"], "quantity": 0.566, "unit_price": KG_PRICE,
                   "restore_to_inventory": True}]})
    assert r.status_code == 200, r.text
    assert r.json()["total_amount"] == 0.566 * KG_PRICE   # q × narx, o'zgarmagan


def test_GOLDEN_vozvrat_boshqa_narx_avvalgidek(client, shop):
    """Narx sotuvdagidan farq qilsa (qo'lda) — sotuv summasiga suyanilmaydi."""
    db, h = shop["db"], _h(client)
    o, (oi,) = _sold(client, h, db, [{"product_id": shop["dona"], "quantity": 2}], 10000)
    assert _ret(client, h, o["id"], [_row(oi, 1, price=4000)])["total_amount"] == 4000.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
