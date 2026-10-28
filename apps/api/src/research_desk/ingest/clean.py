"""Text cleaning and normalization for ingested sources."""

from __future__ import annotations

import re
from collections import Counter


def normalize_whitespace(text: str) -> str:
    """Normalize line endings, remove exotic spaces, and collapse excessive blank lines."""
    if not text:
        return ""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Replace non-breaking and special unicode spaces with standard space
    text = re.sub(r"[\u00A0\u1680\u2000-\u200B\u202F\u205F\u3000]", " ", text)
    # Collapse multiple horizontal whitespace (spaces/tabs) to a single space
    text = re.sub(r"[ \t]+", " ", text)
    # Remove whitespace at the start/end of lines
    text = re.sub(r"^[ \t]+|[ \t]+$", "", text, flags=re.MULTILINE)
    # Collapse 3 or more consecutive newlines into double newlines (paragraph boundary)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def join_hyphenated_line_breaks(text: str) -> str:
    """Join words split by a hyphen at the end of a line (e.g. 'algo-\\nrithm' -> 'algorithm')."""
    if not text:
        return ""
    # Matches letters followed by hyphen and newline, then continuation letters
    # Example: 'algo-\nrithm' -> 'algorithm'
    pattern = re.compile(r"([A-Za-z]{2,})-\s*\n\s*([a-z]{2,})")
    return pattern.sub(r"\1\2", text)


def _is_page_number_or_short(line: str) -> bool:
    """Return True if line is a standalone page number or short artifact."""
    stripped = line.strip()
    if not stripped:
        return True
    # Digits only (e.g. '12')
    if re.fullmatch(r"\d+", stripped):
        return True
    # 'Page X', 'Page X of Y', '- X -'
    if re.fullmatch(r"(?i)(page\s+\d+(\s+of\s+\d+)?|-\s*\d+\s*-)", stripped):
        return True
    return False


def drop_repeated_headers_footers(pages: list[str]) -> list[str]:
    """Detect and remove identical running headers and footers that repeat across pages."""
    if len(pages) <= 1:
        return pages

    # Extract header candidates (first 2 lines) and footer candidates (last 2 lines)
    header_candidates: list[str] = []
    footer_candidates: list[str] = []

    for page in pages:
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        if len(lines) >= 2:
            header_candidates.extend(lines[:2])
            footer_candidates.extend(lines[-2:])
        elif lines:
            header_candidates.append(lines[0])
            footer_candidates.append(lines[-1])

    # Count frequencies
    header_counts = Counter(header_candidates)
    footer_counts = Counter(footer_candidates)

    threshold = max(2, len(pages) // 2)

    repeated_headers = {
        line
        for line, count in header_counts.items()
        if count >= threshold and (len(line) > 3 or _is_page_number_or_short(line))
    }
    repeated_footers = {
        line
        for line, count in footer_counts.items()
        if count >= threshold and (len(line) > 3 or _is_page_number_or_short(line))
    }

    cleaned_pages: list[str] = []
    for page in pages:
        lines = page.splitlines()
        if not lines:
            cleaned_pages.append("")
            continue

        # Check top lines
        start_idx = 0
        while start_idx < min(3, len(lines)):
            s_line = lines[start_idx].strip()
            if s_line in repeated_headers or _is_page_number_or_short(s_line):
                start_idx += 1
            else:
                break

        # Check bottom lines
        end_idx = len(lines)
        while end_idx > start_idx and end_idx > len(lines) - 3:
            s_line = lines[end_idx - 1].strip()
            if s_line in repeated_footers or _is_page_number_or_short(s_line):
                end_idx -= 1
            else:
                break

        cleaned_pages.append("\n".join(lines[start_idx:end_idx]))

    return cleaned_pages


def cut_references(text: str) -> str:
    """Cut references or bibliography section near the end of a paper or report.

    Heuristic: heading on its own line in the latter 60% of the text.
    """
    if not text or len(text) < 1000:
        return text

    # Search for headings like 'References', 'Bibliography', 'Works Cited' on a standalone line
    pattern = re.compile(
        r"^(?:#{1,4}\s*|\*{1,2})?"
        r"(?:References|Bibliography|Works Cited|Literature Cited)"
        r"(?:\*{1,2})?\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    matches = list(pattern.finditer(text))
    if not matches:
        return text

    # Only cut if the heading appears in the latter 60% of the document (index >= 0.4 * len)
    min_cut_offset = int(len(text) * 0.40)
    for m in matches:
        if m.start() >= min_cut_offset:
            # Cut at the start of the reference heading line
            return text[: m.start()].rstrip()

    return text


def clean_text(text: str, max_chars: int = 400000) -> str:
    """Clean arbitrary single-source text (for pasted text or URL article text)."""
    if not text:
        return ""
    text = join_hyphenated_line_breaks(text)
    text = normalize_whitespace(text)
    text = cut_references(text)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def clean_pages(pages: list[str], max_chars: int = 400000) -> tuple[str, list[int]]:
    """Clean multi-page document pages, returning the full joined text and page character offsets.

    page_offsets[i] gives the 0-indexed character offset in cleaned_text where page i+1 begins.
    """
    if not pages:
        return "", []

    # 1. Drop repeated headers and footers across pages
    filtered_pages = drop_repeated_headers_footers(pages)

    # 2. Clean each page individually
    cleaned_parts: list[str] = []
    page_offsets: list[int] = []
    current_offset = 0

    for idx, page in enumerate(filtered_pages):
        cleaned_page = join_hyphenated_line_breaks(page)
        cleaned_page = normalize_whitespace(cleaned_page)

        # Record where this page starts
        page_offsets.append(current_offset)

        if cleaned_page:
            cleaned_parts.append(cleaned_page)
            # Add length of page text plus separator
            separator = "\n\n" if idx < len(filtered_pages) - 1 else ""
            current_offset += len(cleaned_page) + len(separator)

    joined_text = "\n\n".join(cleaned_parts)

    # 3. Cut references section near the end
    joined_text_cut = cut_references(joined_text)
    if len(joined_text_cut) < len(joined_text):
        joined_text = joined_text_cut

    # 4. Truncate if exceeding max_chars
    if len(joined_text) > max_chars:
        joined_text = joined_text[:max_chars].rstrip()

    # 5. Adjust page offsets so none exceed text length
    valid_offsets = [min(offset, len(joined_text)) for offset in page_offsets]

    return joined_text, valid_offsets
