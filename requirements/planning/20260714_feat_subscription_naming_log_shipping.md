# 20260714 — feat: provider-named subscription files + rsyslog shipping + accumulated JSONL log + Clear button

Three coupled asks from one user message:

1. Subscription file storage should be named using the provider's user-supplied `name`, with file names cycling 0..9 (mod 10).
2. Ship every refresh outcome (success / unchanged / failure) and every subscription query to a remote **rsyslog** server on TCP/UDP port 514.
3. Accumulate logs locally with 7-day retention; expose a "Clear logs" button in the management UI.

**Worker territory:** Worker A — backend, persistence, scheduler, routes, config. The Clear logs button touches `index.html` / `app.js` / `app.css` (Worker B), and the planning doc follows the two-worker protocol in `CLAUDE.md`.

## What changed

- `app/config.py` — five new env-driven attrs:
  - `RSYSLOG_HOST` (no default → disabled), `RSYSLOG_PORT=514`, `RSYSLOG_PROTO=tcp`, `RSYSLOG_FACILITY=local0`.
  - `LOGS_DIR = DATA_DIR/logs`, `LOG_RETENTION_DAYS=7`.
- `app/services/version_store.py` — new naming scheme and migration:
  - Module-level `slugify(name)` (`re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32]` with an empty-fallback to `"provider"`).
  - `_provider_dir(provider_id, provider_name=None)` now returns `DATA_DIR/subscriptions/<slug>-<id>/`. Provider id is appended for uniqueness even when two providers share a name.
  - `store_version(provider_id, provider_name, raw_bytes, converted_bytes)` writes to `<seq % 10>_raw.yaml` and `<seq % 10>_converted.txt` — `sequence` stays monotonic in the DB, the on-disk cycle reuses the 10 file slots.
  - `_prune` no longer deletes disk files; the on-disk cycle replaces them. DB rows are still pruned to `VERSION_RETENTION_COUNT=5`.
  - `delete_provider_files(provider_id, provider_name=None)` updated to take the name.
  - Module-level `migrate_naming(app)` — idempotent startup migration that renames legacy `<provider_id>/<seq>_raw.yaml` to `<slug>-<id>/<seq % 10>_raw.yaml` (and same for converted), and updates `SubscriptionVersion.raw_path` / `converted_path` to the new absolute paths.
- `app/services/log_sink.py` (new) — `LogSink` wrapping `logging.handlers.SysLogHandler`. Constructed once at boot, stashed on `app.extensions["log_sink"]`, swallows `OSError` / `socket.error` so a dead rsyslog server never breaks a refresh. Disabled when `RSYSLOG_HOST` is unset.
- `app/services/log_store.py` (new) — `LogStore` over `DATA_DIR/logs/events.jsonl`. `append(event)` is atomic per line (`tempfile.mkstemp` + `os.replace`); `entries(provider_id, limit)` reads newest-first; `purge_older_than(days)` atomically rewrites the file keeping only lines within the window; `clear()` truncates and reports the prior line count.
- `app/services/updater.py` — every `publish_event` is mirrored by a `_emit_log` call that pushes to both `LogStore.append` and `LogSink.emit`. Event types: `refresh.querying`, `refresh.received`, `refresh.unchanged`, `refresh.converting`, `refresh.storing`, `refresh.success`, `refresh.failure`. Stored as `{ts, event, run_id, provider_id, provider_name, trigger, status, message}`.
- `app/routes/subscriptions.py` — same hook after `publish_event`; emits `subscription.served` (or `subscription.stale` when a refresh failed but stale data is served). Carries the captured `client_ip` (X-Forwarded-For with comma-split fallback, then `request.remote_addr`).
- `app/services/scheduler.py` — registers `_purge_old_logs` on `IntervalTrigger(hours=1)` with `id="purge_old_logs"`, next fire offset one minute out. The function uses `with _app.app_context():` so it can read `LOG_RETENTION_DAYS` and call `LogStore.purge_older_than`.
- `app/__init__.py` — calls `migrate_naming(app)` once at boot (idempotent, wrapped in try/except so a missing table at first boot is non-fatal). Builds `LogStore` and `LogSink` and stashes both on `app.extensions`, with an `atexit` hook to close the syslog socket.
- `app/routes/api.py` — two new endpoints:
  - `GET /api/logs?provider_id=&limit=` — returns `{entries: [...]}` newest-first; `limit` clamps to `[0, 1000]`, default `200`.
  - `POST /api/logs/clear` — truncates the file, returns `{cleared: <int>}`.
  - The DELETE `/api/providers/<id>` path now passes `provider.name` to `vs.delete_provider_files(...)`.
