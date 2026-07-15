# Feature: Export Historical Logs + Log Rotation Confirmation

Date: 2026-07-15
Type: feat
Area: `app/services/log_store.py`, `app/routes/api.py`, `app/templates/index.html`, `app/static/app.js`

## What changed

Added an **"Export logs"** button to the management UI (next to "Clear logs") that
downloads the full retained event history as a JSONL file.

- `LogStore.export_text()` — returns the entire `events.jsonl` verbatim
  (oldest-first, exactly as stored). Empty string when no file exists yet.
- `GET /api/logs/export` — serves the text as `application/x-ndjson` with
  `Content-Disposition: attachment; filename="converter-logs-<UTC timestamp>.jsonl"`
  and `Cache-Control: no-store`.
- `index.html` — new `#log-export` button in the log header.
- `app.js` — `exportLogs()` triggers the download via a temporary `<a download>`
  navigation (the attachment header makes the browser save it without leaving
  the page); wired in the same setup block as the clear button.

Tests (`tests/integration/test_log_endpoints.py`): export returns full JSONL as
an attachment (oldest-first, all lines), and returns empty body when there is no
history. Existing log-store, log-endpoint, UI-rendering, and live-log tests still
pass.

## Design decisions

- **Export the raw file, not a re-serialized view.** Faithful to what retention
  actually keeps, chronological, and cheap (the file is small by design).
- **Direct-download via GET**, not the `api()` JSON helper — a file attachment is
  simplest as a browser navigation.
- **No provider filter on export** (unlike `/api/logs`): export is a full-history
  archive/backup action. The list endpoint remains the place for filtered views.

## Log rotation — confirmed current behavior

Storage: append-only JSONL at `DATA_DIR/logs/events.jsonl` (`LogStore`). Every
refresh stage transition and every public subscription query appends one line.

Rotation is **time-based by age**, not size:

- Retention window: `log_retention_days`, read live from the `AppSettings` row
  each tick (UI-editable under "Log forwarding"), defaulting from
  `LOG_RETENTION_DAYS` env (default **7 days**).
- Pruning: APScheduler job `purge_old_logs` runs **hourly** (first run ~1 min
  after startup), calling `LogStore.purge_older_than(days)`, which rewrites the
  file keeping only lines with `ts >= now - days`. Atomic via temp-file +
  `os.replace`.
- Manual: the "Clear logs" button (`POST /api/logs/clear`) truncates the whole
  file.

### Limitations worth noting (not changed here)

- **No size cap.** Retention is purely by age, so a burst of events within the
  window can grow the file unbounded until the next daily-age cutoff prunes it.
  For this single-user LAN tool the volume is low, so this is acceptable, but a
  max-lines/max-bytes guard could be added if event volume grows.
- **`append()` is O(file size)** — it rewrites the whole file per line to stay
  atomic. Fine while the file is small (the point of hourly pruning); would need
  revisiting only if the log grew large between prunes.
- Rotation applies to the JSONL event log only. `UpdateRun` rows in SQLite are a
  separate store (read capped at 50 in `list_update_runs`) and are not part of
  this retention job.
