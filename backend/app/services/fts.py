"""Keyword (full-text) search over chunks, using SQLite's FTS5, to sit beside the
vector search.

Embeddings are good at meaning and weak at exact terms: an acronym, a formula, a
name or a rare word ("3NF", "tombstone") may not move the vector at all. FTS5 is
the opposite, so retrieval uses both and merges the rankings (retrieval_service).

The index is an *external-content* FTS5 table over `chunks.chunk_text`, kept in
step by triggers, so nothing in the application writes to it: inserting, editing or
deleting a chunk (including a bulk delete, as re-indexing does) updates it. It is a
SQLite feature; on any other database the helpers report "unavailable" and
retrieval falls back to vectors alone.

The migration (0009) creates the same objects with its own copy of this SQL; the
`ensure_fts` here exists for databases built without Alembic (the test schema) and
as a self-heal, and is a no-op when the table already exists.
"""

import logging
import re
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

FTS_TABLE = "chunks_fts"

# `porter` stems (collision/collisions), `unicode61` folds case and accents.
CREATE_TABLE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
    "chunk_text, content='chunks', content_rowid='id', "
    "tokenize='porter unicode61 remove_diacritics 2')"
)
CREATE_TRIGGERS = (
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
REBUILD = "INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')"


def _table_exists(connection) -> bool:
    return (
        connection.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": FTS_TABLE},
        ).first()
        is not None
    )


def ensure_fts(engine: Engine) -> bool:
    """Create the index (and fill it from existing chunks) if it is missing.
    Returns whether keyword search is available. Never raises."""
    if engine.dialect.name != "sqlite":
        return False
    try:
        with engine.begin() as connection:
            existed = _table_exists(connection)
            connection.execute(text(CREATE_TABLE))
            for statement in CREATE_TRIGGERS:
                connection.execute(text(statement))
            if not existed:
                connection.execute(text(REBUILD))
        return True
    except Exception:  # e.g. an SQLite build without FTS5
        logger.warning("Keyword search is unavailable (FTS5 could not be set up).", exc_info=True)
        return False


def fts_available(db: Session) -> bool:
    bind = db.get_bind()
    if bind.dialect.name != "sqlite":
        return False
    with bind.connect() as connection:
        return _table_exists(connection)


# --- building a query from a question --------------------------------------------------------------

# Words that carry no search value. Kept small and English-only: the porter tokenizer
# is English too. A question that is nothing but these has no keyword query at all.
STOPWORDS = frozenset(
    """a about above after again all also am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers him his how i if in into is it its just me more most my
    no nor not of off on once only or other our out over own same she should so some such than
    that the their theirs them then there these they this those through to too under until up
    very was we were what when where which while who whom why will with would you your yours
    tell explain describe define please""".split()
)
MAX_TERMS = 12

_WORD = re.compile(r"\w+", re.UNICODE)


def query_terms(question: str) -> List[str]:
    """The question's searchable words: lower-cased, without stopwords, de-duplicated
    in order, at most MAX_TERMS. One-letter words are dropped unless they are digits."""
    seen: Dict[str, None] = {}
    for word in _WORD.findall(question.lower()):
        if word in STOPWORDS or (len(word) < 2 and not word.isdigit()):
            continue
        seen.setdefault(word, None)
    return list(seen)[:MAX_TERMS]


def match_expressions(terms: Sequence[str]) -> Tuple[Optional[str], Optional[str]]:
    """(strict, loose) FTS5 expressions: every term, or any term. Each term is quoted,
    so a word can never be read as FTS syntax. (None, None) if there are no terms."""
    if not terms:
        return None, None
    quoted = [f'"{term}"' for term in terms]
    return " AND ".join(quoted), " OR ".join(quoted)


def search(
    db: Session,
    expression: str,
    user_id: int,
    topic_id: Optional[int] = None,
    course_id: Optional[int] = None,
    source_ids: Optional[Sequence[int]] = None,
    limit: int = 30,
) -> List[int]:
    """Chunk ids matching `expression`, best first (BM25), restricted to chunks in
    `user_id`'s own courses (and to the topic / course / sources given)."""
    clauses = ["chunks_fts MATCH :expression", "courses.user_id = :user_id"]
    params: Dict[str, object] = {"expression": expression, "user_id": user_id, "limit": limit}
    if topic_id is not None:
        clauses.append("chunks.topic_id = :topic_id")
        params["topic_id"] = topic_id
    if course_id is not None:
        clauses.append("courses.id = :course_id")
        params["course_id"] = course_id
    if source_ids:
        placeholders = ", ".join(f":source_{i}" for i in range(len(source_ids)))
        clauses.append(f"chunks.source_id IN ({placeholders})")
        params.update({f"source_{i}": sid for i, sid in enumerate(source_ids)})

    sql = f"""
        SELECT chunks.id
        FROM chunks_fts
        JOIN chunks ON chunks.id = chunks_fts.rowid
        JOIN topics ON topics.id = chunks.topic_id
        JOIN modules ON modules.id = topics.module_id
        JOIN courses ON courses.id = modules.course_id
        WHERE {' AND '.join(clauses)}
        ORDER BY bm25(chunks_fts)
        LIMIT :limit
    """
    try:
        return [row[0] for row in db.execute(text(sql), params)]
    except Exception:
        # A malformed expression or a missing index must cost the keyword half of the
        # search, never the whole search.
        logger.warning("Keyword search failed; using vector search alone.", exc_info=True)
        db.rollback()
        return []
