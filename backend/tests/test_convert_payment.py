"""TO'LOV USULINI KEYIN TUZATISH — `POST /orders/{id}/convert-payment` (2026-10-06).

MUAMMO (jonli, v1.12.14 — "Shuhrat aka holati"):
    kassir nasiyani naqd qilib yopadi yoki karta o'rniga naqd uradi. Chek
    chiqib ketgan, tovar ketgan — lekin kassa hisobi va qarz daftari yolg'on.
    Tuzatish yo'li FAQAT qo'lda SQL edi (prod bazasiga kirish).

BU TESTLAR QULFLAYDI:
  • naqd→nasiya  → qarz YARATILADI va `expected_cash` KAMAYADI
  • nasiya→naqd  → qarz YOPILADI  va `expected_cash` OSHADI
  • omborga TEGILMAYDI (tovar allaqachon ketgan)
  • kassir 403 / admin 200  (kassir o'z xatosini o'zi tuzatmaydi)
  • yopilgan smena 400, qaytarilgan chek 400, aralash to'lov (split) 400
  • audit logda eski/yangi usul + sabab

⚠️ `expected_cash` O'LCHOVI: `POST /shifts/{id}/close` javobidan olinadi —
   kassir ko'radigan AYNAN o'sha raqam (`routers/shift.py`). Har o'lchov uchun
   BAZELINE testi bor, ya'ni test "100000 bo'lsin" deb emas, "konvertatsiya
   AYNAN shu miqdorda o'zgartirdi" deb qulflaydi.

Ishga tushirish:  cd backend && py -m pytest tests/test_convert_payment.py -v
"""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from core.security import get_password_hash
from core.timeutils import utc_now
from database import Base, get_db
from main import app
from models import (
    AuditLog, Cafe, Customer, CustomerDebt, DebtPayment, Inventory, Order,
    OrderItem, Payment, Permission, Product, Return, ReturnItem, Role, Shift, User,
)

ADMIN_PW,  ADMIN_PHONE  = "AdminBosh5x", "+998900000061"
KASSIR_PW, KASSIR_PHONE = "Kassir7Yuz",  "+998900000062"

START_CASH = 100_000.0
SALE       = 50_000.0

# ⚠️ AWARE UTC (naive `datetime.now()` EMAS): `close_shift` oynani `utc_now()`
# bilan quradi. Mahalliy devor vaqti bilan seed qilinsa ma'lumot oynadan 5 soat
# chetda qolardi (shift-timezone tuzog'i).
NOW   = utc_now()
START = NOW - timedelta(hours=6)


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE'LAR
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def eng():
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,       # TestClient va test BIR bazani ko'rsin
    )
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)
    e.dispose()


@pytest.fixture()
def db_session(eng, monkeypatch):
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    # ⚠️ `core.audit.log_audit` ATAYIN ALOHIDA sessiyada yozadi va
    # `database.SessionLocal` ni CHAQIRUV PAYTIDA o'qiydi. Yo'naltirilmasa
    # audit qatorlari DEV BAZASIGA tushadi va testga ko'rinmaydi.
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
    """Ruxsatni OLADI yoki yaratadi — ilovaning `init_db()` urug'i bilan
    to'qnashmasin (UNIQUE constraint: permissions.code)."""
    p = db.query(Permission).filter(Permission.code == code).first()
    if not p:
        p = Permission(code=code, description=desc)
        db.add(p)
        db.flush()
    return p


