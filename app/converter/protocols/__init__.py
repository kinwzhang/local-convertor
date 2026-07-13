# SPDX-License-Identifier: GPL-3.0
"""Per-protocol Clash → share-link encoders.

Each module exports `encode(node: dict) -> str | None`. Returning None or ""
signals an unconvertible proxy; the dispatcher will record a warning and
skip it.
"""

from app.converter.protocols import (
    anytls,
    http,
    hysteria,
    hysteria2,
    mieru,
    socks5,
    ss,
    ssr,
    trojan,
    tuic,
    vless,
    vmess,
    wireguard,
)

ENCODERS = {
    "ss": ss.encode,
    "ssr": ssr.encode,
    "vmess": vmess.encode,
    "vless": vless.encode,
    "trojan": trojan.encode,
    "anytls": anytls.encode,
    "hysteria": hysteria.encode,
    "hysteria2": hysteria2.encode,
    "tuic": tuic.encode,
    "wireguard": wireguard.encode,
    "http": http.encode,
    "socks5": socks5.encode,
    "mieru": mieru.encode,
}

__all__ = ["ENCODERS"]