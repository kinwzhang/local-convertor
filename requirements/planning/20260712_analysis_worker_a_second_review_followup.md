# Worker A Second Review Follow-up

## Status

Worker A's remediation is improved but has not passed the release gate. Resolve the following findings in order and add protocol-compliant fix documentation for the resulting changes.

## Critical finding

### A2-R1. Correct Docker packaging and prove clean startup

**Affected area:** `Dockerfile`, package configuration, container startup.

The Dockerfile copies only `pyproject.toml` before running `pip install .`; the `app` package and other source files are copied afterward. The project cannot be packaged correctly at the installation step.

Required work:

- Copy all files required by the build backend before installing the project, or configure a deliberate dependency-install layer that does not attempt to package absent source code.
- Explicitly configure Hatchling's package selection if automatic discovery is not reliable.
- Preserve the migration-before-Gunicorn startup sequence.
- Add a clean-image build test and a clean-volume startup test.

Acceptance checks:

- `docker build` succeeds from a clean checkout without relying on host files or caches.
- A container with a new empty `/data` volume applies migrations, becomes healthy, and can create a provider.
- A second start against the same volume preserves the provider and reports healthy.

## High-severity findings

### A2-R2. Validate redirects before making the next HTTP request

**Affected area:** `app/services/fetcher.py`.

The fetcher uses `follow_redirects=True`. HTTPX therefore contacts the redirected destination before the response hook validates it. The current hook detects an unsafe destination too late to prevent the SSRF request.

Required work:

- Disable automatic redirect following.
- Process each redirect response manually, resolve the `Location` value against the current URL, and validate scheme, credentials, hostname, port policy, and all resolved addresses before issuing the next request.
- Apply the redirect limit across the complete chain.
- Ensure a trusted initial hostname does not automatically trust a different redirect hostname.
- Retain streamed response-size enforcement for the final response.
- Add a transport-level test proving no request is issued to an unsafe redirect target.

Acceptance checks:

- Direct, DNS-resolved, and redirected requests cannot reach disallowed destinations.
- Unsafe redirects are rejected before the next network request occurs.
- Relative and safe cross-host redirects work within the configured limit.

### A2-R3. Restore the frozen Sunday-zero weekday contract

**Affected areas:** `app/services/scheduler.py`, `app/routes/api.py`, scheduler and API tests.

The shared contract defines `0 = Sunday`, but the current mapping and validation message define `0 = Monday`.

Required work:

- Map `0..6` to `sun..sat` when building APScheduler triggers.
- Update validation messages and documentation to state `0 = Sunday`.
- Add assertions for both Sunday and Monday trigger behavior.
- Confirm the frontend weekday values use the same contract.

Acceptance checks:

- A saved weekday value of `0` produces a Sunday trigger.
- A saved weekday value of `1` produces a Monday trigger.
- API, UI, scheduler, tests, and documentation all use the same mapping.

### A2-R4. Make stale-response outcome explicit and reliable

**Affected areas:** `app/services/updater.py`, `app/routes/subscriptions.py`.

The route checks `provider.last_error` on an object loaded before refresh. The orchestrator performs the update in another application context/session, so the route can retain stale ORM state and omit required stale headers after a failed refresh.

Required work:

- Return a typed refresh outcome that distinguishes success, unchanged success, failure, and already-in-progress contention.
- Base stale-response headers on that explicit outcome rather than a previously loaded ORM object.
- Alternatively reload and expire state after refresh, but still distinguish lock contention from refresh failure.
- Set `Warning` and `X-Subscription-Stale: true` only when a required refresh fails and a last-good version is served.
- Add real-session integration tests rather than relying only on mocks that mutate the original object.

Acceptance checks:

- A failed stale refresh always serves the last-good content with both stale headers.
- A successful or unchanged refresh does not add stale headers.
- Concurrent refresh contention has documented and tested response behavior.

### A2-R5. Complete type-safe API validation

**Affected area:** `app/routes/api.py`; preferably a shared validation module.

The validation added during the first remediation does not safely handle wrong JSON types and omits several frozen constraints. Payloads such as numeric names, numeric URLs, list schedules, malformed times, float intervals, and embedded URL credentials can be accepted or cause `500` responses.

Required work:

- Require the top-level JSON payload and `schedule` to be objects.
- Validate name as a string of 1–128 characters.
- Validate source URL as a string using HTTP/HTTPS, with hostname and no embedded credentials.
- Validate `enabled` as a boolean.
- Require integer-only day and interval values; reject booleans and floats.
- Validate `time_of_day` strictly as `HH:MM` with valid hour and minute ranges and require it for monthly, weekly, and daily schedules.
- Require schedule-specific fields instead of silently substituting defaults.
- Reject unknown and immutable fields consistently for `POST` and `PATCH`.
- Centralize identical create/update validation logic.

Acceptance checks:

- Every malformed payload returns the frozen validation response, never `500`.
- Boundary values for every field are covered.
- `POST` and `PATCH` enforce consistent rules.

## Medium-severity findings

### A2-R6. Finish recoverable version pruning

**Affected area:** `app/services/version_store.py` and persistence operations.

New-version cleanup improved, but pruning still deletes each file before deleting its database record. An interruption can leave retained metadata referencing missing files.

Required work:

- Redesign pruning so a failure cannot leave an active database record referencing a deleted file.
- Use a recoverable deletion state, trash/rename phase, or equivalent transactional strategy across metadata and filesystem operations.
- Preserve the latest five complete raw/converted pairs under every injected failure point.
- Add failure-injection tests for file rename/delete and database commit failures during pruning.

### A2-R7. Apply the configured timezone to interval triggers

**Affected area:** `app/services/scheduler.py`.

Cron triggers receive the configured timezone, but `IntervalTrigger` is constructed without it.

Required work:

- Pass the configured timezone to interval triggers.
- Define and test the first-run anchor across restarts.
- Verify behavior is independent of the container's system timezone.

### A2-R8. Make health verify schema readiness

**Affected area:** `app/__init__.py` health endpoint.

`SELECT 1` proves database connectivity only. It succeeds when migrations or required tables are missing.

Required work:

- Check the current migration revision against the expected head or verify all required tables in addition to connectivity.
- Return `503` until the schema is ready.
- Test connectivity failure, missing schema, outdated schema, and current schema.

### A2-R9. Produce a warning-free, fully released test run

**Affected areas:** `tests/conftest.py`, static response tests, database and scheduler teardown.

The strict run `.venv/bin/pytest -q -W error` produced `130 passed, 3 failed`, followed by an unclosed SQLite connection warning.

Required work:

- Close static-file responses explicitly in tests.
- Remove and dispose of SQLAlchemy sessions and engines during teardown.
- Shut down the global scheduler after the test session.
- Keep warnings promoted to errors in the standard test configuration or CI.

Acceptance checks:

- `.venv/bin/pytest -q -W error` exits successfully with no warnings or unraisable exceptions.
- No background thread, scheduler, response, file, or database resource remains open after the suite.

## Delivery requirement

The current working tree contains uncommitted changes to `app/services/updater.py` that complete required SSE event fields. Include the validated change in the Worker A remediation commit; a clean checkout of the submitted commit must pass the same tests.

## Worker A second-pass completion gate

- [ ] A2-R1 through A2-R9 are resolved.
- [ ] A clean checkout has no required uncommitted changes.
- [ ] Strict tests pass without warnings.
- [ ] Clean Docker build and clean-volume migration startup pass.
- [ ] Worker B's UI works against the finalized validation and event contracts.
- [ ] Fix documentation is added according to `working_protocol.md`.

