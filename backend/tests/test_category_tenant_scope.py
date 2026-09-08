"""KATEGORIYA NOMI — tenant izolyatsiyasi (2026-09-09 auditi).

MUAMMO (jonli, tuzatilgunga qadar):
    `POST /api/v1/categories/` dagi takrorlanish tekshiruvi FILTRSIZ edi:

        db.query(Category).filter(Category.name == category_data.name).first()

    Ya'ni bitta do'kon nomni band qilsa, BOSHQA do'kon o'sha nomni umuman
    ishlata olmasdi. Prod isboti: FAZZA (26) "UMUMIY" yaratgan → 1001 BARAKA (27)
    o'sha nomni yozolmay, "UMUMIY mahsulotlar" deb nomlashga majbur bo'lgan.
    Butun bazada birorta kategoriya nomi ikki tenantda takrorlanmasligi —
    aynan shu global tekshiruvning barmoq izi edi.

    Yonma-yon: `POST /api/v1/products/` dagi kategoriya qidiruvi ham filtrsiz
    edi → mahsulotni BEGONA do'kon kategoriyasiga biriktirib yuborish mumkin edi.

TUZATISH:
    1. `category.py` — takrorlanish FAQAT o'z tenant'i ichida (`apply_tenant_filter`)
    2. `category.py` — registrga sezgir emas: "Umumiy" == "UMUMIY" (`func.lower`)
    3. `product.py`  — kategoriya qidiruvi ham `apply_tenant_filter` bilan

    Xato xabarlari o'zgarmadi ("Bu nomdagi kategoriya mavjud" / "Kategoriya topilmadi").
    Migratsiya YO'Q — bazadagi UNIQUE constraint masalasi roadmapda (ROADMAP.md).

Ishga tushirish:
    cd backend && py -m pytest tests/test_category_tenant_scope.py -v
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
from models import Cafe, Category, User, Role, Permission
from core.security import get_password_hash

ADMIN_A_PW = "AdminAlfa9x"
ADMIN_B_PW = "AdminBeta7y"

PHONE_A = "+998900000011"
PHONE_B = "+998900000012"


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
    """Ikki do'kon (A=FAZZA o'rnida, B=1001 BARAKA o'rnida) va ularning adminlari."""
    db = db_session

    p_menu    = Permission(code="manage_menu",       description="Menyu")
    p_reports = Permission(code="view_reports",      description="Hisobotlar")
    db.add_all([p_menu, p_reports])
    db.flush()

    r_admin = Role(name="admin", description="Administrator")
    r_admin.permissions = [p_menu, p_reports]
    db.add(r_admin)
    db.flush()

    cafe_a = Cafe(name="Do'kon A", code="doka", access_code="100.200.11",
                  business_type="store", subscription_plan="pro", is_active=True)
    cafe_b = Cafe(name="Do'kon B", code="dokb", access_code="100.200.12",
                  business_type="store", subscription_plan="pro", is_active=True)
    db.add_all([cafe_a, cafe_b])
    db.flush()

    admin_a = User(username="admin_a", email="a@x.uz", full_name="Admin A",
                   phone=PHONE_A, hashed_password=get_password_hash(ADMIN_A_PW),
                   is_active=True, is_superuser=False,
                   tenant_id=cafe_a.id, role_id=r_admin.id)
    admin_b = User(username="admin_b", email="b@x.uz", full_name="Admin B",
                   phone=PHONE_B, hashed_password=get_password_hash(ADMIN_B_PW),
                   is_active=True, is_superuser=False,
                   tenant_id=cafe_b.id, role_id=r_admin.id)
    db.add_all([admin_a, admin_b])
    db.commit()

    return {"db": db, "cafe_a": cafe_a.id, "cafe_b": cafe_b.id}


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


def _kategoriya(client, headers, nom):
    return client.post("/api/v1/categories/", json={"name": nom}, headers=headers)


# ══════════════════════════════════════════════════════════════════════════════
# 1) ASOSIY TESHIK: begona do'kon nomni band qila olmaydi
# ══════════════════════════════════════════════════════════════════════════════

