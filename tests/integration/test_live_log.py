"""Integration tests for the live-update-log pipeline.

These tests cover B-R2: verify that the SSE endpoint delivers the frozen
event schema, that the polling endpoint returns runs in the expected
shape, and that the JS client source handles dedup, ordering, and
bounded history correctly.

The actual `publish_event()` call inside the orchestrator is Worker A's
A-R3 task; once it lands, these tests will exercise a complete SSE
end-to-end flow without modification.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.routes import events as events_module


def _read_first_event(client, timeout=2.0):
    """Open the SSE stream, capture the first `event: ...\\ndata: ...\\n\\n`
    chunk, and return it decoded as a string. Returns None on timeout.
    """
    with client.get("/api/events") as response:
        assert response.status_code == 200
        assert response.content_type.startswith("text/event-stream")
        body = b""
        for chunk in response.response:
            body += chunk
            if b"\n\n" in body and b"event:" in body:
                return body.decode("utf-8")
        return body.decode("utf-8")


def _read_until_connected(client):
    """Read the stream until the initial `event: connected` chunk arrives."""
    with client.get("/api/events") as response:
        body = b""
        for chunk in response.response:
            body += chunk
            if b"event: connected" in body:
                return body.decode("utf-8")
        return body.decode("utf-8")


def test_sse_publishes_frozen_event_shape(client):
    """The event payload must match the frozen schema in shared_contracts.md."""
    # Subscribe first so the queue is registered before we publish.
    with client.get("/api/events") as response:
        # Give the streaming generator a chance to register its queue.
        # We use the response itself as a barrier by reading one chunk.
        chunks = []
        for chunk in response.response:
            chunks.append(chunk)
            if b"event: connected" in b"".join(chunks):
                break

        # Now publish.
        sample_event = {
            "run_id": 42,
            "provider_id": 1,
            "provider_name": "test",
            "trigger": "manual",
            "stage": "querying",
            "status": "running",
            "message": "Fetching from provider",
            "created_at": "2026-07-12T20:00:00+00:00",
            "completed_at": None,
        }
        events_module.publish_event(sample_event)

        # Read the next chunk.
        for chunk in response.response:
            chunks.append(chunk)
            body = b"".join(chunks)
            if b"\n\n" in body and b"data: " in body:
                # Find the data: line that follows event: update
                payload = body.decode("utf-8")
                if "event: update" in payload:
                    break

    payload = b"".join(chunks).decode("utf-8")
    # Find the update event data line
    match = re.search(r"event: update\ndata: (\{.*?\})\n\n", payload)
    assert match, f"no update event in stream: {payload!r}"
    parsed = json.loads(match.group(1))
    assert parsed["run_id"] == 42
    assert parsed["stage"] == "querying"
    assert parsed["provider_name"] == "test"
    assert parsed["status"] == "running"


def test_sse_sends_initial_connected_event(client):
    """The first chunk must be `event: connected\\ndata: {}`."""
    payload = _read_until_connected(client)
    assert "event: connected" in payload
    assert "data: {}" in payload


# ---- JS source-inspection tests ----------------------------------------

JS_PATH = Path(__file__).resolve().parent.parent.parent / "app" / "static" / "app.js"
JS_SOURCE = JS_PATH.read_text(encoding="utf-8")


def test_js_uses_data_id_for_dedup():
    """Rendered log lines must carry a data-id so polling/SSE share state."""
    assert re.search(r'el\(\s*["\']div["\'][\s\S]{0,200}"data-id"', JS_SOURCE), (
        "app.js does not stamp data-id on appended log lines"
    )
    assert "seenRunIds" in JS_SOURCE
    assert "seenRunIds.add" in JS_SOURCE
    assert "seenRunIds.has" in JS_SOURCE


def test_js_polling_reverses_newest_first():
    """Polling returns runs newest-first; the client must reverse for ordering."""
    assert re.search(
        r"runs[\s\S]{0,40}\.reverse\(\)|runs\.slice\(\)\.reverse\(\)",
        JS_SOURCE,
    ), "polling does not reverse newest-first ordering"


def test_js_log_history_bounded():
    """MAX_LOG_LINES cap must exist and be enforced when lines are appended."""
    assert "MAX_LOG_LINES" in JS_SOURCE
    assert re.search(
        r"children\.length\s*>\s*MAX_LOG_LINES[\s\S]{0,300}removeChild",
        JS_SOURCE,
    ), "log history does not prune at the configured maximum"


def test_js_sse_polling_fallback_paths_exist():
    assert "EventSource" in JS_SOURCE
    assert "setTimeout(startSSE" in JS_SOURCE
    assert "startPolling" in JS_SOURCE


def test_js_output_is_escaped_in_log_lines():
    """Provider names and messages must pass through escape(), not innerHTML."""
    # The JS uses a local `providerName` variable for defensive rendering,
    # but the escape() call must wrap it.
    assert re.search(r'escape\(providerName\)', JS_SOURCE), (
        "providerName must be wrapped in escape()"
    )
    assert re.search(r'escape\(line\.message\)', JS_SOURCE)
    assert "innerHTML" not in JS_SOURCE, "log lines should not use innerHTML"


def test_js_no_source_url_logged_in_messages():
    """The JS client must never include source_url in log entries."""
    match = re.search(r"function appendLog[\s\S]+?\n    \}", JS_SOURCE)
    assert match, "appendLog function not found"
    append_log_body = match.group(0)
    assert "source_url" not in append_log_body


def test_js_handles_reconnect():
    """Stream drops must trigger reconnect, not stop polling forever."""
    assert re.search(r'addEventListener\(\s*["\']error["\']', JS_SOURCE)
    assert re.search(r'close\(\)[\s\S]{0,200}startSSE', JS_SOURCE), (
        "no reconnect path after EventSource error"
    )


# ---- Orchestrator event-shape regression guards -----------------------
# These tests exercise the real Worker A orchestrator (A-R3) and assert
# that publish_event() emits every field the frozen contract requires.
# If the orchestrator drops a field, these tests fail.

REQUIRED_EVENT_FIELDS = {
    "run_id", "provider_id", "provider_name", "trigger",
    "stage", "status", "message", "created_at",
}


def test_orchestrator_publishes_frozen_event_fields(client, app):
    """A-R3 regression guard: every publish_event call must include the
    full frozen event shape so the JS client can render provider_name,
    trigger, and timestamp without fallback hacks."""
    import time as _time
    from unittest.mock import patch
    from app.repositories import provider_repo
    from app.services.fetcher import FetchResult
    from app.services.updater import RefreshOrchestrator

    p = provider_repo.create_provider(
        name="event-shape-test",
        source_url="https://example.com/clash.yaml",
        schedule={"type": "disabled"},
    )
    raw = (
        b"proxies:\n"
        b"  - name: ok\n"
        b"    type: ss\n"
        b"    server: 1.1.1.1\n"
        b"    port: 8388\n"
        b"    cipher: aes-256-gcm\n"
        b"    password: pw\n"
    )
    fake = FetchResult(content=raw, content_type="text/yaml", status_code=200)

    orch = RefreshOrchestrator(app)
    inbox = []
    with client.get("/api/events") as response:
        chunks = []
        for chunk in response.response:
            chunks.append(chunk)
            if b"event: connected" in b"".join(chunks):
                break
        with patch.object(orch.fetcher, "fetch", return_value=fake):
            orch.refresh(p.id, trigger="manual")
        deadline = _time.monotonic() + 3.0
        for chunk in response.response:
            chunks.append(chunk)
            body = b"".join(chunks)
            while b"event: update\n" in body:
                idx = body.index(b"event: update\n")
                rest = body[idx:]
                d_idx = rest.find(b"data: ")
                e_idx = rest.find(b"\n\n", d_idx)
                if d_idx == -1 or e_idx == -1:
                    break
                payload = rest[d_idx + len(b"data: "):e_idx]
                inbox.append(json.loads(payload.decode("utf-8")))
                body = rest[e_idx + 2:]
            if _time.monotonic() > deadline:
                break

    assert inbox, "no events received from orchestrator"
    for ev in inbox:
        missing = REQUIRED_EVENT_FIELDS - set(ev.keys())
        assert not missing, (
            f"orchestrator event missing required fields: {missing}; event={ev}"
        )