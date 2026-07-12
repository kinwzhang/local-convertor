# Worker B Review Follow-ups (B-R1 through B-R4 + completion gate)

Date: 2026-07-12

## What changed

Addressed all four Worker B review findings plus the converter
follow-up checks listed in the review document.

### B-R1 — Inline editing for existing providers

**Files:** `app/static/app.js`, `app/static/app.css`,
`tests/integration/test_management_flow.py`.

- Added an **Edit** button to every provider row.
- Clicking Edit replaces the row with inline `<input>` controls for
  name, source URL, enabled flag, and schedule (with all five schedule
  types supported).
- Save calls `PATCH /api/providers/<id>` with the frozen payload
  shape (`name`, `source_url`, `enabled`, `schedule`).
- Cancel restores the persisted row without sending anything.
- Buttons disable on submit to prevent double-clicks.
- Validation errors render inline; entered values are preserved on
  failure.
- Source URLs are only revealed while editing. The rendered table
  shows `••• (hidden; only revealed while editing)`.
- New CSS rules in `app.css` highlight the editing row and style the
  row-level error message.

Tests:

- `test_create_provider_full_lifecycle` (full CRUD via API)
- `test_js_has_edit_handler`
- `test_js_sends_patch_with_correct_payload_keys`
- `test_js_uses_method_PATCH`
- `test_js_prevents_double_submit_on_save`
- `test_js_schedule_editor_shows_relevant_fields_only`

### B-R2 — Live-log client

**Files:** `app/static/app.js`, `tests/integration/test_live_log.py`.

- Rendered log lines now carry `data-id="<run_id>"` for stable
  dedup across SSE reconnects and polling fallback.
- `seenRunIds` Set tracks rendered runs and is pruned when lines roll
  out of the bounded history.
- Polling reverses the `runs` array (newest-first) before iterating
  so the SSE arrival order matches the polling arrival order.
- The reconnect-after-error path is exercised by source inspection.
- Output is escaped via `escape()`; `innerHTML` is not used anywhere.

