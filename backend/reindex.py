"""Rebuild stored chunks and embeddings from the text already in the database.

Run this after the chunk size or the embedding model changes (Phase 1 shrank
chunks to fit the embedder's 256-token input; chunks written before that are
partly invisible to search). Stop the API server first.

    python reindex.py --dry-run      # show what would change, write nothing
    python reindex.py                # re-index sources whose chunks are too long
    python reindex.py --force        # re-index every source

A SQLite database is copied to <name>.bak-<timestamp> before anything is
written. Page numbers are rebuilt from the old chunks and checked against the
stored text; a source where that check fails is skipped and reported, unless
you pass --allow-page-loss to re-index it without page numbers.
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from app.database import SessionLocal, engine
from app.services.reindex_service import SourceResult, reindex_all


def backup_sqlite() -> Path:
    path = Path(engine.url.database or "")
    if not path.is_file():
        raise SystemExit(f"Cannot back up: {path} is not a file. Nothing was changed.")
    target = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(path, target)
    return target


def describe(result: SourceResult) -> str:
    head = f"  [{result.source_id}] {result.title}: "
    if result.status == "up_to_date":
        return head + f"already fits ({result.old_chunks} chunks), left alone"
    if result.status == "reindexed":
        note = "" if result.pages_preserved else " (page numbers LOST)"
        return head + f"{result.old_chunks} -> {result.new_chunks} chunks{note}"
    return head + f"{result.status.upper()}: {result.reason}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Re-chunk and re-embed stored sources.")
    parser.add_argument("--dry-run", action="store_true", help="report only; change nothing")
    parser.add_argument("--force", action="store_true", help="re-index sources that already fit")
    parser.add_argument(
        "--allow-page-loss",
        action="store_true",
        help="re-index a source whose page numbers can't be rebuilt, without them",
    )
    parser.add_argument(
        "--i-have-a-backup",
        action="store_true",
        help="required for a non-SQLite database, which this script does not back up",
    )
    args = parser.parse_args(argv)

    if not args.dry_run:
        if engine.url.get_backend_name() == "sqlite":
            print(f"Backed up the database to {backup_sqlite()}")
        elif not args.i_have_a_backup:
            print("This is not a SQLite database, so no automatic backup was made.")
            print("Back it up (pg_dump) and re-run with --i-have-a-backup. Nothing was changed.")
            return 2

    print("Loading the embedding model (the first run is slow)...")
    db = SessionLocal()
    try:
        results = reindex_all(
            db,
            force=args.force,
            allow_page_loss=args.allow_page_loss,
            dry_run=args.dry_run,
            on_result=lambda r: print(describe(r), flush=True),
        )
    finally:
        db.close()

    counts = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    verb = "would be re-indexed" if args.dry_run else "re-indexed"
    print(
        f"\n{len(results)} sources: {counts.get('reindexed', 0)} {verb}, "
        f"{counts.get('up_to_date', 0)} already fit, {counts.get('skipped', 0)} skipped, "
        f"{counts.get('failed', 0)} failed."
    )
    return 1 if counts.get("failed") or counts.get("skipped") else 0


if __name__ == "__main__":
    sys.exit(main())
