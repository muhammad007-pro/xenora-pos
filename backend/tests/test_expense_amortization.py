"""XARAJATNI KUNLARGA TAQSIMLASH — matematika + regressiya testlari.

MUAMMO (Fazza Parfum, 2026-08): ARENDA 1.8M + ISHCHI 2.5M + UJN 1.5M
uchalasi ham `expense_date = 22-avgust` bo'lgani uchun 5 800 000 BITTA KUNGA
tushdi va o'sha kun sof foydasi −5 268 070 bo'lib ko'rindi. Aslida bu oylik
xarajat.

Bu fayl uchta narsani QOTIRADI:
  1) MATEMATIKA — yaxlitlash bir tiyin ham yo'qolmaydi/qo'shilmaydi
  2) REGRESSIYA — taqsimlanmagan xarajat (amortize NULL) AVVALGIDEK ishlaydi
  3) GOLDEN — Fazza avgust ssenariysi: oy jami O'ZGARMAYDI, 22-avgust esa
     endi minus emas

Ishga tushirish:  cd backend && py -m pytest tests/test_expense_amortization.py -v
"""
import os
import sys
from datetime import date as Date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Cafe, Expense
from services.expense_allocation import (
    breakdown_in_range, by_bucket, is_amortized, month_bounds,
    share_in_range, total_in_range,
)


class _User:
    is_superuser = False
    tenant_id = 1
    id = 1
    role = None


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Cafe(id=1, name="Fazza", code="FAZZA"))
    s.commit()
    yield s
    s.close()


def _exp(db, amount, d, am_from=None, am_to=None, name="X"):
    e = Expense(tenant_id=1, category="rent", name=name, amount=amount,
                expense_date=d, amortize_from=am_from, amortize_to=am_to)
    db.add(e); db.commit(); db.refresh(e)
    return e


AUG1, AUG31 = Date(2026, 8, 1), Date(2026, 8, 31)


# ═══════════════════════════════════════════════════════════════════════════
# 1. MATEMATIKA — yaxlitlash
# ═══════════════════════════════════════════════════════════════════════════
def test_butun_davr_yigindisi_aynan_amount(db):
    """1 tiyin ham farq bo'lmasin — bo'linmaydigan summa bilan."""
    e = _exp(db, 1_000_000, AUG1, AUG1, Date(2026, 8, 30))   # 30 kun
    assert share_in_range(e, AUG1, Date(2026, 8, 30)) == 1_000_000.0
    # kunma-kun yig'ish ham AYNAN o'sha summani berishi kerak
    kunlik = [share_in_range(e, AUG1 + timedelta(days=i), AUG1 + timedelta(days=i))
              for i in range(30)]
    assert round(sum(kunlik), 2) == 1_000_000.0
    assert len(kunlik) == 30


def test_bolinadigan_summa_teng_taqsimlanadi(db):
    e = _exp(db, 1_500_000, AUG1, AUG1, Date(2026, 8, 30))   # 30 kun
    for i in range(30):
        d = AUG1 + timedelta(days=i)
        assert share_in_range(e, d, d) == 50_000.0


def test_qoshni_oraliqlar_toliq_davrga_teng(db):
    """1–15 + 16–30 = to'liq davr. Bo'shliq ham, ustma-ustlik ham YO'Q."""
    e = _exp(db, 1_000_000, AUG1, AUG1, Date(2026, 8, 30))
    a = share_in_range(e, AUG1, Date(2026, 8, 15))
    b = share_in_range(e, Date(2026, 8, 16), Date(2026, 8, 30))
    assert round(a + b, 2) == 1_000_000.0
    # uch bo'lakka bo'lganda ham
    c = [share_in_range(e, AUG1, Date(2026, 8, 9)),
         share_in_range(e, Date(2026, 8, 10), Date(2026, 8, 19)),
         share_in_range(e, Date(2026, 8, 20), Date(2026, 8, 30))]
    assert round(sum(c), 2) == 1_000_000.0


def test_qism_oraliq_amountdan_oshmaydi(db):
    e = _exp(db, 1_000_000, AUG1, AUG1, Date(2026, 8, 30))
    for lo in range(0, 30, 7):
        for hi in range(lo, 30, 5):
            sh = share_in_range(e, AUG1 + timedelta(days=lo), AUG1 + timedelta(days=hi))
            assert 0 <= sh <= 1_000_000.0


def test_davrdan_tashqari_nol(db):
    e = _exp(db, 900_000, Date(2026, 8, 22), AUG1, AUG31)
    assert share_in_range(e, Date(2026, 7, 1), Date(2026, 7, 31)) == 0.0
    assert share_in_range(e, Date(2026, 9, 1), Date(2026, 9, 30)) == 0.0


def test_bir_kunlik_davr(db):
    e = _exp(db, 123_456.78, AUG1, AUG1, AUG1)
    assert share_in_range(e, AUG1, AUG1) == 123_456.78


