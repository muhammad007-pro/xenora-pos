# -*- coding: utf-8 -*-
"""SMENA VAQTI ZONASI (migratsiya c9f2a71d3e84).

MUAMMO: `shifts.start_time/end_time` butun bazada YOLG'IZ zona belgisiSIZ
ustunlar edi (orders/payments/audit_logs/... hammasi timestamptz). Ustiga
`shift.py:116` naive `datetime.now()` yozardi -> server UTC bo'lgani uchun
bazaga UTC DEVOR VAQTI tushardi, zona belgisi qolmasdi:

    Pydantic  ->  "2026-09-29T17:37:03.442941"   (OFFSET YO'Q)
    JS new Date(offsetsiz ISO)  ->  MAHALLIY deb o'qiydi  ->  ekranda 17:37
    kompyuter soati             ->  22:37        ya'ni 5 SOAT ORQADA

Ochiq smena taymeri esa teskari xato berardi: `Date.now() - start` -> +5 soat.

Prod o'lchovi (1001 BARAKA, smena #11): start_time = 2026-09-08 16:57:24,
o'sha smenadagi 1-buyurtma orders.created_at = 16:57:43+00 (= Toshkent
21:57:43). Smena buyurtmadan 19 s oldin ochilgan -> haqiqiy vaqt 21:57:24.

Bu fayl to'rt narsani qotiradi:
  1) YOZISH  — UTC saqlanadi (mahalliy devor vaqti EMAS)
  2) O'QISH   — ko'rsatishda tenant zonasiga o'giriladi
  3) GOLDEN   — smena #46: 17:37 UTC -> ekranda 22:37
  4) OYNA     — z-hisobot oralig'i to'g'ri buyurtmalarni qamraydi, summalar
                O'ZGARMAYDI

Ishga tushirish:  cd backend && py -m pytest tests/test_shift_timezone.py -v
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.timeutils import tenant_now, to_local, utc_now
from database import Base
from models import Cafe, Category, Order, OrderItem, Payment, Product, Shift, User

import routers.order as order_router
import routers.shift as shift_router

TID  = 1
_UTC = timezone.utc

#: GOLDEN: prodda 1001 BARAKA ning ochiq smenasi (#46) — bazadagi UTC qiymat
GOLDEN_UTC        = datetime(2026, 9, 29, 17, 37, 3, 442941, tzinfo=_UTC)
GOLDEN_KORINISHI  = "29.09.2026 22:37"     # Toshkent (UTC+5)


class _Perm:
    def __init__(self, code): self.code = code


class _Role:
    def __init__(self, codes): self.permissions = [_Perm(c) for c in codes]


class _User:
    is_superuser = False
    tenant_id = TID
    id = 1
    username = "kassir"
    full_name = "AZIZBEK"
    role = _Role(["view_reports", "view_analytics"])


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    s.add(Cafe(id=TID, name="1001 BARAKA", code="b", business_type="supermarket"))
    s.add(Category(id=1, name="KAT", tenant_id=TID))
    s.add(Product(id=1, name="NON", price=5000, cost_price=3000, sale_unit="pcs",
                  category_id=1, tenant_id=TID))
    s.add(User(id=1, username="kassir", email="k@x.uz", full_name="AZIZBEK",
               phone="+998900000303", hashed_password="x", tenant_id=TID))
    s.commit()
    yield s
    s.close()


def _smena(db, start_utc, end_utc=None, **kw):
    sh = Shift(tenant_id=TID, user_id=1, start_time=start_utc, end_time=end_utc,
               starting_cash=0.0, **kw)
    db.add(sh); db.commit(); db.refresh(sh)
    return sh


def _buyurtma(db, when_utc, summa=50000.0, status="completed", shift_id=None,
              tolov=False):
    n = db.query(Order).count() + 1
    o = Order(order_number=f"S{n:04d}", tenant_id=TID, status=status,
              total_amount=summa, final_amount=summa, discount_amount=0,
              created_at=when_utc, shift_id=shift_id, waiter_id=1)
    db.add(o); db.commit(); db.refresh(o)
    db.add(OrderItem(order_id=o.id, product_id=1, quantity=1,
                     unit_price=summa, total_price=summa, unit_cost=30000))
    if tolov:
        # Z-chek `total_sales` ni TO'LOVLARdan hisoblaydi (hisobot `summary` esa
        # buyurtmalardan) — ataylab ikki manba, shuning uchun ikkisi ham sinaladi.
        db.add(Payment(order_id=o.id, tenant_id=TID, amount=summa, method="cash",
                       status="paid", created_at=when_utc, cashier_id=1))
    db.commit()
    return o


def _hisobot(db, shift_id):
    return asyncio.run(shift_router.get_shift_report(shift_id, db=db, current_user=_User()))


def _zchek(db, shift):
    return shift_router._build_zreport_data(shift, db, _User())


# ══════════════════════════════════════════════════════════════════════════════
# 1) USTUN TIPI — zona belgisi bor
# ══════════════════════════════════════════════════════════════════════════════

def test_ustunlar_timezone_aware(db):
    """`shifts.start_time/end_time` timezone=True bo'lsin (migratsiya shartnomasi)."""
    for ustun in ("start_time", "end_time"):
        col = Shift.__table__.c[ustun]
        assert col.type.timezone is True, f"{ustun} zona belgisiSIZ qolgan"


