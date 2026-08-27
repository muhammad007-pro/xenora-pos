"""Mahsulotlar CRUD testi.

⚠️ 2026-08-27: bu testlar `admin_token` fixture buzilgani uchun UZOQ VAQT
SKIP bo'lib kelgan (hech qachon yugurmagan). Fixture tuzatilgach ikkita
haqiqiy nomuvofiqlik chiqdi va shu yerda to'g'rilandi:

  * `category_id` — `ProductBase` da MAJBURIY (`schemas.py:219`, `int`, Optional
    EMAS). Test `None` yuborardi → 422. Endi avval kategoriya yaratiladi.
  * Yaratilgan mahsulot tekshiruvi `if status in (200,201)` shartiga o'ralgan edi
    — ya'ni endpoint sinsa ham test jim o'tardi. Endi to'g'ridan-to'g'ri assert.
"""
import pytest


@pytest.fixture()
def category_id(client, auth_headers):
    """Mahsulot uchun kategoriya (majburiy bog'liqlik)."""
    r = client.post("/api/v1/categories/",
                    json={"name": "Test kategoriya"}, headers=auth_headers)
    assert r.status_code in (200, 201), f"kategoriya yaratilmadi: {r.status_code} {r.text}"
    return r.json()["id"]


def test_get_products_authenticated(client, auth_headers):
    response = client.get("/api/v1/products/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data or isinstance(data, list)


def test_create_product(client, auth_headers, category_id):
    payload = {
        "name": "Test Mahsulot",
        "price": 15000,
        "category_id": category_id,
        "is_available": True,
        "sale_unit": "pcs",
    }
    response = client.post("/api/v1/products/", json=payload, headers=auth_headers)
    assert response.status_code in (200, 201), response.text
    data = response.json()
    assert data["name"] == "Test Mahsulot"
    assert data["price"] == 15000


def test_create_product_kategoriyasiz_422(client, auth_headers):
    """category_id majburiy — shartnomani qulflab qo'yamiz."""
    response = client.post("/api/v1/products/",
                           json={"name": "Kategoriyasiz", "price": 1000},
                           headers=auth_headers)
    assert response.status_code == 422


def test_get_categories(client, auth_headers):
    response = client.get("/api/v1/categories/", headers=auth_headers)
    assert response.status_code == 200


def test_unauthorized_create_product(client):
    payload = {"name": "Test", "price": 1000}
    response = client.post("/api/v1/products/", json=payload)
    assert response.status_code == 401