def test_buzuq_davr_taqsimlanmagan_deb_qaraladi(db):
    """to < from — manfiy uzunlik. Nolga bo'lish o'rniga eski mantiq."""
    e = _exp(db, 500_000, Date(2026, 8, 22), AUG31, AUG1)
    assert is_amortized(e) is True          # maydonlar to'ldirilgan
    assert share_in_range(e, Date(2026, 8, 22), Date(2026, 8, 22)) == 500_000.0
    assert share_in_range(e, AUG1, Date(2026, 8, 21)) == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 2. REGRESSIYA — taqsimlanmagan xarajat O'ZGARMAYDI
# ═══════════════════════════════════════════════════════════════════════════
def test_regressiya_amortize_null_eski_xatti_harakat(db):
    e = _exp(db, 5_800_000, Date(2026, 8, 22))
    assert is_amortized(e) is False
    assert share_in_range(e, Date(2026, 8, 22), Date(2026, 8, 22)) == 5_800_000.0
    assert share_in_range(e, Date(2026, 8, 21), Date(2026, 8, 21)) == 0.0
    assert total_in_range(db, _User(), AUG1, AUG31) == 5_800_000.0


def test_regressiya_aralash_taqsimlangan_va_oddiy(db):
    _exp(db, 1_500_000, Date(2026, 8, 22), AUG1, AUG31, name="ARENDA")  # taqsimlangan
    _exp(db, 200_000, Date(2026, 8, 10), name="TRANSPORT")              # oddiy
    # Oy jami — ikkalasi to'liq
    assert total_in_range(db, _User(), AUG1, AUG31) == 1_700_000.0
    # 10-avgust: taqsimlangan ulush + oddiy to'liq
    d10 = share_in_range(db.query(Expense).filter(Expense.name == "ARENDA").one(),
                         Date(2026, 8, 10), Date(2026, 8, 10))
    assert total_in_range(db, _User(), Date(2026, 8, 10), Date(2026, 8, 10)) == round(d10 + 200_000, 2)


# ═══════════════════════════════════════════════════════════════════════════
# 3. GOLDEN — Fazza avgust ssenariysi
# ═══════════════════════════════════════════════════════════════════════════
def test_GOLDEN_fazza_oy_jami_ozgarmaydi_22avgust_minus_emas(db):
    """Jonli holat: 22-avgustda 3 ta xarajat, jami 5 800 000."""
    _exp(db, 1_800_000, Date(2026, 8, 22), AUG1, AUG31, name="ARENDA")
    _exp(db, 2_500_000, Date(2026, 8, 22), AUG1, AUG31, name="ISHCHI")
    _exp(db, 1_500_000, Date(2026, 8, 22), AUG1, AUG31, name="UJN")

    # (a) OY JAMI — bir tiyin ham o'zgarmaydi
    assert total_in_range(db, _User(), AUG1, AUG31) == 5_800_000.0

    # (b) kunma-kun yig'indisi ham AYNAN o'sha
    kunlik = [total_in_range(db, _User(), AUG1 + timedelta(days=i), AUG1 + timedelta(days=i))
              for i in range(31)]
    assert round(sum(kunlik), 2) == 5_800_000.0

    # (c) 22-avgust endi 5.8M emas, ~1/31 ulush
    kun22 = total_in_range(db, _User(), Date(2026, 8, 22), Date(2026, 8, 22))
    assert 187_000 <= kun22 <= 187_200          # 5 800 000 / 31 ≈ 187 096.77
    assert kun22 < 200_000

    # (d) 22-avgust yalpi foyda +531 930 edi -> endi MUSBAT
    assert 531_930 - kun22 > 0

    # (e) har bir kun bir xil (31 ga teng bo'linmaydi -> 1 tiyin farq bo'lishi mumkin)
    assert max(kunlik) - min(kunlik) <= 0.05


def test_GOLDEN_avgust_yalpi_minus_xarajat(db):
    """Oy bo'yicha sof foyda o'zgarmasligi: 7 079 540 − 5 800 000 = 1 279 540."""
    _exp(db, 1_800_000, Date(2026, 8, 22), AUG1, AUG31)
    _exp(db, 2_500_000, Date(2026, 8, 22), AUG1, AUG31)
    _exp(db, 1_500_000, Date(2026, 8, 22), AUG1, AUG31)
    yalpi = 7_079_540                       # jonli bazadan (oylik yalpi foyda)
    assert round(yalpi - total_in_range(db, _User(), AUG1, AUG31), 0) == 1_279_540


