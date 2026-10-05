# Nucera

A personal adaptive tutor that runs entirely on your machine. Organise what
you study as **courses → modules → topics**, upload your own material, ask
questions answered only from that material by a local LLM, take quizzes
generated from it, and track mastery across a prerequisite graph.

No cloud calls: embeddings run locally (sentence-transformers) and the LLM is
served by [Ollama](https://ollama.com).

## Features

- **Accounts** — email + password (JWT). Every course, source and score is
  private to its owner; all API routes enforce ownership.
- **Course structure** — courses contain ordered modules (chapters), which
  contain ordered topics. Rename, reorder, move and delete from the course page.
- **Study material** — upload PDF / .txt / .md (up to 20 MB) or paste text per
  topic. Text is chunked, embedded and stored; failed ingests leave nothing behind.
- **Grounded tutor** — answers use only the retrieved passages of your material,
  cite source and page, adapt depth to your mastery, and flag unmastered
  prerequisites. If nothing relevant is found, it says so instead of guessing.
- **Generated quizzes** — multiple-choice questions written by the local LLM
  from your material, validated server-side, each with an explanation and a
  citation. One graded attempt per quiz; old quizzes and attempts are kept.
- **Mastery** — 0–100 per topic. ≥ 80 mastered, 1–79 in progress, 0 unmastered;
  "missed" is set manually and cleared by the next improvement. Revision list
  for topics you want to revisit.
- **Knowledge graph** — interactive prerequisite graph per course, tinted and
  filterable by module.

## Stack

- Backend: FastAPI, SQLAlchemy 2, Alembic, SQLite by default (Postgres optional),
  NetworkX, sentence-transformers (`all-MiniLM-L6-v2`), PyMuPDF, Ollama
- Frontend: Next.js 16 (App Router), React 19, Tailwind CSS v4, shadcn/ui, React Flow

## Setup

### 1. Ollama (for tutor answers and quizzes)

Install Ollama, then:

```
ollama pull llama3.2:3b
ollama serve
```

Without it the app still runs: the tutor replies that the model is unavailable
and quiz generation returns a clear error.

### 2. Backend

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

API at http://localhost:8000 (interactive docs at `/docs`). The first upload or
question after startup is slower while the embedding model loads.

Optional sample data — a "Data Structures & Algorithms" course with 4 modules
and 10 linked topics, attached to an account you've already registered:

```
python seed.py --email you@example.com
```

Postgres instead of SQLite: `docker compose up -d`, then set `DATABASE_URL`
in `.env` (see `.env.example`).

### 3. Frontend

```
cd frontend
npm install
copy .env.local.example .env.local
npm run dev
```

App at http://localhost:3000.

### Upgrading an existing database

Always back up first, then migrate:

```
cd backend
copy dev.db dev.db.bak
alembic upgrade head
```

Migration 0005 turns each old course name into a course with one "General"
module. Migration 0006 removes the old placeholder quiz questions (quiz history
in study sessions is kept).

## Configuration

All settings are environment variables with working defaults; see
`backend/.env.example` for the full list (database, JWT secret, Ollama model
and timeouts, relevance threshold, upload limit, quiz generation).
Set `JWT_SECRET_KEY` to a real secret for anything beyond your own machine.

## Tests

```
cd backend && pytest
cd frontend && npx tsc --noEmit
```

Frontend logic tests (`frontend/lib/*.test.ts`) use only Node's built-in
`assert`; each file's header shows how to run it.

The backend suite loads the real embedding model, so it takes a minute or two;
the LLM is always mocked.

## Project layout

```
backend/app/
  routers/    auth, courses, topics, ingestion (/sources), tutor (/ask),
              quiz, mastery, retrieval
  services/   chunking, embedding, retrieval, graph, prompt builder, llm,
              tutor, quiz, mastery, ordering
  ownership.py  every "does this belong to the caller" lookup
backend/alembic/versions/   0001 … 0006
frontend/app/               / (home) and /course/[courseId]
frontend/components/course/ chat, quiz, graph, mastery, sources, module rail
frontend/lib/               API client, app state, pure helpers + tests
```

See `HANDOFF.md` for current status, known limitations and next steps.
