# Nucera — Handoff (updated 2026-10-06, overnight session)

Read this first. The README covers setup; this file covers status, open
work and the decisions behind it.

## Where things stand

Two unmerged branches, stacked on `main`, nothing pushed:

```
main (7a907c0)
 └─ feat/course-modules   Course → Module → Topic hierarchy
     └─ feat/hardening    security, mastery rule, real quizzes, upload robustness
```

`feat/hardening` contains everything; merging it into `main` brings both.
Each commit on both branches was reviewed before the next one started.

Verification at the tip of `feat/hardening`: backend `pytest` 285 passed;
`tsc --noEmit` clean; node tests 60 passed (graph 46, api-errors 7, quiz 7);
headless browser run with two accounts — every check passed, except one
path only verified against a stand-in model (see "Real-model findings").

### To merge and migrate your database

```
git checkout main
git merge --ff-only feat/hardening
cd backend
copy dev.db dev.db.bak
alembic upgrade head
```

- 0005: each existing course name becomes a course with one "General" module.
- 0006: deletes the old placeholder ("[stub]") quiz questions — 24 in your
  dev.db, including 3 orphans — and creates quiz sets/attempts. Quiz study
  sessions and mastery history are kept.
- Some existing topics may show a status that doesn't match their score
  until their next score change (no migration for that, deliberately).
- Saved graph layouts reset once (now keyed by course id).
- Optional: `python seed.py --email you@example.com` adds the sample DSA course.

## What was built

### feat/course-modules (5 commits)

- Tables `courses` (owner, unique name per owner) and `modules` (ordered);
  topics have `module_id` + `position`. Old `topics.course` string removed.
- API: `/courses` CRUD, `/courses/{id}/tree`, module CRUD + reorder, topic
  PATCH (rename/move within course) + DELETE; prerequisites can't cross courses.
- UI: `/course/[courseId]`; collapsible module rail with add/rename/move/delete;
  course menu (rename/delete); mastery grouped by module; graph tinted and
  filterable by module; "Course · Module" labels; upload picker grouped.

### feat/hardening (8 commits)

- **Auth everywhere.** Every route except register/login/`/`/`/health`
  requires a token and checks ownership through course → user (404 for
  others' data). Retrieval and graph helpers take a required `user_id`.
  Frontend signs out cleanly on an expired token; errors show readable text.
- **Mastery rule** in `services/mastery_service.py`: ≥ 80 mastered, 1–79
  in progress, 0 unmastered; "missed" is manual, cleared by the next real
  increase. `PUT /mastery` takes only `score`.
- **Real quizzes** (`services/quiz_service.py`): local LLM writes multiple-choice
  questions from evenly spread excerpts of the topic's material; strict
  validation, one retry on unusable output, options shuffled server-side,
  citations taken from the excerpts (never model text). `GET /quiz/{topic}`
  never generates; `POST /quiz/{topic}/generate` does (409 if no material or
  already generating, 503 if the model is unavailable). One graded attempt
  per set, enforced by a DB unique constraint. Answers are never sent before
  grading. New quiz UI with results, explanations and citations.
- **Uploads**: .pdf/.txt/.md only, 20 MB cap (also for pasted text), PDF magic-
  byte check, clear 413/415/422 errors; source + chunks are written in one
  transaction after embedding succeeds; upload route no longer blocks the
  server. Citations only for chunks above the relevance threshold; chunk
  overlap and long-sentence splits start on word boundaries.

## Real-model findings (llama3.2:3b on this machine's CPU)

- About 5 tokens/s; a 5-question quiz reply is ~1,100–1,400 tokens, i.e.
  4–5 minutes. Of 5 real generations: 2 succeeded, 2 hit the old 240 s
  timeout, 1 failed inside Ollama itself (HTTP 500, no reason logged). Every
  failure was reported cleanly with nothing stored. The quiz timeout default
  was raised to 600 s because of this.
- The "switch topic while a quiz is generating" path was verified against a
  stand-in model (no duplicate quiz, 409 "already in progress" handled); with
  the real model both attempts failed on the model side, as above.
- Generated questions were valid and cited; their *quality* was not assessed.

## Known limitations and next steps

1. **Quiz speed on CPU.** Options: stream generation progress, default to 3
   questions, or recommend a faster model / GPU. Worth deciding with real use.
2. **In-flight generation guard is per-process** (fine for `uvicorn --reload`
   single worker). The DB constraint still protects grading data.
3. **Tutor prompt** still receives all 5 retrieved chunks, including weak ones
   (only citations were tightened). Chat history is client-side only.
4. **No UI** for adding prerequisites, viewing study-session history, or
   browsing past quizzes (all stored server-side).
5. `JWT_SECRET_KEY` has an insecure dev default — set it for anything beyond
   local use. CORS allows only localhost:3000/3002.
6. Minor: `datetime.utcnow()` deprecation warnings in tests; unused schemas
   `UserLogin` / `ChunkOut`; first request after startup waits for the
   embedding model to load.

## Working conventions (for whoever picks this up)

- Run browsers headless and servers in the background — never pop windows
  on the user's screen.
- Never migrate the real `backend/dev.db` without a backup copy first.
- Migrations don't import `app.models`; test them on a populated copy.
- Frontend: check `frontend/node_modules/next/dist/docs/` before using
  Next.js APIs (Next 16 differs from older versions — see `frontend/AGENTS.md`).