def _role(db, name, perms):
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
    """Bitta do'kon: OCHIQ smena + bitta NAQD sotuv + mijoz.

    Admin: `manage_shifts` BOR. Kassir: ATAYIN YO'Q — aynan shu chiziq
    "o'z xatosini o'zi tuzatmaydi" qoidasini beradi.
    """
    db = db_session

    p_pay    = _perm(db, "process_payments", "To'lovlar")
    p_shift  = _perm(db, "manage_shifts",    "Smenalar")
    p_report = _perm(db, "view_reports",     "Hisobotlar")

    r_admin  = _role(db, "admin",   [p_pay, p_shift, p_report])
    r_kassir = _role(db, "cashier", [p_pay, p_report])

    cafe = Cafe(name="Do'kon K", code="dkk", access_code="100.200.61",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe)
    db.flush()

    admin = User(username="bosh61", email="a61@x.uz", full_name="Rahbar Azizbek",
                 phone=ADMIN_PHONE, hashed_password=get_password_hash(ADMIN_PW),
                 is_active=True, is_superuser=False,
                 tenant_id=cafe.id, role_id=r_admin.id)
    kassir = User(username="kassa61", email="k61@x.uz", full_name="Kassir Diyorbek",
                  phone=KASSIR_PHONE, hashed_password=get_password_hash(KASSIR_PW),
                  is_active=True, is_superuser=False,
                  tenant_id=cafe.id, role_id=r_kassir.id)
    db.add_all([admin, kassir])
    db.flush()

    prod = Product(tenant_id=cafe.id, name="SHAMPUN 500ml",
                   price=SALE, cost_price=30_000.0)
    db.add(prod)
    db.flush()
    inv = Inventory(tenant_id=cafe.id, product_id=prod.id, quantity=12.0, unit="dona")
    db.add(inv)

    shift = Shift(tenant_id=cafe.id, user_id=kassir.id, start_time=START,
                  starting_cash=START_CASH)
    db.add(shift)
    db.flush()

    customer = Customer(tenant_id=cafe.id, name="Shuhrat aka",
                        phone="+998901234561", total_debt=0.0)
    db.add(customer)
    db.flush()

    order = Order(tenant_id=cafe.id, order_number="K-6101", daily_number=1,
                  status="completed", total_amount=SALE, discount_amount=0.0,
                  final_amount=SALE, waiter_id=kassir.id, shift_id=shift.id,
                  created_at=NOW - timedelta(hours=1))
    db.add(order)
    db.flush()
    oi = OrderItem(tenant_id=cafe.id, order_id=order.id, product_id=prod.id,
                   quantity=1, unit_price=SALE, unit_cost=30_000.0, total_price=SALE)
    db.add(oi)
    pay = Payment(tenant_id=cafe.id, order_id=order.id, cashier_id=kassir.id,
                  amount=SALE, method="cash", status="paid",
                  created_at=NOW - timedelta(hours=1))
    db.add(pay)
    db.commit()

    return {"db": db, "cafe": cafe.id, "admin": admin.id, "kassir": kassir.id,
            "shift": shift.id, "order": order.id, "order_item": oi.id,
            "product": prod.id, "payment": pay.id, "customer": customer.id}


# ══════════════════════════════════════════════════════════════════════════════
# YORDAMCHILAR
# ══════════════════════════════════════════════════════════════════════════════

def _login(client, phone, pw):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": pw})
    assert r.status_code == 200, f"login yiqildi: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _convert(client, hdr, order_id, new_method, *, reason="Kassir xato urgan",
             customer_id=None):
    body = {"new_method": new_method, "reason": reason}
    if customer_id is not None:
        body["customer_id"] = customer_id
    return client.post(f"/api/v1/orders/{order_id}/convert-payment",
                       json=body, headers=hdr)


def _close(client, hdr, shift_id, counted_cash=0.0):
    r = client.post(f"/api/v1/shifts/{shift_id}/close?counted_cash={counted_cash}",
                    headers=hdr)
    assert r.status_code == 200, f"smena yopilmadi: {r.status_code} {r.text}"
    return r.json()


def _to_credit(db, seeded):
    """Chekni NASIYA sotuviga aylantiradi (POS nasiya oqimining natijasi):
    `Payment` pending/credit + `CustomerDebt` ochiq. POS aynan shu ikki qadamni
    qiladi (pos.js: order+payment, keyin alohida `POST /debts/`)."""
    pay = db.query(Payment).get(seeded["payment"])
    pay.method = "credit"
    pay.status = "pending"
    order = db.query(Order).get(seeded["order"])
    order.customer_id = seeded["customer"]
    debt = CustomerDebt(tenant_id=seeded["cafe"], customer_id=seeded["customer"],
                        order_id=seeded["order"], amount=SALE, paid_amount=0.0,
                        remaining=SALE, status="open")
    db.add(debt)
    cust = db.query(Customer).get(seeded["customer"])
    cust.total_debt = SALE
    db.commit()
    return debt.id


