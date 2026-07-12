# SPDX-License-Identifier: GPL-3.0
"""Hysteria1 (`hysteria://`) encoder."""
from __future__ import annotations

from app.converter.utils import (
    encode_name,
    is_truthy,
    strip_ipv6_brackets,
    to_query_string,
)


def encode(node: dict) -> str | None:
    server = strip_ipv6_brackets(node.get("server"))
    port = node.get("port") or 443
    if not server:
        return None

    params: list[tuple[str, str]] = [
        ("protocol", node.get("protocol") or "udp"),
    ]
    auth = node.get("auth-str") or node.get("auth")
    if auth:
        params.append(("auth", auth))
    sni = node.get("sni") or node.get("servername")
    if sni:
        params.append(("sni", sni))
    up = node.get("up")
    if up:
        params.append(("upmbps", str(up)))
    down = node.get("down")
    if down:
        params.append(("downmbps", str(down)))
    alpn = node.get("alpn")
    if isinstance(alpn, list) and alpn:
        params.append(("alpn", ",".join(alpn)))
    obfs = node.get("obfs")
    if obfs:
        params.append(("obfs", obfs))
    ports = node.get("ports")
    if ports:
        params.append(("mport", str(ports)))
    if is_truthy(node.get("skip-cert-verify")):
        params.append(("insecure", "1"))
    fp = node.get("fingerprint")
    if fp:
        params.append(("fingerprint", fp))

    query = to_query_string(params)
    name = node.get("name") or f"Hysteria {server}:{port}"
    return f"hysteria://{server}:{port}?{query}#{encode_name(name)}"