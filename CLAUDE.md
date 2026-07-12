# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Local Clash Subscription Converter** — a single-user Flask application that converts remote Clash YAML subscriptions into a share-link format consumable by [daed](https://github.com/daeuniverse/daed). Deployed on a trusted LAN, exposed as a persistent opaque URL per provider.

Reference repos live as git submodules under `external_ref/`:
- `urlclash-converter` — TypeScript implementation being ported to Python (GPL-derived; preserve attribution).
- `openwrt-daede` — daed management UI for consumer reference.

Read `requirements/20260712_initial_requirement.md` for the original product spec, `requirements/planning/20260712_doc_project_plan.md` for the full design, and `requirements/planning/20260712_doc_shared_contracts.md` for frozen contracts.

## Development Commands

Python 3.12+ is required. A project virtualenv exists at `.venv/`.

```bash
# Install dependencies (use the project venv)
.venv/bin/pip install -e ".[dev]"

# Run the Flask dev server
.venv/bin/python main.py
# or with debug
FLASK_DEBUG=1 .venv/bin/python main.py

# Production server
.venv/bin/gunicorn -w 1 -b 0.0.0.0:5000 main:app
# IMPORTANT: a single worker is required — APScheduler runs in-process and
# duplicates would cause double fetches and broken per-provider locks.

# Tests
.venv/bin/pytest                                # full suite
.venv/bin/pytest tests/unit/                    # unit tests only
.venv/bin/pytest tests/integration/             # integration tests
.venv/bin/pytest tests/end_to_end/              # end-to-end tests
.venv/bin/pytest tests/unit/test_persistence.py # single file
.venv/bin/pytest -k test_create_provider        # by name pattern
.venv/bin/pytest --cov=app                      # with coverage

# Database migrations
.venv/bin/flask db migrate -m "<message>"
.venv/bin/flask db upgrade
```

## Architecture

**App factory** at `app/__init__.py` creates a Flask app, registers four blueprints, and wires SQLAlchemy + Flask-Migrate. The entry point `main.py` calls `create_app()` and runs the dev server.

