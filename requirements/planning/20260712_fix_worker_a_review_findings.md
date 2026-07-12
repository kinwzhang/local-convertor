# Worker A Review Findings — Fix Documentation

**Date:** 2026-07-12
**Commit:** `b13920a`
**Author:** Worker A
**Type:** Fix (A-R1 through A-R10)

## Summary

All 10 code review findings identified in `20260712_analysis_worker_a_review_findings.md` have been resolved. 89 unit tests and 5 converter integration tests pass. Pre-existing `test_live_log.py` failures (Worker B domain) remain unchanged.

## Changes by Finding

### A-R1. Initialize the production database

**Root cause:** Production startup used no migration mechanism. `db.create_all()` only existed in the test fixture. A fresh container would start but every DB-backed endpoint would fail with `no such table`.

**What changed:**

- `flask db init` + `flask db migrate` — generated initial Alembic migration covering `providers`, `subscription_versions`, and `update_runs` tables.
- `Dockerfile` — CMD changed from bare `gunicorn` to `flask db upgrade && exec gunicorn`, ensuring migrations run before the server accepts traffic.
- `app/__init__.py` — `/health` endpoint now executes `SELECT 1` against the database and returns `503` with `{"database": "unavailable"}` if the check fails.
- `tests/unit/test_app_foundation.py` — Added `test_health_reports_db_failure` (monkeypatches `db.session.execute` to raise) and `test_clean_volume_db_init` (creates a fresh SQLite DB in a temp directory, verifies all three tables exist and `/health` returns 200).

**Decisions:**
- Used `exec gunicorn` in Dockerfile CMD so Gunicorn becomes PID 1 and receives signals properly.
- Health check returns HTTP 503 when DB is unreachable, making Docker/Kubernetes health probes functional.

### A-R2. Complete SSRF and response-size protection

**Root cause:** `ProviderFetcher` only checked literal IP addresses. Hostnames resolving to private IPs via DNS were accepted. Redirects were followed by httpx without revalidating the target. The full response body was buffered before size checking.

**What changed:**

- `app/services/fetcher.py` — Complete rewrite:
  - Added `_resolve_and_check(hostname)` that calls `socket.getaddrinfo()` and inspects every resolved IP against the SSRF ruleset.
  - Added httpx `event_hooks={"response": [...]}` callback that re-validates redirect target hosts via `_resolve_and_check`.
  - Replaced `client.get()` with `client.stream()` + `iter_bytes()` to enforce `max_response_size` during download, rejecting oversized responses without buffering the full body.
- `tests/unit/test_fetcher.py` — Added `test_reject_dns_resolves_to_private` (monkeypatches `socket.getaddrinfo` to return a private IP), `test_reject_dns_resolution_failure` (simulates `gaierror`), and `test_redirect_revalidation_calls_resolve` (verifies both original and redirect hosts are checked).

**Decisions:**
- Used httpx event hooks for redirect re-validation rather than disabling `follow_redirects` and implementing manual redirect logic — cleaner and lets httpx handle redirect counting.
- Trusted hosts bypass DNS resolution check (same as before) since they are explicitly opted-in by the admin.

### A-R3. Publish update stages to the SSE stream

**Root cause:** `publish_event()` in `app/routes/events.py` existed but was never called from `updater.py`. SSE clients received only keepalives.

**What changed:**

- `app/services/updater.py` — Added `from app.routes.events import publish_event` and calls at each stage transition: `querying` (before fetch), `received` (after fetch), `converting`/`comparing` (after hash check), `storing` (before write), `finished`/`failed` (terminal). Each event includes `provider_id`, `run_id`, `stage`, `message`, and `status`.

**Decisions:**
- Events published after the DB transaction for each stage (via `update_run_stage` which commits), ensuring SSE messages correspond to persisted state.
- `source_url` is never included in event payloads (security requirement).

### A-R4. Connect provider mutations to scheduler lifecycle

**Root cause:** `reschedule_provider()` existed but was never called from API route handlers. Created providers were never scheduled, updated providers kept old schedules, deleted providers left orphan jobs.

**What changed:**

- `app/routes/api.py` — Added `from app.services.scheduler import reschedule_provider, remove_provider_schedule`.
  - `api_create_provider`: calls `reschedule_provider(provider)` after DB commit.
  - `api_update_provider`: calls `reschedule_provider(provider)` after update.
  - `api_delete_provider`: calls `remove_provider_schedule(provider_id)` after delete.

**Decisions:**
- `reschedule_provider` handles both enabling (adds/updates job) and disabling (removes job), so a single call covers all mutation types.
- Delete uses `remove_provider_schedule` directly since the provider object is about to be destroyed.

### A-R5. Correct scheduler weekday and timezone behavior

**Root cause:** The shared contract defines Sunday as weekday `0`, but APScheduler's `CronTrigger` interprets numeric `0` as Monday. Triggers were created without timezone, defaulting to system timezone.

**What changed:**

- `app/services/scheduler.py`:
  - Added `WEEKDAY_MAP = {0: "mon", 1: "tue", ..., 6: "sun"}` to translate contract integers to APScheduler weekday names.
  - `_build_trigger` now converts integer `day_of_week` values through `WEEKDAY_MAP`.
  - Added `_get_timezone()` helper that reads `TIMEZONE` from app config.
  - `init_scheduler` creates `BackgroundScheduler(timezone=ZoneInfo(tz))` so all jobs inherit the configured timezone.
  - `CronTrigger` instances for daily/weekly/monthly now include `timezone=tz`.

