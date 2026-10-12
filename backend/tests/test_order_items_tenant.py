"""⛔ SOTUV QATORI TENANTI — vozvrat "Sotuv qatori topilmadi" nuqsoni.

NUQSON (2026-10-07, MANHATTAN shikoyati; 4 jonli do'konda tasdiqlandi):
  • `order_service.create_order` / `add_item` / `public.py` `OrderItem` ni
    `tenant_id` SIZ yozardi → prodda 30 kunlik 9270 qatorning HAMMASIDA NULL.
  • `POST /returns/` (`_validate_return_items`) qatorni
    `apply_tenant_filter(OrderItem)` bilan qidirardi → do'kon xodimi uchun
    HAR DOIM bo'sh → 400 "Sotuv qatori #N topilmadi". `/returns/lookup` esa
    filtrsiz olib qatorlarni ko'rsatardi (chalg'itardi).
  • Prodda `order_item_id` bog'langan vozvrat 0 ta — v1.12.13 dan beri
    chek/ro'yxat orqali qaytarish HECH QACHON ishlamagan.

NEGA TESTLAR USHLAMADI: `test_returns_validation.py` qatorni
`OrderItem(tenant_id=1)` deb QO'LDA yaratardi. Bu yerda qator FAQAT haqiqiy
kassa yo'li bilan yaratiladi (`POST /api/v1/orders/` + to'lov), `tenant_id`
hech qayerda qo'lda qo'yilmaydi. Foydalanuvchi — superuser EMAS (superuser
tenant filtrini aylanib o'tadi va nuqsonni yashirardi).

Ishga tushirish:  cd backend && py -m pytest tests/test_order_items_tenant.py -v
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.security import get_password_hash
from database import Base, get_db
from main import app
from models import (
    Cafe, Category, Inventory, Order, OrderItem, Permission, Product, Role,
    Shift, Table, User,
)

PW = "DokonAlfa9x"
A, B = 1, 2                      # ikki do'kon
PHONE = {A: "+998900000101", B: "+998900000202"}


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def _sqlite_timezone(dbapi_conn, _rec):          # test_weight_sales bilan bir xil
        dbapi_conn.create_function(
            "timezone", 2, lambda _tz, ts: str(ts)[:10] if ts else None)

    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, autocommit=False, autoflush=False)()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture()
def seeded(db):
    for code in ("process_orders", "process_payments", "manage_menu",
                 "manage_shifts", "view_reports", "manage_inventory"):
        db.add(Permission(code=code, description=code))
    db.flush()
    r = Role(name="admin", description="Administrator")
    r.permissions = db.query(Permission).all()
    db.add(r)
    db.flush()

    for tid in (A, B):
        db.add(Cafe(id=tid, name=f"Dokon{tid}", code=f"d{tid}", business_type="store",
                    is_active=True, block_oversell=False, subscription_plan="pro"))
        db.add(Category(id=tid, name="Umumiy", tenant_id=tid))
        db.flush()
        pid = tid * 10
        db.add(Product(id=pid, name=f"Non {tid}", price=4000, cost_price=2500,
                       sale_unit="pcs", category_id=tid, tenant_id=tid,
                       is_active=True, is_available=True))
        db.add(Inventory(tenant_id=tid, product_id=pid, quantity=100, unit="dona"))
        db.add(Table(id=tid, number=f"{tid}", tenant_id=tid, capacity=4))
        u = User(id=tid, username=f"u{tid}", email=f"u{tid}@x.uz", full_name=f"Admin {tid}",
                 phone=PHONE[tid], hashed_password=get_password_hash(PW),
                 is_active=True, is_superuser=False, tenant_id=tid, role_id=r.id)
        db.add(u)
        db.flush()
        db.add(Shift(tenant_id=tid, user_id=u.id, start_time=datetime.now()))
    db.commit()
    return db


@pytest.fixture()
def client(db):
    def _override():
        yield db
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _h(client, tid):
    r = client.post("/api/v1/auth/login", data={"username": PHONE[tid], "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _sotuv(client, h, pid, qty=3):
    """HAQIQIY kassa yo'li: buyurtma + to'liq naqd to'lov (sotuv `completed`)."""
    r = client.post("/api/v1/orders/", headers=h,
                    json={"items": [{"product_id": pid, "quantity": qty}],
                          "order_type": "takeaway", "source": "pos"})
    assert r.status_code == 200, r.text
    o = r.json()
    p = client.post("/api/v1/payments/", headers=h,
                    json={"order_id": o["id"], "amount": o["total_amount"], "method": "cash"})
    assert p.status_code == 200, p.text
    return o


def _vozvrat(client, h, order_id, oi_id, pid, qty=1, price=4000):
    return client.post("/api/v1/returns/", headers=h, json={
        "order_id": order_id, "reason": "defective", "refund_method": "cash",
        "items": [{"product_id": pid, "order_item_id": oi_id, "quantity": qty,
                   "unit_price": price, "restore_to_inventory": True}],
    })


