"""XAVFSIZLIK — /auth/register orqali imtiyoz oshirish (2026-08-27 auditi).

MUAMMO (jonli, tuzatilgunga qadar):
    `POST /api/v1/auth/register` autentifikatsiyasiz OCHIQ edi va so'rov tanasidan
    `tenant_id` + `role_id` ni to'g'ridan-to'g'ri olardi. Ya'ni internetdagi
    istalgan odam:
        {"phone": "...", "password": "...", "tenant_id": <begona>, "role_id": <admin>}
    yuborib, BEGONA do'konning to'liq admini bo'lib olardi va telefon+parol bilan
    kirardi (login do'kon kodini so'ramaydi).

TUZATISH (core/role_guard.py):
    1. `manage_users` ruxsati majburiy  → autentifikatsiyasiz 401, ruxsatsiz 403
    2. `tenant_id` tanadan OLINMAYDI    → server tokendan aniqlaydi
    3. `role_id` imtiyoz darajasidan oshmaydi
    4. `branch_id` faqat o'sha tenant'niki

REGRESSIYA KAFOLATI: mavjud foydalanuvchilar KIRISHDA davom etadi — bu yerda ham
tekshiriladi (`test_eski_user_login_qila_oladi`).

Ishga tushirish:
    cd backend && py -m pytest tests/test_register_privilege_escalation.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import Cafe, User, Role, Permission, Branch
from core.security import get_password_hash

# Parollar siyosatga mos (8+, harf+raqam, zaif ro'yxatda emas)
ADMIN_A_PW = "AdminAlfa9x"
ADMIN_B_PW = "AdminBeta7y"
MANAGER_PW = "MenejerC5z"
NEW_USER_PW = "YangiUser4k"


@pytest.fixture()
def db_session():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,   # bitta ulanish → TestClient va test bir bazani ko'radi
    )
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
    """Ikki tenant (A, B), rollar va ularning adminlari."""
    db = db_session

    # ── Ruxsatlar ──
    p_users    = Permission(code="manage_users",     description="Foydalanuvchilar")
    p_settings = Permission(code="manage_settings",  description="Sozlamalar")
    p_pay      = Permission(code="process_payments", description="To'lovlar")
    p_reports  = Permission(code="view_reports",     description="Hisobotlar")
    db.add_all([p_users, p_settings, p_pay, p_reports])
    db.flush()

    # admin — HAMMA ruxsat; cashier — ikkita; menejer — manage_users bor, lekin
    # manage_settings YO'Q (ya'ni admin rolini bera olmasligi kerak).
    r_admin   = Role(name="admin",   description="Administrator")
    r_admin.permissions = [p_users, p_settings, p_pay, p_reports]
    r_cashier = Role(name="cashier", description="Kassir")
    r_cashier.permissions = [p_pay, p_reports]
    r_menejer = Role(name="menejer", description="Menejer")
    r_menejer.permissions = [p_users, p_pay, p_reports]
    db.add_all([r_admin, r_cashier, r_menejer])
    db.flush()

    # ── Tenantlar ──
    cafe_a = Cafe(name="Do'kon A", code="doka", access_code="100.200.1",
                  business_type="store", subscription_plan="pro", is_active=True)
    cafe_b = Cafe(name="Do'kon B", code="dokb", access_code="100.200.2",
                  business_type="store", subscription_plan="pro", is_active=True)
    db.add_all([cafe_a, cafe_b])
    db.flush()

    branch_b = Branch(tenant_id=cafe_b.id, name="B filial", is_active=True)
    db.add(branch_b)
    db.flush()

    # ── Foydalanuvchilar ──
    admin_a = User(username="admin_a", email="a@x.uz", full_name="Admin A",
                   phone="+998900000001", hashed_password=get_password_hash(ADMIN_A_PW),
                   is_active=True, is_superuser=False, tenant_id=cafe_a.id, role_id=r_admin.id)
    admin_b = User(username="admin_b", email="b@x.uz", full_name="Admin B",
                   phone="+998900000002", hashed_password=get_password_hash(ADMIN_B_PW),
                   is_active=True, is_superuser=False, tenant_id=cafe_b.id, role_id=r_admin.id)
    menejer_a = User(username="menejer_a", email="m@x.uz", full_name="Menejer A",
                     phone="+998900000003", hashed_password=get_password_hash(MANAGER_PW),
                     is_active=True, is_superuser=False, tenant_id=cafe_a.id, role_id=r_menejer.id)
    db.add_all([admin_a, admin_b, menejer_a])
    db.commit()

    return {
        "db": db,
        "cafe_a": cafe_a.id, "cafe_b": cafe_b.id,
        "branch_b": branch_b.id,
        "admin_a": admin_a.id, "admin_b": admin_b.id, "menejer_a": menejer_a.id,
        "role_admin": r_admin.id, "role_cashier": r_cashier.id, "role_menejer": r_menejer.id,
    }


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client, phone, password):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": password})
    assert r.status_code == 200, f"login yiqildi: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ══════════════════════════════════════════════════════════════════════════════
# 1) REGRESSIYA: mavjud mijozlar buzilmasin
# ══════════════════════════════════════════════════════════════════════════════

def test_eski_user_login_qila_oladi(client, seeded):
    """Fazza Parfum / Eco Aroma kabi mavjud adminlar kirishда davom etadi."""
    headers = _login(client, "+998900000001", ADMIN_A_PW)
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "admin_a"


def test_kassir_pin_login_buzilmagan(client, seeded):
    """PIN bilan kiruvchi xodim oqimi tegilmagan (endpoint mavjud va javob beradi)."""
    r = client.post("/api/v1/auth/pin-login", json={"pin": "1234", "access_code": "100.200.1"})
    # Bunday PIN'li xodim yo'q → 401/404 kutamiz, lekin 500 (buzilish) EMAS.
    assert r.status_code < 500, f"pin-login server xatosi: {r.status_code} {r.text}"


# ══════════════════════════════════════════════════════════════════════════════
# 2) ASOSIY TESHIK: autentifikatsiyasiz register
# ══════════════════════════════════════════════════════════════════════════════

def test_autentifikatsiyasiz_register_401(client, seeded):
    """ILGARI 200 qaytarardi va begona tenantga admin yaratardi. Endi 401."""
    r = client.post("/api/v1/auth/register", json={
        "phone": "+998911111111",
        "password": NEW_USER_PW,
        "full_name": "Buzg'unchi",
        "tenant_id": seeded["cafe_b"],
        "role_id": seeded["role_admin"],
    })
    assert r.status_code == 401, f"kutilgan 401, kelgani {r.status_code}: {r.text}"

    # Eng muhimi: hech qanday user YARATILMAGAN bo'lsin
    assert seeded["db"].query(User).filter(User.phone == "+998911111111").first() is None


def test_notogri_token_bilan_register_401(client, seeded):
    r = client.post(
        "/api/v1/auth/register",
        json={"phone": "+998911111112", "password": NEW_USER_PW,
              "tenant_id": seeded["cafe_b"], "role_id": seeded["role_admin"]},
        headers={"Authorization": "Bearer soxta.token.qiymat"},
    )
    assert r.status_code == 401
    assert seeded["db"].query(User).filter(User.phone == "+998911111112").first() is None


# ══════════════════════════════════════════════════════════════════════════════
# 3) TENANT SAKRASH: A admini B ga user yarata olmaydi
# ══════════════════════════════════════════════════════════════════════════════

def test_admin_begona_tenantga_user_yaratolmaydi(client, seeded):
    """Tanadagi tenant_id E'TIBORSIZ qoldiriladi — user yaratuvchi tenant'ida qoladi."""
    headers = _login(client, "+998900000001", ADMIN_A_PW)   # A admini
    r = client.post("/api/v1/auth/register", json={
        "phone": "+998922222222",
        "password": NEW_USER_PW,
        "full_name": "B ga urinish",
        "tenant_id": seeded["cafe_b"],          # ← begona tenant so'raladi
        "role_id": seeded["role_cashier"],
    }, headers=headers)

    assert r.status_code == 200, r.text
    yaratilgan = seeded["db"].query(User).filter(User.phone == "+998922222222").first()
    assert yaratilgan is not None
    assert yaratilgan.tenant_id == seeded["cafe_a"], (
        f"TENANT SAKRASH! user {seeded['cafe_b']} da bo'lib qoldi, "
        f"kutilgani {seeded['cafe_a']}"
    )


def test_users_endpointida_ham_tenant_sakrash_yopiq(client, seeded):
    """POST /users/ — xodim qo'shishning asosiy yo'li; u ham tanadagi tenant_id ni olmaydi."""
    headers = _login(client, "+998900000001", ADMIN_A_PW)
    r = client.post("/api/v1/users/", json={
        "phone": "+998933333333",
        "password": NEW_USER_PW,
        "full_name": "Xodim",
        "tenant_id": seeded["cafe_b"],
        "role_id": seeded["role_cashier"],
    }, headers=headers)

    assert r.status_code == 200, r.text
    u = seeded["db"].query(User).filter(User.phone == "+998933333333").first()
    assert u.tenant_id == seeded["cafe_a"]


def test_begona_filialga_biriktirib_bolmaydi(client, seeded):
    """branch_id B tenant'niki — A admini uni ishlata olmaydi."""
    headers = _login(client, "+998900000001", ADMIN_A_PW)
    r = client.post("/api/v1/auth/register", json={
        "phone": "+998944444444",
        "password": NEW_USER_PW,
        "full_name": "Filial urinishi",
        "role_id": seeded["role_cashier"],
        "branch_id": seeded["branch_b"],        # ← begona filial
    }, headers=headers)
    assert r.status_code == 400, r.text
    assert seeded["db"].query(User).filter(User.phone == "+998944444444").first() is None


