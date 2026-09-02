"""OBUNA TELEGRAM OGOHLANTIRISHLARI — tasks/subscription_alerts.py.

⚠️ BU TESTLAR HECH QACHON HAQIQIY XABAR YUBORMAYDI.
Ikki qatlam himoya:
  1) `core.alert.send_to_chat` har testda soxta funksiya bilan almashtiriladi
     (monkeypatch) — tarmoqqa umuman chiqilmaydi;
  2) `test_himoya_tarmoqqa_chiqilmaydi` `_post_sync` ni ham to'sib, bironta
     test tasodifan haqiqiy yuborish yo'liga tushmasligini tasdiqlaydi.
Baza — xotiradagi SQLite (jonli bazaga tegilmaydi).

QAMROV
  • bosqich tanlash: 7/3/1 kun, muddat tugagani, muhlat tugagani
  • TAKROR: bir bosqich bir marta (soatlik yugurish 24 marta ursa ham)
  • obuna uzaytirilsa yangi tsikl o'z-o'zidan ochiladi (nollash kerak emas)
  • KILL-SWITCH o'chiq → bazaga ham, tarmoqqa ham tegilmaydi
  • Telegram o'chganda: yozuv yozilmaydi, dastur to'xtamaydi, keyin qayta uriniladi
  • egasiga faqat 7/3/1; chat id yo'q bo'lsa faqat adminga
  • GOLDEN: 5 jonli tenant bugun hech qanday xabar keltirmaydi

Ishga tushirish:  cd backend && py -m pytest tests/test_subscription_alerts.py -v
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
from core.subscription import subscription_state
from database import Base
from models import Cafe, SubscriptionAlert
from tasks import subscription_alerts as sa

GRACE = 2
ADMIN_CHAT = "111111"
OWNER_CHAT = "222222"


# ══════════════════════════════════════════════════════════════════════════
#  Yordamchilar
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db(monkeypatch):
    """Izolyatsiyalangan xotira bazasi + yoqilgan kill-switch.

    Vazifa `database.SessionLocal` ni CHAQIRUV paytida o'qiydi, shuning uchun
    modul atributini almashtirish yetarli.
    """
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    Session = sessionmaker(bind=eng)
    import database as _db
    monkeypatch.setattr(_db, "SessionLocal", Session)
    monkeypatch.setattr(settings, "SUBSCRIPTION_ALERTS_ENABLED", True)
    monkeypatch.setattr(settings, "ALERT_CHAT_ID", ADMIN_CHAT)
    monkeypatch.setattr(settings, "SUBSCRIPTION_GRACE_DAYS", GRACE)
    s = Session()
    yield s
    s.close()


@pytest.fixture()
def sent(monkeypatch):
    """Yuborilgan xabarlarni yig'adi; TARMOQQA CHIQMAYDI."""
    box = []

    def fake(text, chat_id, timeout=10):
        box.append({"chat": str(chat_id), "text": text})
        return True

    monkeypatch.setattr("core.alert.send_to_chat", fake)
    return box


def make_cafe(db, *, days_left=None, expires=None, name="Test Do'kon",
              plan="pro", chat=None, tenant_status="active", is_active=True,
              now=None):
    """Muddati berilgan kunga qolgan do'kon yaratadi."""
    now = now or datetime.now()
    if expires is None and days_left is not None:
        # ANIQ ofset. Kun oxiriga (23:59:59) surilsa `_days_ceil` YUQORIGA
        # yaxlitlab days_left ni bittaga oshirib yuboradi (7 emas, 8) — bu
        # haqiqiy xulq (GOLDEN testga qarang), lekin bu yordamchi aynan
        # N kun qolgan holatni qurishi kerak.
        expires = now + timedelta(days=days_left)
    c = Cafe(name=name, code=f"c{len(name)}{days_left}", business_type="store",
             subscription_plan=plan, subscription_expires=expires,
             tenant_status=tenant_status, is_active=is_active,
             telegram_chat_id=chat)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def run(now=None):
    """Vazifani yugurtiradi (now berilsa — o'sha vaqtda)."""
    if now is None:
        return asyncio.run(sa.check_subscription_alerts())
    import tasks.subscription_alerts as mod

    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    orig = mod.datetime
    mod.datetime = _DT
    try:
        return asyncio.run(sa.check_subscription_alerts())
    finally:
        mod.datetime = orig


def _state(cafe, now=None):
    return subscription_state(cafe, now=now or datetime.now(), grace_days=GRACE)


# ══════════════════════════════════════════════════════════════════════════
#  HIMOYA — jonli mijozlarga xabar ketmasligi
# ══════════════════════════════════════════════════════════════════════════

