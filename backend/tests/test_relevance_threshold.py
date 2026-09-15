"""Empirically checks that RETRIEVAL_RELEVANCE_THRESHOLD actually separates
on-topic from off-topic questions, using the real embedding model (no LLM
involved). This is what the threshold in app/config.py was tuned against.
"""

from app.config import RETRIEVAL_RELEVANCE_THRESHOLD
from app.services.retrieval_service import retrieve_relevant_chunks


def _ingest(client, topic_id, title, text):
    resp = client.post(
        "/sources/text",
        json={"topic_id": topic_id, "source_type": "self_supplied", "title": title, "text": text},
    )
    assert resp.status_code == 200, resp.text


def test_on_topic_question_clears_the_threshold(client, db_session):
    resp = client.post("/topics", json={"name": "Hash Tables", "course": "Test", "description": ""})
    topic_id = resp.json()["id"]
    _ingest(
        client,
        topic_id,
        "Hash table notes",
        "A hash table maps keys to values using a hash function to compute a bucket index. "
        "Collisions are resolved with chaining or open addressing.",
    )

    matches = retrieve_relevant_chunks(db_session, "What is a hash function?", topic_id=topic_id, top_k=3)
    assert matches
    assert matches[0]["similarity_score"] >= RETRIEVAL_RELEVANCE_THRESHOLD


def test_off_topic_question_falls_below_the_threshold(client, db_session):
    resp = client.post("/topics", json={"name": "Hash Tables 2", "course": "Test", "description": ""})
    topic_id = resp.json()["id"]
    _ingest(
        client,
        topic_id,
        "Hash table notes",
        "A hash table maps keys to values using a hash function to compute a bucket index. "
        "Collisions are resolved with chaining or open addressing.",
    )

    # Genuinely unrelated to the uploaded material.
    matches = retrieve_relevant_chunks(
        db_session, "What ingredients go into a chocolate cake?", topic_id=topic_id, top_k=3
    )
    assert matches  # some chunk always comes back, it's just not relevant
    assert matches[0]["similarity_score"] < RETRIEVAL_RELEVANCE_THRESHOLD
