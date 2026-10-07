"""Keyword (FTS5) search beside the vectors: the query builder, the index and its
triggers, rank fusion, hybrid retrieval, and the tutor accepting a strict keyword
match as relevance. The real embedding model is used (no LLM)."""

import pytest
from sqlalchemy import text

from app import models
from app.config import HYBRID_RRF_K, RETRIEVAL_RELEVANCE_THRESHOLD
from app.services import fts, llm_service
from app.services.embedding_service import EMBEDDING_DIM, embed_texts
from app.services.retrieval_service import reciprocal_rank_fusion, retrieve_relevant_chunks
from app.services.tutor_service import is_relevant, prepare_tutor_answer
from helpers import make_topic


# --- the query builder ------------------------------------------------------------------------


def test_query_terms_drop_stopwords_and_punctuation_and_keep_order():
    assert fts.query_terms("What is the load factor of a hash table?") == ["load", "factor", "hash", "table"]


def test_query_terms_are_lower_cased_and_de_duplicated():
    assert fts.query_terms("Hash HASH hash Table") == ["hash", "table"]


def test_acronyms_and_numbers_survive():
    assert fts.query_terms("Explain 3NF and BCNF") == ["3nf", "bcnf"]
    assert fts.query_terms("quicksort in 2 steps") == ["quicksort", "2", "steps"]


def test_a_question_of_only_stopwords_has_no_terms():
    assert fts.query_terms("What is it?") == []
    assert fts.match_expressions([]) == (None, None)


def test_terms_are_capped():
    assert len(fts.query_terms(" ".join(f"word{i}" for i in range(50)))) == fts.MAX_TERMS


def test_expressions_quote_every_term_so_none_can_be_fts_syntax():
    strict, loose = fts.match_expressions(["load", "factor"])
    assert strict == '"load" AND "factor"' and loose == '"load" OR "factor"'
    # Words that are FTS5 operators or NEAR/column syntax are only ever quoted words.
    assert fts.match_expressions(fts.query_terms("tell me about NEAR or AND not"))[1] == '"near"'


@pytest.mark.parametrize("hostile", ['x" OR "1"="1', "col:thing", "a* b^ (c)", '"unbalanced', "-minus +plus", "'; DROP TABLE chunks; --"])
def test_hostile_questions_never_break_the_keyword_search(client, db_session, hostile):
    topic = make_topic(client, "T", course="C")["id"]
    add_chunks(db_session, topic, ["A hash table maps keys to values."])
    strict, loose = fts.match_expressions(fts.query_terms(hostile))
    if loose:
        fts.search(db_session, loose, user_id=client.user_id, topic_id=topic)  # must not raise
    retrieve_relevant_chunks(db_session, hostile, user_id=client.user_id, topic_id=topic)
    assert db_session.query(models.Chunk).count() == 1


# --- helpers ----------------------------------------------------------------------------------------


def add_chunks(db, topic_id, texts, title="Notes", page=None):
    """Chunks with real embeddings, so vector search works too."""
    source = models.Source(
        topic_id=topic_id, source_type=models.SourceType.self_supplied, title=title, raw_text=" ".join(texts)
    )
    db.add(source)
    db.flush()
    vectors = embed_texts(texts)
    chunks = []
    for index, (body, vector) in enumerate(zip(texts, vectors)):
        chunk = models.Chunk(
            source_id=source.id, topic_id=topic_id, chunk_text=body, chunk_index=index, page_number=page, embedding=vector
        )
        db.add(chunk)
        chunks.append(chunk)
    db.commit()
    return chunks


def fts_rows(db, term):
    return [r[0] for r in db.execute(text("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH :t ORDER BY rowid"), {"t": term})]


# --- the index and its triggers --------------------------------------------------------------------------


def test_a_new_chunk_is_searchable_at_once(client, db_session):
    topic = make_topic(client, "T", course="C")["id"]
    (chunk,) = add_chunks(db_session, topic, ["Tombstones mark deleted slots in open addressing."])
    assert fts_rows(db_session, '"tombstone"') == [chunk.id]  # the porter stemmer matches "Tombstones"


def test_deleting_chunks_removes_them_from_the_index_even_in_bulk(client, db_session):
    topic = make_topic(client, "T", course="C")["id"]
    first, second = add_chunks(db_session, topic, ["Alpha unique1 text.", "Beta unique2 text."])
    db_session.query(models.Chunk).filter(models.Chunk.id == first.id).delete(synchronize_session=False)
    db_session.commit()
    assert fts_rows(db_session, "unique1") == [] and fts_rows(db_session, "unique2") == [second.id]
    db_session.query(models.Chunk).delete(synchronize_session=False)  # what re-indexing does
    db_session.commit()
    assert fts_rows(db_session, "unique2") == []


