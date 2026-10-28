"""SSRF protection, IP validation, DNS pinning, and safe HTTP transport."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import urllib.parse
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpcore
import httpx

from research_desk.core.errors import AppError

# Additional prohibited IP networks (metadata, carrier-grade NAT, benchmark, broadcast)
EXTRA_PROHIBITED_NETWORKS = [
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-Grade NAT (RFC 6598)
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / Cloud metadata (IPv4)
    ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol Assignments
    ipaddress.ip_network("198.18.0.0/15"),  # Network Benchmark Tests (RFC 2544)
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved / Class E
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    ipaddress.ip_network("fd00:ec2::/32"),  # AWS IPv6 IMDS metadata
]

ResolverType = Callable[[str, int], Awaitable[list[str]]]


def validate_url_syntax(url: str) -> urllib.parse.SplitResult:
    """Validate URL scheme, host, credentials, and format.

    Raises:
        AppError(FETCH_BLOCKED): On disallowed schemes, missing host, or credentials.
    """
    if not url or not isinstance(url, str):
        raise AppError("FETCH_BLOCKED", "URL is empty or invalid.")

    try:
        parsed = urllib.parse.urlsplit(url.strip())
    except Exception as exc:
        raise AppError("FETCH_BLOCKED", f"Malformed URL syntax: {exc}") from exc

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise AppError(
            "FETCH_BLOCKED",
            f"Unsupported scheme '{parsed.scheme}'; only http and https are allowed.",
        )

    if not parsed.hostname:
        raise AppError("FETCH_BLOCKED", "URL is missing a valid hostname.")

    if parsed.username or parsed.password:
        raise AppError("FETCH_BLOCKED", "URLs with embedded credentials are not allowed.")

    if parsed.port is not None and parsed.port not in (80, 443, 8080, 8443):
        raise AppError("FETCH_BLOCKED", f"Disallowed port '{parsed.port}' in URL.")

    return parsed


def parse_numeric_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse integer, hexadecimal, octal, or dotted IP strings into an IP address object."""
    # Strip brackets for IPv6 literals like '[::1]'
    clean_host = host.strip("[]")

    # Try standard representation
    try:
        return ipaddress.ip_address(clean_host)
    except ValueError:
        pass

    # Try integer/decimal notation (e.g. '2130706433')
    if clean_host.isdigit():
        try:
            val = int(clean_host)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except ValueError:
            pass

    # Try hex notation (e.g. '0x7f000001')
    if clean_host.lower().startswith("0x"):
        try:
            val = int(clean_host, 16)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except ValueError:
            pass

    return None


def is_prohibited_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> tuple[bool, str]:
    """Check if an IP address belongs to loopback, private, link-local, or reserved ranges."""
    # Check for IPv4-mapped IPv6 address (e.g. '::ffff:127.0.0.1')
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return is_prohibited_ip(ip.ipv4_mapped)

    if ip.is_loopback:
        return True, "loopback address"
    if ip.is_private:
        return True, "private address"
    if ip.is_link_local:
        return True, "link-local address"
    if ip.is_multicast:
        return True, "multicast address"
    if ip.is_reserved:
        return True, "reserved address"
    if ip.is_unspecified:
        return True, "unspecified address"

    for net in EXTRA_PROHIBITED_NETWORKS:
        if ip in net:
            return True, f"prohibited network {net}"

    return False, ""


