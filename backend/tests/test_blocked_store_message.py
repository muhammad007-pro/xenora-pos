"""YOPIQ DO'KON — kirish ekranidagi xabar (2026-09-09).

MUAMMO (jonli): uchala kirish yo'lida ham do'kon so'rovi `Cafe.is_active == True`
filtri BILAN yozilgan edi:

    db.query(Cafe).filter(Cafe.access_code == ac, Cafe.is_active == True)

Natijada faolsizlantirilgan/bloklangan do'kon "umuman mavjud emas" bilan bir xil
ko'rinardi — kassir ekranida "Do'kon topilmadi" chiqardi va u kodni xato tergan
deb o'ylab qayta-qayta urinardi. eco aroma (tenant 20) bloklanganda aynan shu
kuzatildi.

TUZATISH: `_find_store_by_code()` yordamchisi ikki holatni AJRATADI —
    · kod yo'q         → 404/400, matn O'ZGARMAGAN (mavjud klientlar buzilmasin)
    · do'kon yopiq     → 403 {code: STORE_INACTIVE} + aloqa raqami

GOLDEN QOIDA: FAOL do'kon yo'li (FAZZA, 1001 BARAKA) tegilmasin — `resolve-code`
avvalgidek 200 va aynan o'sha uch maydonni qaytarsin.

XAVFSIZLIK: javobda `blocked_reason` BO'LMASIN (super-admin ichki eslatmasi) va
sabab (to'lov/obuna) aytilmasin — kirish kodlari ketma-ket, ya'ni sanab chiqish
oson. Test ikkalasini ham tekshiradi.

Ishga tushirish:
    cd backend && py -m pytest tests/test_blocked_store_message.py -v
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
from models import Cafe, User, Role, Permission
from core.security import get_password_hash
from config import settings

ADMIN_PW = "AdminFaol9x"

KOD_FAOL      = "100.200.91"   # normal ishlaydigan do'kon
KOD_OCHIQ     = "100.200.92"   # is_active=False
KOD_BLOCKED   = "100.200.93"   # tenant_status='blocked'
KOD_EXPIRED   = "100.200.94"   # tenant_status='expired' — YOPIQ EMAS (N1)
KOD_YOQ       = "100.200.99"   # umuman mavjud emas


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


@pytest.fixture()
def seeded(db_session):
    """To'rt do'kon: faol, o'chirilgan, bloklangan, muddati tugagan."""
    db = db_session

    p_pay = Permission(code="process_payments", description="To'lovlar")
    db.add(p_pay)
    db.flush()
    r_admin = Role(name="admin", description="Administrator")
    r_admin.permissions = [p_pay]
    db.add(r_admin)
    db.flush()

    faol = Cafe(name="FAOL DO'KON", code="faol", access_code=KOD_FAOL,
                business_type="store", subscription_plan="pro",
                is_active=True, tenant_status="active")
    ochiq = Cafe(name="O'CHIRILGAN", code="ochiq", access_code=KOD_OCHIQ,
                 business_type="store", subscription_plan="pro",
                 is_active=False, tenant_status="blocked",
                 blocked_reason="Ichki eslatma: to'lamadi, 3 marta aytdim")
    blocked = Cafe(name="BLOKLANGAN", code="blok", access_code=KOD_BLOCKED,
                   business_type="store", subscription_plan="pro",
                   is_active=True, tenant_status="blocked",
                   blocked_reason="Ichki eslatma: sud jarayoni")
    expired = Cafe(name="MUDDATI TUGAGAN", code="exp", access_code=KOD_EXPIRED,
                   business_type="store", subscription_plan="pro",
                   is_active=True, tenant_status="expired")
    db.add_all([faol, ochiq, blocked, expired])
    db.flush()

    # Har do'konga bitta admin — /login yo'li (parol + kod) uchun
    for i, (cafe, phone) in enumerate([
        (faol, "+998900000091"), (ochiq, "+998900000092"),
        (blocked, "+998900000093"), (expired, "+998900000094"),
    ]):
        db.add(User(username=f"admin{i}", email=f"a{i}@x.uz", full_name=f"Admin {i}",
                    phone=phone, hashed_password=get_password_hash(ADMIN_PW),
                    is_active=True, is_superuser=False,
                    tenant_id=cafe.id, role_id=r_admin.id))
    db.commit()
    return {"db": db, "faol": faol.id, "ochiq": ochiq.id,
            "blocked": blocked.id, "expired": expired.id}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Uchala kirish yo'lini bitta chaqiruvga keltiruvchi yordamchilar ──────────
def r_resolve(client, kod):
    return client.get(f"/api/v1/auth/resolve-code?code={kod}")

def r_pin(client, kod):
    return client.post("/api/v1/auth/pin-login", json={"pin": "1234", "access_code": kod})

