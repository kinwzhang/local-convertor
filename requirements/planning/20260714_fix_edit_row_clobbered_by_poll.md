# 20260714 — fix: clicking Edit loses the edit row after ~5 s

User report: "once click edit button, the edit status will be exist at
around 5 - 8 seconds, which make edit not possible."

**Worker territory:** frontend (app.js + browser tests) — Worker B.

## What changed

- `app/static/app.js`
  - Added a module-scoped `editingProviderId` tracker, set in
    `beginEdit()` and cleared in `cancelEdit()`.
  - `loadProviders()` now early-returns while `editingProviderId` is
    non-null so the periodic `setInterval(loadProviders, …)` cannot
    rebuild the table mid-edit.
- `tests/browser/app.test.mjs`
  - Added a regression test
    `"periodic table refresh does not destroy an in-progress edit row"`
    that opens an edit row, types a new name, waits past
    `POLL_INTERVAL_MS = 5000`, and asserts the edit row + its typed
    value survive.

## Root cause

`app/static/app.js:513` does

```js
setInterval(loadProviders, POLL_INTERVAL_MS);
```

with `POLL_INTERVAL_MS = 5000` (line 9). `loadProviders()`
(`app/static/app.js:377`) rebuilds the table with

```js
const tbody = $("#provider-rows");
tbody.replaceChildren(...providers.map(displayRow));
```

`beginEdit()` (line 245) does **not** move the providers into a
separate "edit state" — it hides the display row (`tr.hidden = true`)
and inserts `<tr class="editing">` as the *next sibling*, inside the
same `<tbody>`. When the 5 s poll fires, `replaceChildren` wipes every
child of the tbody, including the edit row, and the user's typed
inputs vanish with it. The display row is also recreated fresh (no
`hidden` attr), so visually the entire edit UI disappears in 5–8 s —
matching the user's observation exactly.

The existing JSDOM test suite did not catch this because every test
uses `setTimeout(…, 0)` to settle, which never advances far enough for
the 5 s `setInterval` to fire. The bug only manifests in a real
browser left open long enough for the poll.

## Decisions made

1. **Skip the rebuild rather than snapshotting and restoring mid-edit
   inputs.** A snapshot/restore would also have to preserve focus
   (the edit row calls `setTimeout(() => nameInput.focus(), 0)` in
   `editRow`), the enabled-checkbox state, and the schedule editor's
   dropdown + per-type subfields. Skipping the rebuild is one variable
   toggle, has no focus side-effects, and matches the user's
   expectation ("I haven't pressed Save yet — my changes should be
   intact"). Trade-off: while editing, the table shows a slightly
   older `last_status` / `last_success_at`. That cost is bounded to
   the duration of one edit and is preferable to dropping unsaved
   input.

2. **Track a single id, not a set.** The UI only supports one open
   edit at a time (the "Edit" button is rendered per row, but two
   overlapping edits would race on the same tbody anyway). A scalar
   keeps `beginEdit` / `cancelEdit` symmetric.

3. **`loadProviders()` is the only call site that needs the guard.**
   `createProvider`, `rotateProvider`, `deleteProvider`, and the
   `submitEdit` success path all call `loadProviders()` — but
   `cancelEdit` clears `editingProviderId` first, so the post-save
   rebuild still runs. The error path of `submitEdit` deliberately
   leaves `editingProviderId` set so the edit row (with its
   validation error message) survives subsequent polls until the user
   retries or cancels.

4. **Regression test uses real time, not a mock.** Exposing
   `POLL_INTERVAL_MS` (or a hook to override it) would shave the test
   from 5.1 s to ~0.1 s, but the project rule is "no build runtime,
   no dependencies" and the file is plain IIFE-scoped vanilla JS.
   5.1 s is acceptable for a single regression test.

## Verification

- `node --check app/static/app.js` — clean.
- `node --test tests/browser/app.test.mjs` — 10/10 pass (was 9/9
  before; the new test is the regression).
- `.venv/bin/pytest -q` — 150/150 pass.