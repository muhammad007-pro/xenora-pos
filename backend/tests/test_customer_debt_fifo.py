"""MIJOZ QARZINI UMUMIY TO'LASH (FIFO) — `POST /customers/{id}/pay-debt`.

MUAMMO (jonli, XOZMAG'da 31 ta nasiya): mijoz 500 000 keltirsa va 3 ta qarzi
bo'lsa, kassir `POST /debts/{id}/pay` ni UCH MARTA, summalarni o'zi bo'lib
chaqirishga majbur edi. Firmalarda FIFO bor, mijozlarda yo'q edi.

BU TESTLAR QULFLAYDI:
  • 500 000 → eng eski qarzdan boshlab taqsimlanadi (FIFO)
  • ortiqcha to'lov AVANS bo'ladi (manfiy qoldiq, vozvrat naqshi)
  • qisman to'lov → qarz `partial`
  • KASSIR qabul qila oladi (`process_payments`)
  • ⚠️ Z-hisobotda NAQD qarz to'lovi ko'rinadi va `expected_cash` ga kiradi —
    AVANS qismi ham (aks holda yashikdagi pul "ortiqcha" bo'lib ko'rinardi)
  • begona tenant mijoziga to'lab bo'lmaydi
  • oldindan ko'rsatish (`debt-preview`) HAQIQIY taqsimot bilan bir xil
  • GOLDEN: eski `POST /debts/{id}/pay` (bitta qarz) ishlashda davom etadi

Ishga tushirish:  cd backend && py -m pytest tests/test_customer_debt_fifo.py -v
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
    AuditLog, Cafe, Customer, CustomerDebt, DebtPayment, Permission, Role,
    Shift, User,
)

ADMIN_PW,  ADMIN_PHONE  = "AdminQarz8", "+998900000081"
KASSIR_PW, KASSIR_PHONE = "KassirQrz8", "+998900000082"

NOW = utc_now()

# Uch qarz: 240 000 + 260 000 + 100 000 = 600 000 (eng eskidan)
D1, D2, D3 = 240_000.0, 260_000.0, 100_000.0
START_CASH = 50_000.0


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE'LAR
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def eng():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)
    e.dispose()


@pytest.fixture()
def db_session(eng, monkeypatch):
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False)
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
def shop(db_session):
    """Do'kon + ochiq smena + mijoz (3 ta ochiq qarz, jami 600 000).

    Admin: process_payments + view_finance + view_reports + manage_shifts.
    Kassir: FAQAT process_payments + view_reports — ya'ni `/debts/{id}/pay`
    (view_finance) unga YARAMAYDI, yangi yo'l esa ishlashi KERAK.
    """
    db = db_session

    p_pay    = _perm(db, "process_payments", "To'lovlar")
    p_fin    = _perm(db, "view_finance",     "Moliya")
    p_report = _perm(db, "view_reports",     "Hisobotlar")
    p_shift  = _perm(db, "manage_shifts",    "Smenalar")

    r_admin  = _role(db, "admin",   [p_pay, p_fin, p_report, p_shift])
    r_kassir = _role(db, "cashier", [p_pay, p_report])

    cafe = Cafe(name="XOZMAG test", code="xzt", access_code="100.200.81",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe)
    db.flush()

    admin = User(username="bosh81", email="a81@x.uz", full_name="Rahbar Azizbek",
                 phone=ADMIN_PHONE, hashed_password=get_password_hash(ADMIN_PW),
                 is_active=True, is_superuser=False,
                 tenant_id=cafe.id, role_id=r_admin.id)
    kassir = User(username="kassa81", email="k81@x.uz", full_name="Kassir Diyorbek",
                  phone=KASSIR_PHONE, hashed_password=get_password_hash(KASSIR_PW),
                  is_active=True, is_superuser=False,
                  tenant_id=cafe.id, role_id=r_kassir.id)
    db.add_all([admin, kassir])
    db.flush()

    shift = Shift(tenant_id=cafe.id, user_id=admin.id,
                  start_time=NOW - timedelta(hours=4), starting_cash=START_CASH)
    db.add(shift)
    db.flush()

    cust = Customer(tenant_id=cafe.id, name="Shuhrat aka",
                    phone="+998901234581", total_debt=D1 + D2 + D3)
    db.add(cust)
    db.flush()

    # ⚠️ `created_at` ATAYIN aniq berilgan: FIFO tartibi aynan shundan
    # aniqlanadi (`created_at`, keyin `id`). Teng vaqtda tartib tasodifiy
    # bo'lib, test tebranardi.
    debts = []
    for i, summa in enumerate((D1, D2, D3)):
        d = CustomerDebt(tenant_id=cafe.id, customer_id=cust.id, order_id=None,
                         amount=summa, paid_amount=0.0, remaining=summa,
                         status="open", notes=f"qarz-{i+1}",
                         created_at=NOW - timedelta(days=30 - i * 10))
        db.add(d)
        debts.append(d)
    db.flush()
    db.commit()

    return {"db": db, "cafe": cafe.id, "admin": admin.id, "kassir": kassir.id,
            "shift": shift.id, "customer": cust.id,
            "d1": debts[0].id, "d2": debts[1].id, "d3": debts[2].id}


# ══════════════════════════════════════════════════════════════════════════════
# YORDAMCHILAR
# ══════════════════════════════════════════════════════════════════════════════

def _login(client, phone, pw):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": pw})
    assert r.status_code == 200, f"login yiqildi: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _pay(client, hdr, cid, amount, *, method="cash", notes="Mijoz pul keltirdi"):
    return client.post(f"/api/v1/customers/{cid}/pay-debt",
                       json={"amount": amount, "payment_method": method,
                             "notes": notes}, headers=hdr)


def _preview(client, hdr, cid, amount):
    r = client.get(f"/api/v1/customers/{cid}/debt-preview?amount={amount}", headers=hdr)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    return r.json()


def _close_shift(client, hdr, shift_id, counted_cash=0.0):
    r = client.post(f"/api/v1/shifts/{shift_id}/close?counted_cash={counted_cash}",
                    headers=hdr)
    assert r.status_code == 200, f"smena yopilmadi: {r.status_code} {r.text}"
    return r.json()


def _debt(db, did):
    db.expire_all()
    return db.query(CustomerDebt).filter(CustomerDebt.id == did).first()


# ══════════════════════════════════════════════════════════════════════════════
# 1) FIFO TAQSIMLASH
# ══════════════════════════════════════════════════════════════════════════════

def test_500000_uchta_qarzga_fifo_taqsimlanadi(client, shop):
    """500 000: eng eski 240 000 TO'LIQ, keyingisidan 260 000 — uchinchisiga yetmaydi."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _pay(client, hdr, shop["customer"], 500_000.0)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    b = r.json()

    assert b["applied"]       == 500_000
    assert b["advance"]       == 0
    assert b["debts_touched"] == 2
    assert b["debts_closed"]  == 2

    # Taqsimot AYNAN FIFO tartibida
    assert [(a["debt_id"], a["amount"]) for a in b["allocations"]] == [
        (shop["d1"], D1), (shop["d2"], D2),
    ], b["allocations"]

    db = shop["db"]
    assert (_debt(db, shop["d1"]).status, _debt(db, shop["d1"]).remaining) == ("paid", 0.0)
    assert (_debt(db, shop["d2"]).status, _debt(db, shop["d2"]).remaining) == ("paid", 0.0)
    # Uchinchi TEGILMAGAN
    d3 = _debt(db, shop["d3"])
    assert (d3.status, d3.remaining, d3.paid_amount) == ("open", D3, 0.0)
    # Qoldiq qayta hisoblandi
    assert b["total_debt_after"] == D3
    assert db.query(Customer).filter(Customer.id == shop["customer"]).first().total_debt == D3