# ══════════════════════════════════════════════════════════════════════════════
# 1) NAQD → NASIYA:  qarz yaratiladi, expected_cash KAMAYADI
# ══════════════════════════════════════════════════════════════════════════════

def test_bazelin_naqd_sotuv_expected_cash(client, seeded):
    """BAZELINE: konvertatsiyaSIZ kassada boshlang'ich + naqd sotuv bo'lishi kerak."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    z = _close(client, hdr, seeded["shift"])
    assert z["cash_sales"]    == SALE
    assert z["credit_total"]  == 0
    assert z["expected_cash"] == START_CASH + SALE


def test_naqd_nasiyaga_qarz_yaratiladi(client, seeded):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "credit",
                 reason="Mijoz pulni ertaga keltiradi",
                 customer_id=seeded["customer"])
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body["old_method"] == "cash"
    assert body["new_method"] == "credit"
    assert body["debt_id"]

    db = seeded["db"]
    db.expire_all()
    debt = db.query(CustomerDebt).get(body["debt_id"])
    assert debt is not None
    assert debt.order_id    == seeded["order"]
    assert debt.customer_id == seeded["customer"]
    assert debt.amount      == SALE
    assert debt.remaining   == SALE
    assert debt.status      == "open"
    # `Customer.total_debt` qayta hisoblandi (routers/debt.py:_recalc_customer_debt)
    assert db.query(Customer).get(seeded["customer"]).total_debt == SALE
    # Vozvrat pulni MIJOZ bo'yicha topadi — chek mijozsiz qolmasligi kerak
    assert db.query(Order).get(seeded["order"]).customer_id == seeded["customer"]
    # Tender: nasiya = pul KELMAGAN -> pending
    pay = db.query(Payment).get(seeded["payment"])
    assert str(getattr(pay.method, "value", pay.method)) == "credit"
    assert str(getattr(pay.status, "value", pay.status)) == "pending"


def test_naqd_nasiyaga_expected_cash_kamayadi(client, seeded):
    """ASOSIY PUL QULFI: kassada o'sha pul YO'Q — qarzga berilgan."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _convert(client, hdr, seeded["order"], "credit",
                    customer_id=seeded["customer"]).status_code == 200

    z = _close(client, hdr, seeded["shift"])
    assert z["cash_sales"]    == 0,    "nasiya naqd savdoga kirmasligi kerak"
    assert z["credit_total"]  == SALE, "nasiya alohida qatorda ko'rinishi kerak"
    assert z["expected_cash"] == START_CASH, (
        f"expected_cash KAMAYMADI: {z['expected_cash']} "
        f"(kutilgan {START_CASH}, bazeline {START_CASH + SALE})")


def test_nasiyaga_otkazish_omborga_tegmaydi(client, seeded):
    """Tovar allaqachon ketgan — tender tuzatilsa miqdor o'zgarmaydi."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _convert(client, hdr, seeded["order"], "credit",
                    customer_id=seeded["customer"]).status_code == 200
    db = seeded["db"]
    db.expire_all()
    inv = db.query(Inventory).filter(Inventory.product_id == seeded["product"]).first()
    assert inv.quantity == 12.0, "konvertatsiya omborga TEGMASLIGI kerak"


def test_nasiyaga_mijozsiz_400(client, seeded):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "credit")   # customer_id YO'Q
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert "MIJOZ" in r.json()["detail"].upper()


def test_nasiyaga_qarz_limiti_tekshiriladi(client, seeded):
    """Konvertatsiya `create_debt` ning limit tekshiruvini CHETLAB O'TMASLIGI kerak."""
    db = seeded["db"]
    cust = db.query(Customer).get(seeded["customer"])
    cust.credit_limit = 10_000.0          # sotuv 50 000 — limitdan katta
    db.commit()

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "credit", customer_id=seeded["customer"])
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert "limit" in r.json()["detail"].lower()
    db.expire_all()
    assert db.query(CustomerDebt).count() == 0, "limit oshsa qarz yaratilmasligi kerak"


