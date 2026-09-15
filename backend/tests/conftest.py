import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Must be set before any `app.*` module is imported — app.database reads it
# at import time.
TEST_DB_PATH = BACKEND_DIR / "tests" / "test.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"

import pytest  # noqa: E402

from app import models  # noqa: E402,F401  (registers tables on Base.metadata)
from app.database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Every test starts from an empty database."""
    yield
    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture()
def sample_pdf_bytes() -> bytes:
    """A tiny two-page PDF built at test time so no binary fixture needs
    committing to the repo."""
    import fitz

    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text(
        (72, 72),
        "Database normalization removes redundant data.\n"
        "It organizes tables using normal forms such as 1NF, 2NF and 3NF.",
    )
    page2 = doc.new_page()
    page2.insert_text(
        (72, 72),
        "A binary search tree keeps left children smaller than their parent.\n"
        "This ordering enables fast lookups, insertions and deletions.",
    )
    data = doc.tobytes()
    doc.close()
    return data
