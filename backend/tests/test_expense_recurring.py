# -*- coding: utf-8 -*-
"""TAKRORIY XARAJAT NUSXASI TAQSIMLANADI + Toshkent sanasi (fix/expense-amortization).

NUQSON: `ensure_recurring_expenses` nusxa yaratganda `amortize_from/to` ni
ko'chirmasdi — shablon kunlarga taqsimlangan bo'lsa ham keyingi oylarda 3 mln
yana BITTA kunga tushardi (Fazza 2026-08 xatosining takrori). Bundan tashqari
sanalar `date.today()` (server UTC) dan olinardi — Toshkent 00:00–05:00 da
kiritilgan xarajat kechagi kunga, oyning yangi nusxasi bir kun kech tushardi.

Qotiriladi:
  1) oylik, kalendar oyiga taqsimlangan shablon → har nusxa O'Z oyiga
  2) shablon boshi do'kon ochilgan kunga qisilgan bo'lsa ham nusxa TO'LIQ oy
  3) taqsimlanmagan shablon → nusxa ham taqsimlanmaydi (GOLDEN, avvalgidek)
  4) qo'lda berilgan davr (15-dan 14-gacha) → oyma-oy suriladi
  5) haftalik → kunlar farqiga suriladi
  6) 31-yanvar shablon → fevral nusxasi fevral oxirigacha
  7) idempotent — ikkinchi chaqiruv nusxa yaratmaydi
  8) foyda hisobida oy jami = summa, kuniga summa/oy kunlari
  9) "bugun" va standart xarajat sanasi — Toshkent kuni (UTC emas)

Ishga tushirish:  cd backend && py -m pytest tests/test_expense_recurring.py -v -p no:randomly
"""
import asyncio
import os
import sys
from datetime import date as Date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import routers.profit as profit
from database import Base
from models import Cafe, Expense, User
from services.expense_allocation import recurring_copy_period, share_in_range, total_in_range

UZ = timezone(timedelta(hours=5))


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Cafe(id=1, name="T", code="T"))
    s.add(User(id=1, username="u1", email="u1@x.uz", full_name="U", phone="+998900000501",
               hashed_password="x", is_active=True, is_superuser=False, tenant_id=1))
    s.commit()
    yield s
    s.close()
    eng.dispose()


def _user(db):
    return db.query(User).get(1)


def _now(monkeypatch, dt):
    monkeypatch.setattr(profit, "tenant_now", lambda tz_name=None: dt)


def _tpl(db, d, am_from=None, am_to=None, period="monthly", day=None, amount=3_000_000):
    e = Expense(tenant_id=1, category="rent", name="IJARA", amount=amount, expense_date=d,
                is_recurring=True, recurrence_period=period, recurrence_day=day or d.day,
                amortize_from=am_from, amortize_to=am_to, created_by=1)
    db.add(e); db.commit(); db.refresh(e)
    return e


def _copies(db, t):
    return [(c.expense_date, c.amortize_from, c.amortize_to)
            for c in db.query(Expense).filter(Expense.recurrence_parent_id == t.id)
                                      .order_by(Expense.expense_date).all()]


def test_oylik_taqsimlangan_har_nusxa_oz_oyiga(db, monkeypatch):
    t = _tpl(db, Date(2026, 8, 22), Date(2026, 8, 1), Date(2026, 8, 31))
    _now(monkeypatch, datetime(2026, 11, 5, 12, tzinfo=UZ))
    assert profit.ensure_recurring_expenses(db, _user(db)) == 2
    assert _copies(db, t) == [
        (Date(2026, 9, 22), Date(2026, 9, 1), Date(2026, 9, 30)),
        (Date(2026, 10, 22), Date(2026, 10, 1), Date(2026, 10, 31)),
    ]


def test_qisilgan_shablon_nusxasi_toliq_oy(db, monkeypatch):
    """Do'kon 13-avgustda ochilgan: shablon 13–31 avgust, nusxa esa to'liq sentyabr."""
    t = _tpl(db, Date(2026, 8, 22), Date(2026, 8, 13), Date(2026, 8, 31))
    _now(monkeypatch, datetime(2026, 9, 25, 12, tzinfo=UZ))
    profit.ensure_recurring_expenses(db, _user(db))
    assert _copies(db, t) == [(Date(2026, 9, 22), Date(2026, 9, 1), Date(2026, 9, 30))]


def test_GOLDEN_taqsimlanmagan_shablon_nusxasi_ham_taqsimlanmaydi(db, monkeypatch):
    t = _tpl(db, Date(2026, 8, 22))
    _now(monkeypatch, datetime(2026, 10, 25, 12, tzinfo=UZ))
    profit.ensure_recurring_expenses(db, _user(db))
    assert _copies(db, t) == [(Date(2026, 9, 22), None, None), (Date(2026, 10, 22), None, None)]
    # avvalgidek: butun summa nusxa kuniga
    c = db.query(Expense).filter(Expense.recurrence_parent_id == t.id).first()
    assert share_in_range(c, Date(2026, 9, 22), Date(2026, 9, 22)) == 3_000_000.0


