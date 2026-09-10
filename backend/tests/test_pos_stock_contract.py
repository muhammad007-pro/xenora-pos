"""POS-STOCK KONTRAKTI — `GET /inventory/pos-stock` javob SHAKLI (2026-09-10).

NEGA: `routers/inventory.py` da N+1 tuzatildi —
`db.query(Inventory).join(Product)` ga `.options(joinedload(Inventory.product))`
qo'shildi. Jonli o'lchov: 1001 BARAKA (524 qator) da javob 442–909 ms edi,
asosiy SQL esa o'zi 2 ms (`EXPLAIN ANALYZE`) — qolgani har qator uchun alohida
`SELECT products`.

⚠️ BU ENDPOINTNI POS KLIENTLARI ISHLATADI (kassir ekrani, offline sync) va
2026-09-10 dan beri admin "Mahsulotlar" ro'yxati ham. `joinedload` faqat
`i.product` QANDAY yuklanishini o'zgartiradi — javob dict'i qo'lda quriladi.
Bu test aynan shuni QULFLAYDI: kalitlar to'plami, qiymatlar, tenant/branch
izolyatsiyasi va `view_finance` gating'i o'zgarmasin.

Ishga tushirish:
    cd backend && py -m pytest tests/test_pos_stock_contract.py -v
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

ADMIN_PW = "PosStock9x"
PHONE_MOLIYA = "+998900000081"   # view_finance BOR — tannarx ko'radi
PHONE_KASSIR = "+998900000082"   # view_finance YO'Q — tannarx ko'rmaydi
PHONE_BEGONA = "+998900000083"   # boshqa tenant — o'z qatorlarini ko'radi

# Kassir HAR DOIM ko'radigan kalitlar (POS klienti shularga tayanadi)
ASOSIY_KALITLAR = {
    "product_id", "name", "price", "sale_unit",
    "quantity", "unit", "min_threshold",
    "image_url", "pack_size", "pack_price",
}
# view_finance bo'lsa QO'SHIMCHA keladiganlar
MOLIYA_KALITLAR = {"cost_price", "stock_value"}


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
    p_fin = Permission(code="view_finance", description="Moliya")
    p_menu = Permission(code="manage_menu", description="Menyu")
    db.add_all([p_fin, p_menu]); db.flush()

    r_admin = Role(name="admin", description="Administrator")
    r_admin.permissions = [p_fin, p_menu]
    r_kassir = Role(name="kassir", description="Kassir")
    r_kassir.permissions = [p_menu]          # view_finance ATAYLAB yo'q
    db.add_all([r_admin, r_kassir]); db.flush()

    cafe_a = Cafe(name="SINOV", code="a", access_code="100.200.81",
                  business_type="store", subscription_plan="pro", is_active=True)
    cafe_b = Cafe(name="BEGONA", code="b", access_code="100.200.82",
                  business_type="store", subscription_plan="pro", is_active=True)
    db.add_all([cafe_a, cafe_b]); db.flush()

    kat_a = Category(name="KAT A", tenant_id=cafe_a.id)
    kat_b = Category(name="KAT B", tenant_id=cafe_b.id)
    db.add_all([kat_a, kat_b]); db.flush()

    # A: pachkali dona mahsulot
    p1 = Product(name="AAA COCA", price=12000, cost_price=9000, sale_unit="pcs",
                 category_id=kat_a.id, tenant_id=cafe_a.id, is_active=True,
                 pack_size=12, pack_price=130000, image_url="/uploads/a.jpg")
    # A: kasrli (kg) mahsulot
    p2 = Product(name="BBB SHAKAR", price=14000, cost_price=11000, sale_unit="kg",
                 category_id=kat_a.id, tenant_id=cafe_a.id, is_active=True)
    # A: ombor qatori YO'Q — pos-stock uni QAYTARMASLIGI kerak (join inner)
    p3 = Product(name="CCC OMBORSIZ", price=1000, sale_unit="pcs",
                 category_id=kat_a.id, tenant_id=cafe_a.id, is_active=True)
    # B: begona tenant
    p4 = Product(name="AAA BEGONA", price=7000, cost_price=5000, sale_unit="kg",
                 category_id=kat_b.id, tenant_id=cafe_b.id, is_active=True)
    db.add_all([p1, p2, p3, p4]); db.flush()

    db.add_all([
        Inventory(product_id=p1.id, quantity=12,  unit="dona", min_threshold=5,
                  tenant_id=cafe_a.id),
        Inventory(product_id=p2.id, quantity=0.5, unit="kg",   min_threshold=2,
                  tenant_id=cafe_a.id),
        Inventory(product_id=p4.id, quantity=500, unit="kg",   min_threshold=10,
                  tenant_id=cafe_b.id),
    ])

    for phone, cafe, role in (
        (PHONE_MOLIYA, cafe_a, r_admin),
        (PHONE_KASSIR, cafe_a, r_kassir),
        (PHONE_BEGONA, cafe_b, r_admin),
    ):
        db.add(User(username=f"u{phone[-3:]}", email=f"{phone[-3:]}@x.uz",
                    full_name="U", phone=phone,
                    hashed_password=get_password_hash(ADMIN_PW), is_active=True,
                    is_superuser=False, tenant_id=cafe.id, role_id=role.id))
    db.commit()
    return {"db": db, "p1": p1.id, "p2": p2.id, "p3": p3.id, "p4": p4.id}


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


def _get(client, hdr, qs=""):
    r = client.get(f"/api/v1/inventory/pos-stock{qs}", headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


# ══════════════════════════════════════════════════════════════════════════════
# 1) JAVOB SHAKLI — joinedload dan KEYIN ham AYNAN o'sha
# ══════════════════════════════════════════════════════════════════════════════

def test_yuqori_daraja_kalitlari(client, seeded):
    """`items`, `can_cost`, `block_oversell` — POS klienti shularni o'qiydi."""
    data = _get(client, _login(client, PHONE_KASSIR))
    assert set(data.keys()) == {"items", "can_cost", "block_oversell"}
    assert data["can_cost"] is False
    assert isinstance(data["block_oversell"], bool)