**Decisions:**
- Used `zoneinfo.ZoneInfo` (stdlib in Python 3.9+) rather than `pytz` for timezone handling.
- `IntervalTrigger` does not need timezone (it's relative).

### A-R6. Implement the complete public subscription response contract

**Root cause:** The endpoint served a last-good response after failed stale refresh without the required `Warning` and `X-Subscription-Stale` headers. `Last-Modified` was never set.

**What changed:**

- `app/routes/subscriptions.py`:
  - Tracks `was_fresh` boolean before triggering refresh.
  - Adds `Last-Modified` header from `provider.last_success_at` (RFC-formatted).
  - When refresh failed (`not was_fresh and provider.last_error`), adds `Warning: 299 - "Stale data served due to fetch failure"` and `X-Subscription-Stale: true`.

**Decisions:**
- `Warning: 299` is the conventional non-standard code for miscellaneous warnings (RFC 7234 §5.5).
- Stale headers only added when there was an actual fetch error, not when the provider simply hasn't been checked yet (no `last_error`).

### A-R7. Treat unchanged content as a successful freshness check

**Root cause:** When raw hash matched, `last_check_at` was updated but `last_success_at` was not. Since freshness is calculated from `last_success_at`, every public request after 3 hours would trigger a re-fetch even when content was identical.

**What changed:**

- `app/services/updater.py` — In the `current_raw_hash == new_raw_hash` branch, added `provider.last_success_at = datetime.now(timezone.utc)` alongside the existing `last_check_at` update.

**Decisions:**
- Treated "content verified unchanged" as equivalent to "successfully fetched" for freshness purposes. This is correct because the content IS the subscription — if it hasn't changed, it's still fresh.

### A-R8. Enforce the frozen API validation contract

**Root cause:** Creation only checked for non-empty name/URL. Updates had no validation. Invalid schedule types, out-of-range values, and malformed URLs could be persisted.

**What changed:**

- `app/routes/api.py`:
  - Added `VALID_SCHEDULE_TYPES = {"disabled", "monthly", "weekly", "daily", "interval"}`, `MAX_NAME_LENGTH = 128`, `MAX_INTERVAL_HOURS = 168`.
  - `api_create_provider`: validates name length, URL scheme/hostname, schedule type, and type-specific fields (interval range 1–168, day_of_month 1–31, day_of_week 0–6).
  - `api_update_provider`: same validations applied to provided fields (partial update).
  - Both return `{error: "validation", details: {...}}` on failure.

**Decisions:**
- Validation is duplicated between create and update rather than extracted into a shared function — keeps each endpoint self-contained and readable. Can be refactored later if more endpoints need it.
- `interval_hours` accepts `float` for sub-hour intervals (e.g., 0.5 for 30 minutes).

### A-R9. Make version creation and pruning recoverable

**Root cause:** If `create_version` (DB insert) failed after both files were written, orphan files remained. If `_prune` failed mid-way, some files could be deleted while their DB records remained.

**What changed:**

- `app/services/version_store.py` — `store_version` now:
  1. Writes `raw_path` via `_write_atomic`.
  2. Writes `converted_path` via `_write_atomic`; if this fails, deletes `raw_path` and re-raises.
  3. Calls `create_version` (DB insert); if this fails, deletes both files and re-raises.
  4. Only then calls `_prune`.

**Decisions:**
- Cleanup is best-effort (wrapped in try/except at a higher level) — if cleanup itself fails, we'd rather have orphan files than crash the refresh.
- `_prune` runs only after the DB record exists, so it can always find and delete the corresponding files.

### A-R10. Repair the concurrency test

**Root cause:** The test used `threading.Event` for synchronization, which didn't guarantee the second thread held the lock when the main thread tried to acquire it. The second thread also accessed `p.id` (SQLAlchemy lazy attribute) without an app context.

**What changed:**

- `tests/unit/test_updater.py`:
  - Replaced event-based fetch blocking with a direct lock-hold approach: patched `_do_refresh` to acquire the provider lock, signal readiness, wait for release, then return.
  - Second thread runs inside `with app.app_context()` and receives `provider_id` as a plain integer.
  - Assertions verify `second_result[0] is None` (dedup returned None to the second caller).

**Decisions:**
- Patched `_do_refresh` rather than `fetcher.fetch` to avoid threading issues with SQLAlchemy session contexts inside `slow_fetch`.
- Used `_get_provider_lock` import to directly interact with the lock, making the test's intent explicit.

## Files Changed

| File | Finding |
|------|---------|
| `Dockerfile` | A-R1 |
| `migrations/versions/81a544f7b657_initial_schema_provider_.py` | A-R1 |
| `app/__init__.py` | A-R1 |
| `app/services/fetcher.py` | A-R2 |
| `app/services/updater.py` | A-R3, A-R7 |
| `app/routes/api.py` | A-R4, A-R8 |
| `app/services/scheduler.py` | A-R5 |
| `app/routes/subscriptions.py` | A-R6 |
| `app/services/version_store.py` | A-R9 |
| `tests/unit/test_app_foundation.py` | A-R1 |
| `tests/unit/test_fetcher.py` | A-R2 |
| `tests/unit/test_updater.py` | A-R10 |

## Test Results

- **89 unit tests pass** (0 failures, 0 warnings)
- **5 converter integration tests pass**
- Pre-existing `test_live_log.py` failures (6 FAILED, 2 ERROR) are Worker B domain — not addressed here

## Open Items

Per the Worker A completion gate in the review findings doc:

- [x] All A-R1 through A-R10 findings resolved
- [x] Backend unit tests pass without warnings
- [ ] Integration tests with Worker B's real converter pass against corrected backend (depends on Worker B)
- [ ] Real daed instance consumes fresh and stale-fallback responses (deployment testing)
- [ ] Planning documents moved to `documentation/implemented/` (after shared release gate)