def test_ikki_tenant_bir_xil_nomni_yarata_oladi(client, seeded):
    """ILGARI: B do'kon 400 olardi (A band qilgani uchun). ENDI: ikkalasi ham 200."""
    hdr_a = _login(client, PHONE_A, ADMIN_A_PW)
    hdr_b = _login(client, PHONE_B, ADMIN_B_PW)

    ra = _kategoriya(client, hdr_a, "UMUMIY")
    assert ra.status_code == 200, f"A yarata olmadi: {ra.status_code} {ra.text}"

    rb = _kategoriya(client, hdr_b, "UMUMIY")
    assert rb.status_code == 200, (
        f"REGRESSIYA — begona tenant nomni to'sib qo'ydi: {rb.status_code} {rb.text}")

    # Har biri O'Z do'koniga biriktirilgan (nom bir xil bo'lsa ham)
    assert ra.json()["id"] != rb.json()["id"]
    db = seeded["db"]
    assert db.query(Category).get(ra.json()["id"]).tenant_id == seeded["cafe_a"]
    assert db.query(Category).get(rb.json()["id"]).tenant_id == seeded["cafe_b"]


def test_begona_kategoriya_ro_yxatda_ko_rinmaydi(client, seeded):
    """Nom umumiy bo'lsa ham, B faqat O'Z kategoriyasini ko'radi."""
    hdr_a = _login(client, PHONE_A, ADMIN_A_PW)
    hdr_b = _login(client, PHONE_B, ADMIN_B_PW)
    _kategoriya(client, hdr_a, "PARFUMERIYA")
    rb = _kategoriya(client, hdr_b, "PARFUMERIYA")
    assert rb.status_code == 200

    r = client.get("/api/v1/categories/all", headers=hdr_b)
    assert r.status_code == 200
    idlar = [c["id"] for c in r.json()]
    assert idlar == [rb.json()["id"]], f"B begona kategoriyani ko'rdi: {r.json()}"


# ══════════════════════════════════════════════════════════════════════════════
# 2) MAVJUD XULQ SAQLANSIN: o'z ichida takror — baribir 400
# ══════════════════════════════════════════════════════════════════════════════

def test_bitta_tenant_ichida_takror_nom_400(client, seeded):
    """Tuzatish himoyani BO'SHATMASLIGI kerak — o'z do'konida dublikat bloklanadi."""
    hdr_a = _login(client, PHONE_A, ADMIN_A_PW)

    assert _kategoriya(client, hdr_a, "ICHIMLIKLAR").status_code == 200

    r = _kategoriya(client, hdr_a, "ICHIMLIKLAR")
    assert r.status_code == 400, f"dublikat o'tib ketdi: {r.status_code} {r.text}"
    assert r.json()["detail"] == "Bu nomdagi kategoriya mavjud"   # xabar o'zgarmagan


# ══════════════════════════════════════════════════════════════════════════════
# 3) YANGI XULQ: registr farqi dublikat hisoblanadi
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("birinchi,ikkinchi", [
    ("Umumiy", "UMUMIY"),
    ("UMUMIY", "umumiy"),
    ("Ichimliklar", "ICHIMLIKLAR"),
])
def test_registr_farqi_ham_takror_400(client, seeded, birinchi, ikkinchi):
    """ILGARI: "Umumiy" va "UMUMIY" ikki alohida kategoriya bo'lardi (chalkashlik)."""
    hdr_a = _login(client, PHONE_A, ADMIN_A_PW)

    assert _kategoriya(client, hdr_a, birinchi).status_code == 200

    r = _kategoriya(client, hdr_a, ikkinchi)
    assert r.status_code == 400, (
        f"'{birinchi}' bor edi, '{ikkinchi}' o'tib ketdi: {r.status_code} {r.text}")
    assert r.json()["detail"] == "Bu nomdagi kategoriya mavjud"


