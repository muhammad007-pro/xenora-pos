"""Login: do'kon kodi hisob tenantiga mos kelishi tekshiriladi.

MUAMMO (2026-09-04, prod'da topilgan): login ekranida do'kon kodi terilardi-yu,
parol bilan kirishda u tekshirilmasdi. `100.200.3` (qpa) terilib, amalda
lux-parfum ochilardi — telefon o'sha tenantga bog'langani uchun. Ma'lumot
oqmasdi (izolyatsiya butun), lekin kod ma'nosiz va chalg'ituvchi edi.

Bu testlar to'rt narsani qulflaydi:
  1. To'g'ri kod → kiradi.
  2. Boshqa do'kon kodi → 403, xabar aniq ("Bu hisob {nom} ga tegishli emas").
  3. Kod umuman yuborilmasa → avvalgidek kiradi (⚠️ GOLDEN: tarqatilgan .exe /
     .apk / keshlangan PWA kod yubormaydi, ular buzilmasligi SHART).
  4. Super-admin ta'sirlanmaydi (u do'konga bog'lanmagan).
"""
import pytest

from core.security import get_password_hash
from tests.conftest import SEED_ADMIN_PASSWORD, SEED_ADMIN_PHONE

XODIM_PAROL = "DokonXodim9x"      # parol siyosatiga mos (8+, harf+raqam)
XODIM_PIN = "4417"


def _db():
    import database
    return database.SessionLocal()


@pytest.fixture(scope="module")
def ikki_dokon():
    """Ikki do'kon + birinchisiga bog'langan bitta xodim.

    Xodim FAQAT A do'koniga tegishli; B do'kon kodi bilan kirolmasligi kerak.
    """
    from models import Cafe, Role, User
    from core.security import hash_pin

    db = _db()
    try:
        a = db.query(Cafe).filter(Cafe.access_code == "900.100.1").first()
        if a is None:
            a = Cafe(name="Alfa do'kon", code="alfa-test", access_code="900.100.1",
                     business_type="store", is_active=True)
            db.add(a)
        b = db.query(Cafe).filter(Cafe.access_code == "900.100.2").first()
        if b is None:
            b = Cafe(name="Beta do'kon", code="beta-test", access_code="900.100.2",
                     business_type="store", is_active=True)
            db.add(b)
        db.commit()
        db.refresh(a)
        db.refresh(b)

        rol = db.query(Role).filter(Role.name == "admin").first()
        phone = "+998900001111"
        u = db.query(User).filter(User.phone == phone).first()
        if u is None:
            u = User(
                username="alfa_admin", email="alfa@test.local", full_name="Alfa Admin",
                phone=phone, hashed_password=get_password_hash(XODIM_PAROL),
                hashed_pin=hash_pin(XODIM_PIN),
                is_active=True, is_superuser=False,
                role_id=rol.id if rol else None, tenant_id=a.id,
            )
            db.add(u)
            db.commit()
        return {"a_id": a.id, "a_kod": a.access_code, "a_nom": a.name,
                "b_id": b.id, "b_kod": b.access_code, "b_nom": b.name,
                "telefon": phone}
    finally:
        db.close()


def _login(client, phone, parol, kod=None):
    data = {"username": phone, "password": parol}
    if kod is not None:
        data["access_code"] = kod
    return client.post("/api/v1/auth/login", data=data)


# ══════════════════════════════════════════════════════════════════════════
# PAROL BILAN KIRISH
# ══════════════════════════════════════════════════════════════════════════

def test_togri_kod_bilan_kiradi(client, ikki_dokon):
    r = _login(client, ikki_dokon["telefon"], XODIM_PAROL, ikki_dokon["a_kod"])
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


def test_boshqa_dokon_kodi_rad_etiladi(client, ikki_dokon):
    """⚠️ ASOSIY TUZATISH: parol to'g'ri, lekin kod boshqa do'konniki."""
    r = _login(client, ikki_dokon["telefon"], XODIM_PAROL, ikki_dokon["b_kod"])
    assert r.status_code == 403, r.text
    xabar = r.json()["detail"]
    assert ikki_dokon["b_nom"] in xabar, f"xabar do'kon nomini aytmadi: {xabar}"
    assert "tegishli emas" in xabar, xabar