# ═══════════════════════════════════════════════════════════════════════════
# 4. Bucket (timeline grafigi)
# ═══════════════════════════════════════════════════════════════════════════
def test_bucket_kunlik_yigindisi_toliq(db):
    _exp(db, 1_500_000, Date(2026, 8, 22), AUG1, Date(2026, 8, 30))
    m = by_bucket(db, _User(), AUG1, Date(2026, 8, 30), "day")
    assert len(m) == 30
    assert round(sum(m.values()), 2) == 1_500_000.0
    assert m["2026-08-01"] == 50_000.0


def test_bucket_oylik(db):
    """Davr ikki oyga cho'zilsa — har oy o'z ulushini oladi, jami saqlanadi."""
    _exp(db, 600_000, Date(2026, 8, 15), Date(2026, 8, 1), Date(2026, 9, 30))  # 61 kun
    m = by_bucket(db, _User(), Date(2026, 8, 1), Date(2026, 9, 30), "month")
    assert set(m) == {"2026-08-01", "2026-09-01"}
    assert round(sum(m.values()), 2) == 600_000.0
    # avgust 31 kun, sentabr 30 kun
    assert m["2026-08-01"] > m["2026-09-01"]


def test_bucket_hafta_dushanbadan(db):
    """PostgreSQL date_trunc('week') dushanbadan boshlaydi — kalitlar mos."""
    from services.expense_allocation import bucket_start
    assert bucket_start(Date(2026, 8, 26), "week") == Date(2026, 8, 24)   # chorshanba -> dushanba
    assert bucket_start(Date(2026, 8, 24), "week") == Date(2026, 8, 24)


# ═══════════════════════════════════════════════════════════════════════════
# 5. UI uchun tafsilot
# ═══════════════════════════════════════════════════════════════════════════
def test_breakdown_ui_uchun(db):
    _exp(db, 5_800_000, Date(2026, 8, 22), AUG1, AUG31)
    b = breakdown_in_range(db, _User(), Date(2026, 8, 22), Date(2026, 8, 22))
    assert b["raw"] == 5_800_000.0            # "jami Y so'm dan"
    assert 187_000 <= b["allocated"] <= 187_200
    assert b["amortized_count"] == 1
    assert b["is_split"] is True


def test_breakdown_taqsimlanmagan_bolsa_split_yoq(db):
    _exp(db, 200_000, Date(2026, 8, 10))
    b = breakdown_in_range(db, _User(), AUG1, AUG31)
    assert b["allocated"] == b["raw"] == 200_000.0
    assert b["is_split"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 6. Kalendar oyi chegarasi
# ═══════════════════════════════════════════════════════════════════════════
def test_clamp_dokon_ochilgan_sanadan_oldinga_otmaydi():
    """Do'kon hali ishlamagan kunlar sun'iy zararli bo'lib ko'rinmasin."""
    from services.expense_allocation import clamp_from
    assert clamp_from(Date(2026, 8, 1), Date(2026, 8, 13)) == Date(2026, 8, 13)
    assert clamp_from(Date(2026, 8, 20), Date(2026, 8, 13)) == Date(2026, 8, 20)  # keyinroq — tegilmaydi
    assert clamp_from(Date(2026, 8, 1), None) == Date(2026, 8, 1)                 # sana noma'lum


def test_GOLDEN_fazza_clamp_bilan_13_31_avgust(db):
    """JONLI HOLAT: Fazza 13-avgustda ochilgan, xarajat 1-avgustdan belgilansa
    davr 13–31 ga qisiladi. Kun ulushi oshadi, LEKIN oy jami o'zgarmaydi."""
    F, T = Date(2026, 8, 13), AUG31                    # clamp natijasi
    _exp(db, 1_800_000, Date(2026, 8, 22), F, T)
    _exp(db, 2_500_000, Date(2026, 8, 22), F, T)
    _exp(db, 1_500_000, Date(2026, 8, 22), F, T)

    assert total_in_range(db, _User(), AUG1, AUG31) == 5_800_000.0   # oy jami AYNAN
    assert total_in_range(db, _User(), AUG1, Date(2026, 8, 12)) == 0.0  # ochilishdan oldin 0

    kun22 = total_in_range(db, _User(), Date(2026, 8, 22), Date(2026, 8, 22))
    assert round(kun22, 2) == 305_263.14               # 5 800 000 / 19 kun
    assert 531_930 - kun22 > 0                         # o'sha kun endi MUSBAT


@pytest.mark.parametrize("d,f,t", [
    (Date(2026, 8, 22), Date(2026, 8, 1),  Date(2026, 8, 31)),   # 31 kunlik
    (Date(2026, 9, 5),  Date(2026, 9, 1),  Date(2026, 9, 30)),   # 30 kunlik
    (Date(2026, 2, 14), Date(2026, 2, 1),  Date(2026, 2, 28)),   # fevral
    (2024 and Date(2024, 2, 14), Date(2024, 2, 1), Date(2024, 2, 29)),  # kabisa
])
def test_month_bounds(d, f, t):
    assert month_bounds(d) == (f, t)
