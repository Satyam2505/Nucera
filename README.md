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
- **Study material** — upload PDF, Word (.docx), PowerPoint (.pptx), .txt or .md
  (up to 20 MB) or paste text per topic. Slides keep their slide number as the page;
  scanned PDFs are read with local OCR if you install it (see below). Text is chunked to fit the embedding model, embedded and stored; failed ingests leave nothing behind.
- **Grounded tutor** — answers use only the retrieved passages of your material,
  cite source and page, adapt depth to your mastery, and flag unmastered
  prerequisites. Search combines meaning (embeddings) with exact keywords (SQLite
  FTS5), so an acronym or rare term is found too. If the topic's own material has
  nothing relevant it looks at the rest of the course (citations then say which
  topic each passage came from); if nothing is relevant anywhere, it says so
  instead of guessing.
  Answers stream in as they are written (with a Stop button), render as markdown
  with maths and syntax-highlighted code, and each topic's conversation is saved
  on the server so it survives a reload or a topic switch.
- **Generated quizzes** — multiple-choice questions written by the local LLM
  from your material, validated server-side, each with an explanation and a
  citation. Writing happens in the background, one question at a time (3 by
  default) with a progress bar; leaving the page doesn't stop it, and if the model
  fails part-way the questions already written are kept. One graded attempt per
  quiz; old quizzes and attempts are kept and can be reopened under "Past quizzes".
- **Study history** — a timeline of every question you asked the tutor, quiz you
  took and self-report, with the mastery change each caused, filterable by topic.
- **Mastery** — 0–100 per topic. ≥ 80 mastered, 1–79 in progress, 0 unmastered;
  "missed" is set manually and cleared by the next improvement. Revision list
  for topics you want to revisit.
- **Knowledge graph** — interactive prerequisite graph per course, tinted and
  filterable by module. Prerequisites are added and removed from a topic's panel in
  the graph; a link that would make a loop (A needs B needs A, or any longer circle)
  is refused with the chain shown.

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

### Optional: OCR for scanned PDFs

A PDF whose pages are pictures has no text to read. Install local OCR (RapidOCR, CPU
only, nothing leaves your machine) and such pages are read automatically:

```
cd backend
pip install -r requirements-ocr.txt
```

It takes a few seconds per page and runs inside the upload, so one upload is limited to
`OCR_MAX_PAGES` (30) scanned pages. Without it, a fully scanned PDF is refused with a
message saying so. `requirements-ocr.txt` pins OpenCV to a build that works with the
pinned numpy; installing `rapidocr-onnxruntime` on its own would upgrade numpy.

### Re-indexing after a chunking change

Chunks used to be ~650 tokens, but the embedding model (all-MiniLM-L6-v2) reads
only 256 tokens of each, so most of every chunk was invisible to search. Chunks
are now ~200 tokens and always checked against the model's real tokenizer. Material
uploaded before that is still in the old, oversized chunks; the server logs a
warning at startup if any exist. Stop the server, then:

```
cd backend
python reindex.py --dry-run     # see what would change
python reindex.py               # re-chunk and re-embed
```

This rebuilds chunks from the text already stored (no re-upload needed), keeps PDF
page numbers (rebuilt from the old chunks and checked against the stored text),
and copies a SQLite database to `dev.db.bak-<timestamp>` first. A source whose page
numbers can't be verified is skipped and reported; `--allow-page-loss` re-indexes
it without them. Sources that already fit are left alone unless you pass `--force`.

### Upgrading an existing database

Always back up first, then migrate:

```
cd backend
copy dev.db dev.db.bak
alembic upgrade head
```

Migration 0005 turns each old course name into a course with one "General"
module. Migration 0006 removes the old placeholder quiz questions (quiz history
in study sessions is kept). Migration 0007 adds the saved tutor conversations
(old chats were never stored, so every topic starts empty). Migration 0008 adds
background quiz jobs and a status on quiz sets (every existing quiz stays usable).
Migration 0009 adds the keyword search index over existing chunks (SQLite only).

## Configuration

All settings are environment variables with working defaults; see
`backend/.env.example` for the full list (database, JWT secret, Ollama model
context window and temperature, relevance threshold, upload limit, quiz generation).
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
  services/   chunking, embedding, indexing, reindex, retrieval, graph,
              prompt builder, context budget, llm, tutor, quiz, mastery, ordering
  ownership.py  every "does this belong to the caller" lookup
backend/reindex.py          rebuild chunks/embeddings from stored text
backend/alembic/versions/   0001 … 0009
frontend/app/               / (home) and /course/[courseId]
frontend/components/course/ chat, quiz, graph, mastery, sources, module rail
frontend/lib/               API client, app state, pure helpers + tests
brand/                      logo source files
docs/                       handoff notes; docs/reports/ holds the project PDFs
```

See [`docs/HANDOFF.md`](docs/HANDOFF.md) for current status, known limitations and next steps.