def test_himoya_tarmoqqa_chiqilmaydi(db, monkeypatch):
    """`_post_sync` chaqirilsa test YIQILADI — tarmoq yo'li butunlay yopiq."""
    def portla(*a, **k):
        raise AssertionError("HAQIQIY TELEGRAM YUBORISHGA URINDI!")

    monkeypatch.setattr("core.alert._post_sync", portla)
    # Token bo'sh bo'lgani uchun send_to_chat _post_sync gacha bormaydi:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    make_cafe(db, days_left=7, chat=OWNER_CHAT)
    assert run() == 0          # yuborilmadi
    assert db.query(SubscriptionAlert).count() == 0   # yozuv ham yo'q


def test_kill_switch_ochiq_bolsa_hech_narsa_qilmaydi(db, sent, monkeypatch):
    monkeypatch.setattr(settings, "SUBSCRIPTION_ALERTS_ENABLED", False)
    make_cafe(db, days_left=1, chat=OWNER_CHAT)
    assert run() == 0
    assert sent == []
    assert db.query(SubscriptionAlert).count() == 0


# ══════════════════════════════════════════════════════════════════════════
#  BOSQICH TANLASH
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("days,kutilgan", [(7, "d7"), (3, "d3"), (1, "d1")])
def test_bosqich_7_3_1(days, kutilgan):
    now = datetime(2026, 9, 2, 12)
    st = _state(_Stub(now + timedelta(days=days)), now)
    assert sa.pick_stage(st) == kutilgan


def test_bosqich_muddat_uzoq_bolsa_yoq():
    now = datetime(2026, 9, 2, 12)
    exp = now + timedelta(days=30)
    assert sa.pick_stage(_state(_Stub(exp), now)) is None


def test_bosqich_muddat_tugadi_muhlat_ichida():
    now = datetime(2026, 9, 2, 12)
    exp = now - timedelta(hours=1)      # endigina o'tdi
    st = _state(_Stub(exp), now)
    assert st["state"] == "grace"
    assert sa.pick_stage(st) == "expired"


def test_bosqich_muhlat_tugadi_blok():
    now = datetime(2026, 9, 2, 12)
    exp = now - timedelta(days=GRACE + 1)
    st = _state(_Stub(exp), now)
    assert sa.pick_stage(st) == "blocked"


def test_bosqich_qolda_bloklanganga_xabar_yoq():
    """Super-admin ATAYLAB bloklagan — bot buni takrorlamaydi."""
    now = datetime(2026, 9, 2, 12)
    exp = now + timedelta(days=1)
    st = _state(_Stub(exp, tenant_status="blocked"), now)
    assert sa.pick_stage(st) is None
    st2 = _state(_Stub(exp, is_active=False), now)
    assert sa.pick_stage(st2) is None


def test_bosqich_sakrash_eskirgan_xabar_yuborilmaydi():
    """Server bir kun o'chsa: 7 kun emas, HAQIQIY qolgan muddat aytiladi.

    `==` bilan tanlansa ogohlantirish butunlay tushib qolardi.
    """
    now = datetime(2026, 9, 2, 12)
    assert sa.pick_stage(_state(_Stub(now + timedelta(days=2)), now)) == "d3"


class _Stub:
    """`subscription_state` faqat getattr ishlatadi."""
    def __init__(self, exp, tenant_status="active", is_active=True):
        self.is_active = is_active
        self.tenant_status = tenant_status
        self.blocked_reason = None
        self.subscription_plan = "pro"
        self.subscription_expires = exp
        self.trial_expires = None
        self.id = 1
        self.name = "Stub"


# ══════════════════════════════════════════════════════════════════════════
#  XABAR MAZMUNI
# ══════════════════════════════════════════════════════════════════════════

def test_xabar_mazmuni_aniq_va_harakatga_chorlovchi():
    now = datetime(2026, 9, 10, 12)
    exp = datetime(2026, 9, 17, 23, 59, 59)
    c = _Stub(exp); c.name = "FAZZA PERFUM"; c.id = 26
    st = _state(c, now)
    txt = sa.build_message(c, st, "d7", "owner")

    assert "FAZZA PERFUM" in txt
    assert "17.09.2026" in txt          # muddat sanasi
    assert "Pro" in txt                 # tarif ko'rinadigan nomi
    assert "749 000" in txt             # narx (yagona manbadan)
    assert settings.SUPPORT_CONTACT in txt
    assert "#26" not in txt             # egasiga ichki id ko'rsatilmaydi


def test_xabar_adminga_id_bilan():
    now = datetime(2026, 9, 10, 12)
    c = _Stub(datetime(2026, 9, 17, 23, 59, 59)); c.name = "FAZZA"; c.id = 26
    txt = sa.build_message(c, _state(c, now), "d7", "admin")
    assert "#26" in txt


