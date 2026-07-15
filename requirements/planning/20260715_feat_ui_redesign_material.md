# Feature: Management UI Redesign — "Engineering Console" (light Material theme)

Date: 2026-07-15
Type: feat
Area: `app/templates/index.html`, `app/static/app.css`

## What changed

Redesigned the management page with a card-based layout, a light Material-inspired
theme, and a technical aesthetic. **CSS + additive HTML only** — no JavaScript
changes, so every element ID, class, and table cell position the JS depends on is
preserved.

### Aesthetic direction
- **Concept:** "engineering console" — precise, light, technical.
- **Typography:** IBM Plex Sans (UI) + IBM Plex Mono (labels, status, URLs, log)
  via Google Fonts. Deliberately avoids generic Inter/Roboto/Arial.
- **Color:** light surfaces on a faint blueprint-grid backdrop; indigo-blue
  primary (`#2b5cff`) with a cyan tech accent (`#00b3cc`); soft-tinted state
  colors for ok/fail/running.
- **Depth:** Material elevation shadows, rounded cards, an accent hairline on each
  card's top edge, a sticky translucent app bar with a brand mark and env chip.
- **Motion:** staggered card entrance, button press feedback, a pulsing live-log
  status dot. All gated behind `prefers-reduced-motion`.

### Component treatment
- Each `<section>` → an elevation **card** (`class="card"` added in HTML).
- App bar with gradient brand glyph + monospace "LAN · single-user" chip.
- Provider **table** wrapped in `.table-wrap` (horizontal scroll on small screens
  without clipping the card); Material header, row hover, sticky head.
- Last-status values render as **pill chips** (reusing existing
  `.status-ok/.status-fail/.status-running` classes — no JS change).
- Buttons: contained primary (default), outlined/text variant for row + section
  actions, tinted danger, transparent icon button — all mapped onto the existing
  class names (`button`, `.primary`, `.danger`, `.section-button`, `.icon-button`,
  `.actions button`).
- Live log kept as a deliberately **dark terminal panel** for contrast, with a
  subtle cyan glow, inset shadow, and styled scrollbar.
- Settings grid restyled as labeled Material fields with a disabled state.

## Constraints honored
- No renamed/removed IDs or classes; JS row-builder (`displayRow`/`editRow`,
  `children[3]` in the new-row footer) and log renderer untouched.
- Tests: `tests/unit/test_ui_rendering.py` + `tests/integration/test_live_log.py`
  (21) pass. HTML still contains the title, `app.css`/`app.js` refs, the URL
  placeholder, and no `source_url` string.
- HTML edits are additive only: font `<link>`s, app-bar markup, `card` classes,
  and the `.table-wrap` wrapper.

## Follow-ups / notes
- Google Fonts load from the network; on a fully air-gapped LAN the UI falls back
  to system sans/mono (functional, less distinctive). Self-hosting the two Plex
  families under `static/` would remove the external dependency if desired.
- Needs the usual rebuild/push/redeploy to reach the running container (static
  assets are baked into the image).