**Layered structure** under `app/`:
- `config.py` — env-driven configuration (see env var list below).
- `extensions.py` — shared `db` (SQLAlchemy) and `migrate` singletons.
- `models/` — SQLAlchemy ORM models. `Provider`, `SubscriptionVersion`, `UpdateRun` all live in `app/models/provider.py`. Models must be imported before `db.create_all()` runs (currently the test conftest doesn't import them — see Known Issues).
- `repositories/` — query/transaction layer (e.g. `provider_repo.create_provider`, `provider_repo.create_update_run`). Routes and services call repos; they never query `db` directly.
- `converter/` — Clash YAML → share-link engine. `convert_clash_yaml(raw: bytes) -> ConversionResult` is the frozen entry point defined in `requirements/planning/20260712_doc_shared_contracts.md`. Per-protocol encoders go under `converter/protocols/`.
- `services/` — orchestration: `fetcher` (safe HTTP), `updater` (refresh + locking), `version_store` (atomic writes, 5-version retention), `scheduler` (APScheduler jobs).
- `routes/` — Flask blueprints:
  - `ui` — management page at `/`
  - `api` — `/api/providers/*` CRUD, refresh, rotate; `/api/update-runs`
  - `subscriptions` — public endpoint `GET|HEAD /subscriptions/<token>` (serves converted text to daed)
  - `events` — `/api/events` Server-Sent Events stream for live update logs

**Persistence flow** for a public subscription request:
1. `subscriptions` route looks up `Provider` by opaque 32-char hex token.
2. If `last_success_at` is within `FRESHNESS_THRESHOLD_HOURS` (default 3), serve the latest `SubscriptionVersion`'s converted file.
3. Otherwise trigger a synchronous refresh: fetch YAML via `fetcher` (SSRF-guarded), compare SHA-256 of raw bytes against `current_version.raw_hash`, convert via `converter`, write atomically through `version_store`, prune to 5 versions, commit DB.
4. Stream progress as `UpdateRun` rows (`querying` → `received` → `comparing` → `converting` → `storing` → `finished|failed`) — these drive the SSE live log.

**Schedule types**: `disabled`, `monthly`, `weekly`, `daily`, `interval` (1–168 hours). All times in `TIMEZONE` (default `Asia/Hong_Kong`). APScheduler jobs are re-registered from SQLite on startup and re-created when provider settings change.

## Configuration (Environment Variables)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | dev fallback | Flask session signing |
| `DATA_DIR` | `./data` | parent of `database/` and `subscriptions/` |
| `DATABASE_URL` | `sqlite:///<DATA_DIR>/database/app.db` | SQLAlchemy URI |
| `PUBLIC_BASE_URL` | `http://localhost:5000` | shown in management UI for copy-link |
| `BIND_HOST`, `BIND_PORT` | `0.0.0.0`, `5000` | server bind |
| `TIMEZONE` | `Asia/Hong_Kong` | schedule interpretation |
| `REQUEST_TIMEOUT` | `30` | seconds, for provider fetches |
| `MAX_RESPONSE_SIZE` | `10 MiB` | cap on fetched YAML |
| `FRESHNESS_THRESHOLD_HOURS` | `3` | when public endpoint forces refresh |
| `VERSION_RETENTION_COUNT` | `5` | converted/raw pairs kept per provider |
| `TRUSTED_HOSTS` | empty | comma-separated allowlist for SSRF-blocked destinations (loopback, private, link-local) |

## Working Protocol (from `working_protocol.md`)

1. After making changes, write documentation covering: what changed, root cause of any issue, decisions made and why. Use the file naming convention `yyyymmdd_{doc|analysis|fix|feat|ref}_{topic}.md` and place under `requirements/planning/` for in-flight work.
2. Once a planning artifact is fully implemented and accepted, move it to `documentation/implemented/` (rename with the implementation date prefix).
3. This codebase is developed by **two parallel workers** (see `requirements/planning/20260712_doc_two_worker_checklist.md`):
   - **Worker A** owns backend, persistence, fetcher, scheduler, public endpoint, and deployment files (`app/__init__.py`, `app/config.py`, `app/extensions.py`, `main.py`).
   - **Worker B** owns the converter engine, frontend templates/static, and the live-log client.
   - Both must freeze shared contracts (converter interface, API payloads, event schema, public endpoint rules) before implementing against them — see `20260712_doc_shared_contracts.md`.

## Conventions

- **Never expose `Provider.source_url` through public subscription responses or logs** — it is management-API-only and may contain query-string secrets.
- **Cryptographically random tokens** are 32-char hex via `secrets.token_hex(16)`. Token rotation invalidates the previous URL immediately.
- **Preserve last good version**: failed refreshes must never overwrite `current_version`.
- **Per-provider locks** deduplicate simultaneous scheduled / manual / request-triggered refreshes — only one fetch should run at a time per provider.
- **Single process**: scheduler + locks assume a single gunicorn worker; do not scale `-w` above 1.
- **GPL attribution**: any code or behavior derived from `external_ref/urlclash-converter` must carry the required license notices (Worker B's `B8` task).
- **Empty `__init__.py` files** (`app/models/`, `app/repositories/`, `app/services/`, `app/converter/`, `app/converter/protocols/`, `tests/unit/`, etc.) are placeholders — populate them as you fill in the corresponding modules. Tests import directly from submodules (e.g. `from app.models.provider import Provider`); add explicit imports to `app/models/__init__.py` and `app/repositories/__init__.py` if you want re-exports.

## Known Gaps (foundation-stage)

- The test conftest (`tests/conftest.py`) does not import any models before `db.create_all()`. Persistence tests in `tests/unit/test_persistence.py` currently fail with `no such table: providers` — the model module must be imported into the app context first (e.g. via `app/__init__.py` or a fixture that imports `app.models.provider`).
- All route handlers (`api.py`, `ui.py`, `events.py`, `subscriptions.py`) are stubs returning placeholders — they need real implementations tied to repos/services.
- `app/services/`, `app/converter/protocols/`, `migrations/`, `tests/integration/`, `tests/end_to_end/`, and `tests/fixtures/` are empty — to be filled by follow-up worker tasks.
- No Dockerfile or `compose.yaml` yet (Worker A's `A8`).
- `data/database/` and `data/subscriptions/` are runtime-created and gitignored.