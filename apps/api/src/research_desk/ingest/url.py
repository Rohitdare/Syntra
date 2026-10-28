"""URL article ingestion, readability extraction, and cleaning."""

from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup
from readability import Document  # type: ignore[import-untyped]

from research_desk.core.errors import AppError
from research_desk.ingest.clean import clean_text
from research_desk.ingest.ssrf import ResolverType, safe_fetch_url


@dataclass(frozen=True)
class ParsedUrlResult:
    """Result of safely fetching, extracting, and cleaning article text from a URL."""

    url: str
    title: str
    text: str
    char_count: int
    page_offsets: list[int]


def extract_article_html(html: str) -> tuple[str, str]:
    """Extract article title and cleaned HTML using readability-lxml and BeautifulSoup.

    Returns:
        (title, plain_text)
    """
    try:
        doc = Document(html)
        raw_title = doc.title() or ""
        summary_html = doc.summary()
    except Exception:
        raw_title = ""
        summary_html = html

    # Parse with BeautifulSoup to strip non-content tags and get clean text
    soup = BeautifulSoup(summary_html, "html.parser")

    # Remove script, style, nav, and other boilerplate elements
    for element in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
        element.decompose()

    text = soup.get_text(separator="\n\n")

    # If readability summary was too thin, attempt extraction from the full HTML
    if len(text.strip()) < 200 and summary_html != html:
        full_soup = BeautifulSoup(html, "html.parser")
        for element in full_soup(
            ["script", "style", "noscript", "nav", "header", "footer", "aside"]
        ):
            element.decompose()
        text = full_soup.get_text(separator="\n\n")
        if not raw_title and full_soup.title:
            raw_title = full_soup.title.string or ""

    return raw_title.strip(), text.strip()


async def ingest_url(
    target_url: str,
    max_redirects: int = 3,
    max_bytes: int = 5 * 1024 * 1024,
    timeout_s: float = 10.0,
    max_chars: int = 400000,
    min_chars: int = 500,
    resolver: ResolverType | None = None,
) -> ParsedUrlResult:
    """Safely fetch a URL, extract its article content, and return clean text.

    Args:
        target_url: User-provided web address.
        max_redirects: Maximum number of followed HTTP redirects (default 3).
        max_bytes: Maximum response body size (default 5 MB).
        timeout_s: Network timeout in seconds (default 10s).
        max_chars: Maximum extracted character length (default 400,000).
        min_chars: Minimum required character length (default 500).
        resolver: Optional custom resolver for testing.

    Raises:
        AppError(FETCH_BLOCKED): If destination resolves to a prohibited network.
        AppError(UNSUPPORTED_MEDIA_TYPE): If response is not HTML or plain text.
        AppError(NO_TEXT): If extracted article text is under min_chars.
        AppError(PAYLOAD_TOO_LARGE): If response exceeds max_bytes.
    """
    response = await safe_fetch_url(
        target_url=target_url,
        max_redirects=max_redirects,
        max_bytes=max_bytes,
        timeout_s=timeout_s,
        resolver=resolver,
    )

    # Validate content type
    ctype = response.content_type.lower()
    if not ("text/html" in ctype or "application/xhtml+xml" in ctype or "text/plain" in ctype):
        raise AppError(
            "UNSUPPORTED_MEDIA_TYPE",
            f"URL returned non-HTML content type '{response.content_type}'.",
        )

    # Decode HTML text
    try:
        html_str = response.content.decode("utf-8")
    except UnicodeDecodeError:
        html_str = response.content.decode("latin-1", errors="replace")

    raw_title, raw_text = extract_article_html(html_str)

    cleaned_text = clean_text(raw_text, max_chars=max_chars)
    if len(cleaned_text) < min_chars:
        raise AppError(
            "NO_TEXT",
            (
                f"URL article contains only {len(cleaned_text)} readable characters "
                f"(minimum {min_chars} required)."
            ),
        )

    # Clean or fallback title
    title = raw_title[:100].strip() if raw_title else ""
    if not title:
        first_line = next((ln.strip() for ln in cleaned_text.splitlines() if ln.strip()), "")
        title = first_line[:80].strip() if first_line else "Web Article"

    return ParsedUrlResult(
        url=response.final_url,
        title=title,
        text=cleaned_text,
        char_count=len(cleaned_text),
        page_offsets=[0],
    )
