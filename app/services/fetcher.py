import ipaddress
import logging
from urllib.parse import urlparse
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


class FetchError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class FetchResult:
    content: bytes
    content_type: str
    status_code: int


class ProviderFetcher:
    def __init__(self, timeout=30, max_response_size=10 * 1024 * 1024, trusted_hosts=None):
        self.timeout = timeout
        self.max_response_size = max_response_size
        self.trusted_hosts = set(trusted_hosts or [])

    def _validate_url(self, url):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise FetchError(f"Unsupported scheme: {parsed.scheme}")
        if parsed.username or parsed.password:
            raise FetchError("URLs with embedded credentials are not allowed")
        if not parsed.hostname:
            raise FetchError("No hostname in URL")

    def _is_safe_ip(self, hostname):
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved:
                return False
        except ValueError:
            pass
        return True

    def _check_host(self, hostname):
        if hostname in self.trusted_hosts:
            return
        if not self._is_safe_ip(hostname):
            raise FetchError(f"Destination {hostname} is not allowed (SSRF protection)")

    def fetch(self, url):
        self._validate_url(url)
        parsed = urlparse(url)
        self._check_host(parsed.hostname)

        with httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            max_redirects=10,
        ) as client:
            try:
                response = client.get(url, headers={"User-Agent": "LocalClashConverter/1.0"})
            except httpx.TooManyRedirects:
                raise FetchError("Too many redirects")
            except httpx.TimeoutException:
                raise FetchError("Request timed out")
            except httpx.RequestError as e:
                raise FetchError(f"Request failed: {e}")

            if response.status_code >= 400:
                raise FetchError(
                    f"HTTP {response.status_code}",
                    status_code=response.status_code,
                )

            content = response.content
            if len(content) > self.max_response_size:
                raise FetchError(
                    f"Response too large: {len(content)} bytes "
                    f"(max {self.max_response_size})"
                )

            return FetchResult(
                content=content,
                content_type=response.headers.get("content-type", ""),
                status_code=response.status_code,
            )
