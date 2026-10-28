"""Pasted text ingestion, validation, and cleaning."""

from __future__ import annotations

from dataclasses import dataclass

from research_desk.core.errors import AppError
from research_desk.ingest.clean import clean_text


@dataclass(frozen=True)
class ParsedTextResult:
    """Result of validating and cleaning pasted text."""

    title: str
    text: str
    char_count: int
    page_offsets: list[int]


def parse_pasted_text(
    text: str,
    title: str | None = None,
    max_chars: int = 400000,
    min_chars: int = 500,
) -> ParsedTextResult:
    """Validate, clean, and structure pasted source text.

    Args:
        text: Raw pasted input string.
        title: Optional title supplied by user.
        max_chars: Maximum allowed characters (MAX_PASTE_CHARS = 400,000).
        min_chars: Minimum required characters (MIN_SOURCE_CHARS = 500).

    Raises:
        AppError(NO_TEXT): If text is empty or has fewer than min_chars after cleaning.
        AppError(PAYLOAD_TOO_LARGE): If raw text exceeds max_chars.
    """
    if not text or not text.strip():
        raise AppError("NO_TEXT", "Pasted text is empty.")

    if len(text) > max_chars:
        raise AppError(
            "PAYLOAD_TOO_LARGE",
            f"Pasted text length ({len(text)}) exceeds maximum of {max_chars} characters.",
        )

    cleaned = clean_text(text, max_chars=max_chars)
    if len(cleaned) < min_chars:
        raise AppError(
            "NO_TEXT",
            (
                f"Text contains only {len(cleaned)} readable characters "
                f"(minimum {min_chars} required)."
            ),
        )

    # Derive title if not provided or empty
    derived_title = (title or "").strip()
    if not derived_title:
        # Use first non-empty line up to 80 chars
        first_line = next((ln.strip() for ln in cleaned.splitlines() if ln.strip()), "")
        if first_line:
            derived_title = first_line[:80].strip()
        else:
            derived_title = "Pasted Text"

    return ParsedTextResult(
        title=derived_title,
        text=cleaned,
        char_count=len(cleaned),
        page_offsets=[0],
    )
