# SPDX-License-Identifier: GPL-3.0
"""HTTP(S) (`http://`, `https://`) encoder."""
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
    if not server:
        return None

    username = node.get("username")
    password = node.get("password")
    userinfo = ""
    if username or password:
        userinfo = f"{encode_userinfo(username or '')}:{encode_userinfo(password or '')}@"

    params: list[tuple[str, str]] = []
    if is_truthy(node.get("tls")):
        params.append(("tls", "1"))
    if is_truthy(node.get("skip-cert-verify")):
        params.append(("skip-cert-verify", "1"))
    fp = node.get("fingerprint")
    if fp:
        params.append(("fingerprint", fp))
    ip_version = node.get("ip-version")
    if ip_version:
        params.append(("ip-version", str(ip_version)))

    query = to_query_string(params)
    name = node.get("name") or f"HTTP {server}:{port}"
    base = f"http://{userinfo}{server}:{port}"
    if query:
        return f"{base}?{query}#{encode_name(name)}"
    return f"{base}#{encode_name(name)}"