# ══════════════════════════════════════════════════════════════════════════════
# 2) NASIYA → NAQD:  qarz yopiladi, expected_cash OSHADI
# ══════════════════════════════════════════════════════════════════════════════

def test_bazelin_nasiya_sotuv_expected_cash(client, seeded):
    """BAZELINE: nasiya sotuvida kassada FAQAT boshlang'ich pul bo'ladi."""
    _to_credit(seeded["db"], seeded)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    z = _close(client, hdr, seeded["shift"])
    assert z["cash_sales"]    == 0
    assert z["credit_total"]  == SALE
    assert z["expected_cash"] == START_CASH


def test_nasiya_naqdga_qarz_yopiladi(client, seeded):
    did = _to_credit(seeded["db"], seeded)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)

    r = _convert(client, hdr, seeded["order"], "cash", reason="Mijoz darhol to'lab ketdi")
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body["old_method"]  == "credit"
    assert body["new_method"]  == "cash"
    assert body["debt_closed"] == did

    db = seeded["db"]
    db.expire_all()
    assert db.query(CustomerDebt).get(did) is None, "qarz qatori yopilmadi"
    assert db.query(Customer).get(seeded["customer"]).total_debt == 0
    pay = db.query(Payment).get(seeded["payment"])
    assert str(getattr(pay.method, "value", pay.method)) == "cash"
    assert str(getattr(pay.status, "value", pay.status)) == "paid", (
        "naqdga o'tgach pul KELDI — status `paid` bo'lishi kerak, aks holda "
        "Z-hisobot bu pulni ko'rmaydi")


def test_nasiya_naqdga_expected_cash_oshadi(client, seeded):
    """ASOSIY PUL QULFI: pul haqiqatda kassada — hisob ham shuni ko'rsin."""
    _to_credit(seeded["db"], seeded)
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _convert(client, hdr, seeded["order"], "cash").status_code == 200

    z = _close(client, hdr, seeded["shift"])
    assert z["cash_sales"]    == SALE
    assert z["credit_total"]  == 0
    assert z["expected_cash"] == START_CASH + SALE, (
        f"expected_cash OSHMADI: {z['expected_cash']} "
        f"(kutilgan {START_CASH + SALE}, bazeline {START_CASH})")


def test_nasiya_tolangan_bolsa_400(client, seeded):
    """Yig'ilgan pul JIMGINA yo'qolmasin — qarzga to'lov tushgan bo'lsa rad etiladi."""
    db = seeded["db"]
    did = _to_credit(db, seeded)
    debt = db.query(CustomerDebt).get(did)
    debt.paid_amount = 20_000.0
    debt.remaining   = SALE - 20_000.0
    debt.status      = "partial"
    db.add(DebtPayment(debt_id=did, amount=20_000.0, payment_method="cash",
                       user_id=seeded["kassir"]))
    db.commit()

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "cash")
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert "to'lov" in r.json()["detail"].lower()
    db.expire_all()
    assert db.query(CustomerDebt).get(did) is not None, "400 da qarz o'chmasligi kerak"


# ══════════════════════════════════════════════════════════════════════════════
# 3) RUXSAT:  kassir 403, admin 200
# ══════════════════════════════════════════════════════════════════════════════

def test_kassir_403(client, seeded):
    """Kassir O'Z xatosini o'zi tuzatmaydi — aks holda nazorat yo'qoladi."""
    hdr = _login(client, KASSIR_PHONE, KASSIR_PW)
    r = _convert(client, hdr, seeded["order"], "credit", customer_id=seeded["customer"])
    assert r.status_code == 403, (
        f"NAZORAT TESHIGI — kassir to'lov usulini o'zgartirdi: {r.status_code} {r.text}")

    db = seeded["db"]
    db.expire_all()
    pay = db.query(Payment).get(seeded["payment"])
    assert str(getattr(pay.method, "value", pay.method)) == "cash", "403 da tender tegilmasin"
    assert db.query(CustomerDebt).count() == 0, "403 da qarz yaratilmasin"


def test_admin_200(client, seeded):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "card", reason="Terminal bilan to'lagan")
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    db = seeded["db"]
    db.expire_all()
    pay = db.query(Payment).get(seeded["payment"])
    assert str(getattr(pay.method, "value", pay.method)) == "card"
    assert str(getattr(pay.status, "value", pay.status)) == "paid"


