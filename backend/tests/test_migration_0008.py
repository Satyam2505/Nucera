"""Migration 0008 (quiz jobs + quiz_sets.status) against a populated pre-0008 database."""

import sqlite3

import pytest

from test_migration_0005 import _alembic, _rows


@pytest.fixture()
def populated_db(tmp_path):
    db_path = tmp_path / "pre0008.db"
    _alembic(db_path, "upgrade", "0007")
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@example.com', 'x')")
    con.execute("INSERT INTO courses (id, user_id, name) VALUES (1, 1, 'DSA')")
    con.execute("INSERT INTO modules (id, course_id, name, position) VALUES (1, 1, 'M', 0)")
    con.executemany(
        "INSERT INTO topics (id, user_id, module_id, name, position) VALUES (?, 1, 1, ?, ?)",
        [(1, "T1", 0), (2, "T2", 1)],
    )
    con.execute("INSERT INTO mastery (topic_id, score, status) VALUES (1, 50, 'in_progress')")
    # Two finished quizzes for topic 1, one graded.
    con.executemany("INSERT INTO quiz_sets (id, topic_id) VALUES (?, 1)", [(1,), (2,)])
    con.executemany(
        "INSERT INTO quiz_questions (id, quiz_set_id, position, question_text, options, correct_option) "
        "VALUES (?, ?, 0, 'q?', '{\"A\": \"x\"}', 'A')",
        [(1, 1), (2, 2)],
    )
    con.execute(
        "INSERT INTO quiz_attempts (quiz_set_id, correct, total, score_percent, score_delta, answers) "
        "VALUES (1, 1, 1, 100.0, 10, '{\"1\": \"A\"}')"
    )
    con.commit()
    con.close()
    return db_path


def test_existing_quizzes_become_ready_and_nothing_is_lost(populated_db):
    _alembic(populated_db, "upgrade", "head")

    assert _rows(populated_db, "SELECT id, status FROM quiz_sets ORDER BY id") == [(1, "ready"), (2, "ready")]
    assert _rows(populated_db, "SELECT COUNT(*) FROM quiz_questions") == [(2,)]
    assert _rows(populated_db, "SELECT correct, total FROM quiz_attempts") == [(1, 1)]
    assert _rows(populated_db, "SELECT COUNT(*) FROM quiz_jobs") == [(0,)]


def test_the_status_column_is_required_and_defaults_to_ready(populated_db):
    _alembic(populated_db, "upgrade", "head")
    info = {r[1]: r for r in _rows(populated_db, "PRAGMA table_info(quiz_sets)")}
    assert info["status"][3] == 1  # NOT NULL

    con = sqlite3.connect(populated_db)
    con.execute("INSERT INTO quiz_sets (id, topic_id) VALUES (3, 2)")  # status omitted, as old code did
    con.commit()
    assert con.execute("SELECT status FROM quiz_sets WHERE id = 3").fetchone() == ("ready",)
    con.close()


def test_quiz_jobs_has_the_expected_shape(populated_db):
    _alembic(populated_db, "upgrade", "head")
    info = {r[1]: r for r in _rows(populated_db, "PRAGMA table_info(quiz_jobs)")}
    assert set(info) == {
        "id", "topic_id", "quiz_set_id", "status", "requested", "completed",
        "error", "created_at", "started_at", "finished_at", "heartbeat_at",
    }
    assert info["topic_id"][3] == 1 and info["status"][3] == 1 and info["requested"][3] == 1


def test_the_database_allows_only_one_active_job_per_topic(populated_db):
    _alembic(populated_db, "upgrade", "head")
    con = sqlite3.connect(populated_db)
    con.execute("PRAGMA foreign_keys = ON")
    add = lambda topic, status: con.execute(  # noqa: E731
        "INSERT INTO quiz_jobs (topic_id, status, requested) VALUES (?, ?, 3)", (topic, status)
    )

    add(1, "running")
    with pytest.raises(sqlite3.IntegrityError):
        add(1, "queued")  # a second active job for the same topic
    with pytest.raises(sqlite3.IntegrityError):
        add(1, "running")
    add(2, "queued")  # another topic is independent

    # Finished jobs don't count, however many there are.
    add(1, "failed")
    add(1, "failed")
    add(1, "succeeded")
    add(1, "partial")
    con.commit()

    # Once the active job finishes, the topic can start another.
    con.execute("UPDATE quiz_jobs SET status = 'succeeded' WHERE topic_id = 1 AND status = 'running'")
    add(1, "queued")
    con.commit()
    con.close()


def test_a_job_needs_a_real_topic_and_dies_with_it(populated_db):
    _alembic(populated_db, "upgrade", "head")
    con = sqlite3.connect(populated_db)
    con.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO quiz_jobs (topic_id, status, requested) VALUES (99, 'queued', 3)")
    con.execute("INSERT INTO quiz_jobs (topic_id, quiz_set_id, status, requested) VALUES (1, 1, 'succeeded', 3)")
    con.execute("DELETE FROM quiz_sets WHERE id = 1")  # the set goes, the job row stays, unlinked
    assert con.execute("SELECT quiz_set_id FROM quiz_jobs").fetchone() == (None,)
    con.execute("DELETE FROM topics WHERE id = 1")
    assert con.execute("SELECT COUNT(*) FROM quiz_jobs").fetchone() == (0,)
    con.commit()
    con.close()


def test_downgrade_drops_unfinished_sets_but_keeps_the_rest(populated_db):
    _alembic(populated_db, "upgrade", "head")
    con = sqlite3.connect(populated_db)
    con.execute("INSERT INTO quiz_sets (id, topic_id, status) VALUES (5, 2, 'generating')")
    con.execute(
        "INSERT INTO quiz_questions (quiz_set_id, position, question_text, options, correct_option) "
        "VALUES (5, 0, 'half written', '{\"A\": \"x\"}', 'A')"
    )
    con.commit()
    con.close()

    _alembic(populated_db, "downgrade", "0007")

    tables = {r[0] for r in _rows(populated_db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "quiz_jobs" not in tables
    assert "status" not in {r[1] for r in _rows(populated_db, "PRAGMA table_info(quiz_sets)")}
    assert _rows(populated_db, "SELECT id FROM quiz_sets ORDER BY id") == [(1,), (2,)]
    assert _rows(populated_db, "SELECT COUNT(*) FROM quiz_questions WHERE question_text = 'half written'") == [(0,)]
    assert _rows(populated_db, "SELECT correct FROM quiz_attempts") == [(1,)]


def test_upgrade_works_on_an_empty_database(tmp_path):
    db_path = tmp_path / "fresh.db"
    _alembic(db_path, "upgrade", "head")
    assert _rows(db_path, "SELECT COUNT(*) FROM quiz_jobs") == [(0,)]
    _alembic(db_path, "downgrade", "0007")
    _alembic(db_path, "upgrade", "head")
