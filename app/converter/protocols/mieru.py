# SPDX-License-Identifier: GPL-3.0
"""mieru (`mierus://`) simple-share-link encoder.

The mieru project exposes a `mierus://` (note the trailing `s`) URI scheme
that carries a single-server client configuration as query parameters:

    mierus://<username>:<password>@<server>?<key=value>&...#<name>

Recognised parameters (per upstream docs):

- ``profile`` — required, single value, defaults to ``default``.
- ``port`` — required, repeatable once per server port.
- ``protocol`` — optional, repeatable. Count must match the ``port`` count;
  each entry is paired with the ``port`` at the same position (TCP / UDP).
- ``multiplexing`` — optional, single value
  (``MULTIPLEXING_OFF`` / ``MULTIPLEXING_LOW`` / ``MULTIPLEXING_MIDDLE`` /
  ``MULTIPLEXING_HIGH``).
- ``mtu``, ``handshake-mode``, ``traffic-pattern`` — optional, omitted here
  because Clash's ``mieru`` proxy type does not expose those fields.

Clash exposes the protocol as ``type: mieru`` with these fields: ``name``,
``server``, ``port``, ``username``, ``password``, ``multiplexing``, and
``transport`` (``TCP`` or ``UDP``).
"""
from __future__ import annotations

from app.converter.utils import (
    encode_name,
    encode_userinfo,
    strip_ipv6_brackets,
)


def encode(node: dict) -> str | None:
    server = strip_ipv6_brackets(node.get("server"))
    port = node.get("port")
    username = node.get("username") or ""
    password = node.get("password") or ""

    if not server or not port or not username or not password:
        return None

    transport = (node.get("transport") or "TCP").upper()
    if transport not in {"TCP", "UDP"}:
        transport = "TCP"

    # Build query string by hand — `port` and `protocol` repeat per server
    # port, and `urllib.parse.urlencode` flattens repeats into comma-joined
    # values, which is not what mierus:// expects.
    parts: list[str] = [
        f"port={port}",
        f"protocol={transport}",
    ]

    multiplexing = node.get("multiplexing")
    if multiplexing:
        parts.append(f"multiplexing={multiplexing}")

    # `profile` is mandatory in the simple-link spec; the docs example uses
    # `default`. We emit it last so the trailing fragment stays readable.
    parts.append("profile=default")

    name = node.get("name") or f"mieru {server}:{port}"
    base = (
        f"mierus://{encode_userinfo(username)}:{encode_userinfo(password)}"
        f"@{server}"
    )
    return f"{base}?{'&'.join(parts)}#{encode_name(name)}"