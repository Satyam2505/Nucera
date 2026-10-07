"""Migration 0010 (the mastery memory model's columns) against a populated pre-0010 database."""

import sqlite3
from datetime import datetime

import pytest

from test_migration_0005 import _alembic, _rows

# (topic id, score, status, flagged_for_revision, last_updated)
MASTERY = [
    (1, 0, "unmastered", 0, "2025-01-01 00:00:00"),
    (2, 40, "in_progress", 1, "2025-01-01 00:00:00"),  # untouched for ages
    (3, 85, "mastered", 0, "2026-09-30 00:00:00"),
    (4, 30, "missed", 0, "2026-09-01 00:00:00"),
    (5, 100, "mastered", 0, "2026-10-01 00:00:00"),
]


@pytest.fixture()
def populated_db(tmp_path):
    db_path = tmp_path / "pre0010.db"
    _alembic(db_path, "upgrade", "0009")
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@example.com', 'x')")
    con.execute("INSERT INTO courses (id, user_id, name) VALUES (1, 1, 'DSA')")
    con.execute("INSERT INTO modules (id, course_id, name, position) VALUES (1, 1, 'M', 0)")
    for tid, *_ in MASTERY:
        con.execute("INSERT INTO topics (id, user_id, module_id, name, position) VALUES (?, 1, 1, ?, ?)", (tid, f"T{tid}", tid))
    con.executemany(
        "INSERT INTO mastery (topic_id, score, status, flagged_for_revision, last_updated) VALUES (?, ?, ?, ?, ?)",
        MASTERY,
    )
    con.commit()
    con.close()
    return db_path


def mastery_rows(db_path):
    return {
        r[0]: r
        for r in _rows(
            db_path,
            "SELECT topic_id, score, status, flagged_for_revision, estimate, stability_days, last_reviewed_at FROM mastery",
        )
    }


def test_scores_and_statuses_are_untouched(populated_db):
    _alembic(populated_db, "upgrade", "head")
    rows = mastery_rows(populated_db)
    assert {tid: (r[1], r[2], r[3]) for tid, r in rows.items()} == {tid: (s, st, f) for tid, s, st, f, _ in MASTERY}


def test_a_topic_with_a_score_gets_an_estimate_a_half_life_and_a_review_clock(populated_db):
    _alembic(populated_db, "upgrade", "head")
    rows = mastery_rows(populated_db)
    for tid, score in [(2, 40), (3, 85), (4, 30), (5, 100)]:
        _tid, _s, _st, _f, estimate, stability, reviewed = rows[tid]
        assert estimate == pytest.approx(score / 100)
        assert stability == pytest.approx(3 + 0.1 * score)  # 7.0 for 40, 11.5 for 85 ...
        assert reviewed is not None


def test_a_topic_at_zero_has_no_history(populated_db):
    _alembic(populated_db, "upgrade", "head")
    _tid, _s, _st, _f, estimate, stability, reviewed = mastery_rows(populated_db)[1]
    assert (estimate, stability, reviewed) == (0.0, 3.0, None)


def test_nothing_has_faded_on_the_day_of_the_upgrade_even_for_a_topic_untouched_for_months(populated_db):
    """The clock starts at the migration, not at last_updated: a topic last touched in
    January must not drop to nothing the moment the app is upgraded."""
    from types import SimpleNamespace

    from app.services import mastery_model

    _alembic(populated_db, "upgrade", "head")
    _tid, score, _st, _f, estimate, stability, reviewed = mastery_rows(populated_db)[2]
    started = datetime.fromisoformat(reviewed)
    assert abs((datetime.utcnow() - started).total_seconds()) < 120
    row = SimpleNamespace(estimate=estimate, stability_days=stability, last_reviewed_at=started)
    assert mastery_model.effective_score(row, datetime.utcnow()) == score == 40


def test_the_new_columns_are_required_with_defaults_for_new_topics(populated_db):
    _alembic(populated_db, "upgrade", "head")
    info = {r[1]: r for r in _rows(populated_db, "PRAGMA table_info(mastery)")}
    assert info["estimate"][3] == 1 and info["stability_days"][3] == 1  # NOT NULL
    assert info["last_reviewed_at"][3] == 0  # nullable: no history yet
    con = sqlite3.connect(populated_db)
    con.execute("INSERT INTO topics (id, user_id, module_id, name, position) VALUES (9, 1, 1, 'New', 9)")
    con.execute("INSERT INTO mastery (topic_id) VALUES (9)")  # as old code did, with no model fields
    con.commit()
    assert con.execute("SELECT score, estimate, stability_days, last_reviewed_at FROM mastery WHERE topic_id = 9").fetchone() == (0, 0.0, 3.0, None)
    con.close()


def test_the_app_reads_a_migrated_database_without_changing_what_is_shown(populated_db, monkeypatch):
    """Opens the migrated file through the real ORM, as the server would."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import models

    _alembic(populated_db, "upgrade", "head")
    engine = create_engine(f"sqlite:///{populated_db.as_posix()}")
    session = sessionmaker(bind=engine)()
    try:
        shown = {m.topic_id: (m.score, m.status.value) for m in session.query(models.Mastery)}
    finally:
        session.close()
        engine.dispose()
    assert shown == {tid: (s, st) for tid, s, st, _f, _u in MASTERY}


def test_downgrade_removes_the_columns_and_keeps_the_scores(populated_db):
    _alembic(populated_db, "upgrade", "head")
    _alembic(populated_db, "downgrade", "0009")
    cols = {r[1] for r in _rows(populated_db, "PRAGMA table_info(mastery)")}
    assert not ({"estimate", "stability_days", "last_reviewed_at"} & cols)
    assert _rows(populated_db, "SELECT topic_id, score, status FROM mastery ORDER BY topic_id") == [
        (tid, s, st) for tid, s, st, _f, _u in MASTERY
    ]


def test_upgrading_again_after_a_downgrade_works(populated_db):
    _alembic(populated_db, "upgrade", "head")
    _alembic(populated_db, "downgrade", "0009")
    _alembic(populated_db, "upgrade", "head")
    assert mastery_rows(populated_db)[3][4] == pytest.approx(0.85)


def test_upgrade_works_on_an_empty_database(tmp_path):
    db_path = tmp_path / "fresh.db"
    _alembic(db_path, "upgrade", "head")
    assert _rows(db_path, "SELECT COUNT(*) FROM mastery") == [(0,)]
