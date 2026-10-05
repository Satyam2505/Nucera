"""Auth and ownership on the ingestion, mastery, quiz, tutor and retrieval routes.

One table drives every route: without a token it is a 401, and for another
user's ids it is a 404 that changes nothing. List-style routes are checked
separately for what they return.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app import models
from app.services import graph_service
from app.services.embedding_service import EMBEDDING_DIM
from helpers import make_topic

# (id, method, path(world), request kwargs(world)). `world` holds user A's ids.
ROUTES = [
    (
        "ingest-text",
        "post",
        lambda w: "/sources/text",
        lambda w: {
            "json": {
                "topic_id": w["topic"],
                "source_type": "self_supplied",
                "title": "x",
                "text": "some notes",
            }
        },
    ),
    (
        "ingest-upload",
        "post",
        lambda w: "/sources/upload",
        lambda w: {
            "data": {"topic_id": w["topic"], "source_type": "self_supplied"},
            "files": {"file": ("notes.txt", b"hello there", "text/plain")},
        },
    ),
    ("list-sources", "get", lambda w: f"/sources/topic/{w['topic']}", lambda w: {}),
    ("delete-source", "delete", lambda w: f"/sources/{w['source']}", lambda w: {}),
    ("get-mastery", "get", lambda w: f"/mastery/{w['topic']}", lambda w: {}),
    ("put-mastery", "put", lambda w: f"/mastery/{w['topic']}", lambda w: {"json": {"score": 99}}),
    (
        "toggle-revision",
        "post",
        lambda w: f"/mastery/{w['topic']}/toggle-revision",
        lambda w: {},
    ),
    ("mark-missed", "post", lambda w: f"/mastery/{w['topic']}/missed", lambda w: {}),
    (
        "record-session",
        "post",
        lambda w: "/sessions",
        lambda w: {"json": {"topic_id": w["topic"], "type": "self_report", "score_delta": 50}},
    ),
    ("get-quiz", "get", lambda w: f"/quiz/{w['topic']}", lambda w: {}),
    (
        "submit-quiz",
        "post",
        lambda w: "/quiz/submit",
        lambda w: {"json": {"topic_id": w["topic"], "answers": []}},
    ),
    (
        "ask",
        "post",
        lambda w: "/ask",
        lambda w: {"json": {"query": "anything", "topic_id": w["topic"]}},
    ),
    (
        "retrieve-topic",
        "post",
        lambda w: "/retrieve",
        lambda w: {"json": {"question": "anything", "topic_id": w["topic"]}},
    ),
]
# Routes with no id in them: nothing to 404, only auth to require.
LIST_ROUTES = [
    ("list-mastery", "get", lambda w: "/mastery", lambda w: {}),
    (
        "retrieve-all",
        "post",
        lambda w: "/retrieve",
        lambda w: {"json": {"question": "anything"}},
    ),
]


def _params(routes):
    return [pytest.param(*route, id=route[0]) for route in routes]


@pytest.fixture()
def world(client, db_session):
    """User A's topic with a source, one chunk, and non-default mastery."""
    topic = make_topic(client, "Secret topic", course="A's course")
    source = models.Source(
        topic_id=topic["id"],
        source_type=models.SourceType.self_supplied,
        title="A's notes",
        raw_text="private",
    )
    db_session.add(source)
    db_session.flush()
    chunk = models.Chunk(
        source_id=source.id,
        topic_id=topic["id"],
        chunk_text="private",
        chunk_index=0,
        embedding=[1.0] + [0.0] * (EMBEDDING_DIM - 1),
    )
    db_session.add(chunk)
    db_session.commit()
    mastery = client.put(f"/mastery/{topic['id']}", json={"score": 50}).json()
    return {
        "topic": topic["id"],
        "source": source.id,
        "chunk": chunk.id,
        "status": mastery["status"],
    }


def _send(c, method, path, kwargs):
    return getattr(c, method)(path, **kwargs)


@pytest.mark.parametrize("name,method,path,kwargs", _params(ROUTES + LIST_ROUTES))
def test_every_route_requires_a_token(world, name, method, path, kwargs):
    from app.main import app

    bare = TestClient(app)
    assert _send(bare, method, path(world), kwargs(world)).status_code == 401

    bad = TestClient(app, headers={"Authorization": "Bearer not-a-real-token"})
    assert _send(bad, method, path(world), kwargs(world)).status_code == 401


@pytest.mark.parametrize("name,method,path,kwargs", _params(ROUTES))
def test_other_users_ids_are_404(world, other_client, name, method, path, kwargs):
    resp = _send(other_client, method, path(world), kwargs(world))
    assert resp.status_code == 404, f"{name}: {resp.status_code} {resp.text}"


def test_cross_user_attempts_change_nothing(world, client, other_client, db_session):
    for _name, method, path, kwargs in ROUTES:
        _send(other_client, method, path(world), kwargs(world))

    db_session.rollback()
    count = lambda model: db_session.query(func.count()).select_from(model).scalar()  # noqa: E731
    assert db_session.get(models.Source, world["source"]) is not None
    assert count(models.Source) == 1
    assert count(models.Chunk) == 1
    assert count(models.StudySession) == 0
    mastery = db_session.get(models.Mastery, world["topic"])
    assert mastery.score == 50
    assert mastery.status.value == world["status"]
    assert mastery.flagged_for_revision is False


def test_mastery_list_only_contains_the_callers_rows(world, client, other_client):
    assert [m["topic_id"] for m in client.get("/mastery").json()] == [world["topic"]]
    assert other_client.get("/mastery").json() == []

    mine = make_topic(other_client, "Mine", course="B's course")
    assert [m["topic_id"] for m in other_client.get("/mastery").json()] == [mine["id"]]


def test_retrieve_without_a_topic_only_searches_the_callers_chunks(
    world, client, other_client, db_session
):
    # B has a chunk of their own; A's must never come back for B.
    mine = make_topic(other_client, "Mine", course="B's course")
    source = models.Source(
        topic_id=mine["id"], source_type=models.SourceType.self_supplied, title="B's notes"
    )
    db_session.add(source)
    db_session.flush()
    own_chunk = models.Chunk(
        source_id=source.id,
        topic_id=mine["id"],
        chunk_text="b's text",
        chunk_index=0,
        embedding=[1.0] + [0.0] * (EMBEDDING_DIM - 1),
    )
    db_session.add(own_chunk)
    db_session.commit()

    ids_for_b = [
        r["chunk_id"] for r in other_client.post("/retrieve", json={"question": "text"}).json()["results"]
    ]
    assert ids_for_b == [own_chunk.id]

    ids_for_a = [
        r["chunk_id"] for r in client.post("/retrieve", json={"question": "text"}).json()["results"]
    ]
    assert ids_for_a == [world["chunk"]]

    # Naming A's source id doesn't widen B's search either.
    leaked = other_client.post(
        "/retrieve", json={"question": "text", "source_ids": [world["source"]]}
    ).json()["results"]
    assert leaked == []


def test_unmastered_prerequisites_are_scoped_to_the_user(client, other_client, db_session):
    prereq = make_topic(client, "Prereq", course="A's course")
    main = make_topic(client, "Main", course="A's course")
    assert (
        client.post(
            "/topics/prerequisites",
            json={"topic_id": main["id"], "prerequisite_topic_id": prereq["id"]},
        ).status_code
        == 200
    )

    mine = graph_service.get_unmastered_prerequisites(db_session, main["id"], client.user_id)
    assert [t.id for t in mine] == [prereq["id"]]
    assert graph_service.get_unmastered_prerequisites(db_session, main["id"], other_client.user_id) == []