# ══════════════════════════════════════════════════════════════════════════════
# 4) IMTIYOZ OSHIRISH: o'zidan kuchliroq rol berish
# ══════════════════════════════════════════════════════════════════════════════

def test_menejer_admin_roli_berolmaydi(client, seeded):
    """Menejerda manage_users bor, lekin manage_settings yo'q → admin rolini bera olmaydi."""
    headers = _login(client, "+998900000003", MANAGER_PW)
    r = client.post("/api/v1/auth/register", json={
        "phone": "+998955555555",
        "password": NEW_USER_PW,
        "full_name": "Soxta admin",
        "role_id": seeded["role_admin"],        # ← o'zidan kuchliroq
    }, headers=headers)
    assert r.status_code == 403, f"kutilgan 403, kelgani {r.status_code}: {r.text}"
    assert seeded["db"].query(User).filter(User.phone == "+998955555555").first() is None


def test_menejer_ozidan_past_rol_berolishi_kerak(client, seeded):
    """Cheklov ORTIQCHA qattiq bo'lmasin: kassir roli menejer ruxsatlari ichida."""
    headers = _login(client, "+998900000003", MANAGER_PW)
    r = client.post("/api/v1/auth/register", json={
        "phone": "+998966666666",
        "password": NEW_USER_PW,
        "full_name": "Oddiy kassir",
        "role_id": seeded["role_cashier"],
    }, headers=headers)
    assert r.status_code == 200, r.text
    u = seeded["db"].query(User).filter(User.phone == "+998966666666").first()
    assert u is not None and u.tenant_id == seeded["cafe_a"]


