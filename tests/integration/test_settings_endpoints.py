def test_get_settings_returns_defaults(app):
    client = app.test_client()
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["rsyslog_host"] is None
    assert body["rsyslog_port"] == 514
    assert body["rsyslog_proto"] == "tcp"
    assert body["rsyslog_facility"] == "local0"
    assert body["log_retention_days"] == 7


def test_patch_settings_writes_and_rebuilds_log_sink(app):
    client = app.test_client()
    resp = client.patch(
        "/api/settings",
        json={
            "rsyslog_host": "10.0.0.42",
            "rsyslog_port": 1514,
            "rsyslog_proto": "udp",
            "rsyslog_facility": "local3",
            "log_retention_days": 14,
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["rsyslog_host"] == "10.0.0.42"
    assert body["rsyslog_port"] == 1514
    assert body["rsyslog_proto"] == "udp"
    assert body["log_retention_days"] == 14
    # GET reflects the new values.
    body2 = client.get("/api/settings").get_json()
    assert body2["rsyslog_host"] == "10.0.0.42"
    # LogSink was rebuilt — its host attribute reflects the saved value.
    sink = app.extensions.get("log_sink")
    assert sink is not None
    assert sink.host == "10.0.0.42"


def test_patch_settings_validation_rejects_bad_proto(app):
    client = app.test_client()
    resp = client.patch("/api/settings", json={"rsyslog_proto": "gopher"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "validation"


def test_patch_settings_validation_rejects_bad_port(app):
    client = app.test_client()
    resp = client.patch("/api/settings", json={"rsyslog_port": 70000})
    assert resp.status_code == 400


def test_patch_settings_validation_rejects_zero_retention(app):
    client = app.test_client()
    resp = client.patch("/api/settings", json={"log_retention_days": 0})
    assert resp.status_code == 400


def test_patch_settings_empty_host_disables_log_sink(app):
    client = app.test_client()
    # Set then unset.
    client.patch("/api/settings", json={"rsyslog_host": "10.0.0.42"})
    client.patch("/api/settings", json={"rsyslog_host": ""})
    sink = app.extensions.get("log_sink")
    assert sink is not None
    assert sink.host is None
    assert sink.enabled is False
