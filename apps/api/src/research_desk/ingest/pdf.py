"""PDF ingestion, streaming spooler, magic-byte check, and thread-isolated text extraction."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pypdf

from research_desk.core.errors import AppError
from research_desk.ingest.clean import clean_pages

# Maximum concurrent parsing tasks to prevent thread starvation under heavy load
_PARSER_SEMAPHORE = asyncio.Semaphore(2)


@dataclass(frozen=True)
class ParsedPdfResult:
    """Result of successfully validating, extracting, and cleaning a PDF document."""

    text: str
    char_count: int
    page_count: int
    page_offsets: list[int]


def validate_pdf_magic_bytes(header: bytes) -> None:
    """Verify that bytes begin with standard %PDF signature."""
    if not header or not header.startswith(b"%PDF"):
        raise AppError(
            "UNSUPPORTED_MEDIA_TYPE",
            "File does not have a valid PDF header (%PDF).",
        )


async def spool_pdf_upload(
    stream: AsyncIterable[bytes],
    max_bytes: int = 8 * 1024 * 1024,
    temp_dir: str | Path | None = None,
) -> Path:
    """Spool incoming byte stream to a temporary file, enforcing size limits and header checks.

    Raises:
        AppError(UNSUPPORTED_MEDIA_TYPE): If the header does not match %PDF.
        AppError(PAYLOAD_TOO_LARGE): If the stream exceeds max_bytes while reading.
    """
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=temp_dir)
    temp_path = Path(temp_file.name)
    total_bytes = 0
    header_checked = False

    try:
        async for chunk in stream:
            if not chunk:
                continue

            if not header_checked:
                validate_pdf_magic_bytes(chunk)
                header_checked = True

            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                max_mb = max_bytes // (1024 * 1024)
                raise AppError(
                    "PAYLOAD_TOO_LARGE",
                    f"File exceeds maximum upload size of {max_mb} MB.",
                )

            temp_file.write(chunk)

        if not header_checked:
            raise AppError("UNSUPPORTED_MEDIA_TYPE", "Uploaded file is empty.")

        temp_file.flush()
    except BaseException:
        temp_file.close()
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise
    else:
        temp_file.close()

    return temp_path


@asynccontextmanager
async def temporary_pdf_file(
    stream: AsyncIterable[bytes],
    max_bytes: int = 8 * 1024 * 1024,
) -> AsyncIterator[Path]:
    """Context manager guaranteeing temporary PDF cleanup on completion, error, or cancellation."""
    temp_path = await spool_pdf_upload(stream, max_bytes=max_bytes)
    try:
        yield temp_path
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def extract_pdf_pages_sync(
    pdf_path: str | Path,
    max_pages: int = 100,
    timeout_s: float = 30.0,
) -> list[str]:
    """Synchronous, CPU-bound extraction of pages from a PDF file using pypdf.

    Must be run in a background thread.
    """
    deadline = time.monotonic() + timeout_s

    try:
        reader = pypdf.PdfReader(str(pdf_path))
    except Exception as exc:
        raise AppError("BAD_REQUEST", f"Malformed or unreadable PDF: {exc}") from exc

    if reader.is_encrypted:
        raise AppError(
            "BAD_REQUEST",
            "Encrypted or password-protected PDFs are not supported.",
        )

    try:
        page_count = len(reader.pages)
    except Exception as exc:
        raise AppError("BAD_REQUEST", f"Failed to read PDF page count: {exc}") from exc

    if page_count == 0:
        raise AppError("NO_TEXT", "PDF contains no pages.")

    if page_count > max_pages:
        raise AppError(
            "LIMIT_REACHED",
            f"PDF page count ({page_count}) exceeds the limit of {max_pages} pages.",
        )

    if time.monotonic() > deadline:
        raise AppError(
            "TIMEOUT",
            f"PDF parsing exceeded timeout of {timeout_s}s before page extraction.",
        )

    raw_pages: list[str] = []
    for idx, page in enumerate(reader.pages):
        if time.monotonic() > deadline:
            raise AppError(
                "TIMEOUT",
                f"PDF parsing exceeded timeout of {timeout_s}s at page {idx + 1}.",
            )
        try:
            # Layout extraction provides cleaner paragraph grouping
            text = page.extract_text() or ""
        except Exception:
            text = ""
        raw_pages.append(text)

    return raw_pages


async def parse_pdf(
    pdf_path: str | Path,
    max_pages: int = 100,
    max_chars: int = 400000,
    min_chars: int = 500,
    timeout_s: float = 30.0,
) -> ParsedPdfResult:
    """Parse, extract, clean, and validate text from a PDF file off the event loop.

    Binds concurrency via a semaphore and enforces strict timeouts.
    """
    if not os.path.exists(pdf_path):
        raise AppError("BAD_REQUEST", "PDF file does not exist.")

    async with _PARSER_SEMAPHORE:
        try:
            raw_pages = await asyncio.wait_for(
                asyncio.to_thread(extract_pdf_pages_sync, pdf_path, max_pages, timeout_s),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as exc:
            raise AppError(
                "TIMEOUT",
                f"PDF parsing exceeded timeout of {timeout_s}s.",
            ) from exc

    cleaned_text, page_offsets = clean_pages(raw_pages, max_chars=max_chars)

    if len(cleaned_text) < min_chars:
        raise AppError(
            "NO_TEXT",
            "No readable text found. If this is a scanned PDF, paste the text instead.",
        )

    return ParsedPdfResult(
        text=cleaned_text,
        char_count=len(cleaned_text),
        page_count=len(raw_pages),
        page_offsets=page_offsets,
    )
