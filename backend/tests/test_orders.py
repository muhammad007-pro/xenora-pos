"""Buyurtmalar testi.

⚠️ 2026-08-27: bu testlar `admin_token` fixture buzilgani uchun UZOQ VAQT
SKIP bo'lib kelgan. Fixture tuzatilgach ular haqiqatan yugurdi va buyurtma
YARATISH testlari 500 berdi. Sabab tekshirildi:

    sqlite3.OperationalError: no such function: timezone

`OrderService._next_daily_number()` (order_service.py:38) kunlik chek raqamini
`func.timezone('Asia/Tashkent', Order.created_at)` bilan hisoblaydi — bu
**PostgreSQL funksiyasi**, SQLite'da yo'q. Ya'ni bu PROD XATOSI EMAS
(prod PostgreSQL'da ishlaydi — 2026-08-27 da jonli sotuv o'tgani buni tasdiqladi),
balki test bazasi (sqlite) cheklovi.

QAROR: bu testlar dialektga qarab SKIP bo'ladi — sababi ANIQ ko'rinadi va test
bazasi PostgreSQL'ga o'tkazilsa AVTOMATIK yugurib ketadi. Bu eski "if not
auth_headers: skip" dan tubdan farq qiladi: u hamma narsani shartsiz va
JIMGINA yashirar edi.

Ombor/pul yo'lining haqiqiy qamrovi boshqa joyda:
`test_credit_sale.py`, `test_customer_return.py`, `test_revenue_net.py` —
ular OrderService/PaymentService ni to'g'ridan-to'g'ri chaqiradi.
"""
import pytest
from sqlalchemy import inspect

from tests.conftest import engine

# Kunlik chek raqami PostgreSQL `timezone()` ga bog'liq → sqlite'da yaratib bo'lmaydi.
_PG = engine.dialect.name == "postgresql"
pg_kerak = pytest.mark.skipif(
    not _PG,
    reason=(
        "Buyurtma yaratish PostgreSQL `timezone()` funksiyasini talab qiladi "
        "(_next_daily_number). Joriy test bazasi: "
        f"{engine.dialect.name}. Test bazasi PostgreSQL bo'lsa avtomatik yugadi."
    ),
)


def test_get_orders(client, auth_headers):
    """O'qish yo'li dialektdan mustaqil — har doim yuguradi."""
    response = client.get("/api/v1/orders/", headers=auth_headers)
    assert response.status_code == 200


def test_orders_filter_by_type(client, auth_headers):
    response = client.get("/api/v1/orders/?order_type=delivery", headers=auth_headers)
    assert response.status_code == 200


def test_orders_unauthorized(client):
    """Autentifikatsiyasiz buyurtmalar ko'rinmasligi SHART."""
    assert client.get("/api/v1/orders/").status_code == 401


@pg_kerak
def test_create_order_delivery(client, auth_headers):
    payload = {
        "order_type": "delivery",
        "delivery_address": "Toshkent, Chilonzor",
        "delivery_phone": "+998901234567",
        "items": [],
    }
    response = client.post("/api/v1/orders/", json=payload, headers=auth_headers)
    assert response.status_code in (200, 201, 422), response.text


@pg_kerak
def test_create_order_dine_in(client, auth_headers):
    payload = {"order_type": "dine-in", "table_id": None, "items": []}
    response = client.post("/api/v1/orders/", json=payload, headers=auth_headers)
    assert response.status_code in (200, 201, 404, 422), response.text
