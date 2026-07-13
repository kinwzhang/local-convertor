"""Encoder-specific unit tests for gap-closed fields."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.converter.protocols.mieru import encode as mieru_encode
from app.converter.protocols.vless import encode as vless_encode


def _parse_vless_query(link: str) -> dict[str, str]:
    parsed = urlparse(link)
    return {k: v[0] for k, v in parse_qs(parsed.query).items()}


class TestMieruEncoder:
    def test_basic_node(self):
        node = {
            "name": "HK M1",
            "type": "mieru",
            "server": "x01.endpoint.alwaysbehappy.top",
            "port": 61021,
            "username": "3c57da75-09c8-42df-b106-6ccda51bb9c9",
            "password": "3c57da75-09c8-42df-b106-6ccda51bb9c9",
            "multiplexing": "MULTIPLEXING_OFF",
            "transport": "TCP",
        }
        link = mieru_encode(node)
        assert link is not None
        assert link.startswith("mierus://")
        parsed = urlparse(link)
        assert parsed.scheme == "mierus"
        # userinfo is "<username>:<password>"
        assert parsed.netloc.startswith(
            "3c57da75-09c8-42df-b106-6ccda51bb9c9:"
            "3c57da75-09c8-42df-b106-6ccda51bb9c9@"
        )
        assert parsed.hostname == "x01.endpoint.alwaysbehappy.top"
        # port is part of the query string in mierus://, NOT the URL authority
        assert parsed.port is None
        params = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
        assert params["port"] == "61021"
        assert params["protocol"] == "TCP"
        assert params["multiplexing"] == "MULTIPLEXING_OFF"
        assert params["profile"] == "default"
        assert parsed.fragment == "HK%20M1"

    def test_udp_transport(self):
        node = {
            "name": "udp-test",
            "type": "mieru",
            "server": "1.2.3.4",
            "port": 5555,
            "username": "u",
            "password": "p",
            "transport": "UDP",
        }
        link = mieru_encode(node)
        assert link is not None
        params = {
            k: v[0]
            for k, v in parse_qs(urlparse(link).query, keep_blank_values=True).items()
        }
        assert params["protocol"] == "UDP"

    def test_default_transport_is_tcp(self):
        node = {
            "name": "no-transport",
            "type": "mieru",
            "server": "example.com",
            "port": 9000,
            "username": "u",
            "password": "p",
        }
        link = mieru_encode(node)
        assert link is not None
        params = {
            k: v[0]
            for k, v in parse_qs(urlparse(link).query, keep_blank_values=True).items()
        }
        assert params["protocol"] == "TCP"
        # multiplexing absent when input has none
        assert "multiplexing" not in params

    def test_unknown_transport_falls_back_to_tcp(self):
        node = {
            "name": "weird",
            "type": "mieru",
            "server": "example.com",
            "port": 9000,
            "username": "u",
            "password": "p",
            "transport": "QUIC",
        }
        link = mieru_encode(node)
        assert link is not None
        params = {
            k: v[0]
            for k, v in parse_qs(urlparse(link).query, keep_blank_values=True).items()
        }
        assert params["protocol"] == "TCP"

    def test_missing_server_returns_none(self):
        assert mieru_encode(
            {"name": "x", "type": "mieru", "port": 1, "username": "u", "password": "p"}
        ) is None

    def test_missing_port_returns_none(self):
        assert mieru_encode(
            {"name": "x", "type": "mieru", "server": "h", "username": "u", "password": "p"}
        ) is None

    def test_missing_username_returns_none(self):
        assert mieru_encode(
            {"name": "x", "type": "mieru", "server": "h", "port": 1, "password": "p"}
        ) is None

    def test_missing_password_returns_none(self):
        assert mieru_encode(
            {"name": "x", "type": "mieru", "server": "h", "port": 1, "username": "u"}
        ) is None

    def test_name_with_cjk_and_emoji_is_percent_encoded(self):
        node = {
            "name": "🇭🇰 香港 M1",
            "type": "mieru",
            "server": "h.example",
            "port": 61021,
            "username": "u",
            "password": "p",
            "multiplexing": "MULTIPLEXING_OFF",
            "transport": "TCP",
        }
        link = mieru_encode(node)
        assert link is not None
        assert "🇭🇰" not in link
        assert "香港" not in link
        # Fragment carries the percent-encoded name
        assert urlparse(link).fragment  # non-empty

    def test_default_name_uses_server_port(self):
        node = {
            "type": "mieru",
            "server": "h.example",
            "port": 61021,
            "username": "u",
            "password": "p",
        }
        link = mieru_encode(node)
        assert link is not None
        assert "mieru%20h.example%3A61021" in link


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
