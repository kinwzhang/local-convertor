# SPDX-License-Identifier: GPL-3.0
"""Clash YAML → share-link orchestration.

The frozen entry point is `convert_clash_yaml(raw: bytes) -> ConversionResult`.
It strips control characters, parses YAML, flattens the proxy arrays from
several locations (top-level `proxies`, `Proxy`, `payload`, nested
`proxy-providers`, or a top-level array), deduplicates by name+server+port,
and dispatches each surviving node to the per-protocol encoder.

Behaviour:
- Malformed YAML or non-UTF-8 input → ConversionError.
- An empty proxy list → ConversionError("no usable proxies").
- Individual unconvertible entries (unknown type, missing required fields) →
  ConversionResult.warnings entries; the run does not fail.
- Successful entries → ConversionResult.links, in input order, deduplicated.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

import yaml

from app.converter.errors import ConversionError
from app.converter.protocols import ENCODERS
from app.converter.result import ConversionResult

logger = logging.getLogger(__name__)


# Strip codepoints that are dangerous to YAML parsing, but keep all
# printable ASCII, Latin-1 supplement, and CJK / emoji ranges intact.
# This must run on the text level — running on bytes would shred UTF-8
# continuation bytes (0x80–0xBF) and corrupt every non-ASCII name.
def _strip_control_chars(text: str) -> str:
    return "".join(
        c for c in text
        if c == "\t" or c == "\n" or c == "\r" or (c >= " " and c != "\x7f")
    )


def _parse_yaml(data: bytes) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConversionError("input is not valid UTF-8", detail=str(exc)) from exc

    text = _strip_control_chars(text)
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConversionError("malformed Clash YAML", detail=str(exc)) from exc


def _iter_proxies(config: Any) -> Iterable[dict]:
    if config is None:
        return

    candidates: list[Any] = []
    if isinstance(config, dict):
        candidates.append(config.get("proxies"))
        candidates.append(config.get("Proxy"))
        candidates.append(config.get("payload"))
        providers = config.get("proxy-providers")
        if isinstance(providers, dict):
            for prov in providers.values():
                if isinstance(prov, dict):
                    candidates.append(prov.get("proxies"))
                    candidates.append(prov.get("payload"))
    elif isinstance(config, list):
        candidates.append(config)

    for entry in candidates:
        if entry is None:
            continue
        if isinstance(entry, list):
            for node in entry:
                if isinstance(node, dict):
                    yield node
        elif isinstance(entry, dict):
            yield entry


def _dedupe(proxies: Iterable[dict]) -> list[dict]:
    seen: set[tuple[str, str, int]] = set()
    result: list[dict] = []
    for node in proxies:
        name = str(node.get("name") or "")
        server = str(node.get("server") or "")
        port = int(node.get("port") or 0)
        if not name or not server or not port:
            # Defer the missing-field check to the dispatcher so it can
            # produce a per-proxy warning rather than silently dropping.
            result.append(node)
            continue
        key = (name, server, port)
        if key in seen:
            continue
        seen.add(key)
        result.append(node)
    return result


def convert_clash_yaml(raw: bytes) -> ConversionResult:
    """Convert Clash YAML bytes into share links.

    Args:
        raw: The exact bytes returned by the upstream provider.

    Returns:
        ConversionResult with ordered links, per-proxy warnings, and the count
        of successfully converted proxies.

    Raises:
        ConversionError: on malformed YAML, non-UTF-8 input, or zero usable
        proxies after deduplication.
    """
    config = _parse_yaml(raw)
    proxies = _dedupe(_iter_proxies(config))

    links: list[str] = []
    warnings: list[str] = []
    for node in proxies:
        proxy_type = node.get("type")
        name = node.get("name") or f"<unnamed {proxy_type or 'node'}>"
        if not proxy_type:
            warnings.append(f"skipped '{name}': missing 'type'")
            continue
        encoder = ENCODERS.get(proxy_type)
        if encoder is None:
            warnings.append(f"skipped '{name}': unsupported type '{proxy_type}'")
            continue
        try:
            link = encoder(node)
        except ConversionError as exc:
            warnings.append(f"skipped '{name}': {exc.message}")
            continue
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("encoder failed for %s", name)
            warnings.append(f"skipped '{name}': encoder error ({exc})")
            continue
        if not link:
            warnings.append(f"skipped '{name}': encoder returned empty link")
            continue
        links.append(link)

    if not links:
        raise ConversionError("no usable proxies")

    return ConversionResult(links=links, warnings=warnings, proxy_count=len(links))