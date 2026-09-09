"""OMBOR BIRLIGI — mahsulot tahrirlanganda sinxronlanadimi (2026-09-09).

MUAMMO (jonli, 1001 BARAKA): birlik IKKI joyda dublikat saqlanadi —
`products.sale_unit` va `inventory.unit`. Lekin ularni bog'lab turadigan kod
YO'Q edi: `inventory.unit` faqat ombor qatori YARATILGANDA yozilardi
(`product.py` create + `inventory.py` lazily-create), `update_product` esa unga
umuman tegmasdi.

Natija: "YASHKINO AMERIKANSKOE" mahsuloti `g` → `dona` ga tahrirlangan, lekin
ombor ekrani hamon `g` ko'rsatardi — chunki u `inventory.unit` ni BIRINCHI manba
sifatida o'qiydi (`inventory.html:498`). Bazada tenant 27 bo'ylab aynan bitta
nomuvofiqlik bor edi.

⚠️ MIQDOR TEGILMAYDI. "500 g" ni "500 dona"ga aylantirish qoldiqni jimgina
buzardi (500 g ≠ 500 dona). Shuning uchun faqat YORLIQ yangilanadi va javobda
`unit_warning` qaytariladi. Bu test aynan shuni ham qulflaydi.

Ishga tushirish:
    cd backend && py -m pytest tests/test_inventory_unit_sync.py -v
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
from models import Cafe, Category, Inventory, Product, User, Role, Permission
from core.security import get_password_hash
from services.unit_converter import inventory_unit

ADMIN_PW = "AdminOmbor9x"
PHONE_A = "+998900000071"    # tenant A — sinov do'koni
PHONE_B = "+998900000072"    # tenant B — "FAZZA/ECO AROMA" o'rnida, TEGILMASIN


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
    db = db_session
    p_menu = Permission(code="manage_menu", description="Menyu")
    db.add(p_menu); db.flush()
    r_admin = Role(name="admin", description="Administrator")
    r_admin.permissions = [p_menu]
    db.add(r_admin); db.flush()

    cafe_a = Cafe(name="SINOV", code="a", access_code="100.200.71",
                  business_type="store", subscription_plan="pro", is_active=True)
    cafe_b = Cafe(name="BEGONA", code="b", access_code="100.200.72",
                  business_type="store", subscription_plan="pro", is_active=True)
    db.add_all([cafe_a, cafe_b]); db.flush()

    kat_a = Category(name="KAT A", tenant_id=cafe_a.id)
    kat_b = Category(name="KAT B", tenant_id=cafe_b.id)
    db.add_all([kat_a, kat_b]); db.flush()

    # A: `g` birlikli mahsulot + ombor qatori (aynan Yashkino holati)
    p_g = Product(name="YASHKINO", price=5000, cost_price=3000, sale_unit="g",
                  category_id=kat_a.id, tenant_id=cafe_a.id, is_active=True)
    # A: ombor qatori YO'Q mahsulot (chegaraviy holat)
    p_yoq = Product(name="OMBORSIZ", price=1000, sale_unit="pcs",
                    category_id=kat_a.id, tenant_id=cafe_a.id, is_active=True)
    # B: begona do'kon mahsuloti — TEGILMASLIGI kerak
    p_b = Product(name="BEGONA MAHSULOT", price=7000, sale_unit="kg",
                  category_id=kat_b.id, tenant_id=cafe_b.id, is_active=True)
    db.add_all([p_g, p_yoq, p_b]); db.flush()

    inv_g = Inventory(product_id=p_g.id, quantity=20, unit="g", tenant_id=cafe_a.id)
    inv_b = Inventory(product_id=p_b.id, quantity=500, unit="kg", tenant_id=cafe_b.id)
    db.add_all([inv_g, inv_b]); db.flush()

    for phone, cafe in ((PHONE_A, cafe_a), (PHONE_B, cafe_b)):
        db.add(User(username=f"u{cafe.id}", email=f"{cafe.id}@x.uz", full_name="A",
                    phone=phone, hashed_password=get_password_hash(ADMIN_PW),
                    is_active=True, is_superuser=False,
                    tenant_id=cafe.id, role_id=r_admin.id))
    db.commit()
    return {"db": db, "p_g": p_g.id, "p_yoq": p_yoq.id, "p_b": p_b.id,
            "inv_g": inv_g.id, "inv_b": inv_b.id, "kat_a": kat_a.id}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client, phone):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _patch(client, hdr, pid, body):
    return client.patch(f"/api/v1/products/{pid}", json=body, headers=hdr)


# ══════════════════════════════════════════════════════════════════════════════
# 1) ASOSIY: sale_unit o'zgarsa inventory.unit ham yangilanadi
# ══════════════════════════════════════════════════════════════════════════════

def test_sale_unit_ozgarsa_inventory_unit_yangilanadi(client, seeded):
    """ILGARI: inventory.unit 'g' bo'lib qolardi va ekran eski birlikni ko'rsatardi."""
    hdr = _login(client, PHONE_A)
    db = seeded["db"]

    r = _patch(client, hdr, seeded["p_g"], {"sale_unit": "pcs"})
    assert r.status_code == 200, r.text

    db.expire_all()
    inv = db.query(Inventory).get(seeded["inv_g"])
    assert inv.unit == "dona", f"ombor birligi yangilanmadi: {inv.unit}"


def test_MIQDOR_ozgarmaydi(client, seeded):
    """⚠️ Eng muhim kafolat: yorliq yangilanadi, QOLDIQ RAQAMI tegilmaydi.

    Avtomatik konvertatsiya (20 g → 0.02 kg yoki 20 dona) qoldiqni jimgina
    buzardi. Admin qoldiqni o'zi tekshiradi.
    """
    hdr = _login(client, PHONE_A)
    db = seeded["db"]
    oldingi = db.query(Inventory).get(seeded["inv_g"]).quantity

    _patch(client, hdr, seeded["p_g"], {"sale_unit": "pcs"})

    db.expire_all()
    assert db.query(Inventory).get(seeded["inv_g"]).quantity == oldingi == 20


def test_ogohlantirish_qaytadi(client, seeded):
    """Javobda `unit_warning` — admin qoldiqni tekshirishi kerakligi aytiladi."""
    hdr = _login(client, PHONE_A)
    r = _patch(client, hdr, seeded["p_g"], {"sale_unit": "pcs"})
    ogoh = r.json().get("unit_warning")
    assert ogoh, "ogohlantirish qaytmadi"
    assert "g" in ogoh and "dona" in ogoh
    assert "20" in ogoh, f"qoldiq raqami ko'rsatilmadi: {ogoh}"


# ══════════════════════════════════════════════════════════════════════════════
# 2) pcs → dona o'girish qoidasi
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sotuv,ombor", [
    ("pcs", "dona"),      # yagona o'girish
    ("kg", "kg"),
    ("g", "g"),
    ("l", "l"),
    ("ml", "ml"),
    ("box", "box"),
    (None, "dona"),       # bo'sh → dona
    ("", "dona"),
])
def test_inventory_unit_ogirish(sotuv, ombor):
    assert inventory_unit(sotuv) == ombor


def test_pcs_dona_uchun_qayta_yozilmaydi(client, seeded):
    """`pcs` → `dona` allaqachon mos: ortiqcha yozuv ham, ogohlantirish ham yo'q."""
    hdr = _login(client, PHONE_A)
    db = seeded["db"]
    db.query(Inventory).filter(Inventory.id == seeded["inv_g"]).update({"unit": "dona"})
    db.commit()

    r = _patch(client, hdr, seeded["p_g"], {"sale_unit": "pcs"})
    assert r.status_code == 200
    assert r.json().get("unit_warning") is None, "keraksiz ogohlantirish"
    db.expire_all()
    assert db.query(Inventory).get(seeded["inv_g"]).unit == "dona"


