"""Security unit tests for SSRF protection, IP validation, and DNS pinning (Phase 2.3)."""

import ipaddress
from unittest.mock import patch

import pytest

from research_desk.core.errors import AppError
from research_desk.ingest.ssrf import (
    is_prohibited_ip,
    parse_numeric_ip,
    resolve_and_validate_host,
    safe_fetch_url,
    validate_url_syntax,
)


@pytest.mark.parametrize(
    "ip_str,expected_prohibited",
    [
        ("127.0.0.1", True),
        ("127.255.0.1", True),
        ("10.0.0.1", True),
        ("10.254.254.254", True),
        ("172.16.0.1", True),
        ("172.31.255.255", True),
        ("192.168.0.1", True),
        ("192.168.1.100", True),
        ("169.254.169.254", True),  # Cloud metadata
        ("169.254.1.1", True),  # Link-local
        ("0.0.0.0", True),
        ("224.0.0.1", True),  # Multicast
        ("255.255.255.255", True),  # Broadcast
        ("100.64.0.1", True),  # CGNAT
        ("::1", True),  # IPv6 loopback
        ("fe80::1", True),  # IPv6 link-local
        ("fc00::1", True),  # IPv6 ULA private
        ("fd00:ec2::254", True),  # AWS IPv6 IMDS
        ("ff02::1", True),  # IPv6 multicast
        ("::ffff:127.0.0.1", True),  # IPv4-mapped IPv6 loopback
        ("::ffff:10.1.2.3", True),  # IPv4-mapped IPv6 private
        ("::ffff:169.254.169.254", True),  # IPv4-mapped IPv6 metadata
        ("93.184.216.34", False),  # Public IPv4 (example.com)
        ("1.1.1.1", False),  # Public Cloudflare DNS
        ("8.8.8.8", False),  # Public Google DNS
        ("2606:4700:4700::1111", False),  # Public Cloudflare IPv6
    ],
)
def test_is_prohibited_ip(ip_str: str, expected_prohibited: bool) -> None:
    ip = ipaddress.ip_address(ip_str)
    prohibited, _ = is_prohibited_ip(ip)
    assert prohibited is expected_prohibited


def test_parse_numeric_ip() -> None:
    # Decimal 127.0.0.1 -> 2130706433
    assert parse_numeric_ip("2130706433") == ipaddress.IPv4Address("127.0.0.1")
    # Hex 127.0.0.1 -> 0x7f000001
    assert parse_numeric_ip("0x7f000001") == ipaddress.IPv4Address("127.0.0.1")
    # IPv6 bracket notation
    assert parse_numeric_ip("[::1]") == ipaddress.IPv6Address("::1")
    # Public domain name should return None
    assert parse_numeric_ip("example.com") is None


def test_validate_url_syntax_allowed() -> None:
    parsed1 = validate_url_syntax("https://example.com/article")
    assert parsed1.scheme == "https"
    assert parsed1.hostname == "example.com"

    parsed2 = validate_url_syntax("http://example.com:8080/data")
    assert parsed2.scheme == "http"
    assert parsed2.port == 8080


@pytest.mark.parametrize(
    "bad_url",
    [
        "ftp://example.com/file.txt",
        "file:///etc/passwd",
        "gopher://example.com",
        "javascript:alert(1)",
        "http://user:pass@example.com/",
        "http://example.com:5432/db",
        "http://example.com:6333/qdrant",
        "http://",
        "",
    ],
)
def test_validate_url_syntax_disallowed(bad_url: str) -> None:
    with pytest.raises(AppError) as exc_info:
        validate_url_syntax(bad_url)
    assert exc_info.value.code == "FETCH_BLOCKED"


@pytest.mark.asyncio
async def test_resolve_and_validate_host_literal_ip() -> None:
    # Prohibited literal IP
    with pytest.raises(AppError) as exc_info:
        await resolve_and_validate_host("127.0.0.1", 80)
    assert exc_info.value.code == "FETCH_BLOCKED"

    with pytest.raises(AppError) as exc_info2:
        await resolve_and_validate_host("169.254.169.254", 80)
    assert exc_info2.value.code == "FETCH_BLOCKED"

    # Public literal IP
    pinned = await resolve_and_validate_host("93.184.216.34", 80)
    assert pinned == "93.184.216.34"


@pytest.mark.asyncio
async def test_resolve_and_validate_host_mixed_dns_rejected() -> None:
    # A DNS answer containing a mix of public and private addresses must be rejected
    async def mock_resolver(host: str, port: int) -> list[str]:
        return ["93.184.216.34", "10.0.0.1"]

    with pytest.raises(AppError) as exc_info:
        await resolve_and_validate_host("dual-homed.example.com", 80, resolver=mock_resolver)
    assert exc_info.value.code == "FETCH_BLOCKED"
    assert "prohibited address" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_safe_fetch_url_redirect_to_private_blocked() -> None:
    # Simulate a public URL that redirects to 127.0.0.1
    async def mock_resolver(host: str, port: int) -> list[str]:
        if host == "initial.example.com":
            return ["93.184.216.34"]
        return ["127.0.0.1"]

    # Mock response: initial returns 302 -> http://127.0.0.1/admin
    with pytest.raises(AppError) as exc_info:
        # Patch safe_fetch_url's internal client to return redirect
        with patch("httpx.AsyncClient.send") as mock_send:
            import httpx

            mock_resp = httpx.Response(
                302,
                headers={"Location": "http://127.0.0.1/admin"},
                request=httpx.Request("GET", "http://initial.example.com"),
            )
            mock_send.return_value = mock_resp

            await safe_fetch_url(
                "http://initial.example.com",
                resolver=mock_resolver,
            )

    assert exc_info.value.code == "FETCH_BLOCKED"
