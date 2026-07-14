# 20260714 — fix: Copy URL button does nothing on plain-HTTP LAN addresses

User report: "The copy url button is not working."

**Worker territory:** frontend (app.js + browser tests) — Worker B.

## What changed

- `app/static/app.js` — `copyToClipboard(text, btn)` now
  - tries `navigator.clipboard.writeText` first when present,
  - falls back to a hidden `<textarea>` + `document.execCommand("copy")`
    when the async clipboard API is gated (non-secure / plain HTTP),
  - always reports success via `flash("URL copied", false)`, which is
    pinned to `#form-error` (outside the providers `<tbody>`) and
    therefore visible even if the periodic table poll re-renders the
    row that owned the captured `btn` reference, and
  - optionally flips the button label to "Copied!" for ~1.2 s if the
    button is still attached when the copy resolves.
- `tests/browser/app.test.mjs` — added a regression test
  `"copy URL falls back to a hidden textarea when navigator.clipboard is missing"`
  that redefines `navigator.clipboard` to `undefined` and stubs
  `document.execCommand("copy")`, then asserts the textarea fallback
  was used and `#form-error` now shows `"URL copied"`.

## Root cause

Two stacked issues, both relevant to the LAN deployment described in
`CLAUDE.md` ("Deployed on a trusted LAN, exposed as a persistent
opaque URL per provider").

**Issue 1 — `navigator.clipboard` is undefined outside secure
contexts.** Per the W3C Clipboard API spec, the `Clipboard` interface
is only exposed in secure contexts — that is, `https://`, `localhost`,
or `file://`. A consumer-grade router serving this app over
`http://192.168.x.y:5000` is *not* a secure context, so the property
is `undefined`. The pre-fix code only had one branch:

```js
if (!navigator.clipboard) {
    flash("clipboard not available");
    return;
}
```

That flashes a small red error and silently does nothing else — the
user sees a button click with no visible effect on the button itself
and no URL on the clipboard.

**Issue 2 — feedback is wired to a soon-to-be-detached button.** The
"Copied!" label is set on the captured `btn` reference:

```js
btn.textContent = "Copied!";
btn.disabled = true;
```

But `setInterval(loadProviders, POLL_INTERVAL_MS)` re-renders the
`<tbody>` every 5 s via `replaceChildren(...)`. If the click handler's
Promise resolves between two poll ticks (and especially after a long
edit), the captured `btn` may already be detached; mutations on a
detached node produce no DOM effect, so the user sees no confirmation
even when the clipboard write *did* succeed.

## Decisions made

1. **Keep both copy paths in one function.** Splitting into
   `copyToClipboardModern` / `copyToClipboardLegacy` would inflate
   the IIFE for no gain; the function is 50-ish lines, well within
   the existing style (compare `flash`, `beginEdit`, `scheduleEditor`).

2. **Prefer the async API when available.** A 1-line feature
   detection is cheaper than always running the textarea dance;
   modern browsers in secure contexts get the cleaner path.

3. **Use the `<textarea>` + `execCommand` fallback rather than
   building a richer "select then keypress" / Permissions API path.**
   `execCommand("copy")` is deprecated but still implemented in every
   browser that matters and isn't gated by secure context — exactly
   what we need for the LAN-HTTP case. Permissions Policy / Permissions
   API can't grant clipboard write on an insecure origin anyway.

4. **Pin success feedback to `#form-error`, not just the button.**
   `#form-error` lives outside the providers tbody, so it survives
   any `replaceChildren` from the periodic poll. This also lets users
   on a small / busy screen notice the confirmation without
   squinting at the button. The button-label flip is kept as a
   secondary local cue for clicks where the button is still attached.

5. **No CSS change for a green success variant.** `#form-error`
   without the `.error` class falls back to the default `<p>` styling
   (inheriting the small margin from `.error` since the class is
   toggled off). Visible enough at this scope; tweaking the palette
   is out of scope for a behavior fix.

## Verification

- `node --check app/static/app.js` — clean.
- `node --test tests/browser/app.test.mjs` — 11/11 pass (was 10/10
  before; the new test exercises the fallback path).
- `.venv/bin/pytest -q` — 150/150 pass.

## Related note

This fix does not interact with the earlier `editingProviderId`
guard added in `20260714_fix_edit_row_clobbered_by_poll.md` — that
guard was only about preserving the open edit row across the table
poll. The Copy URL click runs *outside* an edit and so still gets
full table rebuilds every 5 s; that's why the
"feedback lives outside the tbody" decision matters here.
