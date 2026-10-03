"""VOZVRAT NAZORATI — "ikkinchi ko'z" (2026-10-03).

MUAMMO (jonli, XOZMAG tenant 28):
    `RET261002001` — 09:51:42 da yozilgan, 09:51:54 da tasdiqlangan. **12
    sekund**, bitta odam, chekka bog'lanmagan (`order_id IS NULL`). Kassadan
    17 800 so'm chiqdi, tovar omborga qaytdi, keyin "UYGA OLIB KETILDI" deb
    hisobdan chiqarildi. Hech kim tasdiqlamagan — tasdiqlash va yaratish
    ikkalasi ham `process_payments` edi, ya'ni kassir o'z vozvratini o'zi
    tasdiqlardi.

TUZATISH:
    `POST /returns/{id}/approve` va `/reject` endi **`manage_shifts`** talab
    qiladi (admin + menejer rollarida bor, `cashier` da YO'Q). Kassir vozvrat
    YOZADI (`pending`) — pul va ombor rahbar tasdiqlagandan KEYIN harakatlanadi.

    Yangi ruxsat kodi ATAYIN qo'shilmadi: `roles` jadvali GLOBAL (tenant_id
    ustuni yo'q), yangi kod barcha tenantlarga seed qilinishi kerak bo'lardi.

    Admin O'ZI yozgan vozvratni tasdiqlay oladi (bir kishilik do'konda boshqa
    yo'l yo'q) — bu audit logda `self_approved: true` bo'lib qoladi.

Ishga tushirish:
    cd backend && py -m pytest tests/test_returns_control.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import Base, get_db
from main import app
from models import (
    AuditLog, Cafe, Customer, Inventory, Order, OrderItem, Payment, Product,
    Return, Role, Permission, User,
)
from core.security import get_password_hash

ADMIN_PW,  ADMIN_PHONE  = "AdminBosh9x", "+998900000041"
KASSIR_PW, KASSIR_PHONE = "Kassir7Yuz",  "+998900000042"


@pytest.fixture()
def eng():
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,   # TestClient va test bir bazani ko'rsin
    )
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)
    e.dispose()


@pytest.fixture()
def db_session(eng, monkeypatch):
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    # ⚠️ `core.audit.log_audit` ATAYIN ALOHIDA sessiyada yozadi va u
    # `database.SessionLocal` ni CHAQIRUV PAYTIDA o'qiydi. Yo'naltirilmasa
    # audit qatorlari DEV BAZASIGA tushadi va testga ko'rinmaydi
    # (2026-09 tuzog'i). Shu sababli test engine'iga burab qo'yamiz.
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
    """Ruxsatni OLADI yoki yaratadi.

    ⚠️ NEGA "bor bo'lsa oladi": `database.SessionLocal` test engine'iga
    burab qo'yilgani uchun ilovaning `init_db()` (lifespan, `TestClient(app)`
    ichida) rol va ruxsat urug'ini AYNAN SHU test bazasiga sepadi. Ko'r-ko'rona
    `INSERT` qilsa `UNIQUE constraint failed: permissions.code` beradi.
    """
    p = db.query(Permission).filter(Permission.code == code).first()
    if not p:
        p = Permission(code=code, description=desc)
        db.add(p)
        db.flush()
    return p


def _role(db, name, perms):
    """Rolni oladi/yaratadi va ruxsatlarini AYNIQSA o'rnatadi.

    Urug' nima qo'ygan bo'lsa ham test aniq bo'lishi uchun ruxsatlar
    majburlab yoziladi.
    """
    r = db.query(Role).filter(Role.name == name).first()
    if not r:
        r = Role(name=name, description=name)
        db.add(r)
        db.flush()
    r.permissions = perms
    db.flush()
    return r


@pytest.fixture()
def seeded(db_session):
    """Bitta do'kon: admin (manage_shifts BOR) + kassir (YO'Q) + sotuv."""
    db = db_session

    p_pay    = _perm(db, "process_payments", "To'lovlar")
    p_shift  = _perm(db, "manage_shifts",    "Smenalar")
    p_report = _perm(db, "view_reports",     "Hisobotlar")

    r_admin = _role(db, "admin", [p_pay, p_shift, p_report])
    # Kassirda `manage_shifts` ATAYIN YO'Q — aynan shu chiziq ikkinchi ko'zni
    # beradi (database.py dagi jonli rol urug'i bilan bir xil).
    r_kassir = _role(db, "cashier", [p_pay, p_report])

    cafe = Cafe(name="Do'kon A", code="dka", access_code="100.200.41",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe)
    db.flush()

    admin = User(username="bosh", email="a@x.uz", full_name="Rahbar Azizbek",
                 phone=ADMIN_PHONE, hashed_password=get_password_hash(ADMIN_PW),
                 is_active=True, is_superuser=False,
                 tenant_id=cafe.id, role_id=r_admin.id)
    kassir = User(username="kassa", email="k@x.uz", full_name="Kassir Diyorbek",
                  phone=KASSIR_PHONE, hashed_password=get_password_hash(KASSIR_PW),
                  is_active=True, is_superuser=False,
                  tenant_id=cafe.id, role_id=r_kassir.id)
    db.add_all([admin, kassir])
    db.flush()

    prod = Product(tenant_id=cafe.id, name="POLWON PW199-300 METR",
                   price=25000.0, cost_price=17800.0)
    db.add(prod)
    db.flush()
    db.add(Inventory(tenant_id=cafe.id, product_id=prod.id, quantity=15.0, unit="dona"))

    order = Order(tenant_id=cafe.id, order_number="A-3212", daily_number=3,
                  status="completed", total_amount=25000.0, discount_amount=7200.0,
                  final_amount=17800.0, waiter_id=kassir.id)
    db.add(order)
    db.flush()
    oi = OrderItem(tenant_id=cafe.id, order_id=order.id, product_id=prod.id,
                   quantity=1, unit_price=25000.0, unit_cost=17800.0,
                   total_price=25000.0)
    db.add(oi)
    db.add(Payment(tenant_id=cafe.id, order_id=order.id, cashier_id=kassir.id,
                   amount=17800.0, method="cash", status="paid"))
    db.commit()

    return {"db": db, "cafe": cafe.id, "admin": admin.id, "kassir": kassir.id,
            "order": order.id, "order_item": oi.id, "product": prod.id}


def _login(client, phone, pw):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": pw})
    assert r.status_code == 200, f"login yiqildi: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _yarat(client, hdr, seeded, *, bogla=True, qty=1):
    """Vozvrat yaratadi. `bogla=False` → chekka bog'lanmagan (order_id yo'q)."""
    payload = {
        "reason": "dislike",
        "refund_method": "cash",
        "items": [{
            "product_id": seeded["product"],
            "quantity": qty,
            "unit_price": 17800.0,
            "restore_to_inventory": True,
        }],
    }
    if bogla:
        payload["order_id"] = seeded["order"]
        payload["items"][0]["order_item_id"] = seeded["order_item"]
    return client.post("/api/v1/returns/", json=payload, headers=hdr)


# ══════════════════════════════════════════════════════════════════════════════
# 1) KASSIR YARATADI, LEKIN TASDIQLAY OLMAYDI
# ══════════════════════════════════════════════════════════════════════════════

def test_kassir_vozvrat_yaratadi_200_pending(client, seeded):
    hdr = _login(client, KASSIR_PHONE, KASSIR_PW)
    r = _yarat(client, hdr, seeded)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body["status"] == "pending", "kassir yaratgan vozvrat darhol tasdiqlanmasligi kerak"
    assert body["created_by_name"] == "Kassir Diyorbek"
    assert body["approved_by_name"] is None
    assert body["approved_by"] is None


def test_kassir_tasdiqlay_olmaydi_403(client, seeded):
    """ASOSIY TUZATISH: ilgari bu 200 edi — kassir o'z vozvratini o'zi tasdiqlardi."""
    hdr = _login(client, KASSIR_PHONE, KASSIR_PW)
    rid = _yarat(client, hdr, seeded).json()["id"]

    r = client.post(f"/api/v1/returns/{rid}/approve", headers=hdr)
    assert r.status_code == 403, (
        f"NAZORAT TESHIGI — kassir vozvratni tasdiqladi: {r.status_code} {r.text}")

    # Holat o'zgarmagan, ombor TEGILMAGAN (pul chiqmagan)
    db = seeded["db"]
    db.expire_all()
    assert db.query(Return).get(rid).status == "pending"
    inv = db.query(Inventory).filter(Inventory.product_id == seeded["product"]).first()
    assert inv.quantity == 15.0, "403 da ombor tiklanmasligi kerak"


def test_kassir_rad_eta_olmaydi_403(client, seeded):
    """Rad etish ham rahbar ishi — aks holda kassir izni o'chirib yuborardi."""
    hdr = _login(client, KASSIR_PHONE, KASSIR_PW)
    rid = _yarat(client, hdr, seeded).json()["id"]

    r = client.post(f"/api/v1/returns/{rid}/reject", headers=hdr)
    assert r.status_code == 403, f"{r.status_code} {r.text}"
    seeded["db"].expire_all()
    assert seeded["db"].query(Return).get(rid).status == "pending"