def test_har_yopilgan_qarz_uchun_debtpayment_yoziladi(client, shop):
    """⚠️ KASSA IZI: qabul qilingan summa = Σ(DebtPayment.amount)."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hdr, shop["customer"], 500_000.0, method="card").status_code == 200

    db = shop["db"]
    db.expire_all()
    pays = db.query(DebtPayment).all()
    assert len(pays) == 2
    assert sorted(p.debt_id for p in pays) == sorted([shop["d1"], shop["d2"]])
    assert sum(p.amount for p in pays) == 500_000, "kassa izi summaga teng emas"
    assert {p.payment_method for p in pays} == {"card"}, "to'lov usuli saqlanmadi"
    assert all(p.user_id == shop["admin"] for p in pays), "kim qabul qilgani yozilmadi"


def test_qisman_tolov_qarz_partial_boladi(client, shop):
    """100 000: eng eski qarz (240 000) qisman yopiladi."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    b = _pay(client, hdr, shop["customer"], 100_000.0).json()
    assert b["debts_touched"] == 1 and b["debts_closed"] == 0

    d1 = _debt(shop["db"], shop["d1"])
    assert d1.status      == "partial"
    assert d1.paid_amount == 100_000.0
    assert d1.remaining   == D1 - 100_000.0
    assert b["total_debt_after"] == D1 + D2 + D3 - 100_000.0


