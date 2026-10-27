"""Sources shared with a module: used by every topic of that module (tutor, keyword
search, quizzes), never by topics of other modules. The model is replaced; embeddings
are real."""

import sqlite3

import pytest

from app import models
from app.services import fts, quiz_jobs
from helpers import make_topic
from test_course_fallback import HASH, Q_HASH, ask, prompts  # noqa: F401 (fixture)
from test_hybrid_search import add_chunks
from test_migration_0005 import _alembic, _rows
from test_quiz_api import fake_llm, one  # noqa: F401 (fixture)


@pytest.fixture()
def module(client, db_session):
    """Hashing and Probing share module M1; Sorting is in M2. Hashing holds notes shared with M1."""
    hashing = make_topic(client, "Hashing", course="CS", module="M1")
    probing = make_topic(client, "Probing", course="CS", module="M1")
    sorting = make_topic(client, "Sorting", course="CS", module="M2")
    chunks = add_chunks(db_session, hashing["id"], HASH, title="Module notes", page=2)
    chunks[0].source.shared_with_module = True
    db_session.commit()
    return hashing, probing, sorting


def test_a_sibling_topic_answers_from_the_shared_notes_as_its_own(client, module, prompts):
    _, probing, _ = module
    body = ask(client, probing, Q_HASH).json()
    assert body["grounded"] is True
    assert body["sources"][0]["source"] == "Module notes" and body["sources"][0]["page"] == 2
    assert body["sources"][0].get("topic") is None  # the topic's own material, not the course fallback
    assert "OTHER topics of the same course" not in prompts[0]


def test_a_topic_of_another_module_only_reaches_them_through_the_course_fallback(client, module, prompts):
    _, _, sorting = module
    body = ask(client, sorting, Q_HASH).json()
    assert body["sources"][0]["topic"] == "Hashing"
    assert "OTHER topics of the same course" in prompts[0]


def test_unshared_notes_stay_with_their_topic(client, db_session, prompts):
    hashing = make_topic(client, "Hashing", course="CS", module="M1")
    probing = make_topic(client, "Probing", course="CS", module="M1")
    add_chunks(db_session, hashing["id"], HASH, title="Hashing notes")
    body = ask(client, probing, Q_HASH).json()
    assert body["sources"][0]["topic"] == "Hashing"  # found only by the course fallback


def test_keyword_search_has_the_same_scope(db_session, module):
    hashing, probing, sorting = module
    user_id = db_session.query(models.User.id).scalar()
    shared = {c.id for c in db_session.query(models.Chunk).filter_by(topic_id=hashing["id"])}
    assert set(fts.search(db_session, '"collisions"', user_id, topic_id=probing["id"])) <= shared
    assert fts.search(db_session, '"collisions"', user_id, topic_id=probing["id"])
    assert fts.search(db_session, '"collisions"', user_id, topic_id=sorting["id"]) == []


def test_a_sibling_topic_can_have_a_quiz_written_from_the_shared_notes(client, module, fake_llm, monkeypatch):
    _, probing, sorting = module
    monkeypatch.setattr(quiz_jobs, "spawn", lambda job_id: quiz_jobs.run_job(job_id))
    assert client.get(f"/quiz/{probing['id']}").json()["has_material"] is True
    assert client.get(f"/quiz/{sorting['id']}").json()["has_material"] is False
    llm = fake_llm(one(1))
    job = client.post(f"/quiz/{probing['id']}/generate", params={"count": 1}).json()
    assert client.get(f"/quiz/jobs/{job['id']}").json()["status"] == "succeeded"
    assert "hash function" in llm.calls[0]["user"]


def test_uploading_with_the_flag_shares_it_and_every_topic_of_the_module_lists_it(client):
    hashing = make_topic(client, "Hashing", course="CS", module="M1")
    probing = make_topic(client, "Probing", course="CS", module="M1")
    sorting = make_topic(client, "Sorting", course="CS", module="M2")
    made = client.post("/sources/text", json={
        "topic_id": hashing["id"], "source_type": "official_upload", "title": "Module notes",
        "text": " ".join(HASH), "shared_with_module": True,
    }).json()
    assert made["shared_with_module"] is True and made["topic_id"] == hashing["id"]
    listed = lambda t: [s["id"] for s in client.get(f"/sources/topic/{t['id']}").json()]
    assert listed(hashing) == [made["id"]] and listed(probing) == [made["id"]]
    assert listed(sorting) == []


def test_sources_are_not_shared_unless_asked(client):
    hashing = make_topic(client, "Hashing", course="CS", module="M1")
    probing = make_topic(client, "Probing", course="CS", module="M1")
    made = client.post("/sources/text", json={
        "topic_id": hashing["id"], "source_type": "official_upload", "title": "Notes", "text": " ".join(HASH),
    }).json()
    assert made["shared_with_module"] is False
    assert client.get(f"/sources/topic/{probing['id']}").json() == []


def test_migration_0012_leaves_existing_sources_unshared_and_rolls_back(tmp_path):
    db = tmp_path / "pre0012.db"
    _alembic(db, "upgrade", "0011")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@example.com', 'x')")
    con.execute("INSERT INTO courses (id, user_id, name) VALUES (1, 1, 'CS')")
    con.execute("INSERT INTO modules (id, course_id, name, position) VALUES (1, 1, 'M', 0)")
    con.execute("INSERT INTO topics (id, user_id, module_id, name, position) VALUES (1, 1, 1, 'T', 0)")
    con.execute("INSERT INTO sources (id, topic_id, source_type, title) VALUES (1, 1, 'self_supplied', 'Old notes')")
    con.commit()
    con.close()
    _alembic(db, "upgrade", "head")
    assert _rows(db, "SELECT id, title, shared_with_module FROM sources") == [(1, "Old notes", 0)]
    _alembic(db, "downgrade", "0011")
    assert "shared_with_module" not in [r[1] for r in _rows(db, "PRAGMA table_info(sources)")]
    assert _rows(db, "SELECT id, title FROM sources") == [(1, "Old notes")]