def test_begona_tenant_404(client, seeded, db_session):
    """Tenant izolyatsiyasi: boshqa do'kon admini bu chekni KO'RMASLIGI kerak."""
    db = db_session
    other = Cafe(name="Begona", code="bgn", access_code="100.200.62",
                 business_type="store", subscription_plan="pro", is_active=True)
    db.add(other)
    db.flush()
    r_admin = db.query(Role).filter(Role.name == "admin").first()
    u = User(username="bgn", email="b@x.uz", full_name="Begona Admin",
             phone="+998900000063", hashed_password=get_password_hash(ADMIN_PW),
             is_active=True, is_superuser=False, tenant_id=other.id, role_id=r_admin.id)
    db.add(u)
    db.commit()

    hdr = _login(client, "+998900000063", ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "credit", customer_id=seeded["customer"])
    assert r.status_code == 404, f"{r.status_code} {r.text}"


# ══════════════════════════════════════════════════════════════════════════════
# 4) CHEKLOVLAR
# ══════════════════════════════════════════════════════════════════════════════

def test_yopilgan_smena_400(client, seeded):
    """Yopilgan smenaning Z-hisoboti bosilgan — ichidagi tenderga tegilmaydi."""
    db = seeded["db"]
    db.query(Shift).get(seeded["shift"]).end_time = NOW
    db.commit()

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "credit", customer_id=seeded["customer"])
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert "smena" in r.json()["detail"].lower()
    db.expire_all()
    pay = db.query(Payment).get(seeded["payment"])
    assert str(getattr(pay.method, "value", pay.method)) == "cash"


def test_smenasiz_chek_400(client, seeded):
    """`shift_id` NULL (eski yozuv) — qaysi kassa hisobiga tegishi aniqlanmaydi."""
    db = seeded["db"]
    db.query(Order).get(seeded["order"]).shift_id = None
    db.commit()
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "card")
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert "smena" in r.json()["detail"].lower()


def test_yakunlanmagan_buyurtma_400(client, seeded):
    db = seeded["db"]
    db.query(Order).get(seeded["order"]).status = "pending"
    db.commit()
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "card")
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert "yakunlangan" in r.json()["detail"].lower()


def test_qaytarilgan_buyurtma_400(client, seeded):
    """Vozvrat hujjati bo'lsa — pul va ombor O'SHA hujjat orqali yuriydi."""
    db = seeded["db"]
    ret = Return(tenant_id=seeded["cafe"], return_number="RET261006001",
                 order_id=seeded["order"], reason="dislike", total_amount=SALE,
                 refund_method="cash", status="pending", user_id=seeded["kassir"])
    db.add(ret)
    db.flush()
    db.add(ReturnItem(return_id=ret.id, product_id=seeded["product"], quantity=1,
                      unit_price=SALE, total=SALE))
    db.commit()

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "card")
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert "RET261006001" in r.json()["detail"], "xabarda hujjat raqami ko'rinsin"


def test_pul_qaytarilgan_tolov_400(client, seeded):
    """`Payment.status == refunded` — pul chiqib ketgan, tender muzlagan."""
    db = seeded["db"]
    db.query(Payment).get(seeded["payment"]).status = "refunded"
    db.commit()
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "card")
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert "qaytarilgan" in r.json()["detail"].lower()


def test_split_tolov_400_aniq_xabar(client, seeded):
    """Aralash to'lov: 2 ta tender — hozircha rad etiladi, LEKIN aniq xabar bilan."""
    db = seeded["db"]
    db.query(Payment).get(seeded["payment"]).amount = 30_000.0
    db.add(Payment(tenant_id=seeded["cafe"], order_id=seeded["order"],
                   cashier_id=seeded["kassir"], amount=20_000.0,
                   method="card", status="paid", created_at=NOW - timedelta(hours=1)))
    db.commit()

    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "credit", customer_id=seeded["customer"])
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    d = r.json()["detail"]
    assert "split" in d.lower() or "aralash" in d.lower()
    assert "cash" in d and "card" in d, f"xabarda tenderlar ko'rinsin: {d}"
    db.expire_all()
    assert db.query(CustomerDebt).count() == 0


