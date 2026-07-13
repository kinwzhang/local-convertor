# SPDX-License-Identifier: GPL-3.0
"""VLESS (`vless://`) encoder."""
from __future__ import annotations

from app.converter.utils import (
    encode_name,
    is_truthy,
    strip_ipv6_brackets,
    to_query_string,
)


def encode(node: dict) -> str | None:
    server = strip_ipv6_brackets(node.get("server"))
    port = node.get("port")
    uuid = node.get("uuid") or ""
    if not server or not port or not uuid:
        return None

    network = node.get("network") or "tcp"
    params: list[tuple[str, str]] = [
        ("type", network),
        ("encryption", "none"),
    ]

    if node.get("flow"):
        params.append(("flow", node["flow"]))

    reality_opts = node.get("reality-opts") or {}
    use_tls = bool(node.get("tls")) or bool(reality_opts)
    if use_tls:
        is_reality = bool(reality_opts)
        params.append(("security", "reality" if is_reality else "tls"))
        sni = node.get("servername") or node.get("sni")
        if sni:
            params.append(("sni", sni))
        fp = node.get("fingerprint") or node.get("client-fingerprint")
        if fp:
            params.append(("fp", fp))
        if is_truthy(node.get("skip-cert-verify")):
            params.append(("allowInsecure", "1"))
        alpn = node.get("alpn")
        if isinstance(alpn, list) and alpn:
            params.append(("alpn", ",".join(alpn)))
        if is_reality:
            if reality_opts.get("public-key"):
                params.append(("pbk", reality_opts["public-key"]))
            if reality_opts.get("short-id"):
                params.append(("sid", reality_opts["short-id"]))
            if reality_opts.get("spider-x"):
                params.append(("spx", reality_opts["spider-x"]))
            if reality_opts.get("mldsa65-verify"):
                params.append(("pqv", reality_opts["mldsa65-verify"]))
            if reality_opts.get("ech"):
                params.append(("ech", reality_opts["ech"]))

    if network in {"ws", "http", "grpc", "h2"}:
        opts = {}
        if network == "ws":
            opts = node.get("ws-opts") or {}
        elif network == "http":
            opts = node.get("http-opts") or {}
        elif network == "grpc":
            opts = node.get("grpc-opts") or {}
        path = opts.get("path")
        if path:
            params.append(("path", path))
        host = ""
        headers = opts.get("headers")
        if isinstance(headers, dict):
            host = headers.get("Host") or headers.get("host") or ""
        if host:
            params.append(("host", host))

    query = to_query_string(params)
    name = node.get("name") or f"VLESS {server}:{port}"
    base = f"vless://{uuid}@{server}:{port}"
    return f"{base}?{query}#{encode_name(name)}"