# ══════════════════════════════════════════════════════════════════════════════
# 3) CHEGARAVIY HOLATLAR
# ══════════════════════════════════════════════════════════════════════════════

def test_ombor_qatori_yoq_mahsulot_xato_bermaydi(client, seeded):
    """Ombor qatori bo'lmagan mahsulotni tahrirlash 500 bermasin."""
    hdr = _login(client, PHONE_A)
    r = _patch(client, hdr, seeded["p_yoq"], {"sale_unit": "kg"})
    assert r.status_code == 200, f"ombor qatorisiz yiqildi: {r.status_code} {r.text}"
    assert r.json()["sale_unit"] == "kg"
    assert r.json().get("unit_warning") is None


def test_birlik_ozgarmasa_omborga_TEGILMAYDI(client, seeded):
    """Faqat nom/narx tahrirlansa ombor birligi o'z holicha qoladi."""
    hdr = _login(client, PHONE_A)
    db = seeded["db"]

    r = _patch(client, hdr, seeded["p_g"], {"name": "YASHKINO YANGI", "price": 6000})
    assert r.status_code == 200
    assert r.json().get("unit_warning") is None
    db.expire_all()
    inv = db.query(Inventory).get(seeded["inv_g"])
    assert (inv.unit, inv.quantity) == ("g", 20), "birlik o'zgarmagan holda ombor tegildi"


