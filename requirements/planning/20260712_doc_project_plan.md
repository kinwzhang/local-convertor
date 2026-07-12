# Local Clash Subscription Converter Project Plan

## Summary

Build a single-user Flask application deployed with Docker on a trusted LAN. It will:

- Store multiple Clash subscription providers.
- Fetch Clash YAML manually, on schedules, or lazily when daed requests a stale subscription.
- Convert supported Clash proxies into one share link per line.
- Expose each provider through a persistent opaque URL.
- Retain the five most recent changed raw and converted versions.
- Display provider management controls and live update logs.

After the implementation is completed and documented, move this plan to `documentation/implemented/20260712_doc_project_plan.md` as required by `working_protocol.md`.

## Project Design

### Architecture and data flow

1. The Flask web layer serves the management UI, JSON APIs, and public subscription URLs.
2. A service layer validates provider settings and coordinates fetching, conversion, versioning, rotation, and deletion.
3. A Python conversion package ports the Clash-to-link behavior from `external_ref/urlclash-converter`, preserving protocol behavior through parity fixtures.
4. SQLite stores provider configuration, schedules, update state, version metadata, and structured logs.
5. Versioned raw YAML and converted subscription files live in a persistent data volume.
6. APScheduler runs inside the application for monthly, weekly, daily, and interval schedules. A single-process deployment prevents duplicate scheduler execution.
7. Per-provider locks deduplicate simultaneous scheduled, manual, and request-triggered refreshes.

### Refresh behavior

- Saving a provider generates an opaque public token and starts the first fetch.
- The public endpoint is `GET /subscriptions/<token>`.
- If the last successful check is under three hours old, serve the latest converted file.
- If it is older, synchronously refresh before responding.
- If that refresh fails, serve the last successful file with `Warning` and `X-Subscription-Stale` headers; return `503` only when no successful version exists.
- Compare provider responses using a SHA-256 hash of the exact response bytes.
- An unchanged response updates the last-checked timestamp without creating another version.
- A changed response is converted and stored atomically before becoming current.
- Keep the five newest changed versions, pairing each raw response with its converted output; delete older pairs only after the new version is committed.
- Rotation replaces the token and immediately invalidates the former URL.
- Failed refreshes never replace the last successful output.

### Persistence model

Core records:

- `Provider`: ID, display name, source URL, public token, enabled state, schedule type and parameters, last-check/success/error timestamps, current version, and creation/update timestamps.
- `SubscriptionVersion`: provider ID, sequence, raw and converted hashes, file paths, node count, and creation timestamp.
- `UpdateRun`: provider ID, trigger type, status, progress stage, message, timestamps, and error details.

Provider source URLs are returned only by management APIs and never exposed through public subscription responses or logs.

### Management interface

The main page contains:

- Provider, Clash link, generated URL, automatic-update settings, last status, and actions.
- A permanently available new-provider row.
- Actions for update now, copy URL, rotate URL, and delete with confirmation.
- Schedule editors for disabled, monthly day/time, weekly weekday/time, daily time, and every X hours.
- A live log panel updated through Server-Sent Events, with polling fallback.
- Clear states for querying, waiting, response received, unchanged/changed, converting, finished, and failed.

## Target Folder Structure

```text
local-convertor/
├── app/
│   ├── __init__.py              # Flask application factory
│   ├── config.py                # Environment-based configuration
│   ├── extensions.py            # Database and scheduler initialization
│   ├── models/                  # Provider, version, and update-run models
│   ├── repositories/            # Persistence queries and transactions
│   ├── services/
│   │   ├── fetcher.py           # Safe HTTP provider retrieval
│   │   ├── updater.py           # Refresh orchestration and locking
│   │   ├── version_store.py     # Atomic files and five-version retention
│   │   └── scheduler.py         # Schedule registration and execution
│   ├── converter/
│   │   ├── clash.py             # YAML parsing and proxy dispatch
│   │   ├── protocols/           # Per-protocol URI encoders
│   │   └── errors.py
│   ├── routes/
│   │   ├── ui.py                # Management page
│   │   ├── api.py               # Provider and update APIs
│   │   ├── events.py            # Live log stream
│   │   └── subscriptions.py     # Public daed endpoint
│   ├── templates/
│   └── static/
├── data/
│   ├── database/                # Runtime SQLite database
│   └── subscriptions/           # Provider/version raw and converted files
├── migrations/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── end_to_end/
├── documentation/
│   └── implemented/
├── requirements/
│   └── planning/
├── Dockerfile
├── compose.yaml
├── pyproject.toml
├── main.py
└── working_protocol.md
```

Runtime data remains excluded from version control, while empty directory placeholders or startup-created directories establish the required layout.

## Interfaces and Configuration

Management API:

- `GET /api/providers`
- `POST /api/providers`
- `PATCH /api/providers/<id>`
- `DELETE /api/providers/<id>`
- `POST /api/providers/<id>/refresh`
- `POST /api/providers/<id>/rotate`
- `GET /api/update-runs`
- `GET /api/events`