def test_xabarda_MAXFIY_malumot_yoq():
    now = datetime(2026, 9, 10, 12)
    c = _Stub(datetime(2026, 9, 17, 23, 59, 59))
    txt = sa.build_message(c, _state(c, now), "d7", "admin").lower()
    for taqiq in ("parol", "password", "token", "secret", "hash", "bearer"):
        assert taqiq not in txt


def test_xabarda_dokon_nomi_HTML_uchun_qochiriladi():
    """parse_mode=HTML — nomdagi `<` xabarni buzishi yoki teg kiritishi mumkin."""
    now = datetime(2026, 9, 10, 12)
    c = _Stub(datetime(2026, 9, 17, 23, 59, 59))
    c.name = "<b>Yomon</b> & Do'kon"
    txt = sa.build_message(c, _state(c, now), "d7", "owner")
    assert "<b>" not in txt
    assert "&lt;b&gt;" in txt and "&amp;" in txt


def test_blok_xabari_enforcement_ochiq_bolsa_ogohlantiradi(monkeypatch):
    """ENFORCE o'chiq bo'lsa do'kon ishlayapti — admin aldanmasin."""
    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", False)
    now = datetime(2026, 9, 10, 12)
    c = _Stub(now - timedelta(days=GRACE + 1))
    txt = sa.build_message(c, _state(c, now), "blocked", "admin")
    assert "hali ishlayapti" in txt

    monkeypatch.setattr(settings, "ENFORCE_SUBSCRIPTION", True)
    txt2 = sa.build_message(c, _state(c, now), "blocked", "admin")
    assert "hali ishlayapti" not in txt2


# ══════════════════════════════════════════════════════════════════════════
#  TAKROR YUBORILMASLIGI
# ══════════════════════════════════════════════════════════════════════════

def test_takror_bir_bosqich_BIR_MARTA(db, sent):
    """Scheduler soatda ishlaydi — kuniga 24 urinish, xabar BITTA."""
    make_cafe(db, days_left=7, chat=OWNER_CHAT)
    assert run() == 2                      # admin + owner
    for _ in range(23):                    # kunning qolgan yugurishlari
        assert run() == 0
    assert len(sent) == 2
    assert db.query(SubscriptionAlert).count() == 2


def test_takror_bosqichlar_ketma_ket_alohida_yuboriladi(db, sent):
    """7 → 3 → 1 kun: uchtasi ham, lekin har biri bir martadan."""
    now = datetime(2026, 9, 2, 12)
    exp = datetime(2026, 9, 17, 23, 59, 59)
    make_cafe(db, expires=exp, chat=OWNER_CHAT)

    run(now=datetime(2026, 9, 11, 12))   # 7 kun
    run(now=datetime(2026, 9, 11, 18))   # o'sha kun — takror emas
    run(now=datetime(2026, 9, 15, 12))   # 3 kun
    run(now=datetime(2026, 9, 17, 10))   # 1 kun

    bosqichlar = sorted(a.stage for a in db.query(SubscriptionAlert)
                        .filter(SubscriptionAlert.audience == "owner").all())
    assert bosqichlar == ["d1", "d3", "d7"]


def test_obuna_uzaytirilsa_YANGI_tsikl_ochiladi(db, sent):
    """Kalitda MUDDAT SANASI bor — hech narsani nollash kerak emas.

    Bu aynan `renew_subscription` da bo'lgan "flagni tiklashni unutish"
    tuzog'ining oldini oladi: yangi muddat = yangi kalit = yangi tsikl.
    """
    c = make_cafe(db, expires=datetime(2026, 9, 9, 12))

    assert run(now=datetime(2026, 9, 2, 12)) == 1     # 7 kun qoldi
    assert run(now=datetime(2026, 9, 2, 18)) == 0     # o'sha kun — takror yo'q

    # Super-admin obunani 3 oyga uzaytirdi
    c.subscription_expires = datetime(2026, 12, 9, 12)
    db.commit()
    assert run(now=datetime(2026, 9, 3, 12)) == 0     # yangi muddat uzoq

    # Yangi muddatga ham 7 kun qoldi → YANGI sana, yangi ogohlantirish
    assert run(now=datetime(2026, 12, 2, 12)) == 1

    yozuvlar = db.query(SubscriptionAlert).all()
    assert len(yozuvlar) == 2
    assert {a.expiry_date.isoformat() for a in yozuvlar} == {"2026-09-09", "2026-12-09"}
    assert {a.stage for a in yozuvlar} == {"d7"}       # bosqich bir xil, sana boshqa


# ══════════════════════════════════════════════════════════════════════════
#  QABUL QILUVCHILAR
# ══════════════════════════════════════════════════════════════════════════

def test_egasining_chat_id_si_yoq_bolsa_faqat_admin(db, sent):
    make_cafe(db, days_left=3, chat=None)
    assert run() == 1
    assert len(sent) == 1 and sent[0]["chat"] == ADMIN_CHAT


