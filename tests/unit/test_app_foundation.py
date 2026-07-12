from tests.conftest import TestConfig


def test_health_endpoint(app):
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_index_loads(app):
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Local Clash" in response.data
