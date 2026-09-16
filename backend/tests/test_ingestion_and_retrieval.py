from app import models
from app.services import llm_service


def _create_topic(client, name, course="Test Course"):
    resp = client.post("/topics", json={"name": name, "course": course, "description": ""})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_ingest_text_creates_chunks_with_real_embeddings(client, db_session):
    topic_id = _create_topic(client, "Normalization")

    resp = client.post(
        "/sources/text",
        json={
            "topic_id": topic_id,
            "source_type": "self_supplied",
            "title": "Normalization notes",
            "text": (
                "Database normalization removes redundant data. It organizes "
                "tables into normal forms to reduce update anomalies."
            ),
        },
    )
    assert resp.status_code == 200, resp.text
    source_id = resp.json()["id"]

    chunks = db_session.query(models.Chunk).filter(models.Chunk.source_id == source_id).all()
    assert len(chunks) >= 1
    assert all(c.embedding and len(c.embedding) == 384 for c in chunks)
    assert all(c.page_number is None for c in chunks)  # pasted text has no pages


def test_ingest_pdf_upload_extracts_real_text_and_tracks_page_numbers(
    client, db_session, sample_pdf_bytes
):
    topic_id = _create_topic(client, "Mixed PDF Topic")

    resp = client.post(
        "/sources/upload",
        data={"topic_id": str(topic_id), "source_type": "official_upload"},
        files={"file": ("notes.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    source_id = resp.json()["id"]

    chunks = (
        db_session.query(models.Chunk)
        .filter(models.Chunk.source_id == source_id)
        .order_by(models.Chunk.chunk_index)
        .all()
    )
    assert len(chunks) >= 2
    assert {c.page_number for c in chunks} == {1, 2}
    # extraction actually pulled real text out of the PDF, not raw bytes
    joined = " ".join(c.chunk_text.lower() for c in chunks)
    assert "normalization" in joined
    assert "binary search tree" in joined


def test_list_sources_reports_chunk_count(client):
    topic_id = _create_topic(client, "Recursion")

    resp = client.post(
        "/sources/text",
        json={
            "topic_id": topic_id,
            "source_type": "self_supplied",
            "title": "Recursion notes",
            "text": "A recursive function calls itself with a smaller input until it hits a base case.",
        },
    )
    assert resp.status_code == 200, resp.text
    source_id = resp.json()["id"]

    listed = client.get(f"/sources/topic/{topic_id}")
    assert listed.status_code == 200, listed.text
    sources = listed.json()
    assert len(sources) == 1
    assert sources[0]["id"] == source_id
    assert sources[0]["chunk_count"] >= 1


def test_delete_source_removes_it_and_its_chunks(client, db_session):
    topic_id = _create_topic(client, "Hashing")

    resp = client.post(
        "/sources/text",
        json={
            "topic_id": topic_id,
            "source_type": "self_supplied",
            "title": "Hashing notes",
            "text": "A hash function maps keys to bucket indices for fast average-case lookup.",
        },
    )
    assert resp.status_code == 200, resp.text
    source_id = resp.json()["id"]
    assert db_session.query(models.Chunk).filter(models.Chunk.source_id == source_id).count() >= 1

    delete_resp = client.delete(f"/sources/{source_id}")
    assert delete_resp.status_code == 204

    assert db_session.get(models.Source, source_id) is None
    assert db_session.query(models.Chunk).filter(models.Chunk.source_id == source_id).count() == 0

    listed = client.get(f"/sources/topic/{topic_id}")
    assert listed.json() == []


def test_delete_missing_source_returns_404(client):
    resp = client.delete("/sources/999999")
    assert resp.status_code == 404


def test_retrieval_returns_the_relevant_chunk_and_filters_by_topic(client):
    normalization_topic = _create_topic(client, "Normalization")
    bst_topic = _create_topic(client, "Binary Search Trees")

    client.post(
        "/sources/text",
        json={
            "topic_id": normalization_topic,
            "source_type": "self_supplied",
            "title": "Normalization notes",
            "text": (
                "Database normalization removes redundant data by organizing "
                "tables into normal forms such as 1NF, 2NF and 3NF."
            ),
        },
    )
    client.post(
        "/sources/text",
        json={
            "topic_id": bst_topic,
            "source_type": "self_supplied",
            "title": "BST notes",
            "text": (
                "A binary search tree is a hierarchical data structure where "
                "left children are smaller than their parent node."
            ),
        },
    )

    resp = client.post("/retrieve", json={"question": "What is normalization?", "top_k": 3})
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert results, "expected at least one retrieved chunk"
    assert "normal" in results[0]["chunk_text"].lower()
    assert results[0]["filename"] == "Normalization notes"
    assert 0.0 <= results[0]["similarity_score"] <= 1.0001

    # Scoping to the BST topic should exclude the normalization chunk even
    # though the question is about normalization.
    resp_scoped = client.post(
        "/retrieve",
        json={"question": "What is normalization?", "topic_id": bst_topic, "top_k": 3},
    )
    assert resp_scoped.status_code == 200
    scoped_results = resp_scoped.json()["results"]
    assert all(r["filename"] == "BST notes" for r in scoped_results)


def test_ask_endpoint_uses_real_retrieval_and_still_flags_prerequisites(client, monkeypatch):
    # This test's job is confirming the prerequisite/mastery pipeline still
    # works, not exercising the LLM — mock it for determinism and speed.
    monkeypatch.setattr(
        llm_service,
        "generate",
        lambda system, user, model=None: llm_service.LLMResult(ok=True, text="An answer."),
    )

    prereq_topic = _create_topic(client, "Sets", course="DS&A")
    main_topic_resp = client.post(
        "/topics", json={"name": "Hash Tables", "course": "DS&A", "description": ""}
    )
    main_topic = main_topic_resp.json()["id"]

    prereq_resp = client.post(
        "/topics/prerequisites",
        json={"topic_id": main_topic, "prerequisite_topic_id": prereq_topic},
    )
    assert prereq_resp.status_code == 200, prereq_resp.text

    client.post(
        "/sources/text",
        json={
            "topic_id": main_topic,
            "source_type": "self_supplied",
            "title": "Hash table notes",
            "text": (
                "A hash table maps keys to values using a hash function to "
                "compute an index into an array of buckets."
            ),
        },
    )

    resp = client.post("/ask", json={"query": "How do hash tables work?", "topic_id": main_topic})
    assert resp.status_code == 200, resp.text  # /ask must not crash even with the real tutor wired in
    body = resp.json()
    # Tutor answer generation itself (grounded/stub/fallback wording) is
    # covered in test_ask_endpoint_tutor.py — this test's job is confirming
    # the existing prerequisite/mastery logic still works end to end.
    flagged_names = [t["name"] for t in body["flagged_prerequisites"]]
    assert "Sets" in flagged_names  # existing prerequisite/mastery logic still works