def test_editing_a_chunks_text_updates_the_index(client, db_session):
    topic = make_topic(client, "T", course="C")["id"]
    (chunk,) = add_chunks(db_session, topic, ["The word zebrafish appears here."])
    chunk.chunk_text = "The word platypus appears here."
    db_session.commit()
    assert fts_rows(db_session, "zebrafish") == [] and fts_rows(db_session, "platypus") == [chunk.id]


def test_deleting_a_source_or_topic_clears_its_chunks_from_the_index(client, db_session):
    topic = make_topic(client, "T", course="C")["id"]
    add_chunks(db_session, topic, ["Findable sentinelword here."])
    assert fts_rows(db_session, "sentinelword")
    client.delete(f"/topics/{topic}")
    db_session.expire_all()
    assert fts_rows(db_session, "sentinelword") == []


def test_ensure_fts_is_idempotent_and_backfills_an_existing_database(client, db_session):
    from app.database import engine

    topic = make_topic(client, "T", course="C")["id"]
    (chunk,) = add_chunks(db_session, topic, ["Backfilled needleword text."])
    with engine.begin() as connection:  # simulate a database that predates the index
        for name in ("chunks_fts_ai", "chunks_fts_ad", "chunks_fts_au"):
            connection.execute(text(f"DROP TRIGGER {name}"))
        connection.execute(text("DROP TABLE chunks_fts"))
    assert fts.ensure_fts(engine) is True
    assert fts_rows(db_session, "needleword") == [chunk.id]  # filled from the chunks that were already there
    assert fts.ensure_fts(engine) is True  # a second call changes nothing
    assert fts_rows(db_session, "needleword") == [chunk.id]


def test_the_keyword_search_only_sees_the_callers_own_chunks(client, other_client, db_session):
    mine = make_topic(client, "Mine", course="C")["id"]
    theirs = make_topic(other_client, "Theirs", course="C")["id"]
    (mine_chunk,) = add_chunks(db_session, mine, ["Shared secretword content."])
    add_chunks(db_session, theirs, ["Their secretword content."])
    ids = fts.search(db_session, '"secretword"', user_id=client.user_id)
    assert ids == [mine_chunk.id]


def test_the_keyword_search_respects_topic_course_and_source_scopes(client, db_session):
    one = make_topic(client, "One", course="C")
    two = make_topic(client, "Two", course="C")
    other_course = make_topic(client, "Three", course="D")
    (a,) = add_chunks(db_session, one["id"], ["scopeword in topic one."])
    (b,) = add_chunks(db_session, two["id"], ["scopeword in topic two."])
    (c,) = add_chunks(db_session, other_course["id"], ["scopeword in another course."])
    uid = client.user_id
    assert set(fts.search(db_session, '"scopeword"', uid)) == {a.id, b.id, c.id}
    assert fts.search(db_session, '"scopeword"', uid, topic_id=two["id"]) == [b.id]
    assert set(fts.search(db_session, '"scopeword"', uid, course_id=one["course_id"])) == {a.id, b.id}
    assert fts.search(db_session, '"scopeword"', uid, source_ids=[c.source_id]) == [c.id]


def test_a_bad_expression_costs_only_the_keyword_half(client, db_session):
    topic = make_topic(client, "T", course="C")["id"]
    add_chunks(db_session, topic, ["Some text."])
    assert fts.search(db_session, '"unclosed', user_id=client.user_id) == []
    assert db_session.query(models.Chunk).count() == 1  # the session still works


def test_keyword_search_is_unavailable_off_sqlite():
    from sqlalchemy import create_engine

    assert fts.ensure_fts(create_engine("postgresql+psycopg2://u:p@localhost/none")) is False


# --- rank fusion ------------------------------------------------------------------------------------------------


def test_fusion_adds_reciprocal_ranks():
    scores = reciprocal_rank_fusion([[1, 2, 3], [3, 1]], k=60)
    assert scores[1] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[2] == pytest.approx(1 / 62)
    assert scores[3] == pytest.approx(1 / 63 + 1 / 61)


def test_a_chunk_high_in_both_rankings_beats_one_first_in_only_one():
    scores = reciprocal_rank_fusion([[10, 20, 30], [30, 20, 99]], k=60)
    assert scores[20] > scores[10] and scores[20] > scores[99]


def test_fusion_of_one_ranking_keeps_its_order_and_of_none_is_empty():
    scores = reciprocal_rank_fusion([[5, 6, 7]])
    assert sorted(scores, key=lambda i: -scores[i]) == [5, 6, 7]
    assert reciprocal_rank_fusion([]) == {} and reciprocal_rank_fusion([[]]) == {}