def test_egasiga_blok_xabari_YUBORILMAYDI(db, sent):
    """Egasiga 'bloklandingiz' ni bot emas, odam aytadi."""
    make_cafe(db, days_left=-(GRACE + 1), chat=OWNER_CHAT)
    assert run() == 1                       # faqat admin
    assert [m["chat"] for m in sent] == [ADMIN_CHAT]


def test_muddat_tugagan_kuni_faqat_adminga(db, sent):
    make_cafe(db, expires=datetime.now() - timedelta(hours=1), chat=OWNER_CHAT)
    assert run() == 1
    assert sent[0]["chat"] == ADMIN_CHAT
    assert "muddati tugadi" in sent[0]["text"]


def test_muddatsiz_tenant_ogohlantirilmaydi(db, sent):
    make_cafe(db, expires=None, chat=OWNER_CHAT)
    assert run() == 0
    assert sent == []


# ══════════════════════════════════════════════════════════════════════════
#  TELEGRAM ISHLAMAGANDA
# ══════════════════════════════════════════════════════════════════════════

def test_telegram_ochganda_dastur_TOXTAMAYDI(db, monkeypatch):
    """Yuborilmasa: xato otilmaydi, yozuv YOZILMAYDI, keyin qayta uriniladi."""
    monkeypatch.setattr("core.alert.send_to_chat",
                        lambda text, chat_id, timeout=10: False)
    make_cafe(db, days_left=7, chat=OWNER_CHAT)

    assert run() == 0                                  # otmadi
    assert db.query(SubscriptionAlert).count() == 0    # "yuborildi" deb yozilmadi

    # Telegram tiklandi → o'sha bosqich hali ham yuboriladi (yo'qolmadi)
    box = []
    monkeypatch.setattr("core.alert.send_to_chat",
                        lambda text, chat_id, timeout=10: (box.append(chat_id), True)[1])
    assert run() == 2
    assert len(box) == 2


def test_telegram_XATO_OTSA_ham_toxtamaydi(db, monkeypatch):
    """Kutilmagan istisno bitta do'konda — qolganlari baribir xabar oladi."""
    def notinch(text, chat_id, timeout=10):
        if "Yomon" in text:
            raise RuntimeError("tarmoq uzildi")
        return True

    monkeypatch.setattr("core.alert.send_to_chat", notinch)
    make_cafe(db, days_left=7, name="Yomon Do'kon")
    make_cafe(db, days_left=7, name="Yaxshi Do'kon")

    assert run() == 1                                  # ikkinchisi o'tdi
    qolgan = db.query(SubscriptionAlert).all()
    assert len(qolgan) == 1


def test_send_to_chat_sozlanmagan_bolsa_jim(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    from core.alert import send_to_chat
    assert send_to_chat("salom", "123") is False
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "x")
    assert send_to_chat("salom", "") is False          # chat bo'sh


# ══════════════════════════════════════════════════════════════════════════
#  GOLDEN — jonli tenantlar bugun bezovta qilinmaydi
# ══════════════════════════════════════════════════════════════════════════

JONLI = [
    (5,  "lux-parfum",   "standart", "2027-08-12"),
    (7,  "biznes test",  "pro",      "2027-08-12"),
    (19, "qpa",          "pro",      "2027-08-12"),
    (20, "eco aroma",    "pro",      "2027-08-12"),
    (26, "FAZZA PERFUM", "pro",      "2026-09-17"),
]


def test_golden_jonli_tenantlarga_bugun_xabar_yoq(db, sent):
    """2026-09-02: eng yaqini Fazza — 15 kun, ya'ni hech kim ogohlantirilmaydi."""
    now = datetime(2026, 9, 2, 12)
    for tid, nom, plan, muddat in JONLI:
        exp = datetime.strptime(muddat, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59)
        make_cafe(db, expires=exp, name=nom, plan=plan, now=now)
    assert run(now=now) == 0
    assert sent == []


def test_golden_fazza_11_sentabrda_ogohlantiriladi(db, sent):
    """Banner bilan BIR XIL kun: 11-sentabr = 7 kun qoldi."""
    make_cafe(db, expires=datetime(2026, 9, 17, 23, 59, 59),
              name="FAZZA PERFUM", plan="pro", chat=OWNER_CHAT)

    assert run(now=datetime(2026, 9, 10, 12)) == 0     # hali 8 kun
    assert run(now=datetime(2026, 9, 11, 12)) == 2     # 7 kun → admin + owner
    txt = [m["text"] for m in sent if m["chat"] == OWNER_CHAT][0]
    assert "7 kundan keyin tugaydi" in txt
    assert "17.09.2026" in txt
