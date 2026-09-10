# EduPilot AI — local scaffold (non-RAG)

Personal, solo-use adaptive tutor scaffold. Tracks topics, prerequisite
relationships, mastery, and study sessions. The tutor's answers and quiz
generation are stubbed — clearly marked `STUB` in the code — so the whole
app is runnable and demoable end to end today, ready for the real
RAG/local-LLM pipeline to be dropped in later without touching anything
else.

## Stack

- Backend: FastAPI + SQLAlchemy + Alembic, PostgreSQL
- Graph: NetworkX (rebuilt from Postgres on each request)
- Frontend: Next.js (App Router) + Tailwind CSS + react-flow
- No auth — single user

## 1. Start Postgres

```
docker compose up -d
```

This starts Postgres on `localhost:5432` (user/db/password: `postgres`).

## 2. Backend

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
python seed.py
uvicorn app.main:app --reload
```

API runs at http://localhost:8000 (docs at `/docs`).

`seed.py` loads a sample "Data Structures & Algorithms" course with 10
topics and realistic prerequisite links.

## 3. Frontend

```
cd frontend
npm install
copy .env.local.example .env.local
npm run dev
```

App runs at http://localhost:3000.

## Pages

- `/` — Progress dashboard (mastery per topic, mark a topic missed)
- `/graph` — Prerequisite graph, nodes colored by mastery status
- `/upload` — Add study material (paste text or upload a file) for a topic
- `/tutor` — Ask a question about a topic; see the stubbed answer plus any
  flagged unmastered prerequisites
- `/quiz` — Take the stubbed quiz for a topic; submitting updates mastery

## Where the stubs are

- `backend/app/services/embedding_service.py` — `generate_embedding()`
- `backend/app/services/tutor_service.py` — `generate_tutor_response()`
- `backend/app/services/quiz_service.py` — `generate_quiz()`

Swap these out for real Sentence Transformers embeddings, a FAISS/Chroma
vector store + Ollama-backed RAG, and LLM-driven quiz generation later —
nothing else in the app needs to change since every router only talks to
these functions.
