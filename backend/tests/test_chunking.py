from app.services.chunking import chunk_pages, chunk_text


def test_chunk_text_respects_max_chars():
    long_text = "This is a sentence. " * 300  # ~6000 chars
    chunks = chunk_text(long_text, max_chars=500, overlap_chars=75)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 500 + 100  # small slack for the overlap join


def test_chunk_text_overlap_carries_context_across_the_seam():
    long_text = "Alpha rises. Beta follows. Gamma continues. Delta ends. " * 30
    chunks = chunk_text(long_text, max_chars=200, overlap_chars=40)
    assert len(chunks) > 1
    tail_of_first = chunks[0][-15:]
    assert any(tail_of_first in chunks[i] for i in range(1, len(chunks)))


def test_chunk_text_empty_input_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_pages_tracks_page_number_and_sequential_index():
    pages = [(1, "First page content. " * 5), (2, "Second page content. " * 5)]
    pieces = chunk_pages(pages, max_chars=100, overlap_chars=15)

    assert pieces, "expected at least one chunk"
    assert {p.page_number for p in pieces} == {1, 2}
    assert [p.chunk_index for p in pieces] == list(range(len(pieces)))

    # A chunk never straddles two pages.
    page1_chunks = [p for p in pieces if p.page_number == 1]
    page2_chunks = [p for p in pieces if p.page_number == 2]
    assert all("Second page" not in p.text for p in page1_chunks)
    assert all("First page" not in p.text for p in page2_chunks)
