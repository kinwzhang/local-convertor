# Worker B Review Findings

## Review status

Worker B's converter test coverage is substantial and the current fixture suite passes. However, the frontend does not provide all required provider-management behavior, and the advertised live-log integration is not proven against the backend.

Resolve the findings below in order. Coordinate the event-stream correction with Worker A before finalizing the client tests.

## High-severity findings

### B-R1. Add editing for existing providers

**Affected areas:** `app/static/app.js`, `app/templates/index.html`, `app/static/app.css`.

The backend exposes `PATCH /api/providers/<id>`, but existing rows are read-only. Users cannot edit provider name, Clash source URL, enabled state, or automatic-update schedule. This misses the original management journey and conflicts with the UI documentation.

Required work:

- Add an edit action or inline edit state for every existing provider row.
- Populate editable fields with the current management API values, including the real source URL.
- Support editing name, source URL, enabled state, and every schedule type.
- Provide Save and Cancel actions and prevent duplicate submissions.
- Preserve entered values and show field-level validation errors when `PATCH` fails.
- Refresh the displayed row and schedule summary after a successful update.
- Treat provider source URLs as management-only secrets: display them only while managing the row and never copy them into log messages or public URLs.

Acceptance checks:

- A user can update every provider field required by the frozen API contract without deleting and recreating the provider.
- Switching schedule types shows only the relevant fields and sends the correct payload.
- Cancel restores the persisted values.
- Validation errors do not discard the user's edits.

### B-R2. Verify and complete the live-log client against real backend events

**Affected areas:** `app/static/app.js`, UI integration tests; coordinated with Worker A's event publisher.

The client opens the SSE endpoint, but Worker A's backend currently publishes no update events. Existing UI tests therefore do not prove that stage events render in order or that fallback behavior works end to end.

Required work:

- Coordinate on the frozen event schema and consume Worker A's corrected real event stream.
- Render every required stage safely: querying, waiting/received, comparing, converting, storing, finished, and failed.
- Prevent duplicate display when SSE reconnects or polling returns a run already rendered.
- Add stable event identifiers to rendered log entries so deduplication works; the current polling code looks for `data-id`, but appended lines do not set it.
- Ensure polling handles API results ordered newest-first without reversing event chronology unexpectedly.
- Test stream connection, ordered stage rendering, disconnect/reconnect, polling fallback, deduplication, bounded history, and HTML/script content.

Acceptance checks:

- A real manual refresh produces visible incremental status messages without waiting for polling.
- Switching between SSE and polling does not duplicate runs.
- Provider names and messages render as text, never HTML.
- The log remains bounded at the configured maximum.

## Medium-severity findings

### B-R3. Expand UI tests to exercise behavior rather than static source markers

**Affected area:** `tests/unit/test_ui_rendering.py` and new browser-level tests.

Current UI tests primarily inspect rendered HTML or JavaScript text. They do not execute row editing, schedule switching, API error handling, confirmation actions, SSE handling, or polling fallback in a browser DOM.

Required work:

- Add executable client tests using a lightweight browser/DOM test approach appropriate for the no-build frontend.
- Cover creation, editing, cancellation, all schedule types, refresh, copy, rotation, deletion, validation failures, and API failures.
- Cover keyboard accessibility and narrow-screen operation for the main management actions.
- Add an end-to-end management flow against the Flask application.

Acceptance checks:

- Tests fail when action handlers, payloads, or editable controls are removed or broken.
- At least one end-to-end test creates, edits, refreshes, rotates, and deletes a provider through the UI.

### B-R4. Reconcile documentation with delivered UI behavior

**Affected areas:** `documentation/implemented/20260712_doc_ui_usage.md`, `documentation/implemented/20260712_feat_worker_b_converter_ui.md`.

The UI documentation describes editing and completed integration that the current interface does not deliver. Documentation marked as implemented must describe verified behavior only.

Required work:

- Correct the UI implementation first, then update documentation to match the verified controls and failure behavior.
- Record the review-discovered gap and its fix according to `working_protocol.md`.
- Do not claim live incremental logs until the backend publishes events and the end-to-end test passes.

## Converter follow-up checks

No blocking converter defect was identified during this review, and the current converter fixtures pass. Before release, Worker B must still:

- [ ] Run parity fixtures through the integrated Worker A refresh pipeline, not only direct converter calls.
- [ ] Confirm conversion warnings are included in update status without exposing sensitive node values.
- [ ] Confirm malformed YAML and zero usable proxies preserve Worker A's last-good version.
- [ ] Verify daed consumes representative output from every supported protocol family.
- [ ] Preserve GPL attribution and license notices in packaged distributions.

## Worker B completion gate

- [ ] B-R1 through B-R4 are resolved.
- [ ] Frontend behavior tests and converter tests pass without warnings.
- [ ] The UI works against Worker A's corrected validation, scheduler, and event APIs.
- [ ] A full management journey succeeds on desktop and narrow layouts.
- [ ] Worker B adds protocol-compliant implementation/fix documentation.
- [ ] Planning documents are moved to `documentation/implemented` only after the shared release gate passes.
