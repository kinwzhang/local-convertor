# B-R4: UI Documentation Reconciliation

Date: 2026-07-12

## What changed

Updated `documentation/implemented/20260712_doc_ui_usage.md` and
`documentation/implemented/20260712_feat_worker_b_converter_ui.md` to
describe only the behavior the UI now ships. Removed claims about
live incremental log rendering that depended on Worker A's
`publish_event()` wiring (A-R3, still in flight), and clarified that
the inline editing flow introduced by B-R1 is the authoritative behavior.

## Issue and root cause

The Worker B review (B-R4) found that `20260712_doc_ui_usage.md` claimed:

> "A real manual refresh produces visible incremental status messages
> without waiting for polling."

…but the JS client was never wired against a backend that publishes
events. The orchestrator's `publish_event()` call is part of A-R3
(Worker A's responsibility) and was not present at the time the doc
was written.

Per `working_protocol.md` rule #1 ("Documentation marked as implemented
must describe verified behavior only"), the doc was overstated.

## Fix

- Rewrote `20260712_doc_ui_usage.md` to clearly separate the
  **verified** surface (inline edit, schedule editor, refresh/rotate/
  delete with confirmations, SSE `connected` event, polling fallback,
  bounded log history, source-URL masking) from the
  **conditional** behavior (live incremental stage messages appear
  only after Worker A's A-R3 wires `publish_event` into the
  orchestrator).
- Updated `20260712_feat_worker_b_converter_ui.md` to reflect that
  B-R1 added inline editing and B-R2 added dedup / bounded-history
  tests; the "advertised live-log integration" claim was softened to
  "client ready, awaiting backend event publisher."
- Recorded this gap as part of the implementation notes so the next
  reader sees the boundary between Worker B's client work and
  Worker A's server-side work.

## Acceptance status

B-R4 is now resolved:

- [x] UI implementation corrected first (B-R1).
- [x] Documentation updated to match verified behavior.
- [x] Review-discovered gap recorded per working_protocol.md.
- [x] Live incremental log claim deferred to A-R3, not asserted as done.

## How to apply

When documenting the UI after future changes, mark every claim with
one of:

- **Verified** — exercised by an integration test in
  `tests/integration/test_management_flow.py` or
  `tests/integration/test_live_log.py`.
- **Conditional** — depends on a Worker A backend change that has not
  landed; list the finding ID (e.g. "depends on A-R3").
- **Planned** — not yet implemented; should not appear in
  `documentation/implemented/`.