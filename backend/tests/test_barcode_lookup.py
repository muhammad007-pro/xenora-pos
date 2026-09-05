"""Shtrix-kod lookup — `GET /products/lookup/{barcode}` (mahsulot qo'shishda
avtomatik nom topish).

Uch qatlam qulflanadi: `own` → `catalog` → `off`. Lekin bu testlarning ASOSIY
maqsadi tezlik yoki qulaylik emas — TENANT IZOLYATSIYASI. Endpoint umumiy
katalogdan o'qiydigan BIRINCHI joy, ya'ni bu yerda xato qilinsa bir do'konning
ma'lumoti boshqasiga oqib chiqadi.

Uch qat'iy shart (har biri alohida test bilan):
  1. `tenant_id` javobga HECH QACHON chiqmaydi;
  2. narx/qoldiq javobga HECH QACHON chiqmaydi;
  3. so'rovchining O'Z nomzodi "boshqa manba" bo'lib qaytmaydi.

Ishga tushirish:
    cd backend && py -m pytest tests/test_barcode_lookup.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.catalog import gs1_check_digit
from core.security import get_password_hash
from database import Base, get_db
from main import app
from models import (
    Cafe, CatalogCandidate, Category, OffProduct, Permission, Product,
    ProductBarcode, Role, User,
)
from routers.product import _lookup_limiter

ADMIN_A_PW = "AdminAlfa9x"
ADMIN_B_PW = "AdminBeta7y"
KASSIR_PW = "KassirC5z"


def _kod(tana: str) -> str:
    """Nazorat raqami to'g'ri bo'lgan kod quradi (test kodi o'zi buzuq bo'lmasin)."""
    return tana + str(gs1_check_digit(tana))


# Haqiqiy prefikslar: RU / TR / UZ / CN — sinov buyurtmada aynan shu to'rttasi.
KOD_RU = _kod("460129600734")
KOD_TR = _kod("869000000041")
KOD_UZ = _kod("478002262211")
KOD_CN = _kod("690000000107")
KOD_YOQ = _kod("477012345678")      # hech qayerda yo'q
KOD_ICHKI = _kod("200123456789")    # do'kon ichki kodi (prefiks 2)


@pytest.fixture()
def db_session():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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


@pytest.fixture(autouse=True)
def _limitni_tozalash():
    """Har test toza hisob bilan boshlansin (limiter modul darajasida yashaydi)."""
    _lookup_limiter.reset()
    yield
    _lookup_limiter.reset()


@pytest.fixture()
def seeded(db_session):
    """Ikki do'kon (A, B), ularning adminlari va ruxsatsiz kassir."""
    db = db_session

    p_menu = Permission(code="manage_menu", description="Menyu")
    p_pay = Permission(code="process_payments", description="To'lovlar")
    db.add_all([p_menu, p_pay])
    db.flush()

    r_admin = Role(name="admin", description="Administrator")
    r_admin.permissions = [p_menu, p_pay]
    r_kassir = Role(name="cashier", description="Kassir")
    r_kassir.permissions = [p_pay]          # manage_menu YO'Q
    db.add_all([r_admin, r_kassir])
    db.flush()

    cafe_a = Cafe(name="Do'kon A", code="doka", access_code="100.200.1",
                  business_type="store", subscription_plan="pro", is_active=True)
    cafe_b = Cafe(name="Do'kon B", code="dokb", access_code="100.200.2",
                  business_type="store", subscription_plan="pro", is_active=True)
    db.add_all([cafe_a, cafe_b])
    db.flush()

    admin_a = User(username="admin_a", email="a@x.uz", full_name="Admin A",
                   phone="+998900000001", hashed_password=get_password_hash(ADMIN_A_PW),
                   is_active=True, is_superuser=False, tenant_id=cafe_a.id,
                   role_id=r_admin.id)
    admin_b = User(username="admin_b", email="b@x.uz", full_name="Admin B",
                   phone="+998900000002", hashed_password=get_password_hash(ADMIN_B_PW),
                   is_active=True, is_superuser=False, tenant_id=cafe_b.id,
                   role_id=r_admin.id)
    kassir_a = User(username="kassir_a", email="k@x.uz", full_name="Kassir A",
                    phone="+998900000003", hashed_password=get_password_hash(KASSIR_PW),
                    is_active=True, is_superuser=False, tenant_id=cafe_a.id,
                    role_id=r_kassir.id)
    db.add_all([admin_a, admin_b, kassir_a])
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


def _lookup(client, headers, kod):
    return client.get(f"/api/v1/products/lookup/{kod}", headers=headers)


# ══════════════════════════════════════════════════════════════════════════════
# 1) QATLAMLAR — to'g'ri tartibda ishlaydimi
# ══════════════════════════════════════════════════════════════════════════════

