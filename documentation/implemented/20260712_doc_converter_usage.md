# Converter Documentation (Worker B deliverable B8)

Date: 2026-07-12

## Overview

`app/converter/` is a Python port of the TypeScript reference at
`external_ref/urlclash-converter/src/converter.ts`. It converts a Clash YAML
subscription into the share-link format consumed by daed (and most other
proxy clients). It supports 12 protocols and produces one share URI per line.

## License

The reference converter is GPL-3.0, and this port is therefore also GPL-3.0.
See `app/converter/LICENSE_GPL3.txt` for the full license text and
`app/converter/__init__.py` for the SPDX header applied to every module.

## Public API

```python
from app.converter import convert_clash_yaml, ConversionError, ConversionResult

result: ConversionResult = convert_clash_yaml(raw_bytes)
text: str = result.to_text()  # newline-joined links
```

`ConversionResult` has three fields:

- `links: list[str]` — ordered share URIs.
- `warnings: list[str]` — human-readable warnings for proxies that were
  skipped (unsupported type, missing required fields, encoder error).
- `proxy_count: int` — count of successfully converted proxies.

`ConversionError` (subclass of `Exception`) is raised on:

- Non-UTF-8 input.
- Malformed YAML.
- A document with zero usable proxies after deduplication.

## Supported Protocols

| Clash `type` | URI scheme | Notes |
|---|---|---|
| `ss` | `ss://` | All standard ciphers; obfs / v2ray-plugin preserved on the YAML side |
| `ssr` | `ssr://` | base64(host:port:protocol:method:obfs:base64(pass)) |
| `vmess` | `vmess://` | V2rayN JSON base64; supports ws / http / grpc networks |
| `vless` | `vless://` | tls / reality, flow=xtls-rprx-vision, ws / http / grpc / h2 |
| `trojan` | `trojan://` | ws / grpc transports |
| `anytls` | `anytls://` | sni / alpn / client-fingerprint / idle-session tuning |
| `hysteria` | `hysteria://` | udp / wechat-video / faketcp protocols |
| `hysteria2` | `hysteria2://` | obfs + obfs-password + alpn |
| `tuic` | `tuic://` | v5 / nat / congestion-controller |
| `wireguard` | `wireguard://` | ip / ipv6 split, allowed-ips, mtu |
| `http` | `http://` or `https://` | basic auth, tls flag, fingerprint, ip-version |
| `socks5` | `socks5://` | basic auth, tls, udp, ip-version |

## Behavioural guarantees

1. **Order preserved**: links appear in the same order as the input proxies.
2. **Deduplication**: proxies with identical `name|server|port` triples are
   deduplicated (the first occurrence wins).
3. **Multiple input shapes**: the parser accepts proxies from `proxies`,
   `Proxy`, `payload`, nested `proxy-providers[*].proxies`,
   `proxy-providers[*].payload`, or a top-level array — in that priority.
4. **Per-proxy warnings**: a malformed proxy never aborts the run; it shows up
   in `result.warnings` with a reason.
5. **UTF-8 names**: emoji and CJK display names round-trip through percent
   encoding in the URI fragment.
6. **No silent drops**: if the run produces zero links, `ConversionError`
   is raised so the caller can record an `UpdateRun` failure.

## Known compatibility limits

- VMess output uses the V2rayN JSON-base64 form. Quantumult / Shadowrocket-
  specific VMess URI shapes are not emitted.
- SS plugin metadata (`obfs`, `v2ray-plugin`) is preserved on the YAML side
  but is **not** carried into the share link (the spec for `ss://` is
  cipher:password@host:port#name only).
- Round-trip conversion (`link → yaml → link`) is not supported.

## Adding a new protocol encoder

1. Add `app/converter/protocols/<name>.py` with an `encode(node: dict) -> str`
   function. Return `None` or `""` for unconvertible nodes.
2. Register it in `app/converter/protocols/__init__.py` (`ENCODERS`).
3. Add sanitized fixtures:
   - `tests/fixtures/clash/<name>.yaml`
   - `tests/fixtures/links/<name>.txt`
4. The parametrized `test_converter_matches_fixture` picks them up
   automatically.
5. Add the protocol to the README table above.

## Adding a fixture

1. Pick the simplest Clash YAML that exercises the protocol's required
   fields. Place it in `tests/fixtures/clash/<name>.yaml`.
2. Run the converter locally and capture `result.to_text()`. Strip a trailing
   newline if present and save to `tests/fixtures/links/<name>.txt`.
3. Add an extra test under `tests/unit/test_converter.py` if you want to
   assert additional behaviour (e.g. optional fields).

## Calling conventions for Worker A

The refresh service should:

```python
from app.converter import convert_clash_yaml, ConversionError

try:
    result = convert_clash_yaml(raw)
    text = result.to_text()
    # … persist version, set as current …
except ConversionError as exc:
    # record an UpdateRun with status="failure" and message=exc.message
    …
```

Warnings should be appended to the `UpdateRun.message` so the UI can display
them in the live log.