"""Autentifikatsiya testi"""


def test_login_success(client):
    response = client.post("/api/v1/auth/login", data={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client):
    response = client.post("/api/v1/auth/login", data={
        "username": "admin",
        "password": "wrongpassword"
    })
    assert response.status_code in (400, 401, 422)


def test_login_missing_fields(client):
    response = client.post("/api/v1/auth/login", data={})
    assert response.status_code == 422


def test_me_authenticated(client, auth_headers):
    if not auth_headers:
        pytest.skip("Admin token olinmadi")
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "admin"
    assert data["is_superuser"] is True


def test_me_unauthenticated(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_protected_endpoint_without_token(client):
    response = client.get("/api/v1/products/")
    assert response.status_code == 401
