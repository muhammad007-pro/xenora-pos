# -*- coding: utf-8 -*-
"""VOZVRAT PUL HISOBOTIDA QAYTARILGAN KUNGA (fix/returns-tender-day).

MANHATTAN shikoyati: /reports/sales, /analytics/summary `by_payment_method` va
AnalyticsService.get_period_data `Payment.status == "paid"` dan o'qirdi. To'liq
vozvratda asl to'lov `refunded` bo'ladi → sotuv O'TGAN kundan yo'qolardi
(16.10: 6 865 000 → 5 965 000), qaytarish esa hech qaysi kunda ko'rinmasdi.
Qisman vozvratda asl to'lov `paid` qoladi → vozvrat umuman ko'rinmasdi.

Qotiriladi (qoida `utils/cashflow.period_tenders` da, uch joy bitta funksiyadan):
  1) kecha sotilgan, bugun TO'LIQ qaytarilgan: kecha o'zgarmaydi, bugun ayiriladi
  2) QISMAN qaytarish ham shunday
  3) uch hisobot bir xil raqam beradi (har kun)
  4) hujjatsiz `refund_payment` yo'li ham qaytarilgan kunda
  5) nasiya qarzidan yopilgan (balansga) vozvrat: sotuv hisobotida bor,
     "kassaga tushgan"dan ayirilmaydi (pul chiqmagan)
  6) GOLDEN: savdo kartasi (sales_breakdown) qaytarishi /reports/sales bilan bir xil

Pul harakati HAQIQIY yo'l bilan: `routers.returns._refund_money` (asl to'lov
`refunded` + manfiy yozuv) — test o'zi status yozmaydi.

Ishga tushirish:  cd backend && py -m pytest tests/test_returns_tender_day.py -v -p no:randomly
"""
import asyncio
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Order, OrderItem, Payment, Return, ReturnItem, User

from tests.test_dashboard_net_profit import (  # noqa: F401 — pytest fixture'lari
    _clock, db_session, seeded, client, _at, TODAY, YESTERDAY,
)


def _user(db, seeded):
    return db.query(User).get(seeded["user"])


def _bounds(d):
    from core.timeutils import day_bounds
    s, nxt = day_bounds(d)
    return s, nxt - timedelta(microseconds=1)


def _reports(db, u, d):
    """Bir kun uchun uch hisobot (+ savdo kartasi) — to'g'ridan funksiyalar."""
    from routers.analytics import get_summary
    from services.analytics_service import AnalyticsService
    from services.report_service import ReportService
    s, e = _bounds(d)
    sales = ReportService(db).generate_sales_report(s, e, current_user=u)
    summ = asyncio.run(get_summary(period="today", date_from=d.isoformat(), date_to=d.isoformat(),
                                   db=db, current_user=u))
    pdata = AnalyticsService(db).get_period_data(s, e, current_user=u)
    return sales, summ, pdata


def _method(rows, m, key="amount"):
    return sum(r[key] for r in rows if r["method"] == m)


def _yesterday_order(db):
    """Fixture'dagi kechagi 50 000 naqd chek (50 dona)."""
    return db.query(Order).filter(Order.final_amount == 50_000).one()


def _return(db, u, order, qty, ts, method="cash", customer_id=None, n=[0]):
    """`order` dan qty dona qaytarish, `ts` da tasdiqlangan — pul HAQIQIY yo'l bilan."""
    from routers.returns import _refund_money
    n[0] += 1
    oi = db.query(OrderItem).filter(OrderItem.order_id == order.id).first()
    r = Return(tenant_id=order.tenant_id, return_number=f"RT{n[0]:04d}", order_id=order.id,
               customer_id=customer_id, total_amount=1000 * qty, refund_method=method,
               status="approved", approved_at=ts, created_at=ts)
    db.add(r); db.flush()
    db.add(ReturnItem(return_id=r.id, product_id=oi.product_id, order_item_id=oi.id,
                      quantity=qty, unit_price=1000, total=1000 * qty))
    db.flush()
    _refund_money(db, r, u)
    # `refund_payment` manfiy yozuvni hozirgi vaqtga qo'yadi — test soati bilan bir xil bo'lsin
    for p in db.query(Payment).filter(Payment.order_id == order.id, Payment.amount < 0,
                                      Payment.created_at.is_(None) | (Payment.created_at > ts)):
        p.created_at = ts
    db.commit()
    return r