def _eski_nusxa(db):
    """2026-10-07 gacha bo'lgan prod holati: hamma qatorda tenant_id NULL."""
    db.query(OrderItem).update({OrderItem.tenant_id: None}, synchronize_session=False)
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# 1. ILDIZ: kassa yo'li qatorga tenant yozadi
# ═══════════════════════════════════════════════════════════════════════════
def test_POS_sotuvi_qatorga_tenant_yozadi(seeded, client):
    o = _sotuv(client, _h(client, A), pid=10)
    rows = seeded.query(OrderItem).filter(OrderItem.order_id == o["id"]).all()
    assert rows and all(oi.tenant_id == A for oi in rows), \
        "order_service.create_order OrderItem.tenant_id ni yozishi SHART"


def test_add_item_qatorga_tenant_yozadi(seeded, client):
    from services.order_service import OrderService
    o = _sotuv(client, _h(client, A), pid=10)
    OrderService(seeded).add_item(o["id"], product_id=10, quantity=1)  # mavjud qator
    seeded.add(Product(id=11, name="Sut", price=9000, cost_price=7000, sale_unit="pcs",
                       category_id=A, tenant_id=A, is_active=True, is_available=True))
    seeded.commit()
    OrderService(seeded).add_item(o["id"], product_id=11, quantity=2)  # YANGI qator
    rows = seeded.query(OrderItem).filter(OrderItem.order_id == o["id"]).all()
    assert len(rows) == 2 and {oi.tenant_id for oi in rows} == {A}


def test_QR_menyu_buyurtmasi_qatorga_tenant_yozadi(seeded, client):
    r = client.post(f"/public/order/d{B}", json={
        "table_id": B, "items": [{"product_id": 20, "quantity": 2}]})
    assert r.status_code == 200, r.text
    order = seeded.query(Order).filter(Order.tenant_id == B).order_by(Order.id.desc()).first()
    rows = seeded.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    assert rows and {oi.tenant_id for oi in rows} == {B}


