"""Encoder-specific unit tests for gap-closed fields."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.converter.protocols.vless import encode as vless_encode


def _parse_vless_query(link: str) -> dict[str, str]:
    parsed = urlparse(link)
    return {k: v[0] for k, v in parse_qs(parsed.query).items()}


class TestVlessEncoder:
    def test_reality_mldsa65_verify(self):
        node = {
            "name": "test-mldsa65",
            "type": "vless",
            "server": "example.com",
            "port": 443,
            "uuid": "abc-123",
            "tls": True,
            "reality-opts": {
                "public-key": "pk123",
                "short-id": "sid",
                "mldsa65-verify": "mldsa_verify_key",
            },
        }
        link = vless_encode(node)
        assert link is not None
        params = _parse_vless_query(link)
        assert params["pqv"] == "mldsa_verify_key"
        assert params["pbk"] == "pk123"
        assert params["sid"] == "sid"

    def test_reality_ech(self):
        node = {
            "name": "test-ech",
            "type": "vless",
            "server": "example.com",
            "port": 443,
            "uuid": "abc-123",
            "tls": True,
            "reality-opts": {
                "public-key": "pk456",
                "short-id": "sid2",
                "ech": "ech_config_data",
            },
        }
        link = vless_encode(node)
        assert link is not None
        params = _parse_vless_query(link)
        assert params["ech"] == "ech_config_data"
        assert params["pbk"] == "pk456"

    def test_reality_all_fields(self):
        node = {
            "name": "test-all",
            "type": "vless",
            "server": "1.2.3.4",
            "port": 8443,
            "uuid": "u-u-i-d",
            "tls": True,
            "reality-opts": {
                "public-key": "pk_full",
                "short-id": "full_sid",
                "spider-x": "/path",
                "mldsa65-verify": "pq_key",
                "ech": "ech_val",
            },
        }
        link = vless_encode(node)
        params = _parse_vless_query(link)
        assert params["pbk"] == "pk_full"
        assert params["sid"] == "full_sid"
        assert params["spx"] == "/path"
        assert params["pqv"] == "pq_key"
        assert params["ech"] == "ech_val"

    def test_reality_without_exotic_fields(self):
        node = {
            "name": "test-basic",
            "type": "vless",
            "server": "example.com",
            "port": 443,
            "uuid": "abc-123",
            "tls": True,
            "reality-opts": {
                "public-key": "pk",
                "short-id": "sid",
            },
        }
        link = vless_encode(node)
        params = _parse_vless_query(link)
        assert "pqv" not in params
        assert "ech" not in params
