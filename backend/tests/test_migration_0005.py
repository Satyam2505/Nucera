"""Migration 0005 (courses + modules) against a populated pre-0005 database.

Runs the real alembic CLI in a subprocess against a throwaway SQLite file
so env.py's DATABASE_URL handling is exercised exactly as in production.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr}"


@pytest.fixture()
def populated_db(tmp_path):
    """A database at revision 0004 holding topics for two users plus an unowned one."""
    db_path = tmp_path / "pre0005.db"
    _alembic(db_path, "upgrade", "0004")

    con = sqlite3.connect(db_path)
    con.executemany(
        "INSERT INTO users (id, email, hashed_password) VALUES (?, ?, 'x')",
        [(1, "a@example.com"), (2, "b@example.com")],
    )
    topics = [
        (1, 1, "Sets", "DSA"),
        (2, 1, "Big-O", "DSA"),
        (3, 1, "Cells", "Biology"),
        (4, 2, "Sets", "DSA"),  # same course name, different user -> its own course
        (5, None, "Seeded", "Seed Course"),  # unowned (seed.py before auth)
    ]
    con.executemany(
        "INSERT INTO topics (id, user_id, name, course) VALUES (?, ?, ?, ?)", topics
    )
    con.execute("INSERT INTO mastery (topic_id, score, status) VALUES (2, 40, 'in_progress')")
    con.execute("INSERT INTO prerequisites (topic_id, prerequisite_topic_id) VALUES (2, 1)")
    con.commit()
    con.close()
    return db_path


def _rows(db_path, sql):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_upgrade_backfills_one_course_and_general_module_per_user_course_pair(populated_db):
    _alembic(populated_db, "upgrade", "head")

    # Ordered by each pair's lowest topic id, so ids are deterministic.
    assert _rows(populated_db, "SELECT id, user_id, name FROM courses ORDER BY id") == [
        (1, 1, "DSA"),
        (2, 1, "Biology"),
        (3, 2, "DSA"),
        (4, None, "Seed Course"),
    ]
    assert _rows(
        populated_db, "SELECT id, course_id, name, position FROM modules ORDER BY id"
    ) == [
        (1, 1, "General", 0),
        (2, 2, "General", 0),
        (3, 3, "General", 0),
        (4, 4, "General", 0),
    ]
    assert _rows(
        populated_db, "SELECT id, module_id, position FROM topics ORDER BY id"
    ) == [(1, 1, 0), (2, 1, 1), (3, 2, 0), (4, 3, 0), (5, 4, 0)]


def test_upgrade_drops_course_column_and_keeps_related_rows(populated_db):
    _alembic(populated_db, "upgrade", "head")

    columns = [r[1] for r in _rows(populated_db, "PRAGMA table_info(topics)")]
    assert "course" not in columns
    assert {"module_id", "position", "user_id"} <= set(columns)

    module_id_col = next(
        r for r in _rows(populated_db, "PRAGMA table_info(topics)") if r[1] == "module_id"
    )
    assert module_id_col[3] == 1  # NOT NULL

    assert _rows(populated_db, "SELECT topic_id, score FROM mastery") == [(2, 40)]
    assert _rows(populated_db, "SELECT topic_id, prerequisite_topic_id FROM prerequisites") == [
        (2, 1)
    ]
    # topics.user_id is preserved (it is still used for scoping).
    assert _rows(populated_db, "SELECT id, user_id FROM topics ORDER BY id") == [
        (1, 1),
        (2, 1),
        (3, 1),
        (4, 2),
        (5, None),
    ]


def test_downgrade_restores_course_string_from_course_name(populated_db):
    _alembic(populated_db, "upgrade", "head")
    _alembic(populated_db, "downgrade", "0004")

    assert _rows(populated_db, "SELECT id, course FROM topics ORDER BY id") == [
        (1, "DSA"),
        (2, "DSA"),
        (3, "Biology"),
        (4, "DSA"),
        (5, "Seed Course"),
    ]
    tables = {r[0] for r in _rows(populated_db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "courses" not in tables and "modules" not in tables
    columns = [r[1] for r in _rows(populated_db, "PRAGMA table_info(topics)")]
    assert "module_id" not in columns and "position" not in columns


def test_upgrade_on_empty_database(tmp_path):
    db_path = tmp_path / "empty.db"
    _alembic(db_path, "upgrade", "head")
    assert _rows(db_path, "SELECT COUNT(*) FROM courses") == [(0,)]
    assert _rows(db_path, "SELECT COUNT(*) FROM modules") == [(0,)]