def test_registr_tekshiruvi_tenantdan_oshmaydi(client, seeded):
    """Registr qoidasi ham FAQAT o'z do'koni ichida — B ga "umumiy" ochiq."""
    hdr_a = _login(client, PHONE_A, ADMIN_A_PW)
    hdr_b = _login(client, PHONE_B, ADMIN_B_PW)

    assert _kategoriya(client, hdr_a, "UMUMIY").status_code == 200
    r = _kategoriya(client, hdr_b, "umumiy")
    assert r.status_code == 200, f"registr tekshiruvi tenantdan oshdi: {r.text}"


# ══════════════════════════════════════════════════════════════════════════════
# 4) MAHSULOT: begona kategoriyaga biriktirib bo'lmaydi
# ══════════════════════════════════════════════════════════════════════════════

def test_begona_category_id_bilan_mahsulot_yaratilmaydi(client, seeded):
    """ILGARI: A ning kategoriyasi B ning mahsulotiga biriktirilardi."""
    hdr_a = _login(client, PHONE_A, ADMIN_A_PW)
    hdr_b = _login(client, PHONE_B, ADMIN_B_PW)

    kat_a = _kategoriya(client, hdr_a, "A KATEGORIYA").json()["id"]

    r = client.post("/api/v1/products/", headers=hdr_b, json={
        "name": "Begona kategoriyali mahsulot",
        "price": 1000,
        "category_id": kat_a,
    })
    assert r.status_code == 404, f"begona kategoriya qabul qilindi: {r.status_code} {r.text}"
    assert r.json()["detail"] == "Kategoriya topilmadi"

    # Mahsulot umuman yaratilmagan bo'lishi kerak
    from models import Product
    assert seeded["db"].query(Product).filter(
        Product.name == "Begona kategoriyali mahsulot").first() is None


def test_oz_kategoriyasi_bilan_mahsulot_ishlaydi(client, seeded):
    """REGRESSIYA: normal oqim (o'z kategoriyasi) buzilmagan."""
    hdr_b = _login(client, PHONE_B, ADMIN_B_PW)
    kat_b = _kategoriya(client, hdr_b, "B KATEGORIYA").json()["id"]

    r = client.post("/api/v1/products/", headers=hdr_b, json={
        "name": "O'z mahsuloti",
        "price": 1500,
        "category_id": kat_b,
    })
    assert r.status_code == 200, f"normal oqim buzildi: {r.status_code} {r.text}"
    assert r.json()["category_id"] == kat_b


# ══════════════════════════════════════════════════════════════════════════════
# 5) MAVJUD MA'LUMOT BUZILMASIN
# ══════════════════════════════════════════════════════════════════════════════

def test_mavjud_kategoriyalar_tegilmaydi(client, seeded):
    """Prodda 38 kategoriya bor — tuzatish ularni o'zgartirmaydi/o'chirmaydi.

    Bu yerda o'sha holat modellashtirilgan: oldindan mavjud (registri turlicha,
    ikki tenantga tarqalgan) kategoriyalar o'qilaveradi va yangi yozuv qo'shilishi
    ularning birortasini ham o'zgartirmaydi.
    """
    db = seeded["db"]
    oldindan = [
        Category(name="Umumiy",     tenant_id=seeded["cafe_a"]),
        Category(name="MAROJNOE",   tenant_id=seeded["cafe_a"]),
        Category(name="Ichimliklar", tenant_id=seeded["cafe_b"]),
    ]
    db.add_all(oldindan)
    db.commit()
    avvalgi = {c.id: (c.name, c.tenant_id) for c in oldindan}

    hdr_b = _login(client, PHONE_B, ADMIN_B_PW)
    assert _kategoriya(client, hdr_b, "MAROJNOE").status_code == 200   # A da bor, B da yo'q

    db.expire_all()
    for kid, (nom, tid) in avvalgi.items():
        c = db.query(Category).get(kid)
        assert c is not None, f"kategoriya {kid} yo'qoldi"
        assert (c.name, c.tenant_id) == (nom, tid), f"kategoriya {kid} o'zgardi"
