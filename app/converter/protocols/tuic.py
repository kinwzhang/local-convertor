# SPDX-License-Identifier: GPL-3.0
"""TUIC (`tuic://`) encoder."""
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
    uuid = node.get("uuid") or ""
    password = node.get("password") or ""
    if not server or not uuid:
        return None

    params: list[tuple[str, str]] = []
    sni = node.get("sni") or node.get("servername")
    if sni:
        params.append(("sni", sni))
    alpn = node.get("alpn")
    if isinstance(alpn, list) and alpn:
        params.append(("alpn", ",".join(alpn)))
    if is_truthy(node.get("skip-cert-verify")):
        params.append(("allow_insecure", "1"))
    if node.get("congestion-controller"):
        params.append(("congestion-controller", str(node["congestion-controller"])))
    udp_relay_mode = node.get("udp-relay-mode")
    if udp_relay_mode:
        params.append(("udp-relay-mode", str(udp_relay_mode)))

    query = to_query_string(params)
    name = node.get("name") or f"TUIC {server}:{port}"
    base = f"tuic://{uuid}:{encode_userinfo(password)}@{server}:{port}"
    if query:
        return f"{base}?{query}#{encode_name(name)}"
    return f"{base}#{encode_name(name)}"