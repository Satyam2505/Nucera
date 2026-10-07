"""Re-chunking stored sources from raw_text + old chunks (reindex_service and the
reindex.py CLI). Uses the real embedding model; no LLM is involved."""

import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine

import reindex
from app import models
from app.services import reindex_service
from app.services.chunking import chunk_pages
from app.services.embedding_service import EMBEDDING_DIM, count_tokens, embed_texts, max_input_tokens
from app.services.reindex_service import (
    STALE_CHUNK_CHARS,
    count_stale,
    pages_for_source,
    reconstruct_pages,
    reindex_all,
    reindex_source,
)
from helpers import distinct_prose, make_topic

# What the chunker used before chunk sizes were reduced.
OLD_MAX_CHARS, OLD_OVERLAP_CHARS = 2600, 390


def norm(text):
    return " ".join(text.split())


def add_legacy_source(db, topic_id, pages, title="notes.pdf", raw_text=None, embed=False):
    """A source as the old ingestion wrote it: old-size chunks, page numbers on
    the chunks, raw_text = the pages joined by blank lines."""
    pieces = chunk_pages(pages, max_chars=OLD_MAX_CHARS, overlap_chars=OLD_OVERLAP_CHARS)
    vectors = embed_texts([p.text for p in pieces]) if embed else [[0.1] * EMBEDDING_DIM] * len(pieces)
    source = models.Source(
        topic_id=topic_id,
        source_type=models.SourceType.self_supplied,
        title=title,
        raw_text="\n\n".join(text for _, text in pages) if raw_text is None else raw_text,
    )
    for piece, vector in zip(pieces, vectors):
        source.chunks.append(
            models.Chunk(
                topic_id=topic_id,
                chunk_text=piece.text,
                chunk_index=piece.chunk_index,
                page_number=piece.page_number,
                embedding=vector,
            )
        )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@pytest.fixture()
def topic_id(client):
    return make_topic(client, "Hash Tables", course="Test")["id"]


def three_pages():
    return [
        (1, distinct_prose(30)),
        (2, distinct_prose(45)),
        (3, "A short last page. It has two sentences."),
    ]


def chunks_of(db, source_id):
    db.expire_all()
    return (
        db.query(models.Chunk)
        .filter(models.Chunk.source_id == source_id)
        .order_by(models.Chunk.chunk_index)
        .all()
    )


# --- rebuilding pages from old chunks ----------------------------------------------------


def test_old_chunks_stitch_back_into_exactly_their_pages(db_session, topic_id):
    pages = three_pages()
    source = add_legacy_source(db_session, topic_id, pages)
    assert len(source.chunks) > 3  # multi-chunk pages exercise the overlap removal

    rebuilt = reconstruct_pages(list(source.chunks))
    assert [p for p, _ in rebuilt] == [1, 2, 3]
    for (_, original), (_, text) in zip(pages, rebuilt):
        assert norm(text) == norm(original)


def test_a_page_split_without_overlap_stitches_back_too(db_session, topic_id):
    # One enormous "sentence" is cut at word boundaries with no overlap carried over.
    page = " ".join(f"token{i}" for i in range(1500))
    source = add_legacy_source(db_session, topic_id, [(1, page)])
    assert len(source.chunks) > 1
    ((number, text),) = reconstruct_pages(list(source.chunks))
    assert number == 1 and norm(text) == norm(page)


def test_pages_for_a_text_source_come_from_raw_text(db_session, topic_id):
    text = distinct_prose(40)
    source = add_legacy_source(db_session, topic_id, [(None, text)])
    pages, reason = pages_for_source(source)
    assert pages == [(None, text)] and reason == ""


def test_a_source_whose_text_no_longer_matches_its_chunks_cannot_be_rebuilt(db_session, topic_id):
    source = add_legacy_source(db_session, topic_id, three_pages(), raw_text="something else entirely")
    pages, reason = pages_for_source(source)
    assert pages is None and "raw_text" in reason


# --- reindexing ------------------------------------------------------------------------------


