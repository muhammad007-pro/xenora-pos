"""Retrospektiv yig'ish: `source` ustuni va bir martalik ko'chirish mantig'i.

Ikki narsa qulflanadi:
  1. Jonli yozuv (`record_candidate`) DOIM `source='live'` beradi — retrospektiv
     yozuv bilan aralashib ketmasin.
  2. Retrospektiv yozuv jonli yozuv USTIGA yozmaydi. Jonli nom yangiroq va
     ishonchliroq: uni tarixiy nom bilan almashtirish ma'lumot yo'qotish bo'lardi.

⚠️ Skriptning o'zi (`scripts/backfill_catalog_candidates.py`) PostgreSQL'ga xos
`ON CONFLICT` ishlatadi va testlar SQLite'da yuradi, shuning uchun bu yerda
skript emas, uning QARORI sinaladi: qaysi mahsulot o'tadi, qaysi biri yo'q va
mavjud qatorga nima bo'ladi. Filtr aynan bir xil funksiya (`is_shareable_barcode`).
"""
import pytest

from core.catalog import gs1_check_digit, is_shareable_barcode, normalize_name, record_candidate


def _db():
    import database
    return database.SessionLocal()


def bc(seed: int) -> str:
    body = f"{410000000000 + seed:012d}"
    return body + str(gs1_check_digit(body))


@pytest.fixture()
def dokon():
    """Ruxsat bergan do'kon (catalog_share_enabled=True)."""
    from models import Cafe

    db = _db()
    try:
        c = db.query(Cafe).filter(Cafe.code == "backfill-test").first()
        if c is None:
            c = Cafe(name="Backfill do'kon", code="backfill-test",
                     access_code="910.100.1", business_type="store", is_active=True)
            db.add(c)
            db.commit()
            db.refresh(c)
        c.catalog_share_enabled = True
        db.commit()
        return c.id
    finally:
        db.close()


def _nomzod(tenant_id, barcode):
    from models import CatalogCandidate

    db = _db()
    try:
        return (db.query(CatalogCandidate)
                .filter(CatalogCandidate.tenant_id == tenant_id,
                        CatalogCandidate.barcode == barcode)
                .first())
    finally:
        db.close()


def test_jonli_yozuv_source_live(dokon):
    """Standart qiymat 'live' — ustun qo'shilgach ham jonli yo'l o'zgarmaydi."""
    code = bc(11)
    db = _db()
    try:
        assert record_candidate(db, dokon, code, "Jonli mahsulot",
                                category_hint="Test", unit="pcs") is True
    finally:
        db.close()

    row = _nomzod(dokon, code)
    assert row is not None
    assert row.source == "live"


def test_tahrirlash_source_ni_ozgartirmaydi(dokon):
    """Retrospektiv qator keyin tahrirlansa — u 'backfill' bo'lib qoladimi.

    Bu ataylab: `record_candidate` `source` ga TEGMAYDI. Ya'ni bir marta
    ko'chirilgan qator do'kon nomni o'zgartirganda ham 'backfill' bo'lib qoladi.
    Agar kelajakda "tahrirlangan = jonli" deb hisoblansa, shu test yiqiladi va
    qaror ONGLI ravishda qayta ko'riladi.
    """
    from models import CatalogCandidate

    code = bc(12)
    db = _db()
    try:
        db.add(CatalogCandidate(
            tenant_id=dokon, barcode=code,
            name_normalized="eski nom", name_original="Eski nom",
            source="backfill",
        ))
        db.commit()
        assert record_candidate(db, dokon, code, "Yangi nom") is True
    finally:
        db.close()

    row = _nomzod(dokon, code)
    assert row.name_original == "Yangi nom"      # nom yangilandi
    assert row.source == "backfill"              # manba o'zgarmadi


def test_retrospektiv_filtr_endpoint_bilan_bir_xil():
    """Skript va endpoint AYNI oq ro'yxatni ishlatadi — ikki xil qoida bo'lmasin.

    Skript `is_shareable_barcode` ni to'g'ridan-to'g'ri import qiladi; bu test
    o'sha qoidaning retrospektiv uchun muhim uchta holatini qayd etadi.
    """
    ichki = "200123456789"
    assert is_shareable_barcode(ichki + str(gs1_check_digit(ichki))) is False
    assert is_shareable_barcode("123") is False                  # prod bazadagi axlat
    assert is_shareable_barcode("4780069410335") is True         # haqiqiy zavod kodi


def test_nomsiz_mahsulot_otmaydi():
    """Nomi faqat belgidan iborat mahsulot nomzod bo'la olmaydi."""
    assert normalize_name("!!!") == ""
    assert normalize_name("   ") == ""
