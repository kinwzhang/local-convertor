# SPDX-License-Identifier: GPL-3.0
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConversionResult:
    """Outcome of `convert_clash_yaml`.

    Attributes:
        links: ordered share URIs, one per line.
        warnings: per-proxy warnings for malformed entries that were skipped.
        proxy_count: number of successfully converted proxies.
    """

    links: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    proxy_count: int = 0

    def to_text(self) -> str:
        """Render as the public subscription response body."""
        return "\n".join(self.links)