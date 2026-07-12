# UI Documentation (Worker B deliverable B4-B6)

Date: 2026-07-12

## Layout

`app/templates/index.html` is a single-page management console. It ships
two static assets served from `/static/`:

- `app.css` — responsive layout (collapses cleanly below 720 px).
- `app.js` — vanilla-JS client. No build runtime, no dependencies.

## Behaviour

### Provider table

Renders one row per `Provider` returned by `GET /api/providers`. Each row
shows the provider name, generated URL, schedule summary, last status, and
four actions:

| Action | Effect |
|---|---|
| Refresh | `POST /api/providers/{id}/refresh` (manual trigger; UI optimistically waits for SSE event) |
| Copy URL | Copies the public subscription URL to the clipboard |
| Rotate | `POST /api/providers/{id}/rotate` (invalidates the previous URL after confirmation) |
| Delete | `DELETE /api/providers/{id}` (after confirmation) |

### Permanent new-provider row

The `<tfoot>` row is always present. The user types a name and source URL,
picks a schedule type, and clicks **Save**. Each schedule type reveals its
own inline editor (day-of-month, weekday, time-of-day, interval hours)
without leaving the page.

### Validation

The client enforces the frozen `20260712_doc_shared_contracts.md` rules:
schedule type maps to the field subset shown in the spec, the field is
required when its type requires it, and validation errors from the server
(422 with `details`) are surfaced under the form without losing the
user's input.

### Live update log

`app.js` opens an `EventSource` on `/api/events` and listens for `update`
events. If the stream does not open within 10 s, or drops mid-session, the
client falls back to `GET /api/update-runs?limit=50` polling every 5 s.

Log lines are rendered as escaped HTML — provider names and messages
never reach `innerHTML` unescaped. The log is bounded to 500 lines.

## Endpoints the UI consumes

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/providers` | List all providers |
| POST | `/api/providers` | Create a new provider |
| PATCH | `/api/providers/{id}` | Update name / URL / schedule / enabled |
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