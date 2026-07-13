# UI Documentation (Worker B deliverable B4-B6)

Date: 2026-07-12 (revised after Worker B second review)

## Status summary

| Capability | Status | Evidence |
|---|---|---|
| Provider table render | Verified | `test_index_page_renders`, `test_static_js_served` |
| Inline edit (B-R1) | Verified | Executable JSDOM edit, cancel, and validation-preservation tests |
| Schedule editor (monthly/weekly/daily/interval) | Verified | Executable JSDOM transition and payload tests |
| Refresh / Copy / Rotate / Delete actions | Verified | `test_js_refresh_calls_correct_endpoint`, `test_js_rotate_calls_correct_endpoint`, `test_js_delete_calls_correct_endpoint`, `test_js_confirms_destructive_actions` |
| Source-URL masking | Verified | `test_js_copies_public_url_only_on_copy_action`, `test_no_source_url_leak_in_index_html` |
| SSE `connected` event | Verified | `test_sse_sends_initial_connected_event` |
| Polling fallback | Verified | Executable JSDOM reconnect/fallback test plus integration guards |
| Bounded log history | Verified | `test_js_log_history_bounded` |
| Safe text rendering | Verified | Executable hostile-text DOM test; no `innerHTML` use |
| Stable event dedup via `data-id` | Verified | Composite `run_id:stage:status` executable test |
| Live incremental stage messages | Verified against current worktree | Executable multi-stage SSE test; final clean-checkout verification depends on Worker A committing the event schema |

## Layout

`app/templates/index.html` is a single-page management console. It ships
two static assets served from `/static/`:

- `app.css` — responsive layout (collapses cleanly below 720 px).
- `app.js` — vanilla-JS client. No build runtime, no dependencies.

## Behaviour

### Provider table

Renders one row per `Provider` returned by `GET /api/providers`. Each row
shows the provider name, generated URL, schedule summary, last status, and
five actions:

| Action | Effect |
|---|---|
| Refresh | `POST /api/providers/{id}/refresh` (orchestrator is stubbed in tests) |
| Copy URL | Copies the public subscription URL to the clipboard |
| Edit | Replaces the row with inline inputs (B-R1) |
| Rotate | `POST /api/providers/{id}/rotate` (invalidates the previous URL after confirmation) |
| Delete | `DELETE /api/providers/{id}` (after confirmation) |

### Inline editing (B-R1)

Clicking **Edit** inserts a sibling `<tr>` populated with editable inputs
for name, source URL, enabled state, and schedule. Save calls
`PATCH /api/providers/{id}` with the frozen payload shape; Cancel removes
the edit row and re-shows the original.

- Buttons disable on submit to prevent double-clicks.
- Validation errors render inline without losing entered values.
- Source URLs are only displayed while editing; the rendered table shows
  `••• (hidden; only revealed while editing)` to discourage shoulder
  surfing on a shared screen.

### Permanent new-provider row

The `<tfoot>` row is always present. The user types a name and source URL,
picks a schedule type, and clicks **Save**. Each schedule type reveals its
own inline editor (day-of-month, weekday, time-of-day, interval hours)
without leaving the page.

### Validation

The client enforces the frozen `20260712_doc_shared_contracts.md` rules:
schedule type maps to the field subset shown in the spec, the field is
required when its type requires it, and validation errors from the server
(400 with `details`) are surfaced under the form without losing the
user's input.

### Live update log

`app.js` opens an `EventSource` on `/api/events` and listens for `update`
events. If the stream does not open within 10 s, or drops mid-session, the
client falls back to `GET /api/update-runs?limit=50` polling every 5 s.

The client renders each distinct `run_id:stage:status` event, so all stages
of one refresh remain visible while exact duplicates delivered by SSE and
polling are suppressed. Final clean-checkout integration depends on Worker A
committing the current full event-schema changes in `app/services/updater.py`.

Log lines are created with text nodes; provider names and messages never
reach `innerHTML`. This avoids both markup injection and visible double
escaping. The log is bounded to 500 lines; oldest lines and their composite
event IDs are dropped together.

## Executable UI tests

`npm run test:ui` runs the shipped template and `app.js` in JSDOM. It covers
the browser management lifecycle, Sunday-zero scheduling, inline validation,
confirmation behavior, hostile text, incremental events, reconnect/polling
fallback, and native focusable controls at a narrow viewport. JSDOM is a
development-only dependency and is not shipped to the production container.

## Endpoints the UI consumes

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/providers` | List all providers |
| POST | `/api/providers` | Create a new provider |
| PATCH | `/api/providers/{id}` | Update name / URL / enabled / schedule |
| DELETE | `/api/providers/{id}` | Delete a provider |
| POST | `/api/providers/{id}/refresh` | Trigger a refresh |
| POST | `/api/providers/{id}/rotate` | Rotate the public token |
| GET | `/api/update-runs?limit=N` | Polling fallback for the live log |
| GET | `/api/events` | SSE stream of `update` events |

## Endpoints the UI does **not** call

- `GET /subscriptions/<token>` is the public consumption URL — only daed
  (or its human operator) hits it.
- `GET /health` — for the container health check.

## Asset pipeline

The HTML references `app.css` and `app.js` directly. No bundler, no
transpiler, no source maps. This is intentional (per project plan A8 / B4):
the project is single-user / trusted-LAN and does not benefit from a build
runtime.

If a future contributor wants to introduce one, they should preserve the
URL surface (`/static/app.css`, `/static/app.js`) so the HTML keeps
working without modification.
