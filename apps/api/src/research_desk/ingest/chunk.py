"""Document text chunker with paragraph awareness, overlap, and page tracking."""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """A single embedded text chunk with provenance metadata."""

    index: int
    text: str
    char_count: int
    start_char: int
    end_char: int
    page_start: int
    page_end: int


def _find_page(page_offsets: list[int], char_offset: int) -> int:
    """Find 1-indexed page number for a character offset."""
    if not page_offsets:
        return 1
    # bisect_right returns index of first offset > char_offset
    idx = bisect.bisect_right(page_offsets, char_offset)
    return max(1, idx)


def _split_into_units(text: str, target_chars: int) -> list[str]:
    """Break text into fine-grained units (paragraphs, sentences, or word chunks)."""
    # 1. First split by paragraph
    raw_paragraphs = re.split(r"(\n\n+)", text)
    units: list[str] = []

    for raw in raw_paragraphs:
        if not raw:
            continue
        # If raw is just the separator, append it to the previous unit or keep
        if re.fullmatch(r"\n\n+", raw):
            if units:
                units[-1] += raw
            else:
                units.append(raw)
            continue

        if len(raw) <= target_chars:
            units.append(raw)
        else:
            # Paragraph is too long: split into sentences
            sentence_splits = re.split(r"([.?!]\s+)", raw)
            current_sentence = ""
            for s_part in sentence_splits:
                if not s_part:
                    continue
                if len(current_sentence) + len(s_part) <= target_chars:
                    current_sentence += s_part
                else:
                    if current_sentence:
                        units.append(current_sentence)
                    if len(s_part) <= target_chars:
                        current_sentence = s_part
                    else:
                        # Sentence is longer than target: split by words
                        words = s_part.split(" ")
                        cur_word_chunk = ""
                        for w in words:
                            if len(cur_word_chunk) + len(w) + 1 <= target_chars:
                                cur_word_chunk = f"{cur_word_chunk} {w}".strip()
                            else:
                                if cur_word_chunk:
                                    units.append(cur_word_chunk)
                                cur_word_chunk = w
                        current_sentence = cur_word_chunk
            if current_sentence:
                units.append(current_sentence)

    return units


def chunk_text(
    text: str,
    page_offsets: list[int] | None = None,
    target_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[Chunk]:
    """Split text into paragraph-aware chunks with overlap and page range mapping.

    Args:
        text: Cleaned document text.
        page_offsets: List of start offsets for each page (0-indexed).
        target_chars: Target character count per chunk (~1200).
        overlap_chars: Number of trailing characters to include in the next chunk (~150).

    Returns:
        List of Chunk objects.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    offsets = page_offsets or [0]

    # If the total text is smaller than target + overlap, emit a single chunk
    if len(cleaned) <= target_chars:
        p_start = _find_page(offsets, 0)
        p_end = _find_page(offsets, max(0, len(cleaned) - 1))
        return [
            Chunk(
                index=0,
                text=cleaned,
                char_count=len(cleaned),
                start_char=0,
                end_char=len(cleaned),
                page_start=p_start,
                page_end=p_end,
            )
        ]

    # Find chunks iteratively
    chunks: list[Chunk] = []
    text_len = len(text)
    chunk_idx = 0
    start_pos = 0

    while start_pos < text_len:
        # Determine candidate end position
        candidate_end = min(text_len, start_pos + target_chars)

        if candidate_end >= text_len:
            end_pos = text_len
        else:
            # Look for a paragraph boundary '\n\n' near candidate_end (within 20% range)
            search_start = max(start_pos + int(target_chars * 0.7), start_pos)
            search_window = text[search_start : candidate_end + int(target_chars * 0.2)]
            para_break = search_window.rfind("\n\n")

            if para_break != -1:
                end_pos = search_start + para_break + 2
            else:
                # Look for sentence boundary
                sent_match = None
                for match in re.finditer(r"[.?!]\s+", search_window):
                    sent_match = match
                if sent_match:
                    end_pos = search_start + sent_match.end()
                else:
                    # Look for whitespace boundary
                    space_pos = search_window.rfind(" ")
                    if space_pos != -1:
                        end_pos = search_start + space_pos + 1
                    else:
                        end_pos = candidate_end

        chunk_content = text[start_pos:end_pos].strip()

        if chunk_content:
            p_start = _find_page(offsets, start_pos)
            p_end = _find_page(offsets, max(start_pos, end_pos - 1))
            chunks.append(
                Chunk(
                    index=chunk_idx,
                    text=chunk_content,
                    char_count=len(chunk_content),
                    start_char=start_pos,
                    end_char=end_pos,
                    page_start=p_start,
                    page_end=p_end,
                )
            )
            chunk_idx += 1

        if end_pos >= text_len:
            break

        # Calculate next start position with overlap
        overlap_pos = max(start_pos + 1, end_pos - overlap_chars)
        # Snap overlap to whitespace boundary to avoid mid-word slicing
        next_space = text.find(" ", overlap_pos, end_pos)
        if next_space != -1 and next_space > start_pos:
            start_pos = next_space + 1
        else:
            start_pos = overlap_pos

    return chunks
