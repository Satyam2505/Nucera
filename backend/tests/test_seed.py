import pytest
from sqlalchemy import func

import seed
from app import models


def _counts(db_session):
    db_session.rollback()
    return {
        "courses": db_session.query(func.count()).select_from(models.Course).scalar(),
        "modules": db_session.query(func.count()).select_from(models.Module).scalar(),
        "topics": db_session.query(func.count()).select_from(models.Topic).scalar(),
        "mastery": db_session.query(func.count()).select_from(models.Mastery).scalar(),
        "prereqs": db_session.query(func.count()).select_from(models.Prerequisite).scalar(),
    }


def test_seed_with_email_creates_a_visible_course_with_modules(client, db_session):
    seed.seed(email="test-user@example.com")

    (course,) = client.get("/courses").json()
    assert course["name"] == seed.COURSE_NAME
    assert course["module_count"] == len(seed.MODULES) == 4
    assert course["topic_count"] == 10

    tree = client.get(f"/courses/{course['id']}/tree").json()
    assert [m["name"] for m in tree["modules"]] == [name for name, _ in seed.MODULES]
    assert sum(len(v) for v in seed.PREREQUISITES.values()) == _counts(db_session)["prereqs"]

    # Every seeded topic belongs to the account, so it shows up in its graph.
    assert len(client.get("/topics/graph/json").json()["nodes"]) == 10


def test_seed_without_email_is_unowned_and_hidden_from_users(client, db_session):
    seed.seed()
    assert _counts(db_session)["topics"] == 10
    assert client.get("/courses").json() == []
    assert client.get("/topics").json() == []


def test_seed_is_idempotent_per_owner(client, db_session):
    seed.seed(email="test-user@example.com")
    seed.seed(email="test-user@example.com")
    assert _counts(db_session)["courses"] == 1


def test_seed_with_unknown_email_exits_without_creating_anything(db_session):
    with pytest.raises(SystemExit):
        seed.seed(email="nobody@example.com")
    assert _counts(db_session)["courses"] == 0
