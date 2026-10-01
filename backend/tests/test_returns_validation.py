"""VOZVRAT MIQDOR CHEKLOVI — 2026-10-01 auditi testlari.

MUAMMO: `POST /returns/` miqdorni HECH QANDAY tekshirmasdi. 10 dona sotib
50 dona qaytarish mumkin edi -> ombor yo'q tovarga to'lardi, foyda esa
asossiz kamayardi. Bu xato emas, NIYAT bilan ham ishlatiladigan yo'l edi.

Shu yerda qotiriladigan qoidalar:
  1) `order_item_id` bog'langan bo'lsa: qaytariladigan <= sotilgan - qaytarilgan
  2) `pending` vozvrat ham miqdorni BAND qiladi (ikki kassir bir sotuvni
     ikki marta qaytarmasin)
  3) `order_item_id` yo'q bo'lsa — vozvrat O'TADI, lekin OGOHLANTIRISH qaytadi
  4) Nasiyaga sotilganga naqd/karta qaytarish — TO'SILADI (pul yo'qotish yo'li)
  5) `restore_to_inventory=False` (brak) — ombor OSHMAYDI
  6) Z-hisobot `pending` vozvratni SANAMAYDI (kassa yolg'on "ortiqcha" bermasin)

Ishga tushirish:  cd backend && py -m pytest tests/test_returns_validation.py -v
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Category, Customer, CustomerDebt, Inventory, Order, OrderItem,
    Payment, Product, Return, ReturnItem, Shift, StockMovement, User,
)
from schemas import ReturnCreate, ReturnItemCreate

import routers.returns as ret_router
from core.timeutils import utc_now


class _User:
    is_superuser = False
    tenant_id = 1
    id = 5
    role = None
    _active_branch_id = None


# ── Fikstura: 10 dona × 12 000 = 120 000 sotuv (oboy kley misoli) ───────────
@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Category(id=1, name="Qurilish", tenant_id=1))
    s.add(Product(id=1, name="Oboy kley", price=12000, cost_price=8000,
                  category_id=1, tenant_id=1))
    s.add(Product(id=2, name="Shpaklovka", price=30000, cost_price=22000,
                  category_id=1, tenant_id=1))
    s.add(Inventory(id=1, tenant_id=1, product_id=1, quantity=50, unit="dona"))
    s.add(Inventory(id=2, tenant_id=1, product_id=2, quantity=20, unit="dona"))
    s.add(User(id=5, tenant_id=1, full_name="Kassir", phone="+998900000005",
               hashed_password="x"))
    s.add(Customer(id=1, tenant_id=1, name="Anvar", phone="+998901112233",
                   total_debt=0))
    s.commit()
    yield s
    s.close()


def _sale(db, qty=10.0, price=12000.0, oid=1, oi_id=1, product_id=1,
          paid_method="cash", daily=7):
    """Tugallangan sotuv + bitta qator (`order_item_id` bilan)."""
    db.add(Order(id=oid, order_number=f"CHK{oid:05d}", daily_number=daily,
                 tenant_id=1, status="completed", total_amount=qty * price,
                 discount_amount=0, final_amount=qty * price, customer_id=1,
                 created_at=datetime.now(), ingredients_deducted=True))
    db.add(OrderItem(id=oi_id, order_id=oid, product_id=product_id, tenant_id=1,
                     quantity=qty, unit_price=price, unit_cost=8000,
                     total_price=qty * price))
    if paid_method == "credit":
        db.add(Payment(id=oid * 10, tenant_id=1, order_id=oid, cashier_id=5,
                       amount=qty * price, method="credit", status="pending",
                       transaction_id=f"TRXC{oid}"))
    elif paid_method:
        db.add(Payment(id=oid * 10, tenant_id=1, order_id=oid, cashier_id=5,
                       amount=qty * price, method=paid_method, status="paid",
                       transaction_id=f"TRX{oid}"))
    db.commit()


def _ret(db, qty, oi_id=1, method="cash", order_id=1, product_id=1,
         restore=True):
    return ret_router.create_return(
        data=ReturnCreate(
            order_id=order_id, customer_id=1, reason="dislike",
            refund_method=method,
            items=[ReturnItemCreate(product_id=product_id, order_item_id=oi_id,
                                    quantity=qty, unit_price=12000.0,
                                    restore_to_inventory=restore)],
        ),
        db=db, current_user=_User(),
    )


def _approve(db, rid):
    return ret_router.approve_return(return_id=rid, db=db, current_user=_User())


def _inv(db, iid=1):
    return db.query(Inventory).filter(Inventory.id == iid).one().quantity


# ═══ 1) ASOSIY MISOL: 10 ta sotilgan, 3 ta qaytarish ═══════════════════════
def test_uch_ta_qaytarish_otadi(db):
    _sale(db, qty=10)
    r = _ret(db, 3)
    assert r.total_amount == 36000
    assert len(r.items) == 1
    assert r.items[0].order_item_id == 1
    # Bog'langan qator — ogohlantirish BO'LMAYDI
    assert r.warnings == []


def test_keyin_yana_sakkiz_ta_400(db):
    """3 ta qaytardi -> 8 ta yana qaytarib bo'lmaydi (7 tasi qoldi)."""
    _sale(db, qty=10)
    _ret(db, 3)

    with pytest.raises(HTTPException) as e:
        _ret(db, 8)
    assert e.value.status_code == 400
    xabar = e.value.detail
    assert "10" in xabar                    # sotilgan
    assert "3" in xabar                     # allaqachon qaytarilgan
    assert "Oboy kley" in xabar             # mahsulot nomi tushunarli


