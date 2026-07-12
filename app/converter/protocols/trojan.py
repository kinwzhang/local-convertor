# SPDX-License-Identifier: GPL-3.0
"""Trojan (`trojan://`) encoder."""
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
    network = node.get("network")
    if network and network != "tcp":
        params.append(("type", network))

    sni = node.get("sni") or node.get("servername")
    if sni:
        params.append(("sni", sni))
    if is_truthy(node.get("skip-cert-verify")):
        params.append(("allowInsecure", "1"))
    fp = node.get("fingerprint")
    if fp:
        params.append(("fp", fp))

    alpn = node.get("alpn")
    if isinstance(alpn, list) and alpn:
        params.append(("alpn", ",".join(alpn)))

    ws_opts = node.get("ws-opts") or {}
    grpc_opts = node.get("grpc-opts") or {}
    if network == "ws" and isinstance(ws_opts, dict):
        headers = ws_opts.get("headers") or {}
        if isinstance(headers, dict) and headers.get("Host"):
            params.append(("host", headers["Host"]))
        if ws_opts.get("path"):
            params.append(("path", ws_opts["path"]))
    elif network == "grpc" and isinstance(grpc_opts, dict):
        if grpc_opts.get("grpc-service-name"):
            params.append(("path", grpc_opts["grpc-service-name"]))

    query = to_query_string(params)
    name = node.get("name") or f"Trojan {server}:{port}"
    base = f"trojan://{encode_userinfo(password)}@{server}:{port}"
    if query:
        return f"{base}?{query}#{encode_name(name)}"
    return f"{base}#{encode_name(name)}"