# SPDX-License-Identifier: GPL-3.0
"""Hysteria2 (`hysteria2://`) encoder."""
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
    obfs = node.get("obfs")
    if obfs:
        params.append(("obfs", obfs))
    obfs_password = node.get("obfs-password")
    if obfs_password:
        params.append(("obfs-password", obfs_password))
    if is_truthy(node.get("skip-cert-verify")):
        params.append(("insecure", "1"))
    alpn = node.get("alpn")
    if isinstance(alpn, list) and alpn:
        params.append(("alpn", ",".join(alpn)))
    fp = node.get("fingerprint")
    if fp:
        params.append(("fingerprint", fp))

    query = to_query_string(params)
    name = node.get("name") or f"Hysteria2 {server}:{port}"
    base = f"hysteria2://{encode_userinfo(password)}@{server}:{port}"
    if query:
        return f"{base}?{query}#{encode_name(name)}"
    return f"{base}#{encode_name(name)}"