def test_orders_bilan_bir_xil_tip(db):
    """Smena vaqtlari `orders.created_at` bilan BIR XIL tipda bo'lsin."""
    assert Shift.__table__.c.start_time.type.timezone is Order.__table__.c.created_at.type.timezone


# ══════════════════════════════════════════════════════════════════════════════
# 2) YOZISH — UTC saqlanadi, mahalliy devor vaqti EMAS
# ══════════════════════════════════════════════════════════════════════════════

def test_ochish_utc_yozadi(db):
    """Smena ochilganda UTC yoziladi; `to_local()` esa Toshkent vaqtini beradi.

    ILGARI naive `datetime.now()` yozilardi va zona belgisi qolmasdi.
    """
    oldin = utc_now()
    sh    = _smena(db, utc_now())
    keyin = utc_now()

    saqlangan = to_local(sh.start_time)
    # Saqlangan qiymat UTC oralig'ida (mahalliy devor vaqti EMAS)
    assert to_local(oldin) <= saqlangan <= to_local(keyin)
    # Va u tenant zonasida HOZIRGI vaqtga mos (5 soat siljish YO'Q)
    assert abs((saqlangan - tenant_now()).total_seconds()) < 60


def test_saqlangan_qiymat_mahalliy_devor_vaqti_EMAS(db):
    """⚠️ Regressiya qo'riqchisi: `tenant_now()` ni to'g'ridan yozish XATO.

    SQLAlchemy'ning SQLite dialekti zonani tashlaydi va aware qiymatning DEVOR
    vaqtini yozadi -> `tenant_now()` yozilsa bazada 01:55 qolardi va `to_local()`
    uni UTC deb olib 06:55 qilardi (5 soat OSHIQ). `utc_now()` bu tuzoqdan
    qutqaradi — shuning uchun yozish yo'li aynan shunday bo'lishi kerak.
    """
    sh = _smena(db, utc_now())
    xom = sh.start_time
    xom_naive = xom.replace(tzinfo=None) if xom.tzinfo else xom
    toshkent_devor = tenant_now().replace(tzinfo=None)
    # Xom qiymat Toshkent devor vaqtiga TENG BO'LMASIN (u UTC bo'lishi kerak)
    assert abs((toshkent_devor - xom_naive).total_seconds()) > 3600 * 4


def test_yopish_utc_yozadi(db):
    """Yopilgan smenaning `end_time` i ham UTC va `start_time` dan keyin."""
    sh = _smena(db, utc_now() - timedelta(hours=3))
    sh.end_time = utc_now()
    db.commit(); db.refresh(sh)
    assert to_local(sh.end_time) > to_local(sh.start_time)
    assert abs((to_local(sh.end_time) - tenant_now()).total_seconds()) < 60


# ══════════════════════════════════════════════════════════════════════════════
# 3) ⚠️ GOLDEN — smena #46: 17:37 UTC -> ekranda 22:37
# ══════════════════════════════════════════════════════════════════════════════

def test_golden_smena_46_toshkent_vaqtini_korsatadi(db):
    """Prod smena #46: bazada 17:37 UTC, ekranda 22:37 Toshkent bo'lishi SHART."""
    sh = _smena(db, GOLDEN_UTC)
    r  = _hisobot(db, sh.id)
    assert r["start_time"] == GOLDEN_KORINISHI, (
        f"kutilgan {GOLDEN_KORINISHI}, kelgan {r['start_time']}"
    )