def test_aniq_summa_bitta_qarzni_yopadi(client, shop):
    """Chegara holati: AYNAN qarz summasi berilsa qarz `paid` bo'ladi, avans YO'Q."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    b = _pay(client, hdr, shop["customer"], D1).json()
    assert b["advance"] == 0 and b["debts_closed"] == 1
    assert _debt(shop["db"], shop["d1"]).status == "paid"
    assert _debt(shop["db"], shop["d2"]).status == "open"


def test_hamma_qarzni_yopish(client, shop):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    b = _pay(client, hdr, shop["customer"], D1 + D2 + D3).json()
    assert b["debts_closed"] == 3 and b["advance"] == 0
    assert b["total_debt_after"] == 0
    db = shop["db"]
    for k in ("d1", "d2", "d3"):
        assert _debt(db, shop[k]).status == "paid"


# ══════════════════════════════════════════════════════════════════════════════
# 2) ORTIQCHA TO'LOV → AVANS
# ══════════════════════════════════════════════════════════════════════════════

def test_ortiqcha_tolov_avans_boladi(client, shop):
    """700 000: 600 000 qarzga, 100 000 AVANS (manfiy qoldiq — vozvrat naqshi)."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    b = _pay(client, hdr, shop["customer"], 700_000.0).json()

    assert b["applied"]      == 600_000
    assert b["advance"]      == 100_000
    assert b["debts_closed"] == 3
    assert b["advance_debt_id"]

    db = shop["db"]
    adv = _debt(db, b["advance_debt_id"])
    assert adv.amount    == -100_000.0
    assert adv.remaining == -100_000.0, "avans MANFIY qoldiq bo'lishi kerak"
    assert adv.status    == "open"
    # `total_debt` minusga tushadi = do'kon mijozga qarzdor
    assert b["total_debt_after"] == -100_000.0
    assert db.query(Customer).filter(Customer.id == shop["customer"]).first().total_debt == -100_000.0


def test_avans_qismi_HAM_kassa_izida(client, shop):
    """⚠️ Avans uchun ham `DebtPayment` yoziladi — pul YASHIKKA TUSHGAN.

    Busiz `expected_cash` kam chiqardi va yashikdagi haqiqiy naqd "ortiqcha"
    bo'lib ko'rinardi (2026-08-19 xatosining aynan o'zi, utils/cashflow.py).
    """
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hdr, shop["customer"], 700_000.0).status_code == 200

    db = shop["db"]
    db.expire_all()
    pays = db.query(DebtPayment).all()
    assert sum(p.amount for p in pays) == 700_000, (
        f"kassa izi {sum(p.amount for p in pays)} — qabul qilingan 700 000 ga teng emas")
    assert len(pays) == 4, "3 qarz + 1 avans yozuvi kutilgan"


def test_ochiq_qarz_yoq_bolsa_400(client, shop):
    """Jimgina avans yaratmaymiz — kassir adashib boshqa mijozni tanlagan
    bo'lishi mumkin, pul esa yashikka tushib ketardi."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hdr, shop["customer"], D1 + D2 + D3).status_code == 200

    r = _pay(client, hdr, shop["customer"], 50_000.0)
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert "ochiq qarz yo'q" in r.json()["detail"]


# ══════════════════════════════════════════════════════════════════════════════
# 3) OLDINDAN KO'RSATISH (UI uchun) — HAQIQIY taqsimot bilan bir xil
# ══════════════════════════════════════════════════════════════════════════════

def test_preview_haqiqiy_taqsimot_bilan_AYNI(client, shop):
    """UI "500 000 → #1 ga 240 000, #2 ga 260 000" deb ko'rsatadi — bazada
    boshqa narsa bo'lmasligi KERAK (hisob frontendda takrorlanmaydi)."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    pv = _preview(client, hdr, shop["customer"], 500_000.0)
    assert pv["applied"] == 500_000 and pv["advance"] == 0
    assert [(a["debt_id"], a["amount"]) for a in pv["allocations"]] == [
        (shop["d1"], D1), (shop["d2"], D2)]
    assert [a["closes"] for a in pv["allocations"]] == [True, True]

    # Preview HECH NARSA yozmaydi
    db = shop["db"]
    assert _debt(db, shop["d1"]).remaining == D1
    assert db.query(DebtPayment).count() == 0

    real = _pay(client, hdr, shop["customer"], 500_000.0).json()
    assert [(a["debt_id"], a["amount"]) for a in real["allocations"]] == \
           [(a["debt_id"], a["amount"]) for a in pv["allocations"]]


