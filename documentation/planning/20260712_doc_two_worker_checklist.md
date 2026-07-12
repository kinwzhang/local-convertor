# Two-Worker Development Checklist

This checklist divides the Local Clash Subscription Converter implementation between two workers. Tasks within each worker's list are sequential; Worker A and Worker B may run their lists concurrently except at the explicit integration gates.

Related design: `requirements/planning/20260712_doc_project_plan.md`.

## Ownership and Coordination Rules

- Worker A owns the Flask backend, persistence, provider fetching, scheduling, public subscription endpoint, and deployment files.
- Worker B owns the Python conversion engine, frontend assets/templates, live-log client, and converter/frontend tests.
- Worker A owns shared application wiring in `app/__init__.py`, `app/config.py`, `app/extensions.py`, and `main.py`.
- Worker B may request wiring changes but should not edit Worker A-owned files without agreement.
- Agree on API payloads, event shapes, model field names, and converter interfaces at Integration Gate 1 before feature implementation.
- Rebase or synchronize before each integration gate and run the combined test suite after merging.
- Each worker must document completed features, fixes, root causes, and user decisions using `yyyymmdd_{doc|analysis|fix|feat|ref}_{topic}.md`.
- Do not move this checklist or the project plan to `documentation/implemented` until all acceptance checks pass.

## Shared Contracts to Freeze First

- [ ] Define `convert_clash_yaml(raw: bytes) -> ConversionResult`, where the result contains ordered links, warnings, and proxy counts, and malformed YAML or zero usable proxies raises a typed conversion error.
- [ ] Define provider CRUD request/response fields, schedule representation, validation errors, and timestamps.
- [ ] Define update-run event fields: run ID, provider ID, trigger, stage, status, message, and timestamp.
- [ ] Define public endpoint behavior for fresh, stale-refresh-success, stale-refresh-failure, missing-version, invalid-token, `GET`, and `HEAD` requests.
- [ ] Record the frozen contracts in a protocol document before either worker builds against them.

## Worker A — Backend, Storage, Scheduling, and Deployment

Complete these tasks in order.

### A1. Application foundation

- [ ] Replace the sample entry point with the Flask application-factory pattern.
- [ ] Add backend dependencies and development/test dependency groups to `pyproject.toml`.
- [ ] Implement environment-based configuration for database path, data path, public base URL, bind address, timezone, request limits, freshness threshold, and retention count.
- [ ] Initialize SQLAlchemy, migrations, scheduler, and structured application logging.
- [ ] Add health-check behavior and basic application startup tests.

### A2. Persistence model

- [ ] Implement `Provider`, `SubscriptionVersion`, and `UpdateRun` models using the frozen field contract.
- [ ] Add the initial database migration and repository/query layer.
- [ ] Generate cryptographically random, unique public tokens.
- [ ] Add transaction-level tests for provider creation, edits, deletion, current-version selection, and token rotation.

### A3. Versioned file storage

- [ ] Implement provider-specific raw and converted storage directories.
- [ ] Write files atomically and store SHA-256 hashes of exact raw bytes and converted output.
- [ ] Promote a new version only after both files and database metadata succeed.
- [ ] Retain the five newest changed raw/converted pairs and safely prune older pairs.
- [ ] Test interrupted writes, pruning, unchanged content, and recovery without losing the last good version.

### A4. Safe provider fetcher

- [ ] Accept only HTTP and HTTPS source URLs and reject embedded credentials.
- [ ] Apply connection/read timeouts, redirect limits, response-size limits, and a configurable User-Agent.
- [ ] Block loopback, private, link-local, and otherwise unsafe resolved destinations unless explicitly allowlisted.
- [ ] Revalidate every redirect destination and protect against DNS rebinding where feasible.
- [ ] Return exact response bytes plus safe metadata without logging provider URL credentials or query secrets.
- [ ] Add tests for schemes, redirects, timeouts, oversized responses, unsafe destinations, and allowed trusted hosts.

### A5. Refresh orchestration

- [ ] Call Worker B's frozen converter interface after a successful changed fetch.
- [ ] Implement exact raw-byte hash comparison and update the last-checked time without version creation when unchanged.
- [ ] Record structured update stages and terminal success/failure states.
- [ ] Add per-provider locking so concurrent manual, scheduled, and public requests share one active refresh.
- [ ] Preserve the last successful version on fetch, conversion, storage, or database failure.
- [ ] Test first fetch, changed/unchanged fetches, conversion failure, concurrent triggers, and last-good fallback.

### A6. Backend routes and public endpoint

- [ ] Implement provider list/create/update/delete APIs using the frozen payload contract.
- [ ] Implement manual refresh and immediate token-rotation APIs.
- [ ] Implement update-run history and Server-Sent Events endpoints.
- [ ] Implement `GET` and `HEAD /subscriptions/<token>` with plain UTF-8 share links, `ETag`, and `Last-Modified`.
- [ ] Refresh synchronously when the last successful check is at least three hours old.
- [ ] On failed stale refresh, serve the last good file with `Warning` and `X-Subscription-Stale`; return `503` when no successful version exists.
- [ ] Return `404` for unknown or invalidated tokens and ensure public responses never expose the provider source URL.

### A7. Scheduling

- [ ] Implement disabled, monthly day/time, weekly weekday/time, daily time, and every-X-hours schedules.
- [ ] Register, replace, and remove scheduler jobs when provider settings change.
- [ ] Restore all enabled jobs from SQLite at application startup.
- [ ] Record missed and failed executions without corrupting provider state.
- [ ] Test timezone behavior, restart restoration, edits, disabling, and duplicate-job prevention.

### A8. Container and operations

- [ ] Add a production Dockerfile and Compose configuration with a persistent `/data` volume.
- [ ] Ensure one application/scheduler process runs per deployment.
- [ ] Add container health checks, graceful shutdown, configuration examples, and runtime data exclusions.
- [ ] Document installation, trusted-LAN limitations, backups, restoration, upgrades, and troubleshooting.

## Worker B — Conversion Engine, Management UI, and Client Behavior

Complete these tasks in order.

### B1. Converter analysis and fixtures

- [ ] Inventory protocol behavior in `external_ref/urlclash-converter` and record any GPL-derived code requiring attribution.
- [ ] Build sanitized Clash YAML fixtures and expected share-link outputs for every supported protocol.
- [ ] Include Unicode names, IPv6, optional transport/TLS fields, absent values, and malformed proxies.
- [ ] Confirm the fixtures satisfy the frozen `ConversionResult` interface.

### B2. Conversion engine core

- [ ] Implement Clash YAML byte decoding, safe YAML parsing, proxy-list extraction, and ordered protocol dispatch.
- [ ] Implement shared URL encoding, Base64, host/port, query-string, and name-fragment utilities.
- [ ] Return typed errors for malformed input or zero usable proxies.
- [ ] Return explicit per-proxy warnings/errors rather than silently dropping malformed entries.

### B3. Protocol encoders

- [ ] Implement and test Shadowsocks and ShadowsocksR encoders.
- [ ] Implement and test VMess and VLESS encoders.
- [ ] Implement and test Trojan and AnyTLS encoders.
- [ ] Implement and test Hysteria, Hysteria2, and TUIC encoders.
- [ ] Implement and test WireGuard, HTTP(S), and SOCKS5 encoders.
- [ ] Verify output parity with the reference fixtures and preserve proxy order and display names.

### B4. UI shell and provider table

- [ ] Build the responsive management page and static asset structure without introducing a separate frontend build runtime.
- [ ] Implement provider, source link, generated URL, automatic-update, status, and action columns.
- [ ] Keep a permanent new-provider row with save behavior.
- [ ] Escape rendered provider data and avoid exposing source URLs outside the management view.
- [ ] Add empty, loading, validation-error, and server-error states.

### B5. Schedule controls and actions

- [ ] Implement controls for disabled, monthly, weekly, daily, and every-X-hours schedules using the frozen API representation.
- [ ] Implement update-now behavior with duplicate-submit prevention.
- [ ] Implement copy-public-URL feedback.
- [ ] Implement token rotation with confirmation and immediate replacement of the displayed URL.
- [ ] Implement provider deletion with confirmation and clear destructive-action messaging.

### B6. Live update log

- [ ] Implement the Server-Sent Events client using the frozen event schema.
- [ ] Display querying, waiting, response received, changed/unchanged, converting, finished, and failed stages.
- [ ] Reconnect after transient stream errors and fall back to polling update-run history.
- [ ] Bound the displayed log history and prevent messages from rendering as HTML.

### B7. UI and integration tests

- [ ] Test provider creation/edit/delete, schedule-field switching, validation, copying, rotating, and manual refresh interactions.
- [ ] Test live-event ordering, reconnect behavior, polling fallback, redaction, and output escaping.
- [ ] Add integration fixtures that Worker A can use to test converter success, warnings, and typed failures.
- [ ] Verify the management page remains usable on desktop and narrow mobile layouts.

### B8. Converter documentation and licensing

- [ ] Document supported protocols, known compatibility limits, and malformed-proxy behavior.
- [ ] Preserve required GPL attribution and license notices for behavior or code derived from the reference converter.
- [ ] Add contributor guidance for creating fixtures and extending a protocol encoder.

## Integration Gates

### Gate 1 — Contracts frozen

- [ ] Both workers approve converter input/output types, API payloads, schedule schema, event schema, and public endpoint rules.
- [ ] Worker A can use a temporary converter stub; Worker B can use static API fixtures after this gate.

### Gate 2 — Converter/backend integration

- [ ] Worker B's converter passes its complete fixture suite.
- [ ] Worker A's refresh service invokes the real converter and persists a converted version.
- [ ] Changed, unchanged, warning, and conversion-error paths pass integration tests.

### Gate 3 — UI/backend integration

- [ ] Provider CRUD, all schedule types, refresh, rotation, deletion, event streaming, and polling fallback work against the real backend.
- [ ] Source URLs and sensitive query values do not appear in public responses or logs.

### Gate 4 — Release candidate

- [ ] The combined unit, integration, security, and end-to-end test suites pass in a clean container.
- [ ] Data and schedules survive a container restart.
- [ ] Simultaneous requests trigger only one refresh per provider.
- [ ] Exactly five changed raw/converted versions remain after repeated updates.
- [ ] A daed instance successfully consumes and refreshes a generated URL.
- [ ] Failed stale refreshes serve the last good subscription with stale headers.
- [ ] Token rotation invalidates the previous URL immediately.
- [ ] Operational and implementation documentation complies with `working_protocol.md`.
- [ ] Move completed planning documents into `documentation/implemented` only after every release-candidate item passes.

## Recommended Parallel Timeline

1. Both workers complete Shared Contracts and Gate 1 together.
2. Worker A completes A1–A4 while Worker B completes B1–B3.
3. Worker A completes A5 while Worker B completes B4–B5.
4. Complete Gate 2; resolve converter/backend integration issues before proceeding.
5. Worker A completes A6–A7 while Worker B completes B6–B7.
6. Complete Gate 3; then Worker A completes A8 while Worker B completes B8.
7. Both workers complete Gate 4, the final documentation handoff, and planning-file archival.