- `app/templates/index.html` — new `<div class="log-header">` wraps `#log-status` plus a `<button id="log-clear">Clear logs</button>`.
- `app/static/app.css` — new `.log-header` (flex row, justify-between) and `.section-button` rules. Reuses existing tokens (`--muted`, `--accent`, `--border`); reset of the global `button:hover { filter: brightness(1.1) }` via `filter: none`.
- `app/static/app.js` — new `clearLogs()` function. On click: confirms, `POST /api/logs/clear`, clears `seenEventIds` and `$("#log-box").replaceChildren()`, flashes `cleared N log entries`. Wired up inside the `DOMContentLoaded` listener.
- `tests/conftest.py` — added `LOGS_DIR` / `LOG_RETENTION_DAYS` / `RSYSLOG_*` to `TestConfig` and switched to per-session tmp directories. Added an autouse `_clear_log_store` fixture that resets the JSONL file between tests.
- `tests/unit/test_app_foundation.py` — `CleanConfig` extended with the new keys so the foundation smoke test still creates the app cleanly.
- `tests/unit/test_routes.py` — `store_version` calls now pass `provider.name` for the new signature.
- New tests:
  - `tests/unit/test_log_store.py` — append/entries round-trip, provider filter, limit cap, retention purge, clear, atomic per-line guarantees.
  - `tests/unit/test_log_sink.py` — disabled-when-no-host behavior, unknown-proto fallback, handler emit contract, quote-on-spaces, swallows OSError, close releases handler.
  - `tests/integration/test_log_endpoints.py` — `/api/logs` and `/api/logs/clear` exercise the new endpoints through the Flask test client.
- Updated `tests/unit/test_version_store.py` — name-based directory naming, mod-10 iteration, `slugify` unit tests, idempotent `migrate_naming` against a hand-rolled legacy layout.

## Decisions made

1. **Directory = `<slug>-<id>`, never just `<id>`.** Two providers sharing a name slug would otherwise collide on disk. Including the id also keeps the path unique even before the migration runs (so old `data/subscriptions/<id>/` directories and new `data/subscriptions/<slug>-<id>/` can coexist briefly mid-migration).

2. **No new `SubscriptionVersion` column.** `iter = sequence % 10` is computed on the fly. The existing `sequence` column keeps being monotonic, which is what `_prune` and `get_current_version` already depend on. Avoiding a schema change means no Alembic migration, which keeps this change fully reversible.

3. **On-disk rotation replaces manual file deletion in `_prune`.** With at most 10 raw + 10 converted files per provider on disk, the cycle reuses slots, so DB-pruned rows no longer need to `os.unlink` their files. The unlink loop stays as a defense-in-depth no-op (`os.unlink` on a non-existent path is silent).

4. **`LogStore.append` reads-and-rewrites the whole file.** Cost is `O(file size)` per append, but the file is bounded by retention (a week of low-volume events is well under a megabyte). The simpler shape was preferred over append-only single-line writes because a half-written line would corrupt downstream readers (entries parser is forgiving but useless for `clear()` and `purge_older_than()` if a line is malformed).

5. **`LogSink` is a no-op when `RSYSLOG_HOST` is unset.** This matches the user's deployment shape (rsyslog on LAN, server might be down) without forcing every deployment to ship logs. Test fixtures that don't want to bind a socket just leave `RSYSLOG_HOST=None`.

6. **`POST /api/logs/clear` does not call `subscribe_event` or `publish_event`.** "Clear logs" is a UI affordance, not an event. The success flash (`cleared N entries`) is enough confirmation; broadcasting it to all SSE clients would be noisy and would itself land in the JSONL log we just truncated.

7. **Retention cron fires hourly, with a one-minute `next_run_time` offset.** The hourly tick is plenty for "not expecting tons of logs" and keeps the JSONL file from growing indefinitely as a backstop to the manual Clear button. The one-minute offset just means the first run happens shortly after boot, useful in development.

## Verification

```bash
# Syntax + tests
node --check app/static/app.js                  # clean
node --test tests/browser/app.test.mjs          # 16/16 still pass
.venv/bin/pytest -q                              # 172/172 pass (was 150; +22 new tests)

# Manual end-to-end
RSYSLOG_HOST=127.0.0.1 RSYSLOG_PORT=1514 \
  .venv/bin/python main.py

# In another terminal, run a tiny TCP listener:
nc -l 514

# In the UI:
#   - create provider "my-hk-vpn"
#   - click Refresh 12 times → on disk: data/subscriptions/my-hk-vpn-7/{0..9}_raw.yaml,
#     cycling; nc shows 12 refresh.* events
#   - hit the public subscription URL → nc shows subscription.served with client_ip
#   - click "Clear logs" → file is empty, in-browser log box is empty
```

