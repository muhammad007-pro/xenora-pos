"""Umumiy katalog — YIG'ISH qatlami testi (o'qish API'si yo'q).

Bu testlar uchta narsani qulflaydi:

  1. **Oq ro'yxat** — ichki kod (prefiks 2), buzuq checksum va axlat kodlar
     katalogga TUSHMAYDI. Bu eng muhim shart: ichki kodlar do'konga xos, ular
     umumiy katalogni zaharlaydi.
  2. **Ruxsat** — `catalog_share_enabled=False` bo'lsa hech narsa yozilmaydi.
     Standart holat aynan shu.
  3. **GOLDEN** — mavjud mahsulot yaratish/tahrirlash oqimi buzilmaydi va
     katalog qatlami yiqilsa ham mahsulot yaratish TO'XTAMAYDI.
"""
import time

import pytest

from core.catalog import (
    gs1_check_digit,
    is_shareable_barcode,
    normalize_name,
    record_candidate,
)
from utils.helpers import calculate_ean13_checksum


# ══════════════════════════════════════════════════════════════════════════
# 1) OQ RO'YXAT — sof funksiya testlari (bazasiz, tez)
# ══════════════════════════════════════════════════════════════════════════

def test_checksum_ean13_bilan_bir_xil():
    """`gs1_check_digit` EAN-13 uchun mavjud helper bilan AYNAN bir xil.

    Ikki xil checksum mantiqи paydo bo'lsa, oq ro'yxat bir kodni qabul qilib,
    generator boshqasini yaratardi. Shu ikkisini bir-biriga qulflaymiz.
    """
    for base12 in ("478006941033", "880104643439", "460712345678", "000000000000"):
        assert gs1_check_digit(base12) == calculate_ean13_checksum(base12), base12


@pytest.mark.parametrize("code", [
    "4780069410335",   # EAN-13, O'zbekiston (prod bazadan, haqiqiy)
    "8801046434390",   # EAN-13, Koreya (prod bazadan, haqiqiy)
    "4780083293051",   # EAN-13
    "0123456789012",   # EAN-13, nol bilan boshlanadi
])
def test_zavod_ean13_qabul_qilinadi(code):
    assert is_shareable_barcode(code) is True


def test_upc_a_va_ean8_qabul_qilinadi():
    """12 va 8 raqamli zavod kodlari ham yaroqli (prod bazada 24 ta bor)."""
    upc = "03600029145"          # 11 raqamli tana
    upc += str(gs1_check_digit(upc))
    assert len(upc) == 12 and is_shareable_barcode(upc) is True

    ean8 = "9638507"             # 7 raqamli tana
    ean8 += str(gs1_check_digit(ean8))
    assert len(ean8) == 8 and is_shareable_barcode(ean8) is True


def test_ichki_kod_prefiks_2_rad_etiladi():
    """⚠️ ENG MUHIM SHART: `core/barcode.py` yaratgan ichki kodlar tushmaydi.

    Ular do'kon ICHIDA unikal, lekin ikki do'kon bir kodni ikki xil mahsulotga
    beradi. Checksum TO'G'RI bo'lsa ham rad etilishi kerak — ya'ni test kodni
    haqiqiy generator qoidasi bo'yicha quradi.
    """
    for prefix in ("20", "29", "21", "25"):
        body = prefix + "0123456789"          # 12 raqamli tana
        code = body + str(gs1_check_digit(body))
        assert len(code) == 13
        assert gs1_check_digit(code[:-1]) == int(code[-1]), "test kodi o'zi buzuq"
        assert is_shareable_barcode(code) is False, code

    # 12 va 8 raqamli "2..." kodlar ham do'kon ichki kodi (og'irlik yorlig'i)
    for body in ("20123456789", "2012345"):
        code = body + str(gs1_check_digit(body))
        assert is_shareable_barcode(code) is False, code


def test_buzuq_checksum_rad_etiladi():
    good = "4780069410335"
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    assert is_shareable_barcode(good) is True
    assert is_shareable_barcode(bad) is False


