# SPDX-License-Identifier: GPL-3.0
"""Auto-detect subscription format and convert to share links.

Handles:
- Clash YAML (proxies list) → convert via convert_clash_yaml
- Base64-encoded share links (one link per line) → decode and pass through
"""
from __future__ import annotations

import base64
import binascii
import logging

from app.converter.clash import convert_clash_yaml
from app.converter.errors import ConversionError
from app.converter.result import ConversionResult

logger = logging.getLogger(__name__)

_SHARE_LINK_SCHEMES = frozenset({
    "ss://", "ssr://", "vmess://", "vless://", "trojan://", "anytls://",
    "hysteria://", "hysteria2://", "hy2://", "tuic://",
    "wireguard://", "http://", "https://", "socks5://",
})


def _try_decode_base64_links(raw: bytes) -> list[str] | None:
    """Try to decode raw bytes as base64-encoded share links.

    Returns the list of decoded link strings, or None if the content
    doesn't look like base64-encoded share links.
    """
    text = raw.decode("utf-8", errors="ignore").strip()
    if not text:
        return None

    lines = text.split("\n")
    if len(lines) < 1:
        return None

    try:
        decoded = base64.b64decode(text, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None

    decoded_lines = decoded.strip().split("\n")
    if not decoded_lines:
        return None

    match_count = 0
    for line in decoded_lines:
        lower = line.strip().lower()
        for scheme in _SHARE_LINK_SCHEMES:
            if lower.startswith(scheme):
                match_count += 1
                break

    if match_count == 0:
        return None

    if match_count < len(decoded_lines) * 0.5:
        return None

    return [line.strip() for line in decoded_lines if line.strip()]


def convert_subscription(raw: bytes) -> ConversionResult:
    """Convert subscription bytes to share links, auto-detecting format.

    Tries base64-encoded share links first, then falls back to Clash YAML.

    Raises:
        ConversionError: if the content cannot be converted by any method.
    """
    links = _try_decode_base64_links(raw)
    if links is not None:
        logger.info("Detected base64-encoded subscription (%d links)", len(links))
        return ConversionResult(links=links, warnings=[], proxy_count=len(links))

    return convert_clash_yaml(raw)
