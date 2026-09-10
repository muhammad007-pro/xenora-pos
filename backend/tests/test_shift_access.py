"""SMENA RUXSATLARI — kim ocha oladi, kim yopa oladi (2026-09-10).

MUAMMO (audit, 1001 BARAKA smena oqimini o'rganishda topildi):

1. `POST /shifts/` da `user_id` KLIENT TANASIDAN kelardi va umuman
   tekshirilmasdi. Istalgan xodim boshqa kassir nomiga smena ocha olardi.
   Bu shunchaki noto'g'ri yozuv emas: sotuv aynan shu bog'lanish bo'yicha
   taqsimlanadi (`order_service`: `Shift.user_id == waiter_id`), ya'ni pul
   boshqa odamning Z-hisobotiga tushardi, kamomad ham o'shanga yozilardi.

2. `POST /shifts/{id}/close` tenant'dan boshqa hech narsa tekshirmasdi —
   bir kassir ikkinchisining smenasini yopib, uning kun yakunini yakunlab
   qo'yishi mumkin edi.

QOIDA:
  • Smena HAR DOIM so'rov yuborgan xodimga ochiladi.
  • Kassir FAQAT o'z smenasini yopadi.
  • `manage_shifts` (admin va menejer) — istalganini yopadi. Kassir smenani
    yopmasdan ketib qolsa, kun yakunini kimdir yopishi kerak.

⚠️ JONLI MIJOZ: prod audit'iga ko'ra 11 smenadan 10 tasi xodim O'ZI ochgan
(FAZZA 26 va 1001 BARAKA 27 — ikkalasi ham o'zi). Ya'ni majburlash mavjud
oqimni buzmaydi. Shu sabab bu testda "kassir o'zi ochadi → 200" yo'li ham
qulflanadi.

Ishga tushirish:
    cd backend && py -m pytest tests/test_shift_access.py -v
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
from models import Cafe, Shift, User, Role, Permission
from core.security import get_password_hash

PW = "SmenaTest9x"
PHONE_KASSIR_A = "+998900000091"   # kassir A — o'z smenasi
PHONE_KASSIR_B = "+998900000092"   # kassir B — A ning smenasiga TEGA OLMASIN
PHONE_ADMIN    = "+998900000093"   # admin — manage_shifts bor
PHONE_MENEJER  = "+998900000094"   # menejer — manage_shifts bor
PHONE_BEGONA   = "+998900000095"   # boshqa tenant admini


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
    p_shifts = Permission(code="manage_shifts",   description="Smenalar")
    p_pay    = Permission(code="process_payments", description="To'lovlar")
    db.add_all([p_shifts, p_pay]); db.flush()

    # Kassirda `manage_shifts` ATAYLAB yo'q (database.py dagi urug' bilan bir xil)
    r_kassir  = Role(name="cashier", description="Kassir");        r_kassir.permissions  = [p_pay]
    r_admin   = Role(name="admin",   description="Administrator"); r_admin.permissions   = [p_pay, p_shifts]
    r_menejer = Role(name="menejer", description="Menejer");       r_menejer.permissions = [p_pay, p_shifts]
    db.add_all([r_kassir, r_admin, r_menejer]); db.flush()

    cafe_a = Cafe(name="SINOV", code="a", access_code="100.200.91",
                  business_type="supermarket", subscription_plan="pro", is_active=True)
    cafe_b = Cafe(name="BEGONA", code="b", access_code="100.200.92",
                  business_type="store", subscription_plan="pro", is_active=True)
    db.add_all([cafe_a, cafe_b]); db.flush()

    users = {}
    for phone, role, cafe, nom in (
        (PHONE_KASSIR_A, r_kassir,  cafe_a, "KASSIR A"),
        (PHONE_KASSIR_B, r_kassir,  cafe_a, "KASSIR B"),
        (PHONE_ADMIN,    r_admin,   cafe_a, "ADMIN"),
        (PHONE_MENEJER,  r_menejer, cafe_a, "MENEJER"),
        (PHONE_BEGONA,   r_admin,   cafe_b, "BEGONA ADMIN"),
    ):
        u = User(username=f"u{phone[-3:]}", email=f"{phone[-3:]}@x.uz", full_name=nom,
                 phone=phone, hashed_password=get_password_hash(PW), is_active=True,
                 is_superuser=False, tenant_id=cafe.id, role_id=role.id)
        db.add(u); db.flush()
        users[phone] = u.id
    db.commit()
    return {"db": db, "users": users, "cafe_a": cafe_a.id, "cafe_b": cafe_b.id}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client, phone):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _open(client, hdr, user_id, starting_cash=0):
    return client.post("/api/v1/shifts/", headers=hdr,
                       json={"user_id": user_id, "starting_cash": starting_cash})


def _close(client, hdr, shift_id, counted_cash=0):
    return client.post(f"/api/v1/shifts/{shift_id}/close?counted_cash={counted_cash}",
                       headers=hdr)


# ══════════════════════════════════════════════════════════════════════════════
# 1) OCHISH — smena egasi klientdan olinmaydi
# ══════════════════════════════════════════════════════════════════════════════

def test_kassir_ozi_ochadi(client, seeded):
    """Oddiy yo'l (FAZZA/1001 BARAKA aynan shunday ishlaydi) — buzilmasin."""
    uid = seeded["users"][PHONE_KASSIR_A]
    r = _open(client, _login(client, PHONE_KASSIR_A), uid, 50000)
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == uid
    assert r.json()["starting_cash"] == 50000