def r_login(client, kod, phone):
    return client.post("/api/v1/auth/login",
                       data={"username": phone, "password": ADMIN_PW, "access_code": kod})


# ══════════════════════════════════════════════════════════════════════════════
# 1) REGRESSIYA: faol do'kon yo'li TEGILMAGAN (FAZZA / 1001 BARAKA)
# ══════════════════════════════════════════════════════════════════════════════

def test_faol_dokon_resolve_code_200(client, seeded):
    r = r_resolve(client, KOD_FAOL)
    assert r.status_code == 200, f"faol do'kon buzildi: {r.status_code} {r.text}"
    body = r.json()
    assert body["id"] == seeded["faol"]
    assert body["name"] == "FAOL DO'KON"
    assert body["business_type"] == "store"
    assert set(body.keys()) == {"id", "name", "business_type"}, "javob sxemasi o'zgardi"


def test_faol_dokon_login_ishlaydi(client, seeded):
    """Parol + to'g'ri kod → token (jonli do'konlar shu yo'ldan kiradi)."""
    r = r_login(client, KOD_FAOL, "+998900000091")
    assert r.status_code == 200, f"faol do'kon login buzildi: {r.status_code} {r.text}"
    assert r.json().get("access_token")


# ══════════════════════════════════════════════════════════════════════════════
# 2) MAVJUD BO'LMAGAN KOD — matn O'ZGARMAGAN
# ══════════════════════════════════════════════════════════════════════════════

def test_yoq_kod_resolve_code_404(client, seeded):
    r = r_resolve(client, KOD_YOQ)
    assert r.status_code == 404
    assert r.json()["detail"] == "Do'kon topilmadi"


def test_yoq_kod_pin_login_400(client, seeded):
    """pin-login da eski matn saqlanadi ("Do'kon kodi noto'g'ri")."""
    r = r_pin(client, KOD_YOQ)
    assert r.status_code == 400
    assert r.json()["detail"] == "Do'kon kodi noto'g'ri"


def test_yoq_kod_login_400(client, seeded):
    r = r_login(client, KOD_YOQ, "+998900000091")
    assert r.status_code == 400
    assert r.json()["detail"] == "Do'kon kodi noto'g'ri"


# ══════════════════════════════════════════════════════════════════════════════
# 3) YOPIQ DO'KON — 403 STORE_INACTIVE, uchala yo'lda BIR XIL
# ══════════════════════════════════════════════════════════════════════════════

KUTILGAN_MATN = f"Do'kon vaqtincha faol emas. Bog'laning: {settings.SUPPORT_CONTACT}"


@pytest.mark.parametrize("kod,izoh", [
    (KOD_OCHIQ,   "is_active=False"),
    (KOD_BLOCKED, "tenant_status='blocked'"),
])
def test_yopiq_dokon_resolve_code_403(client, seeded, kod, izoh):
    """ILGARI: 404 'Do'kon topilmadi' — kassir kodni xato tergan deb o'ylardi."""
    r = r_resolve(client, kod)
    assert r.status_code == 403, f"{izoh}: {r.status_code} {r.text}"
    body = r.json()
    assert body["code"] == "STORE_INACTIVE"
    assert body["detail"] == KUTILGAN_MATN
    # ⚠️ `detail` MATN bo'lishi SHART — obyekt bo'lsa frontend "[object Object]"
    # ko'rsatadi (2026-09-09 da jonli chiqqan nuqson).
    assert isinstance(body["detail"], str), f"detail obyekt: {body['detail']!r}"


@pytest.mark.parametrize("kod", [KOD_OCHIQ, KOD_BLOCKED])
def test_yopiq_dokon_pin_login_403(client, seeded, kod):
    r = r_pin(client, kod)
    assert r.status_code == 403, f"{r.status_code} {r.text}"
    assert r.json()["code"] == "STORE_INACTIVE"
    assert isinstance(r.json()["detail"], str)


@pytest.mark.parametrize("kod,phone", [
    (KOD_OCHIQ,   "+998900000092"),
    (KOD_BLOCKED, "+998900000093"),
])
def test_yopiq_dokon_login_403(client, seeded, kod, phone):
    """Parol TO'G'RI bo'lsa ham do'kon yopiq → token berilmaydi."""
    r = r_login(client, kod, phone)
    assert r.status_code == 403, f"{r.status_code} {r.text}"
    assert r.json()["code"] == "STORE_INACTIVE"
    assert isinstance(r.json()["detail"], str)
    assert "access_token" not in r.json()


