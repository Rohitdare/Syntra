"""Unit tests for pasted text ingestion and validation (Phase 2.2)."""

import pytest

from research_desk.core.errors import AppError
from research_desk.ingest.text import parse_pasted_text


def test_parse_pasted_text_valid() -> None:
    body = "Distributed consensus algorithms ensure state machine replication.\n\n" + (
        "Detailed explanation of Paxos and Raft protocols in action.\n" * 20
    )
    result = parse_pasted_text(body, title="Consensus Notes")

    assert result.title == "Consensus Notes"
    assert result.char_count == len(result.text)
    assert result.char_count >= 500
    assert result.page_offsets == [0]
    assert "Distributed consensus" in result.text


def test_parse_pasted_text_title_fallback_first_line() -> None:
    body = "Key Findings on Solar Irradiance\n\n" + ("Comprehensive measurement data.\n" * 30)
    result = parse_pasted_text(body, title=None)
    assert result.title == "Key Findings on Solar Irradiance"


def test_parse_pasted_text_empty_rejected() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_pasted_text("")
    assert exc_info.value.code == "NO_TEXT"

    with pytest.raises(AppError) as exc_info2:
        parse_pasted_text("   \n\n\t  ")
    assert exc_info2.value.code == "NO_TEXT"


def test_parse_pasted_text_too_short_rejected() -> None:
    short_text = "This text has only about thirty characters."
    with pytest.raises(AppError) as exc_info:
        parse_pasted_text(short_text, min_chars=500)
    assert exc_info.value.code == "NO_TEXT"


def test_parse_pasted_text_too_large_rejected() -> None:
    huge_text = "A" * 5001
    with pytest.raises(AppError) as exc_info:
        parse_pasted_text(huge_text, max_chars=5000)
    assert exc_info.value.code == "PAYLOAD_TOO_LARGE"