@pytest.mark.parametrize("code", [
    None, "", "   ",
    "123",                       # prod bazada bor: 3 raqamli "kod"
    "798165116",                 # 9 raqamli
    "12345678901234",            # 14 raqamli
    "12345678901234567890123456",  # 26 belgili
    "ABC12345",                  # harfli
    "478-0069-410335",           # tire bilan
])
def test_axlat_kodlar_rad_etiladi(code):
    assert is_shareable_barcode(code) is False


# ══════════════════════════════════════════════════════════════════════════
# 2) NORMALIZATSIYA
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("a,b", [
    ("NIVEA", "nivea"),                       # registr
    ("coca  cola", "coca cola"),              # ortiqcha bo'shliq
    (" Kerasys ", "kerasys"),                 # chet bo'shliq
    ("Coca-Cola 0.5", "coca cola 0 5"),       # tire va nuqta
    ("0,5L", "0 5l"),                         # vergul
    ("o'simlik", "osimlik"),                  # to'g'ri apostrof
    ("o‘simlik", "osimlik"),                  # burchakli apostrof
    ("oʻsimlik", "osimlik"),                  # o'zbek harfi
    ("Шампунь", "shampun"),                   # kirill → lotin
    ("ЙОД", "yod"),
    ("Ўзбекистон", "ozbekiston"),             # o'zbek kirill ў
])
def test_normalizatsiya(a, b):
    assert normalize_name(a) == b


def test_lotin_va_kirill_bir_kalitga_tushadi():
    assert normalize_name("Шампунь") == normalize_name("shampun")
    assert normalize_name("КЕРАСИС") == normalize_name("kerasis")


def test_bosh_nom_bosh_kalit():
    assert normalize_name(None) == ""
    assert normalize_name("   ") == ""
    assert normalize_name("!!!") == ""


# ══════════════════════════════════════════════════════════════════════════
# 3) INTEGRATSIYA — haqiqiy endpoint orqali
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def cafe_id():
    """Yagona faol kafe — `resolve_tenant_id` uni tanlaydi (deps.py:153)."""
    import database
    from models import Cafe

    db = database.SessionLocal()
    try:
        cafe = db.query(Cafe).filter(Cafe.is_active == True).first()
        if cafe is None:
            cafe = Cafe(name="Test do'kon", code="testshop",
                        business_type="store", is_active=True)
            db.add(cafe)
            db.commit()
            db.refresh(cafe)
        return cafe.id
    finally:
        db.close()


def _set_share(cafe_id, value):
    import database
    from models import Cafe

    db = database.SessionLocal()
    try:
        db.query(Cafe).filter(Cafe.id == cafe_id).update(
            {Cafe.catalog_share_enabled: value})
        db.commit()
    finally:
        db.close()


def _candidates(cafe_id, barcode=None):
    import database
    from models import CatalogCandidate

    db = database.SessionLocal()
    try:
        q = db.query(CatalogCandidate).filter(CatalogCandidate.tenant_id == cafe_id)
        if barcode:
            q = q.filter(CatalogCandidate.barcode == barcode)
        return q.all()
    finally:
        db.close()


CATEGORY_NAME = "Katalog test kategoriya"


def bc(seed: int) -> str:
    """Sinov uchun HAQIQIY EAN-13 (nazorat raqami to'g'ri, prefiks 2 emas).

    ⚠️ Har testga UNIKAL kod kerak: test bazasi sessiya bo'yicha yagona va
    mahsulot barkodi tenant ichida UNIQUE — takroriy kod 400 "Bu barcode band"
    beradi (integratsiya testlari shunda yiqilardi).
    """
    body = f"{400000000000 + seed:012d}"   # 12 raqamli tana, "4" bilan boshlanadi
    assert len(body) == 12 and body[0] != "2"
    return body + str(gs1_check_digit(body))


