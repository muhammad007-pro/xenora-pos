# -*- coding: utf-8 -*-
"""DASHBOARD: "Bugungi savdo" kartasi qatorlari (feature/dashboard-sales-breakdown).

`/analytics/summary` ga FAQAT qo'shimcha kalit `sales_breakdown`:
    savdo = naqd + karta + nasiya + boshqa
    savdo − qaytarish = SOF SAVDO   (ishchi premiyasi shundan)
    kassadan olingan — ma'lumot (hisobga kirmaydi)

Qotiriladi:
  1) GOLDEN: eski kalitlar (total_revenue, by_payment_method, ...) o'zgarmagan
  2) qatorlar yig'indisi == total_revenue (aynan), sales == total_revenue
  3) GOLDEN: sof savdo == /profit/summary `revenue`, qaytarish == summary `returns`
     (dashboard foyda bloki bilan bir xil son)
  4) nasiya (pending credit) savdoda; tugallanmagan Click (pending) savdo EMAS
  5) to'liq qaytarilgan naqd chek sotuvda qoladi (Z qoidasi), qaytarish alohida
  6) bekor qilingan buyurtma to'lovi kirmaydi
  7) kassadan olingan — bugungi inkassatsiya, kechagi va razmen kirmaydi
  8) Z-hisobot `_shift_totals` refaktordan keyin ham aynan (sale_tenders)

Ishga tushirish:  cd backend && py -m pytest tests/test_dashboard_sales_breakdown.py -v -p no:randomly
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import CashMovement, Order, OrderItem, Payment, Product, Shift

from tests.test_dashboard_net_profit import (  # noqa: F401 — pytest fixture'lari
    _clock, db_session, seeded, client, _hdr, _summary, _at, TODAY, YESTERDAY,
)
from tests.test_dashboard_returns_row import _ret


def _an(client, h, qs="period=today"):
    r = client.get(f"/api/v1/analytics/summary?{qs}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _sale(db, cafe, user, ts, payments, status="completed", n=[0]):
    """payments: [(amount, method, status)] — buyurtma summasi = yig'indi."""
    n[0] += 1
    p = db.query(Product).first()
    amt = sum(a for a, _, _ in payments)
    o = Order(order_number=f"B{n[0]:03d}", tenant_id=cafe, status=status,
              total_amount=amt, final_amount=amt, discount_amount=0, waiter_id=user, created_at=ts)
    db.add(o); db.flush()
    db.add(OrderItem(order_id=o.id, product_id=p.id, quantity=amt / 1000, tenant_id=cafe,
                     unit_price=1000, total_price=amt, unit_cost=600))
    for a, m, st in payments:
        db.add(Payment(tenant_id=cafe, order_id=o.id, amount=a, method=m, status=st,
                       cashier_id=user, created_at=ts))
    db.commit()
    return o


def _sum_rows(b):
    return b["cash"] + b["card"] + b["credit"] + b["other"]


def test_GOLDEN_eski_kalitlar_ozgarmagan(seeded, client):
    d = _an(client, _hdr(client))
    assert d["total_revenue"] == 10_000 and d["total_orders"] == 2
    assert d["by_payment_method"] == [{"method": "cash", "amount": 10_000}]
    assert d["avg_order"] == 5_000


def test_qatorlar_yigindisi_savdoga_teng(db_session, seeded, client):
    cafe, u = seeded["cafe"], seeded["user"]
    _sale(db_session, cafe, u, _at(TODAY, 9, 10), [(4_000, "card", "paid")])
    _sale(db_session, cafe, u, _at(TODAY, 9, 20), [(2_000, "cash", "paid"), (3_000, "credit", "pending")])
    _sale(db_session, cafe, u, _at(TODAY, 9, 30), [(1_000, "click", "paid")])
    _sale(db_session, cafe, u, _at(TODAY, 9, 40), [(5_000, "qr", "paid")])
    d = _an(client, _hdr(client))
    b = d["sales_breakdown"]
    assert b["sales"] == d["total_revenue"] == 25_000
    assert (b["cash"], b["card"], b["credit"], b["other"]) == (12_000, 5_000, 3_000, 5_000)
    assert _sum_rows(b) == b["sales"]


def test_GOLDEN_sof_savdo_profit_summary_bilan(db_session, seeded, client):
    cafe, u = seeded["cafe"], seeded["user"]
    _sale(db_session, cafe, u, _at(TODAY, 9, 10), [(4_000, "card", "paid")])
    _ret(db_session, cafe, _at(TODAY, 9, 30), 2)               # bugun — kiradi
    _ret(db_session, cafe, _at(YESTERDAY, 16), 5)              # kecha — kirmaydi
    _ret(db_session, cafe, _at(TODAY, 9, 50), 4, "pending")    # tasdiqlanmagan — kirmaydi
    h = _hdr(client)
    b = _an(client, h)["sales_breakdown"]
    s = _summary(client, h)
    assert b["returns"] == s["returns"] == 2_000 and b["returns_count"] == 1
    assert b["sales"] == s["sales_gross"] == 14_000
    assert b["net_sales"] == s["revenue"] == 12_000