def test_jami_ONDAN_oshmaydi(db):
    """3 + 7 = 10 -> o'tadi. Undan keyin 1 ta ham o'tmaydi."""
    _sale(db, qty=10)
    _ret(db, 3)
    _ret(db, 7)                             # aynan chegara — o'tishi SHART

    with pytest.raises(HTTPException) as e:
        _ret(db, 1)
    assert e.value.status_code == 400

    jami = sum(ri.quantity for ri in db.query(ReturnItem).all())
    assert jami == 10                       # 10 tadan OSHMADI


def test_bir_sorovda_ikki_marta_ayni_qator_jamlanadi(db):
    """2 × 6 = 12 > 10 — bitta so'rov ichida ham jamlanib tekshiriladi."""
    _sale(db, qty=10)
    with pytest.raises(HTTPException) as e:
        ret_router.create_return(
            data=ReturnCreate(
                order_id=1, customer_id=1, reason="broken", refund_method="cash",
                items=[
                    ReturnItemCreate(product_id=1, order_item_id=1, quantity=6,
                                     unit_price=12000.0),
                    ReturnItemCreate(product_id=1, order_item_id=1, quantity=6,
                                     unit_price=12000.0),
                ],
            ),
            db=db, current_user=_User(),
        )
    assert e.value.status_code == 400


# ═══ 2) `pending` MIQDORNI BAND QILADI ═════════════════════════════════════
def test_pending_vozvrat_miqdorni_band_qiladi(db):
    """Tasdiqlanmagan 10 talik vozvrat bo'lsa — yana qaytarib bo'lmaydi.

    Aks holda ikki kassir 10 talik ikki pending vozvrat yozib, ikkalasi
    tasdiqlanganda 20 dona qaytardi.
    """
    _sale(db, qty=10)
    r = _ret(db, 10)
    assert r.status == "pending"

    with pytest.raises(HTTPException) as e:
        _ret(db, 1)
    assert e.value.status_code == 400


def test_rad_etilgan_vozvrat_miqdorni_bomaydi(db):
    """`rejected` bekor qilingan — miqdor yana bo'shaydi."""
    _sale(db, qty=10)
    r = _ret(db, 10)
    ret_router.reject_return(return_id=r.id, db=db, current_user=_User())

    r2 = _ret(db, 10)                       # endi o'tishi SHART
    assert r2.status == "pending"


