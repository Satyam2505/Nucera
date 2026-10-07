"""Empirically checks that RETRIEVAL_RELEVANCE_THRESHOLD actually separates
on-topic from off-topic questions, using the real embedding model (no LLM
involved). This is what the threshold in app/config.py was tuned against.
"""

import pytest

from app.config import RETRIEVAL_RELEVANCE_THRESHOLD
from app.services.retrieval_service import retrieve_relevant_chunks
from helpers import make_topic
from relevance_corpus import NOTES, OFF_TOPIC, ON_TOPIC


def _ingest(client, topic_id, title, text):
    resp = client.post(
        "/sources/text",
        json={"topic_id": topic_id, "source_type": "self_supplied", "title": title, "text": text},
    )
    assert resp.status_code == 200, resp.text


def test_on_topic_question_clears_the_threshold(client, db_session):
    topic_id = make_topic(client, "Hash Tables", course="Test")["id"]
    _ingest(
        client,
        topic_id,
        "Hash table notes",
        "A hash table maps keys to values using a hash function to compute a bucket index. "
        "Collisions are resolved with chaining or open addressing.",
    )

    matches = retrieve_relevant_chunks(
        db_session, "What is a hash function?", user_id=client.user_id, topic_id=topic_id, top_k=3
    )
    assert matches
    assert matches[0]["similarity_score"] >= RETRIEVAL_RELEVANCE_THRESHOLD


def test_off_topic_question_falls_below_the_threshold(client, db_session):
    topic_id = make_topic(client, "Hash Tables 2", course="Test")["id"]
    _ingest(
        client,
        topic_id,
        "Hash table notes",
        "A hash table maps keys to values using a hash function to compute a bucket index. "
        "Collisions are resolved with chaining or open addressing.",
    )

    # Genuinely unrelated to the uploaded material.
    matches = retrieve_relevant_chunks(
        db_session,
        "What ingredients go into a chocolate cake?",
        user_id=client.user_id,
        topic_id=topic_id,
        top_k=3,
    )
    assert matches  # some chunk always comes back, it's just not relevant
    assert matches[0]["similarity_score"] < RETRIEVAL_RELEVANCE_THRESHOLD


# --- the threshold against a labelled corpus ---------------------------------------------------
#
# RETRIEVAL_RELEVANCE_THRESHOLD depends on the embedding model and the chunk size,
# so it is re-checked here against tests/relevance_corpus.py, ingested through the
# real pipeline (chunking, tokenizer, embedder). If this fails after changing
# either, re-measure and choose the threshold again; don't loosen the asserts.
#
# Measured when chunks were reduced to fit the embedder (11 chunks, 28 on-topic and
# 16 off-topic questions): lowest on-topic top match 0.314, highest off-topic 0.290.
# 0.35 is kept rather than the 0.30 midpoint: it refused 3 of 28 on-topic questions
# and accepted none of the off-topic ones, and 0.30 leaves only a 0.01 margin that a
# larger topic (more chunks to match by chance) would erode.

@pytest.fixture()
def corpus_topic(client):
    topic_id = make_topic(client, "Study notes", course="Test")["id"]
    for title, text in NOTES.items():
        _ingest(client, topic_id, title, text)
    return topic_id


def _top_scores(client, db_session, topic_id, questions):
    return {
        q: retrieve_relevant_chunks(
            db_session, q, user_id=client.user_id, topic_id=topic_id, top_k=1
        )[0]["similarity_score"]
        for q in questions
    }


def test_no_off_topic_question_clears_the_threshold(client, db_session, corpus_topic):
    scores = _top_scores(client, db_session, corpus_topic, OFF_TOPIC)
    accepted = {q: round(s, 3) for q, s in scores.items() if s >= RETRIEVAL_RELEVANCE_THRESHOLD}
    assert not accepted, f"off-topic questions that would be answered: {accepted}"


def test_off_topic_questions_keep_a_margin_below_the_threshold(client, db_session, corpus_topic):
    scores = _top_scores(client, db_session, corpus_topic, OFF_TOPIC)
    assert max(scores.values()) <= RETRIEVAL_RELEVANCE_THRESHOLD - 0.03


def test_nearly_all_on_topic_questions_clear_the_threshold(client, db_session, corpus_topic):
    scores = _top_scores(client, db_session, corpus_topic, ON_TOPIC)
    refused = {q: round(s, 3) for q, s in scores.items() if s < RETRIEVAL_RELEVANCE_THRESHOLD}
    # Short keyword queries and paraphrases score lowest; they are a known cost of
    # a threshold that has to keep adjacent-topic questions out.
    assert len(refused) <= 0.15 * len(ON_TOPIC), f"on-topic questions that would be refused: {refused}"


def test_a_question_about_the_end_of_a_long_passage_is_found(client, db_session, corpus_topic):
    """Under the old 2600-character chunks the last part of each chunk was past the
    embedder's 256-token cut-off, and this query scored 0.01."""
    matches = _top_scores(client, db_session, corpus_topic, ["load factor 0.75"])
    assert matches["load factor 0.75"] > 0.2


# --- the full gate: similarity OR a strict keyword match ---------------------------------------------------
#
# With hybrid search the tutor accepts a chunk when its cosine similarity clears the
# threshold OR it contains every searchable word of the question. Measured on this
# corpus: 27 of 28 on-topic questions are accepted (25 on similarity alone) and none
# of the 16 off-topic ones, none of which has a keyword match at all.

from app.services.tutor_service import is_relevant  # noqa: E402


def _accepted(client, db_session, topic_id, questions):
    accepted = {}
    for q in questions:
        matches = retrieve_relevant_chunks(db_session, q, user_id=client.user_id, topic_id=topic_id, top_k=5)
        accepted[q] = any(
            is_relevant({"similarity": m["similarity_score"], "keyword_match": m["keyword_match"]}) for m in matches
        )
    return accepted


def test_the_full_gate_accepts_no_off_topic_question(client, db_session, corpus_topic):
    accepted = _accepted(client, db_session, corpus_topic, OFF_TOPIC)
    assert not any(accepted.values()), [q for q, ok in accepted.items() if ok]


def test_the_full_gate_accepts_nearly_every_on_topic_question(client, db_session, corpus_topic):
    accepted = _accepted(client, db_session, corpus_topic, ON_TOPIC)
    refused = [q for q, ok in accepted.items() if not ok]
    assert len(refused) <= 0.1 * len(ON_TOPIC), refused


def test_keyword_matching_rescues_questions_that_similarity_alone_refused(client, db_session, corpus_topic):
    by_similarity = {
        q: retrieve_relevant_chunks(db_session, q, user_id=client.user_id, topic_id=corpus_topic, top_k=1)[0]["similarity_score"]
        >= RETRIEVAL_RELEVANCE_THRESHOLD
        for q in ON_TOPIC
    }
    full = _accepted(client, db_session, corpus_topic, ON_TOPIC)
    assert sum(full.values()) > sum(by_similarity.values())
    assert all(full[q] for q, ok in by_similarity.items() if ok)  # nothing accepted before is lost
