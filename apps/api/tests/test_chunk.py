"""Unit tests for text chunker (Phase 2.1)."""

from research_desk.ingest.chunk import chunk_text


def test_chunk_empty_input() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n\t  ") == []


def test_chunk_small_text_single_chunk() -> None:
    text = "This is a single short paragraph under the target chunk size limit."
    chunks = chunk_text(text, target_chars=1200)
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].text == text
    assert chunks[0].char_count == len(text)
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 1


def test_chunk_paragraph_boundaries() -> None:
    p1 = "Paragraph 1 is fairly long. " * 20  # ~560 chars
    p2 = "Paragraph 2 provides more details. " * 25  # ~875 chars
    p3 = "Paragraph 3 concludes the topic. " * 20  # ~660 chars
    text = f"{p1}\n\n{p2}\n\n{p3}"

    chunks = chunk_text(text, target_chars=1000, overlap_chars=100)
    assert len(chunks) >= 2

    # Verify monotonic indices
    for i, c in enumerate(chunks):
        assert c.index == i
        assert c.char_count == len(c.text)
        assert c.char_count > 0

    # Verify overlap exists between consecutive chunks
    if len(chunks) > 1:
        # Some words from end of chunk 0 appear near the beginning of chunk 1
        tail_words = chunks[0].text.split()[-3:]
        assert any(w in chunks[1].text for w in tail_words)


def test_chunk_page_range_mapping() -> None:
    # Page 1 has 500 chars, Page 2 has 500 chars, Page 3 has 500 chars
    page1 = "Page 1 start. " + ("Text of page one. " * 20)
    page2 = "Page 2 start. " + ("Text of page two. " * 20)
    page3 = "Page 3 start. " + ("Text of page three. " * 20)

    offsets = [0, len(page1) + 2, len(page1) + len(page2) + 4]
    combined_text = f"{page1}\n\n{page2}\n\n{page3}"

    # Chunk with target_chars = 700 so chunks span page boundaries
    chunks = chunk_text(combined_text, page_offsets=offsets, target_chars=700, overlap_chars=100)
    assert len(chunks) >= 2

    # First chunk starts on page 1
    assert chunks[0].page_start == 1

    # Later chunks reach page 2 and page 3
    last_chunk = chunks[-1]
    assert last_chunk.page_end == 3