def _snapshot(db, u, d):
    sales, summ, pdata = _reports(db, u, d)
    return (sales["total_sales"], sales["returns_total"], _method(summ["by_payment_method"], "cash"),
            pdata["sales_paid"])


def test_kecha_sotilgan_bugun_TOLIQ_qaytarildi(db_session, seeded):
    db, u = db_session, _user(db_session, seeded)
    oldin = _snapshot(db, u, YESTERDAY)
    assert oldin == (50_000, 0, 50_000, 50_000)

    order = _yesterday_order(db)
    _return(db, u, order, 50, _at(TODAY, 9, 30))
    # haqiqiy yo'l asl to'lovni `refunded` qildi (xato sababi aynan shu edi)
    asl = db.query(Payment).filter(Payment.order_id == order.id, Payment.amount > 0).one()
    assert str(getattr(asl.status, "value", asl.status)) == "refunded"

    # KECHA — o'zgarmaydi
    assert _snapshot(db, u, YESTERDAY) == oldin
    # BUGUN — sotuv 10 000 (2 chek), qaytarish 50 000 shu kunda ayiriladi
    sales, summ, pdata = _reports(db, u, TODAY)
    assert (sales["total_sales"], sales["returns_total"], sales["net_sales"]) == (10_000, 50_000, -40_000)
    assert sales["money_refunds"] == 50_000
    assert _method(sales["payment_methods"], "cash", "returns") == 50_000
    today_row = [r for r in sales["daily_sales"] if r["date"] == TODAY.isoformat()][0]
    assert (today_row["total"], today_row["returns"], today_row["net"]) == (10_000, 50_000, -40_000)
    assert _method(summ["by_payment_method"], "cash") == -40_000
    assert summ["payment_refunds"] == [{"method": "cash", "amount": 50_000}]
    assert pdata["sales_paid"] == -40_000 and pdata["refunds"] == 50_000


def test_kecha_sotilgan_bugun_QISMAN_qaytarildi(db_session, seeded):
    db, u = db_session, _user(db_session, seeded)
    oldin = _snapshot(db, u, YESTERDAY)
    order = _yesterday_order(db)
    _return(db, u, order, 12, _at(TODAY, 9, 30))
    asl = db.query(Payment).filter(Payment.order_id == order.id, Payment.amount > 0).one()
    assert str(getattr(asl.status, "value", asl.status)) == "paid"     # qisman — asl to'lov qoladi

    assert _snapshot(db, u, YESTERDAY) == oldin
    sales, summ, pdata = _reports(db, u, TODAY)
    assert (sales["total_sales"], sales["returns_total"], sales["net_sales"]) == (10_000, 12_000, -2_000)
    assert _method(summ["by_payment_method"], "cash") == -2_000
    assert pdata["sales_paid"] == -2_000


def test_uch_hisobot_bir_xil_raqam(db_session, seeded):
    db, u = db_session, _user(db_session, seeded)
    order = _yesterday_order(db)
    _return(db, u, order, 20, _at(TODAY, 9, 30))
    _return(db, u, order, 5, _at(TODAY, 9, 40))
    for d in (YESTERDAY, TODAY, TODAY - timedelta(days=5)):
        sales, summ, pdata = _reports(db, u, d)
        kassa_sales = sum(m["net"] for m in sales["payment_methods"] if m["method"] != "credit")
        kassa_summary = sum(m["amount"] for m in summ["by_payment_method"])
        assert kassa_sales == kassa_summary == pdata["sales_paid"], d
        # sotuv hisoboti zanjiri
        assert sales["total_sales"] - sales["returns_total"] == sales["net_sales"]
        assert sum(r["net"] for r in sales["daily_sales"]) == sales["net_sales"]


