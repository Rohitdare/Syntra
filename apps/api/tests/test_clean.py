"""Unit tests for text cleaning and normalization (Phase 2.1)."""

from research_desk.ingest.clean import (
    clean_pages,
    clean_text,
    cut_references,
    drop_repeated_headers_footers,
    join_hyphenated_line_breaks,
    normalize_whitespace,
)


def test_normalize_whitespace() -> None:
    raw = "  Hello   world!\r\n\r\nThis has\u00a0non-breaking  spaces.\n\n\n\nExtra lines.\t\t"
    cleaned = normalize_whitespace(raw)
    assert "Hello world!" in cleaned
    assert "non-breaking spaces." in cleaned
    assert "\n\nExtra lines." in cleaned
    assert "\r" not in cleaned
    assert "\u00a0" not in cleaned


def test_join_hyphenated_line_breaks() -> None:
    text = (
        "We introduce a novel algo-\nrithm for distributed trans-\n"
        "formers and model opti-\n  mization."
    )
    joined = join_hyphenated_line_breaks(text)
    assert "algorithm" in joined
    assert "transformers" in joined
    assert "optimization" in joined
    assert "algo-\nrithm" not in joined


def test_drop_repeated_headers_footers() -> None:
    pages = [
        (
            "Journal of Systems Research\nPage 1 of 3\n"
            "Title of the paper\nFirst page body text here.\nConfidential Draft\n1"
        ),
        (
            "Journal of Systems Research\nPage 2 of 3\n"
            "Section 2 Analysis\nSecond page body text.\nConfidential Draft\n2"
        ),
        (
            "Journal of Systems Research\nPage 3 of 3\n"
            "Section 3 Conclusion\nThird page body text.\nConfidential Draft\n3"
        ),
    ]
    cleaned = drop_repeated_headers_footers(pages)
    assert len(cleaned) == 3
    for page in cleaned:
        assert "Journal of Systems Research" not in page
        assert "Confidential Draft" not in page
        assert "Page 1 of 3" not in page

    assert "First page body text here." in cleaned[0]
    assert "Second page body text." in cleaned[1]
    assert "Third page body text." in cleaned[2]


def test_cut_references() -> None:
    # A paper where references appear near the end
    body = "Introduction.\n" + ("Discussion of previous results.\n" * 50)
    refs = (
        "\n\nReferences\n"
        "[1] Turing, A. M. (1950). Computing Machinery and Intelligence.\n"
        "[2] Shannon, C. (1948)."
    )
    full_text = body + refs

    cut = cut_references(full_text)
    assert "Introduction." in cut
    assert "Discussion of previous results." in cut
    assert "Turing, A. M." not in cut
    assert "References" not in cut


def test_cut_references_early_mention_not_cut() -> None:
    # An early mention of References in a table of contents must NOT cut the paper
    early_text = (
        "Table of Contents:\n1. Introduction\n2. References to related work\n3. Methodology\n"
    )
    long_body = "Extensive technical methodology details.\n" * 100
    full_text = early_text + long_body

    cut = cut_references(full_text)
    assert cut == full_text
    assert "Methodology" in cut


def test_clean_text_truncation() -> None:
    long_text = "A" * 5000
    cleaned = clean_text(long_text, max_chars=1000)
    assert len(cleaned) == 1000


def test_clean_pages_offsets() -> None:
    pages = [
        "Header\nPage 1 content here that is clean.",
        "Header\nPage 2 content that continues the study.",
    ]
    text, offsets = clean_pages(pages, max_chars=10000)
    assert len(offsets) == 2
    assert offsets[0] == 0
    assert offsets[1] > 0
    # Page 2 text should start at or around offset offsets[1]
    assert "Page 2 content" in text[offsets[1] :]
