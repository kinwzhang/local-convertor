# SPDX-License-Identifier: GPL-3.0
# Ported from urlclash-converter (https://github.com/siiway/urlclash-converter),
# which is itself a derivative of clash-verge-rev's uri-parser.ts.
# See ./LICENSE_GPL3.txt for the full license text.

"""Clash YAML → share-link conversion engine.

Public API:
    convert_clash_yaml(raw: bytes) -> ConversionResult
    ConversionError
"""

from app.converter.clash import convert_clash_yaml
from app.converter.errors import ConversionError
from app.converter.result import ConversionResult

__all__ = ["convert_clash_yaml", "ConversionError", "ConversionResult"]