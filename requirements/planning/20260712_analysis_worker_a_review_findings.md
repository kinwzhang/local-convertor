# Worker A Review Findings

## Review status

Worker A's backend work is not release-ready. The test suite reports `89 passed`, but one concurrency test raises an unhandled thread exception and several required production and integration behaviors are absent.

Resolve the findings below in severity order. After each correction, add the feature or fix documentation required by `working_protocol.md`.

## Critical finding

### A-R1. Initialize the production database

**Affected areas:** `app/__init__.py`, `Dockerfile`, migration configuration.

The test fixture creates tables with `db.create_all()`, but production startup neither creates tables nor applies migrations. No migration files are present. A fresh container can start successfully while every database-backed endpoint fails.

Required work:

- Add and commit an initial migration for `Provider`, `SubscriptionVersion`, and `UpdateRun`.
- Apply migrations as an explicit container startup step before Gunicorn starts.
- Do not silently ignore migration or schema failures.
- Add a clean-volume deployment test that starts the application, checks `/health`, and successfully creates a provider.

Acceptance checks:

- A new empty `/data` volume becomes usable without manual database commands.
- Restarting with an existing database preserves providers and versions.
- Migration failure prevents the application from reporting a healthy operational state.

## High-severity findings

### A-R2. Complete SSRF and response-size protection

**Affected area:** `app/services/fetcher.py`.

Current validation checks literal IP addresses only. Hostnames resolving to loopback/private/link-local/reserved addresses are accepted, and automatic redirects are not revalidated. The response is fully buffered before its size is checked.

Required work:

- Resolve hostnames and reject every unsafe resolved address unless the hostname is explicitly allowlisted.
- Follow redirects manually and revalidate the scheme, credentials, hostname, resolved addresses, and redirect count at each hop.
- Stream response bytes and stop as soon as the configured maximum size is exceeded.
- Ensure trusted-host matching is normalized and exact; document its security implications.
- Add tests for `localhost`, public-looking domains resolving privately, IPv4/IPv6 private addresses, unsafe redirects, redirect loops, oversized streamed bodies, and allowlisted hosts.

Acceptance checks:

- No untrusted request can reach loopback, private, link-local, multicast, unspecified, or reserved destinations through direct URLs, DNS, or redirects.
- Oversized responses are terminated without buffering the full body.

### A-R3. Publish update stages to the SSE stream

**Affected areas:** `app/repositories/provider_repo.py`, `app/routes/events.py`, `app/services/updater.py`.

`publish_event()` is never called. Connected clients receive only keepalives, and polling can retrieve only a run's latest stored state rather than its progression.

Required work:

- Publish the frozen update-run event after run creation, every stage change, and terminal completion/failure.
- Publish only after the corresponding database transaction succeeds.
- Preserve the frozen event shape and ensure messages do not expose source URLs or query-string secrets.
- Add an integration test that connects to SSE, performs a refresh, and observes ordered progress through a terminal event.

Acceptance checks:

- The UI receives querying, received, comparing/converting, storing, and finished/failed events as applicable.
- Multiple connected clients receive the same events.
- A slow or disconnected client does not block refresh processing.

### A-R4. Connect provider mutations to scheduler lifecycle

**Affected areas:** `app/routes/api.py`, `app/services/scheduler.py`.

Provider creation and updates do not schedule or reschedule jobs, and deletion does not remove jobs. Schedule changes therefore require a restart, and deleted providers leave orphan jobs.

Required work:

- Schedule a newly created enabled provider after its database commit.
- Reschedule after schedule or enabled-state updates.
- Remove the scheduled job when a provider is disabled or deleted.
- Define rollback/error behavior if scheduler mutation fails after persistence.
- Add integration tests that exercise create, edit, disable, re-enable, and delete through the API and inspect the resulting jobs.

Acceptance checks:

- Every enabled provider has at most one correctly configured job.
- API changes take effect without application restart.
- Deleted and disabled providers have no active job.

### A-R5. Correct scheduler weekday and timezone behavior

**Affected area:** `app/services/scheduler.py`.

The frozen contract defines Sunday as weekday `0`, while APScheduler interprets numeric `0` as Monday. Triggers also omit the configured timezone.

Required work:

