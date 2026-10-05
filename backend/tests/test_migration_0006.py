"""Migration 0006 (quiz sets and attempts) against a populated pre-0006 database.

Same approach as test_migration_0005: the real alembic CLI against a
throwaway SQLite file.
"""

import sqlite3

import pytest

from test_migration_0005 import _alembic, _rows


@pytest.fixture()
def populated_db(tmp_path):
    """A database at revision 0005 with stub quiz questions, a quiz session,
    and orphaned questions whose topic no longer exists."""
    db_path = tmp_path / "pre0006.db"
    _alembic(db_path, "upgrade", "0005")

    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@example.com', 'x')")
    con.execute("INSERT INTO courses (id, user_id, name) VALUES (1, 1, 'DSA')")
    con.execute("INSERT INTO modules (id, course_id, name, position) VALUES (1, 1, 'M', 0)")
    con.execute("INSERT INTO topics (id, user_id, module_id, name, position) VALUES (1, 1, 1, 'T', 0)")
    con.execute("INSERT INTO mastery (topic_id, score, status) VALUES (1, 40, 'in_progress')")
    con.execute("INSERT INTO sessions (topic_id, type, score_delta) VALUES (1, 'quiz', 4)")
    questions = [
        (1, 1, "[stub] What is a foundational concept in T?"),
        (2, 1, "[stub] Which statement about T is true?"),
        (3, 99, "[stub] orphan of a deleted topic"),  # topic 99 doesn't exist
    ]
    con.executemany(
        "INSERT INTO quiz_questions (id, topic_id, question_text, options, correct_option) "
        "VALUES (?, ?, ?, '{\"A\": \"x\"}', 'A')",
        questions,
    )
    con.commit()
    con.close()
    return db_path


def test_upgrade_deletes_the_stub_and_orphan_questions_and_keeps_history(populated_db):
    _alembic(populated_db, "upgrade", "head")

    assert _rows(populated_db, "SELECT COUNT(*) FROM quiz_questions") == [(0,)]
    assert _rows(populated_db, "SELECT COUNT(*) FROM quiz_sets") == [(0,)]
    assert _rows(populated_db, "SELECT COUNT(*) FROM quiz_attempts") == [(0,)]
    # The mastery history and quiz session the stub quizzes produced are untouched.
    assert _rows(populated_db, "SELECT topic_id, score, status FROM mastery") == [
        (1, 40, "in_progress")
    ]
    assert _rows(populated_db, "SELECT topic_id, type, score_delta FROM sessions") == [
        (1, "quiz", 4)
    ]


def test_upgrade_reshapes_quiz_questions(populated_db):
    _alembic(populated_db, "upgrade", "head")

    info = {r[1]: r for r in _rows(populated_db, "PRAGMA table_info(quiz_questions)")}
    assert "topic_id" not in info
    assert {"quiz_set_id", "position", "explanation", "sources"} <= set(info)
    assert info["quiz_set_id"][3] == 1  # NOT NULL

    # The new shape accepts a real set, question and attempt.
    con = sqlite3.connect(populated_db)
    con.execute("INSERT INTO quiz_sets (id, topic_id) VALUES (1, 1)")
    con.execute(
        "INSERT INTO quiz_questions (quiz_set_id, position, question_text, options, correct_option, "
        "explanation, sources) VALUES (1, 0, 'q', '{}', 'B', 'because', '[{\"source\": \"s\", \"page\": 2}]')"
    )
    con.execute(
        "INSERT INTO quiz_attempts (quiz_set_id, correct, total, score_percent, score_delta, answers) "
        "VALUES (1, 1, 1, 100.0, 10, '{}')"
    )
    con.commit()
    con.close()
    assert _rows(populated_db, "SELECT COUNT(*) FROM quiz_questions") == [(1,)]


def test_downgrade_restores_topic_id_from_the_set(populated_db):
    _alembic(populated_db, "upgrade", "head")
    con = sqlite3.connect(populated_db)
    con.execute("INSERT INTO quiz_sets (id, topic_id) VALUES (1, 1)")
    con.execute(
        "INSERT INTO quiz_questions (id, quiz_set_id, position, question_text, options, correct_option) "
        "VALUES (7, 1, 0, 'real question', '{}', 'C')"
    )
    con.commit()
    con.close()

    _alembic(populated_db, "downgrade", "0005")

    assert _rows(populated_db, "SELECT id, topic_id, question_text FROM quiz_questions") == [
        (7, 1, "real question")
    ]
    tables = {r[0] for r in _rows(populated_db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "quiz_sets" not in tables and "quiz_attempts" not in tables
    columns = [r[1] for r in _rows(populated_db, "PRAGMA table_info(quiz_questions)")]
    assert "quiz_set_id" not in columns and "topic_id" in columns


def test_upgrade_on_empty_database(tmp_path):
    db_path = tmp_path / "empty.db"
    _alembic(db_path, "upgrade", "head")
    assert _rows(db_path, "SELECT COUNT(*) FROM quiz_sets") == [(0,)]