async def default_dns_resolver(host: str, port: int) -> list[str]:
    """Default asynchronous DNS resolution using socket.getaddrinfo."""
    loop = asyncio.get_running_loop()
    try:
        addr_info = await loop.getaddrinfo(
            host, port, proto=socket.IPPROTO_TCP, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise AppError("FETCH_FAILED", f"DNS resolution failed for '{host}': {exc}") from exc

    resolved: list[str] = []
    for item in addr_info:
        sockaddr = item[4]
        resolved.append(str(sockaddr[0]))
    return resolved


async def resolve_and_validate_host(
    host: str,
    port: int,
    resolver: ResolverType | None = None,
) -> str:
    """Resolve host and ensure all returned IP addresses are public.

    Returns the first validated IP to pin the connection to.

    Raises:
        AppError(FETCH_BLOCKED): If any resolved IP is in a prohibited range.
    """
    # 1. Check if host is a literal IP (dotted, decimal, hex, or IPv6)
    literal_ip = parse_numeric_ip(host)
    if literal_ip is not None:
        prohibited, reason = is_prohibited_ip(literal_ip)
        if prohibited:
            raise AppError(
                "FETCH_BLOCKED",
                f"Destination address '{host}' ({literal_ip}) is prohibited: {reason}.",
            )
        return str(literal_ip)

    # 2. Resolve hostname via DNS
    resolve_fn = resolver or default_dns_resolver
    resolved_ips = await resolve_fn(host, port)
    if not resolved_ips:
        raise AppError("FETCH_FAILED", f"No IP addresses returned for host '{host}'.")

    # 3. Check every returned IP address. If ANY IP is prohibited, reject.
    for ip_str in resolved_ips:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise AppError("FETCH_BLOCKED", f"Invalid IP address '{ip_str}' from DNS.") from exc

        prohibited, reason = is_prohibited_ip(ip_obj)
        if prohibited:
            raise AppError(
                "FETCH_BLOCKED",
                f"Host '{host}' resolved to prohibited address '{ip_str}': {reason}.",
            )

    # Return the first validated IP for DNS pinning
    return resolved_ips[0]


class SSRFSafeNetworkBackend(httpcore.AnyIOBackend):
    """Network backend connecting directly to a pre-validated pinned IP."""

    def __init__(self, pinned_ip: str) -> None:
        super().__init__()
        self.pinned_ip = pinned_ip

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        """Connect TCP socket directly to pinned_ip, bypassing OS DNS resolution."""
        return await super().connect_tcp(
            host=self.pinned_ip,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class SSRFSafeTransport(httpx.AsyncHTTPTransport):
    """Custom HTTP transport using SSRFSafeNetworkBackend with DNS pinning."""

    def __init__(self, pinned_ip: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=self._pool._ssl_context,
            max_connections=self._pool._max_connections,
            max_keepalive_connections=self._pool._max_keepalive_connections,
            keepalive_expiry=self._pool._keepalive_expiry,
            http1=self._pool._http1,
            http2=self._pool._http2,
            network_backend=SSRFSafeNetworkBackend(pinned_ip=pinned_ip),
        )


@dataclass(frozen=True)
class SafeFetchResponse:
    """Result of safely fetching content from a URL."""

    final_url: str
    status_code: int
    content_type: str
    content: bytes


async def safe_fetch_url(
    target_url: str,
    max_redirects: int = 3,
    max_bytes: int = 5 * 1024 * 1024,
    timeout_s: float = 10.0,
    resolver: ResolverType | None = None,
) -> SafeFetchResponse:
    """Fetch URL with SSRF protection, DNS pinning, redirect re-checks, and streaming size limits.

    Raises:
        AppError(FETCH_BLOCKED): If URL or any redirect target resolves to a prohibited IP.
        AppError(PAYLOAD_TOO_LARGE): If the body exceeds max_bytes while streaming.
        AppError(TIMEOUT): On connection or read timeouts.
        AppError(FETCH_FAILED): On network or HTTP error.
    """
    current_url = target_url
    redirect_count = 0

    while True:
        parsed = validate_url_syntax(current_url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # Resolve host and obtain pinned public IP
        pinned_ip = await resolve_and_validate_host(host, port, resolver=resolver)

        transport = SSRFSafeTransport(pinned_ip=pinned_ip)

        try:
            async with httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(timeout_s),
                follow_redirects=False,
                headers={"User-Agent": "ResearchDesk/1.0 (+https://github.com/Rohitdare/Syntra)"},
            ) as client:
                req = client.build_request("GET", current_url)
                resp = await client.send(req, stream=True)

                # Check redirect
                if resp.status_code in (301, 302, 303, 307, 308):
                    await resp.aclose()
                    redirect_count += 1
                    if redirect_count > max_redirects:
                        raise AppError(
                            "FETCH_FAILED",
                            f"Too many redirects (exceeded maximum of {max_redirects}).",
                        )
                    location = resp.headers.get("location")
                    if not location:
                        raise AppError("FETCH_FAILED", "Redirect missing Location header.")

                    current_url = urllib.parse.urljoin(current_url, location)
                    continue

                if resp.status_code >= 400:
                    await resp.aclose()
                    raise AppError(
                        "FETCH_FAILED",
                        f"URL returned HTTP status {resp.status_code}.",
                    )

                # Stream response body enforcing max_bytes limit
                content_chunks: list[bytes] = []
                total_bytes = 0

                async for chunk in resp.aiter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        await resp.aclose()
                        max_mb = max_bytes // (1024 * 1024)
                        raise AppError(
                            "PAYLOAD_TOO_LARGE",
                            f"URL content exceeds maximum limit of {max_mb} MB.",
                        )
                    content_chunks.append(chunk)

                await resp.aclose()
                content = b"".join(content_chunks)
                content_type = resp.headers.get("content-type", "text/html").lower()

                return SafeFetchResponse(
                    final_url=current_url,
                    status_code=resp.status_code,
                    content_type=content_type,
                    content=content,
                )

        except httpx.TimeoutException as exc:
            raise AppError("TIMEOUT", f"Fetching URL timed out after {timeout_s}s.") from exc
        except AppError:
            raise
        except Exception as exc:
            raise AppError("FETCH_FAILED", f"Network error fetching URL: {exc}") from exc
