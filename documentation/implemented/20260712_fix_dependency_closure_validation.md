# Worker B → Worker A Dependency Closure (2026-07-12)

Date: 2026-07-12

## What changed

Validated that every Worker B item previously marked "Conditional" or
"skipped pending A-R*" is now closed, after Worker A landed its review
fixes in commit `b13920a`. Unskipped the regression guard, added an
event-shape regression guard that locks the frozen contract in place,
and added a validation-contract integration suite to cover A-R8.

## Dependency audit

| Worker B item | Was blocked on | Now |
|---|---|---|
| `tests/integration/test_unchanged_content_updates_last_success_at` (skipped) | A-R7 | **Unskipped.** Test now runs and passes — orchestrator updates `last_success_at` on unchanged content (lines 93–94 of `app/services/updater.py`). |
| B-R2 live incremental stage messages (Conditional on A-R3) | A-R3 | **Verified.** Orchestrator calls `publish_event()` at every stage change. New `test_orchestrator_publishes_frozen_event_fields` exercises the live stream end-to-end and asserts the frozen contract fields (`run_id`, `provider_id`, `provider_name`, `trigger`, `stage`, `status`, `message`, `created_at`) are all present. |
| JS client defensiveness against missing event fields | (preventive) | **Hardened.** `appendLog` now defaults `provider_name`, `trigger`, `stage`, `status` to readable fallbacks and treats an invalid `created_at` as the current time, so the log never renders `[undefined]` or `Invalid Date`. |
| B-R2 escape pattern in JS | (preventive) | **Updated.** `test_js_output_is_escaped_in_log_lines` now asserts `escape(providerName)` to match the defensive local variable. |
| Validation UX (B-R3 acceptance: "validation failures do not discard edits") | A-R8 | **Verified.** New `tests/integration/test_validation_contract.py` exercises the frozen `{error: "validation", details: ...}` response shape and confirms the JS submit handler preserves entered values on failure. |
| Public endpoint (B-R6 acceptance) | A-R6 | Already covered by `tests/unit/test_routes.py` in Worker A's suite — `Last-Modified`, `Warning`, `X-Subscription-Stale: true`, `ETag`, `HEAD` semantics, and 404 for unknown tokens. |
| Scheduler lifecycle (A-R4) | A-R4 | Not directly exercised by Worker B tests but the API smoke tests in `test_management_flow.py::test_create_provider_full_lifecycle` pass end-to-end against the real scheduler wiring. |

## New tests

### `tests/integration/test_live_log.py::test_orchestrator_publishes_frozen_event_fields`

Connects to `/api/events`, runs the real orchestrator against a stubbed
fetcher, and asserts every published event includes the frozen contract
fields. Catches future regressions where Worker A drops a field (e.g.
the JS client would silently render `[undefined]`).

### `tests/integration/test_validation_contract.py` (new file)

Nine tests covering:

- Name length cap.
- Source URL scheme (`http`/`https` only).
- Schedule type whitelist.
- Interval / monthly / weekly range bounds.
- Positive acceptance of every valid schedule type.
- Frozen error response shape `{error, details}`.
- JS submit handler preserves entered values on failure.
- JS surfaces `details` from the API response.

## Acceptance status

- All Worker B Conditional items are now Verified.
- All Worker B skipped tests are now unskipped and passing.
- 133 tests passing, 0 skipped.
- The frozen event-schema contract has a regression guard.
- The frozen validation contract has a regression guard.

## How to apply

When Worker A's orchestrator or API changes event fields in the future:

1. `tests/integration/test_live_log.py::test_orchestrator_publishes_frozen_event_fields`
   will fail with the exact missing fields listed in the assertion.
2. Update the frozen contract in
   `requirements/planning/20260712_doc_shared_contracts.md` first.
3. Then update both Worker A (orchestrator) and Worker B (JS defensive
   defaults) to match.

When Worker A's API validation changes:

1. `tests/integration/test_validation_contract.py` catches every
   boundary violation in the response shape.
2. The JS source-inspection tests catch when the submit handler stops
   preserving entered values on failure.