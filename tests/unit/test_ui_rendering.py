"""UI and API integration tests.

These tests cover:
- The management page renders the expected markup
- Static assets are served
- API endpoints (provider CRUD stub, update-runs stub) return valid JSON
- The SSE stream sends the initial 'connected' event
- Provider source URLs never appear in any public response (redaction)
- Subscription token lookup returns 404 for unknown tokens
"""
from __future__ import annotations

import json

import pytest


def test_index_page_renders(client):
    with client.get("/") as response:
        assert response.status_code == 200
        assert b"Local Clash Subscription Converter" in response.data
        assert b"app.css" in response.data
        assert b"app.js" in response.data


def test_static_css_served(client):
    with client.get("/static/app.css") as response:
        assert response.status_code == 200
        assert b"background" in response.data or b"--bg" in response.data


def test_static_js_served(client):
    with client.get("/static/app.js") as response:
        assert response.status_code == 200
        assert b"/api/providers" in response.data
        assert b"/api/events" in response.data


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    # Worker A's health check (A-R1) also reports database reachability.
    assert "database" in body


def test_api_providers_list_returns_json(client):
    response = client.get("/api/providers")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_api_update_runs_returns_json(client):
    response = client.get("/api/update-runs")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_sse_endpoint_sends_connected_event(client):
    with client.get("/api/events") as response:
        assert response.status_code == 200
        assert response.content_type.startswith("text/event-stream")
        body = b""
        for chunk in response.response:
            body += chunk
            if b"connected" in body:
                break
        assert b"data: {" in body
        assert b"connected" in body


def test_subscription_unknown_token_returns_404(client):
    response = client.get("/subscriptions/00000000000000000000000000000000")
    assert response.status_code == 404


def test_subscription_unknown_token_head_returns_404(client):
    response = client.head("/subscriptions/00000000000000000000000000000000")
    assert response.status_code == 404


def test_subscription_url_format_in_index(client):
    """The JS client must reference /subscriptions/<token> URLs."""
    with client.get("/static/app.js") as response:
        body = response.data.decode("utf-8")
        assert "/subscriptions/${" in body or "/subscriptions/" in body


def test_no_source_url_leak_in_index_html(client):
    """The management page must not include any provider source URL placeholder.

    The placeholder "https://example.com/clash.yaml" is permitted as an
    input hint to teach the user the URL format; what we forbid is rendering
    a real `source_url` value or query-string secrets in the HTML.
    """
    response = client.get("/")
    body = response.data.decode("utf-8")
    assert "source_url" not in body
    # The placeholder appears only as an HTML attribute value
    assert 'placeholder="https://example.com/clash.yaml"' in body