def test_the_default_constant_is_the_usual_one():
    assert HYBRID_RRF_K == 60


# --- hybrid retrieval ----------------------------------------------------------------------------------------------

NOTES = [
    "A hash table maps keys to values using a hash function to compute a bucket index.",
    "Collisions are resolved with chaining or open addressing in a hash table.",
    "Third normal form (3NF) removes transitive dependencies between non-key columns.",
    "Merge sort splits a list in half, sorts each half and merges the sorted halves.",
    "Deleting from an open-addressed table leaves a tombstone so probe sequences stay intact.",
]


@pytest.fixture()
def topic_with_notes(client, db_session):
    topic = make_topic(client, "Mixed", course="C")["id"]
    chunks = add_chunks(db_session, topic, NOTES)
    return topic, {i: c for i, c in enumerate(chunks)}


def retrieve(client, db_session, topic, question, **kwargs):
    return retrieve_relevant_chunks(db_session, question, user_id=client.user_id, topic_id=topic, **kwargs)


def test_results_carry_cosine_similarity_a_keyword_flag_and_a_rank(client, db_session, topic_with_notes):
    topic, chunks = topic_with_notes
    results = retrieve(client, db_session, topic, "What is 3NF?")
    assert [r["rank"] for r in results] == [1, 2, 3, 4, 5]
    top = results[0]
    assert top["chunk"].id == chunks[2].id and top["keyword_match"] is True
    assert all(isinstance(r["similarity_score"], float) for r in results)
    assert [r["keyword_match"] for r in results[1:]] == [False] * 4


def test_a_bare_rare_word_is_found_by_keyword_though_its_cosine_is_under_the_threshold(client, db_session, topic_with_notes):
    """The vector ranking already puts the right chunk first for "tombstone", but a
    single rare word is a weak embedding query: its cosine similarity (~0.27) is below
    the relevance threshold, so on similarity alone the tutor would refuse. The strict
    keyword match is the certain signal that rescues it."""
    topic, chunks = topic_with_notes
    (top, *_rest) = retrieve(client, db_session, topic, "tombstone", hybrid=True)
    assert top["chunk"].id == chunks[4].id
    assert top["similarity_score"] < RETRIEVAL_RELEVANCE_THRESHOLD
    assert top["keyword_match"] is True and is_relevant({"similarity": top["similarity_score"], "keyword_match": True})
    vectors_only = retrieve(client, db_session, topic, "tombstone", hybrid=False)
    assert vectors_only[0]["keyword_match"] is False
    assert not is_relevant({"similarity": vectors_only[0]["similarity_score"], "keyword_match": vectors_only[0]["keyword_match"]})


def test_without_a_keyword_signal_hybrid_equals_the_vector_ranking(client, db_session, topic_with_notes):
    topic, _ = topic_with_notes
    question = "What ingredients go into a chocolate cake?"
    hybrid = retrieve(client, db_session, topic, question, hybrid=True)
    vectors_only = retrieve(client, db_session, topic, question, hybrid=False)
    assert [r["chunk"].id for r in hybrid] == [r["chunk"].id for r in vectors_only]
    assert not any(r["keyword_match"] for r in hybrid)


def test_hybrid_can_be_switched_off(client, db_session, topic_with_notes):
    topic, _ = topic_with_notes
    results = retrieve(client, db_session, topic, "3NF", hybrid=False)
    assert not any(r["keyword_match"] for r in results)


def test_keyword_match_needs_every_term_not_just_one(client, db_session, topic_with_notes):
    topic, chunks = topic_with_notes
    results = {r["chunk"].id: r for r in retrieve(client, db_session, topic, "hash table collisions")}
    assert results[chunks[1].id]["keyword_match"] is True  # has hash, table and collisions
    assert results[chunks[0].id]["keyword_match"] is False  # has hash and table, not collisions


def test_a_question_with_no_searchable_words_still_gets_vector_results(client, db_session, topic_with_notes):
    topic, _ = topic_with_notes
    results = retrieve(client, db_session, topic, "What is it?")
    assert len(results) == 5 and not any(r["keyword_match"] for r in results)


def test_top_k_and_empty_scopes(client, db_session, topic_with_notes):
    topic, _ = topic_with_notes
    assert len(retrieve(client, db_session, topic, "hash", top_k=2)) == 2
    empty = make_topic(client, "Empty", course="C")["id"]
    assert retrieve(client, db_session, empty, "hash") == []


