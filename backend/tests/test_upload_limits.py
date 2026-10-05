"""Upload validation (type, size, content) and atomic ingestion.

The embedder is replaced with a fast fake, so none of this loads the real
sentence-transformers model.
"""

import fitz
import pytest
from sqlalchemy import func

from app import config, models
from app.routers import ingestion
from app.services.embedding_service import EMBEDDING_DIM
from helpers import make_topic

MB = 1024 * 1024


@pytest.fixture(autouse=True)
def fast_embedder(monkeypatch):
    monkeypatch.setattr(
        ingestion, "embed_texts", lambda texts: [[0.1] * EMBEDDING_DIM for _ in texts]
    )


@pytest.fixture()
def topic(client):
    return make_topic(client, "Upload target", course="Uploads")["id"]


def upload(client, topic_id, filename, content, content_type="application/octet-stream"):
    return client.post(
        "/sources/upload",
        data={"topic_id": str(topic_id), "source_type": "self_supplied"},
        files={"file": (filename, content, content_type)},
    )


def counts(db_session):
    db_session.rollback()
    return (
        db_session.query(func.count()).select_from(models.Source).scalar(),
        db_session.query(func.count()).select_from(models.Chunk).scalar(),
    )


def pdf_bytes(*page_texts):
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


# --- accepted types --------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,content",
    [
        ("notes.txt", b"Plain text notes about hash tables."),
        ("NOTES.TXT", b"Upper-case extension is fine."),
        ("readme.md", b"# Heading\n\nMarkdown notes about trees."),
    ],
)
def test_text_and_markdown_files_are_accepted(client, db_session, topic, filename, content):
    resp = upload(client, topic, filename, content)
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == filename
    assert resp.json()["chunk_count"] >= 1
    sources, chunks = counts(db_session)
    assert sources == 1 and chunks >= 1


def test_a_real_pdf_is_accepted_even_with_an_upper_case_extension(client, topic):
    resp = upload(client, topic, "Lecture.PDF", pdf_bytes("Normalization removes redundancy."))
    assert resp.status_code == 200, resp.text


# --- rejected types ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    ["notes.docx", "image.png", "archive.zip", "notes", "notes.pdf.exe", "script.py", ".txt.bak"],
)
def test_other_file_types_are_415(client, db_session, topic, filename):
    resp = upload(client, topic, filename, b"some bytes")
    assert resp.status_code == 415
    assert "PDF, .txt or .md" in resp.json()["detail"]
    assert counts(db_session) == (0, 0)


def test_a_pdf_extension_without_pdf_content_is_415(client, db_session, topic):
    resp = upload(client, topic, "fake.pdf", b"This is just text pretending to be a PDF.")
    assert resp.status_code == 415
    assert "isn't a PDF" in resp.json()["detail"]
    assert counts(db_session) == (0, 0)


def test_a_pdf_header_is_found_even_after_a_little_leading_junk(client, topic):
    resp = upload(client, topic, "lecture.pdf", b"\n\n" + pdf_bytes("Some real text here."))
    # The header is within the first KB, so it is not refused as "not a PDF"
    # (whatever the parser then makes of the stray bytes).
    assert resp.status_code in (200, 422)
    assert resp.status_code != 415


def test_a_corrupt_pdf_is_422(client, db_session, topic):
    resp = upload(client, topic, "broken.pdf", b"%PDF-1.4\nthis is not a real pdf body at all")
    assert resp.status_code == 422
    assert "Couldn't read this PDF" in resp.json()["detail"]
    assert counts(db_session) == (0, 0)


# --- empty content -----------------------------------------------------------------------------


@pytest.mark.parametrize("content", [b"", b"   \n\n\t  \n"])
def test_a_text_file_with_no_text_is_422(client, db_session, topic, content):
    resp = upload(client, topic, "empty.txt", content)
    assert resp.status_code == 422
    assert "No text could be extracted" in resp.json()["detail"]
    assert counts(db_session) == (0, 0)


def test_a_pdf_with_no_extractable_text_is_422(client, db_session, topic):
    resp = upload(client, topic, "blank.pdf", pdf_bytes(None, None))
    assert resp.status_code == 422
    assert "OCR" in resp.json()["detail"]
    assert counts(db_session) == (0, 0)


