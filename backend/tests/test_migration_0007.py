"""Migration 0007 (chat_messages) against a populated pre-0007 database."""

import sqlite3

import pytest

from test_migration_0005 import _alembic, _rows


@pytest.fixture()
def populated_db(tmp_path):
    db_path = tmp_path / "pre0007.db"
    _alembic(db_path, "upgrade", "0006")
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@example.com', 'x')")
    con.execute("INSERT INTO courses (id, user_id, name) VALUES (1, 1, 'DSA')")
    con.execute("INSERT INTO modules (id, course_id, name, position) VALUES (1, 1, 'M', 0)")
    con.execute("INSERT INTO topics (id, user_id, module_id, name, position) VALUES (1, 1, 1, 'T', 0)")
    con.execute("INSERT INTO mastery (topic_id, score, status) VALUES (1, 40, 'in_progress')")
    con.execute("INSERT INTO sessions (topic_id, type, score_delta) VALUES (1, 'chat', 0)")
    con.execute(
        "INSERT INTO sources (id, topic_id, source_type, title, raw_text) "
        "VALUES (1, 1, 'self_supplied', 'notes', 'text')"
    )
    con.commit()
    con.close()
    return db_path


def test_upgrade_keeps_existing_data_and_adds_an_empty_chat_table(populated_db):
    _alembic(populated_db, "upgrade", "head")

    assert _rows(populated_db, "SELECT COUNT(*) FROM chat_messages") == [(0,)]
    assert _rows(populated_db, "SELECT topic_id, score, status FROM mastery") == [
        (1, 40, "in_progress")
    ]
    assert _rows(populated_db, "SELECT COUNT(*) FROM sessions") == [(1,)]
    assert _rows(populated_db, "SELECT title FROM sources") == [("notes",)]


def test_the_new_table_has_the_expected_shape_and_accepts_a_conversation(populated_db):
    _alembic(populated_db, "upgrade", "head")

    info = {r[1]: r for r in _rows(populated_db, "PRAGMA table_info(chat_messages)")}
    assert {"id", "topic_id", "role", "content", "sources", "flagged", "grounded", "created_at"} == set(info)
    assert info["topic_id"][3] == 1 and info["role"][3] == 1 and info["content"][3] == 1  # NOT NULL

    con = sqlite3.connect(populated_db)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("INSERT INTO chat_messages (topic_id, role, content) VALUES (1, 'user', 'What is X?')")
    con.execute(
        "INSERT INTO chat_messages (topic_id, role, content, sources, flagged, grounded) "
        "VALUES (1, 'assistant', 'X is Y.', '[{\"source\": \"notes\", \"page\": 2}]', '[\"Prereq\"]', 1)"
    )
    con.commit()
    assert con.execute("SELECT role FROM chat_messages ORDER BY id").fetchall() == [("user",), ("assistant",)]
    assert con.execute("SELECT created_at IS NOT NULL FROM chat_messages").fetchall() == [(1,), (1,)]

    # Deleting the topic takes its conversation with it.
    con.execute("DELETE FROM topics WHERE id = 1")
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM chat_messages").fetchone() == (0,)
    con.close()


def test_a_chat_message_needs_a_real_topic(populated_db):
    _alembic(populated_db, "upgrade", "head")
    con = sqlite3.connect(populated_db)
    con.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO chat_messages (topic_id, role, content) VALUES (99, 'user', 'x')")
    con.close()


def test_downgrade_removes_the_table_and_keeps_everything_else(populated_db):
    _alembic(populated_db, "upgrade", "head")
    _alembic(populated_db, "downgrade", "0006")

    tables = {r[0] for r in _rows(populated_db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "chat_messages" not in tables
    assert _rows(populated_db, "SELECT title FROM sources") == [("notes",)]


def test_upgrade_works_on_an_empty_database(tmp_path):
    db_path = tmp_path / "fresh.db"
    _alembic(db_path, "upgrade", "head")
    assert _rows(db_path, "SELECT COUNT(*) FROM chat_messages") == [(0,)]