def test_click_kutilmoqda_savdo_emas_nasiya_savdo(db_session, seeded, client):
    cafe, u = seeded["cafe"], seeded["user"]
    # Tugallanmagan Click: buyurtma completed bo'lsa ham to'lov savdo tenderi emas
    _sale(db_session, cafe, u, _at(TODAY, 9, 10), [(1_000, "click", "pending")])
    _sale(db_session, cafe, u, _at(TODAY, 9, 20), [(3_000, "credit", "pending")])
    b = _an(client, _hdr(client))["sales_breakdown"]
    assert b["credit"] == 3_000 and b["card"] == 0
    assert b["other"] == 1_000                 # yig'indi savdoga teng qoladi
    assert _sum_rows(b) == b["sales"] == 14_000


def test_qaytarilgan_naqd_sotuvda_qoladi_bekor_kirmaydi(db_session, seeded, client):
    cafe, u = seeded["cafe"], seeded["user"]
    _sale(db_session, cafe, u, _at(TODAY, 9, 10), [(2_000, "cash", "refunded")])
    _sale(db_session, cafe, u, _at(TODAY, 9, 20), [(9_000, "cash", "paid")], status="cancelled")
    b = _an(client, _hdr(client))["sales_breakdown"]
    assert b["cash"] == 12_000 and b["sales"] == 12_000 and b["other"] == 0


def test_kassadan_olingan(db_session, seeded, client):
    cafe, u = seeded["cafe"], seeded["user"]
    sh = Shift(tenant_id=cafe, user_id=u, start_time=_at(TODAY, 8))
    db_session.add(sh); db_session.flush()
    db_session.add_all([
        CashMovement(tenant_id=cafe, shift_id=sh.id, user_id=u, kind="withdrawal", amount=1_500,
                     reason="egasiga", created_at=_at(TODAY, 9)),
        CashMovement(tenant_id=cafe, shift_id=sh.id, user_id=u, kind="withdrawal", amount=500,
                     reason="non", created_at=_at(TODAY, 9, 30)),
        CashMovement(tenant_id=cafe, shift_id=sh.id, user_id=u, kind="deposit", amount=7_000,
                     reason="razmen", created_at=_at(TODAY, 9, 40)),
        CashMovement(tenant_id=cafe, shift_id=sh.id, user_id=u, kind="withdrawal", amount=9_999,
                     reason="kecha", created_at=_at(YESTERDAY, 21)),
    ])
    db_session.commit()
    b = _an(client, _hdr(client))["sales_breakdown"]
    assert b["cash_withdrawn"] == 2_000 and b["cash_withdrawn_count"] == 2
    assert b["net_sales"] == b["sales"] == 10_000          # sof savdoga ta'sir yo'q


def test_davr_oraligi_va_bosh_davr(db_session, seeded, client):
    h = _hdr(client)
    b = _an(client, h, f"period=today&date_from={YESTERDAY}&date_to={YESTERDAY}")["sales_breakdown"]
    assert b["sales"] == b["cash"] == 50_000 and b["other"] == 0
    e = _an(client, h, "period=today&date_from=2026-01-01&date_to=2026-01-01")["sales_breakdown"]
    assert e == {"sales": 0, "cash": 0, "card": 0, "credit": 0, "other": 0, "returns": 0,
                 "returns_count": 0, "net_sales": 0, "cash_withdrawn": 0, "cash_withdrawn_count": 0}


def test_z_hisobot_refaktordan_keyin_aynan(db_session, seeded, client):
    """`_shift_totals` endi `sale_tenders` ni chaqiradi — natija avvalgi qoida bilan."""
    from routers.shift import _shift_totals
    from models import User
    cafe, u = seeded["cafe"], seeded["user"]
    sh = Shift(tenant_id=cafe, user_id=u, start_time=_at(TODAY, 8))
    db_session.add(sh); db_session.flush()
    for pays in ([(2_000, "cash", "paid")], [(3_000, "credit", "pending")],
                 [(1_000, "click", "pending")], [(4_000, "card", "refunded")]):
        o = _sale(db_session, cafe, u, _at(TODAY, 9), pays)
        o.shift_id = sh.id
    db_session.commit()
    user = db_session.query(User).get(u)
    t = _shift_totals(db_session, user, sh, _at(TODAY, 10))
    assert (t["cash_sales"], t["card_sales"], t["credit_total"]) == (2_000, 4_000, 3_000)
    assert t["total_sales"] == 9_000 and t["sales_count"] == 3
