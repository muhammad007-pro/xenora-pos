"""Health va asosiy endpointlar testi"""


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "version" in data


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "version" in data


def test_docs_available(client):
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
