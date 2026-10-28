"""Unit tests for PDF ingestion, spooling, limits, and extraction (Phase 2.2)."""

import io
import tempfile
from collections.abc import AsyncIterable
from pathlib import Path

import pypdf
import pytest

from research_desk.core.errors import AppError
from research_desk.ingest.pdf import (
    parse_pdf,
    spool_pdf_upload,
    temporary_pdf_file,
    validate_pdf_magic_bytes,
)


def _create_sample_pdf(
    pages_text: list[str],
    password: str | None = None,
) -> bytes:
    """Helper to generate a blank PDF in memory using pypdf."""
    writer = pypdf.PdfWriter()
    for _ in pages_text:
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    if password:
        writer.encrypt(password)
    writer.write(buf)
    return buf.getvalue()


def _create_sample_pdf_with_text(pages_text: list[str]) -> bytes:
    """Helper to generate a PDF with real font resources and text streams."""
    writer = pypdf.PdfWriter()
    for text in pages_text:
        page = writer.add_blank_page(width=612, height=792)

        # Attach Type1 Helvetica font resource so extract_text() can parse operators
        font = pypdf.generic.DictionaryObject(
            {
                pypdf.generic.NameObject("/Type"): pypdf.generic.NameObject("/Font"),
                pypdf.generic.NameObject("/Subtype"): pypdf.generic.NameObject("/Type1"),
                pypdf.generic.NameObject("/BaseFont"): pypdf.generic.NameObject("/Helvetica"),
            }
        )
        font_ref = writer._add_object(font)
        res = pypdf.generic.DictionaryObject(
            {
                pypdf.generic.NameObject("/Font"): pypdf.generic.DictionaryObject(
                    {pypdf.generic.NameObject("/F1"): font_ref}
                )
            }
        )
        page[pypdf.generic.NameObject("/Resources")] = res

        # Text stream
        escaped = text.replace("(", "\\(").replace(")", "\\)")
        content_str = f"BT /F1 12 Tf 72 712 Td ({escaped}) Tj ET"
        stream = pypdf.generic.DecodedStreamObject()
        stream.set_data(content_str.encode("utf-8"))
        stream_ref = writer._add_object(stream)
        page[pypdf.generic.NameObject("/Contents")] = stream_ref

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def _async_byte_stream(chunks: list[bytes]) -> AsyncIterable[bytes]:
    for chunk in chunks:
        yield chunk


def test_validate_pdf_magic_bytes_valid() -> None:
    validate_pdf_magic_bytes(b"%PDF-1.7\n...")


def test_validate_pdf_magic_bytes_invalid() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_pdf_magic_bytes(b"<html><body>Not a PDF</body></html>")
    assert exc_info.value.code == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.asyncio
async def test_spool_pdf_upload_success() -> None:
    valid_pdf = _create_sample_pdf_with_text(["Sample text on page one."])
    stream = _async_byte_stream([valid_pdf[:100], valid_pdf[100:]])

    temp_path = await spool_pdf_upload(stream, max_bytes=1024 * 1024)
    try:
        assert temp_path.exists()
        assert temp_path.stat().st_size == len(valid_pdf)
    finally:
        if temp_path.exists():
            temp_path.unlink()


@pytest.mark.asyncio
async def test_spool_pdf_upload_oversized_rejected_while_reading() -> None:
    # 2 MB stream with 1 MB limit
    chunk = b"%PDF" + (b"A" * 1024 * 1024)  # 1 MB + 4 bytes
    stream = _async_byte_stream([chunk, chunk])

    with pytest.raises(AppError) as exc_info:
        await spool_pdf_upload(stream, max_bytes=1024 * 1024)  # 1 MB limit

    assert exc_info.value.code == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_temporary_pdf_file_lifecycle_cleanup() -> None:
    valid_pdf = _create_sample_pdf_with_text(["Sample lifecycle text."])
    stream = _async_byte_stream([valid_pdf])

    path_ref: Path | None = None
    async with temporary_pdf_file(stream) as pdf_path:
        path_ref = pdf_path
        assert pdf_path.exists()

    assert path_ref is not None
    assert not path_ref.exists()


@pytest.mark.asyncio
async def test_parse_pdf_valid() -> None:
    # Build text that exceeds 500 chars (MIN_SOURCE_CHARS)
    long_p1 = "First page content. " + ("Scientific observations in detail. " * 20)
    long_p2 = "Second page content. " + ("Further analytical conclusions here. " * 20)
    pdf_bytes = _create_sample_pdf_with_text([long_p1, long_p2])

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(pdf_bytes)
        f.flush()
        temp_path = Path(f.name)

    try:
        res = await parse_pdf(temp_path, max_pages=10, min_chars=100)
        assert res.page_count == 2
        assert res.char_count > 500
        assert "First page content" in res.text
        assert "Second page content" in res.text
        assert len(res.page_offsets) == 2
    finally:
        if temp_path.exists():
            temp_path.unlink()


@pytest.mark.asyncio
async def test_parse_pdf_page_limit_exceeded() -> None:
    pdf_bytes = _create_sample_pdf_with_text(["Page 1", "Page 2", "Page 3", "Page 4"])
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(pdf_bytes)
        temp_path = Path(f.name)

    try:
        with pytest.raises(AppError) as exc_info:
            await parse_pdf(temp_path, max_pages=2)
        assert exc_info.value.code == "LIMIT_REACHED"
    finally:
        if temp_path.exists():
            temp_path.unlink()


@pytest.mark.asyncio
async def test_parse_pdf_encrypted_rejected() -> None:
    pdf_bytes = _create_sample_pdf(["Secret text"], password="secretpassword")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(pdf_bytes)
        temp_path = Path(f.name)

    try:
        with pytest.raises(AppError) as exc_info:
            await parse_pdf(temp_path)
        assert exc_info.value.code == "BAD_REQUEST"
        assert "Encrypted" in str(exc_info.value.message)
    finally:
        if temp_path.exists():
            temp_path.unlink()


@pytest.mark.asyncio
async def test_parse_pdf_corrupt_file() -> None:
    # Corrupt PDF with valid magic header
    corrupt_bytes = b"%PDF-1.4\nGARBAGE NOT REAL PDF CONTENT 12345"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(corrupt_bytes)
        temp_path = Path(f.name)

    try:
        with pytest.raises(AppError) as exc_info:
            await parse_pdf(temp_path)
        assert exc_info.value.code == "BAD_REQUEST"
    finally:
        if temp_path.exists():
            temp_path.unlink()


@pytest.mark.asyncio
async def test_parse_pdf_scanned_no_text() -> None:
    # Blank pages produce no extracted text -> should raise NO_TEXT
    blank_pdf = _create_sample_pdf([""])
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(blank_pdf)
        temp_path = Path(f.name)

    try:
        with pytest.raises(AppError) as exc_info:
            await parse_pdf(temp_path, min_chars=500)
        assert exc_info.value.code == "NO_TEXT"
    finally:
        if temp_path.exists():
            temp_path.unlink()


@pytest.mark.asyncio
async def test_parse_pdf_timeout_handling() -> None:
    pdf_bytes = _create_sample_pdf_with_text(["Page content"])
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(pdf_bytes)
        temp_path = Path(f.name)

    try:
        with pytest.raises(AppError) as exc_info:
            # -1.0s timeout ensures deadline is in the past before extraction
            await parse_pdf(temp_path, timeout_s=-1.0)
        assert exc_info.value.code == "TIMEOUT"
    finally:
        if temp_path.exists():
            temp_path.unlink()
