"""Integration fixtures for Worker A's refresh pipeline.

Worker A can use these via:

    from tests.integration.test_converter_integration import (
        sample_clash_yaml,
        expected_link_count,
        sample_provider_source_url,
    )

The fixtures are designed so the refresh service can:
1. Use `sample_provider_source_url` as a stub server URL.
2. Use `sample_clash_yaml` as the response body.
3. Assert the resulting version contains `expected_link_count` share links.

This file also exercises the conversion engine on a more realistic,
multi-protocol subscription that mirrors what real providers ship.
"""
from __future__ import annotations

import pytest

from app.converter import ConversionError, convert_clash_yaml


SAMPLE_CLASH_YAML = b"""\
proxies:
  - name: "ss-a"
    type: ss
    server: 1.1.1.1
    port: 8388
    cipher: aes-256-gcm
    password: pw-a
  - name: "vmess-b"
    type: vmess
    server: 2.2.2.2
    port: 443
    uuid: 22222222-2222-2222-2222-222222222222
    cipher: auto
    alterId: 0
    network: ws
    tls: true
    servername: cdn.example.com
    ws-opts:
      path: /
      headers:
        Host: cdn.example.com
  - name: "trojan-c"
    type: trojan
    server: 3.3.3.3
    port: 443
    password: trojan-c-pw
"""


SAMPLE_PROVIDER_SOURCE_URL = "https://provider.example.com/sub?token=secret"


def sample_clash_yaml() -> bytes:
    """Return a realistic multi-protocol Clash YAML."""
    return SAMPLE_CLASH_YAML


def sample_provider_source_url() -> str:
    """Return the source URL Worker A's fetcher should mock."""
    return SAMPLE_PROVIDER_SOURCE_URL


def expected_link_count() -> int:
    """All three proxies in the sample are valid; expect three links."""
    return 3


def test_sample_yaml_converts_cleanly():
    """Sanity check: the fixture itself converts cleanly."""
    result = convert_clash_yaml(SAMPLE_CLASH_YAML)
    assert result.proxy_count == 3
    assert result.warnings == []


def test_sample_yaml_links_have_expected_schemes():
    result = convert_clash_yaml(SAMPLE_CLASH_YAML)
    schemes = sorted(link.split("://", 1)[0] for link in result.links)
    assert schemes == ["ss", "trojan", "vmess"]


@pytest.mark.parametrize("bad_input", [
    b"",
    b"proxies: []",
    b"- this is not a mapping",
])
def test_conversion_error_cases_for_refresh_pipeline(bad_input):
    """Worker A's refresh service should map these to update-run failures."""
    with pytest.raises(ConversionError):
        convert_clash_yaml(bad_input)