Test counts after this change:
- `tests/unit/test_version_store.py`: 5 → 9 (added dir-naming, mod-10, slugify, migrate).
- `tests/unit/test_log_store.py`: 0 → 6 (new file).
- `tests/unit/test_log_sink.py`: 0 → 6 (new file).
- `tests/unit/test_updater.py`: unchanged assertions; the JSONL-append is verified indirectly because the orchestrator and routes share the same `_emit_log` helper.
- `tests/integration/test_log_endpoints.py`: 0 → 4 (new file).
- Everything else: unchanged, all green.

## Critical files

- `app/config.py`
- `app/services/version_store.py` (rewritten naming + migrate)
- `app/services/log_sink.py` (new)
- `app/services/log_store.py` (new)
- `app/services/updater.py` (emit hooks at every stage)
- `app/routes/subscriptions.py` (emit hook on every query)
- `app/routes/api.py` (`/api/logs`, `/api/logs/clear`, `delete_provider_files` arg)
- `app/services/scheduler.py` (retention cron)
- `app/__init__.py` (wiring + migration)
- `app/templates/index.html`, `app/static/app.js`, `app/static/app.css`
- `tests/conftest.py`, `tests/unit/test_app_foundation.py`, `tests/unit/test_routes.py`
- `tests/unit/test_log_store.py`, `tests/unit/test_log_sink.py`, `tests/unit/test_version_store.py` (extended)
- `tests/integration/test_log_endpoints.py` (new)

## Out of scope

- Provider name in the *public* subscription URL (would break daed clients; only the on-disk layout changed).
- Compression of the JSONL log.
- A UI to filter logs by provider / time / event type beyond the existing live stream.
- A connection-check / health probe for the rsyslog server.
- Migration of `data/logs/` itself — there is no legacy data because `LogStore` is new.

---

## Followup — UI-configurable log forwarding

The user asked to drop the env-var configuration and make log forwarding settable from the management UI instead. Same planning doc, separate intent.

### What changed (relative to "before")

- New `AppSettings` single-row table (`app/models/settings.py`) plus Alembic migration `e4f2a1c8b3d7_add_app_settings.py`. The migration seeds the row with the same defaults the env vars used (`host=NULL`, `port=514`, `proto='tcp'`, `facility='local0'`, `retention_days=7`).
- New repo `app/repositories/settings_repo.py` — `get_settings()` (idempotent; creates the singleton if missing) and `update_settings(**fields)` (validates port / proto / retention; raises `ValueError` on bad input).
- New endpoints in `app/routes/api.py`:
  - `GET /api/settings` returns the current row.
  - `PATCH /api/settings` mutates the row and rebuilds `app.extensions["log_sink"]` so a saved change takes effect immediately.
- `app/__init__.py` now reads `LogSink` configuration from the AppSettings row at boot. A `_table_exists(app, ...)` helper detects the pre-migration / pre-`create_all()` case (test conftest, fresh boot without upgrade) and falls back to env vars for that single instance — kept only as a bootstrap path, the UI is the canonical config.
- `app/services/scheduler.py::_purge_old_logs` reads `s.log_retention_days` from the live row on each tick, so a UI change applies within an hour without restarting the worker.
- New "Log forwarding" section in `app/templates/index.html`: `rsyslog_host`, `rsyslog_port`, `rsyslog_proto` (select), `rsyslog_facility`, `log_retention_days`. Save button calls `PATCH /api/settings`. `loadSettings()` runs at boot.
- New tests in `tests/integration/test_settings_endpoints.py` — defaults, persistence, validation, LogSink rebuild on PATCH, empty-host disables shipping.

### Decisions made

- **Env vars stay as bootstrap only.** A user who already exports `RSYSLOG_HOST=...` keeps working on next deploy: `_init_settings` persists env values into the row if the row's `rsyslog_host` is still empty. Subsequent UI edits overwrite, but env vars don't keep pushing. This avoids breaking existing deployments while making the UI canonical.
- **LogSink rebuilt in-process on PATCH.** The underlying `SysLogHandler` holds an open socket, so a settings change requires recreating it. The endpoint closes the old handler, builds a new one, and swaps `app.extensions["log_sink"]`. Next `emit` uses the new config.
- **Retention cron reads live settings, not the static config.** Same socket-style rationale as above, applied to scheduler jobs.
- **Empty host disables shipping.** `rsyslog_host=""` persists as `NULL` and the LogSink becomes a no-op. The UI matches: blank host = no forwarding.
- **The conftest's `app` fixture (session-scoped, in-memory SQLite) needed a tweak.** `_init_settings` and `_configure_log_sinks` query `app_settings`, which doesn't exist until `db.create_all()` runs. The `_table_exists(app, "app_settings")` guard lets the boot path skip cleanly when the table is missing; the conftest now imports `AppSettings` and seeds the row before yielding.