# ══════════════════════════════════════════════════════════════════════════════
# 4) BEGONA TENANT BUZILMASIN (FAZZA / ECO AROMA kafolati)
# ══════════════════════════════════════════════════════════════════════════════

def test_begona_tenant_ombori_TEGILMAYDI(client, seeded):
    """A do'kon tahriri B do'konning ombor qatoriga hech qanday ta'sir qilmasin."""
    hdr = _login(client, PHONE_A)
    db = seeded["db"]
    b_oldin = (db.query(Inventory).get(seeded["inv_b"]).unit,
               db.query(Inventory).get(seeded["inv_b"]).quantity)

    _patch(client, hdr, seeded["p_g"], {"sale_unit": "pcs"})

    db.expire_all()
    inv_b = db.query(Inventory).get(seeded["inv_b"])
    assert (inv_b.unit, inv_b.quantity) == b_oldin == ("kg", 500)


def test_begona_mahsulotni_tahrirlab_bolmaydi(client, seeded):
    """A do'kon B ning mahsulotini umuman tahrirlay olmaydi (404)."""
    hdr = _login(client, PHONE_A)
    r = _patch(client, hdr, seeded["p_b"], {"sale_unit": "pcs"})
    assert r.status_code == 404
    seeded["db"].expire_all()
    assert seeded["db"].query(Inventory).get(seeded["inv_b"]).unit == "kg"


# ══════════════════════════════════════════════════════════════════════════════
# 5) YARATISH yo'li buzilmagan (yordamchi refaktoringidan keyin)
# ══════════════════════════════════════════════════════════════════════════════

def test_yangi_mahsulot_ombor_birligi_togri(client, seeded):
    """create_product endi `inventory_unit()` yordamchisini ishlatadi."""
    hdr = _login(client, PHONE_A)
    db = seeded["db"]
    r = client.post("/api/v1/products/", headers=hdr, json={
        "name": "YANGI KG", "price": 9000, "category_id": seeded["kat_a"], "sale_unit": "kg",
    })
    assert r.status_code == 200, r.text
    inv = db.query(Inventory).filter(Inventory.product_id == r.json()["id"]).first()
    assert inv is not None and inv.unit == "kg"

    r2 = client.post("/api/v1/products/", headers=hdr, json={
        "name": "YANGI PCS", "price": 9000, "category_id": seeded["kat_a"], "sale_unit": "pcs",
    })
    assert r2.status_code == 200, r2.text
    inv2 = db.query(Inventory).filter(Inventory.product_id == r2.json()["id"]).first()
    assert inv2 is not None and inv2.unit == "dona", "pcs → dona o'girish buzildi"
