# SPDX-License-Identifier: GPL-3.0
"""WireGuard (`wireguard://`) encoder."""
from __future__ import annotations

import re

from app.converter.utils import (
    encode_name,
    encode_userinfo,
    strip_ipv6_brackets,
    to_query_string,
)


def _is_ipv6(s: str) -> bool:
    return ":" in s


def encode(node: dict) -> str | None:
    server = strip_ipv6_brackets(node.get("server"))
    port = node.get("port") or 443
    private_key = node.get("private-key") or ""
    if not server:
        return None

    addresses: list[str] = []
    raw_address = node.get("address") or node.get("ip")
    if isinstance(raw_address, list):
        raw_address = ",".join(raw_address)
    if isinstance(raw_address, str) and raw_address:
        for part in raw_address.split(","):
            part = part.strip().split("/")[0]
            part = part.strip("[]")
            if part:
                addresses.append(part)
    elif node.get("ip"):
        addresses.append(node["ip"])
    if node.get("ipv6"):
        addresses.append(node["ipv6"])

    params: list[tuple[str, str]] = []
    public_key = node.get("public-key")
    if public_key:
        params.append(("public-key", public_key))
    if addresses:
        params.append(("address", ",".join(addresses)))
    allowed_ips = node.get("allowed-ips")
    if isinstance(allowed_ips, list) and allowed_ips:
        params.append(("allowed-ips", ",".join(allowed_ips)))
    elif isinstance(allowed_ips, str) and allowed_ips:
        params.append(("allowed-ips", allowed_ips))
    psk = node.get("pre-shared-key")
    if psk:
        params.append(("pre-shared-key", psk))
    reserved = node.get("reserved")
    if isinstance(reserved, list) and len(reserved) == 3:
        params.append(("reserved", ",".join(str(x) for x in reserved)))
    mtu = node.get("mtu")
    if mtu:
        params.append(("mtu", str(mtu)))
    dns = node.get("dns")
    if isinstance(dns, list) and dns:
        params.append(("dns", ",".join(dns)))

    query = to_query_string(params)
    name = node.get("name") or f"WireGuard {server}:{port}"
    base = f"wireguard://{encode_userinfo(private_key)}@{server}:{port}"
    if query:
        return f"{base}?{query}#{encode_name(name)}"
    return f"{base}#{encode_name(name)}"