def test_hybrid_retrieval_stays_inside_the_callers_courses(client, other_client, db_session):
    mine = make_topic(client, "Mine", course="C")["id"]
    theirs = make_topic(other_client, "Theirs", course="C")["id"]
    add_chunks(db_session, mine, ["My notes mention quokka."])
    add_chunks(db_session, theirs, ["Their notes mention quokka."])
    results = retrieve_relevant_chunks(db_session, "quokka", user_id=client.user_id)
    assert [r["chunk"].topic_id for r in results] == [mine]


def test_the_retrieve_endpoint_reports_the_keyword_flag(client, db_session, topic_with_notes):
    topic, _ = topic_with_notes
    body = client.post("/retrieve", json={"question": "3NF", "topic_id": topic, "top_k": 2}).json()
    assert body["results"][0]["keyword_match"] is True and "3NF" in body["results"][0]["chunk_text"]


# --- the tutor's relevance gate -----------------------------------------------------------------------------------------


def test_a_strict_keyword_match_counts_as_relevant_even_with_low_similarity():
    low = RETRIEVAL_RELEVANCE_THRESHOLD - 0.2
    assert is_relevant({"similarity": low, "keyword_match": True}) is True
    assert is_relevant({"similarity": low, "keyword_match": False}) is False
    assert is_relevant({"similarity": low}) is False
    assert is_relevant({"similarity": RETRIEVAL_RELEVANCE_THRESHOLD}) is True


def test_the_tutor_answers_from_a_keyword_match_the_vectors_would_have_refused(monkeypatch):
    low = RETRIEVAL_RELEVANCE_THRESHOLD - 0.2
    prepared = prepare_tutor_answer(
        "What is a tombstone?",
        [{"source": "N.pdf", "page": 2, "text": "A tombstone marks a deleted slot.", "similarity": low, "keyword_match": True}],
        "T",
        50,
        [],
    )
    assert prepared.immediate is None and prepared.sources == [{"source": "N.pdf", "page": 2}]
    refused = prepare_tutor_answer(
        "What is a tombstone?",
        [{"source": "N.pdf", "page": 2, "text": "x", "similarity": low, "keyword_match": False}],
        "T",
        50,
        [],
    )
    assert refused.immediate is not None and refused.immediate.grounded is False


def test_relevant_chunks_keep_the_retrievals_merged_order():
    chunks = [
        {"source": "Low.pdf", "page": 1, "text": "a", "similarity": 0.4, "rank": 1},
        {"source": "High.pdf", "page": 1, "text": "b", "similarity": 0.9, "rank": 2},
    ]
    prepared = prepare_tutor_answer("Q?", chunks, "T", 50, [])
    assert [s["source"] for s in prepared.sources] == ["Low.pdf", "High.pdf"]


def test_asking_about_an_acronym_end_to_end(client, db_session, monkeypatch):
    prompts = []
    monkeypatch.setattr(
        llm_service, "generate", lambda system, user, model=None, **k: prompts.append(user) or llm_service.LLMResult(ok=True, text="ok")
    )
    topic = make_topic(client, "Databases", course="C")["id"]
    add_chunks(db_session, topic, NOTES, title="DB notes")
    body = client.post("/ask", json={"query": "What is 3NF?", "topic_id": topic}).json()
    assert body["grounded"] is True
    assert "transitive dependencies" in prompts[0]
    assert body["sources"][0]["source"] == "DB notes"


def test_embedding_dimension_assumption_holds():
    assert len(embed_texts(["x"])[0]) == EMBEDDING_DIM


def test_reindexing_keeps_the_keyword_index_in_step(client, db_session):
    """Re-indexing deletes and re-inserts every chunk of a source in bulk; the triggers
    must leave the keyword index matching the new chunks, not the old ones."""
    from app.services.reindex_service import reindex_source

    topic = make_topic(client, "T", course="C")["id"]
    body = " ".join(f"Sentence number {i} discusses the zebrafish genome in detail." for i in range(60))
    source = models.Source(topic_id=topic, source_type=models.SourceType.self_supplied, title="Long", raw_text=body)
    db_session.add(source)
    db_session.flush()
    db_session.add(models.Chunk(source_id=source.id, topic_id=topic, chunk_text=body, chunk_index=0, embedding=embed_texts([body])[0]))
    db_session.commit()
    assert len(fts_rows(db_session, "zebrafish")) == 1

    assert reindex_source(db_session, source, force=True).status == "reindexed"
    db_session.expire_all()
    new_ids = [c.id for c in db_session.query(models.Chunk).filter(models.Chunk.source_id == source.id)]
    assert len(new_ids) > 1
    assert fts_rows(db_session, "zebrafish") == sorted(new_ids)
