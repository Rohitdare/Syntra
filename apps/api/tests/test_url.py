"""Unit tests for URL article ingestion, extraction, and limits (Phase 2.3)."""

from unittest.mock import AsyncMock, patch

import pytest

from research_desk.core.errors import AppError
from research_desk.ingest.ssrf import SafeFetchResponse
from research_desk.ingest.url import extract_article_html, ingest_url


def test_extract_article_html_normal() -> None:
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Quantum Computing Breakthrough</title></head>
    <body>
        <nav><a href="/">Home</a><a href="/news">News</a></nav>
        <article>
            <h1>Quantum Computing Breakthrough</h1>
            <p>Researchers have demonstrated fault-tolerant logical qubits in silicon.</p>
            <p>The system operates at cryogenic temperatures with high fidelity gates.</p>
        </article>
        <script>console.log("track analytics");</script>
        <footer>Copyright 2026 Tech Journal</footer>
    </body>
    </html>
    """
    title, text = extract_article_html(html)
    assert "Quantum Computing Breakthrough" in title
    assert "fault-tolerant logical qubits" in text
    assert "console.log" not in text
    assert "Home" not in text
    assert "Copyright" not in text


@pytest.mark.asyncio
async def test_ingest_url_success() -> None:
    # 600 characters of clean article text
    article_body = (
        "<h1>Autonomous Agents in Complex Environments</h1>"
        + "<p>Multi-agent collaboration allows specialized subagents to divide tasks cleanly.</p>"
        + ("<p>Extensive verification ensures state consistency and security guarantees.</p>" * 10)
    )
    mock_html = f"<html><head><title>Agents Study</title></head><body>{article_body}</body></html>"

    mock_resp = SafeFetchResponse(
        final_url="https://example.com/agents-study",
        status_code=200,
        content_type="text/html; charset=utf-8",
        content=mock_html.encode("utf-8"),
    )

    with patch("research_desk.ingest.url.safe_fetch_url", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_resp
        result = await ingest_url("https://example.com/agents-study")

        assert result.url == "https://example.com/agents-study"
        assert result.title == "Agents Study"
        assert result.char_count >= 500
        assert "Multi-agent collaboration" in result.text
        assert result.page_offsets == [0]


@pytest.mark.asyncio
async def test_ingest_url_unsupported_content_type() -> None:
    mock_resp = SafeFetchResponse(
        final_url="https://example.com/file.bin",
        status_code=200,
        content_type="application/octet-stream",
        content=b"BINARY DATA",
    )

    with patch("research_desk.ingest.url.safe_fetch_url", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_resp
        with pytest.raises(AppError) as exc_info:
            await ingest_url("https://example.com/file.bin")
        assert exc_info.value.code == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.asyncio
async def test_ingest_url_thin_text_rejected() -> None:
    mock_html = "<html><head><title>Empty</title></head><body><p>Short snippet.</p></body></html>"
    mock_resp = SafeFetchResponse(
        final_url="https://example.com/short",
        status_code=200,
        content_type="text/html",
        content=mock_html.encode("utf-8"),
    )

    with patch("research_desk.ingest.url.safe_fetch_url", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_resp
        with pytest.raises(AppError) as exc_info:
            await ingest_url("https://example.com/short", min_chars=500)
        assert exc_info.value.code == "NO_TEXT"
