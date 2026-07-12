import json
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models.provider import Provider
from app.repositories.provider_repo import create_provider


SAMPLE_YAML = b"""proxies:
  - name: TestNode
    type: ss
    server: 1.2.3.4
    port: 443
    cipher: aes-256-gcm
    password: testpassword
"""


def test_list_providers(app):
    client = app.test_client()
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_create_provider(app):
    client = app.test_client()
    resp = client.post("/api/providers", json={
        "name": "New Provider",
        "source_url": "https://example.com/clash.yaml",
        "schedule": {"type": "disabled"},
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "New Provider"
    assert len(data["public_token"]) == 32


def test_create_provider_validation(app):
    client = app.test_client()
    resp = client.post("/api/providers", json={"name": ""})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "validation"


def test_update_provider(app):
    client = app.test_client()
    with app.app_context():
        p = create_provider("Old", "https://example.com/clash.yaml", {"type": "disabled"})
        pid = p.id
    resp = client.patch(f"/api/providers/{pid}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "New"


def test_delete_provider(app):
    client = app.test_client()
    with app.app_context():
        p = create_provider("Delete", "https://example.com/clash.yaml", {"type": "disabled"})
        pid = p.id
    resp = client.delete(f"/api/providers/{pid}")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "deleted"


def test_rotate_provider(app):
    client = app.test_client()
    with app.app_context():
        p = create_provider("Rotate", "https://example.com/clash.yaml", {"type": "disabled"})
        old_token = p.public_token
        pid = p.id
    resp = client.post(f"/api/providers/{pid}/rotate")
    assert resp.status_code == 200
    assert resp.get_json()["public_token"] != old_token


def test_refresh_provider(app):
    client = app.test_client()
    with app.app_context():
        p = create_provider("Refresh", "https://example.com/clash.yaml", {"type": "disabled"})
        pid = p.id
    resp = client.post(f"/api/providers/{pid}/refresh")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "refreshing"


def test_list_update_runs(app):
    client = app.test_client()
    resp = client.get("/api/update-runs")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_subscription_not_found(app):
    client = app.test_client()
    resp = client.get("/subscriptions/invalid-token")
    assert resp.status_code == 404


def test_subscription_serves_content(app):
    client = app.test_client()
    with app.app_context():
        p = create_provider("Sub", "https://example.com/clash.yaml", {"type": "disabled"})
        token = p.public_token
        from app.services.version_store import VersionStore
        vs = VersionStore(app.config["SUBSCRIPTIONS_DIR"], 5)
        vs.store_version(p.id, SAMPLE_YAML, b"ss://test@1.2.3.4:443#test")
        p.last_success_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        db.session.commit()
    resp = client.get(f"/subscriptions/{token}")
    assert resp.status_code == 200
    assert b"ss://test@1.2.3.4:443#test" in resp.data
    assert "ETag" in resp.headers


def test_subscription_head(app):
    client = app.test_client()
    with app.app_context():
        p = create_provider("HeadSub", "https://example.com/clash.yaml", {"type": "disabled"})
        token = p.public_token
        from app.services.version_store import VersionStore
        vs = VersionStore(app.config["SUBSCRIPTIONS_DIR"], 5)
        vs.store_version(p.id, SAMPLE_YAML, b"ss://test@1.2.3.4:443#test")
        p.last_success_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        db.session.commit()
    resp = client.head(f"/subscriptions/{token}")
    assert resp.status_code == 200
    assert resp.data == b""
