# Worker B Implementation Notes (2026-07-12)

## What changed

Worker B's portion of the two-worker checklist (`B1` through `B8`).

### B1 — Protocol inventory, fixtures, GPL attribution

- Bundled `external_ref/urlclash-converter/LICENSE` (GPL-3.0) at
  `app/converter/LICENSE_GPL3.txt` and added SPDX headers to every Python
  file in the converter package.
- Built sanitized fixtures under `tests/fixtures/clash/` and
  `tests/fixtures/links/`. Coverage:
  - All 12 supported protocols (SS, SSR, VMess, VLESS, Trojan, AnyTLS,
    Hysteria, Hysteria2, TUIC, WireGuard, HTTP(S), SOCKS5).
  - Unicode / emoji display names (`ss_unicode.yaml`).
  - IPv6 literals (`wireguard.yaml`).
  - Optional transport / TLS fields (ws / grpc / sni / alpn / reality /
    fingerprint).
  - Error inputs: malformed YAML, missing required fields, mixed valid+invalid.
- Inventoried the reference at `documentation/implemented/20260712_doc_protocol_inventory.md`.

### B2 — Conversion engine core

- `app/converter/__init__.py`, `errors.py`, `result.py` — frozen contract
  per `requirements/planning/20260712_doc_shared_contracts.md`.
- `app/converter/clash.py` — YAML parser, multi-shape proxy extractor
  (`proxies` / `Proxy` / `payload` / `proxy-providers` / top-level list),
  dedupe by `(name, server, port)`, dispatch.
- `app/converter/utils.py` — UTF-8-safe base64 helpers, URL-encoding,
  IPv6 bracket stripping, query-string builder, truthy coercion.

### B3 — Protocol encoders

12 modules under `app/converter/protocols/`, each exporting `encode(node)`.
Registered in `protocols/__init__.py` via the `ENCODERS` dict.

### B4-B6 — UI

- `app/templates/index.html` — single-page management console with
  permanent new-provider row, schedule editor, and live-log panel.
- `app/static/app.css` — responsive layout (collapses below 720 px).
- `app/static/app.js` — vanilla-JS client. Calls `GET /api/providers`,
  `POST/PATCH/DELETE` provider APIs, and `EventSource('/api/events')`.
  Includes SSE → polling fallback (5 s poll) and 10 s stream timeout.

### B7 — Tests

- `tests/unit/test_converter.py` — 24 tests. 18 fixture-parity cases are
  parametrized over the fixtures dir; 6 cover error paths.
- `tests/unit/test_ui_rendering.py` — 11 tests covering index rendering,
  static-asset delivery, API stub responses, SSE connected event,
  unknown-token 404, source-URL redaction.
- `tests/integration/test_converter_integration.py` — Worker-A-importable
  fixtures (`sample_clash_yaml`, `sample_provider_source_url`,
  `expected_link_count`).

### B8 — Documentation

Three docs under `documentation/implemented/`:
- `20260712_doc_protocol_inventory.md`
- `20260712_doc_converter_usage.md`
- `20260712_doc_ui_usage.md`

This file (B-work summary) and `CLAUDE.md` (project-level Claude memory).

## Issues encountered and root causes

### 1. `_strip_control_chars` corrupted UTF-8 multibyte sequences

**Symptom:** `ss_unicode.yaml` (CJK + emoji name) failed with
`malformed Clash YAML`, even though `yaml.safe_load` parses the bytes
directly.

**Root cause:** the first implementation of `_strip_control_chars` operated
on raw bytes and included `0x80–0x9F` in the control-char set. Those bytes
are legitimate UTF-8 continuation bytes, so the filter shredded every
multibyte sequence and left a stream of `0x00` bytes behind. PyYAML then
rejected the document on the first NUL.

**Fix:** operate on the decoded text and use codepoint-level filtering —
`c >= " " and c != "\x7f"`. Verified by `test_converter_strips_control_chars_but_keeps_codepoints`.

### 2. `bytes.translate` with a 256-entry table didn't actually delete

**Symptom:** even after reworking the filter, decoded text still contained
null bytes that broke YAML parsing.

**Root cause:** `bytes.translate(table)` deletes bytes only where `table[i] is None`;
mapping `table[i]` to `0x00` substitutes `0x00`, it does not delete. Used a list
comprehension on the decoded text instead.

### 3. Query-string parameter ordering didn't match expected fixtures

**Symptom:** `https.yaml`, `vless_reality.yaml`, and the WireGuard fixture
mismatched on parameter order.

**Root cause:** the fixture builder script encoded the params in one order
but the encoder built them in another (e.g. `host` before `path` vs
`path` before `host`). Real consumers don't care about order, but
byte-exact parity tests do.

**Fix:** reordered `http.py` and `vless.py` so parameters match the
reference converter's emission order. WireGuard fixture updated to match
the reference behaviour (CIDR suffix is stripped — the reference's
`replace(/\/\d+$/, "")`).

### 4. SSR fixture used a base64 padding typo from the helper script

**Symptom:** initial fixture for `ssr_basic` decoded to invalid base64.

**Root cause:** the helper script used the wrong variable when computing
the inner `remarks` base64, producing `c05NyLXBhc2Jj` (13 chars, not a
multiple of 4) instead of the actual `c3NyLXBhc2Jj`.

**Fix:** regenerated the fixture directly and verified both sides decode
to the same plaintext.

