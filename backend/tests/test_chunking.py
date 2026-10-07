from app.services import chunking
from app.services.chunking import (
    _overlap_tail,
    _split_long_sentence,
    chunk_pages,
    chunk_text,
    fit_to_token_limit,
)
from app.services.embedding_service import count_tokens, max_input_tokens
from helpers import distinct_prose


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


def test_a_sentence_longer_than_the_limit_is_split_at_word_boundaries():
    words = [f"word{i}" for i in range(300)]
    sentence = " ".join(words)  # one huge "sentence": no punctuation to split on
    assert len(sentence) > 1000

    chunks = chunk_text(sentence, max_chars=200, overlap_chars=40)
    assert len(chunks) > 5
    rejoined = []
    for chunk in chunks:
        assert len(chunk) <= 200
        for token in chunk.split():
            assert token in set(words), f"split mid-word: {token!r}"
        rejoined.extend(chunk.split())
    assert rejoined == words  # nothing lost, nothing repeated


def test_split_long_sentence_uses_the_last_whitespace_before_the_limit():
    assert _split_long_sentence("aaaa bbbb cccc dddd", 9) == ["aaaa bbbb", "cccc dddd"]
    # A break exactly at the limit is used.
    assert _split_long_sentence("aaaa bbbb cccc", 9) == ["aaaa bbbb", "cccc"]
    # Newlines and tabs count as whitespace.
    assert _split_long_sentence("aaaa" + chr(10) + "bbbb" + chr(9) + "cccc dddd", 9) == [
        "aaaa" + chr(10) + "bbbb",
        "cccc dddd",
    ]
    # Short enough already: one piece.
    assert _split_long_sentence("short one", 50) == ["short one"]


def test_split_long_sentence_falls_back_to_a_hard_cut_only_without_any_whitespace():
    url = "https://example.com/" + "a" * 80
    pieces = _split_long_sentence(url, 30)
    assert all(len(p) <= 30 for p in pieces)
    assert "".join(pieces) == url  # hard cuts lose nothing

    mixed = "intro " + "x" * 50 + " outro"
    pieces = _split_long_sentence(mixed, 20)
    assert all(len(p) <= 20 for p in pieces)
    assert pieces[0] == "intro"  # split at the space before the long run
    assert "".join(pieces).replace(" ", "") == mixed.replace(" ", "")
    assert pieces[-1] == "xxxxxxxxxx outro"  # the remainder fits, so the break is kept


def test_split_long_sentence_always_makes_progress():
    pieces = _split_long_sentence(" " * 5 + "x" * 25, 10)
    assert pieces and all(0 < len(p) <= 10 for p in pieces)
    assert "".join(pieces) == "x" * 25


# --- fitting the embedding model's input limit --------------------------------------------

# The chunk size in effect before the embedding input limit was taken into account.
OLD_MAX_CHARS, OLD_OVERLAP_CHARS = 2600, 390


def test_default_chunks_target_well_inside_the_embedders_input_limit():
    assert chunking.TARGET_TOKENS <= 0.8 * max_input_tokens()
    assert chunking.MAX_CHARS == chunking.TARGET_TOKENS * chunking.CHARS_PER_TOKEN


def words_as_tokens(texts):
    return [len(t.split()) for t in texts]


def test_fit_leaves_chunks_that_already_fit_untouched():
    chunks = ["a b c", "d e f g"]
    assert fit_to_token_limit(chunks, words_as_tokens, max_tokens=10) == chunks


def test_fit_splits_an_overlong_chunk_until_every_piece_fits_and_loses_no_words():
    words = [f"w{i}" for i in range(500)]
    sentence_text = ". ".join(" ".join(words[i : i + 10]) for i in range(0, 500, 10)) + "."
    fitted = fit_to_token_limit(["short one", sentence_text], words_as_tokens, max_tokens=60)
    assert fitted[0] == "short one"
    assert len(fitted) > 3
    assert all(words_as_tokens([c])[0] <= 60 for c in fitted)
    rejoined = " ".join(fitted).replace(".", "").split()
    assert set(words) <= set(rejoined)  # overlap may repeat words, but none is lost


def test_fit_always_terminates_even_if_nothing_can_be_small_enough():
    stubborn = lambda texts: [10_000 for _ in texts]  # every text "has" 10000 tokens
    out = fit_to_token_limit(["some words here that cannot get small enough " * 5], stubborn, max_tokens=5)
    assert out  # gave up and kept the text rather than looping or dropping it


def test_fit_handles_no_chunks():
    assert fit_to_token_limit([], words_as_tokens, 10) == []


def test_chunk_pages_enforces_the_token_limit_when_given_a_counter():
    page = "word " * 400  # 2000 chars, one 400-token sentence under the fake counter
    plain = chunk_pages([(1, page)], max_chars=2000, overlap_chars=0)
    assert max(words_as_tokens([p.text for p in plain])) > 50
    fitted = chunk_pages(
        [(1, page)], max_chars=2000, overlap_chars=0, token_counter=words_as_tokens, max_tokens=50
    )
    assert max(words_as_tokens([p.text for p in fitted])) <= 50
    assert {p.page_number for p in fitted} == {1}
    assert [p.chunk_index for p in fitted] == list(range(len(fitted)))


def test_prose_chunks_fit_the_real_embedding_model():
    pieces = chunk_pages([(1, distinct_prose(200))])
    counts = count_tokens([p.text for p in pieces])
    assert len(pieces) > 5
    assert max(counts) <= max_input_tokens()


def test_the_old_chunk_size_overflowed_the_embedder_which_is_the_bug_being_fixed():
    pages = [(1, distinct_prose(200))]
    old = chunk_pages(pages, max_chars=OLD_MAX_CHARS, overlap_chars=OLD_OVERLAP_CHARS)
    counts = count_tokens([p.text for p in old])
    limit = max_input_tokens()
    assert max(counts) > limit
    visible = sum(min(c, limit) for c in counts) / sum(counts)
    assert visible < 0.6  # most of each old chunk was invisible to search


DENSE_TEXTS = {
    "maths": " ".join(
        f"Let $x_{i} = \\frac{{{i}}}{{{i + 1}}} \\sum_{{k=0}}^{{{i}}} a_k^{{{i}}}$." for i in range(120)
    ),
    "code": "\n".join(f"for (int i{n} = 0; i{n} < n; i{n}++) {{ a[i{n}] += b[i{n}] * c[{n}]; }}" for n in range(120)),
    "digits": ", ".join(str(1000003 * n) for n in range(300)) + ".",
}


import pytest  # noqa: E402


@pytest.mark.parametrize("kind", sorted(DENSE_TEXTS))
def test_text_that_tokenizes_badly_still_fits_the_real_embedding_model(kind):
    """Maths, code and long numbers pack many more tokens into each character
    than prose; the character budget alone would overflow, so the token pass
    has to split them further."""
    text = DENSE_TEXTS[kind]
    chars_only = chunk_pages([(1, text)])
    assert max(count_tokens([p.text for p in chars_only])) > max_input_tokens(), (
        f"{kind} was supposed to overflow on characters alone; make the sample denser"
    )

    pieces = chunk_pages([(1, text)], token_counter=count_tokens, max_tokens=max_input_tokens())
    assert max(count_tokens([p.text for p in pieces])) <= max_input_tokens()
