# -*- coding: utf-8 -*-
"""KECH OCHILGAN SMENA (fix/shift-midnight-open, 2026-10).

MUAMMO (jonli, MANHATTAN #89): kassir 23.10 smenasini 22.10 23:57 da ochdi →
smena kuni 22.10, himoya 23.10 06:00 da tugadi, 24.10 00:02 dagi 1 850 000
chek 24.10 ga tushdi. Sozlama `report_day.late_open = "HH:MM"` (standart
o'chiq) yoqilsa — chegaradan keyin ochilgan smena kuni = ochilgan kun + 1.

Qotiriladi:
  1) yoqiq: 23:57 da ochilgan smena → ertangi kun (shu jumladan 23:59 va
     ertasi 00:02 dagi cheklar)
  2) o'chiq: 23:57 → o'sha kun (avvalgi xulq, BARAKA kabi)
  3) normal vaqtda (09:35) ochilgan smena siljimaydi
  4) himoya oynasi: kech smenada ham D+1 06:00 dan keyin kalendar
  5) jami == Σ kunlar, hamma ekran bir xil (filtr == day_of)
  6) rejim va late_open bir-birini o'chirmaydi

SQLite zona tuzog'i — test_business_day.py izohiga qara (mahalliy zona = UTC).
Ishga tushirish:  cd backend && py -m pytest tests/test_shift_late_open.py -v -p no:randomly
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.timeutils as tu
from core import business_day as bdmod
from core.business_day import (BusinessDay, MODE_CALENDAR, MODE_SHIFT, get_late_open,
                               get_mode, set_late_open, set_mode)
from core.security import get_password_hash
from database import Base, get_db
from main import app
from models import (Cafe, Category, Order, OrderItem, Payment, Permission, Product,
                    Role, Shift, User)

PW = "LateOpn9x"
PHONE = "+998900000404"
LATE = "23:00"


@pytest.fixture()
def _utc_local(monkeypatch):
    monkeypatch.setattr(tu, "_local_tz", lambda tz_name=None: timezone.utc)


@pytest.fixture()
def db_session(_utc_local):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, autocommit=False, autoflush=False)()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(eng)
        eng.dispose()


def _at(d, hour, minute=0):
    return datetime(d.year, d.month, d.day) + timedelta(hours=hour, minutes=minute)


@pytest.fixture()
def seeded(db_session):
    db = db_session
    perms = [Permission(code=c, description=c)
             for c in ("view_analytics", "view_finance", "view_reports", "manage_settings")]
    db.add_all(perms); db.flush()
    role = Role(name="admin", description="Administrator"); role.permissions = perms
    db.add(role); db.flush()
    cafe = Cafe(name="KECH", code="k", access_code="100.200.404",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe); db.flush()
    kat = Category(name="KAT", tenant_id=cafe.id); db.add(kat); db.flush()
    user = User(username="u404", email="404@x.uz", full_name="ADMIN", phone=PHONE,
                hashed_password=get_password_hash(PW), is_active=True,
                is_superuser=False, tenant_id=cafe.id, role_id=role.id)
    db.add(user); db.flush()

    # MANHATTAN #86/#89/#93 shakli: D kunduzgi, D 23:57 da N uchun ochilgan, M ertalab
    D = tu.tenant_now().date() - timedelta(days=5)
    N, M = D + timedelta(days=1), D + timedelta(days=2)
    s_day = Shift(tenant_id=cafe.id, user_id=user.id, start_time=_at(D, 10),
                  end_time=_at(D, 23, 57))
    s_late = Shift(tenant_id=cafe.id, user_id=user.id, start_time=_at(D, 23, 57),
                   end_time=_at(M, 0, 32))
    s_m = Shift(tenant_id=cafe.id, user_id=user.id, start_time=_at(M, 9, 35),
                end_time=_at(M, 23, 0))
    db.add_all([s_day, s_late, s_m]); db.flush()

    plan = [
        (_at(D, 12),     s_day.id,  100.0),
        (_at(D, 23, 30), s_day.id,  200.0),    # kunduzgi smena, kech savdo → D
        (_at(D, 23, 59), s_late.id, 1600.0),   # kech smena, yarim tundan oldin
        (_at(N, 12),     s_late.id, 400.0),
        (_at(M, 0, 2),   s_late.id, 800.0),    # #4930 holati
        (_at(M, 10),     s_m.id,    3200.0),
    ]
    for i, (ts, sid, amt) in enumerate(plan):
        p = Product(name=f"P{i}", price=amt, cost_price=amt / 2, sale_unit="pcs",
                    category_id=kat.id, tenant_id=cafe.id, is_active=True)
        db.add(p); db.flush()
        o = Order(order_number=f"L{i:04d}", tenant_id=cafe.id, status="completed",
                  total_amount=amt, final_amount=amt, discount_amount=0,
                  shift_id=sid, waiter_id=user.id, created_at=ts)
        db.add(o); db.flush()
        db.add(OrderItem(order_id=o.id, product_id=p.id, quantity=1, tenant_id=cafe.id,
                         unit_price=amt, total_price=amt, unit_cost=amt / 2))
        db.add(Payment(tenant_id=cafe.id, order_id=o.id, amount=amt, method="cash",
                       status="paid", cashier_id=user.id, created_at=ts))
    db.commit()
    return {"cafe": cafe.id, "D": D, "N": N, "M": M,
            "s_day": s_day.id, "s_late": s_late.id, "s_m": s_m.id}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _hdr(client):
    r = client.post("/api/v1/auth/login", data={"username": PHONE, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _get(client, hdr, url):
    r = client.get(f"/api/v1{url}", headers=hdr)
    assert r.status_code == 200, f"{url} -> {r.status_code}: {r.text}"
    return r.json()


def _q(d1, d2=None):
    return f"date_from={d1.isoformat()}&date_to={(d2 or d1).isoformat()}"


#: holat → {kun: sotuv}
KUTILGAN = {
    "calendar": {"D": 1900.0, "N": 400.0, "M": 4000.0},
    "shift":    {"D": 1900.0, "N": 400.0, "M": 4000.0},   # kech smena D kuniniki
    "late":     {"D": 300.0,  "N": 2800.0, "M": 3200.0},  # kech smena N kuniniki
}


def _setup(db, seeded, case):
    if case != "calendar":
        set_mode(db, seeded["cafe"], MODE_SHIFT)
    if case == "late":
        set_late_open(db, seeded["cafe"], LATE)


@pytest.mark.parametrize("case", ["calendar", "shift", "late"])
def test_har_kun_hamma_ekranda_bir_xil(db_session, seeded, client, case):
    _setup(db_session, seeded, case)
    h = _hdr(client)
    for key in ("D", "N", "M"):
        q = _q(seeded[key])
        want = KUTILGAN[case][key]
        assert _get(client, h, f"/analytics/summary?{q}")["total_revenue"] == want, key
        assert _get(client, h, f"/profit/summary?{q}")["revenue"] == want, key
        assert _get(client, h, f"/reports/sales?{q}")["total_sales"] == want, key
        assert _get(client, h, f"/orders/history?{q}")["summary"]["total"] == want, key


@pytest.mark.parametrize("case", ["calendar", "shift", "late"])
def test_jami_kunlar_yigindisiga_teng_va_takror_yoq(db_session, seeded, client, case):
    _setup(db_session, seeded, case)
    h = _hdr(client)
    D, N, M = seeded["D"], seeded["N"], seeded["M"]
    want = {d.isoformat(): KUTILGAN[case][k] for k, d in (("D", D), ("N", N), ("M", M))}
    p = _get(client, h, f"/reports/profit?{_q(D, M)}")
    assert {r["date"]: r["revenue"] for r in p["daily"]} == want
    assert round(p["total_revenue"], 2) == 6300.0
    s = _get(client, h, f"/reports/sales?{_q(D, M)}")
    assert s["total_sales"] == 6300.0
    hist = _get(client, h, f"/orders/history?{_q(D, M)}")
    assert {d["date"]: d["total"] for d in hist["days"]} == want


def test_yoqiq_2357_ertangi_kun(db_session, seeded):
    bd = BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_SHIFT, late_open=LATE)
    D, N, M = seeded["D"], seeded["N"], seeded["M"]
    assert bd.day_of(_at(D, 23, 59), seeded["s_late"]) == N
    assert bd.day_of(_at(N, 12), seeded["s_late"]) == N
    assert bd.day_of(_at(M, 0, 2), seeded["s_late"]) == N      # #4930 → kechagi kun
    assert bd.day_of(_at(D, 23, 30), seeded["s_day"]) == D     # eski smena joyida


def test_ochiq_2357_osha_kun_avvalgidek(db_session, seeded):
    """O'chiq (BARAKA): 23:57 da ochilgan smena o'sha kunniki, tungi savdo shu kunga."""
    bd = BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_SHIFT)
    D, N, M = seeded["D"], seeded["N"], seeded["M"]
    assert bd.day_of(_at(N, 3), seeded["s_late"]) == D         # himoya ichida → D
    assert bd.day_of(_at(N, 12), seeded["s_late"]) == N
    assert bd.day_of(_at(M, 0, 2), seeded["s_late"]) == M      # himoyadan keyin


def test_normal_vaqtda_ochilgan_smena_siljimaydi(db_session, seeded):
    bd = BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_SHIFT, late_open=LATE)
    M = seeded["M"]
    assert bd._opened_on(seeded["s_m"]) == M
    assert bd._opened_on(seeded["s_day"]) == seeded["D"]
    assert bd.day_of(_at(M, 10), seeded["s_m"]) == M
    # s_m ning ertasi 01:00 dagi savdosi himoya bilan M ga
    assert bd.day_of(_at(M + timedelta(days=1), 1), seeded["s_m"]) == M


def test_himoya_oynasi_kech_smenada_ham(db_session, seeded):
    bd = BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_SHIFT, late_open=LATE)
    M = seeded["M"]
    sid = seeded["s_late"]                                     # ish kuni N
    assert bd.day_of(_at(M, 5, 59), sid) == seeded["N"]        # N+1 06:00 gacha → N
    assert bd.day_of(_at(M, 6), sid) == M                      # keyin → kalendar
    assert bd.day_of(_at(M + timedelta(days=1), 1), sid) == M + timedelta(days=1)


def test_chegara_aniq_vaqti(db_session, seeded):
    """Chegaradan oldin (22:59) ochilgan smena siljimaydi, aynan 23:00 — siljiydi."""
    D = seeded["D"]
    a = Shift(tenant_id=seeded["cafe"], start_time=_at(D, 22, 59), end_time=_at(D, 23, 10))
    b = Shift(tenant_id=seeded["cafe"], start_time=_at(D, 23, 0), end_time=_at(D, 23, 20))
    db_session.add_all([a, b]); db_session.commit()
    bd = BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_SHIFT, late_open=LATE)
    assert bd._opened_on(a.id) == D
    assert bd._opened_on(b.id) == D + timedelta(days=1)


def test_kalendar_rejimida_late_open_tasir_qilmaydi(db_session, seeded):
    bd = BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_CALENDAR, late_open=LATE)
    assert bd.day_of(_at(seeded["D"], 23, 59), seeded["s_late"]) == seeded["D"]
    s, e = tu.day_bounds(seeded["D"])
    from sqlalchemy import and_
    got = bd.window(Order.created_at, Order.shift_id, s, e)
    assert str(got.compile()) == str(and_(Order.created_at >= s, Order.created_at <= e).compile())


def test_bugun_tunda_kech_ochilgan_smena(db_session, seeded, monkeypatch):
    """00:30 da: kecha 23:57 da ochilgan (ochiq) smena — yoqiqda BUGUNniki, o'chiqda kechaniki."""
    N = seeded["N"]
    sh = Shift(tenant_id=seeded["cafe"], start_time=_at(N, 23, 57))
    db_session.add(sh); db_session.commit()
    fake_now = datetime(N.year, N.month, N.day, tzinfo=timezone.utc) + timedelta(days=1, minutes=30)
    monkeypatch.setattr(bdmod, "tenant_now", lambda tz_name=None: fake_now)
    off = BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_SHIFT)
    on = BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_SHIFT, late_open=LATE)
    assert off.today() == N
    assert on.today() == N + timedelta(days=1)


