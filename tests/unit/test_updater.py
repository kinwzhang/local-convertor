import time
import threading
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models.provider import Provider, UpdateRun
from app.repositories.provider_repo import create_provider, get_current_version
from app.services.updater import RefreshOrchestrator, _get_provider_lock
from app.services.fetcher import FetchError


SAMPLE_YAML = b"""proxies:
  - name: TestNode
    type: ss
    server: 1.2.3.4
    port: 443
    cipher: aes-256-gcm
    password: testpassword
"""


def _make_orchestrator(app):
    return RefreshOrchestrator(app)


def _get_run(app, run_id):
    with app.app_context():
        return db.session.get(UpdateRun, run_id)


def test_refresh_converts_and_stores(app):
    with app.app_context():
        p = create_provider("Refresh Test", "https://example.com/clash.yaml", {"type": "disabled"})
        orch = _make_orchestrator(app)
        mock_result = MagicMock()
        mock_result.content = SAMPLE_YAML
        mock_result.content_type = "text/yaml"
        mock_result.status_code = 200
        with patch.object(orch.fetcher, "fetch", return_value=mock_result):
            run_id = orch.refresh(p.id, trigger="manual")
    run = _get_run(app, run_id)
    assert run.status == "success"
    with app.app_context():
        current = get_current_version(p.id)
        assert current is not None
        assert current.node_count == 1


def test_refresh_unchanged_content(app):
    with app.app_context():
        p = create_provider("Unchanged", "https://example.com/clash.yaml", {"type": "disabled"})
        orch = _make_orchestrator(app)
        mock_result = MagicMock()
        mock_result.content = SAMPLE_YAML
        mock_result.content_type = "text/yaml"
        mock_result.status_code = 200
        with patch.object(orch.fetcher, "fetch", return_value=mock_result):
            orch.refresh(p.id)
            run2_id = orch.refresh(p.id)
    run2 = _get_run(app, run2_id)
    assert run2.status == "success"
    assert "unchanged" in run2.message.lower()


def test_refresh_fetch_failure(app):
    with app.app_context():
        p = create_provider("Fail Test", "https://example.com/clash.yaml", {"type": "disabled"})
        orch = _make_orchestrator(app)
        with patch.object(orch.fetcher, "fetch", side_effect=FetchError("Network error")):
            run_id = orch.refresh(p.id)
    run = _get_run(app, run_id)
    assert run.status == "failure"
    assert "Network error" in run.message


def test_refresh_preserves_last_good(app):
    with app.app_context():
        p = create_provider("Preserve", "https://example.com/clash.yaml", {"type": "disabled"})
        orch = _make_orchestrator(app)
        mock_result = MagicMock()
        mock_result.content = SAMPLE_YAML
        mock_result.content_type = "text/yaml"
        mock_result.status_code = 200
        with patch.object(orch.fetcher, "fetch", return_value=mock_result):
            orch.refresh(p.id)
            old_version = get_current_version(p.id)
        with patch.object(orch.fetcher, "fetch", side_effect=FetchError("Network error")):
            orch.refresh(p.id)
            current = get_current_version(p.id)
            assert current.id == old_version.id


def test_concurrent_refresh_dedup(app):
    with app.app_context():
        p = create_provider("Dedup", "https://example.com/clash.yaml", {"type": "disabled"})
        orch = _make_orchestrator(app)
        provider_id = p.id
        second_result = [None]
        hold_event = threading.Event()
        release_event = threading.Event()

        def do_refresh_held(provider_id, trigger="manual"):
            lock = _get_provider_lock(provider_id)
            if not lock.acquire(blocking=False):
                return None
            try:
                hold_event.set()
                release_event.wait(timeout=5)
                return 12345
            finally:
                lock.release()

        with patch.object(orch, "_do_refresh", side_effect=do_refresh_held):
            def do_second():
                with app.app_context():
                    second_result[0] = orch.refresh(provider_id)

            t = threading.Thread(target=do_second)
            t.start()
            hold_event.wait(timeout=5)
            orch.refresh(provider_id)
            release_event.set()
            t.join(timeout=5)

    assert second_result[0] is None


def test_is_fresh(app):
    with app.app_context():
        p = create_provider("Fresh", "https://example.com/clash.yaml", {"type": "disabled"})
        orch = _make_orchestrator(app)
        assert not orch.is_fresh(p.id)
        p.last_success_at = datetime.now(timezone.utc)
        db.session.commit()
        assert orch.is_fresh(p.id)