- Translate contract weekdays to explicit APScheduler weekday names or the correct numeric mapping.
- Instantiate the scheduler and every trigger with the configured timezone.
- Define monthly behavior for days that do not exist in shorter months and document it.
- Add deterministic tests for Sunday, Monday, configured-timezone execution, daylight-saving zones, and restart restoration.

Acceptance checks:

- A configured Sunday schedule runs on Sunday in the configured timezone.
- Default scheduling uses `Asia/Hong_Kong`, independent of the container's system timezone.

### A-R6. Implement the complete public subscription response contract

**Affected area:** `app/routes/subscriptions.py`.

The public endpoint omits `Last-Modified`. It also serves a last-good response after failed stale refresh without the required `Warning` and `X-Subscription-Stale: true` headers.

Required work:

- Distinguish refresh success, refresh failure, and lock-contention outcomes.
- Add an RFC-compliant `Last-Modified` based on the served version.
- Add stale headers only when an attempted required refresh fails and a prior version is served.
- Preserve identical headers for `GET` and `HEAD`, with no `HEAD` body.
- Add endpoint tests for fresh, stale-success, stale-failure with last-good data, no version, invalid token, `GET`, and `HEAD`.

Acceptance checks:

- Responses exactly match the frozen public endpoint table.
- Provider source details never appear in response bodies or headers.

### A-R7. Treat unchanged content as a successful freshness check

**Affected area:** `app/services/updater.py`.

An unchanged response updates `last_check_at` but not `last_success_at`. Freshness is calculated from `last_success_at`, causing every request to refetch indefinitely once the last changed version is older than three hours.

Required work:

- Update the successful freshness timestamp after a valid unchanged provider response.
- Clear any previous fetch error after that successful check.
- Preserve the existing version without creating another version pair.
- Add a regression test proving subsequent public requests remain fresh for the configured period.

Acceptance checks:

- An unchanged successful fetch prevents another request-triggered fetch for three hours.
- Version count and current output remain unchanged.

## Medium-severity findings

### A-R8. Enforce the frozen API validation contract

**Affected areas:** `app/routes/api.py`, `app/repositories/provider_repo.py`.

Creation checks only for nonempty name and URL; updates perform no validation. Invalid schedules and source URLs can be persisted and later crash scheduler or fetch processing.

Required work:

- Centralize create/update validation rather than placing raw request values directly into models.
- Validate name type and length, HTTP/HTTPS URL shape, schedule type, required schedule fields, day/time ranges, interval range, and boolean fields.
- Return the frozen `{error: "validation", details: ...}` response consistently.
- Reject unknown or immutable fields rather than silently accepting them.
- Add boundary and malformed-payload tests for both `POST` and `PATCH`.

### A-R9. Make version creation and pruning recoverable

**Affected areas:** `app/services/version_store.py`, persistence repository.

Files are written before database insertion, so database failure leaves orphan files. Pruning deletes files before records, so partial failure can leave records referencing missing files.

Required work:

- Stage both new files, commit metadata and promotion coherently, and clean staged/orphan files on failure.
- Make current-version visibility change only after both files are durable and readable.
- Rework pruning so interruptions cannot leave current or retained database records referencing missing files.
- Add failure-injection tests for the first write, second write, database insertion, promotion, file deletion, and database deletion.

### A-R10. Repair the concurrency test

**Affected area:** `tests/unit/test_updater.py`.

The concurrent-refresh test accesses an expired SQLAlchemy model outside an application context. Pytest reports the exception only as a warning, so the test passes without proving deduplication.

Required work:

- Capture the primitive provider ID before starting the thread.
- Propagate thread exceptions into the test result.
- Assert fetch/converter invocation count and the explicit result returned to both callers.
- Configure pytest to fail on unhandled thread exceptions.

Acceptance checks:

- The complete test run has no warnings.
- The test fails if two provider fetches occur.

## Worker A completion gate

- [ ] All A-R1 through A-R10 findings are resolved.
- [ ] Backend unit, integration, security, and clean-container tests pass without warnings.
- [ ] Worker B's real converter and event client pass against the corrected backend.
- [ ] A real daed instance successfully consumes fresh and stale-fallback subscription responses.
- [ ] Worker A adds protocol-compliant implementation/fix documentation.
- [ ] Planning documents are moved to `documentation/implemented` only after the shared release gate passes.
