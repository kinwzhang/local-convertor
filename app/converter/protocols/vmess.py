# SPDX-License-Identifier: GPL-3.0
"""VMess (`vmess://`) encoder.

Format: vmess://base64(json_with_v2_fields)
"""
from __future__ import annotations

import json

from app.converter.utils import utf8_b64encode


def encode(node: dict) -> str | None:
    server = node.get("server")
    port = node.get("port")
    if not server or not port:
        return None

    network = node.get("network") or "tcp"
    ws_opts = node.get("ws-opts") or {}
    grpc_opts = node.get("grpc-opts") or {}

    if network == "ws":
        host = (ws_opts.get("headers") or {}).get("Host", "") if isinstance(ws_opts.get("headers"), dict) else ""
        path = ws_opts.get("path") or ""
    elif network == "grpc":
        host = ""
        path = grpc_opts.get("grpc-service-name") or ""
    elif network == "http":
        host = (ws_opts.get("headers") or {}).get("Host", "") if isinstance(ws_opts.get("headers"), dict) else ""
        path = ws_opts.get("path") or "/"
    else:
        host = ""
        path = ""

    alpn = node.get("alpn") or []
    alpn_str = ",".join(alpn) if isinstance(alpn, list) else ""

    vmess = {
        "v": "2",
        "ps": node.get("name") or "",
        "add": server,
        "port": port,
        "id": node.get("uuid") or "",
        "aid": int(node.get("alterId") or 0),
        "scy": node.get("cipher") or "auto",
        "net": network,
        "type": "none",
        "host": host,
        "path": path,
        "tls": "tls" if node.get("tls") else "",
        "sni": node.get("servername") or "",
        "alpn": alpn_str,
        "fp": node.get("fingerprint") or node.get("client-fingerprint") or "",
    }
    return f"vmess://{utf8_b64encode(json.dumps(vmess, separators=(',', ':')))}"