def test_bir_xil_usul_400(client, seeded):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _convert(client, hdr, seeded["order"], "cash")
    assert r.status_code == 400, f"{r.status_code} {r.text}"


def test_izoh_majburiy_422(client, seeded):
    """Sabab yozilmasa keyin hech kim farqni tushuntirib bera olmaydi."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    for bad in ("", "  ", "ok"):
        r = client.post(f"/api/v1/orders/{seeded['order']}/convert-payment",
                        json={"new_method": "card", "reason": bad}, headers=hdr)
        assert r.status_code == 422, f"izoh {bad!r} o'tib ketdi: {r.status_code} {r.text}"
    r = client.post(f"/api/v1/orders/{seeded['order']}/convert-payment",
                    json={"new_method": "card"}, headers=hdr)
    assert r.status_code == 422, "izohsiz so'rov o'tib ketdi"


def test_notogri_usul_422(client, seeded):
    """`click`/`payme` shlyuzi YO'Q (stub) — "to'langan" deb belgilash yolg'on
    bo'lardi. `room_charge` esa mehmonxona folio hisobi bilan bog'liq."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    for bad in ("click", "payme", "room_charge", "transfer", "qr"):
        r = _convert(client, hdr, seeded["order"], bad)
        assert r.status_code == 422, f"{bad!r} o'tib ketdi: {r.status_code} {r.text}"


# ══════════════════════════════════════════════════════════════════════════════
# 5) AUDIT  —  har o'zgarish izi qoladi
# ══════════════════════════════════════════════════════════════════════════════

def _audit_rows(db):
    return (db.query(AuditLog)
            .filter(AuditLog.resource == "orders", AuditLog.action == "UPDATE")
            .order_by(AuditLog.id).all())


def test_audit_eski_yangi_usul_yoziladi(client, seeded):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _convert(client, hdr, seeded["order"], "credit",
                    reason="Shuhrat aka keyin to'laydi",
                    customer_id=seeded["customer"]).status_code == 200

    db = seeded["db"]
    db.expire_all()
    rows = _audit_rows(db)
    assert rows, "audit yozuvi yo'q"
    d = rows[-1].detail or {}
    assert d.get("action")     == "convert_payment"
    assert d.get("old_method") == "cash"
    assert d.get("new_method") == "credit"
    assert d.get("amount")     == SALE
    assert d.get("reason")     == "Shuhrat aka keyin to'laydi"
    assert d.get("customer_id") == seeded["customer"]
    assert d.get("debt_created")
    assert rows[-1].user_id == seeded["admin"]


def test_bir_necha_marta_ozgartirish_har_biri_auditda(client, seeded):
    """Takroriy tuzatish MUMKIN, lekin har qadam izsiz qolmaydi."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _convert(client, hdr, seeded["order"], "card",   reason="Karta edi").status_code == 200
    assert _convert(client, hdr, seeded["order"], "credit", reason="Yo'q, nasiya",
                    customer_id=seeded["customer"]).status_code == 200
    assert _convert(client, hdr, seeded["order"], "cash",   reason="Pulni keltirdi").status_code == 200

    db = seeded["db"]
    db.expire_all()
    rows = [r for r in _audit_rows(db)
            if (r.detail or {}).get("action") == "convert_payment"]
    assert len(rows) == 3, f"3 ta qadam kutilgan, {len(rows)} ta yozilgan"
    chain = [((r.detail or {}).get("old_method"), (r.detail or {}).get("new_method"))
             for r in rows]
    assert chain == [("cash", "card"), ("card", "credit"), ("credit", "cash")], chain

    # Oxirgi holat izchil: tender naqd, qarz qolmagan
    pay = db.query(Payment).get(seeded["payment"])
    assert str(getattr(pay.method, "value", pay.method)) == "cash"
    assert str(getattr(pay.status, "value", pay.status)) == "paid"
    assert db.query(CustomerDebt).count() == 0
    assert db.query(Customer).get(seeded["customer"]).total_debt == 0
