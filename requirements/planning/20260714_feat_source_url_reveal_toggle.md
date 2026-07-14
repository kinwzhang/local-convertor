# 20260714 — feat: source URL reveal toggle in management UI

User report: "Don't need the hint: (hidden; only revealed while editing), but put an eye icon to reveal the link."

**Worker territory:** Worker B — frontend (`app/static/app.js`, `app/static/app.css`, `tests/browser/app.test.mjs`).

## What changed

- `app/static/app.js`
  - Added an `ICON_NS` constant and a `svgEl(tag, attrs, children)` helper that uses `document.createElementNS` (the existing `el()` uses `document.createElement`, which would emit `<svg>` as a void HTML element without inline children).
  - Added two icon factories: `eyeIcon()` and `eyeOffIcon()` — Lucide-style 16×16 SVGs with `currentColor` stroke so CSS tokens carry through.
  - Added a module-scoped `revealedProviderIds = new Set()` of provider ids whose source URL should be unhidden.
  - Added `toggleSourceUrlReveal(provider)` — flips set membership, then re-renders just the affected `<tr>` via `existing.replaceWith(displayRow(provider))`. The provider is captured through the click-handler closure so the handler does not need to look it up.
  - Updated `displayRow()` to render the source-URL cell as a `[icon-button, span.source-url-mask]` pair. Default state shows `••••••••`; the eye opens it on click; the eye-off icon then closes it.
  - Updated `loadProviders()` to prune `revealedProviderIds` against the live id list on every successful fetch, so the set stays bounded by the active provider count.
- `app/static/app.css`
  - Extended `.source-url-mask` with a `.source-url-revealed` modifier (full color, normal style, word-break for long URLs).
  - Added an `.icon-button` class — transparent background, `--muted` color in rest, `--accent` on `:hover` / `:focus-visible` / `[aria-pressed="true"]`. Uses `filter: none` to override the global `button:hover { filter: brightness(1.1) }` rule. Existing `:focus-visible` outline pattern lifted from `input:focus, select:focus`.
  - Added `.icon-button .icon { display: block; pointer-events: none; }` for the inner SVG.
- `tests/browser/app.test.mjs`
  - 5 new tests after the existing poll-survival test: default masked state, click-to-reveal, click-to-hide-again, survives the 5 s periodic refresh, pruned-on-delete.

## Why

The previous cell content was a static hint string:

```js
el("td", { class: "cell-url muted" }, [
    el("span", { class: "source-url-mask" }, ["••• (hidden; only revealed while editing)"]),
]),
```

The only way to see the actual URL was to click **Edit** — which opens the edit form for the whole provider, a heavy interaction just to glance at a URL.

The new design replaces the hint with a small eye-icon toggle inline in the row. It costs no network round-trip per click (re-renders the affected `<tr>` only) and does not interfere with the existing edit/save/cancel flow.

## Decisions made

1. **Real `<button type="button">`, not `<span role="button">`.** Native keyboard activation (Enter/Space), free `:focus-visible`, free form-submission prevention. Matches `Refresh`, `Edit`, `Copy URL`, etc. already in `app.js:201-206` and keeps the `tests/browser/app.test.mjs:264-273` invariant ("every control is a `<button>` and not `tabindex="-1"`") green by construction.

2. **`currentColor` SVG strokes over `fill: black` icons.** Lets the existing CSS tokens `--muted` (rest) and `--accent` (hover/focus/pressed) do the work — no new colors introduced.

3. **Module-scoped `Set`, not DOM `data-*` attributes.** A `data-revealed="true"` attribute on the `<tr>` would be wiped on every `tbody.replaceChildren(...)` from the 5 s poll. State in the JS closure survives.

4. **`toggleSourceUrlReveal(provider)` takes the provider object, not an id.** The click handler captures `p` in its closure (`app/static/app.js:228`); passing it in avoids an unused `lastProviders` global. The handler now does exactly one look-up: `$(`#provider-${id}`, tbody)` to find the live `<tr>`.

5. **Re-render only the affected `<tr>` on click, do not call `loadProviders()`.** A click is a UI toggle, not a data refresh — issuing a `GET /api/providers` for every reveal would be wasteful and would also reset `revealedProviderIds` semantics if it raced with the 5 s poll.

6. **No localStorage.** Reveal is a momentary UI preference; persisting it across page loads would survive deletes and re-introduce the same stale-id problem we already solved in memory. In-memory is the right scope.

7. **`<button>` accessibly named via `title`/`aria-label`**, with the inner `<svg aria-hidden="true">`. Screen readers announce "Reveal source URL, toggle button, not pressed" on first focus and "pressed" after a click, matching the WAI-ARIA toggle-button pattern.

8. **Hidden text uses `••••••••` (eight bullets, no parenthetical).** Eight dots roughly approximates the visual weight of a host name and makes the cell feel "ready to be revealed" rather than "an explanatory placeholder".

9. **Final test fix discovered during implementation:** the captured `cell.querySelector(...)` reference in tests pointed at the *old, soon-to-be-detached* `<td>` after `replaceWith` ran. All click-driven tests now re-query the DOM by `#provider-<id>` selector rather than relying on a captured reference. This is a test-only change; production behaviour is unaffected.

## Verification

- `node --check app/static/app.js` — clean.
- `node --test tests/browser/app.test.mjs` — 16/16 pass (was 11/11; 5 new tests added).
- `.venv/bin/pytest -q tests/unit/test_ui_rendering.py -k test_no_source_url_leak_in_index_html` — passes (the `app/templates/index.html` Jinja template is untouched, so `"source_url" not in body` holds).
- `.venv/bin/pytest -q` — 150/150 pass.