# ═══ 3) BOG'LANMAGAN QATOR — o'tadi, lekin ogohlantiradi ═══════════════════
def test_boglanmagan_qator_ogohlantiradi(db):
    """`order_item_id` yo'q -> tekshirib bo'lmaydi, lekin to'silmaydi."""
    _sale(db, qty=10)
    r = ret_router.create_return(
        data=ReturnCreate(
            order_id=1, customer_id=1, reason="broken", refund_method="cash",
            items=[ReturnItemCreate(product_id=1, quantity=999,
                                    unit_price=12000.0)],
        ),
        db=db, current_user=_User(),
    )
    assert r.status == "pending"             # O'TDI (orqaga moslik)
    assert len(r.warnings) == 1
    assert "TEKSHIRA OLMADI" in r.warnings[0]


def test_begona_buyurtma_qatori_400(db):
    """Boshqa buyurtmaning qatoriga suyanib cheklovni aylanib o'tib bo'lmaydi."""
    _sale(db, qty=10, oid=1, oi_id=1)
    _sale(db, qty=2, oid=2, oi_id=2, product_id=2, daily=8)

    with pytest.raises(HTTPException) as e:
        _ret(db, 1, oi_id=2, order_id=1)     # #2 qator #2 buyurtmada
    assert e.value.status_code == 400
    assert "tegishli emas" in e.value.detail


# ═══ 4) NASIYA SOTUVGA NAQD QAYTARISH — TO'SILADI ══════════════════════════
def test_nasiya_sotuvga_naqd_qaytarish_400(db):
    """Nasiya to'lovi `pending` -> naqd qaytarishda hech qanday yozuv
    yaratilmasdi, qarz ham kamaymasdi, Z-hisobot esa naqd kamayganini
    ko'rsatardi. Uchtasi birga = pul yo'qotish."""
    _sale(db, qty=10, paid_method="credit")
    with pytest.raises(HTTPException) as e:
        _ret(db, 3, method="cash")
    assert e.value.status_code == 400
    assert "NASIYAGA" in e.value.detail


def test_nasiya_sotuvga_balansga_qaytarish_otadi(db):
    """To'g'ri usul (credit) — qarz FIFO bilan kamayadi (mavjud xulq)."""
    _sale(db, qty=10, paid_method="credit")
    db.add(CustomerDebt(id=1, tenant_id=1, customer_id=1, order_id=1,
                        amount=120000, paid_amount=0.0, remaining=120000,
                        status="open"))
    db.query(Customer).filter(Customer.id == 1).update({"total_debt": 120000})
    db.commit()

    r = _ret(db, 3, method="credit")
    _approve(db, r.id)

    d = db.query(CustomerDebt).filter(CustomerDebt.id == 1).one()
    assert d.remaining == 120000 - 36000
    assert d.status == "partial"


def test_usul_mos_kelmasa_ogohlantiradi(db):
    """Karta bilan to'langan, naqd qaytarish tanlangan — to'siq EMAS, ogohlantirish."""
    _sale(db, qty=10, paid_method="card")
    r = _ret(db, 3, method="cash")
    assert r.status == "pending"
    assert any("card" in w for w in r.warnings)


# ═══ 5) BRAK: ombor OSHMAYDI ═══════════════════════════════════════════════
def test_brak_ombor_oshmaydi(db):
    """`restore_to_inventory=False` -> buzuq tovar sotiladigan qoldiqqa
    QO'SHILMAYDI (ilgari frontend doim `true` yuborardi)."""
    _sale(db, qty=10)
    oldin = _inv(db)

    r = _ret(db, 3, restore=False)
    _approve(db, r.id)

    assert _inv(db) == oldin                              # ombor TEGILMADI
    assert db.query(StockMovement).count() == 0           # harakat ham yozilmadi
    assert db.query(Return).filter(Return.id == r.id).one().status == "approved"


def test_brak_emas_ombor_oshadi(db):
    """Teskari hol — oddiy vozvrat avvalgidek omborni tiklaydi (regressiya)."""
    _sale(db, qty=10)
    oldin = _inv(db)

    r = _ret(db, 3, restore=True)
    _approve(db, r.id)

    assert _inv(db) == oldin + 3
    assert db.query(StockMovement).count() == 1