def test_kassir_qator_kalitlari_ozgarmagan(client, seeded):
    """view_finance YO'Q → tannarx/qiymat kalitlari UMUMAN bo'lmasin."""
    data = _get(client, _login(client, PHONE_KASSIR))
    assert len(data["items"]) == 2
    for row in data["items"]:
        assert set(row.keys()) == ASOSIY_KALITLAR, f"kalitlar o'zgardi: {set(row.keys())}"
    assert "total_value" not in data


def test_moliya_qator_kalitlari_ozgarmagan(client, seeded):
    """view_finance BOR → tannarx + stock_value + total_value qo'shiladi."""
    data = _get(client, _login(client, PHONE_MOLIYA))
    assert data["can_cost"] is True
    for row in data["items"]:
        assert set(row.keys()) == ASOSIY_KALITLAR | MOLIYA_KALITLAR
    # 12×9000 + 0.5×11000 = 108000 + 5500
    assert data["total_value"] == pytest.approx(113500.0)


def test_qiymatlar_togri(client, seeded):
    """`joinedload` mahsulot maydonlarini BUZMAGANINI qulflaydi."""
    data = _get(client, _login(client, PHONE_MOLIYA))
    row = {r["name"]: r for r in data["items"]}

    coca = row["AAA COCA"]
    assert coca["product_id"] == seeded["p1"]
    assert coca["price"] == 12000
    assert coca["sale_unit"] == "pcs"
    assert coca["quantity"] == 12
    assert coca["unit"] == "dona"
    assert coca["min_threshold"] == 5
    assert coca["image_url"] == "/uploads/a.jpg"
    assert coca["pack_size"] == 12
    assert coca["pack_price"] == 130000
    assert coca["cost_price"] == 9000
    assert coca["stock_value"] == pytest.approx(108000.0)

    shakar = row["BBB SHAKAR"]
    assert shakar["quantity"] == 0.5        # kasrli qoldiq buzilmadi
    assert shakar["unit"] == "kg"
    assert shakar["pack_size"] is None
    assert shakar["pack_price"] is None


