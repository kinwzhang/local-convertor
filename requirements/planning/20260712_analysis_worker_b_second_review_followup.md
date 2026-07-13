# Worker B Second Review Follow-up

## Status

Worker B added editable provider rows and broader integration tests. The UI remediation is directionally complete, but the browser behavior and shared weekday/event contracts are not yet fully proven.

Coordinate B2-R1 and B2-R2 with Worker A before declaring completion.

## High-severity finding

### B2-R1. Align the frontend weekday values with Sunday zero

**Affected areas:** `app/static/app.js`, schedule controls, UI tests and documentation.

The frozen shared contract defines `day_of_week: 0` as Sunday. Worker A's current backend incorrectly treats zero as Monday; Worker B must ensure the frontend does not encode or document the same mistake.

Required work:

- Make the weekday selector submit `0 = Sunday` through `6 = Saturday`.
- Display the correct weekday for provider schedule summaries and edit controls.
- Add UI assertions for Sunday and Monday payloads and summaries.
- Coordinate with Worker A so the API and scheduler use identical values.

Acceptance checks:

- Selecting Sunday sends `day_of_week: 0`.
- Loading `day_of_week: 0` selects and displays Sunday.
- Editing without changing the weekday preserves the same semantic day.

## Medium-severity findings

### B2-R2. Add executable browser/DOM behavior tests

**Affected areas:** UI test suite and frontend behavior.

The new management-flow tests call Flask APIs and inspect JavaScript with regular expressions. They do not execute the JavaScript in a DOM or browser, so they cannot prove that inline editing, schedule switching, validation preservation, confirmation dialogs, SSE reconnect, polling fallback, or responsive interactions work.

Required work:

- Add a browser or executable DOM test setup appropriate for the dependency-free frontend.
- Execute the actual `app.js` against the rendered management page.
- Test provider creation, begin edit, cancel, successful save, field-level API failure, and value preservation.
- Test all schedule-type transitions and payloads.
- Test refresh, copy, rotate confirmation, delete confirmation, and failed actions.
- Test SSE stage rendering, disconnect/reconnect, polling fallback, deduplication, and bounded history.
- Include at least one narrow-viewport management journey and basic keyboard interaction.

Acceptance checks:

- Tests fail when the relevant handler or DOM control is functionally broken, not merely when source text is absent.
- One browser-driven flow creates, edits, refreshes, rotates, and deletes a provider.
- One browser-driven flow proves SSE-to-polling fallback without duplicate log entries.

### B2-R3. Verify live logs against the committed full event schema

**Affected areas:** `app/static/app.js`, `tests/integration/test_live_log.py`, shared Worker A integration.

Worker A's full event-schema additions are currently uncommitted. Worker B's final verification must run against the committed backend that provides `run_id`, provider fields, trigger, stage, status, timestamps, and completion state.

Required work:

- Ensure every rendered log line receives a stable run/stage identifier used by SSE and polling deduplication.
- Verify incremental stages appear in chronological order.
- Avoid double escaping values passed through `document.createTextNode`; render raw strings as text rather than pre-escaping them into visible HTML entities.
- Confirm failure messages and provider names never render as HTML.
- Run the UI event tests against a clean checkout after Worker A commits the event-schema correction.

Acceptance checks:

- SSE and polling do not duplicate the same run/stage entry.
- Names containing `<`, `&`, quotes, and Unicode display correctly as text and cannot inject markup.
- Missing or malformed events are handled without breaking subsequent updates.

### B2-R4. Repair Worker B-owned resource-cleanup test failures

**Affected area:** `tests/unit/test_ui_rendering.py` and other UI response tests.

With warnings promoted to errors, static CSS and JavaScript response tests leak file handles. These failures prevent the promised warning-free suite.

Required work:

- Use response context managers or explicitly close every streamed/static response.
- Audit other UI tests for the same pattern.
- Coordinate with Worker A on shared fixture and database teardown warnings.

Acceptance checks:

- All Worker B tests pass under `.venv/bin/pytest -q -W error`.
- No static response emits an unclosed-file warning.

## Documentation follow-up

- Update UI documentation only after executable behavior tests pass.
- Clearly distinguish Flask API integration tests from browser-driven UI tests.
- Record the second remediation and its test evidence using the working protocol's filename convention.

## Worker B second-pass completion gate

- [ ] B2-R1 through B2-R4 are resolved.
- [ ] Executable browser/DOM tests cover the full management flow.
- [ ] Live-log tests pass against Worker A's committed final event schema.
- [ ] Worker B tests pass with warnings treated as errors.
- [ ] UI documentation matches verified behavior.
- [ ] Fix documentation is added according to `working_protocol.md`.