def test_reindex_keeps_page_numbers_and_every_chunk_fits_the_embedder(db_session, topic_id):
    pages = three_pages()
    source = add_legacy_source(db_session, topic_id, pages)
    old_count = len(source.chunks)
    assert max(count_tokens([c.chunk_text for c in source.chunks])) > max_input_tokens()

    result = reindex_source(db_session, source)

    assert result.status == "reindexed" and result.pages_preserved is True
    assert result.old_chunks == old_count and result.new_chunks > old_count
    new = chunks_of(db_session, source.id)
    assert len(new) == result.new_chunks
    assert [c.chunk_index for c in new] == list(range(len(new)))
    assert max(count_tokens([c.chunk_text for c in new])) <= max_input_tokens()
    assert all(c.embedding and len(c.embedding) == EMBEDDING_DIM for c in new)
    assert all(c.topic_id == topic_id for c in new)
    assert [p for p in dict.fromkeys(c.page_number for c in new)] == [1, 2, 3]
    # A chunk never spans pages: the page-3 sentence is only ever under page 3.
    for chunk in new:
        assert ("short last page" in chunk.chunk_text) == (chunk.page_number == 3)
    # No text was lost: every page's words are still there.
    for number, original in pages:
        rebuilt = " ".join(c.chunk_text for c in new if c.page_number == number)
        assert set(norm(original).split()) <= set(rebuilt.split())


def test_the_source_itself_is_untouched(db_session, topic_id):
    source = add_legacy_source(db_session, topic_id, three_pages(), title="Lecture 4.pdf")
    raw_before = source.raw_text
    reindex_source(db_session, source)
    db_session.expire_all()
    again = db_session.get(models.Source, source.id)
    assert again.title == "Lecture 4.pdf" and again.raw_text == raw_before


def test_reindex_is_idempotent(db_session, topic_id):
    source = add_legacy_source(db_session, topic_id, three_pages())
    assert reindex_source(db_session, source).status == "reindexed"
    ids_after_first = [c.id for c in chunks_of(db_session, source.id)]

    second = reindex_source(db_session, source)
    assert second.status == "up_to_date"
    assert [c.id for c in chunks_of(db_session, source.id)] == ids_after_first  # not rewritten


def test_force_rebuilds_even_when_everything_fits(db_session, topic_id, monkeypatch):
    source = add_legacy_source(db_session, topic_id, three_pages())
    reindex_source(db_session, source)
    texts_before = [c.chunk_text for c in chunks_of(db_session, source.id)]

    embedded = []
    real_embed = reindex_service.embed_texts
    monkeypatch.setattr(
        reindex_service, "embed_texts", lambda texts: embedded.append(len(texts)) or real_embed(texts)
    )

    assert reindex_source(db_session, source).status == "up_to_date"
    assert embedded == []  # nothing recomputed unless asked

    assert reindex_source(db_session, source, force=True).status == "reindexed"
    assert embedded == [len(texts_before)]
    assert [c.chunk_text for c in chunks_of(db_session, source.id)] == texts_before  # same result


def test_a_plain_text_source_is_reindexed_without_page_numbers(db_session, topic_id):
    source = add_legacy_source(db_session, topic_id, [(None, distinct_prose(60))])
    result = reindex_source(db_session, source)
    assert result.status == "reindexed" and result.pages_preserved is True
    new = chunks_of(db_session, source.id)
    assert len(new) > 1 and {c.page_number for c in new} == {None}


def test_a_small_source_that_already_fits_is_left_alone(db_session, topic_id):
    source = add_legacy_source(db_session, topic_id, [(None, "Just one short note about hashing.")])
    result = reindex_source(db_session, source)
    assert result.status == "up_to_date"


def test_dry_run_changes_nothing(db_session, topic_id):
    source = add_legacy_source(db_session, topic_id, three_pages())
    before = [(c.id, c.chunk_text) for c in chunks_of(db_session, source.id)]
    result = reindex_source(db_session, source, dry_run=True)
    assert result.status == "reindexed" and result.new_chunks > result.old_chunks
    assert [(c.id, c.chunk_text) for c in chunks_of(db_session, source.id)] == before