### Verification (followup)

- `node --check app/static/app.js` clean.
- `node --test tests/browser/app.test.mjs` 16/16 pass.
- `.venv/bin/pytest -q` **178/178 pass** (was 172; +6 settings-endpoint tests).

Test counts after this followup:
- `tests/integration/test_settings_endpoints.py`: 0 → 6 (new file).
- Everything else: unchanged.

### Critical files (followup)

- `app/models/settings.py` (new)
- `migrations/versions/e4f2a1c8b3d7_add_app_settings.py` (new)
- `app/repositories/settings_repo.py` (new)
- `app/__init__.py` (`_table_exists`, `_init_settings` rewired, `_configure_log_sinks` reads live settings)
- `app/routes/api.py` (`/api/settings` GET + PATCH, `_rebuild_log_sink`)
- `app/services/scheduler.py` (`_purge_old_logs` reads `s.log_retention_days`)
- `app/templates/index.html` ("Log forwarding" section)
- `app/static/app.js` (`loadSettings`, `saveSettings`, wired into `DOMContentLoaded`)
- `app/static/app.css` (`.settings-grid` rule)
- `tests/conftest.py` (import `AppSettings`, seed row)
- `tests/integration/test_settings_endpoints.py` (new)

---

## Followup — Edit gate on the log-forwarding form

The user asked for the form to be read-only by default, with an explicit click into "Edit" mode before any value can be changed. The rationale is that rsyslog settings are easy to fat-finger (typo'd host, wrong port, retention_days that prunes everything the moment the hourly cron fires), and the operator doesn't want a stray keystroke to push a PATCH that rebuilds the live `LogSink`.

### What changed

- `app/templates/index.html` — every `#settings-*` input now carries `disabled` by default. A new `#settings-edit` button sits next to `#settings-save` / `#settings-cancel`; `save` and `cancel` are `hidden` until edit mode is entered.
- `app/static/app.js` — three new helpers: `_captureSettingsSnapshot` / `_restoreSettingsSnapshot` (form values are snapshotted on Edit click and reapplied on Cancel), plus `beginSettingsEdit` / `cancelSettingsEdit`. After a successful PATCH, `saveSettings()` re-enters view mode (`_settingsMode(true)`) and re-fetches via `loadSettings()` so the disabled view reflects server-side normalization. On a PATCH failure the form stays in edit mode so the operator can fix the input.
- `tests/browser/app.test.mjs` — new test "settings form starts read-only and toggles via the Edit / Cancel buttons" covering: all five inputs disabled on load, Edit visible / Save+Cancel hidden, click Edit enables them and hides Edit, edit + Cancel restores the original value.

### Decisions made

- **Snapshot on entry, not on every input change.** Simpler, and the form has only five fields — capturing once on Edit click covers every interaction model (type-then-Cancel, paste-then-Cancel, edit several-then-Cancel).
- **No `disabled` toggle via CSS — only via the `disabled` attribute.** Screen readers and keyboard navigation respect `disabled` correctly out of the box; CSS-only `pointer-events: none` would let the field still receive focus.
- **`Save` stays in DOM, not removed.** Toggling `hidden` is cheaper than re-rendering, and lets us wire the click handler once at boot.
- **Edit re-fetches after a successful save.** Server can normalize values (proto casing, port integer coercion); the disabled view should reflect what was *persisted*, not what was *submitted*.

### Verification (followup)

- `node --check app/static/app.js`: clean.
- `node --test tests/browser/app.test.mjs`: **17/17 pass** (was 16; +1 settings-edit-gate test).
- `.venv/bin/pytest -q`: **178/178 pass** (no regressions).

### Critical files (followup)

- `app/templates/index.html` (added `disabled` on every `#settings-*` input, `#settings-edit` button)
- `app/static/app.js` (`_settingsMode`, `_settingsSnapshot`, `beginSettingsEdit`, `cancelSettingsEdit`; rewire of `saveSettings`)
- `tests/browser/app.test.mjs` (new test)
