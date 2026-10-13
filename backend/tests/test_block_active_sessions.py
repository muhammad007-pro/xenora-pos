"""BLOKLASH OCHIQ SESSIYANI HAM UZADI (2026-10-13, BARAKA).

MUAMMO (jonli): super-admin "Bloklash" (`POST /super-admin/tenants/{id}/block`)
faqat KIRISH yo'lini (resolve-code / pin-login kod bilan) to'sardi. Har so'rovda
faqat `user.is_active` tekshirilardi, `/auth/refresh` esa har safar yangi 30
kunlik token berardi — bloklangan do'kon kassasi CHEKSIZ sotishda davom etdi.
Uzish uchun xodimlarni birma-bir nofaol qilishga to'g'ri keldi.

TUZATISH: `deps.assert_store_open` — `get_current_user`, `/auth/refresh`,
`/auth/login` (kodsiz) va `/auth/pin-login` (eski branch_id yo'li) da:
    cafe.is_active=False YOKI tenant_status='blocked' → 403 STORE_INACTIVE

KAFOLATLAR (shu fayl qulflaydi):
  · bitta "Bloklash" tugmasi yetadi — mavjud token keyingi so'rovda 403, refresh 403
  · ENFORCE_SUBSCRIPTION dan MUSTAQIL (False va True da bir xil)
  · muddati tugagan (`expired`) do'kon kill-switch o'chiq bo'lsa ISHLAYVERADI
  · faol do'kon va super-admin tegilmaydi; unblock'dan keyin o'sha token tiklanadi

Ishga tushirish:
    cd backend && py -m pytest tests/test_block_active_sessions.py -v
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import Cafe, User, Role, Permission, Branch
from core.security import get_password_hash, hash_pin, create_access_token, create_refresh_token
from routers.auth import _build_token_data
from config import settings

PW = "AdminFaol9x"
KOD_A, KOD_B = "100.200.81", "100.200.82"
PH_A, PH_B = "+998900000081", "+998900000082"
API = "/api/v1"


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
    """Ikki faol do'kon (A — bloklanadigan, B — qo'shni) + super-admin."""
    db = db_session
    perm = Permission(code="manage_users", description="Xodimlar")
    db.add(perm)
    db.flush()
    role = Role(name="admin", description="Administrator")
    role.permissions = [perm]
    db.add(role)
    db.flush()

    a = Cafe(name="DO'KON A", code="a", access_code=KOD_A, business_type="store",
             subscription_plan="pro", is_active=True, tenant_status="active")
    b = Cafe(name="DO'KON B", code="b", access_code=KOD_B, business_type="store",
             subscription_plan="pro", is_active=True, tenant_status="active")
    db.add_all([a, b])
    db.flush()
    br_a = Branch(tenant_id=a.id, name="Asosiy", is_active=True, is_default=True)
    db.add(br_a)
    db.flush()

    ua = User(username="adminA", email="a@x.uz", full_name="Admin A", phone=PH_A,
              hashed_password=get_password_hash(PW), hashed_pin=hash_pin("2580"),
              is_active=True, is_superuser=False, tenant_id=a.id, role_id=role.id,
              branch_id=br_a.id)
    ub = User(username="adminB", email="b@x.uz", full_name="Admin B", phone=PH_B,
              hashed_password=get_password_hash(PW),
              is_active=True, is_superuser=False, tenant_id=b.id, role_id=role.id)
    su = User(username="root", email="r@x.uz", full_name="Super", phone="+998900000080",
              hashed_password=get_password_hash(PW), is_active=True, is_superuser=True,
              tenant_id=None)
    db.add_all([ua, ub, su])
    db.commit()
    return {"db": db, "a": a.id, "b": b.id, "ua": ua.id, "ub": ub.id, "su": su.id,
            "br_a": br_a.id}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def tokens(db, uid):
    """Ochiq sessiya: login'dagi bilan bir xil shakldagi access + refresh."""
    u = db.get(User, uid)
    td = _build_token_data(u, db, u.branch_id)
    return create_access_token(td), create_refresh_token(td)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def me(client, tok):
    return client.get(f"{API}/auth/me", headers=H(tok))


def refresh(client, ref):
    return client.post(f"{API}/auth/refresh", json={"refresh_token": ref})


def block(client, db, tenant_id):
    su_tok, _ = tokens(db, db.query(User).filter(User.is_superuser).first().id)
    r = client.post(f"{API}/super-admin/tenants/{tenant_id}/block", headers=H(su_tok),
                    json={"reason": "To'lov qilinmagan"})
    assert r.status_code == 200, r.text
    return su_tok


def assert_store_inactive(r):
    assert r.status_code == 403, f"{r.status_code} {r.text}"
    body = r.json()
    assert body.get("code") == "STORE_INACTIVE"
    assert isinstance(body.get("detail"), str), "detail MATN bo'lishi shart ([object Object])"
    assert "To'lov" not in body["detail"], "sabab (blocked_reason) oshkor bo'lmasin"


# ══════════════════════════════════════════════════════════════════════════════
# 1) FAOL DO'KON — tegilmagan
# ══════════════════════════════════════════════════════════════════════════════