def test_golden_zchekda_ham_22_37(db):
    """Z-hisobot chekida ham tenant zonasi (serverda formatlangan satr)."""
    sh = _smena(db, GOLDEN_UTC)
    z  = _zchek(db, sh)
    assert z["start_time"] == GOLDEN_KORINISHI
    # chek sarlavhasidagi "datetime" ham Toshkent zonasida
    assert z["datetime"] == to_local(utc_now()).strftime("%d.%m.%Y %H:%M")


def test_utc_devor_vaqti_QAYTARILMAYDI(db):
    """Regressiya: ilgari `start.strftime()` UTC devor vaqtini chop etardi."""
    sh = _smena(db, GOLDEN_UTC)
    r  = _hisobot(db, sh.id)
    assert r["start_time"] != "29.09.2026 17:37", "hali ham UTC ko'rsatilyapti"


def test_yopilgan_smena_ikkala_vaqti_ham_ogiriladi(db):
    sh = _smena(db, GOLDEN_UTC, end_utc=GOLDEN_UTC + timedelta(hours=8))
    r  = _hisobot(db, sh.id)
    assert r["start_time"] == GOLDEN_KORINISHI
    assert r["end_time"]   == "30.09.2026 06:37"          # 17:37+8h = 01:37 UTC -> 06:37
    assert r["duration_hours"] == 8.0                      # davomiylik O'ZGARMAYDI


# ══════════════════════════════════════════════════════════════════════════════
# 4) Z-HISOBOT OYNASI — to'g'ri buyurtmalar, summalar O'ZGARMAYDI
# ══════════════════════════════════════════════════════════════════════════════

def test_oyna_shift_id_boyicha_qamraydi(db):
    """Asosiy yo'l: `shift_id` bog'lanishi (vaqt oralig'iga tayanmaydi)."""
    sh = _smena(db, GOLDEN_UTC, end_utc=GOLDEN_UTC + timedelta(hours=8))
    _buyurtma(db, GOLDEN_UTC + timedelta(hours=1), 50000.0, shift_id=sh.id)
    _buyurtma(db, GOLDEN_UTC + timedelta(hours=2), 70000.0, shift_id=sh.id)
    r = _hisobot(db, sh.id)
    assert r["summary"]["total_orders"] == 2
    assert r["summary"]["total_revenue"] == pytest.approx(120000.0, abs=1)


def test_oyna_legacy_fallback_vaqt_boyicha(db):
    """Legacy yo'l: `shift_id` yo'q buyurtmalar VAQT ORALIG'I bilan olinadi.

    ⚠️ Aynan shu yerda naive/aware aralashuvi xatoga olib kelardi: naive
    `start` timestamptz `Order.created_at` bilan solishtirilardi. Migratsiyadan
    keyin ikkalasi ham aware -> oraliq to'g'ri.
    """
    sh = _smena(db, GOLDEN_UTC, end_utc=GOLDEN_UTC + timedelta(hours=8))
    _buyurtma(db, GOLDEN_UTC + timedelta(hours=1), 50000.0)          # ICHIDA
    _buyurtma(db, GOLDEN_UTC + timedelta(hours=7), 70000.0)          # ICHIDA
    _buyurtma(db, GOLDEN_UTC - timedelta(hours=1), 90000.0)          # OLDIN
    _buyurtma(db, GOLDEN_UTC + timedelta(hours=9), 30000.0)          # KEYIN
    r = _hisobot(db, sh.id)
    assert r["summary"]["total_orders"] == 2, "oyna chetdagi buyurtmani tortdi"
    assert r["summary"]["total_revenue"] == pytest.approx(120000.0, abs=1)


def test_summalar_zonadan_MUSTAQIL(db):
    """Sotuv summalari vaqt ko'rsatilishiga BOG'LIQ EMAS — o'zgarmasin.

    Hisobot `summary` — BUYURTMAlardan, z-chek `total_sales` — TO'LOVlardan
    (ataylab ikki manba). Ikkisi ham to'liq qamralsin va mos kelsin.
    """
    sh = _smena(db, GOLDEN_UTC, end_utc=GOLDEN_UTC + timedelta(hours=8))
    for i in range(5):
        _buyurtma(db, GOLDEN_UTC + timedelta(hours=i + 1), 10000.0,
                  shift_id=sh.id, tolov=True)
    r = _hisobot(db, sh.id)
    z = _zchek(db, sh)
    assert r["summary"]["total_revenue"] == pytest.approx(50000.0, abs=1)
    assert z["total_sales"] == pytest.approx(50000.0, abs=1)
    assert z["cash_sales"] == pytest.approx(50000.0, abs=1)


