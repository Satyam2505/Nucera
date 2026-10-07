"""keyword (full-text) index over chunks, for hybrid search

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-08

Retrieval used vectors only, which find meaning but can miss an exact term (an
acronym, a formula, a name). This adds an SQLite FTS5 index over chunks.chunk_text
so retrieval can combine keyword and vector rankings.

It is an external-content table (no second copy of the text) kept up to date by
three triggers on `chunks`, so no application code writes to it; the existing
chunks are indexed by a one-off 'rebuild'. FTS5 is SQLite-only: on any other
database this migration does nothing and retrieval stays vector-only.

Written with its own SQL (no app imports) so it keeps working after the code
changes. Downgrade drops the triggers and the table; the chunks are untouched.
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS chunks_fts_ai AFTER INSERT ON chunks BEGIN
         INSERT INTO chunks_fts(rowid, chunk_text) VALUES (new.id, new.chunk_text);
       END""",
    """CREATE TRIGGER IF NOT EXISTS chunks_fts_ad AFTER DELETE ON chunks BEGIN
         INSERT INTO chunks_fts(chunks_fts, rowid, chunk_text) VALUES ('delete', old.id, old.chunk_text);
       END""",
    """CREATE TRIGGER IF NOT EXISTS chunks_fts_au AFTER UPDATE OF chunk_text ON chunks BEGIN
         INSERT INTO chunks_fts(chunks_fts, rowid, chunk_text) VALUES ('delete', old.id, old.chunk_text);
         INSERT INTO chunks_fts(rowid, chunk_text) VALUES (new.id, new.chunk_text);
       END""",
)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
        "chunk_text, content='chunks', content_rowid='id', "
        "tokenize='porter unicode61 remove_diacritics 2')"
    )
    for statement in _TRIGGERS:
        op.execute(statement)
    op.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    for name in ("chunks_fts_ai", "chunks_fts_ad", "chunks_fts_au"):
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    op.execute("DROP TABLE IF EXISTS chunks_fts")