def test_faol_dokon_sessiyasi_ishlaydi(client, seeded):
    acc, ref = tokens(seeded["db"], seeded["ua"])
    assert me(client, acc).status_code == 200
    assert client.get(f"{API}/users/", headers=H(acc)).status_code == 200
    r = refresh(client, ref)
    assert r.status_code == 200 and r.json()["access_token"]


# ══════════════════════════════════════════════════════════════════════════════
# 2) BITTA "BLOKLASH" — ochiq sessiya uziladi
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("enforce", [False, True], ids=["enforce_off", "enforce_on"])
def test_bloklash_ochiq_sessiyani_uzadi(client, seeded, monkeypatch, enforce):
    """ENFORCE_SUBSCRIPTION ga BOG'LIQ EMAS — qo'lda bloklash har doim ishlaydi."""
    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", enforce)
    db = seeded["db"]
    acc, ref = tokens(db, seeded["ua"])
    assert me(client, acc).status_code == 200          # bloklashdan oldin ishlardi

    block(client, db, seeded["a"])

    assert_store_inactive(me(client, acc))
    assert_store_inactive(client.get(f"{API}/users/", headers=H(acc)))
    assert_store_inactive(refresh(client, ref))         # sessiya cho'zilmaydi
    # xodim nofaol QILINMAGAN — bitta tugma yetdi
    db.expire_all()
    assert db.get(User, seeded["ua"]).is_active is True


def test_qoshni_dokon_va_super_admin_tegilmaydi(client, seeded):
    db = seeded["db"]
    acc_b, ref_b = tokens(db, seeded["ub"])
    su_tok = block(client, db, seeded["a"])
    assert me(client, acc_b).status_code == 200
    assert refresh(client, ref_b).status_code == 200
    assert me(client, su_tok).status_code == 200
    assert client.get(f"{API}/super-admin/tenants", headers=H(su_tok)).status_code == 200


def test_faqat_is_active_false_ham_uzadi(client, seeded):
    """Do'kon o'chirilgan (tenant_status tegilmagan) — xuddi shunday 403."""
    db = seeded["db"]
    acc, ref = tokens(db, seeded["ua"])
    db.get(Cafe, seeded["a"]).is_active = False
    db.commit()
    assert_store_inactive(me(client, acc))
    assert_store_inactive(refresh(client, ref))


def test_unblock_dan_keyin_osha_token_ishlaydi(client, seeded):
    db = seeded["db"]
    acc, ref = tokens(db, seeded["ua"])
    su_tok = block(client, db, seeded["a"])
    assert_store_inactive(me(client, acc))
    r = client.post(f"{API}/super-admin/tenants/{seeded['a']}/unblock", headers=H(su_tok))
    assert r.status_code == 200
    assert me(client, acc).status_code == 200
    assert refresh(client, ref).status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 3) KIRISH YO'LLARIDAGI TESHIKLAR — kodsiz login, eski branch_id PIN
# ══════════════════════════════════════════════════════════════════════════════

def test_kodsiz_login_bloklangan_dokonga_token_bermaydi(client, seeded):
    block(client, seeded["db"], seeded["a"])
    r = client.post(f"{API}/auth/login", data={"username": PH_A, "password": PW})
    assert_store_inactive(r)


def test_branch_id_pin_login_bloklangan_dokonga_token_bermaydi(client, seeded):
    db = seeded["db"]
    # bloklashdan oldin — eski yo'l ishlaydi
    ok = client.post(f"{API}/auth/pin-login", json={"pin": "2580", "branch_id": seeded["br_a"]})
    assert ok.status_code == 200, ok.text
    block(client, db, seeded["a"])
    r = client.post(f"{API}/auth/pin-login", json={"pin": "2580", "branch_id": seeded["br_a"]})
    assert_store_inactive(r)


# ══════════════════════════════════════════════════════════════════════════════
# 4) KILL-SWITCH TESHILMAGAN — muddati tugagan do'kon (expired) ishlayveradi
# ══════════════════════════════════════════════════════════════════════════════

def test_muddati_tugagan_dokon_enforce_ochiq_bolsa_ishlaydi(client, seeded, monkeypatch):
    """`expired` — obuna SANASI hukmi, u ENFORCE_SUBSCRIPTION ostida qoladi."""
    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", False)
    db = seeded["db"]
    c = db.get(Cafe, seeded["a"])
    c.tenant_status = "expired"
    c.subscription_expires = datetime.now() - timedelta(days=30)
    db.commit()
    acc, ref = tokens(db, seeded["ua"])
    assert me(client, acc).status_code == 200
    assert refresh(client, ref).status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 5) QULF: tekshiruv get_current_user DA (barcha 227+ endpoint bitta joydan)
# ══════════════════════════════════════════════════════════════════════════════

def test_tekshiruv_get_current_user_va_refresh_da():
    import inspect
    import deps
    import routers.auth as ra
    assert "assert_store_open(user, db)" in inspect.getsource(deps.get_current_user)
    assert "ENFORCE_SUBSCRIPTION" not in inspect.getsource(deps.assert_store_open).split('"""')[-1], \
        "qo'lda blok kill-switch'ga bog'lanmasin"
    for fn in (ra.refresh_token, ra.login, ra.pin_login):
        assert "assert_store_open(user, db)" in inspect.getsource(fn), fn.__name__
