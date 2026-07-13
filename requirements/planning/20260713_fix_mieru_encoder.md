# 20260713 — fix: mieru protocol encoder missing from converter

## What changed

- Added `app/converter/protocols/mieru.py` — encodes Clash `type: mieru`
  nodes into `mierus://` simple share-link URIs.
- Registered `"mieru": mieru.encode` in
  `app/converter/protocols/__init__.py` `ENCODERS`.
- Added 10 unit tests in `tests/unit/test_encoders.py::TestMieruEncoder`.
- Added 1 regression integration test in
  `tests/integration/test_converter_integration.py::test_real_sample_subscription_yields_all_proxies`
  that locks in the expected 29-link count against the bundled
  `sample/sample1.md`.

## Root cause

The bundled `sample/sample1.md` contains **29 proxies**:
- 20 `type: mieru` (lines 26–45)
- 9 `type: tuic` (lines 46–54)

The dispatch table in `app/converter/protocols/__init__.py` had entries
for `ss`, `ssr`, `vmess`, `vless`, `trojan`, `anytls`, `hysteria`,
`hysteria2`, `tuic`, `wireguard`, `http`, `socks5` — but no `mieru`.

In `app/converter/clash.py` the dispatcher hits the
`"unsupported type '{proxy_type}'"` branch (`clash.py:131`) for every
mieru node and records a warning while skipping the node. With 20 mieru
nodes dropped, only the 9 tuic nodes survive — exactly the symptom the
user reported ("only gets 9").

## Share-link format chosen

The mieru project ships two URI schemes:

- `mieru://...` — base64-encoded full client config (heavy; carries every
  field of the JSON config including `socks5Port`, `httpPort`, traffic
  shaping, etc.)
- `mierus://...` — simple single-server share link. Format:
  `mierus://<user>:<pass>@<server>?<key=value>&...#<name>`

The simple `mierus://` scheme is the right fit here because:

1. Clash's `mieru` proxy type only exposes the fields a client needs to
   connect to one server (`name`, `server`, `port`, `username`,
   `password`, `multiplexing`, `transport`) — not the local-listener
   fields the full `mieru://` schema carries.
2. It mirrors how `urlclash-converter` and `clash-verge-rev` treat
   protocol-specific quirks: encode only what Clash gives us, drop the
   rest. The full base64 form is only useful for a round-trip through
   mieru's own client.
3. daed (the consumer in `CLAUDE.md`) consumes share-link text the same
   way it consumes every other protocol's URI list — scheme-prefixed
   lines — so a thin per-line URI fits the existing pipeline without
   special-casing.

### Parameters emitted

| Param        | Source          | Notes                                  |
|--------------|-----------------|----------------------------------------|
| `port`       | `port`          | One entry; simple-link repeats per port if needed (not used here) |
| `protocol`   | `transport`     | `TCP` (default) or `UDP`               |
| `multiplexing` | `multiplexing` | Omitted if Clash node lacks the field  |
| `profile`    | hardcoded       | `default` — required by the spec       |

The name is appended as a percent-encoded URI fragment (`#...`), matching
how `ss`, `vless`, `trojan`, and `tuic` encoders behave.

`mtu`, `handshake-mode`, and `traffic-pattern` are valid simple-link
parameters but Clash's `mieru` proxy type does not expose them, so they
are not emitted.

## Decisions

- **`mierus://` over `mieru://`** — see "Share-link format chosen" above.
- **No `transport=UDP` without `multiplexing`** — keep emitted query
  minimal; the encoder only adds a param when the source has the field.
- **Unknown transport falls back to TCP** rather than dropping the
  proxy — this matches how `trojan`/`vless` default unknown networks to
  `tcp` and avoids silently losing nodes on misconfigured provider YAML.
- **Required-field gating returns `None` instead of raising** — matches
  the dispatcher contract documented in `protocols/__init__.py:4-6`,
  which says "Returning None or '' signals an unconvertible proxy; the
  dispatcher will record a warning and skip it." The dispatcher turns
  that into a `ConversionResult.warnings` entry; the overall run still
  succeeds when *some* nodes convert.

## Test coverage added

Unit (`tests/unit/test_encoders.py`):

- `test_basic_node` — round-trip the canonical sample node; asserts
  scheme, userinfo, host, query keys (`port`, `protocol`,
  `multiplexing`, `profile`), and percent-encoded fragment.
- `test_udp_transport` — `transport: UDP` round-trips.
- `test_default_transport_is_tcp` — missing `transport` defaults to TCP.
- `test_unknown_transport_falls_back_to_tcp` — `transport: QUIC` →
  `protocol=TCP`.
- `test_missing_*_returns_none` — server/port/username/password gating.
- `test_name_with_cjk_and_emoji_is_percent_encoded` — UTF-8 names
  survive the percent-encoder (consistent with how other encoders in
  this package handle CJK / emoji).
- `test_default_name_uses_server_port` — empty-name fallback is
  `mieru <host>:<port>` (mirrors the `Trojan <host>:<port>` /
  `TUIC <host>:<port>` conventions used elsewhere).

Integration (`tests/integration/test_converter_integration.py`):

- `test_real_sample_subscription_yields_all_proxies` — reads the
  bundled `sample/sample1.md`, runs the full `convert_clash_yaml`
  pipeline, asserts exactly 29 links with 20 `mierus://` + 9 `tuic://`
  and no warnings. This is the regression test for the user-reported
  bug.

## Verification

```
.venv/bin/python -m pytest
============================= 150 passed in 36.72s =============================
```

Before this change: `convert_clash_yaml(sample1)` returned
`proxy_count=9` and 20 `"skipped '<name>': unsupported type 'mieru'"`
warnings.

After this change: `convert_clash_yaml(sample1)` returns
`proxy_count=29` and zero warnings.