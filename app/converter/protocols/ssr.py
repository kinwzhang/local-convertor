# SPDX-License-Identifier: GPL-3.0
"""ShadowsocksR (`ssr://`) encoder.

Format (after outer base64):
    base64(host:port:protocol:method:obfs:base64(password)/?remarks=...&protoparam=...&obfsparam=...)
"""
from __future__ import annotations

import urllib.parse

from app.converter.utils import utf8_b64encode


def encode(node: dict) -> str | None:
    server = node.get("server")
    port = node.get("port")
    if not server or not port:
        return None
    name = node.get("name") or server
    protocol = node.get("protocol") or "origin"
    method = node.get("cipher") or "aes-256-cfb"
    obfs = node.get("obfs") or "plain"
    password = node.get("password") or ""

    core = (
        f"{server}:{port}:{protocol}:{method}:{obfs}:{utf8_b64encode(password)}"
    )
    params = {
        "remarks": utf8_b64encode(name),
    }
    protoparam = (node.get("protocol-param") or "").replace(" ", "")
    obfsparam = (node.get("obfs-param") or "").replace(" ", "")
    if protoparam:
        params["protoparam"] = utf8_b64encode(protoparam)
    if obfsparam:
        params["obfsparam"] = utf8_b64encode(obfsparam)

    query = urllib.parse.urlencode(params)
    inner = f"{core}/?{query}"
    return f"ssr://{utf8_b64encode(inner)}"