def test_ombor_qatorisiz_mahsulot_qaytmaydi(client, seeded):
    """`join(Product)` INNER — ombor qatorisiz mahsulot ro'yxatda yo'q.

    (Admin ro'yxati bunday mahsulotga "—" ko'rsatadi — bu KUTILGAN xatti-harakat.)
    """
    data = _get(client, _login(client, PHONE_MOLIYA))
    assert "CCC OMBORSIZ" not in {r["name"] for r in data["items"]}


# ══════════════════════════════════════════════════════════════════════════════
# 2) IZOLYATSIYA va PARAMETRLAR — joinedload ularni buzmasin
# ══════════════════════════════════════════════════════════════════════════════

def test_tenant_izolyatsiyasi(client, seeded):
    """⚠️ Eng muhim: begona do'kon qoldig'i sizib chiqmasin."""
    a = _get(client, _login(client, PHONE_MOLIYA))
    b = _get(client, _login(client, PHONE_BEGONA))
    assert {r["name"] for r in a["items"]} == {"AAA COCA", "BBB SHAKAR"}
    assert {r["name"] for r in b["items"]} == {"AAA BEGONA"}


def test_search_filtri(client, seeded):
    """`search` mahsulot NOMI bo'yicha — joinedload qo'shilgach ham ishlaydi."""
    data = _get(client, _login(client, PHONE_MOLIYA), "?search=shakar")
    assert [r["name"] for r in data["items"]] == ["BBB SHAKAR"]


def test_limit_va_tartib(client, seeded):
    """Tartib — mahsulot NOMI bo'yicha; `limit` kesadi."""
    data = _get(client, _login(client, PHONE_MOLIYA), "?limit=1")
    assert [r["name"] for r in data["items"]] == ["AAA COCA"]   # alifbo bo'yicha birinchi


def test_n_plus_1_qaytmasin(client, seeded):
    """N+1 QAYTMASIN: mahsulot ALOHIDA SELECT bilan olinmasligi kerak.

    Imzo: asosiy so'rov `FROM inventory JOIN products ...` deb yoziladi, ya'ni
    unda "FROM products" matni YO'Q. Har qator uchun ketadigan lazy-load esa
    aynan `SELECT ... FROM products WHERE products.id = ?` — "FROM products"
    bilan boshlanadi. Demak bunday so'rovlar soni 0 bo'lishi shart.

    `joinedload` olib tashlansa test YIQILADI (o'lchandi: 3 mahsulotда
    joinedload bilan 1 so'rov, usiz 4 so'rov).
    """
    from sqlalchemy import event

    eng = seeded["db"].get_bind()
    lazy_sorovlar = []

    def _yozib_ol(conn, cursor, statement, params, context, executemany):
        if "FROM products" in statement.replace("\n", " "):
            lazy_sorovlar.append(statement.replace("\n", " "))

    # Login listener'dan TASHQARIDA — faqat pos-stock so'rovi o'lchansin.
    hdr = _login(client, PHONE_MOLIYA)

    event.listen(eng, "before_cursor_execute", _yozib_ol)
    try:
        data = _get(client, hdr)
    finally:
        event.remove(eng, "before_cursor_execute", _yozib_ol)

    assert len(data["items"]) == 2, "sinov ma'lumoti kutilganday emas"
    assert lazy_sorovlar == [], (
        f"products jadvaliga {len(lazy_sorovlar)} ta ALOHIDA so'rov ketdi — "
        f"joinedload ishlamayapti (N+1):\n" + "\n".join(s[:160] for s in lazy_sorovlar)
    )