@pytest.fixture()
def category_id(client, auth_headers):
    """Kategoriya — bor bo'lsa qayta ishlatiladi.

    Baza `setup_database` da sessiya bo'yicha bir marta yaratiladi, ya'ni
    ikkinchi test uni QAYTA yaratolmaydi ("Bu nomdagi kategoriya mavjud", 400).
    """
    r = client.post("/api/v1/categories/",
                    json={"name": CATEGORY_NAME}, headers=auth_headers)
    if r.status_code in (200, 201):
        return r.json()["id"]

    lst = client.get("/api/v1/categories/", headers=auth_headers)
    assert lst.status_code == 200, lst.text
    data = lst.json()
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    for c in items:
        if c["name"] == CATEGORY_NAME:
            return c["id"]
    raise AssertionError(f"kategoriya yaratilmadi ham, topilmadi ham: {r.text}")


def test_bayroq_ochiq_bolsa_umuman_yozilmaydi(client, auth_headers, category_id, cafe_id):
    """⚠️ STANDART HOLAT: ruxsat berilmagan do'kondan HECH NARSA yig'ilmaydi."""
    _set_share(cafe_id, False)
    barcode = bc(101)

    r = client.post("/api/v1/products/", json={
        "name": "Ruxsatsiz mahsulot", "price": 1000,
        "category_id": category_id, "barcode": barcode, "sale_unit": "pcs",
    }, headers=auth_headers)
    assert r.status_code in (200, 201), r.text

    assert _candidates(cafe_id, barcode) == []


def test_bayroq_yoqilganda_yoziladi(client, auth_headers, category_id, cafe_id):
    _set_share(cafe_id, True)
    barcode = bc(102)

    r = client.post("/api/v1/products/", json={
        "name": "  KOPUM PLUS 1.5 kg  ", "price": 25000,
        "category_id": category_id, "barcode": barcode, "sale_unit": "pcs",
    }, headers=auth_headers)
    assert r.status_code in (200, 201), r.text

    rows = _candidates(cafe_id, barcode)
    assert len(rows) == 1
    assert rows[0].name_normalized == "kopum plus 1 5 kg"
    assert rows[0].name_original == "KOPUM PLUS 1.5 kg"   # asl nom saqlanadi
    assert rows[0].unit == "pcs"
    assert rows[0].category_hint == "Katalog test kategoriya"
    # ⚠️ Narx ustuni sxemada YO'Q — kafolatni test ham qulflaydi
    assert not hasattr(rows[0], "price")
    assert not hasattr(rows[0], "cost_price")
    assert not hasattr(rows[0], "supplier_id")
    assert not hasattr(rows[0], "quantity")


def test_ichki_kodli_mahsulot_yozilmaydi(client, auth_headers, category_id, cafe_id):
    """Do'kon ichki kodli mahsulot yaratsa — mahsulot yaratiladi, nomzod yo'q."""
    _set_share(cafe_id, True)
    body = "200123456789"
    barcode = body + str(gs1_check_digit(body))

    r = client.post("/api/v1/products/", json={
        "name": "Ichki kodli atir", "price": 50000,
        "category_id": category_id, "barcode": barcode, "sale_unit": "ml",
    }, headers=auth_headers)
    assert r.status_code in (200, 201), r.text      # mahsulot YARATILDI
    assert _candidates(cafe_id, barcode) == []      # lekin nomzod YO'Q


def test_tahrirlash_yangi_qator_yaratmaydi(client, auth_headers, category_id, cafe_id):
    """Bir do'kon = bir ovoz. Tahrirlash mavjud qatorni YANGILAYDI."""
    _set_share(cafe_id, True)
    barcode = bc(103)

    r = client.post("/api/v1/products/", json={
        "name": "FAZZA", "price": 12000,
        "category_id": category_id, "barcode": barcode, "sale_unit": "pcs",
    }, headers=auth_headers)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    assert len(_candidates(cafe_id, barcode)) == 1

    r2 = client.patch(f"/api/v1/products/{pid}",
                      json={"name": "FAZZA PLUS kok"}, headers=auth_headers)
    assert r2.status_code == 200, r2.text

    rows = _candidates(cafe_id, barcode)
    assert len(rows) == 1, "tahrirlash yangi qator yaratdi — UNIQUE ishlamayapti"
    assert rows[0].name_original == "FAZZA PLUS kok"
    assert rows[0].name_normalized == "fazza plus kok"


