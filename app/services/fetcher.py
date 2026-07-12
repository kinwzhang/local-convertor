import ipaddress
import logging
import socket
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

    def _resolve_and_check(self, hostname):
        if hostname in self.trusted_hosts:
            return
        if not self._is_safe_ip(hostname):
            raise FetchError(f"Destination {hostname} is not allowed (SSRF protection)")
        try:
            resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for family, _, _, _, sockaddr in resolved:
                resolved_ip = ipaddress.ip_address(sockaddr[0])
                if resolved_ip.is_loopback or resolved_ip.is_private or resolved_ip.is_link_local or resolved_ip.is_reserved:
                    raise FetchError(
                        f"Hostname {hostname} resolves to private/reserved IP {resolved_ip} (SSRF protection)"
                    )
        except socket.gaierror:
            raise FetchError(f"DNS resolution failed for {hostname}")

    def _check_host(self, hostname):
        if hostname in self.trusted_hosts:
            return
        if not self._is_safe_ip(hostname):
            raise FetchError(f"Destination {hostname} is not allowed (SSRF protection)")

    def fetch(self, url):
        self._validate_url(url)
        parsed = urlparse(url)
        self._resolve_and_check(parsed.hostname)

        collected = bytearray()
        content_type = ""

        def on_response(response):
            nonlocal content_type
            content_type = response.headers.get("content-type", "")
            redirect_host = urlparse(str(response.url)).hostname
            if redirect_host and redirect_host != parsed.hostname:
                self._resolve_and_check(redirect_host)

        def on_stream_response(response):
            nonlocal content_type
            content_type = response.headers.get("content-type", "")

        with httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            max_redirects=10,
            event_hooks={"response": [on_response]},
        ) as client:
            try:
                with client.stream("GET", url, headers={"User-Agent": "LocalClashConverter/1.0"}) as response:
                    on_stream_response(response)

                    if response.status_code >= 400:
                        raise FetchError(
                            f"HTTP {response.status_code}",
                            status_code=response.status_code,
                        )

                    for chunk in response.iter_bytes():
                        collected.extend(chunk)
                        if len(collected) > self.max_response_size:
                            raise FetchError(
                                f"Response too large: exceeds {self.max_response_size} bytes"
                            )

            except httpx.TooManyRedirects:
                raise FetchError("Too many redirects")
            except httpx.TimeoutException:
                raise FetchError("Request timed out")
            except httpx.RequestError as e:
                raise FetchError(f"Request failed: {e}")

        return FetchResult(
            content=bytes(collected),
            content_type=content_type,
            status_code=response.status_code,
        )