def test_tolov_oynasi_ham_zonaga_bogliq_EMAS(db):
    """To'lov oynasi (`Payment.created_at`) ham chetdagini tortmasin."""
    sh = _smena(db, GOLDEN_UTC, end_utc=GOLDEN_UTC + timedelta(hours=8))
    _buyurtma(db, GOLDEN_UTC + timedelta(hours=2), 40000.0, tolov=True)   # ICHIDA
    _buyurtma(db, GOLDEN_UTC - timedelta(hours=2), 90000.0, tolov=True)   # OLDIN
    _buyurtma(db, GOLDEN_UTC + timedelta(hours=10), 90000.0, tolov=True)  # KEYIN
    z = _zchek(db, sh)
    assert z["total_sales"] == pytest.approx(40000.0, abs=1)


def test_yarim_tundan_keyingi_smena_oz_kuniga_tushadi(db):
    """00:30 Toshkent (= 19:30 UTC oldingi kun) smenasi o'z kunini ko'rsatsin."""
    utc_1930 = datetime(2026, 9, 29, 19, 30, tzinfo=_UTC)   # Toshkent 30-sentabr 00:30
    sh = _smena(db, utc_1930)
    r  = _hisobot(db, sh.id)
    assert r["start_time"] == "30.09.2026 00:30"


# ══════════════════════════════════════════════════════════════════════════════
# 5) CHEK VAQTI — order.py:373 / 458
# ══════════════════════════════════════════════════════════════════════════════

def test_chek_vaqti_tenant_zonasida(db):
    """Chekdagi `date` Toshkent zonasida bo'lsin (ilgari UTC edi)."""
    o = _buyurtma(db, GOLDEN_UTC)
    r = asyncio.run(order_router.get_order_receipt(o.id, db=db, current_user=_User()))
    assert r["date"] == GOLDEN_KORINISHI
    assert r["date"] != "29.09.2026 17:37", "chek hali ham UTC ko'rsatyapti"


def test_fmt_local_none_ni_kotarmaydi():
    """Ochiq smenada `end_time` NULL — formatlovchi yiqilmasin."""
    assert shift_router._fmt_local(None) is None
    assert order_router._fmt_local(None) is None


# ══════════════════════════════════════════════════════════════════════════════
# 6) MIGRATSIYA SHARTNOMASI — `USING ... AT TIME ZONE 'UTC'` semantikasi
# ══════════════════════════════════════════════════════════════════════════════

def test_migratsiya_qiymatni_ozgartirmaydi():
    """Migratsiya faqat ZONA BELGISINI qo'shadi — raqamlar o'sha qoladi.

    `ALTER ... USING start_time AT TIME ZONE 'UTC'` mavjud naive qiymatni UTC
    deb TALQIN qiladi. Prodda SELECT bilan tekshirilgan:
        2026-09-29 17:37:03.442941  ->  2026-09-29 17:37:03.442941+00
    """
    naive = datetime(2026, 9, 29, 17, 37, 3, 442941)
    aware = naive.replace(tzinfo=_UTC)                  # migratsiyaning natijasi
    assert aware.replace(tzinfo=None) == naive          # raqamlar bit-bitiga o'sha
    assert to_local(aware).strftime("%d.%m.%Y %H:%M") == GOLDEN_KORINISHI


def test_migratsiya_fayli_utc_ni_qatiy_yozadi():
    """⚠️ USING'da 'UTC' QAT'IY bo'lsin — sessiya zonasiga tayanmasin.

    Sessiya `Asia/Tashkent` bo'lsa, zonasiz USING har bir smenani YANA 5 soat
    surardi. Shu sabab migratsiya matnida 'UTC' aniq yozilgan.
    """
    import pathlib
    yol = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions" / \
        "c9f2a71d3e84_shifts_timestamptz.py"
    matn = yol.read_text(encoding="utf-8")
    assert "AT TIME ZONE 'UTC'" in matn
    assert matn.count("AT TIME ZONE 'UTC'") >= 2, "upgrade va downgrade da ham bo'lsin"


def test_naive_qiymat_UTC_deb_oqiladi():
    """`to_local()` naive qiymatni UTC deb oladi — migratsiya shunga tayanadi."""
    assert to_local(datetime(2026, 9, 29, 17, 37)).strftime("%H:%M") == "22:37"
