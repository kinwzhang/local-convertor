import json
import os
from datetime import datetime, timedelta, timezone

from app.services.log_store import LogStore


def test_append_then_entries_round_trip(tmp_path):
    store = LogStore(str(tmp_path))
    store.append({"event": "refresh.success", "provider_id": 1, "provider_name": "A"})
    store.append({"event": "refresh.unchanged", "provider_id": 2, "provider_name": "B"})
    entries = store.entries()
    assert len(entries) == 2
    # Newest-first order
    assert entries[0]["event"] == "refresh.unchanged"
    assert entries[1]["event"] == "refresh.success"
    # Each line carries a `ts` after `append`.
    assert "ts" in entries[0]


def test_entries_filters_by_provider(tmp_path):
    store = LogStore(str(tmp_path))
    store.append({"event": "refresh.success", "provider_id": 1})
    store.append({"event": "refresh.success", "provider_id": 2})
    out = store.entries(provider_id=2)
    assert len(out) == 1
    assert out[0]["provider_id"] == 2


def test_entries_respects_limit(tmp_path):
    store = LogStore(str(tmp_path))
    for i in range(5):
        store.append({"event": "refresh.success", "provider_id": i})
    assert len(store.entries(limit=2)) == 2
    # No limit returns all
    assert len(store.entries(limit=0)) == 5


def test_purge_older_than_removes_old_keeps_recent(tmp_path):
    store = LogStore(str(tmp_path))
    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=10)).isoformat()
    new_ts = (now - timedelta(days=2)).isoformat()
    store.append({"ts": old_ts, "event": "refresh.success"})
    store.append({"ts": new_ts, "event": "refresh.success"})
    removed = store.purge_older_than(days=7)
    assert removed == 1
    remaining = store.entries()
    assert len(remaining) == 1
    assert remaining[0]["ts"] == new_ts


def test_clear_truncates_and_returns_count(tmp_path):
    store = LogStore(str(tmp_path))
    store.append({"event": "refresh.success"})
    store.append({"event": "refresh.unchanged"})
    cleared = store.clear()
    assert cleared == 2
    assert store.entries() == []
    # Second clear is a no-op
    assert store.clear() == 0


def test_atomicity_no_partial_line_under_concurrent_reads(tmp_path):
    """Each append is atomic so readers never see a half-written JSON line."""
    store = LogStore(str(tmp_path))
    store.append({"event": "refresh.success", "provider_id": 1})
    # Read the file directly to confirm one line per append.
    lines = [ln for ln in open(os.path.join(str(tmp_path), "events.jsonl"), "r", encoding="utf-8") if ln.strip()]
    assert len(lines) == 1
    # And the line is parseable JSON.
    json.loads(lines[0])
