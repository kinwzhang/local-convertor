# SPDX-License-Identifier: GPL-3.0
"""AnyTLS (`anytls://`) encoder."""
from __future__ import annotations

from app.converter.utils import (
    encode_name,
    encode_userinfo,
    is_truthy,
    strip_ipv6_brackets,
    to_query_string,
)


def encode(node: dict) -> str | None:
    server = strip_ipv6_brackets(node.get("server"))
    port = node.get("port") or 443
    password = node.get("password") or ""
    if not server:
        return None

    params: list[tuple[str, str]] = []
    sni = node.get("sni") or node.get("servername")
    if sni:
        params.append(("sni", sni))
    alpn = node.get("alpn")
    if isinstance(alpn, list) and alpn:
        params.append(("alpn", ",".join(alpn)))
    fp = node.get("client-fingerprint") or node.get("fingerprint")
    if fp:
        params.append(("client-fingerprint", fp))
    if is_truthy(node.get("skip-cert-verify")):
        params.append(("allowInsecure", "1"))
    if is_truthy(node.get("udp")):
        params.append(("udp", "1"))
    for field in ("idle-session-check-interval", "idle-session-timeout", "min-idle-session"):
        value = node.get(field)
        if value:
            params.append((field, str(value)))

    query = to_query_string(params)
    name = node.get("name") or f"anytls {server}:{port}"
    base = f"anytls://{encode_userinfo(password)}@{server}:{port}"
    if query:
        return f"{base}?{query}#{encode_name(name)}"
    return f"{base}#{encode_name(name)}"