def test_barkodsiz_mahsulot_yozilmaydi(client, auth_headers, category_id, cafe_id):
    _set_share(cafe_id, True)
    oldin = len(_candidates(cafe_id))

    r = client.post("/api/v1/products/", json={
        "name": "Barkodsiz mahsulot", "price": 3000,
        "category_id": category_id, "sale_unit": "pcs",
    }, headers=auth_headers)
    assert r.status_code in (200, 201), r.text
    assert len(_candidates(cafe_id)) == oldin


# ══════════════════════════════════════════════════════════════════════════
# 4) GOLDEN — mavjud oqim buzilmasin
# ══════════════════════════════════════════════════════════════════════════

def test_golden_katalog_yiqilsa_ham_mahsulot_yaratiladi(
        client, auth_headers, category_id, cafe_id, monkeypatch):
    """⚠️ GOLDEN: katalog qatlami butunlay sinsa ham mahsulot yaratilishi SHART.

    `record_candidate` ni ataylab yiqiladigan qilib almashtiramiz — endpoint
    baribir 200/201 qaytarishi kerak. Bu 3-band talabining ("xato bo'lsa
    mahsulot yaratish TO'XTAMASIN") to'g'ridan-to'g'ri tekshiruvi.
    """
    _set_share(cafe_id, True)

    import routers.product as product_router

    def _portlaydi(*a, **kw):
        raise RuntimeError("katalog qatlami ataylab yiqildi")

    monkeypatch.setattr(product_router, "record_candidate", _portlaydi)

    r = client.post("/api/v1/products/", json={
        "name": "Golden mahsulot", "price": 7000,
        "category_id": category_id, "barcode": bc(104), "sale_unit": "pcs",
    }, headers=auth_headers)
    assert r.status_code in (200, 201), (
        "katalog xatosi mahsulot yaratishni to'xtatdi — 3-band buzilgan: " + r.text)
    assert r.json()["name"] == "Golden mahsulot"


def test_golden_sessiya_buzilmaydi(client, auth_headers, category_id, cafe_id):
    """Katalog yozuvidan keyin sessiya ishlashda davom etadi (rollback to'g'ri).

    Nomzod yozuvi commit qiladi; agar u sessiyani buzsa, KEYINGI so'rov
    yiqilardi. Ketma-ket uchta amal — hammasi o'tishi kerak.
    """
    _set_share(cafe_id, True)
    for i, code in enumerate((bc(105), bc(106), bc(107))):
        r = client.post("/api/v1/products/", json={
            "name": f"Ketma-ket {i}", "price": 1000 + i,
            "category_id": category_id, "barcode": code, "sale_unit": "pcs",
        }, headers=auth_headers)
        assert r.status_code in (200, 201), f"{i}-so'rov yiqildi: {r.text}"

    r = client.get("/api/v1/products/", headers=auth_headers)
    assert r.status_code == 200


def test_qoshimcha_sorovlar_soni_chegaralangan(client, auth_headers, category_id, cafe_id):
    """Katalog qatlami mahsulot yaratishga nechta QO'SHIMCHA SQL qo'shadi.

    ⚠️ NEGA VAQT EMAS, SO'ROV SONI: devordagi vaqt SQLite/Windows'da bir so'rov
    uchun 280ms dan 2300ms gacha tebranadi — nisbat testi shovqinda yiqiladi va
    hech narsani isbotlamaydi. So'rov soni esa determinlashgan va aynan
    xavflisini ushlaydi: tasodifiy N+1 yoki indekssiz qidiruv kirib qolsa.

    Kutilgan qo'shimcha: 1 SELECT cafes (bayroq) + 1 SELECT catalog_candidates
    (mavjudmi) + 1 INSERT + tranzaksiya xizmat so'rovlari.
    """
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    hisob = {"n": 0}

    def _sana(conn, cursor, statement, params, context, executemany):
        hisob["n"] += 1

    event.listen(Engine, "after_cursor_execute", _sana)
    try:
        def _olch(bayroq, seed):
            _set_share(cafe_id, bayroq)
            hisob["n"] = 0
            r = client.post("/api/v1/products/", json={
                "name": f"So'rov {seed}", "price": 1000,
                "category_id": category_id, "barcode": bc(seed), "sale_unit": "pcs",
            }, headers=auth_headers)
            assert r.status_code in (200, 201), r.text
            return hisob["n"]

        ochiq = _olch(False, 3001)
        yoqiq = _olch(True, 3002)
    finally:
        event.remove(Engine, "after_cursor_execute", _sana)

    qoshimcha = yoqiq - ochiq
    assert 0 < qoshimcha <= 6, (
        f"katalog qatlami {qoshimcha} ta qo'shimcha SQL qo'shdi "
        f"(o'chiq {ochiq}, yoqiq {yoqiq}) — N+1 yoki ortiqcha so'rov kirdimi?")