def test_admin_tasdiqlaydi_200(client, seeded):
    hdr_k = _login(client, KASSIR_PHONE, KASSIR_PW)
    rid = _yarat(client, hdr_k, seeded).json()["id"]

    hdr_a = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = client.post(f"/api/v1/returns/{rid}/approve", headers=hdr_a)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body["status"] == "approved"
    assert body["created_by_name"]  == "Kassir Diyorbek"
    assert body["approved_by_name"] == "Rahbar Azizbek"
    assert body["user_id"] != body["approved_by"], "ikki xil odam bo'lishi kerak"

    # Ombor tiklandi (tasdiqlangandan KEYIN)
    db = seeded["db"]
    db.expire_all()
    inv = db.query(Inventory).filter(Inventory.product_id == seeded["product"]).first()
    assert inv.quantity == 16.0


def test_admin_rad_etadi_200(client, seeded):
    hdr_k = _login(client, KASSIR_PHONE, KASSIR_PW)
    rid = _yarat(client, hdr_k, seeded).json()["id"]

    hdr_a = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = client.post(f"/api/v1/returns/{rid}/reject", headers=hdr_a)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    assert r.json()["status"] == "rejected"
    # Rad etilganda ombor TEGILMAYDI
    seeded["db"].expire_all()
    inv = seeded["db"].query(Inventory).filter(Inventory.product_id == seeded["product"]).first()
    assert inv.quantity == 15.0


