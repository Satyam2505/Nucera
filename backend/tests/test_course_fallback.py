"""When a topic's own material has nothing relevant, the tutor looks at the rest of
the same course before giving up. The model is replaced; embeddings are real."""

import json

import pytest

from app import models
from app.services import llm_service
from app.services.tutor_service import INSUFFICIENT_MATERIAL_MESSAGE
from helpers import make_topic
from test_hybrid_search import add_chunks

HASH = ["A hash table maps keys to values using a hash function to compute a bucket index.",
        "Collisions are resolved with chaining or open addressing in a hash table."]
SORT = ["Merge sort splits a list in half, sorts each half and merges the sorted halves.",
        "Quicksort partitions the list around a pivot element and sorts each part."]
Q_HASH = "How does a hash table resolve collisions?"


@pytest.fixture()
def prompts(monkeypatch):
    seen = []
    monkeypatch.setattr(
        llm_service,
        "generate",
        lambda system, user, model=None, **k: seen.append(user) or llm_service.LLMResult(ok=True, text="An answer."),
    )
    return seen


@pytest.fixture()
def course(client, db_session):
    """Two topics of one course: Sorting (merge sort / quicksort notes) and an empty Hashing."""
    sorting = make_topic(client, "Sorting", course="CS", module="M1")
    hashing = make_topic(client, "Hashing", course="CS", module="M2")
    add_chunks(db_session, sorting["id"], SORT, title="Sorting notes", page=3)
    return sorting, hashing


def ask(client, topic, question):
    return client.post("/ask", json={"query": question, "topic_id": topic["id"]})


def test_a_question_the_topic_cannot_answer_is_answered_from_another_topic_of_the_course(client, db_session, prompts):
    sorting = make_topic(client, "Sorting", course="CS", module="M1")
    hashing = make_topic(client, "Hashing", course="CS", module="M2")
    add_chunks(db_session, sorting["id"], SORT, title="Sorting notes")
    add_chunks(db_session, hashing["id"], HASH, title="Hash notes", page=7)

    body = ask(client, sorting, Q_HASH).json()  # asked in the Sorting topic

    assert body["grounded"] is True
    assert body["sources"] and all(s["topic"] == "Hashing" for s in body["sources"])
    assert body["sources"][0]["source"] == "Hash notes" and body["sources"][0]["page"] == 7
    prompt = prompts[0]
    assert "OTHER topics of the same course" in prompt
    assert "from topic: Hashing" in prompt and "hash function" in prompt
    assert "Merge sort" not in prompt  # this topic's irrelevant chunks are not mixed in


def test_a_topic_with_no_material_at_all_still_gets_help_from_the_course(client, db_session, prompts):
    sorting = make_topic(client, "Sorting", course="CS", module="M1")
    empty = make_topic(client, "Scratch", course="CS", module="M2")
    add_chunks(db_session, sorting["id"], SORT, title="Sorting notes")
    body = ask(client, empty, "How does merge sort work?").json()
    assert body["grounded"] is True and body["sources"][0]["topic"] == "Sorting"


def test_when_the_topic_has_its_own_answer_the_course_is_not_searched(client, db_session, prompts):
    sorting = make_topic(client, "Sorting", course="CS", module="M1")
    hashing = make_topic(client, "Hashing", course="CS", module="M2")
    add_chunks(db_session, sorting["id"], SORT, title="Sorting notes")
    add_chunks(db_session, hashing["id"], HASH, title="Hash notes")

    body = ask(client, hashing, Q_HASH).json()

    assert body["grounded"] is True
    assert all(s["topic"] is None for s in body["sources"])  # citations carry no topic for the topic's own material
    assert "OTHER topics" not in prompts[0] and "Merge sort" not in prompts[0]


