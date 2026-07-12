"""Fixture-driven converter parity tests.

Each test loads a sanitized YAML input from `tests/fixtures/clash/`,
runs `convert_clash_yaml`, and asserts the joined output matches
`tests/fixtures/links/<name>.txt` exactly.

Additional tests cover the error path (ConversionError) and the
mixed-validity case (warnings + partial success).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.converter import ConversionError, convert_clash_yaml

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
CLASH_DIR = FIXTURES_DIR / "clash"
LINKS_DIR = FIXTURES_DIR / "links"


def _iter_fixture_pairs():
    pairs = []
    for yaml_path in sorted(CLASH_DIR.glob("*.yaml")):
        base = yaml_path.stem
        # Skip error-case fixtures; they have no expected .txt.
        if base in {"malformed_yaml", "missing_server", "mixed"}:
            continue
        link_path = LINKS_DIR / f"{base}.txt"
        if link_path.exists():
            pairs.append((yaml_path, link_path))
    return pairs


@pytest.mark.parametrize("yaml_path,link_path", _iter_fixture_pairs(), ids=lambda p: p.stem)
def test_converter_matches_fixture(yaml_path: Path, link_path: Path):
    raw = yaml_path.read_bytes()
    expected = link_path.read_text(encoding="utf-8").strip()

    result = convert_clash_yaml(raw)

    actual = "\n".join(result.links)
    assert actual == expected
    assert result.proxy_count == len(result.links)
    assert result.warnings == []


def test_converter_rejects_malformed_yaml():
    raw = (CLASH_DIR / "malformed_yaml.yaml").read_bytes()
    with pytest.raises(ConversionError) as excinfo:
        convert_clash_yaml(raw)
    assert excinfo.value.message == "malformed Clash YAML"


def test_converter_rejects_missing_server():
    raw = (CLASH_DIR / "missing_server.yaml").read_bytes()
    with pytest.raises(ConversionError) as excinfo:
        convert_clash_yaml(raw)
    assert excinfo.value.message == "no usable proxies"


def test_converter_warns_on_mixed_inputs():
    raw = (CLASH_DIR / "mixed.yaml").read_bytes()
    result = convert_clash_yaml(raw)

    # The valid VMess node should still convert
    assert result.proxy_count == 1
    assert any(link.startswith("vmess://") for link in result.links)

    # Two invalid entries become warnings, not exceptions
    assert len(result.warnings) == 2
    messages = " ".join(result.warnings)
    assert "broken-no-server" in messages
    assert "supersecret" in messages


def test_converter_rejects_non_utf8():
    bad = b"\xff\xfe\x00\x01not-utf-8"
    with pytest.raises(ConversionError) as excinfo:
        convert_clash_yaml(bad)
    assert "UTF-8" in excinfo.value.message


def test_converter_strips_control_chars_but_keeps_codepoints():
    # NUL is a control char, but the CJK sequence after it must survive.
    raw = (
        b'proxies:\n'
        b'  - name: "\x00\xe6\xb5\x8b\xe8\xaf\x95"\n'
        b'    type: ss\n'
        b'    server: 1.2.3.4\n'
        b'    port: 8388\n'
        b'    cipher: aes-256-gcm\n'
        b'    password: secret\n'
    )
    result = convert_clash_yaml(raw)
    assert result.proxy_count == 1
    assert "%E6%B5%8B%E8%AF%95" in result.links[0]


def test_converter_result_to_text():
    from app.converter.result import ConversionResult
    text = ConversionResult(links=["a", "b"], warnings=[], proxy_count=2).to_text()
    assert text == "a\nb"