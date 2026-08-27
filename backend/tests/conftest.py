"""Test konfigurasiyasi va shared fixturalar.

⚠️ 2026-08-27 TUZATISH — `admin_token` fixture ISHLAMASDI, natijada
`test_orders.py` va `test_products.py` butunlay SKIP bo'lardi (API integratsiya
testlari amalda yo'q edi). Uch sabab bor edi:

  1. **Baza urug'lantirilmasdi.** `setup_database` faqat `create_all()` qilardi —
     rol ham, admin ham yaratilmasdi. Ilovaning `init_db()` esa lifespan'da
     ishlaydi-yu, u `database.SessionLocal` ni TO'G'RIDAN-TO'G'RI chaqiradi,
     ya'ni `dependency_overrides[get_db]` unga TA'SIR QILMAYDI → u dev bazasini
     urug'lantirardi, testlar esa bo'sh `test.db` ni o'qirdi.
  2. **Login kaliti noto'g'ri.** BOSQICH 38 dan beri `authenticate_user()` faqat
     TELEFON qabul qiladi (`auth_service.py:46`), fixture esa `username="admin"`
     yuborardi → har doim 401.
  3. `test_auth.py` da `pytest.skip` ishlatilgan, lekin `import pytest` yo'q edi
     → `NameError` (skip emas, YIQILISH).

Endi test bazasi shu yerda, test dvigateli orqali urug'lantiriladi — ilovaning
`init_db()` iga bog'liq emas.
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

# Test uchun SQLite (fayl) bazasi
TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,   # TestClient va fixture AYNAN bir ulanishni ko'rsin
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Urug' admin — parol siyosatiga mos (8+, harf+raqam, zaif ro'yxatda emas).
# ⚠️ "admin123" ISHLAMAYDI: u `_WEAK_PASSWORDS` ro'yxatida.
SEED_ADMIN_PHONE    = "+998900000000"
SEED_ADMIN_PASSWORD = "TestAdmin9x"
SEED_ADMIN_USERNAME = "admin"


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed(db):
    """Rollar + ruxsatlar + superadmin. `database.init_db()` ning test analogi.

    Ataylab qo'lda yozilgan: `init_db()` ni chaqirib bo'lmaydi (u o'z
    `SessionLocal` ini ishlatadi va dev bazasiga yozadi).
    """
    from models import User, Role, Permission
    from core.security import get_password_hash

    if db.query(User).filter(User.phone == SEED_ADMIN_PHONE).first():
        return   # idempotent

    # Ruxsatlar — `has_permission(...)` tekshiradigan kodlar.
    codes = [
        ("manage_users",      "Foydalanuvchilar"),
        ("manage_roles",      "Rollar"),
        ("manage_settings",   "Sozlamalar"),
        ("manage_products",   "Mahsulotlar"),
        ("manage_menu",       "Menyu"),
        ("manage_inventory",  "Ombor"),
        ("manage_customers",  "Mijozlar"),
        ("manage_discounts",  "Chegirmalar"),
        ("manage_tables",     "Stollar"),
        ("manage_reservations", "Bronlar"),
        ("manage_shifts",     "Smenalar"),
        ("process_orders",    "Buyurtmalar"),
        ("process_payments",  "To'lovlar"),
        ("view_reports",      "Hisobotlar"),
        ("view_analytics",    "Analitika"),
        ("view_finance",      "Moliya"),
    ]
    perms = []
    for code, desc in codes:
        p = db.query(Permission).filter(Permission.code == code).first()
        if not p:
            p = Permission(code=code, description=desc)
            db.add(p)
        perms.append(p)
    db.flush()

    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        admin_role = Role(name="admin", description="Administrator")
        db.add(admin_role)
        db.flush()
    admin_role.permissions = perms

    db.add(User(
        username=SEED_ADMIN_USERNAME,
        email="admin@test.local",
        full_name="Test Admin",
        phone=SEED_ADMIN_PHONE,
        hashed_password=get_password_hash(SEED_ADMIN_PASSWORD),
        is_active=True,
        is_superuser=True,     # tenant_id=None → apply_tenant_filter cheklamaydi
        role_id=admin_role.id,
    ))
    db.commit()


@pytest.fixture(scope="session", autouse=True)
def _sessionlocal_test_bazaga_yonaltirilsin():
    """`database.SessionLocal` ni TEST bazasiga yo'naltiradi.

    ⚠️ NEGA KERAK: `dependency_overrides[get_db]` faqat ENDPOINT bog'liqliklariga
    ta'sir qiladi. Kod ichida `SessionLocal()` ni TO'G'RIDAN-TO'G'RI chaqiradigan
    joylar undan chetda qoladi:
        * `database.init_db()`   — ilova lifespan'ida
        * `core.audit.log_audit()` — audit ataylab ALOHIDA sessiyada yozadi
    Ular DEV BAZASIGA yozardi — ya'ni har test yugurishi dev ma'lumotini
    o'zgartirardi va audit qatorlari testga umuman ko'rinmasdi.

    Ikkalasi ham `SessionLocal` ni chaqiruv PAYTIDA modul globalidan o'qiydi,
    shuning uchun modul atributini almashtirish yetarli.
    """
    import database as _db_mod
    asl = _db_mod.SessionLocal
    _db_mod.SessionLocal = TestingSessionLocal
    try:
        yield
    finally:
        _db_mod.SessionLocal = asl


@pytest.fixture(scope="session", autouse=True)
def setup_database(_sessionlocal_test_bazaga_yonaltirilsin):
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        _seed(db)
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def admin_token(client):
    """Admin token — TELEFON + parol bilan (BOSQICH 38 dan beri username emas)."""
    response = client.post("/api/v1/auth/login", data={
        "username": SEED_ADMIN_PHONE,      # OAuth2 form maydoni nomi; qiymat — telefon
        "password": SEED_ADMIN_PASSWORD,
    })
    assert response.status_code == 200, (
        f"Urug' admin login qilolmadi ({response.status_code}): {response.text}\n"
        "Bu fixture SKIP bermaydi — buzilgan bo'lsa testlar YIQILISHI kerak, "
        "aks holda integratsiya testlari jimgina o'tkazib yuboriladi (2026-08-27 xatosi)."
    )
    return response.json()["access_token"]


@pytest.fixture(scope="function")
def auth_headers(admin_token):
    """Admin auth headerlari"""
    return {"Authorization": f"Bearer {admin_token}"}
