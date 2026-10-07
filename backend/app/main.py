import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import SessionLocal
from app.routers import auth, courses, ingestion, mastery, quiz, retrieval, topics, tutor
from app.services.quiz_jobs import interrupt_active_jobs
from app.services.reindex_service import count_stale

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _warn_if_chunks_are_stale()
    _close_orphaned_quiz_jobs()
    yield


def _warn_if_chunks_are_stale() -> None:
    """Chunks written when chunks were larger are partly invisible to search;
    say so once at startup rather than let search quietly get worse."""
    db = SessionLocal()
    try:
        chunks, sources = count_stale(db)
    except Exception:  # e.g. the database isn't migrated yet; startup must not depend on this
        return
    finally:
        db.close()
    if chunks:
        logger.warning(
            "%d chunks in %d sources are longer than the embedding model reads, so part "
            "of each is invisible to search. Stop the server and run `python reindex.py`.",
            chunks,
            sources,
        )


def _close_orphaned_quiz_jobs() -> None:
    """A quiz job still marked active when the server starts lost its worker with
    the previous process; close it (keeping any questions it had written) so it
    stops blocking its topic."""
    db = SessionLocal()
    try:
        closed = interrupt_active_jobs(db)
    except Exception:  # e.g. the database isn't migrated yet
        db.rollback()
        return
    finally:
        db.close()
    if closed:
        logger.warning("Closed %d quiz generation job(s) left running by the last server.", closed)


app = FastAPI(title="Nucera", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # 3002 covers local dev when 3000 is already taken by another project
    # on the same machine (Next.js auto-picks the next free port).
    allow_origins=["http://localhost:3000", "http://localhost:3002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(topics.router)
app.include_router(ingestion.router)
app.include_router(mastery.router)
app.include_router(quiz.router)
app.include_router(tutor.router)
app.include_router(retrieval.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "Nucera backend"}


@app.get("/health")
def health():
    return {"status": "healthy"}