def test_soxta_user_id_bloklanadi(client, seeded):
    """⚠️ ASOSIY: kassir B nomiga smena ochib bo'lmaydi.

    ILGARI 200 qaytardi va smena B ga ochilardi — B ning sotuvi va kamomadi
    o'sha smenaga tushardi.
    """
    hdr = _login(client, PHONE_KASSIR_A)
    r = _open(client, hdr, seeded["users"][PHONE_KASSIR_B])
    assert r.status_code == 403, r.text
    assert "o'zingizga" in r.json()["detail"]

    # Va hech qanday smena YARATILMAGAN bo'lsin
    db = seeded["db"]
    assert db.query(Shift).count() == 0


def test_admin_ham_boshqaga_ocholmaydi(client, seeded):
    """Hozircha admin ham boshqa xodimga ocholmaydi (keyin alohida endpoint)."""
    r = _open(client, _login(client, PHONE_ADMIN), seeded["users"][PHONE_KASSIR_A])
    assert r.status_code == 403, r.text


def test_user_id_nol_bolsa_oziga_ochiladi(client, seeded):
    """`user_id` 0/None bo'lsa ham smena so'rov yuborgan xodimga ochiladi."""
    r = _open(client, _login(client, PHONE_KASSIR_A), 0)
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == seeded["users"][PHONE_KASSIR_A]


# ══════════════════════════════════════════════════════════════════════════════
# 2) YOPISH — kassir faqat o'zinikini
# ══════════════════════════════════════════════════════════════════════════════

def test_kassir_oz_smenasini_yopadi(client, seeded):
    hdr = _login(client, PHONE_KASSIR_A)
    sid = _open(client, hdr, seeded["users"][PHONE_KASSIR_A]).json()["id"]

    r = _close(client, hdr, sid, counted_cash=1000)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == sid
    assert r.json()["cashier"] == "KASSIR A"


def test_kassir_BEGONA_smenani_yopolmaydi(client, seeded):
    """⚠️ ASOSIY: ILGARI 200 qaytardi — B, A ning kun yakunini yopa olardi."""
    hdr_a = _login(client, PHONE_KASSIR_A)
    sid_a = _open(client, hdr_a, seeded["users"][PHONE_KASSIR_A]).json()["id"]

    r = _close(client, _login(client, PHONE_KASSIR_B), sid_a)
    assert r.status_code == 403, r.text
    assert "o'z smenangizni" in r.json()["detail"]

    # Smena OCHIQ qolgan bo'lsin (yopilib ketmagan)
    seeded["db"].expire_all()
    assert seeded["db"].query(Shift).get(sid_a).end_time is None


def test_admin_istalgan_smenani_yopadi(client, seeded):
    """Kassir yopmasdan ketsa — kun yakunini admin yopadi."""
    hdr_a = _login(client, PHONE_KASSIR_A)
    sid_a = _open(client, hdr_a, seeded["users"][PHONE_KASSIR_A]).json()["id"]

    r = _close(client, _login(client, PHONE_ADMIN), sid_a, counted_cash=2000)
    assert r.status_code == 200, r.text
    assert r.json()["cashier"] == "KASSIR A"   # egasi o'zgarmaydi


def test_menejer_istalgan_smenani_yopadi(client, seeded):
    """`manage_shifts` menejerda ham bor (database.py rol urug'i)."""
    hdr_a = _login(client, PHONE_KASSIR_A)
    sid_a = _open(client, hdr_a, seeded["users"][PHONE_KASSIR_A]).json()["id"]

    r = _close(client, _login(client, PHONE_MENEJER), sid_a)
    assert r.status_code == 200, r.text


def test_begona_tenant_kormaydi(client, seeded):
    """Tenant izolyatsiyasi — boshqa do'kon smenasi 404 (403 emas: mavjudligi ham sir)."""
    hdr_a = _login(client, PHONE_KASSIR_A)
    sid_a = _open(client, hdr_a, seeded["users"][PHONE_KASSIR_A]).json()["id"]

    r = _close(client, _login(client, PHONE_BEGONA), sid_a)
    assert r.status_code == 404, r.text


def test_ikki_kassir_parallel_ishlaydi(client, seeded):
    """Navbat almashish: ikkalasi o'z smenasini ochadi va o'zi yopadi."""
    hdr_a = _login(client, PHONE_KASSIR_A)
    hdr_b = _login(client, PHONE_KASSIR_B)
    sid_a = _open(client, hdr_a, seeded["users"][PHONE_KASSIR_A]).json()["id"]
    sid_b = _open(client, hdr_b, seeded["users"][PHONE_KASSIR_B]).json()["id"]
    assert sid_a != sid_b

    assert _close(client, hdr_a, sid_a).status_code == 200
    assert _close(client, hdr_b, sid_b).status_code == 200


def test_allaqachon_yopilgan(client, seeded):
    """Mavjud xatti-harakat saqlanadi: ikkinchi yopish 400."""
    hdr = _login(client, PHONE_KASSIR_A)
    sid = _open(client, hdr, seeded["users"][PHONE_KASSIR_A]).json()["id"]
    assert _close(client, hdr, sid).status_code == 200
    r = _close(client, hdr, sid)
    assert r.status_code == 400
    assert "allaqachon" in r.json()["detail"]


def test_begona_smena_holati_sizmaydi(client, seeded):
    """403 tekshiruvi "allaqachon yopilgan" dan OLDIN bo'lsin.

    Aks holda kassir B, A ning smenasi yopiq yoki ochiqligini xato kodidan
    (400 vs 403) bilib olardi.
    """
    hdr_a = _login(client, PHONE_KASSIR_A)
    sid_a = _open(client, hdr_a, seeded["users"][PHONE_KASSIR_A]).json()["id"]
    _close(client, hdr_a, sid_a)                      # A o'zi yopdi

    r = _close(client, _login(client, PHONE_KASSIR_B), sid_a)
    assert r.status_code == 403, "yopiq smena uchun ham 403 bo'lsin (400 emas)"
