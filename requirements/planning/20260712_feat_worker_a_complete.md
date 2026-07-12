# Worker A Implementation — Complete (A1–A8)

## Summary

All Worker A tasks from `requirements/planning/20260712_doc_two_worker_checklist.md` have been implemented and tested. 49 unit tests pass.

## What Was Built

### Shared Contracts
- `requirements/planning/20260712_doc_shared_contracts.md` — frozen interfaces for converter, API payloads, schedule schema, event schema, and public endpoint behavior.

### A1: Application Foundation
- `app/__init__.py` — Flask app factory with Blueprint registration, scheduler init, logging.
- `app/config.py` — Environment-based configuration (DATA_DIR, DATABASE_URL, PUBLIC_BASE_URL, TIMEZONE, REQUEST_TIMEOUT, MAX_RESPONSE_SIZE, FRESHNESS_THRESHOLD_HOURS, VERSION_RETENTION_COUNT, TRUSTED_HOSTS).
- `app/extensions.py` — Shared `db` and `migrate` singletons.
- `main.py` — Entry point calling `create_app()`.
- `pyproject.toml` — Dependencies (Flask, SQLAlchemy, migrations, APScheduler, PyYAML, httpx, gunicorn) and dev/test groups.

### A2: Persistence Model
- `app/models/provider.py` — `Provider`, `SubscriptionVersion`, `UpdateRun` ORM models with frozen field contract, cryptographically random tokens (32-char hex), and `to_dict()` serializers.
- `app/repositories/provider_repo.py` — Query/transaction layer for CRUD, version management, and update run lifecycle.

### A3: Versioned File Storage
- `app/services/version_store.py` — Atomic file writes via tempfile+os.replace, SHA-256 hashing of raw and converted content, 5-version pruning, provider-specific directories.

### A4: Safe Provider Fetcher
- `app/services/fetcher.py` — HTTP/HTTPS-only validation, embedded credentials rejection, SSRF protection (loopback/private/link-local blocking), configurable trusted host allowlist, timeout/size/redirect limits via httpx.

### A5: Refresh Orchestration
- `app/services/updater.py` — Per-provider threading locks for deduplication, raw hash comparison (unchanged = skip conversion), converter integration, structured update stages, last-good fallback on failure.
- `app/converter/clash.py` — YAML parsing, proxy extraction/deduplication, stub encoder supporting SS/Trojan/VMess/VLESS/Hysteria2. Worker B will replace with full ported implementation.

### A6: Backend Routes and Public Endpoint
- `app/routes/api.py` — Provider CRUD, manual refresh, token rotation, update-run history. Create triggers background first-fetch.
- `app/routes/subscriptions.py` — `GET|HEAD /subscriptions/<token>` with freshness check, synchronous stale refresh, ETag/Cache-Control headers, 404 for invalid tokens, 503 when no version exists.
- `app/routes/events.py` — Server-Sent Events stream with keepalive and per-client queue.
- `app/routes/ui.py` — Management page stub (Worker B will replace with full UI).

### A7: Scheduling
- `app/services/scheduler.py` — APScheduler BackgroundScheduler with disabled/monthly/weekly/daily/interval triggers, startup restoration from SQLite, reschedule on provider settings change.

### A8: Container and Operations
- `Dockerfile` — Python 3.12-slim, non-root user, health check, gunicorn single-worker.
- `compose.yaml` — Persistent `/data` volume, environment variables, restart policy.
- `.dockerignore` / `.gitignore` — Runtime data exclusions.

## Key Decisions

1. **Single-worker gunicorn** — Required because APScheduler runs in-process; multiple workers would duplicate scheduled jobs.
2. **Converter stub** — Worker A provides a minimal `convert_clash_yaml` stub. Worker B will replace it with the full ported implementation from `external_ref/urlclash-converter`.
3. **Thread-based refresh** — Manual/creation refreshes run in daemon threads to avoid blocking API responses. Per-provider locks prevent concurrent fetches.
4. **Session-scoped test DB** — In-memory SQLite shared across test session for performance; individual tests don't clean up (test isolation via unique names).

## Root Causes of Issues Fixed

1. **DetachedInstanceError in updater** — `_do_refresh` returned ORM objects that became detached when the inner `app_context` exited. Fixed by returning `run_id` (int) instead.
2. **Missing config keys in TestConfig** — Scheduler and updater required REQUEST_TIMEOUT etc. Added to `TestConfig`.
3. **Scheduler init before tables** — `init_scheduler` tried to query providers before `db.create_all()`. Added exception guard.
4. **httpx.Limits misuse** — `max_redirects` is not a `Limits` parameter. Removed it.
