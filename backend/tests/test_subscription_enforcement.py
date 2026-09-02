"""OBUNA ENFORCEMENT — uchta nuqson tuzatildi (2026-09-02).

TUZATILGAN NUQSONLAR

N1  `tasks/scheduler.check_expired_tenants` UCH XATO qilardi:
      a) `is_active = False` qo'yardi. `is_active` KIRISH yo'lida tekshiriladi
         (`auth.resolve-code` va `auth.pin-login` `Cafe.is_active == True` filtri),
         shuning uchun muddat tugashi bilan kassirlar kirish ekranida
         "Do'kon topilmadi" ko'rardi — ENFORCE_SUBSCRIPTION=False bo'lsa ham.
         Ya'ni enforcement'ning bir qismi KILL-SWITCH'DAN TASHQARIDA edi.
      b) muhlatni (grace) hisobga olmasdi;
      c) kill-switch o'chiq bo'lsa ham bazani o'zgartirardi.

N2  `core.subscription.subscription_state` da `tenant_status == 'expired'`
    tekshiruvi MUHLAT shoxidan OLDIN turardi → grace shoxiga navbat hech
    qachon kelmasdi, `SUBSCRIPTION_GRACE_DAYS` amalda o'lik edi.

N3  `routers/cafe.renew_subscription` sanani uzaytirar, lekin
    `tenant_status`/`is_active` ni tiklamasdi → do'kon bloklangan qolardi.

GOLDEN: hozirgi 5 jonli tenant konfiguratsiyasi (hammasi active, muddati
kelajakda) hech qaysi holatda bloklanmasligi shart.

Ishga tushirish:  cd backend && py -m pytest tests/test_subscription_enforcement.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings
from core.subscription import subscription_state, WARN_DAYS
from database import Base
from models import Cafe

GRACE = 2   # settings.SUBSCRIPTION_GRACE_DAYS standarti


# ══════════════════════════════════════════════════════════════════════════
#  Yordamchilar
# ══════════════════════════════════════════════════════════════════════════

class _CafeStub:
    """`subscription_state` faqat getattr ishlatadi — baza shart emas."""
    def __init__(self, **kw):
        self.is_active = kw.get("is_active", True)
        self.tenant_status = kw.get("tenant_status", "active")
        self.blocked_reason = kw.get("blocked_reason", None)
        self.subscription_plan = kw.get("subscription_plan", "pro")
        self.subscription_expires = kw.get("subscription_expires", None)
        self.trial_expires = kw.get("trial_expires", None)


def _st(cafe, now=None):
    return subscription_state(cafe, now=now, grace_days=GRACE)


@pytest.fixture()
def sched_db(monkeypatch):
    """`check_expired_tenants` uchun izolyatsiyalangan baza.

    Vazifa `database.SessionLocal` ni CHAQIRUV PAYTIDA o'qiydi, shuning uchun
    modul atributini almashtirish yetarli (conftest ham shu usulni ishlatadi).
    """
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    Session = sessionmaker(bind=eng)
    import database as _db
    monkeypatch.setattr(_db, "SessionLocal", Session)
    s = Session()
    yield s
    s.close()


def _run_task():
    from tasks.scheduler import check_expired_tenants
    asyncio.run(check_expired_tenants())


# ══════════════════════════════════════════════════════════════════════════
#  GOLDEN — hozirgi 5 jonli tenant buzilmasin
# ══════════════════════════════════════════════════════════════════════════

# (id, nom, tarif, muddat) — 2026-09-02 holati, prod bazasidan olingan
JONLI_TENANTLAR = [
    (5,  "lux-parfum",   "standart", "2027-08-12"),
    (7,  "biznes test",  "pro",      "2027-08-12"),
    (19, "qpa",          "pro",      "2027-08-12"),
    (20, "eco aroma",    "pro",      "2027-08-12"),
    (26, "FAZZA PERFUM", "pro",      "2026-09-17"),
]


@pytest.mark.parametrize("tid,nom,plan,muddat", JONLI_TENANTLAR)
def test_golden_jonli_tenantlar_bloklanmaydi(tid, nom, plan, muddat):
    """Hozirgi holat: hammasi active, muddat kelajakda → BLOK YO'Q."""
    now = datetime(2026, 9, 2, 12, 0, 0)
    exp = datetime.strptime(muddat, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    st = _st(_CafeStub(subscription_plan=plan, subscription_expires=exp), now=now)
    assert st["blocked"] is False, f"{nom} bekorga bloklandi: {st}"
    assert st["state"] in ("active", "expiring"), f"{nom}: {st['state']}"


def test_golden_fazza_ogohlantirish_7_kun_qolganda():
    """Fazza 17-sentabr 23:59 da tugaydi → banner 11-sentabrdan.

    `_days_ceil` kunni YUQORIGA yaxlitlaydi: 10-sentabr 12:00 dan muddatgacha
    7 kun 12 soat bor → 8 kun deb hisoblanadi va hali `active`. 11-sentabrda
    7 kun bo'ladi va banner chiqadi.
    """
    exp = datetime(2026, 9, 17, 23, 59, 59)
    c = _CafeStub(subscription_expires=exp)

    assert _st(c, now=datetime(2026, 9,  2, 12))["state"] == "active"    # 16 kun
    assert _st(c, now=datetime(2026, 9, 10, 12))["state"] == "active"    # 8 kun
    st = _st(c, now=datetime(2026, 9, 11, 12))
    assert st["state"] == "expiring" and st["blocked"] is False          # 7 kun
    assert st["days_left"] <= WARN_DAYS
    assert _st(c, now=datetime(2026, 9, 16, 12))["blocked"] is False


# ══════════════════════════════════════════════════════════════════════════
#  N2 — MUHLAT (grace) endi ishlaydi
# ══════════════════════════════════════════════════════════════════════════

def test_n2_muddat_otgach_grace_boshlanadi():
    exp = datetime(2026, 9, 17, 23, 59, 59)
    st = _st(_CafeStub(subscription_expires=exp), now=datetime(2026, 9, 18, 10))
    assert st["state"] == "grace"
    assert st["blocked"] is False, "muhlat davrida ishlash to'xtamasligi kerak"
    assert st["in_grace"] is True
    assert 1 <= st["grace_days_left"] <= GRACE


def test_n2_grace_tugagach_bloklanadi():
    exp = datetime(2026, 9, 17, 23, 59, 59)
    st = _st(_CafeStub(subscription_expires=exp), now=datetime(2026, 9, 20, 10))
    assert st["state"] == "expired" and st["blocked"] is True


def test_n2_expired_belgisi_grace_ni_YEB_QOMAYDI():
    """ENG MUHIM N2 REGRESSIYASI.

    Ilgari `tenant_status='expired'` shoxi grace'dan OLDIN edi va darhol
    qattiq blok qaytarardi. Endi SANA yutadi: muhlat ichidagi tenant
    belgisidan qat'iy nazar ishlashda davom etadi.
    """
    exp = datetime(2026, 9, 17, 23, 59, 59)
    c = _CafeStub(subscription_expires=exp, tenant_status="expired")
    st = _st(c, now=datetime(2026, 9, 18, 10))
    assert st["state"] == "grace", f"grace shoxiga navbat kelmadi: {st}"
    assert st["blocked"] is False


def test_n2_tolov_muddatni_uzaytirsa_belgi_eskirgan_bolsa_ham_ochiladi():
    """N3 ning ikkinchi qatlam himoyasi: sana kelajakda → blok yo'q."""
    c = _CafeStub(subscription_expires=datetime(2026, 12, 1), tenant_status="expired")
    st = _st(c, now=datetime(2026, 9, 20, 10))
    assert st["blocked"] is False and st["state"] == "active"


def test_n2_qolda_qoyilgan_bloklar_QATTIQ_qoladi():
    """Super-admin amallari sanadan qat'iy nazar blok bo'lib qolsin —
    aks holda "do'konni o'chirish" tugmasi ma'nosini yo'qotardi."""
    kelajak = datetime(2027, 1, 1)
    o = _st(_CafeStub(subscription_expires=kelajak, is_active=False))
    assert o["state"] == "inactive" and o["blocked"] is True

    b = _st(_CafeStub(subscription_expires=kelajak, tenant_status="blocked",
                      blocked_reason="To'lov yo'q"))
    assert b["state"] == "blocked" and b["blocked"] is True
    assert b["message"] == "To'lov yo'q"


def test_n2_sanasiz_expired_belgisi_hali_ham_bloklaydi():
    """Muddat yo'q bo'lsa hukm faqat belgiga qoladi (orqaga moslik)."""
    st = _st(_CafeStub(subscription_expires=None, tenant_status="expired"))
    assert st["blocked"] is True and st["state"] == "expired"


def test_n2_muddatsiz_tenant_hech_qachon_bloklanmaydi():
    st = _st(_CafeStub(subscription_expires=None))
    assert st["blocked"] is False and st["state"] == "active"


# ══════════════════════════════════════════════════════════════════════════
#  N1 — scheduler: kill-switch, grace, is_active
# ══════════════════════════════════════════════════════════════════════════

def _tenant(db, **kw):
    c = Cafe(id=kw.pop("id", 1), name=kw.pop("name", "Sinov"), code="S1",
             subscription_plan="pro", tenant_status="active", is_active=True, **kw)
    db.add(c)
    db.commit()
    return c


def test_n1_kill_switch_ochiq_bolsa_vazifa_BAZAGA_TEGMAYDI(sched_db, monkeypatch):
    """ENFORCE=False → hech narsa o'zgarmasin (kill-switch TO'LIQ)."""
    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", False)
    c = _tenant(sched_db, subscription_expires=datetime.now() - timedelta(days=30))

    _run_task()
    sched_db.refresh(c)
    assert c.tenant_status == "active", "kill-switch o'chiq, lekin status o'zgardi"
    assert c.is_active is True


def test_n1_is_active_ga_HECH_QACHON_tegilmaydi(sched_db, monkeypatch):
    """ENG MUHIM N1 REGRESSIYASI — kassir kirish ekrani o'lmasin.

    `resolve-code` va `pin-login` `Cafe.is_active == True` filtrini
    ishlatadi; vazifa uni False qilsa kassir "Do'kon topilmadi" ko'radi.
    """
    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", True)
    monkeypatch.setattr(settings, "SUBSCRIPTION_GRACE_DAYS", GRACE)
    c = _tenant(sched_db, subscription_expires=datetime.now() - timedelta(days=30))

    _run_task()
    sched_db.refresh(c)
    assert c.is_active is True, "vazifa `is_active` ni o'zgartirdi — kirish yo'li sinadi"
    assert c.tenant_status == "expired", "belgi qo'yilishi kerak edi"


def test_n1_grace_ichida_belgilanmaydi(sched_db, monkeypatch):
    """Muddat tugagan, lekin muhlat hali tugamagan → tegilmasin."""
    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", True)
    monkeypatch.setattr(settings, "SUBSCRIPTION_GRACE_DAYS", GRACE)
    c = _tenant(sched_db, subscription_expires=datetime.now() - timedelta(hours=6))

    _run_task()
    sched_db.refresh(c)
    assert c.tenant_status == "active", "muhlat ichida bo'lsa ham `expired` qo'yildi"
    assert c.is_active is True


def test_n1_grace_tugagach_belgilanadi(sched_db, monkeypatch):
    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", True)
    monkeypatch.setattr(settings, "SUBSCRIPTION_GRACE_DAYS", GRACE)
    c = _tenant(sched_db,
                subscription_expires=datetime.now() - timedelta(days=GRACE, hours=2))

    _run_task()
    sched_db.refresh(c)
    assert c.tenant_status == "expired"
    assert c.is_active is True


def test_n1_ochirilgan_dokonga_tegilmaydi(sched_db, monkeypatch):
    """`is_active=False` — super-admin amali; vazifa uni qaytadan ishlamasin."""
    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", True)
    c = _tenant(sched_db, subscription_expires=datetime.now() - timedelta(days=30))
    c.is_active = False
    sched_db.commit()

    _run_task()
    sched_db.refresh(c)
    assert c.tenant_status == "active", "o'chirilgan do'kon holati o'zgartirildi"


def test_n1_muddati_kelajakdagi_tenantga_tegilmaydi(sched_db, monkeypatch):
    """GOLDEN: jonli 5 tenantning hammasi shu holatda."""
    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", True)
    c = _tenant(sched_db, subscription_expires=datetime.now() + timedelta(days=300))

    _run_task()
    sched_db.refresh(c)
    assert c.tenant_status == "active" and c.is_active is True


# ══════════════════════════════════════════════════════════════════════════
#  TO'LIQ HAYOT SIKLI — muddat → grace → blok → to'lov → ochilish
# ══════════════════════════════════════════════════════════════════════════

def test_toliq_sikl():
    exp = datetime(2026, 9, 17, 23, 59, 59)
    c = _CafeStub(subscription_expires=exp)

    bosqichlar = [
        (datetime(2026, 9,  2, 12), "active",   False),
        (datetime(2026, 9, 12, 12), "expiring", False),   # <=7 kun — banner
        (datetime(2026, 9, 18, 10), "grace",    False),   # muhlat — ishlaydi
        (datetime(2026, 9, 19, 10), "grace",    False),
        (datetime(2026, 9, 20, 10), "expired",  True),    # muhlat tugadi — blok
    ]
    for now, kutilgan, blok in bosqichlar:
        st = _st(c, now=now)
        assert st["state"] == kutilgan, f"{now:%d.%m}: {st['state']} != {kutilgan}"
        assert st["blocked"] is blok, f"{now:%d.%m}: blocked={st['blocked']}"

    # To'lov: `super_admin.add_payment` mantiqi — sana + holat tiklanadi
    c.subscription_expires = datetime(2026, 10, 20, 23, 59, 59)
    c.tenant_status = "active"
    c.is_active = True
    st = _st(c, now=datetime(2026, 9, 20, 10, 5))
    assert st["blocked"] is False and st["state"] == "active", "to'lovdan keyin ochilmadi"