# ══════════════════════════════════════════════════════════════════════════════
# 2) AUDIT — yaratuvchi va tasdiqlovchi ALOHIDA
# ══════════════════════════════════════════════════════════════════════════════

def test_auditda_yaratuvchi_va_tasdiqlovchi_alohida(client, seeded):
    hdr_k = _login(client, KASSIR_PHONE, KASSIR_PW)
    rid = _yarat(client, hdr_k, seeded).json()["id"]
    hdr_a = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert client.post(f"/api/v1/returns/{rid}/approve", headers=hdr_a).status_code == 200

    db = seeded["db"]
    logs = (db.query(AuditLog)
              .filter(AuditLog.resource == "returns", AuditLog.resource_id == str(rid))
              .all())
    turlar = {lg.action: lg for lg in logs}
    assert "RETURN" in turlar, "yaratish audit logda yo'q"
    assert "UPDATE" in turlar, "tasdiqlash audit logda yo'q"

    # Yaratish — kassir nomidan
    yarat = turlar["RETURN"]
    assert yarat.user_id == seeded["kassir"]

    # Tasdiqlash — admin nomidan, LEKIN yaratuvchi ham detailda qoladi
    tasdiq = turlar["UPDATE"]
    assert tasdiq.user_id == seeded["admin"]
    d = tasdiq.detail
    assert d["action"] == "approve"
    assert d["created_by"]       == seeded["kassir"]
    assert d["created_by_name"]  == "Kassir Diyorbek"
    assert d["approved_by"]      == seeded["admin"]
    assert d["self_approved"] is False
    assert d["order_linked"] is True