def test_own_qatlami_ogohlantiradi(seeded, client):
    """O'z bazasida bor kod → source=own, product_id va ogohlantirish matni."""
    db = seeded["db"]
    kat = Category(name="Ichimlik", tenant_id=seeded["cafe_a"])
    db.add(kat)
    db.flush()
    p = Product(name="Pepsi 1L", price=12000, barcode=KOD_UZ,
                tenant_id=seeded["cafe_a"], category_id=kat.id, is_active=True)
    db.add(p)
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    r = _lookup(client, h, KOD_UZ)
    assert r.status_code == 200
    d = r.json()
    assert d["found"] is True
    assert d["source"] == "own"
    assert d["product_id"] == p.id
    assert d["name"] == "Pepsi 1L"
    assert d["category"] == "Ichimlik"
    assert "bazangizda bor" in (d["message"] or "")


def test_own_qatlami_qoshimcha_shtrix_kodni_ham_koradi(seeded, client):
    """Kod `product_barcodes` da bo'lsa ham "bazangizda bor" deyilsin.

    Aks holda bir mahsulotning ikkinchi kodi skanerlanganda "yo'q" deb aytib,
    dublikat yaratishga yo'l qo'yardik.
    """
    db = seeded["db"]
    p = Product(name="Cola 0.5", price=8000, barcode="ASOSIY-1",
                tenant_id=seeded["cafe_a"], is_active=True)
    db.add(p)
    db.flush()
    db.add(ProductBarcode(product_id=p.id, barcode=KOD_TR,
                          tenant_id=seeded["cafe_a"], barcode_type="EAN13"))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    d = _lookup(client, h, KOD_TR).json()
    assert d["source"] == "own"
    assert d["product_id"] == p.id


def test_catalog_qatlami_boshqa_dokon_nomini_taklif_qiladi(seeded, client):
    """B do'koni kiritgan nom A ga TAKLIF bo'lib keladi (tenant_id chiqmasdan)."""
    db = seeded["db"]
    db.add(CatalogCandidate(
        tenant_id=seeded["cafe_b"], barcode=KOD_RU,
        name_normalized="sosiski sochnie", name_original="Сосиски Сочные",
        category_hint="Kolbasa", unit="pcs", source="live",
    ))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    d = _lookup(client, h, KOD_RU).json()
    assert d["found"] is True
    assert d["source"] == "catalog"
    assert d["name"] == "Сосиски Сочные"
    assert d["category"] == "Kolbasa"
    assert d["unit"] == "pcs"
    assert d["votes"] == 1


def test_off_qatlami_brend_va_hajmni_qaytaradi(seeded, client):
    """Katalogda yo'q bo'lsa — tashqi baza (OFF): nom + brend + hajm + kategoriya."""
    db = seeded["db"]
    db.add(OffProduct(barcode=KOD_CN, name="Green Tea", brand="Master Kong",
                      quantity="500 ml", category="Iced teas", source="off"))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    d = _lookup(client, h, KOD_CN).json()
    assert d["source"] == "off"
    assert d["name"] == "Green Tea"
    assert d["brand"] == "Master Kong"
    assert d["quantity"] == "500 ml"
    assert d["category"] == "Iced teas"


def test_qatlam_tartibi_own_catalogdan_ustun(seeded, client):
    """Bir kod uch joyda ham bo'lsa — `own` g'olib (ogohlantirish muhimroq)."""
    db = seeded["db"]
    db.add(Product(name="O'z nomim", price=5000, barcode=KOD_RU,
                   tenant_id=seeded["cafe_a"], is_active=True))
    db.add(CatalogCandidate(tenant_id=seeded["cafe_b"], barcode=KOD_RU,
                            name_normalized="boshqa", name_original="Boshqa nom",
                            source="live"))
    db.add(OffProduct(barcode=KOD_RU, name="OFF nomi", source="off"))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    d = _lookup(client, h, KOD_RU).json()
    assert d["source"] == "own"
    assert d["name"] == "O'z nomim"


def test_catalog_offdan_ustun(seeded, client):
    """Katalog (bizning do'konlar) OFF (tashqi baza) dan ustun turadi."""
    db = seeded["db"]
    db.add(CatalogCandidate(tenant_id=seeded["cafe_b"], barcode=KOD_TR,
                            name_normalized="halva", name_original="Tahin halva 400g",
                            source="live"))
    db.add(OffProduct(barcode=KOD_TR, name="Halva", source="off"))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    d = _lookup(client, h, KOD_TR).json()
    assert d["source"] == "catalog"
    assert d["name"] == "Tahin halva 400g"


