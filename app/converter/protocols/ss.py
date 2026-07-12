# SPDX-License-Identifier: GPL-3.0
"""Shadowsocks (`ss://`) encoder."""
from __future__ import annotations

from app.converter.utils import encode_name, encode_userinfo, utf8_b64encode


def encode(node: dict) -> str | None:
    name = node.get("name") or f"SS {node.get('server')}:{node.get('port')}"
    cipher = node.get("cipher") or "auto"
    password = node.get("password") or ""
    server = node.get("server")
    port = node.get("port")
    if not server or not port:
        return None
    auth = utf8_b64encode(f"{cipher}:{password}")
    return f"ss://{auth}@{server}:{port}#{encode_name(name)}"