def test_unrebuildable_page_numbers_skip_the_source_by_default(db_session, topic_id):
    source = add_legacy_source(db_session, topic_id, three_pages(), raw_text="not the same text")
    before = [(c.id, c.page_number) for c in chunks_of(db_session, source.id)]

    result = reindex_source(db_session, source)

    assert result.status == "skipped" and "raw_text" in result.reason
    assert [(c.id, c.page_number) for c in chunks_of(db_session, source.id)] == before


def test_allow_page_loss_reindexes_without_page_numbers_and_says_so(db_session, topic_id):
    source = add_legacy_source(db_session, topic_id, three_pages(), raw_text=distinct_prose(30))
    result = reindex_source(db_session, source, allow_page_loss=True)
    assert result.status == "reindexed" and result.pages_preserved is False
    new = chunks_of(db_session, source.id)
    assert {c.page_number for c in new} == {None}
    assert max(count_tokens([c.chunk_text for c in new])) <= max_input_tokens()


def test_a_failing_embedding_step_leaves_the_old_chunks_exactly_as_they_were(
    db_session, topic_id, monkeypatch
):
    source = add_legacy_source(db_session, topic_id, three_pages())
    before = [(c.id, c.chunk_text, c.page_number) for c in chunks_of(db_session, source.id)]

    def boom(texts):
        raise RuntimeError("embedding model crashed")

    monkeypatch.setattr(reindex_service, "embed_texts", boom)
    with pytest.raises(RuntimeError):
        reindex_source(db_session, source)

    assert [(c.id, c.chunk_text, c.page_number) for c in chunks_of(db_session, source.id)] == before


def test_a_wrong_number_of_vectors_is_a_failure_and_changes_nothing(db_session, topic_id, monkeypatch):
    source = add_legacy_source(db_session, topic_id, three_pages())
    before = [c.id for c in chunks_of(db_session, source.id)]
    monkeypatch.setattr(reindex_service, "embed_texts", lambda texts: [[0.0] * EMBEDDING_DIM])
    result = reindex_source(db_session, source)
    assert result.status == "failed"
    assert [c.id for c in chunks_of(db_session, source.id)] == before


def test_a_write_failure_rolls_back_to_the_old_chunks(db_session, topic_id, monkeypatch):
    source = add_legacy_source(db_session, topic_id, three_pages())
    before = [c.id for c in chunks_of(db_session, source.id)]

    real_commit = db_session.commit

    def failing_commit():
        raise RuntimeError("disk full")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    result = reindex_source(db_session, source)
    monkeypatch.setattr(db_session, "commit", real_commit)

    assert result.status == "failed"
    assert [c.id for c in chunks_of(db_session, source.id)] == before


def test_one_bad_source_does_not_stop_the_others(db_session, topic_id, monkeypatch):
    first = add_legacy_source(db_session, topic_id, three_pages(), title="first.pdf")
    second = add_legacy_source(db_session, topic_id, three_pages(), title="second.pdf")

    real_embed = reindex_service.embed_texts
    calls = {"n": 0}

    def flaky(texts):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return real_embed(texts)

    monkeypatch.setattr(reindex_service, "embed_texts", flaky)
    seen = []
    results = reindex_all(db_session, on_result=seen.append)

    assert [r.status for r in results] == ["failed", "reindexed"]
    assert [r.source_id for r in seen] == [first.id, second.id]
    assert max(count_tokens([c.chunk_text for c in chunks_of(db_session, second.id)])) <= max_input_tokens()


def test_reindexing_recovers_a_fact_the_old_chunks_hid_from_search(db_session, client, topic_id):
    """The bug itself: a fact late in a big chunk was past the embedder's 256-token
    cut-off, so searching for it found nothing; after re-indexing it is found."""
    from app.services.retrieval_service import retrieve_relevant_chunks

    filler = distinct_prose(60)
    fact = (
        "The sandwich orchestra of Quillington plays exclusively on seventeen "
        "copper trombones every harvest festival."
    )
    source = add_legacy_source(db_session, topic_id, [(4, filler + " " + fact)], embed=True)
    query = "Which instruments does the Quillington sandwich orchestra play?"
    assert any(fact in c.chunk_text for c in source.chunks)

    def best_chunk_with_fact():
        matches = retrieve_relevant_chunks(
            db_session, query, user_id=client.user_id, topic_id=topic_id, top_k=1
        )
        return matches[0]

    before = best_chunk_with_fact()
    assert reindex_source(db_session, source).status == "reindexed"
    after = best_chunk_with_fact()

    assert "copper trombones" in after["chunk"].chunk_text
    assert after["chunk"].page_number == 4
    assert after["similarity_score"] > before["similarity_score"] + 0.1


