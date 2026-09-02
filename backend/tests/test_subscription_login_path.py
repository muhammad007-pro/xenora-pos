"""OBUNA — KIRISH YO'LI muddati tugagandan keyin ham ochiq qolsinmi (N1).

NEGA ALOHIDA FAYL: bu yerda HAQIQIY endpointlar (`/auth/resolve-code`,
`/auth/pin-login`) sinaladi, ya'ni `client` fixture va test.db kerak —
`test_subscription_enforcement.py` esa sof birlik (unit) testlar.

MUAMMO (2026-09-02 gacha): `tasks/scheduler.check_expired_tenants` muddat
tugashi bilan `Cafe.is_active = False` qo'yardi. Ikkala kirish endpointi ham
`Cafe.is_active == True` filtri bilan ishlaydi (`routers/auth.py:264, 284`),
shuning uchun kassir kirish ekranida "Do'kon topilmadi" ko'rardi — va bu
`ENFORCE_SUBSCRIPTION=False` bo'lganda ham sodir bo'lardi, ya'ni kill-switch
teshik edi.

Bu fayl AYNAN shu holatni qulflaydi: muddati o'tgan tenant uchun kod+PIN
kirish ISHLASHDA DAVOM ETSIN. Bloklash — `deps._enforce_subscription` ning
ishi (u kill-switch ostida), kirish ekranining emas.

Ishga tushirish:  cd backend && py -m pytest tests/test_subscription_login_path.py -v
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.security import hash_pin, get_password_hash
from models import Cafe, Role, User

ACCESS_CODE = "100.900.1"
PIN = "4771"
TID = 9001


@pytest.fixture()
def expired_tenant(client):
    """Muddati 30 kun oldin tugagan tenant + PIN'li kassir.

    `is_active=True` — tuzatishdan keyin scheduler bu maydonga tegmaydi,
    shuning uchun jonli holat aynan shunday bo'ladi.
    """
    from tests.conftest import TestingSessionLocal
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.tenant_id == TID).delete()
        db.query(Cafe).filter(Cafe.id == TID).delete()
        db.commit()

        db.add(Cafe(
            id=TID, name="Muddati Tugagan Do'kon", code="MTD",
            access_code=ACCESS_CODE, business_type="store",
            subscription_plan="pro", tenant_status="expired",   # scheduler belgisi
            is_active=True,                                     # ← TEGILMAGAN
            subscription_expires=datetime.now() - timedelta(days=30),
        ))
        role = db.query(Role).filter(Role.name == "admin").first()
        db.add(User(
            username="kassir9001", email="k9001@test.local", full_name="Kassir",
            phone="+998900009001", hashed_password=get_password_hash("TestKassir9x"),
            hashed_pin=hash_pin(PIN), is_active=True, is_superuser=False,
            tenant_id=TID, role_id=role.id if role else None,
        ))
        db.commit()
        yield TID
        db.query(User).filter(User.tenant_id == TID).delete()
        db.query(Cafe).filter(Cafe.id == TID).delete()
        db.commit()
    finally:
        db.close()


def test_muddati_tugagan_dokon_kirish_ekranida_KORINADI(client, expired_tenant):
    """`resolve-code` — kassir kodni kiritganda do'kon nomi chiqsin.

    Ilgari bu 404 "Do'kon topilmadi" bo'lardi va kassir nima bo'lganini
    tushunmasdi (obuna haqida bir og'iz so'z yo'q edi).
    """
    r = client.get(f"/api/v1/auth/resolve-code?code={ACCESS_CODE}")
    assert r.status_code == 200, (
        f"Muddati tugagan do'kon kirish ekranidan yo'qoldi ({r.status_code}): {r.text}"
    )
    assert r.json()["id"] == expired_tenant


def test_muddati_tugagan_dokonda_PIN_login_ISHLAYDI(client, expired_tenant):
    """`pin-login` — token berilsin.

    Enforcement yoqilgan bo'lsa keyingi so'rov 403 (SUBSCRIPTION_EXPIRED)
    bo'ladi va foydalanuvchi TUSHUNARLI blok ekranini ko'radi. Kirishning
    o'zi esa "kod noto'g'ri" degan ADASHTIRUVCHI xato bermasligi kerak.
    """
    r = client.post("/api/v1/auth/pin-login",
                    json={"pin": PIN, "access_code": ACCESS_CODE})
    assert r.status_code == 200, (
        f"Muddati tugagan do'konda PIN login sindi ({r.status_code}): {r.text}"
    )
    assert r.json().get("access_token")


def test_ochirilgan_dokon_kirish_ekranida_KORINMAYDI(client, expired_tenant):
    """Aksincha holat: super-admin QO'LDA o'chirgan do'kon yashirin qolsin.

    `is_active` ma'nosi shu — u obuna emas, do'konning o'zi o'chirilgani.
    """
    from tests.conftest import TestingSessionLocal
    db = TestingSessionLocal()
    try:
        cafe = db.query(Cafe).filter(Cafe.id == TID).first()
        cafe.is_active = False
        db.commit()
    finally:
        db.close()

    assert client.get(f"/api/v1/auth/resolve-code?code={ACCESS_CODE}").status_code == 404
    r = client.post("/api/v1/auth/pin-login",
                    json={"pin": PIN, "access_code": ACCESS_CODE})
    assert r.status_code == 400