# ═══════════════════════════════════════════════════════════════════════════
# 2. VOZVRAT: lookup -> POST /returns/ (yangi VA eski NULL qatorlarda)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("eski_null", [False, True], ids=["yangi_sotuv", "eski_NULL_qator"])
def test_chek_orqali_vozvrat_ishlaydi(seeded, client, eski_null):
    h = _h(client, A)
    o = _sotuv(client, h, pid=10, qty=3)
    if eski_null:
        _eski_nusxa(seeded)        # prodda 9270 qator aynan shunday

    lk = client.get("/api/v1/returns/lookup", params={"q": o["order_number"]}, headers=h)
    assert lk.status_code == 200, lk.text
    it = lk.json()["items"][0]
    assert it["returnable_qty"] == 3

    r = _vozvrat(client, h, o["id"], it["order_item_id"], it["product_id"], qty=2)
    assert r.status_code == 200, f"'Sotuv qatori topilmadi' qaytdimi? {r.text}"

    # Miqdor cheklovi ham ISHLAYDI (ilgari bu yergacha yetib bormasdi)
    r2 = _vozvrat(client, h, o["id"], it["order_item_id"], it["product_id"], qty=2)
    assert r2.status_code == 400 and "ko'pi bilan 1" in r2.json()["detail"], r2.text
    lk2 = client.get("/api/v1/returns/lookup", params={"q": o["order_number"]}, headers=h)
    assert lk2.json()["items"][0]["returnable_qty"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 3. ⛔ TENANT IZOLYATSIYASI — begona do'kon qatoriga tegib bo'lmaydi
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("eski_null", [False, True], ids=["yangi_sotuv", "eski_NULL_qator"])
def test_begona_dokon_qatorini_qaytarib_bolmaydi(seeded, client, eski_null):
    o = _sotuv(client, _h(client, A), pid=10)
    oi = seeded.query(OrderItem).filter(OrderItem.order_id == o["id"]).first()
    if eski_null:
        _eski_nusxa(seeded)
    hb = _h(client, B)

    # B o'z buyurtmasi bilan A ning qatorini ko'rsatadi
    ob = _sotuv(client, hb, pid=20)
    r = _vozvrat(client, hb, ob["id"], oi.id, 10)
    assert r.status_code == 400 and "topilmadi" in r.json()["detail"], r.text

    # B buyurtmasiz (order_id yo'q) A ning qatorini ko'rsatadi
    r = client.post("/api/v1/returns/", headers=hb, json={
        "reason": "defective", "refund_method": "cash",
        "items": [{"product_id": 10, "order_item_id": oi.id, "quantity": 1,
                   "unit_price": 4000, "restore_to_inventory": True}]})
    assert r.status_code == 400 and "topilmadi" in r.json()["detail"], r.text

    # B A ning buyurtmasini ko'rsatadi
    r = _vozvrat(client, hb, o["id"], oi.id, 10)
    assert r.status_code == 404, r.text

    # B lookup bilan A ning chekini topa olmaydi
    lk = client.get("/api/v1/returns/lookup", params={"q": o["order_number"]}, headers=hb)
    assert lk.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 4. /order-items/{id} — 4 endpoint (eski NULL qatorda ham) + izolyatsiya
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("eski_null", [False, True], ids=["yangi_sotuv", "eski_NULL_qator"])
def test_order_items_endpointlari(seeded, client, eski_null):
    ha, hb = _h(client, A), _h(client, B)
    r = client.post("/api/v1/orders/", headers=ha,
                    json={"items": [{"product_id": 10, "quantity": 2}],
                          "order_type": "takeaway", "source": "pos"})
    oi_id = r.json()["items"][0]["id"]
    if eski_null:
        _eski_nusxa(seeded)
    u = f"/api/v1/order-items/{oi_id}"

    # Begona do'kon: 4 tasi ham 404 (qator O'ZGARMAYDI)
    assert client.get(u, headers=hb).status_code == 404
    assert client.patch(u, headers=hb, json={"quantity": 9}).status_code == 404
    assert client.patch(f"{u}/status", headers=hb, params={"status": "ready"}).status_code == 404
    assert client.delete(u, headers=hb).status_code == 404
    seeded.expire_all()
    assert seeded.get(OrderItem, oi_id).quantity == 2

    # O'z do'koni: ishlaydi (ilgari eski NULL qatorda 404 edi)
    assert client.get(u, headers=ha).status_code == 200
    assert client.patch(u, headers=ha, json={"quantity": 3}).status_code == 200
    assert client.patch(f"{u}/status", headers=ha, params={"status": "ready"}).status_code == 200
    assert client.delete(u, headers=ha).status_code == 200
    seeded.expire_all()
    assert seeded.get(OrderItem, oi_id) is None


# ═══════════════════════════════════════════════════════════════════════════
# 5. GOLDEN: qo'lda kiritilgan vozvrat (order_item_id siz) avvalgidek
# ═══════════════════════════════════════════════════════════════════════════
def test_qolda_vozvrat_avvalgidek_ogohlantirish_bilan(seeded, client):
    h = _h(client, A)
    r = client.post("/api/v1/returns/", headers=h, json={
        "reason": "defective", "refund_method": "cash",
        "items": [{"product_id": 10, "quantity": 1, "unit_price": 4000,
                   "restore_to_inventory": True}]})
    assert r.status_code == 200, r.text
    assert any("bog'lanmagan" in w for w in r.json().get("warnings", []))


# ═══════════════════════════════════════════════════════════════════════════
# 6. BACKFILL skripti
# ═══════════════════════════════════════════════════════════════════════════
def _bf():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import backfill_order_items_tenant
    return backfill_order_items_tenant


def test_backfill_preview_apply_idempotent(seeded, client):
    _sotuv(client, _h(client, A), pid=10)
    _sotuv(client, _h(client, A), pid=10)
    _sotuv(client, _h(client, B), pid=20)
    _eski_nusxa(seeded)
    # Nomuvofiq qator (A buyurtmasi, B tenanti) — TEGILMASLIGI kerak
    bad = seeded.query(OrderItem).join(Order).filter(Order.tenant_id == A).first()
    bad.tenant_id = B
    seeded.commit()
    bf = _bf()

    p = bf.plan(seeded)
    assert p["to_fill"] == {A: 1, B: 1} and p["total"] == 2 and p["mismatch"] == 1
    assert seeded.query(OrderItem).filter(OrderItem.tenant_id.is_(None)).count() == 2, \
        "preview hech narsa yozmasligi kerak"

    assert bf.apply(seeded) == 2
    seeded.expire_all()
    for oi in seeded.query(OrderItem).all():
        if oi.id == bad.id:
            assert oi.tenant_id == B, "nomuvofiq qator tegilmaydi"
        else:
            assert oi.tenant_id == oi.order.tenant_id
    assert bf.plan(seeded)["total"] == 0
    assert bf.apply(seeded) == 0          # idempotent


def test_backfill_tenant_filtri(seeded, client):
    _sotuv(client, _h(client, A), pid=10)
    _sotuv(client, _h(client, B), pid=20)
    _eski_nusxa(seeded)
    bf = _bf()
    assert bf.plan(seeded, tenant=B)["to_fill"] == {B: 1}
    assert bf.apply(seeded, tenant=B) == 1
    seeded.expire_all()
    by = {oi.order.tenant_id: oi.tenant_id for oi in seeded.query(OrderItem).all()}
    assert by == {A: None, B: B}