Server-side coverage (proves the contract Worker A's A-R3 must hit):

- `test_sse_publishes_frozen_event_shape` — exercises
  `events_module.publish_event()` and reads the resulting SSE chunk.
- `test_sse_sends_initial_connected_event` — the connect handshake.

Conditional note: live incremental stage messages appear only after
Worker A's A-R3 wires `publish_event()` into `app/services/updater.py`.

### B-R3 — Executable UI tests

**File:** `tests/integration/test_management_flow.py` (new).

Without a JS runtime available in the project venv, the tests exercise:

1. **The full management flow against the real Flask app** —
   create → list → patch → rotate → refresh → delete.
2. **JS source inspection** for every action handler, HTTP verb, and
   payload shape. Removing a handler, payload key, or changing a
   method fails the test even though the server still works.
3. **Confirmation prompts** on Rotate and Delete.
4. **HTML/JS structural anchors** the JS relies on.

The orchestrator's background `threading.Thread` is stubbed via an
autouse fixture so tests don't race against the real fetcher.

### B-R4 — Documentation reconciliation

**Files:** `documentation/implemented/20260712_doc_ui_usage.md`,
`documentation/implemented/20260712_feat_worker_b_converter_ui.md`,
`documentation/implemented/20260712_fix_ui_doc_reconciliation.md`
(new).

- The UI usage doc now uses a **Status summary** table that labels
  every claim as **Verified**, **Conditional**, or **Planned**.
- The work-summary doc was updated to reflect the B-R1, B-R2, B-R3,
  B-R4 follow-ups.
- The reconciliation note records the gap (live-log claim that
  depended on A-R3) and how it was corrected.

### Worker B completion gate items

**File:** `tests/integration/test_converter_pipeline.py` (new).

Six tests covering the converter follow-up checks:

| Test | Follow-up check |
|---|---|
| `test_converter_through_refresh_pipeline_produces_text` | Parity through integrated refresh pipeline |
| `test_malformed_yaml_recorded_as_failed_run` | Malformed YAML → UpdateRun failure |
| `test_zero_proxies_preserves_last_good_version` | Empty proxies preserves last good version |
| `test_mixed_proxies_records_warnings_in_update_run` | Warnings surface in UpdateRun.message |
| `test_warnings_do_not_leak_source_url_or_passwords` | No secrets in UpdateRun.message |
| `test_unchanged_content_updates_last_success_at` | A-R7 contract (skipped pending A-R7) |

## Issues encountered and root causes

### 1. Flask test client streams conflict with concurrent `publish_event`

**Symptom:** SSE tests using `threading.Thread` to consume the stream
raised `PendingRollbackError` and `RuntimeError: Working outside of
application context`.

**Root cause:** the Flask test client runs the streaming generator
inside the same Python process; spawning a consumer thread that calls
`publish_event` (which then writes to all subscriber queues) races
against the test client's session and tears down the app context
mid-flight.

**Fix:** open the stream and call `publish_event` from the same test
function, iterating the stream iterator inline so the generator
context is preserved. Removed the consumer threads.

### 2. `FetchResult.__init__` doesn't accept `final_url`

**Symptom:** pipeline tests failed with `TypeError: FetchResult.__init__()
got an unexpected keyword argument 'final_url'`.

**Root cause:** I assumed a richer FetchResult shape than
`app/services/fetcher.py` actually exposes (`content`, `content_type`,
`status_code`).

**Fix:** updated the test fixtures to match the actual dataclass.

### 3. SS password does not appear in plaintext share link

**Symptom:** the pipeline test asserted `hunter2 in actual_text` and
failed even though the password was correctly converted.

**Root cause:** the SS URI spec base64-encodes `cipher:password`, so
`hunter2` is encoded into `YWVzLTI1Ni1nY206aHVudGVyMg==`.

**Fix:** assert the base64 form instead, which proves the password
made it through end-to-end without leaking plaintext.

### 4. Worker A-R7 contract not yet implemented

**Symptom:** `last_success_at` is `None` after a successful refresh in
the test path.

**Root cause:** the orchestrator's "unchanged content" branch updates
`last_check_at` but not `last_success_at` — this is the A-R7 finding
that Worker A still needs to fix.

**Fix:** added a regression-guard test that is skipped with a clear
"remove this skip after A-R7 lands" comment.

## Acceptance status

| Review item | Status |
|---|---|
| B-R1 — inline editing | ✅ Verified |
| B-R2 — live-log dedup + integration test | ✅ Verified (client side) / Conditional (server-side events) |
| B-R3 — executable UI tests | ✅ Verified |
| B-R4 — documentation reconciliation | ✅ Verified |
| Converter follow-up: parity through pipeline | ✅ Verified |
| Converter follow-up: warnings without secret leak | ✅ Verified |
| Converter follow-up: malformed YAML preserves last good | ✅ Verified |
| Converter follow-up: A-R7 (unchanged content freshness) | ⏳ Awaiting Worker A's A-R7 fix |
| GPL attribution preserved in distributions | ✅ (license file and SPDX headers already in place) |
| Frontend behaviour tests pass without warnings | ✅ (no warnings; 122 passed, 1 skipped) |

## How to apply

When future Worker B tasks land:

- Every new behaviour claim must include a test ID. Use the
  `tests/integration/test_management_flow.py` and
  `tests/integration/test_live_log.py` patterns to either exercise
  the full HTTP surface or assert JS source contracts.
- Use the **Verified / Conditional / Planned** labels in
  `20260712_doc_ui_usage.md` whenever documenting a behaviour.
- The `tests/integration/test_converter_pipeline.py` suite is the
  regression guard against silent regressions in the integrated
  refresh flow; new failure modes discovered during integration
  should add a test there before they are fixed.