def test_preview_avansni_ham_korsatadi(client, shop):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    pv = _preview(client, hdr, shop["customer"], 700_000.0)
    assert pv["applied"] == 600_000 and pv["advance"] == 100_000
    assert pv["debts_count"] == 3
    assert pv["total_debt"] == D1 + D2 + D3


# ══════════════════════════════════════════════════════════════════════════════
# 4) RUXSAT va TENANT
# ══════════════════════════════════════════════════════════════════════════════

def test_kassir_tolov_qabul_qila_oladi(client, shop):
    """Pul olish kassirning ishi. ⚠️ Eski `/debts/{id}/pay` `view_finance`
    talab qiladi va kassirga YARAMAYDI — yangi yo'l shu teshikni yopadi."""
    hdr = _login(client, KASSIR_PHONE, KASSIR_PW)
    r = _pay(client, hdr, shop["customer"], 500_000.0)
    assert r.status_code == 200, f"kassir to'lov qabul qila olmadi: {r.status_code} {r.text}"
    assert r.json()["debts_closed"] == 2

    db = shop["db"]
    db.expire_all()
    assert all(p.user_id == shop["kassir"] for p in db.query(DebtPayment).all())

    # Eski yo'l kassirga yopiq ekani ATAYIN qulflanadi (regressiya bo'lmasin)
    r2 = client.post(f"/api/v1/debts/{shop['d3']}/pay",
                     json={"amount": 1_000.0, "payment_method": "cash"}, headers=hdr)
    assert r2.status_code == 403, f"eski yo'l kassirga ochilib ketdi: {r2.status_code}"


def test_kassir_preview_kora_oladi(client, shop):
    hdr = _login(client, KASSIR_PHONE, KASSIR_PW)
    pv = _preview(client, hdr, shop["customer"], 300_000.0)
    assert pv["applied"] == 300_000


def test_begona_tenant_mijoziga_tolab_bolmaydi(client, shop, db_session):
    db = db_session
    other = Cafe(name="Begona", code="bgn81", access_code="100.200.82",
                 business_type="store", subscription_plan="pro", is_active=True)
    db.add(other)
    db.flush()
    r_admin = db.query(Role).filter(Role.name == "admin").first()
    db.add(User(username="bgn81", email="b81@x.uz", full_name="Begona Admin",
                phone="+998900000083", hashed_password=get_password_hash(ADMIN_PW),
                is_active=True, is_superuser=False,
                tenant_id=other.id, role_id=r_admin.id))
    db.commit()

    hdr = _login(client, "+998900000083", ADMIN_PW)
    r = _pay(client, hdr, shop["customer"], 100_000.0)
    assert r.status_code == 404, f"begona tenant qarzini to'ladi: {r.status_code} {r.text}"
    r2 = client.get(f"/api/v1/customers/{shop['customer']}/debt-preview?amount=100000",
                    headers=hdr)
    assert r2.status_code == 404

    # Qarz TEGILMAGAN
    assert _debt(shop["db"], shop["d1"]).remaining == D1
    assert shop["db"].query(DebtPayment).count() == 0


def test_nasiyaga_tolash_rad_etiladi_422(client, shop):
    """Nasiyani yana nasiyaga yozish — qarz kamayardi, pul kelmasdi."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = _pay(client, hdr, shop["customer"], 100_000.0, method="credit")
    assert r.status_code == 422, f"{r.status_code} {r.text}"


def test_manfiy_yoki_nol_summa_422(client, shop):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    for bad in (0, -100):
        assert _pay(client, hdr, shop["customer"], bad).status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# 5) Z-HISOBOT / CASHFLOW
# ══════════════════════════════════════════════════════════════════════════════

def test_zhisobotda_naqd_qarz_tolovi_korinadi(client, shop):
    """⚠️ PUL YO'LI: naqd qarz to'lovi `expected_cash` ga KIRADI.

    `routers/debt.py` `Payment` yozmaydi (faqat `DebtPayment`), shuning uchun
    `utils/cashflow.debt_payments_totals` shu yozuvlardan o'qiydi. Yozuv
    qoldirilsa yashikdagi pul "ortiqcha" bo'lib ko'rinardi.
    """
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hdr, shop["customer"], 500_000.0).status_code == 200

    z = _close_shift(client, hdr, shop["shift"], counted_cash=START_CASH + 500_000.0)
    assert z["debt_paid_cash"]  == 500_000
    assert z["debt_paid_total"] == 500_000
    assert z["debt_paid_count"] == 2, "ikki qarzga ikki yozuv"
    assert z["expected_cash"]   == START_CASH + 500_000
    assert z["shortage"]        == 0, "kassir asossiz kamomad/ortiqcha olmasligi kerak"
    # Qarz to'lovi SOTUV EMAS — `total_sales` ga qo'shilmaydi
    assert z["total_sales"] == 0


def test_zhisobotda_avans_ham_hisobga_kiradi(client, shop):
    """700 000 qabul qilindi (100 000 avans) — kassada 700 000 bo'lishi kerak."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hdr, shop["customer"], 700_000.0).status_code == 200

    z = _close_shift(client, hdr, shop["shift"], counted_cash=START_CASH + 700_000.0)
    assert z["debt_paid_cash"] == 700_000, (
        f"avans kassa hisobidan tushib qoldi: {z['debt_paid_cash']}")
    assert z["expected_cash"] == START_CASH + 700_000
    assert z["shortage"] == 0