def test_yigish_tezligi_bazaviy_sorovga_nisbatan(client, auth_headers, category_id, cafe_id):
    """Nomzod yozuvi oddiy SELECT'dan necha barobar sekin.

    ⚠️ IKKI XATO O'LCHOVDAN KEYINGI UCHINCHI URINISH — tarixi qoldirilgan,
    chunki xato o'lchov testdan ham yomonroq (u yolg'on tinchlik beradi):

      1-urinish, MUTLAQ VAQT (`ortacha < 0.25s`): YOLG'IZ o'tib, TO'PLAMDA
         yiqilardi — bir xil kod, bir xil baza. Sabab mashina yuklamasi:
         o'sha to'plam bir yugurishda 62s, boshqasida 248s davom etdi.
      2-urinish, ODDIY SELECT ga nisbatan: o'lchov 161x berdi (yozuv 207ms,
         SELECT 1.3ms). Bu ham noto'g'ri edi — 207ms ning deyarli hammasi
         `commit` (SQLite/Windows'da diskka fsync), so'rov emas. Commit
         qiladigan yozuvni commit qilmaydigan o'qish bilan solishtirib
         bo'lmaydi: nisbat kod sifatini emas, disk tezligini o'lchaydi.

    To'g'ri bazaviy — AYNI JADVALGA bitta oddiy INSERT + commit. Ikkalasi ham
    fsync to'laydi, ya'ni disk va yuklama qisqaradi; qolgan farq aynan
    `record_candidate` qo'shadigan ish (kafe qidiruvi + mavjud nomzod qidiruvi).
    Chegara 4x — indeks yo'qolsa yoki to'liq skan kirsa ushlanadi.

    Haqiqiy N+1 qo'riqchisi — yuqoridagi so'rov soni testi. Bu esa qo'shimcha
    qatlam: so'rov SONI to'g'ri bo'lib turib, so'rovning O'ZI sekinlashsa.
    """
    import database
    from models import CatalogCandidate

    _set_share(cafe_id, True)
    db = database.SessionLocal()
    try:
        N = 25
        # Bazaviy: yalang'och INSERT + commit (record_candidate'ning qidiruvlarisiz)
        boshlandi = time.perf_counter()
        for i in range(N):
            db.add(CatalogCandidate(
                tenant_id=cafe_id, barcode=bc(5000 + i),
                name_normalized=f"bazaviy {i}", name_original=f"Bazaviy {i}",
            ))
            db.commit()
        bazaviy = (time.perf_counter() - boshlandi) / N

        boshlandi = time.perf_counter()
        for i in range(N):
            record_candidate(db, cafe_id, bc(4000 + i), f"Tezlik mahsulot {i}",
                             category_hint="Test", unit="pcs")
        yozuv = (time.perf_counter() - boshlandi) / N
    finally:
        db.close()

    nisbat = yozuv / max(bazaviy, 1e-6)
    assert nisbat < 4, (
        f"nomzod yozuvi yalang'och INSERT'dan {nisbat:.1f}x sekin "
        f"(yozuv {yozuv*1000:.1f}ms, bazaviy {bazaviy*1000:.1f}ms) — "
        f"indeks yo'qoldimi yoki to'liq skan kirdimi?")
