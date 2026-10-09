"""Migration 0003 (users and topic ownership) against a populated pre-login database.

Before accounts existed, topics belonged to nobody. The migration gives them a
placeholder account so they don't become invisible, and its password hash is a
constant baked into the migration. These tests pin that: the account exists, its
password really is the documented one, and the old topics belong to it, while a
database with no topics gets no such account.

Runs the real alembic CLI against throwaway SQLite files, like test_migration_0005.
"""

import sqlite3

import pytest

from app.security import verify_password
from test_migration_0005 import _alembic, _rows

LEGACY_EMAIL = "legacy@edupilot.local"
LEGACY_PASSWORD = "changeme123"


@pytest.fixture()
def pre_login_db(tmp_path):
    """A database at revision 0002 (no users table yet) that already holds topics."""
    db_path = tmp_path / "pre0003.db"
    _alembic(db_path, "upgrade", "0002")

    con = sqlite3.connect(db_path)
    con.executemany(
        "INSERT INTO topics (id, name, course) VALUES (?, ?, ?)",
        [(1, "Sets", "DSA"), (2, "Cells", "Biology")],
    )
    con.commit()
    con.close()
    return db_path


def test_existing_topics_get_a_legacy_account_with_the_documented_password(pre_login_db):
    _alembic(pre_login_db, "upgrade", "0003")

    users = _rows(pre_login_db, "SELECT id, email, hashed_password FROM users")
    assert [email for _id, email, _hash in users] == [LEGACY_EMAIL]
    legacy_id, _email, stored_hash = users[0]

    # Compare as booleans so a failure never prints the stored hash.
    accepts_documented_password = verify_password(LEGACY_PASSWORD, stored_hash)
    rejects_other_passwords = not verify_password("not-the-password", stored_hash)
    assert accepts_documented_password, "the legacy account no longer accepts its documented password"
    assert rejects_other_passwords, "the legacy account accepts a password it should not"

    # Every topic that existed before accounts now belongs to that account.
    assert _rows(pre_login_db, "SELECT id, user_id FROM topics ORDER BY id") == [
        (1, legacy_id),
        (2, legacy_id),
    ]
    # ...and the topics themselves are intact.
    assert _rows(pre_login_db, "SELECT id, name, course FROM topics ORDER BY id") == [
        (1, "Sets", "DSA"),
        (2, "Cells", "Biology"),
    ]


def test_an_empty_database_gets_no_legacy_account(tmp_path):
    db_path = tmp_path / "empty.db"
    _alembic(db_path, "upgrade", "head")

    # No topics to adopt, so no placeholder account (and no accounts at all).
    assert _rows(db_path, f"SELECT COUNT(*) FROM users WHERE lower(email) = '{LEGACY_EMAIL}'") == [(0,)]
    assert _rows(db_path, "SELECT COUNT(*) FROM users") == [(0,)]
