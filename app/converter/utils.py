# SPDX-License-Identifier: GPL-3.0
from __future__ import annotations

import base64 as _b64
import binascii
import urllib.parse

from app.converter.errors import ConversionError


def utf8_b64encode(data: str | bytes) -> str:
    """UTF-8-safe base64 encode.

    Python's `base64.b64encode` accepts bytes already; we just need to make
    sure the input is encoded as UTF-8 first so CJK / emoji survive.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return _b64.b64encode(data).decode("ascii")


def utf8_b64decode(data: str) -> str:
    """Try UTF-8 base64 decode, fall back to Latin-1.

    Mirrors the reference converter behaviour: prefer UTF-8, but raw binary
    (e.g. SS passwords) survives by falling back to the original string.
    """
    stripped = data.strip()
    if not stripped:
        return ""
    try:
        raw = _b64.b64decode(stripped, validate=True)
    except (binascii.Error, ValueError):
        return data
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def encode_name(name: str | None) -> str:
    """Encode a proxy display name for use as a URI fragment."""
    if not name:
        return ""
    return urllib.parse.quote(name, safe="")


def encode_userinfo(value: str) -> str:
    """Percent-encode a userinfo component (password / uuid)."""
    return urllib.parse.quote(value, safe="")


def strip_ipv6_brackets(server: str | None) -> str:
    """Strip `[...]` from an IPv6 literal."""
    if server and server.startswith("[") and server.endswith("]"):
        return server[1:-1]
    return server or ""


def to_query_string(params: list[tuple[str, str]]) -> str:
    """URL-encode a list of (key, value) pairs.

    Skips pairs with empty values, matching URLSearchParams.toString() semantics
    from the reference converter.
    """
    encoded: list[tuple[str, str]] = []
    for key, value in params:
        if value is None or value == "":
            continue
        encoded.append((key, str(value)))
    return urllib.parse.urlencode(encoded)


def is_truthy(value: object) -> bool:
    """Loose boolean: matches JavaScript `/(TRUE)|1/i.test(value)` semantics."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value) and str(value).strip().lower() in {"true", "1", "yes"}


def require(value: object, field: str, proxy_name: str) -> None:
    """Raise ConversionError if `value` is missing or empty."""
    if value is None or value == "":
        raise ConversionError(
            f"missing required field '{field}'",
            f"proxy '{proxy_name}'",
        )