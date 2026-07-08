"""Mahsulotlar CRUD testi"""
import pytest


def test_get_products_authenticated(client, auth_headers):
    if not auth_headers:
        pytest.skip("Admin token olinmadi")
    response = client.get("/api/v1/products/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data or isinstance(data, list)


def test_create_product(client, auth_headers):
    if not auth_headers:
        pytest.skip("Admin token olinmadi")
    payload = {
        "name": "Test Mahsulot",
        "price": 15000,
        "category_id": None,
        "is_available": True,
        "sale_unit": "pcs"
    }
    response = client.post("/api/v1/products/", json=payload, headers=auth_headers)
    assert response.status_code in (200, 201)
    if response.status_code in (200, 201):
        data = response.json()
        assert data["name"] == "Test Mahsulot"
        assert data["price"] == 15000
        return data["id"]


def test_get_categories(client, auth_headers):
    if not auth_headers:
        pytest.skip("Admin token olinmadi")
    response = client.get("/api/v1/categories/", headers=auth_headers)
    assert response.status_code == 200


def test_unauthorized_create_product(client):
    payload = {"name": "Test", "price": 1000}
    response = client.post("/api/v1/products/", json=payload)
    assert response.status_code == 401