def test_admin_admin_yaratа_oladi(client, seeded):
    """Kafe admini o'z do'koniga ikkinchi admin qo'sha olishi SHART (blokirovka bo'lmasin)."""
    headers = _login(client, "+998900000001", ADMIN_A_PW)
    r = client.post("/api/v1/auth/register", json={
        "phone": "+998977777777",
        "password": NEW_USER_PW,
        "full_name": "Ikkinchi admin",
        "role_id": seeded["role_admin"],
    }, headers=headers)
    assert r.status_code == 200, r.text
    u = seeded["db"].query(User).filter(User.phone == "+998977777777").first()
    assert u.role_id == seeded["role_admin"]
    assert u.tenant_id == seeded["cafe_a"]


def test_rol_koTarish_patchda_ham_yopiq(client, seeded):
    """PATCH /users/{id} orqali rolni ko'tarish ham bloklanadi (setattr teshigi)."""
    headers = _login(client, "+998900000003", MANAGER_PW)   # menejer
    r = client.patch(
        f"/api/v1/users/{seeded['menejer_a']}",
        json={"role_id": seeded["role_admin"]},
        headers=headers,
    )
    assert r.status_code == 403, f"kutilgan 403, kelgani {r.status_code}: {r.text}"
    seeded["db"].expire_all()
    u = seeded["db"].query(User).filter(User.id == seeded["menejer_a"]).first()
    assert u.role_id == seeded["role_menejer"], "rol ko'tarilib ketdi!"


# ══════════════════════════════════════════════════════════════════════════════
# 5) RUXSATSIZ ROL: kassir umuman user yarata olmaydi
# ══════════════════════════════════════════════════════════════════════════════

def test_kassir_user_yaratolmaydi(client, seeded):
    db = seeded["db"]
    kassir = User(username="kassir_a", email="k@x.uz", full_name="Kassir A",
                  phone="+998900000009", hashed_password=get_password_hash("Kassir123x"),
                  is_active=True, tenant_id=seeded["cafe_a"], role_id=seeded["role_cashier"])
    db.add(kassir)
    db.commit()

    headers = _login(client, "+998900000009", "Kassir123x")
    r = client.post("/api/v1/auth/register", json={
        "phone": "+998988888888", "password": NEW_USER_PW,
        "full_name": "X", "role_id": seeded["role_admin"],
    }, headers=headers)
    assert r.status_code == 403
    assert db.query(User).filter(User.phone == "+998988888888").first() is None