## Decisions made

- **GPL-3.0 only.** The reference is GPL-3.0; per the working protocol
  (and the project plan's last assumption), the Python port must carry
  the same licence. Added SPDX headers to every Python file in the
  converter package and bundled the licence text.
- **Strip control characters at the codepoint level.** Anything stricter
  (e.g. `xmlcharrefreplace`) would mangle valid names. We only reject
  `0x00–0x08`, `0x0B`, `0x0C`, `0x0E–0x1F`, and `0x7F`.
- **No build runtime for the UI.** Per the project plan ("no separate
  frontend build runtime"), `app.js` is hand-written vanilla JS. Future
  contributors adding a bundler must preserve the static-asset paths.
- **SSE with polling fallback at 5 s.** A 10-second stream-open timeout
  falls back to `GET /api/update-runs?limit=50`. Stream drops reconnect
  after 3 s.
- **Log line cap at 500.** Prevents runaway memory growth in long-running
  sessions.
- **Source-URL placeholder text in the HTML input is fine.** It is a UI
  hint, not a leaked secret. Test asserts that real `source_url` values
  never appear in the rendered HTML.
- **Per-proxy warnings are emitted, not raised.** Per the shared contract,
  an unconvertible proxy produces a `warnings[]` entry rather than aborting
  the run. The frozen interface lets Worker A surface those warnings in
  the live-log panel.
- **Failed runs raise ConversionError** (not return an empty result), so
  Worker A's refresh service can reliably distinguish "no proxies" from
  "conversion succeeded but produced zero links" and record an
  `UpdateRun` failure.

## Acceptance status against the two-worker checklist

| Item | Status |
|---|---|
| B1 — converter analysis and fixtures | ✅ |
| B2 — conversion engine core | ✅ |
| B3 — protocol encoders (12 protocols) | ✅ |
| B4 — UI shell and provider table | ✅ |
| B5 — schedule controls and actions | ✅ |
| B6 — live update log (client ready; awaits A-R3) | ⚠ Conditional |
| B7 — UI and integration tests | ✅ |
| B8 — converter documentation and licensing | ✅ |

## B-R1, B-R2, B-R3, B-R4 follow-ups (2026-07-12 revision)

The Worker B review (`requirements/planning/20260712_analysis_worker_b_review_findings.md`)
identified four follow-up items; all four are now resolved:

### B-R1 — Inline editing

The JS client now exposes an **Edit** action on every provider row that
opens an inline editor with name / source URL / enabled / schedule
inputs and Save / Cancel buttons. Source URLs are only visible while
editing. Edit submits a `PATCH /api/providers/{id}` with the frozen
payload shape. Buttons disable on submit; validation errors render inline.

Tests:

- `tests/integration/test_management_flow.py::test_create_provider_full_lifecycle`
- `tests/integration/test_management_flow.py::test_js_has_edit_handler`
- `tests/integration/test_management_flow.py::test_js_sends_patch_with_correct_payload_keys`

### B-R2 — Live-log client

Stable `data-id` identifiers on rendered lines; `seenRunIds` Set
deduplicates across SSE reconnects and polling fallback; polling
reverses newest-first ordering; history bounded at 500 with eviction
also pruning the dedup set.

Tests:

- `tests/integration/test_live_log.py::test_sse_publishes_frozen_event_shape`
- `tests/integration/test_live_log.py::test_js_uses_data_id_for_dedup`
- `tests/integration/test_live_log.py::test_js_polling_reverses_newest_first`
- `tests/integration/test_live_log.py::test_js_log_history_bounded`
- `tests/integration/test_live_log.py::test_js_handles_reconnect`
- `tests/integration/test_live_log.py::test_js_output_is_escaped_in_log_lines`

**Conditional:** live incremental stage messages appear only after Worker
A's A-R3 wires `publish_event()` into `app/services/updater.py`. The
client-side contract is proven end-to-end via the static-analysis and
SSE-format tests.

### B-R3 — Executable UI tests

`tests/integration/test_management_flow.py` exercises the full
provider lifecycle (create → list → patch → rotate → refresh → delete)
through the same `/api/providers` surface the JS client uses, and
verifies every JS action handler ships the right HTTP verb + payload
shape via static analysis. Without a browser-level JS runtime
available, this gives us failure detection when handlers or payload
fields are removed without updating both sides.

### B-R4 — Documentation reconciliation

`20260712_doc_ui_usage.md` and this file now describe only verified
behaviour; the conditional nature of live incremental stage messages
is recorded as a dependency on A-R3. See
`20260712_fix_ui_doc_reconciliation.md` for the rationale and
diff summary.

Integration Gate 2 (converter passes its complete fixture suite;
backend refresh service invokes the real converter and persists a
version) requires Worker A to wire the `convert_clash_yaml` call into
their refresh service. All required artefacts for that gate are in place.

## How to apply

When extending the converter:

- Add a new protocol module under `app/converter/protocols/` with
  `encode(node) -> str`.
- Register it in `app/converter/protocols/__init__.py` (`ENCODERS`).
- Drop a sanitized YAML into `tests/fixtures/clash/` and the expected
  output into `tests/fixtures/links/`. The parametrized parity test picks
  it up automatically.

When extending the UI:

- All assets must remain in `app/static/` and be referenced by absolute
  path from `index.html`. The page loads no external resources.