import hashlib
import logging
import threading
from datetime import datetime, timezone

from app.extensions import db
from app.models.provider import Provider
from app.repositories.provider_repo import (
    create_update_run,
    complete_update_run,
    update_run_stage,
    get_provider,
    get_current_version,
)
from app.services.fetcher import ProviderFetcher, FetchError
from app.services.version_store import VersionStore
from app.routes.events import publish_event

logger = logging.getLogger(__name__)

_provider_locks: dict[int, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_provider_lock(provider_id):
    with _locks_lock:
        if provider_id not in _provider_locks:
            _provider_locks[provider_id] = threading.Lock()
        return _provider_locks[provider_id]


class RefreshOrchestrator:
    def __init__(self, app):
        self.app = app
        self.fetcher = ProviderFetcher(
            timeout=app.config["REQUEST_TIMEOUT"],
            max_response_size=app.config["MAX_RESPONSE_SIZE"],
            trusted_hosts=app.config["TRUSTED_HOSTS"],
        )
        self.version_store = VersionStore(
            subscriptions_dir=app.config["SUBSCRIPTIONS_DIR"],
            retention_count=app.config["VERSION_RETENTION_COUNT"],
        )

    def refresh(self, provider_id, trigger="manual"):
        lock = _get_provider_lock(provider_id)
        if not lock.acquire(blocking=False):
            logger.info("Provider %d refresh already in progress, skipping", provider_id)
            return None

        try:
            return self._do_refresh(provider_id, trigger)
        finally:
            lock.release()

    def _do_refresh(self, provider_id, trigger):
        with self.app.app_context():
            provider = get_provider(provider_id)
            if not provider:
                logger.error("Provider %d not found", provider_id)
                return None

            run = create_update_run(provider_id, trigger)
            run_id = run.id

            publish_event({
                "provider_id": provider_id,
                "run_id": run_id,
                "stage": "querying",
                "message": "Fetching from provider",
                "status": "running",
            })

            try:
                update_run_stage(run, "querying", "Fetching from provider")
                fetch_result = self.fetcher.fetch(provider.source_url)

                publish_event({
                    "provider_id": provider_id,
                    "run_id": run_id,
                    "stage": "received",
                    "message": f"Got {len(fetch_result.content)} bytes",
                    "status": "running",
                })

                update_run_stage(run, "received", f"Got {len(fetch_result.content)} bytes")

                current_raw_hash = self.version_store.get_current_raw_hash(provider_id)
                new_raw_hash = hashlib.sha256(fetch_result.content).hexdigest()

                if current_raw_hash == new_raw_hash:
                    update_run_stage(run, "comparing", "Content unchanged")
                    provider.last_check_at = datetime.now(timezone.utc)
                    provider.last_success_at = datetime.now(timezone.utc)
                    db.session.commit()
                    publish_event({
                        "provider_id": provider_id,
                        "run_id": run_id,
                        "stage": "comparing",
                        "message": "Content unchanged",
                        "status": "success",
                    })
                    complete_update_run(run, "success", "Content unchanged")
                    return run_id

                publish_event({
                    "provider_id": provider_id,
                    "run_id": run_id,
                    "stage": "converting",
                    "message": "Converting to share links",
                    "status": "running",
                })

                update_run_stage(run, "converting", "Converting to share links")
                from app.converter.clash import convert_clash_yaml

                conversion = convert_clash_yaml(fetch_result.content)

                publish_event({
                    "provider_id": provider_id,
                    "run_id": run_id,
                    "stage": "storing",
                    "message": f"Storing {conversion.proxy_count} nodes",
                    "status": "running",
                })

                update_run_stage(run, "storing", f"Storing {conversion.proxy_count} nodes")
                self.version_store.store_version(
                    provider_id=provider_id,
                    raw_bytes=fetch_result.content,
                    converted_bytes="\n".join(conversion.links).encode("utf-8"),
                )

                provider.last_check_at = datetime.now(timezone.utc)
                provider.last_success_at = datetime.now(timezone.utc)
                provider.last_error = None
                current_ver = get_current_version(provider_id)
                provider.current_version = current_ver.sequence if current_ver else None
                db.session.commit()

                complete_update_run(
                    run, "success",
                    f"Converted {conversion.proxy_count} nodes"
                )

                publish_event({
                    "provider_id": provider_id,
                    "run_id": run_id,
                    "stage": "finished",
                    "message": f"Converted {conversion.proxy_count} nodes",
                    "status": "success",
                })

                return run_id

            except Exception as e:
                logger.exception("Refresh failed for provider %d", provider_id)
                provider.last_check_at = datetime.now(timezone.utc)
                provider.last_error = str(e)
                db.session.commit()
                complete_update_run(run, "failure", str(e), error_details=str(e))
                publish_event({
                    "provider_id": provider_id,
                    "run_id": run_id,
                    "stage": "failed",
                    "message": str(e),
                    "status": "failure",
                })
                return run_id

    def is_fresh(self, provider_id):
        provider = get_provider(provider_id)
        if not provider or not provider.last_success_at:
            return False
        threshold = self.app.config["FRESHNESS_THRESHOLD_HOURS"]
        last_success = provider.last_success_at
        if last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_success).total_seconds() / 3600
        return elapsed < threshold