# ═══ 6) Z-HISOBOT: `pending` vozvrat sanalmaydi ════════════════════════════
def _shift(db):
    """Ochiq smena.

    ⚠️ `start_time` — AWARE UTC (`utc_now()`), aynan `routers/shift.py:164`
    dagidek. Naive `datetime.now()` yozilsa `to_utc()` uni Toshkent deb
    talqin qilib 5 soat siljitadi va test oynasi teskari bo'lib qoladi
    (start > end) — bu fikstura xatosi, kod xatosi emas.
    """
    sh = Shift(id=1, tenant_id=1, user_id=5, starting_cash=100000.0,
               start_time=utc_now() - timedelta(hours=2))
    db.add(sh)
    db.commit()
    return sh


def test_zhisobot_pending_vozvratni_sanamaydi(db):
    """GOLDEN: tasdiqlanmagan vozvrat kutilgan naqdni KAMAYTIRMASIN.

    Ilgari filtr `status != "rejected"` edi -> pending ham sanalardi va
    yashikdagi haqiqiy naqd "ortiqcha" bo'lib ko'rinardi.
    """
    import routers.shift as shift_router

    _sale(db, qty=10)
    sh = _shift(db)
    _ret(db, 3)                              # PENDING holatda qoldi

    rows = shift_router._returns_in_range(
        db, _User(), shift_router.to_utc(sh.start_time), shift_router.utc_now()
    )
    assert rows == []                        # pending SANALMAYDI


def test_zhisobot_approved_vozvratni_sanaydi(db):
    """Tasdiqlangach — sanaladi (teskari tomon ham qotiriladi)."""
    import routers.shift as shift_router

    _sale(db, qty=10)
    sh = _shift(db)
    r = _ret(db, 3)
    _approve(db, r.id)

    rows = shift_router._returns_in_range(
        db, _User(), shift_router.to_utc(sh.start_time), shift_router.utc_now()
    )
    assert len(rows) == 1
    assert sum(x.total_amount for x in rows) == 36000


def test_zhisobot_rad_etilgan_vozvratni_sanamaydi(db):
    import routers.shift as shift_router

    _sale(db, qty=10)
    sh = _shift(db)
    r = _ret(db, 3)
    ret_router.reject_return(return_id=r.id, db=db, current_user=_User())

    rows = shift_router._returns_in_range(
        db, _User(), shift_router.to_utc(sh.start_time), shift_router.utc_now()
    )
    assert rows == []


# ═══ 7) LOOKUP: chek raqami bo'yicha buyurtmani topish ═════════════════════
def test_lookup_chek_raqami_bilan_topadi(db):
    _sale(db, qty=10)
    out = ret_router.lookup_order(q="CHK00001", db=db, current_user=_User())

    assert out["order_id"] == 1
    assert out["suggested_refund_method"] == "cash"
    assert out["is_credit_sale"] is False
    assert len(out["items"]) == 1
    it = out["items"][0]
    assert it["order_item_id"] == 1
    assert it["sold_qty"] == 10
    assert it["returned_qty"] == 0
    assert it["returnable_qty"] == 10
    assert it["unit_price"] == 12000


def test_lookup_kunlik_raqam_bilan_ham_topadi(db):
    _sale(db, qty=10, daily=7)
    out = ret_router.lookup_order(q="7", db=db, current_user=_User())
    assert out["order_id"] == 1


def test_lookup_qaytarilganni_ayiradi(db):
    """3 ta qaytarilgan bo'lsa — `returnable_qty` 7 chiqadi (kassir cheklovni
    ekranda ko'radi, 400 ga urilmaydi)."""
    _sale(db, qty=10)
    _ret(db, 3)

    out = ret_router.lookup_order(q="CHK00001", db=db, current_user=_User())
    it = out["items"][0]
    assert it["returned_qty"] == 3
    assert it["returnable_qty"] == 7


def test_lookup_nasiya_sotuvda_credit_taklif_qiladi(db):
    _sale(db, qty=10, paid_method="credit")
    out = ret_router.lookup_order(q="CHK00001", db=db, current_user=_User())
    assert out["is_credit_sale"] is True
    assert out["suggested_refund_method"] == "credit"


def test_lookup_topilmasa_404(db):
    with pytest.raises(HTTPException) as e:
        ret_router.lookup_order(q="YOQ999", db=db, current_user=_User())
    assert e.value.status_code == 404


