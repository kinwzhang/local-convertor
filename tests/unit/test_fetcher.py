import pytest
from unittest.mock import patch, MagicMock
from app.services.fetcher import ProviderFetcher, FetchError


def test_reject_ftp_scheme():
    f = ProviderFetcher()
    with pytest.raises(FetchError, match="Unsupported scheme"):
        f.fetch("ftp://example.com/clash.yaml")


def test_reject_embedded_credentials():
    f = ProviderFetcher()
    with pytest.raises(FetchError, match="credentials"):
        f.fetch("https://user:pass@example.com/clash.yaml")


def test_reject_loopback():
    f = ProviderFetcher()
    with pytest.raises(FetchError, match="not allowed"):
        f.fetch("http://127.0.0.1/clash.yaml")


def test_reject_private_ip():
    f = ProviderFetcher()
    with pytest.raises(FetchError, match="not allowed"):
        f.fetch("http://192.168.1.1/clash.yaml")


def test_reject_link_local():
    f = ProviderFetcher()
    with pytest.raises(FetchError, match="not allowed"):
        f.fetch("http://169.254.169.254/metadata")


def test_reject_dns_resolves_to_private(monkeypatch):
    f = ProviderFetcher()

    def fake_getaddrinfo(host, port, family, type_):
        return [(2, 1, 6, "", ("192.168.1.100", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(FetchError, match="resolves to private/reserved IP"):
        f.fetch("http://example.com/clash.yaml")


def test_reject_dns_resolution_failure(monkeypatch):
    f = ProviderFetcher()

    def fake_getaddrinfo(host, port, family, type_):
        raise socket.gaierror("Name resolution failed")

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(FetchError, match="DNS resolution failed"):
        f.fetch("http://example.com/clash.yaml")


import socket


def test_trusted_host_allowed(monkeypatch):
    f = ProviderFetcher(trusted_hosts=["my-lan-host"])

    def fake_getaddrinfo(host, port, family, type_):
        return [(2, 1, 6, "", ("192.168.1.50", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/yaml"}

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=mock_response)
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_response.iter_bytes.return_value = iter([b"proxies: []"])

    with patch("httpx.Client.stream", return_value=mock_stream_ctx):
        result = f.fetch("http://my-lan-host/clash.yaml")
        assert result.content == b"proxies: []"


def test_reject_oversized_response(monkeypatch):
    f = ProviderFetcher(max_response_size=100)

    def fake_getaddrinfo(host, port, family, type_):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/yaml"}

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=mock_response)
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_response.iter_bytes.return_value = iter([b"x" * 200])

    with patch("httpx.Client.stream", return_value=mock_stream_ctx):
        with pytest.raises(FetchError, match="too large"):
            f.fetch("http://example.com/clash.yaml")


def test_reject_http_error(monkeypatch):
    f = ProviderFetcher()

    def fake_getaddrinfo(host, port, family, type_):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.headers = {"content-type": "text/plain"}

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=mock_response)
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_response.iter_bytes.return_value = iter([b"Not Found"])

    with patch("httpx.Client.stream", return_value=mock_stream_ctx):
        with pytest.raises(FetchError, match="404"):
            f.fetch("http://example.com/clash.yaml")


def test_redirect_revalidation_calls_resolve(monkeypatch):
    f = ProviderFetcher()
    resolved_hosts = []

    original_resolve = f._resolve_and_check

    def fake_resolve(hostname):
        resolved_hosts.append(hostname)
        if hostname == "evil.example.com":
            raise FetchError(f"Hostname {hostname} resolves to private/reserved IP 10.0.0.1 (SSRF protection)")

    f._resolve_and_check = fake_resolve

    class FakeResponse:
        url = "http://evil.example.com/clash.yaml"
        headers = {"content-type": "text/yaml"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self._event_hooks = kwargs.get("event_hooks", {})

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def stream(self, method, url, headers=None):
            resp = FakeResponse()
            for hook in self._event_hooks.get("response", []):
                hook(resp)

            class StreamResponse:
                status_code = 200
                headers = {"content-type": "text/yaml"}

                def iter_bytes(self):
                    yield b"content"

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return StreamResponse()

    with patch("httpx.Client", FakeClient):
        with pytest.raises(FetchError, match="resolves to private"):
            f.fetch("http://example.com/clash.yaml")

    assert "example.com" in resolved_hosts
    assert "evil.example.com" in resolved_hosts