def test_detail_MATN_object_Object_chiqmaydi(client, seeded):
    """NUQSON (2026-09-09, jonli): javob ichma-ich edi —

        {"detail": {"code": "STORE_INACTIVE", "detail": "..."}}

    chunki `HTTPException(detail=<obyekt>)` ni FastAPI yana `{"detail": ...}`
    ichiga o'raydi. Frontend (`login.html:636`) `data.detail` ni MATN deb
    kutadi → kassir ekranida "[object Object]" chiqardi.

    Endi shakl TEKIS: `detail` — matn, `code` — yonida alohida maydon.
    """
    for javob in (r_resolve(client, KOD_BLOCKED),
                  r_pin(client, KOD_BLOCKED),
                  r_login(client, KOD_BLOCKED, "+998900000093")):
        body = javob.json()
        assert isinstance(body["detail"], str), f"detail obyekt qaytdi: {body!r}"
        assert body["detail"] == KUTILGAN_MATN
        assert body["code"] == "STORE_INACTIVE"
        # JS `String(data.detail)` aynan shu natijani beradi
        assert "[object Object]" not in str(body["detail"])
        assert "{" not in body["detail"] and "}" not in body["detail"]


def test_MUDDATI_TUGAGAN_dokon_YOPILMAYDI(client, seeded):
    """⚠️ CHEGARA: `expired` bu darvozaga KIRMAYDI — 2026-09-02 kafolati (N1).

    Muddati tugagan do'kon kirish ekranida KO'RINISHDA DAVOM ETADI. Sabab:
    obuna bo'yicha bloklash `deps._enforce_subscription` ning ishi va u
    KILL-SWITCH ostida. Bu yerga qo'shilsa, `ENFORCE_SUBSCRIPTION=False`
    bo'lganda ham muddati tugaganlar bloklanardi — kill-switch teshilardi.
    Qarang: tests/test_subscription_login_path.py.
    """
    r = r_resolve(client, KOD_EXPIRED)
    assert r.status_code == 200, (
        f"muddati tugagan do'kon kirish ekranidan yo'qoldi: {r.status_code} {r.text}")
    assert r.json()["id"] == seeded["expired"]

    # PIN login ham ishlashda davom etadi (token beriladi yoki PIN xato — 403 EMAS)
    assert r_pin(client, KOD_EXPIRED).status_code != 403


def test_uchala_endpoint_bir_xil_javob(client, seeded):
    """Uchala yo'l ham AYNAN bir xil tanani qaytaradi (izchillik)."""
    javoblar = [
        r_resolve(client, KOD_BLOCKED).json(),
        r_pin(client, KOD_BLOCKED).json(),
        r_login(client, KOD_BLOCKED, "+998900000093").json(),
    ]
    assert javoblar[0] == javoblar[1] == javoblar[2], javoblar
    for j in javoblar:
        assert set(j.keys()) == {"detail", "code"}, f"javob shakli o'zgardi: {j}"


# ══════════════════════════════════════════════════════════════════════════════
# 4) XAVFSIZLIK: ichki ma'lumot oqmasin
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("kod", [KOD_OCHIQ, KOD_BLOCKED])
def test_blocked_reason_javobda_YOQ(client, seeded, kod):
    """`blocked_reason` — super-admin ICHKI eslatmasi, mijoz ko'rmasin."""
    matn = r_resolve(client, kod).text.lower()
    assert "ichki eslatma" not in matn
    assert "to'lamadi" not in matn
    assert "sud jarayoni" not in matn
    assert "blocked_reason" not in matn


@pytest.mark.parametrize("kod", [KOD_OCHIQ, KOD_BLOCKED])
def test_sabab_aytilmaydi(client, seeded, kod):
    """Matn NEYTRAL: kodlar ketma-ket, begona odam to'lov holatini bilmasin."""
    matn = r_resolve(client, kod).text.lower()
    for taqiq in ("obuna", "to'lov", "tolov", "muddat", "qarz", "expired", "blocked"):
        assert taqiq not in matn, f"sabab oshkor bo'ldi: '{taqiq}'"


def test_dokon_nomi_va_holati_oshkor_bolmaydi(client, seeded):
    """Yopiq do'kon javobida na nom, na tenant_status bo'lsin."""
    matn = r_resolve(client, KOD_BLOCKED).text
    assert "BLOKLANGAN" not in matn
    assert "tenant_status" not in matn


def test_aloqa_raqami_konfiguratsiyadan(client, seeded):
    """Telefon kodda qattiq yozilmagan — `settings.SUPPORT_CONTACT` dan keladi."""
    body = r_resolve(client, KOD_BLOCKED).json()
    assert settings.SUPPORT_CONTACT in body["detail"]


def test_enforce_subscription_bayrogidan_mustaqil(client, seeded, monkeypatch):
    """Bayroq o'chiq (prod holati) bo'lsa ham yopiq do'kon xabari chiqadi."""
    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", False)
    r = r_resolve(client, KOD_BLOCKED)
    assert r.status_code == 403
    assert r.json()["code"] == "STORE_INACTIVE"
