"""End-to-end management flow tests (B-R3).

These tests exercise the full provider lifecycle through the management API
(the same surface the JS client calls). They prove that the API supports:

- Provider creation, retrieval, edit (PATCH), refresh, rotate, delete.
- Schedule validation behaviour.
- Validation error responses that preserve client UX.

For each API behavior the tests also assert that the corresponding JS
handler exists and uses the right HTTP verb + payload shape. This catches
the failure mode where someone removes an action handler or payload field
without updating the JS — the static-analysis test fails even though the
server still works.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from app.extensions import db
from app.repositories import provider_repo


JS_PATH = Path(__file__).resolve().parent.parent.parent / "app" / "static" / "app.js"
JS_SOURCE = JS_PATH.read_text(encoding="utf-8")
HTML_PATH = Path(__file__).resolve().parent.parent.parent / "app" / "templates" / "index.html"
HTML_SOURCE = HTML_PATH.read_text(encoding="utf-8")


# Worker A's POST /api/providers and POST /api/providers/<id>/refresh spawn
# real background threads that touch the database. In tests we replace those
# threads with no-ops so we don't race the orchestrator against our assertions.
@pytest.fixture(autouse=True)
def _stub_refresh_threads():
    class _NoopThread:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            pass
    with patch("app.routes.api.threading.Thread", _NoopThread):
        yield


# ---- End-to-end management flow ----------------------------------------

def test_create_provider_full_lifecycle(client):
    """Create → list → update → rotate → delete."""
    response = client.post("/api/providers", json={
        "name": "lifecycle-test",
        "source_url": "https://example.com/clash.yaml",
        "schedule": {"type": "daily", "time_of_day": "04:00"},
    })
    assert response.status_code == 201
    body = response.get_json()
    provider_id = body["id"]
    assert body["name"] == "lifecycle-test"
    assert body["source_url"] == "https://example.com/clash.yaml"
    assert body["public_token"] and len(body["public_token"]) == 32

    # List
    response = client.get("/api/providers")
    assert response.status_code == 200
    assert any(p["id"] == provider_id for p in response.get_json())

    # Update (PATCH)
    response = client.patch(f"/api/providers/{provider_id}", json={
        "name": "renamed",
        "schedule": {"type": "weekly", "day_of_week": 1, "time_of_day": "09:00"},
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body["name"] == "renamed"
    assert body["schedule"]["type"] == "weekly"
    assert body["schedule"]["day_of_week"] == 1

    # Rotate
    response = client.post(f"/api/providers/{provider_id}/rotate")
    assert response.status_code == 200
    new_token = response.get_json()["public_token"]
    assert new_token != body["public_token"]

    # Refresh — stubbed, just check status
    response = client.post(f"/api/providers/{provider_id}/refresh")
    assert response.status_code == 200

    # Delete
    response = client.delete(f"/api/providers/{provider_id}")
    assert response.status_code == 200


def test_create_provider_validates_required_fields(client):
    response = client.post("/api/providers", json={"name": ""})
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "validation"
    assert "name" in body["details"]


def test_update_provider_returns_404_for_unknown(client):
    response = client.patch("/api/providers/999999", json={"name": "x"})
    assert response.status_code == 404


def test_refresh_unknown_provider_returns_404(client):
    response = client.post("/api/providers/999999/refresh")
    assert response.status_code == 404


def test_delete_unknown_provider_returns_404(client):
    response = client.delete("/api/providers/999999")
    assert response.status_code == 404


def test_list_update_runs_supports_provider_filter(client):
    """Worker B's polling fallback relies on this filter for scoped queries."""
    response = client.get("/api/update-runs?provider_id=999999")
    assert response.status_code == 200
    assert response.get_json() == []


# ---- JS handler coverage (B-R3 acceptance) -----------------------------

def test_js_has_edit_handler():
    """Inline editing must exist in the JS client."""
    assert re.search(r"beginEdit|editRow", JS_SOURCE), "no inline-edit handler"


def test_js_sends_patch_with_correct_payload_keys():
    """The PATCH payload must include name, source_url, enabled, schedule."""
    match = re.search(
        r"/api/providers/\$\{p\.id\}[\s\S]{0,400}body:\s*JSON\.stringify\(\s*\{([^}]+)\}",
        JS_SOURCE,
    )
    assert match, "no PATCH payload found"
    keys = match.group(1)
    for required in ("name", "source_url", "enabled", "schedule"):
        assert required in keys, f"PATCH payload missing {required}"


def test_js_uses_method_PATCH():
    """Method must be PATCH (not POST) for edits."""
    assert re.search(r"method:\s*[\"']PATCH[\"']", JS_SOURCE)


def test_js_create_uses_POST_with_name_and_source_url():
    """createProvider must send POST with name and source_url."""
    match = re.search(
        r"api\(\s*[\"']/api/providers[\"'][\s\S]{0,500}JSON\.stringify",
        JS_SOURCE,
    )
    assert match, "no POST /api/providers call found"
    body = match.group(0)
    assert "name" in body and "source_url" in body
    assert "POST" in body


def test_js_refresh_calls_correct_endpoint():
    """The Refresh button must POST to /api/providers/<id>/refresh."""
    assert re.search(
        r"/api/providers/\$\{[^}]+\}/refresh[\s\S]{0,80}method:\s*[\"']POST[\"']",
        JS_SOURCE,
    ), "Refresh button is not wired to /refresh"


def test_js_rotate_calls_correct_endpoint():
    assert re.search(
        r"/api/providers/\$\{[^}]+\}/rotate[\s\S]{0,80}method:\s*[\"']POST[\"']",
        JS_SOURCE,
    ), "Rotate button is not wired to /rotate"


def test_js_delete_calls_correct_endpoint():
    assert re.search(
        r"/api/providers/\$\{[^}]+\}[\s\S]{0,80}method:\s*[\"']DELETE[\"']",
        JS_SOURCE,
    ), "Delete button is not wired to DELETE /api/providers/<id>"


def test_js_confirms_destructive_actions():
    """Rotate and Delete must require explicit user confirmation."""
    delete_match = re.search(r"async function deleteProvider[\s\S]+?\n    \}", JS_SOURCE)