@pytest.mark.parametrize("text", ["", "   ", "\n\t \n"])
def test_pasted_blank_text_is_422(client, db_session, topic, text):
    resp = client.post(
        "/sources/text",
        json={"topic_id": topic, "source_type": "self_supplied", "title": "x", "text": text},
    )
    assert resp.status_code == 422
    assert counts(db_session) == (0, 0)


# --- size ---------------------------------------------------------------------------------------


def test_the_default_limit_is_20_mb():
    assert config.UPLOAD_MAX_BYTES == 20 * MB


def test_a_file_over_the_limit_is_413_and_one_at_the_limit_is_fine(client, db_session, topic, monkeypatch):
    monkeypatch.setattr(ingestion, "UPLOAD_MAX_BYTES", MB)
    line = b"word " * 20 + b"\n"

    at_limit = (line * (MB // len(line) + 1))[:MB]
    assert len(at_limit) == MB
    assert upload(client, topic, "exact.txt", at_limit).status_code == 200

    sources_before, chunks_before = counts(db_session)
    resp = upload(client, topic, "big.txt", at_limit + b"x")
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"] and "1 MB" in resp.json()["detail"]
    assert counts(db_session) == (sources_before, chunks_before)


def test_the_type_is_checked_before_the_size(client, topic, monkeypatch):
    monkeypatch.setattr(ingestion, "UPLOAD_MAX_BYTES", 10)
    assert upload(client, topic, "big.docx", b"x" * 1000).status_code == 415


# --- atomic ingestion -------------------------------------------------------------------------------


def failing_embedder(monkeypatch):
    def boom(texts):
        raise RuntimeError("embedding model exploded")

    monkeypatch.setattr(ingestion, "embed_texts", boom)


def test_an_embedding_failure_on_upload_leaves_no_source_and_no_chunks(client, db_session, topic, monkeypatch):
    failing_embedder(monkeypatch)
    resp = upload(client, topic, "notes.txt", b"Some perfectly good notes.")
    assert resp.status_code == 503
    assert "Nothing was saved" in resp.json()["detail"]
    assert counts(db_session) == (0, 0)  # neither the source nor any chunk rows
    assert client.get(f"/sources/topic/{topic}").json() == []


def test_an_embedding_failure_on_pasted_text_leaves_nothing_either(client, db_session, topic, monkeypatch):
    failing_embedder(monkeypatch)
    resp = client.post(
        "/sources/text",
        json={"topic_id": topic, "source_type": "self_supplied", "title": "x", "text": "Some notes."},
    )
    assert resp.status_code == 503
    assert counts(db_session) == (0, 0)


def test_a_failure_does_not_disturb_sources_that_already_exist(client, db_session, topic, monkeypatch):
    assert upload(client, topic, "first.txt", b"First notes.").status_code == 200
    existing = counts(db_session)

    failing_embedder(monkeypatch)
    assert upload(client, topic, "second.txt", b"Second notes.").status_code == 503
    assert counts(db_session) == existing


def test_an_embedder_that_returns_too_few_vectors_is_also_atomic(client, db_session, topic, monkeypatch):
    monkeypatch.setattr(ingestion, "embed_texts", lambda texts: [[0.1] * EMBEDDING_DIM][:0])
    resp = upload(client, topic, "notes.txt", b"Some notes.")
    assert resp.status_code == 503
    assert counts(db_session) == (0, 0)


def test_source_and_chunks_are_written_together_with_embeddings(client, db_session, topic):
    resp = upload(client, topic, "notes.txt", b"Alpha. " * 1000)  # several chunks
    assert resp.status_code == 200
    db_session.rollback()
    chunks = db_session.query(models.Chunk).filter(models.Chunk.source_id == resp.json()["id"]).all()
    assert len(chunks) == resp.json()["chunk_count"] > 1
    assert all(len(c.embedding) == EMBEDDING_DIM for c in chunks)
    assert {c.topic_id for c in chunks} == {topic}


def test_uploading_to_someone_elses_topic_is_404_before_anything_is_read(other_client, topic, db_session):
    resp = upload(other_client, topic, "notes.txt", b"Sneaky notes.")
    assert resp.status_code == 404
    assert counts(db_session) == (0, 0)
