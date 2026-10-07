"""Migration 0011 (lower-case emails + unique index on lower(email)) against a populated
pre-0011 database, including the case where it must refuse to run."""

import os
import sqlite3
import subprocess
import sys

import pytest

from test_migration_0005 import BACKEND_DIR, _alembic, _rows


def _alembic_result(db_path, *args):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND_DIR, env=env, capture_output=True, text=True
    )


def make_db(tmp_path, emails):
    db_path = tmp_path / "pre0011.db"
    _alembic(db_path, "upgrade", "0010")
    con = sqlite3.connect(db_path)
    for i, email in enumerate(emails, start=1):
        con.execute("INSERT INTO users (id, email, hashed_password) VALUES (?, ?, 'x')", (i, email))
        con.execute("INSERT INTO courses (id, user_id, name) VALUES (?, ?, ?)", (i, i, f"Course {i}"))
    con.commit()
    con.close()
    return db_path


def emails(db_path):
    return [r[0] for r in _rows(db_path, "SELECT email FROM users ORDER BY id")]


def test_mixed_case_and_padded_emails_are_lower_cased_and_trimmed(tmp_path):
    db = make_db(tmp_path, ["Alice@Example.com", "bob@example.com", "  Carol@EXAMPLE.com "])
    _alembic(db, "upgrade", "head")
    assert emails(db) == ["alice@example.com", "bob@example.com", "carol@example.com"]


def test_nothing_else_about_the_accounts_changes(tmp_path):
    db = make_db(tmp_path, ["Alice@Example.com", "bob@example.com"])
    _alembic(db, "upgrade", "head")
    assert _rows(db, "SELECT id, hashed_password FROM users ORDER BY id") == [(1, "x"), (2, "x")]
    assert _rows(db, "SELECT user_id, name FROM courses ORDER BY id") == [(1, "Course 1"), (2, "Course 2")]


def test_the_database_then_refuses_an_account_that_differs_only_by_case(tmp_path):
    db = make_db(tmp_path, ["alice@example.com"])
    _alembic(db, "upgrade", "head")
    con = sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO users (email, hashed_password) VALUES ('ALICE@example.com', 'x')")
    con.execute("INSERT INTO users (email, hashed_password) VALUES ('someone-else@example.com', 'x')")  # others are fine
    con.commit()
    con.close()


def test_two_accounts_that_differ_only_by_case_stop_the_migration_before_anything_changes(tmp_path):
    db = make_db(tmp_path, ["Dave@Example.com", "erin@Example.com", "dave@example.com"])
    result = _alembic_result(db, "upgrade", "head")
    assert result.returncode != 0
    message = result.stderr
    assert "differ only by capitalisation" in message
    assert "'Dave@Example.com' (account id 1)" in message and "'dave@example.com' (account id 3)" in message
    assert "Nothing was changed" in message
    # Not even the harmless rows were touched, and the database is still at 0010.
    assert emails(db) == ["Dave@Example.com", "erin@Example.com", "dave@example.com"]
    assert _rows(db, "SELECT version_num FROM alembic_version") == [("0010",)]


def test_after_resolving_the_clash_by_hand_the_migration_runs(tmp_path):
    db = make_db(tmp_path, ["Dave@Example.com", "dave@example.com"])
    assert _alembic_result(db, "upgrade", "head").returncode != 0
    con = sqlite3.connect(db)
    con.execute("DELETE FROM users WHERE id = 2")
    con.commit()
    con.close()
    _alembic(db, "upgrade", "head")
    assert emails(db) == ["dave@example.com"]


def test_downgrade_drops_the_index_and_keeps_the_lower_case_emails(tmp_path):
    db = make_db(tmp_path, ["Alice@Example.com"])
    _alembic(db, "upgrade", "head")
    _alembic(db, "downgrade", "0010")
    names = {r[0] for r in _rows(db, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "uq_users_email_lower" not in names
    assert emails(db) == ["alice@example.com"]
    con = sqlite3.connect(db)  # and the old rule (exact match only) applies again
    con.execute("INSERT INTO users (email, hashed_password) VALUES ('ALICE@example.com', 'x')")
    con.commit()
    con.close()


def test_upgrade_works_on_an_empty_database(tmp_path):
    db = tmp_path / "fresh.db"
    _alembic(db, "upgrade", "head")
    assert _rows(db, "SELECT COUNT(*) FROM users") == [(0,)]
    names = {r[0] for r in _rows(db, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "uq_users_email_lower" in names