Public interface:

- `GET` and `HEAD /subscriptions/<token>`
- UTF-8 plain-text response containing one node share URI per line.
- Conditional response headers including `ETag`, `Last-Modified`, and stale indicators.

Configuration uses environment variables for database/data paths, bind address, public base URL, timezone, request timeout, maximum response size, three-hour freshness threshold, and retention count. Defaults target one Docker container, `/data` persistence, and the `Asia/Hong_Kong` timezone.

Provider fetching accepts only HTTP/HTTPS, rejects embedded credentials, limits redirects and response size, applies timeouts, and blocks loopback/private/link-local destinations by default to reduce server-side request-forgery risk. A documented trusted-host allowlist can explicitly permit LAN-hosted providers.

## Development Sequence

1. **Foundation**
   - Replace the sample entry point with an application factory.
   - Add Flask, SQLAlchemy, migrations, YAML, HTTP client, scheduler, production server, and test dependencies.
   - Establish configuration, logging, Docker, persistent volume, health check, and ignored runtime paths.

2. **Conversion engine**
   - Port the reference TypeScript encoders into protocol-specific Python modules.
   - Initially cover all protocols claimed by the reference converter: SS, SSR, VMess, VLESS, Trojan, Hysteria/Hysteria2, TUIC, WireGuard, HTTP(S), SOCKS5, and AnyTLS.
   - Add fixture-driven parity tests and explicit unsupported/malformed-proxy reporting.
   - Preserve proxy order and names; skip no malformed entries silently.

3. **Persistence and version storage**
   - Implement database models and initial migration.
   - Add atomic raw/converted file writes, content hashing, current-version selection, and paired five-version pruning.
   - Add opaque cryptographically random public tokens and transactional rotation.

4. **Refresh pipeline**
   - Implement safe fetching, exact raw comparison, conversion, structured progress events, and last-good fallback.
   - Add per-provider concurrency locks and idempotent update behavior.
   - Ensure failed fetches or conversions leave the current version untouched.

5. **HTTP and management APIs**
   - Add provider CRUD, validation, manual refresh, rotation, deletion, event retrieval, and public subscription delivery.
   - Implement freshness checks, synchronous stale refresh, cache headers, stale headers, `404` for invalidated tokens, and `503` when no valid version exists.

6. **Scheduling**
   - Map monthly, weekly, daily, and hourly settings to scheduler jobs.
   - Restore jobs from SQLite during startup and replace/remove jobs when settings change.
   - Record missed or failed runs without corrupting provider state.

7. **Frontend**
   - Build the responsive provider table, editable schedule controls, permanent creation row, status indicators, copy/rotate/delete actions, and live log panel.
   - Prevent duplicate submissions and display validation and refresh failures without losing entered values.

8. **Hardening and delivery**
   - Add SSRF controls, payload limits, output escaping, redacted logs, graceful shutdown, database backup guidance, and container health checks.
   - Run the complete test suite in a clean container.
   - Verify daed can subscribe to and refresh generated URLs.
   - Document installation, configuration, trusted-LAN security limits, backup/restore, upgrade, and troubleshooting.
   - Record each implemented change according to `working_protocol.md`, then move the completed plan into `documentation/implemented`.

## Test Plan and Acceptance Criteria

- Converter fixture tests cover each supported protocol, Unicode names, optional transport/TLS fields, malformed YAML, missing proxies, and mixed valid/invalid entries.
- Refresh tests cover first fetch, unchanged content, changed content, five-version pruning, fetch failure, conversion failure, and atomic recovery.
- Concurrency tests prove simultaneous public/manual/scheduled requests perform only one provider fetch.
- Scheduling tests cover every schedule type, timezone handling, application restart, job edits, and disabled schedules.
- API tests cover validation, CRUD, rotation invalidation, deletion, event ordering, redaction, and public `GET`/`HEAD`.
- Security tests cover unsupported schemes, redirects, oversized responses, embedded credentials, and blocked internal destinations.
- End-to-end tests create a provider against a controlled HTTP fixture, receive a generated URL, trigger refreshes, observe live logs, rotate the link, and consume the resulting link list.
- Acceptance requires persistence across container restarts, correct three-hour request-time refresh behavior, last-good fallback, exactly five changed versions retained, and successful daed consumption.

## Assumptions and Defaults

- The first release is a trusted-LAN, single-user service without built-in authentication.
- Docker is the primary deployment path; native Python execution remains useful for development but is not a separately supported production target.
- SQLite and local files are sufficient for the intended single-instance workload.
- The converter is ported to Python rather than requiring Node or Bun at runtime.
- The generated public token is independent of provider name and source URL.
- Rotating a token invalidates the former URL immediately.
- The latest successful subscription remains available when a stale refresh fails.
- Provider deletion removes its schedule, token, database records, raw files, and converted files after confirmation.
- GPL-derived converter code retains required attribution and license notices.
