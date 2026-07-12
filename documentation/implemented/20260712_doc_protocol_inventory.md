# Protocol Inventory and Attribution Notes (Worker B deliverable B1)

Date: 2026-07-12

## Source

The reference converter lives at `external_ref/urlclash-converter/src/converter.ts` (TypeScript). It is a derivative of `clash-verge-rev`'s `src/utils/uri-parser.ts` (original at the URL in the source header).

## License

`external_ref/urlclash-converter/LICENSE` is **GPL-3.0**. The same license is bundled with the converter module at `app/converter/LICENSE_GPL3.txt`. Because behavior and code are ported from a GPL-3.0 work, this Python port is also GPL-3.0 — see `app/converter/__init__.py` and `LICENSE`.

## Supported Protocols

| Protocol | URI scheme | Clash type | Encoder module |
|---|---|---|---|
| Shadowsocks | `ss://` | `ss` | `protocols/ss.py` |
| ShadowsocksR | `ssr://` | `ssr` | `protocols/ssr.py` |
| VMess | `vmess://` | `vmess` | `protocols/vmess.py` |
| VLESS | `vless://` | `vless` | `protocols/vless.py` |
| Trojan | `trojan://` | `trojan` | `protocols/trojan.py` |
| AnyTLS | `anytls://` | `anytls` | `protocols/anytls.py` |
| Hysteria | `hysteria://` | `hysteria` | `protocols/hysteria.py` |
| Hysteria2 | `hysteria2://` | `hysteria2` | `protocols/hysteria2.py` |
| TUIC | `tuic://` | `tuic` | `protocols/tuic.py` |
| WireGuard | `wireguard://` | `wireguard` | `protocols/wireguard.py` |
| HTTP(S) | `http(s)://` | `http` | `protocols/http.py` |
| SOCKS5 | `socks5://` | `socks5` | `protocols/socks5.py` |

All 12 protocols listed in the project plan are covered.

## Behavioral parity notes

- **Plugin opts** (obfs / v2ray-plugin on SS): the link side only carries `cipher:password@host:port#name`; plugin metadata is preserved on the YAML side and round-trips through `linkToClash` (out of scope for this code path).
- **VMess**: the `ps` field carries the name inside the base64 JSON. A trailing `#fragment` is **not** appended because `#` is not valid base64 and breaks round-trip parsing.
- **Hysteria1 vs Hysteria2**: hysteria1 has no password in the URL (uses `?auth=`); hysteria2 has the password in the userinfo. We emit both forms.
- **WireGuard**: `address` parameter is split on `/` to remove the prefix length and then categorized as IPv4 (`ip`) or IPv6 (`ipv6`).
- **TUIC**: when `udp-relay-mode` and friends are absent, only the SNI / alpn / insecure fields are emitted.
- **VLESS**: `encryption=none` is always emitted. `flow=xtls-rprx-vision` is emitted only when present.
- **Server names**: Punycode is preserved when given as ASCII; IDNs are kept verbatim (we do **not** encode punycode here, the input is assumed to be in the form Clash stored it).

## Differences vs. the reference

- Reference uses TypeScript's `btoa` and `TextEncoder` for UTF-8-safe base64; we use Python's `base64.b64encode(bytes)` which already handles arbitrary UTF-8.
- Reference has a `linkToClash` (URI → YAML) path; this port only implements `clashToLink` (YAML → URI). Round-trip is not a goal of this app.
- Reference defaults Hysteria1 `protocol` to `udp` if absent; we do the same.
- Reference falls back to Latin-1 if UTF-8 decoding of base64 fails; we instead raise `ConversionError` on decode failure (cleaner error path).

## Unsupported (intentionally out of scope)

- `linkToClash` (URI → Clash YAML).
- Plugins other than `obfs` / `v2ray-plugin` (which are preserved as raw fields; the link side does not round-trip them).
- QuantumultX/Shadowrocket-only VMess URI parsing (we only emit V2rayN-format vmess://).