def test_topilmasa_jimgina_bosh_javob(seeded, client):
    """Topilmasa 404 EMAS — found=false. UI xato ko'rsatmasin, jimgina o'tsin."""
    h = _login(client, "+998900000001", ADMIN_A_PW)
    r = _lookup(client, h, KOD_YOQ)
    assert r.status_code == 200
    d = r.json()
    assert d["found"] is False
    assert d["source"] is None
    assert d["name"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 2) TENANT IZOLYATSIYASI — eng muhim qism
# ══════════════════════════════════════════════════════════════════════════════

def test_tenant_id_javobga_hech_qachon_chiqmaydi(seeded, client):
    """⚠️ Javobda `tenant_id` bo'lmasin — "qaysi do'kon nima sotadi" sizmasin."""
    db = seeded["db"]
    db.add(CatalogCandidate(tenant_id=seeded["cafe_b"], barcode=KOD_RU,
                            name_normalized="test", name_original="Test nom",
                            source="live"))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    r = _lookup(client, h, KOD_RU)
    d = r.json()
    assert "tenant_id" not in d
    assert "tenant" not in r.text.lower()
    # Ehtiyot shart: do'kon nomi ham chiqmasin
    assert "Do'kon B" not in r.text


def test_narx_va_qoldiq_javobga_chiqmaydi(seeded, client):
    """⚠️ Narx HECH QACHON qaytmasin — raqobatchi narxini o'qiy olmasin."""
    db = seeded["db"]
    db.add(Product(name="Qimmat mahsulot", price=999999, cost_price=500000,
                   barcode=KOD_UZ, tenant_id=seeded["cafe_a"], is_active=True))
    db.add(OffProduct(barcode=KOD_CN, name="OFF mahsulot", source="off"))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    for kod in (KOD_UZ, KOD_CN):
        d = _lookup(client, h, kod).json()
        for taqiq in ("price", "cost_price", "stock", "quantity_in_stock", "tenant_id"):
            if taqiq == "quantity_in_stock":
                continue
            assert taqiq not in d or taqiq == "quantity", f"{taqiq} javobda bor!"
        assert "999999" not in str(d)
        assert "500000" not in str(d)


def test_oz_nomzodi_boshqa_manba_bolib_qaytmaydi(seeded, client):
    """A ning O'Z nomzodi A ga "katalogdan topildi" bo'lib qaytmasin.

    Aks holda do'kon o'z yozganini "boshqa do'kon tasdiqladi" deb o'qirdi —
    ovoz sanash ma'nosini yo'qotardi.
    """
    db = seeded["db"]
    db.add(CatalogCandidate(tenant_id=seeded["cafe_a"], barcode=KOD_RU,
                            name_normalized="ozimniki", name_original="O'zimniki",
                            source="live"))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    d = _lookup(client, h, KOD_RU).json()
    assert d["found"] is False, "o'z nomzodi qaytib keldi"


def test_boshqa_tenant_mahsuloti_own_bolib_kelmaydi(seeded, client):
    """B ning mahsuloti A uchun `own` bo'lib ko'rinmasin (apply_tenant_filter)."""
    db = seeded["db"]
    db.add(Product(name="B do'koni mahsuloti", price=1000, barcode=KOD_UZ,
                   tenant_id=seeded["cafe_b"], is_active=True))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    d = _lookup(client, h, KOD_UZ).json()
    assert d["source"] != "own"
    assert d["found"] is False
    assert "B do'koni" not in str(d)


