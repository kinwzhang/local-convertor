import json


def test_logs_endpoint_returns_appended_entries(app):
    client = app.test_client()
    log_store = app.extensions["log_store"]
    log_store.append({"event": "refresh.success", "provider_id": 1, "provider_name": "p1"})
    log_store.append({"event": "refresh.unchanged", "provider_id": 2, "provider_name": "p2"})
    resp = client.get("/api/logs")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "entries" in body
    assert len(body["entries"]) == 2
    # newest-first
    assert body["entries"][0]["event"] == "refresh.unchanged"
    assert body["entries"][1]["event"] == "refresh.success"


def test_logs_endpoint_filters_by_provider(app):
    client = app.test_client()
    log_store = app.extensions["log_store"]
    log_store.append({"event": "refresh.success", "provider_id": 1})
    log_store.append({"event": "refresh.success", "provider_id": 2})
    resp = client.get("/api/logs?provider_id=2")
    body = resp.get_json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["provider_id"] == 2


def test_logs_endpoint_caps_at_1000(app):
    client = app.test_client()
    log_store = app.extensions["log_store"]
    for i in range(3):
        log_store.append({"event": "refresh.success", "provider_id": i})
    # request 9999 — must clamp to 1000
    resp = client.get("/api/logs?limit=9999")
    body = resp.get_json()
    assert len(body["entries"]) == 3  # only 3 exist; cap is upper bound


def test_logs_clear_truncates_and_reports_count(app):
    client = app.test_client()
    log_store = app.extensions["log_store"]
    log_store.append({"event": "refresh.success", "provider_id": 1})
    log_store.append({"event": "refresh.unchanged", "provider_id": 2})
    resp = client.post("/api/logs/clear")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["cleared"] == 2
    # File should now be empty.
    assert log_store.entries() == []
