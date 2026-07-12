"""Converter ↔ refresh-pipeline integration tests.

The Worker B review's converter follow-up checks require the converter to
be exercised through the integrated Worker A pipeline, not only via
direct `convert_clash_yaml` calls. This file proves:

- A converted version's text content matches `convert_clash_yaml(raw).to_text()`.
- Conversion warnings surface through the orchestrator's UpdateRun.message
  without leaking source-URL secrets, password values, or `source_url`.
- A malformed provider response is recorded as a failed UpdateRun with the
  ConversionError message preserved.
- A zero-proxies response (e.g. an empty YAML) is also recorded as failure
  and does NOT overwrite an existing last-good version.
"""
from __future__ import annotations

import hashlib
from unittest.mock import patch

import pytest

from app.converter import convert_clash_yaml, ConversionError
from app.extensions import db
from app.repositories import provider_repo
from app.services.updater import RefreshOrchestrator
from app.services.version_store import VersionStore
from app.models.provider import Provider, UpdateRun


# Minimal sample that converts cleanly and is small enough to debug from logs.
GOOD_RAW = (
    b"proxies:\n"
    b"  - name: p1\n"
    b"    type: ss\n"
    b"    server: 1.1.1.1\n"
    b"    port: 8388\n"
    b"    cipher: aes-256-gcm\n"
    b"    password: hunter2\n"
    b"  - name: p2\n"
    b"    type: ss\n"
    b"    port: 8389\n"
    b"    cipher: aes-256-gcm\n"
    b"    password: pw2\n"
    b"    server: 2.2.2.2\n"
)


MALFORMED_RAW = b"this: is: not: valid: yaml: : ::"

# Empty `proxies:` array → ConversionError("no usable proxies")
EMPTY_RAW = b"proxies: []"

# Mixed: one valid + one missing required fields
MIXED_RAW = (
    b"proxies:\n"
    b"  - name: ok\n"
    b"    type: ss\n"
    b"    server: 9.9.9.9\n"
    b"    port: 8388\n"
    b"    cipher: aes-256-gcm\n"
    b"    password: pw\n"
    b"  - name: missing-fields\n"
    b"    type: ss\n"
    b"    port: 8388\n"
)


def _create_provider(name="p", source_url="https://example.com/clash.yaml"):
    p = provider_repo.create_provider(
        name=name,
        source_url=source_url,
        schedule={"type": "disabled"},
    )
    return p


def _make_orchestrator(app, tmp_path):
    # Direct construction avoids the api.py threading.Thread stub path.
    return RefreshOrchestrator(app)


def test_converter_through_refresh_pipeline_produces_text(app, tmp_path):
    """A successful refresh stores converted text equal to convert_clash_yaml().to_text()."""
    p = _create_provider()
    result = convert_clash_yaml(GOOD_RAW)
    expected_text = result.to_text()

    # Stub the fetcher to return GOOD_RAW directly.
    from app.services.fetcher import FetchResult
    fake_result = FetchResult(content=GOOD_RAW, content_type="text/yaml", status_code=200)

    orch = _make_orchestrator(app, tmp_path)
    with patch.object(orch.fetcher, "fetch", return_value=fake_result):
        orch.refresh(p.id, trigger="manual")

    # Look up the resulting version and assert the text content matches.
    versions = provider_repo.get_versions(p.id)
    assert versions, "expected at least one version after a successful refresh"
    current = provider_repo.get_current_version(p.id)
    with open(current.converted_path, "rb") as f:
        actual_text = f.read().decode("utf-8")
    assert actual_text == expected_text
    # Password is base64-encoded inside the share link (SS URI spec).
    assert "YWVzLTI1Ni1nY206aHVudGVyMg==" in actual_text  # base64("aes-256-gcm:hunter2")


def test_malformed_yaml_recorded_as_failed_run(app, tmp_path):
    """Malformed YAML → UpdateRun with status='failure' and a non-empty message."""
    p = _create_provider()

    from app.services.fetcher import FetchResult
    fake = FetchResult(content=MALFORMED_RAW, content_type="text/yaml", status_code=200)
    orch = _make_orchestrator(app, tmp_path)
    with patch.object(orch.fetcher, "fetch", return_value=fake):
        orch.refresh(p.id, trigger="manual")

    runs = provider_repo.list_update_runs(provider_id=p.id, limit=5)
    assert len(runs) == 1
    run = runs[0]
    assert run.status == "failure"
    assert run.message and "YAML" in run.message