def test_ovoz_sanash_kopchilik_golib(seeded, client):
    """Ikki do'kon bir nomni, bittasi boshqa nomni yozgan → ko'pchilik yutadi."""
    db = seeded["db"]
    cafe_c = Cafe(name="Do'kon C", code="dokc", access_code="100.200.3",
                  business_type="store", subscription_plan="free", is_active=True)
    db.add(cafe_c)
    db.flush()
    db.add_all([
        CatalogCandidate(tenant_id=seeded["cafe_b"], barcode=KOD_RU,
                         name_normalized="kolbasa dok", name_original="Kolbasa Doktorskaya",
                         source="live"),
        CatalogCandidate(tenant_id=cafe_c.id, barcode=KOD_RU,
                         name_normalized="kolbasa dok", name_original="Kolbasa Doktorskaya",
                         source="live"),
        CatalogCandidate(tenant_id=seeded["cafe_a"], barcode=KOD_RU,
                         name_normalized="kolbasa", name_original="Kolbasa",
                         source="live"),
    ])
    db.commit()

    # C do'koniga kirmaymiz — B ning ovozi ham, C niki ham A uchun tashqi.
    # A o'z yozuvi hisobga OLINMAYDI, ya'ni 2 ovozli nom g'olib.
    h = _login(client, "+998900000001", ADMIN_A_PW)
    d = _lookup(client, h, KOD_RU).json()
    assert d["source"] == "catalog"
    assert d["name"] == "Kolbasa Doktorskaya"
    assert d["votes"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# 3) RUXSAT, CHEKLOV, OQ RO'YXAT
# ══════════════════════════════════════════════════════════════════════════════

def test_ruxsatsiz_kassir_403(seeded, client):
    """Lookup umumiy katalogdan o'qiydi → `manage_menu` ruxsati SHART."""
    h = _login(client, "+998900000003", KASSIR_PW)
    r = _lookup(client, h, KOD_RU)
    assert r.status_code == 403


def test_autentifikatsiyasiz_401(seeded, client):
    r = client.get(f"/api/v1/products/lookup/{KOD_RU}")
    assert r.status_code in (401, 403)


def test_ichki_kod_umumiy_katalogga_bormaydi(seeded, client):
    """Prefiks 2 (do'kon ichki kodi) — katalog/OFF so'ralmaydi.

    Ichki kodlar do'konga xos: ikki do'kon bir kodni ikki xil mahsulotga beradi.
    Yozishda ham (`core/catalog.py`), o'qishda ham AYNI filtr ishlashi kerak.
    """
    db = seeded["db"]
    db.add(CatalogCandidate(tenant_id=seeded["cafe_b"], barcode=KOD_ICHKI,
                            name_normalized="ichki", name_original="Ichki kod nomi",
                            source="live"))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    d = _lookup(client, h, KOD_ICHKI).json()
    assert d["found"] is False, "ichki kod bo'yicha begona nom qaytdi"


def test_tezlik_chegarasi_429(seeded, client):
    """Cheklov oshsa 429 — ommaviy yig'ishning oldini oladi."""
    h = _login(client, "+998900000001", ADMIN_A_PW)
    eski = _lookup_limiter.limit
    _lookup_limiter.limit = 3
    _lookup_limiter.reset()
    try:
        for _ in range(3):
            assert _lookup(client, h, KOD_YOQ).status_code == 200
        r = _lookup(client, h, KOD_YOQ)
        assert r.status_code == 429
        assert r.headers.get("Retry-After")
    finally:
        _lookup_limiter.limit = eski
        _lookup_limiter.reset()


def test_cheklov_tenant_boyicha_alohida(seeded, client):
    """A ning limiti tugasa, B ishlashda davom etsin (kalit — tenant)."""
    ha = _login(client, "+998900000001", ADMIN_A_PW)
    hb = _login(client, "+998900000002", ADMIN_B_PW)
    eski = _lookup_limiter.limit
    _lookup_limiter.limit = 2
    _lookup_limiter.reset()
    try:
        for _ in range(2):
            _lookup(client, ha, KOD_YOQ)
        assert _lookup(client, ha, KOD_YOQ).status_code == 429
        assert _lookup(client, hb, KOD_YOQ).status_code == 200
    finally:
        _lookup_limiter.limit = eski
        _lookup_limiter.reset()


def test_bosh_va_juda_uzun_kod_yiqilmaydi(seeded, client):
    """Axlat kirish 500 bermasin."""
    h = _login(client, "+998900000001", ADMIN_A_PW)
    for kod in ("0", "x" * 60, "abc-def", "%20"):
        r = _lookup(client, h, kod)
        assert r.status_code in (200, 404), f"{kod} -> {r.status_code}"


# ══════════════════════════════════════════════════════════════════════════════
# 4) GOLDEN — mavjud oqim buzilmasin
# ══════════════════════════════════════════════════════════════════════════════

def test_mahsulot_yaratish_oqimi_buzilmadi(seeded, client):
    """Lookup qo'shilgandan keyin ham mahsulot yaratish avvalgidek ishlaydi."""
    db = seeded["db"]
    kat = Category(name="Umumiy", tenant_id=seeded["cafe_a"])
    db.add(kat)
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    r = client.post("/api/v1/products/", headers=h, json={
        "name": "Yangi mahsulot", "price": 15000, "barcode": KOD_UZ,
        "category_id": kat.id,
    })
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Yangi mahsulot"

    # ...va endi u o'z bazasida topiladi
    d = _lookup(client, h, KOD_UZ).json()
    assert d["source"] == "own"


def test_eski_barcode_endpointi_ishlashda_davom_etadi(seeded, client):
    """`/products/barcode/{kod}` (POS ishlatadi) yangi marshrut bilan to'qnashmasin."""
    db = seeded["db"]
    kat = Category(name="POS kat", tenant_id=seeded["cafe_a"])
    db.add(kat)
    db.flush()
    db.add(Product(name="POS mahsuloti", price=3000, barcode=KOD_CN,
                   tenant_id=seeded["cafe_a"], category_id=kat.id, is_active=True))
    db.commit()

    h = _login(client, "+998900000001", ADMIN_A_PW)
    r = client.get(f"/api/v1/products/barcode/{KOD_CN}", headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "POS mahsuloti"
