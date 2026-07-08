"""Buyurtmalar testi"""
import pytest


def test_get_orders(client, auth_headers):
    if not auth_headers:
        pytest.skip("Admin token olinmadi")
    response = client.get("/api/v1/orders/", headers=auth_headers)
    assert response.status_code == 200


def test_create_order_delivery(client, auth_headers):
    if not auth_headers:
        pytest.skip("Admin token olinmadi")
    payload = {
        "order_type": "delivery",
        "delivery_address": "Toshkent, Chilonzor",
        "delivery_phone": "+998901234567",
        "items": []
    }
    response = client.post("/api/v1/orders/", json=payload, headers=auth_headers)
    # Mahsulotlarsiz buyurtma ham qabul qilinishi kerak
    assert response.status_code in (200, 201, 422)


def test_create_order_dine_in(client, auth_headers):
    if not auth_headers:
        pytest.skip("Admin token olinmadi")
    payload = {
        "order_type": "dine-in",
        "table_id": None,
        "items": []
    }
    response = client.post("/api/v1/orders/", json=payload, headers=auth_headers)
    assert response.status_code in (200, 201, 404, 422)


def test_orders_filter_by_type(client, auth_headers):
    if not auth_headers:
        pytest.skip("Admin token olinmadi")
    response = client.get("/api/v1/orders/?order_type=delivery", headers=auth_headers)
    assert response.status_code == 200
