"""POS SKANER — `GET /barcodes/lookup/{kod}` BITTA so'rovda yetarli (2026-11-18).

NEGA: FAZZA (26) da skaner sekin edi. POS xotirada topmagan kod uchun ikki
so'rovni KETMA-KET yuborardi: `/barcodes/lookup` (404) → `/products/?search=`
(ilike, `items[0]`). Server har birida 5–15 ms, lekin tarmoq ~200 ms
(Amsterdam). Ikkinchi so'rov esa QISMAN moslik bilan TASODIFIY mahsulot
qaytarardi (prod, 7 kun: 133 ta 404 kodning birortasi to'g'ri topilmagan;
"82" → 44 ta qisman moslik).

Endi POS faqat lookup'ni chaqiradi. Shu sabab lookup:
  • aniq SKU ni ham tekshiradi (eski fallback'ning yagona to'g'ri holati),
  • POS savat mantig'i uchun maydonlarni qaytaradi (pachka, ko'tara, birlik),
  • QISMAN moslik QILMAYDI (tasodifiy mahsulot qaytmasin),
  • eski kalitlarni saqlaydi (inventory/kirim/firma sahifalari o'qiydi).

Ishga tushirish:
    cd backend && py -m pytest tests/test_barcodes_lookup_pos.py -v
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
from models import Cafe, Category, Product, ProductBarcode, User, Role, Permission
from core.security import get_password_hash

PW = "ScanSpeed9x"
PHONE_A = "+998900000091"
PHONE_B = "+998900000092"

# Eski iste'molchilar (inventory.html, purchase_receipts.html, suppliers.html)
# o'qiydigan kalitlar — O'CHMASLIGI kerak.
ESKI_KALITLAR = {"id", "name", "price", "cost_price", "barcode", "unit",
                 "image_url", "barcode_type", "weight_variable"}
# POS savat mantig'i uchun QO'SHILGANLAR
POS_KALITLAR = {"sale_unit", "sku", "category_id", "is_active", "is_available",
                "pack_size", "pack_price", "wholesale_price", "wholesale_min_qty",
                "requires_prescription", "active_ingredient", "dosage"}


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
    role = Role(name="admin", description="Administrator")
    role.permissions = [p_menu]
    db.add(role); db.flush()

    cafe_a = Cafe(name="ATIR", code="a", access_code="100.200.91",
                  business_type="store", subscription_plan="pro", is_active=True)
    cafe_b = Cafe(name="BEGONA", code="b", access_code="100.200.92",
                  business_type="store", subscription_plan="pro", is_active=True)
    db.add_all([cafe_a, cafe_b]); db.flush()
    kat_a = Category(name="KAT A", tenant_id=cafe_a.id)
    kat_b = Category(name="KAT B", tenant_id=cafe_b.id)
    db.add_all([kat_a, kat_b]); db.flush()

    pachka = Product(name="ATIR PACHKA", price=50000, cost_price=30000,
                     barcode="4780019310302", sale_unit="pcs", pack_size=6,
                     pack_price=280000, wholesale_price=45000, wholesale_min_qty=12,
                     category_id=kat_a.id, tenant_id=cafe_a.id, is_active=True)
    skuli = Product(name="SKU MAHSULOT", price=10000, sku="M300006", sale_unit="pcs",
                    category_id=kat_a.id, tenant_id=cafe_a.id, is_active=True)
    # Shtrix-kodi boshqa mahsulotning SKU si bilan BIR XIL — shtrix-kod ustun
    ustun_bc = Product(name="USTUN BARCODE", price=1000, barcode="2222",
                       category_id=kat_a.id, tenant_id=cafe_a.id, is_active=True)
    ustun_sku = Product(name="USTUN SKU", price=1000, sku="2222",
                        category_id=kat_a.id, tenant_id=cafe_a.id, is_active=True)
    # Narxi 0 — ProductInDB (price > 0) bilan o'qilsa 500 berardi
    bepul = Product(name="NARXSIZ", price=0, barcode="5555555555555",
                    category_id=kat_a.id, tenant_id=cafe_a.id, is_active=True)
    begona = Product(name="BEGONA SKU", price=7000, sku="BEG777",
                     category_id=kat_b.id, tenant_id=cafe_b.id, is_active=True)
    # O'CHIRILGAN, lekin kodlari SAQLANGAN (PATCH is_active=false / qo'lda SQL
    # yo'li — ilovaning "O'chirish" tugmasi esa kodni NULL qiladi)
    ochirilgan = Product(name="OCHIRILGAN", price=3000, barcode="9990001112223",
                         sku="DEL001", category_id=kat_a.id, tenant_id=cafe_a.id,
                         is_active=False, is_available=False)
    # Boshqa tenantda AYNI shtrix-kod FAOL — o'z tenantida topiladi, A ga sizmaydi
    begona_faol = Product(name="BEGONA FAOL", price=4000, barcode="9990001112223",
                          category_id=kat_b.id, tenant_id=cafe_b.id, is_active=True)
    db.add_all([pachka, skuli, ustun_bc, ustun_sku, bepul, begona,
                ochirilgan, begona_faol]); db.flush()
    # Qo'shimcha kod (product_barcodes) va tarozi PLU ham o'chirilganga ishora qiladi
    db.add_all([
        ProductBarcode(tenant_id=cafe_a.id, product_id=ochirilgan.id, barcode="7770001"),
        ProductBarcode(tenant_id=cafe_a.id, product_id=ochirilgan.id, barcode="12345",
                       weight_variable=True),
    ])

    for phone, cafe in ((PHONE_A, cafe_a), (PHONE_B, cafe_b)):
        db.add(User(username=f"u{phone[-3:]}", email=f"{phone[-3:]}@x.uz",
                    full_name="U", phone=phone, hashed_password=get_password_hash(PW),
                    is_active=True, is_superuser=False, tenant_id=cafe.id,
                    role_id=role.id))
    db.commit()
    return {"pachka": pachka.id, "skuli": skuli.id, "ustun_bc": ustun_bc.id,
            "bepul": bepul.id, "begona_faol": begona_faol.id}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _hdr(client, phone=PHONE_A):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _lookup(client, hdr, kod):
    return client.get(f"/api/v1/barcodes/lookup/{kod}", headers=hdr)


# ── 1) Javob POS uchun yetarli, eski kalitlar joyida ─────────────────────────

def test_asosiy_barcode_POS_maydonlari_bilan(client, seeded):
    r = _lookup(client, _hdr(client), "4780019310302")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["id"] == seeded["pachka"]
    assert ESKI_KALITLAR <= set(d), ESKI_KALITLAR - set(d)
    assert POS_KALITLAR <= set(d), POS_KALITLAR - set(d)
    assert d["sale_unit"] == "pcs" and d["unit"] == "pcs"
    assert (d["pack_size"], d["pack_price"]) == (6, 280000)
    assert (d["wholesale_price"], d["wholesale_min_qty"]) == (45000, 12)


def test_narxi_nol_mahsulot_500_bermaydi(client, seeded):
    r = _lookup(client, _hdr(client), "5555555555555")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded["bepul"]


# ── 2) Aniq SKU — eski `/products/?search` ning yagona to'g'ri holati ────────

def test_aniq_sku_topiladi(client, seeded):
    r = _lookup(client, _hdr(client), "M300006")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded["skuli"]


def test_barcode_SKU_dan_ustun(client, seeded):
    r = _lookup(client, _hdr(client), "2222")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded["ustun_bc"]


def test_begona_tenant_SKU_si_topilmaydi(client, seeded):
    assert _lookup(client, _hdr(client), "BEG777").status_code == 404
    # o'z tenantida esa topiladi
    assert _lookup(client, _hdr(client, PHONE_B), "BEG777").status_code == 200


# ── 3) ⚠️ QISMAN moslik YO'Q — tasodifiy mahsulot qaytmasin ─────────────────

@pytest.mark.parametrize("kod", [
    "478001931030",     # barcode'ning boshi (kesilgan skan)
    "82",               # prodda 44 ta qisman moslik bergan kod
    "M3000",            # SKU ning boshi
    "ATIR",             # mahsulot nomi
])
def test_qisman_moslik_404(client, seeded, kod):
    assert _lookup(client, _hdr(client), kod).status_code == 404


# ── 3b) ⚠️ O'CHIRILGAN mahsulot HECH BIR yo'lda qaytmaydi ────────────────────
# Ilgari qaytardi: POS xotirasida yo'q kod → lookup → o'chirilgan mahsulot savatga.

@pytest.mark.parametrize("kod,yol", [
    ("9990001112223", "asosiy shtrix-kod"),
    ("DEL001",        "SKU"),
    ("7770001",       "qo'shimcha kod (product_barcodes)"),
    ("2112345005007", "tarozi PLU (12345, 500 g)"),
])
def test_ochirilgan_mahsulot_404(client, seeded, kod, yol):
    r = _lookup(client, _hdr(client), kod)
    assert r.status_code == 404, f"{yol}: {r.status_code} {r.text}"


def test_ochirilgan_filtri_boshqa_tenantga_tegmaydi(client, seeded):
    # B da ayni kod FAOL — B o'zinikini topadi (A dagi o'chirilgan aralashmaydi)
    r = _lookup(client, _hdr(client, PHONE_B), "9990001112223")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == seeded["begona_faol"]


# ── 4) pos-stock chegarasi — butun katalog bir so'rovda ─────────────────────

def test_pos_stock_10000_qabul_qilinadi(client, seeded):
    hdr = _hdr(client)
    assert client.get("/api/v1/inventory/pos-stock?limit=10000", headers=hdr).status_code == 200
    assert client.get("/api/v1/inventory/pos-stock?limit=10001", headers=hdr).status_code == 422
