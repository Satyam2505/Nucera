"""Migration 0009 (FTS5 keyword index over chunks) against a populated pre-0009 database."""

import sqlite3

import pytest

from test_migration_0005 import _alembic, _rows

_OURS = {"chunks_fts", "chunks_fts_ai", "chunks_fts_ad", "chunks_fts_au"}
TEXTS = [
    "Tombstones mark deleted slots in open addressing.",
    "Third normal form removes transitive dependencies.",
    "Merge sort halves the list and merges the halves.",
]


@pytest.fixture()
def populated_db(tmp_path):
    db_path = tmp_path / "pre0009.db"
    _alembic(db_path, "upgrade", "0008")
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@example.com', 'x')")
    con.execute("INSERT INTO courses (id, user_id, name) VALUES (1, 1, 'DSA')")
    con.execute("INSERT INTO modules (id, course_id, name, position) VALUES (1, 1, 'M', 0)")
    con.execute("INSERT INTO topics (id, user_id, module_id, name, position) VALUES (1, 1, 1, 'T', 0)")
    con.execute("INSERT INTO sources (id, topic_id, source_type, title, raw_text) VALUES (1, 1, 'self_supplied', 'n', 'x')")
    con.executemany(
        "INSERT INTO chunks (id, source_id, topic_id, chunk_text, chunk_index, page_number) VALUES (?, 1, 1, ?, ?, ?)",
        [(i + 1, text, i, i + 1) for i, text in enumerate(TEXTS)],
    )
    con.commit()
    con.close()
    return db_path


def fts_match(db_path, term):
    return [r[0] for r in _rows(db_path, f"SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH '{term}' ORDER BY rowid")]


def test_existing_chunks_are_indexed_by_the_migration(populated_db):
    _alembic(populated_db, "upgrade", "head")
    assert fts_match(populated_db, "tombstone") == [1]  # stemmed: "Tombstones" matches
    assert fts_match(populated_db, "transitive") == [2]
    assert fts_match(populated_db, "halves") == [3]
    assert _rows(populated_db, "SELECT COUNT(*) FROM chunks") == [(3,)]  # the chunks themselves are untouched


def test_the_index_has_no_second_copy_of_the_text(populated_db):
    _alembic(populated_db, "upgrade", "head")
    sql = _rows(populated_db, "SELECT sql FROM sqlite_master WHERE name = 'chunks_fts'")[0][0]
    assert "content='chunks'" in sql and "porter" in sql
    tables = {r[0] for r in _rows(populated_db, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "chunks_fts_content" not in tables  # an ordinary FTS5 table would keep its own copy here


def test_the_three_triggers_keep_it_in_step(populated_db):
    _alembic(populated_db, "upgrade", "head")
    names = {r[0] for r in _rows(populated_db, "SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert {"chunks_fts_ai", "chunks_fts_ad", "chunks_fts_au"} <= names

    con = sqlite3.connect(populated_db)
    con.execute("INSERT INTO chunks (id, source_id, topic_id, chunk_text, chunk_index) VALUES (4, 1, 1, 'A brand new zebrafish chunk.', 3)")
    con.execute("UPDATE chunks SET chunk_text = 'Quicksort partitions around a pivot.' WHERE id = 2")
    con.execute("DELETE FROM chunks WHERE id = 3")
    con.commit()
    con.close()

    assert fts_match(populated_db, "zebrafish") == [4]  # insert
    assert fts_match(populated_db, "transitive") == []  # the old text of the updated chunk is gone
    assert fts_match(populated_db, "pivot") == [2]  # and the new text is there
    assert fts_match(populated_db, "halves") == []  # delete


def test_downgrade_removes_the_index_and_keeps_the_chunks(populated_db):
    _alembic(populated_db, "upgrade", "head")
    _alembic(populated_db, "downgrade", "0008")
    names = {r[0] for r in _rows(populated_db, "SELECT name FROM sqlite_master")}
    assert "chunks_fts" not in names and not {"chunks_fts_ai", "chunks_fts_ad", "chunks_fts_au"} & names
    assert _rows(populated_db, "SELECT COUNT(*) FROM chunks") == [(3,)]
    # Chunks can still be written and deleted without the triggers.
    con = sqlite3.connect(populated_db)
    con.execute("DELETE FROM chunks WHERE id = 1")
    con.commit()
    con.close()


def test_upgrading_again_after_a_downgrade_rebuilds_from_the_current_chunks(populated_db):
    _alembic(populated_db, "upgrade", "head")
    _alembic(populated_db, "downgrade", "0008")
    con = sqlite3.connect(populated_db)
    con.execute("DELETE FROM chunks WHERE id = 1")
    con.execute("INSERT INTO chunks (id, source_id, topic_id, chunk_text, chunk_index) VALUES (9, 1, 1, 'Added while the index was gone: aardvark.', 5)")
    con.commit()
    con.close()
    _alembic(populated_db, "upgrade", "head")
    assert fts_match(populated_db, "aardvark") == [9]
    assert fts_match(populated_db, "tombstone") == []


def test_it_matches_what_the_application_creates_for_databases_built_without_alembic(populated_db):
    """services/fts.ensure_fts and the migration must agree, or a self-healed database
    would behave differently from a migrated one."""
    from sqlalchemy import create_engine

    from app.services import fts

    _alembic(populated_db, "upgrade", "head")
    migrated = {
        r[0]: " ".join(r[1].split())
        for r in _rows(populated_db, "SELECT name, sql FROM sqlite_master WHERE name LIKE 'chunks_fts%' AND sql IS NOT NULL")
        if r[0] in _OURS  # FTS5 also creates its own shadow tables (chunks_fts_data, ...)
    }

    fresh = sqlite3.connect(":memory:")
    fresh.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, chunk_text TEXT)")
    fresh.commit()
    fresh.close()
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE chunks (id INTEGER PRIMARY KEY, chunk_text TEXT)")
    assert fts.ensure_fts(engine) is True
    with engine.connect() as connection:
        built = {
            r[0]: " ".join(r[1].split())
            for r in connection.exec_driver_sql(
                "SELECT name, sql FROM sqlite_master WHERE name LIKE 'chunks_fts%' AND sql IS NOT NULL"
            )
            if r[0] in _OURS
        }

    assert set(migrated) == set(built) == _OURS
    for name in migrated:
        assert migrated[name].lower().replace("if not exists ", "") == built[name].lower().replace("if not exists ", ""), name


def test_upgrade_works_on_an_empty_database(tmp_path):
    db_path = tmp_path / "fresh.db"
    _alembic(db_path, "upgrade", "head")
    assert _rows(db_path, "SELECT COUNT(*) FROM chunks_fts") == [(0,)]
