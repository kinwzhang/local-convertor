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


def test_trusted_host_allowed():
    f = ProviderFetcher(trusted_hosts=["my-lan-host"])
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"proxies: []"
    mock_response.headers = {"content-type": "text/yaml"}
    with patch("httpx.Client.get", return_value=mock_response):
        result = f.fetch("http://my-lan-host/clash.yaml")
        assert result.content == b"proxies: []"


def test_reject_oversized_response():
    f = ProviderFetcher(max_response_size=100)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"x" * 200
    mock_response.headers = {"content-type": "text/yaml"}
    with patch("httpx.Client.get", return_value=mock_response):
        with pytest.raises(FetchError, match="too large"):
            f.fetch("http://example.com/clash.yaml")


def test_reject_http_error():
    f = ProviderFetcher()
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.content = b"Not Found"
    with patch("httpx.Client.get", return_value=mock_response):
        with pytest.raises(FetchError, match="404"):
            f.fetch("http://example.com/clash.yaml")