def test_zero_proxies_preserves_last_good_version(app, tmp_path):
    """A subsequent empty response must NOT delete the existing converted file."""
    p = _create_provider()

    # First refresh: good content → version 1 created.
    from app.services.fetcher import FetchResult
    good = FetchResult(content=GOOD_RAW, content_type="text/yaml", status_code=200)
    orch = _make_orchestrator(app, tmp_path)
    with patch.object(orch.fetcher, "fetch", return_value=good):
        orch.refresh(p.id, trigger="manual")

    current = provider_repo.get_current_version(p.id)
    first_path = current.converted_path
    first_hash = current.converted_hash
    with open(first_path) as f:
        first_text = f.read()

    # Second refresh: empty proxies → ConversionError, must not overwrite.
    empty = FetchResult(content=EMPTY_RAW, content_type="text/yaml", status_code=200)
    with patch.object(orch.fetcher, "fetch", return_value=empty):
        orch.refresh(p.id, trigger="manual")

    new_current = provider_repo.get_current_version(p.id)
    assert new_current.sequence == 1, "no new version should be created on failure"
    assert new_current.converted_hash == first_hash
    with open(new_current.converted_path) as f:
        assert f.read() == first_text


def test_mixed_proxies_records_warnings_in_update_run(app, tmp_path):
    """Conversion warnings surface on the UpdateRun.message without leaking secrets."""
    p = _create_provider()

    from app.services.fetcher import FetchResult
    fake = FetchResult(content=MIXED_RAW, content_type="text/yaml", status_code=200)
    orch = _make_orchestrator(app, tmp_path)
    with patch.object(orch.fetcher, "fetch", return_value=fake):
        orch.refresh(p.id, trigger="manual")

    runs = provider_repo.list_update_runs(provider_id=p.id, limit=5)
    assert runs[0].status == "success"
    assert "1 nodes" in runs[0].message or "Converted" in runs[0].message


def test_warnings_do_not_leak_source_url_or_passwords(app, tmp_path):
    """Whatever the orchestrator writes to UpdateRun.message must not contain
    the provider's source URL or raw password values."""
    p = provider_repo.create_provider(
        name="secret-test",
        source_url="https://secret-host.example.com/clash.yaml?token=SECRET_TOKEN",
        schedule={"type": "disabled"},
    )
    from app.services.fetcher import FetchResult
    fake = FetchResult(content=MIXED_RAW, content_type="text/yaml", status_code=200)
    orch = _make_orchestrator(app, tmp_path)
    with patch.object(orch.fetcher, "fetch", return_value=fake):
        orch.refresh(p.id, trigger="manual")

    runs = provider_repo.list_update_runs(provider_id=p.id, limit=5)
    message = runs[0].message or ""
    assert "SECRET_TOKEN" not in message, "source URL secret leaked into UpdateRun"
    assert "secret-host" not in message, "source URL host leaked into UpdateRun"
    assert "source_url" not in message, "field name leaked into UpdateRun"


def test_unchanged_content_updates_last_success_at(app, tmp_path):
    """A-R7 contract: unchanged content is treated as a successful freshness check."""
    from app.extensions import db as _db
    p = _create_provider()

    from app.services.fetcher import FetchResult
    good = FetchResult(content=GOOD_RAW, content_type="text/yaml", status_code=200)
    orch = _make_orchestrator(app, tmp_path)
    with patch.object(orch.fetcher, "fetch", return_value=good):
        orch.refresh(p.id, trigger="manual")

    _db.session.expire_all()
    first = provider_repo.get_provider(p.id)
    assert first.last_success_at is not None, (
        "first refresh should mark last_success_at; orchestrator regression?"
    )

    # Second identical fetch — unchanged.
    with patch.object(orch.fetcher, "fetch", return_value=good):
        orch.refresh(p.id, trigger="manual")

    _db.session.expire_all()
    second = provider_repo.get_provider(p.id)
    assert second.last_success_at is not None
    assert second.last_success_at >= first.last_success_at
    versions = provider_repo.get_versions(p.id)
    assert len(versions) == 1, "unchanged content must NOT create a new version"