def test_qolda_berilgan_davr_oyma_oy_suriladi(db, monkeypatch):
    t = _tpl(db, Date(2026, 8, 15), Date(2026, 8, 15), Date(2026, 9, 14))
    _now(monkeypatch, datetime(2026, 9, 20, 12, tzinfo=UZ))
    profit.ensure_recurring_expenses(db, _user(db))
    assert _copies(db, t) == [(Date(2026, 9, 15), Date(2026, 9, 15), Date(2026, 10, 14))]


def test_haftalik_kunlar_farqiga_suriladi(db, monkeypatch):
    t = _tpl(db, Date(2026, 8, 3), Date(2026, 8, 3), Date(2026, 8, 9), period="weekly")
    _now(monkeypatch, datetime(2026, 8, 18, 12, tzinfo=UZ))
    profit.ensure_recurring_expenses(db, _user(db))
    assert _copies(db, t) == [
        (Date(2026, 8, 10), Date(2026, 8, 10), Date(2026, 8, 16)),
        (Date(2026, 8, 17), Date(2026, 8, 17), Date(2026, 8, 23)),
    ]


def test_31_yanvar_fevral_oxirigacha(db, monkeypatch):
    t = _tpl(db, Date(2027, 1, 31), Date(2027, 1, 1), Date(2027, 1, 31), day=31)
    _now(monkeypatch, datetime(2027, 3, 31, 12, tzinfo=UZ))
    profit.ensure_recurring_expenses(db, _user(db))
    assert _copies(db, t) == [
        (Date(2027, 2, 28), Date(2027, 2, 1), Date(2027, 2, 28)),
        (Date(2027, 3, 31), Date(2027, 3, 1), Date(2027, 3, 31)),
    ]
    # qo'lda davr ham oy oxiridan oy oxiriga suriladi
    t2 = Expense(expense_date=Date(2027, 1, 31), recurrence_period="monthly",
                 amortize_from=Date(2027, 1, 16), amortize_to=Date(2027, 2, 15))
    assert recurring_copy_period(t2, Date(2027, 2, 28)) == (Date(2027, 2, 16), Date(2027, 3, 15))


def test_idempotent(db, monkeypatch):
    t = _tpl(db, Date(2026, 8, 22), Date(2026, 8, 1), Date(2026, 8, 31))
    _now(monkeypatch, datetime(2026, 10, 25, 12, tzinfo=UZ))
    assert profit.ensure_recurring_expenses(db, _user(db)) == 2
    assert profit.ensure_recurring_expenses(db, _user(db)) == 0
    assert len(_copies(db, t)) == 2


def test_foyda_hisobida_oy_jami_va_kunlik_ulush(db, monkeypatch):
    _tpl(db, Date(2026, 8, 22), Date(2026, 8, 1), Date(2026, 8, 31))
    _now(monkeypatch, datetime(2026, 9, 25, 12, tzinfo=UZ))
    profit.ensure_recurring_expenses(db, _user(db))
    u = _user(db)
    assert total_in_range(db, u, Date(2026, 9, 1), Date(2026, 9, 30)) == 3_000_000.0
    assert total_in_range(db, u, Date(2026, 9, 22), Date(2026, 9, 22)) == 100_000.0   # 3 mln / 30
    assert total_in_range(db, u, Date(2026, 8, 1), Date(2026, 9, 30)) == 6_000_000.0


def test_bugun_toshkent_kuni_tunda_nusxa_kech_qolmaydi(db, monkeypatch):
    """Toshkent 1-oktabr 01:00 = UTC 30-sentabr 20:00. Oktabr nusxasi (1-kun) SHU kuni bo'lishi kerak."""
    t = _tpl(db, Date(2026, 9, 1), Date(2026, 9, 1), Date(2026, 9, 30), day=1)
    _now(monkeypatch, datetime(2026, 10, 1, 1, tzinfo=UZ))
    profit.ensure_recurring_expenses(db, _user(db))
    assert _copies(db, t) == [(Date(2026, 10, 1), Date(2026, 10, 1), Date(2026, 10, 31))]


def test_standart_xarajat_sanasi_toshkent_kuni(db, monkeypatch):
    """Sana berilmasa — Toshkent kuni (server UTC sanasi emas)."""
    _now(monkeypatch, datetime(2030, 1, 2, 1, 30, tzinfo=UZ))   # UTC da hali 1-yanvar
    asyncio.run(profit.create_expense({"name": "TAKSI", "amount": 50_000}, db=db, current_user=_user(db)))
    e = db.query(Expense).filter(Expense.name == "TAKSI").one()
    assert e.expense_date == Date(2030, 1, 2)