# --- finding stale chunks --------------------------------------------------------------------------


def test_count_stale_sees_only_chunks_the_current_chunker_could_not_have_written(db_session, topic_id):
    assert count_stale(db_session) == (0, 0)
    add_legacy_source(db_session, topic_id, [(None, "Short note.")], title="short")
    assert count_stale(db_session) == (0, 0)

    big = add_legacy_source(db_session, topic_id, three_pages(), title="big")
    expected = sum(len(c.chunk_text) > STALE_CHUNK_CHARS for c in chunks_of(db_session, big.id))
    assert expected >= 2  # the long pages produced oversized chunks; the short last page did not
    assert count_stale(db_session) == (expected, 1)

    reindex_source(db_session, big)
    assert count_stale(db_session) == (0, 0)


def test_a_server_start_warns_when_stale_chunks_exist(db_session, topic_id, caplog):
    from fastapi.testclient import TestClient

    from app.main import app

    add_legacy_source(db_session, topic_id, three_pages())
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        with TestClient(app):  # entering the context runs the startup hook
            pass
    assert "python reindex.py" in caplog.text


def test_a_clean_database_starts_without_a_warning(db_session, caplog):
    from fastapi.testclient import TestClient

    from app.main import app

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        with TestClient(app):
            pass
    assert "reindex.py" not in caplog.text


# --- the command-line script ---------------------------------------------------------------------------


def test_cli_dry_run_reports_and_writes_nothing(db_session, topic_id, capsys):
    source = add_legacy_source(db_session, topic_id, three_pages(), title="Lecture.pdf")
    before = [c.id for c in chunks_of(db_session, source.id)]

    code = reindex.main(["--dry-run"])

    out = capsys.readouterr().out
    assert code == 0
    assert "Lecture.pdf" in out and "would be re-indexed" in out
    assert "Backed up" not in out
    assert [c.id for c in chunks_of(db_session, source.id)] == before


def test_cli_backs_up_a_sqlite_database_before_writing(db_session, topic_id, capsys, monkeypatch, tmp_path):
    add_legacy_source(db_session, topic_id, three_pages())
    fake_db = tmp_path / "dev.db"
    fake_db.write_bytes(b"pretend database contents")
    monkeypatch.setattr(reindex, "engine", create_engine(f"sqlite:///{fake_db.as_posix()}"))

    code = reindex.main([])

    backups = list(tmp_path.glob("dev.db.bak-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"pretend database contents"
    assert "Backed up the database to" in capsys.readouterr().out
    assert code == 0


def test_cli_refuses_to_write_without_a_backup_for_other_databases(monkeypatch, capsys):
    monkeypatch.setattr(reindex, "engine", create_engine("postgresql+psycopg2://u:p@localhost/none"))
    called = []
    monkeypatch.setattr(reindex, "reindex_all", lambda *a, **k: called.append(1) or [])

    assert reindex.main([]) == 2
    assert not called
    assert "--i-have-a-backup" in capsys.readouterr().out


def test_cli_does_not_run_if_the_backup_cannot_be_made(monkeypatch, tmp_path):
    monkeypatch.setattr(reindex, "engine", create_engine(f"sqlite:///{(tmp_path / 'missing.db').as_posix()}"))
    called = []
    monkeypatch.setattr(reindex, "reindex_all", lambda *a, **k: called.append(1) or [])
    with pytest.raises(SystemExit):
        reindex.main([])
    assert not called
    assert not Path(tmp_path / "missing.db").exists()


def test_cli_exit_code_flags_skipped_sources(db_session, topic_id, capsys):
    add_legacy_source(db_session, topic_id, three_pages(), raw_text="mismatch", title="Odd.pdf")
    assert reindex.main(["--dry-run"]) == 1
    assert "SKIPPED" in capsys.readouterr().out
