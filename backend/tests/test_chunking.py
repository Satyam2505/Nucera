from app.services.chunking import _overlap_tail, chunk_pages, chunk_text


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


def test_overlap_starts_on_a_whole_word():
    words = [f"word{i}" for i in range(400)]
    # Sentences of five words, so the chunker splits on sentence boundaries
    # and carries an overlap across each seam.
    text = ". ".join(" ".join(words[i : i + 5]) for i in range(0, len(words), 5)) + "."
    chunks = chunk_text(text, max_chars=200, overlap_chars=40)
    assert len(chunks) > 3

    known = set(words)
    for previous, chunk in zip(chunks, chunks[1:]):
        first_word = chunk.split()[0]
        assert first_word.rstrip(".") in known, f"chunk starts mid-word: {first_word!r}"
        assert first_word in previous.split()  # a whole word carried over from the seam
        assert len(previous) <= 200


def test_overlap_tail_cases():
    # Begins exactly on a word start: kept whole.
    assert _overlap_tail("aaa bbb ccc", 3) == "ccc"
    # Would begin mid-word ("b ccc"): the partial word is dropped.
    assert _overlap_tail("aaa bbb ccc", 5) == "ccc"
    # Short text fits entirely.
    assert _overlap_tail("aaa bbb", 40) == "aaa bbb"
    # No word break in the tail: nothing clean to carry over.
    assert _overlap_tail("x" * 100, 40) == ""
    # Overlap disabled.
    assert _overlap_tail("aaa bbb ccc", 0) == ""
    # A tail that starts on whitespace is trimmed, not cut.
    assert _overlap_tail("aaa bbb ccc", 4) == "ccc"