def test_karta_bilan_tolov_expected_cash_ga_KIRMAYDI(client, shop):
    """Karta — pul keladi, lekin kassa YASHIGIGA emas (utils/cashflow.py)."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hdr, shop["customer"], 500_000.0, method="card").status_code == 200

    z = _close_shift(client, hdr, shop["shift"], counted_cash=START_CASH)
    assert z["debt_paid_cash"]  == 0
    assert z["debt_paid_card"]  == 500_000
    assert z["debt_paid_total"] == 500_000
    assert z["expected_cash"]   == START_CASH
    assert z["shortage"]        == 0


# ══════════════════════════════════════════════════════════════════════════════
# 6) GOLDEN — eski yo'l va audit
# ══════════════════════════════════════════════════════════════════════════════

def test_golden_eski_bitta_qarzga_tolash_ishlaydi(client, shop):
    """`POST /debts/{id}/pay` o'zgarmasligi kerak — refaktoring uni buzmadi."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = client.post(f"/api/v1/debts/{shop['d2']}/pay",
                    json={"amount": 60_000.0, "payment_method": "cash",
                          "notes": "eski yo'l"}, headers=hdr)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    b = r.json()
    assert b["paid_amount"] == 60_000.0
    assert b["remaining"]   == D2 - 60_000.0
    assert b["status"]      == "partial"
    # FIFO yo'li EMAS: aynan tanlangan qarzga tushadi (eng eski d1 TEGILMAGAN)
    assert _debt(shop["db"], shop["d1"]).remaining == D1
    # `total_debt` qayta hisoblandi (yagona manba)
    assert shop["db"].query(Customer).filter(
        Customer.id == shop["customer"]).first().total_debt == D1 + D2 + D3 - 60_000.0


def test_golden_eski_yol_oshiq_tolovni_rad_etadi(client, shop):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    r = client.post(f"/api/v1/debts/{shop['d3']}/pay",
                    json={"amount": D3 + 1_000.0, "payment_method": "cash"}, headers=hdr)
    assert r.status_code == 400, f"{r.status_code} {r.text}"


def test_ikki_yol_birgalikda_izchil(client, shop):
    """Eski yo'l bilan qisman to'lab, keyin FIFO bilan qolganini yopish."""
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert client.post(f"/api/v1/debts/{shop['d1']}/pay",
                       json={"amount": 40_000.0, "payment_method": "cash"},
                       headers=hdr).status_code == 200

    b = _pay(client, hdr, shop["customer"], 200_000.0).json()
    # Eng eski qarzning QOLGANI (200 000) birinchi yopiladi
    assert b["allocations"][0]["debt_id"] == shop["d1"]
    assert b["allocations"][0]["amount"]  == D1 - 40_000.0
    assert b["debts_closed"] == 1
    d1 = _debt(shop["db"], shop["d1"])
    assert (d1.status, d1.remaining, d1.paid_amount) == ("paid", 0.0, D1)


def test_audit_taqsimot_bilan_yoziladi(client, shop):
    hdr = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hdr, shop["customer"], 700_000.0,
                notes="Shuhrat aka to'ladi").status_code == 200

    db = shop["db"]
    db.expire_all()
    rows = (db.query(AuditLog)
            .filter(AuditLog.resource == "customer_debts")
            .order_by(AuditLog.id).all())
    assert rows, "audit yozuvi yo'q"
    d = rows[-1].detail or {}
    assert d.get("action")         == "pay_debt_fifo"
    assert d.get("amount")         == 700_000
    assert d.get("payment_method") == "cash"
    assert d.get("notes")          == "Shuhrat aka to'ladi"
    assert d.get("advance")        == 100_000
    assert sorted(d.get("debts_closed") or []) == sorted([shop["d1"], shop["d2"], shop["d3"]])
    assert len(d.get("allocations") or []) == 3
    assert rows[-1].user_id == shop["admin"]