def test_ozi_yozib_ozi_tasdiqlasa_auditda_belgilanadi(client, seeded):
    """Bir kishilik do'kon (XOZMAG): admin o'z vozvratini tasdiqlaydi.

    TO'SILMAYDI — boshqa yo'l yo'q. Lekin `self_approved` bilan ko'rinadi.
    """
    hdr_a = _login(client, ADMIN_PHONE, ADMIN_PW)
    rid = _yarat(client, hdr_a, seeded).json()["id"]
    assert client.post(f"/api/v1/returns/{rid}/approve", headers=hdr_a).status_code == 200

    db = seeded["db"]
    lg = (db.query(AuditLog)
            .filter(AuditLog.resource == "returns", AuditLog.action == "UPDATE",
                    AuditLog.resource_id == str(rid))
            .first())
    assert lg is not None
    assert lg.detail["self_approved"] is True, "o'zi tasdiqlagani belgilanmagan"
    assert lg.detail["created_by"] == lg.detail["approved_by"] == seeded["admin"]


def test_rad_etish_ham_auditga_tushadi(client, seeded):
    """Ilgari `reject` da log_audit UMUMAN yo'q edi — kim rad etgani qolmasdi."""
    hdr_k = _login(client, KASSIR_PHONE, KASSIR_PW)
    rid = _yarat(client, hdr_k, seeded).json()["id"]
    hdr_a = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert client.post(f"/api/v1/returns/{rid}/reject", headers=hdr_a).status_code == 200

    lg = (seeded["db"].query(AuditLog)
            .filter(AuditLog.resource == "returns", AuditLog.action == "UPDATE",
                    AuditLog.resource_id == str(rid))
            .first())
    assert lg is not None, "rad etish audit logda yo'q"
    assert lg.detail["action"] == "reject"
    assert lg.detail["rejected_by"] == seeded["admin"]
    assert lg.detail["created_by"]  == seeded["kassir"]


# ══════════════════════════════════════════════════════════════════════════════
# 3) CHEKKA BOG'LANMAGAN VOZVRAT — ogohlantirish
# ══════════════════════════════════════════════════════════════════════════════

def test_order_id_null_ogohlantirish_chiqadi(client, seeded):
    hdr = _login(client, KASSIR_PHONE, KASSIR_PW)
    r = _yarat(client, hdr, seeded, bogla=False)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body["order_id"] is None
    assert body["warnings"], "chekka bog'lanmagan vozvratda ogohlantirish yo'q"
    assert any("bog'lanmagan" in w for w in body["warnings"])


def test_bogsiz_vozvrat_auditda_order_linked_false(client, seeded):
    hdr = _login(client, KASSIR_PHONE, KASSIR_PW)
    rid = _yarat(client, hdr, seeded, bogla=False).json()["id"]
    hdr_a = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert client.post(f"/api/v1/returns/{rid}/approve", headers=hdr_a).status_code == 200

    lg = (seeded["db"].query(AuditLog)
            .filter(AuditLog.resource == "returns", AuditLog.action == "UPDATE",
                    AuditLog.resource_id == str(rid))
            .first())
    assert lg.detail["order_linked"] is False
    assert lg.detail["order_id"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 4) RO'YXAT — ikki ustun ko'rinadi
# ══════════════════════════════════════════════════════════════════════════════

def test_royxatda_kim_yozdi_kim_tasdiqladi_korinadi(client, seeded):
    hdr_k = _login(client, KASSIR_PHONE, KASSIR_PW)
    rid = _yarat(client, hdr_k, seeded).json()["id"]
    hdr_a = _login(client, ADMIN_PHONE, ADMIN_PW)
    client.post(f"/api/v1/returns/{rid}/approve", headers=hdr_a)

    r = client.get("/api/v1/returns/", headers=hdr_a)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    row = next(x for x in r.json() if x["id"] == rid)
    assert row["created_by_name"]  == "Kassir Diyorbek"
    assert row["approved_by_name"] == "Rahbar Azizbek"
