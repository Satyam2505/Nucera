import logging
from contextlib import asynccontextmanager
from typing import Optional, Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.database import SessionLocal
from app.routers import auth, courses, ingestion, mastery, quiz, retrieval, topics, tutor
from app.security import insecure_secret_problem
from app.services.quiz_jobs import interrupt_active_jobs
from app.services.reindex_service import count_stale

logger = logging.getLogger("uvicorn.error")


def check_secret_or_refuse(secret: Optional[str] = None, dev: Optional[bool] = None) -> None:
    """Refuse to start with a JWT secret anyone could guess.

    Tokens are signed with this secret, so with the well-known default (or a short
    one) anyone can mint a token for any account. Local development opts out with
    NUCERA_DEV=true, which only downgrades the refusal to a warning.
    """
    secret = config.JWT_SECRET_KEY if secret is None else secret
    dev = config.NUCERA_DEV if dev is None else dev
    problem = insecure_secret_problem(secret)
    if problem is None:
        return
    if dev:
        logger.warning("%s (allowed because NUCERA_DEV is set; never do this on a shared machine).", problem)
        return
    raise RuntimeError(
        f"Refusing to start: {problem}\n"
        "Set JWT_SECRET_KEY in backend/.env to a long random value, for example:\n"
        '    python -c "import secrets; print(secrets.token_urlsafe(48))"\n'
        "or, for local development only, set NUCERA_DEV=true."
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    check_secret_or_refuse()
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


def create_app(cors_origins: Optional[Sequence[str]] = None) -> FastAPI:
    """The application. `cors_origins` defaults to the CORS_ORIGINS setting; it is a
    parameter so the CORS behaviour can be tested without reloading modules."""
    application = FastAPI(title="Nucera", version="0.1.0", lifespan=lifespan)

    application.add_middleware(
        CORSMiddleware,
        # Exactly the origins in CORS_ORIGINS (never "*": the browser sends the login
        # token with credentials, which a wildcard would hand to any website).
        allow_origins=list(config.CORS_ORIGINS if cors_origins is None else cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(auth.router)
    application.include_router(courses.router)
    application.include_router(topics.router)
    application.include_router(ingestion.router)
    application.include_router(mastery.router)
    application.include_router(quiz.router)
    application.include_router(tutor.router)
    application.include_router(retrieval.router)

    @application.get("/")
    def root():
        return {"status": "ok", "service": "Nucera backend"}

    @application.get("/health")
    def health():
        return {"status": "healthy"}

    return application


app = create_app()
