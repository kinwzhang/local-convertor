# SPDX-License-Identifier: GPL-3.0
from __future__ import annotations


class ConversionError(Exception):
    """Raised when a Clash YAML document cannot be converted to share links.

    Attributes:
        message: human-readable summary.
        detail: optional underlying cause (e.g. parser error message).
    """

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail