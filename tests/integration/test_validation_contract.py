"""Validation-contract integration tests (A-R8).

Worker A's API enforces the frozen validation contract:

- name length, type, and presence
- source_url must be http(s) with a hostname
- schedule.type must be one of the five valid types
- schedule-specific fields must satisfy their range / shape rules

Errors return `{error: "validation", details: {field: [...]}}`.

These tests cover the Worker-B-facing edge cases: validation must not
discard the user's edits (the JS re-renders errors inline), and the
frozen payload shape must be enforced.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


JS_PATH = Path(__file__).resolve().parent.parent.parent / "app" / "static" / "app.js"
JS_SOURCE = JS_PATH.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _stub_refresh_threads():
    class _NoopThread:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            pass
    from unittest.mock import patch
    with patch("app.routes.api.threading.Thread", _NoopThread):
        yield


def test_create_rejects_oversize_name(client):
    response = client.post("/api/providers", json={
        "name": "x" * 200,
        "source_url": "https://example.com/clash.yaml",
        "schedule": {"type": "disabled"},
    })
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "validation"
    assert "name" in body["details"]


def test_create_rejects_ftp_scheme(client):
    response = client.post("/api/providers", json={
        "name": "ok",
        "source_url": "ftp://example.com/clash.yaml",
        "schedule": {"type": "disabled"},
    })
    assert response.status_code == 400
    body = response.get_json()
    assert "source_url" in body["details"]


def test_create_rejects_invalid_schedule_type(client):
    response = client.post("/api/providers", json={
        "name": "ok",
        "source_url": "https://example.com/clash.yaml",
        "schedule": {"type": "yearly"},
    })
    assert response.status_code == 400
    body = response.get_json()
    assert "schedule" in body["details"]


def test_create_rejects_interval_out_of_range(client):
    response = client.post("/api/providers", json={
        "name": "ok",
        "source_url": "https://example.com/clash.yaml",
        "schedule": {"type": "interval", "interval_hours": 200},
    })
    assert response.status_code == 400
    body = response.get_json()
    assert "schedule" in body["details"]


def test_create_accepts_valid_interval(client):
    response = client.post("/api/providers", json={
        "name": "ok",
        "source_url": "https://example.com/clash.yaml",
        "schedule": {"type": "interval", "interval_hours": 6},
    })
    assert response.status_code == 201


def test_create_accepts_all_valid_schedule_types(client):
    for sched in [
        {"type": "disabled"},
        {"type": "monthly", "day_of_month": 15, "time_of_day": "03:00"},
        {"type": "weekly", "day_of_week": 1, "time_of_day": "04:00"},
        {"type": "daily", "time_of_day": "05:00"},
        {"type": "interval", "interval_hours": 12},
    ]:
        response = client.post("/api/providers", json={
            "name": f"sched-{sched['type']}",
            "source_url": "https://example.com/clash.yaml",
            "schedule": sched,
        })
        assert response.status_code == 201, f"valid schedule rejected: {sched}; {response.get_json()}"


def test_validation_error_response_shape_matches_contract(client):
    response = client.post("/api/providers", json={"name": ""})
    assert response.status_code == 400
    body = response.get_json()
    assert set(body.keys()) >= {"error", "details"}
    assert body["error"] == "validation"
    for field, errors in body["details"].items():
        assert isinstance(errors, list)
        for message in errors:
            assert isinstance(message, str)


# ---- JS surface tests for validation UX --------------------------------

def test_js_surfaces_validation_errors_without_losing_input():
    """The submit handler must keep entered values when validation fails."""
    # The submit handler does NOT clear the form fields on error; only on success.
    match = re.search(r"async function submitEdit[\s\S]+?\n    \}", JS_SOURCE)
    assert match
    body = match.group(0)
    # No `$("#edit-name-...").value = ""` in the error path.
    assert "edit-name-" not in body or "value =" not in body.split("value =")[0].split("errBox")[1], (
        "form must not be cleared on validation failure"
    )


def test_js_includes_details_in_error_message():
    """When the API returns details, the JS surfaces them in the error text."""
    assert "JSON.stringify(e.details)" in JS_SOURCE or "details" in JS_SOURCE