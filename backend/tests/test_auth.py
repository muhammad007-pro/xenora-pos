"""Autentifikatsiya testi.

⚠️ 2026-08-27: bu fayl `pytest` ni import qilmasdan `pytest.skip` chaqirardi
(NameError) va `username="admin"` bilan login qilardi — BOSQICH 38 dan beri
login kaliti TELEFON (`auth_service.authenticate_user`). Ikkalasi ham tuzatildi;
urug' foydalanuvchi `conftest.py` da yaratiladi.
"""
import pytest

from tests.conftest import (
    SEED_ADMIN_PHONE, SEED_ADMIN_PASSWORD, SEED_ADMIN_USERNAME,
)


def test_login_success(client):
    response = client.post("/api/v1/auth/login", data={
        "username": SEED_ADMIN_PHONE,      # OAuth2 form maydoni; qiymat — telefon
        "password": SEED_ADMIN_PASSWORD,
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client):
    response = client.post("/api/v1/auth/login", data={
        "username": SEED_ADMIN_PHONE,
        "password": "ataylab_notogri_parol",
    })
    assert response.status_code in (400, 401, 422)


def test_login_nomavjud_telefon(client):
    response = client.post("/api/v1/auth/login", data={
        "username": "+998900000777",
        "password": SEED_ADMIN_PASSWORD,
    })
    assert response.status_code in (400, 401)


def test_login_username_bilan_ishlamaydi(client):
    """Login kaliti TELEFON — username bilan kirib bo'lmasligi SHART.

    Aynan shu noto'g'ri taxmin fixture'ni buzib, integratsiya testlarini
    yarim yil davomida jimgina skip qildirgan edi.
    """
    response = client.post("/api/v1/auth/login", data={
        "username": SEED_ADMIN_USERNAME,   # "admin" — telefon emas
        "password": SEED_ADMIN_PASSWORD,
    })
    assert response.status_code in (400, 401)


def test_login_missing_fields(client):
    response = client.post("/api/v1/auth/login", data={})
    assert response.status_code == 422


def test_me_authenticated(client, auth_headers):
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["username"] == SEED_ADMIN_USERNAME
    assert data["is_superuser"] is True


def test_me_unauthenticated(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_protected_endpoint_without_token(client):
    response = client.get("/api/v1/products/")
    assert response.status_code == 401