def test_sozlama_saqlash_bir_birini_ochirmaydi(db_session, seeded):
    t = seeded["cafe"]
    assert get_late_open(db_session, t) is None                # standart o'chiq
    set_late_open(db_session, t, LATE)
    set_mode(db_session, t, MODE_SHIFT)
    assert get_mode(db_session, t) == MODE_SHIFT
    assert str(get_late_open(db_session, t)) == "23:00:00"
    set_late_open(db_session, t, None)
    assert get_late_open(db_session, t) is None
    assert get_mode(db_session, t) == MODE_SHIFT
    for bad in ("25:00", "x", "00:00"):
        with pytest.raises(ValueError):
            set_late_open(db_session, t, bad)
    # tenantdan o'qiladi (mode berilmasa)
    set_late_open(db_session, t, "23:30")
    bd = BusinessDay(db_session, tenant_id=t)
    assert bd.is_shift and bd._late == timedelta(hours=23, minutes=30)


def test_toshkent_zonasi_sof(monkeypatch):
    """Haqiqiy +5: smena Toshkent 22.10 23:57 (UTC 18:57) → 23.10; chek 24.10 00:02 → 23.10."""
    monkeypatch.setattr(tu, "_local_tz", lambda tz_name=None: timezone(timedelta(hours=5)))
    utc = timezone.utc
    bd = BusinessDay(None, tenant_id=1, mode=MODE_SHIFT, late_open=LATE)
    bd._shift_day = {89: date(2026, 10, 23)}
    assert bd.day_of(datetime(2026, 10, 23, 19, 2, tzinfo=utc), 89) == date(2026, 10, 23)
    off = BusinessDay(None, tenant_id=1, mode=MODE_SHIFT)
    off._shift_day = {89: date(2026, 10, 22)}
    assert off.day_of(datetime(2026, 10, 23, 19, 2, tzinfo=utc), 89) == date(2026, 10, 24)