def test_hujjatsiz_refund_payment_yoli_ham_qaytarilgan_kunda(db_session, seeded):
    from services.payment_service import PaymentService
    db, u = db_session, _user(db_session, seeded)
    oldin = _snapshot(db, u, YESTERDAY)
    order = _yesterday_order(db)
    asl = db.query(Payment).filter(Payment.order_id == order.id).one()
    PaymentService(db).refund_payment(asl, 50_000, "mijoz so'radi", commit=False)
    db.query(Payment).filter(Payment.amount < 0).update({"created_at": _at(TODAY, 9, 30)})
    db.commit()
    assert _snapshot(db, u, YESTERDAY) == oldin
    sales, summ, pdata = _reports(db, u, TODAY)
    assert sales["returns_total"] == sales["money_refunds"] == 50_000
    assert _method(summ["by_payment_method"], "cash") == pdata["sales_paid"] == -40_000


def test_nasiya_balansga_vozvrat_kassadan_ayirilmaydi(db_session, seeded):
    from models import Customer, CustomerDebt
    db, u = db_session, _user(db_session, seeded)
    c = Customer(tenant_id=seeded["cafe"], name="QARZDOR", phone="+998900000699")
    db.add(c); db.flush()
    o = Order(order_number="N001", tenant_id=seeded["cafe"], status="completed", customer_id=c.id,
              total_amount=8_000, final_amount=8_000, discount_amount=0, waiter_id=u.id,
              created_at=_at(YESTERDAY, 12))
    db.add(o); db.flush()
    prod = db.query(OrderItem).first().product_id
    db.add(OrderItem(order_id=o.id, product_id=prod, quantity=8, tenant_id=seeded["cafe"],
                     unit_price=1000, total_price=8_000, unit_cost=600))
    db.add(Payment(tenant_id=seeded["cafe"], order_id=o.id, amount=8_000, method="credit",
                   status="pending", cashier_id=u.id, created_at=_at(YESTERDAY, 12)))
    db.add(CustomerDebt(tenant_id=seeded["cafe"], customer_id=c.id, order_id=o.id, amount=8_000,
                        paid_amount=0, remaining=8_000, status="open", created_at=_at(YESTERDAY, 12)))
    db.commit()
    oldin = _reports(db, u, YESTERDAY)[0]["credit_sales"]
    assert oldin == 8_000

    _return(db, u, o, 3, _at(TODAY, 9, 30), method="credit", customer_id=c.id)
    assert _reports(db, u, YESTERDAY)[0]["credit_sales"] == oldin           # kecha o'zgarmaydi
    sales, summ, pdata = _reports(db, u, TODAY)
    assert sales["returns_total"] == 3_000 and sales["money_refunds"] == 0
    assert _method(sales["payment_methods"], "credit", "returns") == 3_000
    assert summ["payment_refunds"] == []                                   # pul chiqmagan
    assert pdata["sales_paid"] == 10_000 and pdata["refunds"] == 0


def test_GOLDEN_savdo_kartasi_qaytarishi_bilan_mos(db_session, seeded):
    db, u = db_session, _user(db_session, seeded)
    _return(db, u, _yesterday_order(db), 7, _at(TODAY, 9, 30))
    sales, summ, _ = _reports(db, u, TODAY)
    b = summ["sales_breakdown"]
    assert b["returns"] == sales["returns_total"] == 7_000
    assert b["sales"] == sales["total_sales"] == 10_000
    assert b["net_sales"] == sales["net_sales"]


def test_vozvratsiz_kun_shakli_va_raqami(db_session, seeded):
    db, u = db_session, _user(db_session, seeded)
    sales, summ, pdata = _reports(db, u, YESTERDAY)
    assert summ["by_payment_method"] == [{"method": "cash", "amount": 50_000}]
    assert summ["payment_refunds"] == []
    assert sales["payment_methods"] == [{"method": "cash", "total": 50_000, "count": 1,
                                         "returns": 0, "net": 50_000}]
    assert (sales["total_sales"], sales["returns_total"], sales["transactions_count"]) == (50_000, 0, 1)
    assert pdata["sales_paid"] == pdata["total_cash_in"] == 50_000