def test_lookup_bekor_qilingan_sotuvni_bermaydi(db):
    _sale(db, qty=10)
    db.query(Order).filter(Order.id == 1).update({"status": "cancelled"})
    db.commit()
    with pytest.raises(HTTPException) as e:
        ret_router.lookup_order(q="CHK00001", db=db, current_user=_User())
    assert e.value.status_code == 404


# ═══ 8) KASRLI MIQDOR (kg) ═════════════════════════════════════════════════
def test_kasrli_qaytarish_ishlaydi(db):
    """0.740 kg sotilgan, 0.240 qaytariladi — qolgan 0.5 dan oshmaydi."""
    _sale(db, qty=0.740, price=25000.0)
    r = _ret(db, 0.240)
    assert r.items[0].quantity == 0.24

    with pytest.raises(HTTPException) as e:
        _ret(db, 0.6)                        # 0.24 + 0.6 > 0.74
    assert e.value.status_code == 400


def test_kasrli_miqdor_uch_xonaga_yaxlitlanadi(db):
    """`ReturnItemCreate` da validator YO'Q edi — 0.3333333 xom saqlanardi."""
    _sale(db, qty=10)
    r = _ret(db, 0.3333333)
    assert r.items[0].quantity == 0.333


def test_kasrli_chegara_aynan_tolaydi(db):
    """0.740 dan 0.740 — float qoldig'i sabab 400 bermasligi SHART."""
    _sale(db, qty=0.740, price=25000.0)
    r = _ret(db, 0.740)
    assert r.items[0].quantity == 0.74


# ═══ 9) JAVOB SHARTNOMASI (API chegarasi) ══════════════════════════════════
#
# Yuqoridagi testlar router FUNKSIYASINI to'g'ridan-to'g'ri chaqiradi, ya'ni
# FastAPI serializatsiyasi va marshrut tartibi TEKSHIRILMAYDI. Ikkisi ham
# jimgina 500 beradigan joy, shuning uchun alohida qotiriladi.

def test_lookup_marshruti_param_dan_OLDIN():
    """`/lookup` `/{return_id}` dan keyin tursa FastAPI uni return_id deb
    o'qib 422 qaytaradi — vozvrat ekrani butunlay ishlamay qolardi."""
    yollar = [(r.path, sorted(r.methods)) for r in ret_router.router.routes]
    i_lookup = next(i for i, (p, _) in enumerate(yollar) if p == "/lookup")
    i_param = next(i for i, (p, m) in enumerate(yollar)
                   if p == "/{return_id}" and "GET" in m)
    assert i_lookup < i_param


def test_warnings_javobga_serializatsiya_bolinadi(db):
    """`warnings` — mapped ustun EMAS, oddiy atribut. `from_attributes` uni
    o'qiy olmasa POST /returns/ har safar 500 berardi."""
    from schemas import ReturnInDB

    _sale(db, qty=10)
    r = _ret(db, 3)
    r.warnings = ["sinov ogohlantirishi"]
    out = ReturnInDB.model_validate(r)
    assert out.warnings == ["sinov ogohlantirishi"]
    assert out.items[0].order_item_id == 1


def test_warnings_atribut_yoq_bolsa_bosh_royxat(db):
    """GET /returns/ va GET /returns/{id} ORM obyektini atributsiz qaytaradi —
    standart qiymat bo'sh ro'yxat bo'lishi shart (aks holda 500).

    ⚠️ `create_return()` qaytargan obyektda `warnings` ATRIBUT bo'lib turadi va
    u sessiya identity-map'ida SHU obyekt bo'lib qoladi (`expire_all()` mapped
    ustunlarni bo'shatadi, oddiy atributni TEGMAYDI). Shuning uchun bu yerda
    router TEGMAGAN toza obyekt yasaladi — GET yo'lidagi holat aynan shunday.
    """
    from schemas import ReturnInDB

    toza = Return(id=99, tenant_id=1, return_number="RET99", total_amount=50.0,
                  reason="other", refund_method="cash", status="approved")
    db.add(toza)
    db.commit()
    db.refresh(toza)

    assert not hasattr(toza, "warnings")
    assert ReturnInDB.model_validate(toza).warnings == []