def test_yoq_kod_400(client, ikki_dokon):
    """Mavjud bo'lmagan kod — 'do'kon topilmadi' ma'nosida 400."""
    r = _login(client, ikki_dokon["telefon"], XODIM_PAROL, "900.999.9")
    assert r.status_code == 400, r.text
    assert "kodi" in r.json()["detail"].lower()


def test_kodsiz_login_avvalgidek_ishlaydi(client, ikki_dokon):
    """⚠️ GOLDEN: eski klientlar (.exe/.apk/keshlangan PWA) kod yubormaydi.

    Ular bir kechada sinmasligi uchun kod IXTIYORIY. Bu test o'sha shartnomani
    qulflaydi — kelajakda "kodni majburiy qilamiz" degan o'zgarish shu yerda
    yiqiladi va odam qaror qabul qiladi.
    """
    r = _login(client, ikki_dokon["telefon"], XODIM_PAROL)          # kod umuman yo'q
    assert r.status_code == 200, r.text
    r2 = _login(client, ikki_dokon["telefon"], XODIM_PAROL, "")      # bo'sh kod
    assert r2.status_code == 200, r2.text


def test_notogri_parol_baribir_401(client, ikki_dokon):
    """Kod to'g'ri bo'lsa ham parol noto'g'ri bo'lsa — 401.

    Tartib muhim: kod tekshiruvi paroldan KEYIN. Aks holda "bu do'konda bunday
    telefon bor" degan ma'lumot parolsiz ochilardi.
    """
    r = _login(client, ikki_dokon["telefon"], "XatoParol9x", ikki_dokon["a_kod"])
    assert r.status_code == 401, r.text


def test_super_admin_tasirlanmaydi(client, ikki_dokon):
    """Super-admin do'konga bog'lanmagan — kod bilan ham, kodsiz ham kiradi."""
    r = _login(client, SEED_ADMIN_PHONE, SEED_ADMIN_PASSWORD)
    assert r.status_code == 200, r.text

    # Kod yuborilsa ham to'sib qo'yilmasin (u istalgan do'konga kira oladi)
    r2 = _login(client, SEED_ADMIN_PHONE, SEED_ADMIN_PASSWORD, ikki_dokon["b_kod"])
    assert r2.status_code == 200, r2.text


# ══════════════════════════════════════════════════════════════════════════
# PIN BILAN KIRISH — allaqachon tenant ichida qidiradi, xulq o'zgarmadi
# ══════════════════════════════════════════════════════════════════════════

def test_pin_togri_kod_bilan_kiradi(client, ikki_dokon):
    r = client.post("/api/v1/auth/pin-login",
                    json={"pin": XODIM_PIN, "access_code": ikki_dokon["a_kod"]})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


def test_pin_boshqa_dokon_kodi_bilan_kirmaydi(client, ikki_dokon):
    """PIN qidiruvi tenant ichida — B do'konda bu PIN yo'q, ya'ni 401.

    ⚠️ XABAR ATAYLAB UMUMIY ("PIN noto'g'ri"), parol yo'lidagidek aniq emas:
    PIN'da hech qanday parol tasdiqlanmagan, shuning uchun "bu PIN Alfa
    do'koniga tegishli" deyish begona odamga ma'lumot berardi.
    """
    r = client.post("/api/v1/auth/pin-login",
                    json={"pin": XODIM_PIN, "access_code": ikki_dokon["b_kod"]})
    assert r.status_code == 401, r.text


def test_pin_yoq_kod_400(client, ikki_dokon):
    r = client.post("/api/v1/auth/pin-login",
                    json={"pin": XODIM_PIN, "access_code": "900.999.9"})
    assert r.status_code == 400, r.text


def test_pin_kodsiz_rad_etiladi(client, ikki_dokon):
    """Kodsiz PIN — global qidiruvga yo'l yo'q (avvaldan shunday)."""
    r = client.post("/api/v1/auth/pin-login", json={"pin": XODIM_PIN})
    assert r.status_code == 400, r.text