def test_nothing_relevant_anywhere_is_still_a_refusal_and_never_calls_the_model(client, db_session, prompts):
    sorting = make_topic(client, "Sorting", course="CS", module="M1")
    hashing = make_topic(client, "Hashing", course="CS", module="M2")
    add_chunks(db_session, sorting["id"], SORT)
    add_chunks(db_session, hashing["id"], HASH)
    body = ask(client, sorting, "What ingredients go into a chocolate cake?").json()
    assert body["grounded"] is False and body["answer"] == INSUFFICIENT_MATERIAL_MESSAGE and body["sources"] == []
    assert prompts == []


def test_other_courses_of_the_same_user_are_never_searched(client, db_session, prompts):
    here = make_topic(client, "Sorting", course="CS", module="M1")
    elsewhere = make_topic(client, "Hashing", course="OtherCourse", module="M1")
    add_chunks(db_session, here["id"], SORT)
    add_chunks(db_session, elsewhere["id"], HASH, title="Hash notes")
    body = ask(client, here, Q_HASH).json()
    assert body["grounded"] is False and prompts == []


def test_other_users_courses_are_never_searched(client, other_client, db_session, prompts):
    mine = make_topic(client, "Sorting", course="CS", module="M1")
    theirs = make_topic(other_client, "Hashing", course="CS", module="M1")
    add_chunks(db_session, mine["id"], SORT)
    add_chunks(db_session, theirs["id"], HASH, title="Their notes")
    body = ask(client, mine, Q_HASH).json()
    assert body["grounded"] is False and prompts == []


def test_a_keyword_match_in_another_topic_counts_too(client, db_session, prompts):
    sorting = make_topic(client, "Sorting", course="CS", module="M1")
    other = make_topic(client, "Other", course="CS", module="M2")
    add_chunks(db_session, sorting["id"], SORT)
    add_chunks(db_session, other["id"], ["Deleting leaves a tombstone so probe sequences stay intact."], title="Probing")
    body = ask(client, sorting, "tombstone").json()
    assert body["grounded"] is True and body["sources"][0]["topic"] == "Other"


def test_fallback_citations_are_saved_with_the_conversation(client, db_session, prompts):
    sorting = make_topic(client, "Sorting", course="CS", module="M1")
    hashing = make_topic(client, "Hashing", course="CS", module="M2")
    add_chunks(db_session, sorting["id"], SORT)
    add_chunks(db_session, hashing["id"], HASH, title="Hash notes")
    ask(client, sorting, Q_HASH)
    saved = client.get(f"/chat/{sorting['id']}").json()[1]
    assert saved["sources"][0]["topic"] == "Hashing" and saved["sources"][0]["source"] == "Hash notes"


def test_the_streaming_route_falls_back_the_same_way(client, db_session, monkeypatch):
    sorting = make_topic(client, "Sorting", course="CS", module="M1")
    hashing = make_topic(client, "Hashing", course="CS", module="M2")
    add_chunks(db_session, sorting["id"], SORT)
    add_chunks(db_session, hashing["id"], HASH, title="Hash notes")

    def fake_stream(system, user, model=None, **kwargs):
        assert "from topic: Hashing" in user
        yield "token", "Streamed."
        yield "end", llm_service.LLMResult(ok=True, text="Streamed.")

    monkeypatch.setattr(llm_service, "generate_stream", fake_stream)
    resp = client.post("/ask/stream", json={"query": Q_HASH, "topic_id": sorting["id"]})
    done = [json.loads(line) for line in resp.text.splitlines() if line.strip()][-1]
    assert done["type"] == "done" and done["sources"][0]["topic"] == "Hashing"


def test_the_fallback_cites_only_what_the_model_was_shown(client, db_session, prompts):
    sorting = make_topic(client, "Sorting", course="CS", module="M1")
    hashing = make_topic(client, "Hashing", course="CS", module="M2")
    add_chunks(db_session, sorting["id"], SORT)
    add_chunks(db_session, hashing["id"], HASH, title="Hash notes")
    body = ask(client, sorting, Q_HASH).json()
    for source in body["sources"]:
        assert source["topic"] == "Hashing"  # never a Sorting chunk
    assert db_session.query(models.Chunk).count() == 4
