# Nucera — Handoff (updated 2026-10-07)

Read this first. The README covers setup; this file covers status, open
work and the decisions behind it.

## Where things stand

`main` already contains both `feat/course-modules` and `feat/hardening`
(`main`, `feat/hardening` and `origin/main` all point at `6c8c54f`), so there
is nothing left to merge from those two. Work since then lands on one branch
per phase of the review follow-up plan; nothing is pushed or merged to `main`
without the owner.

Verification at `6c8c54f`: backend `pytest` 285 passed; `tsc --noEmit` clean;
node tests 86 passed (graph 46, greeting 26, api-errors 7, quiz 7); headless
browser run with two accounts — every check passed, except one path only
verified against a stand-in model (see "Real-model findings").

### Migrating an older database

If your `backend/dev.db` predates the course/module hierarchy:

```
cd backend
copy dev.db dev.db.bak
alembic upgrade head
```

- 0005: each existing course name becomes a course with one "General" module.
- 0006: deletes the old placeholder ("[stub]") quiz questions — 24 in the
  original dev.db, including 3 orphans — and creates quiz sets/attempts. Quiz
  study sessions and mastery history are kept.
- Some existing topics may show a status that doesn't match their score
  until their next score change (no migration for that, deliberately).
- Saved graph layouts reset once (now keyed by course id).
- Optional: `python seed.py --email you@example.com` adds the sample DSA course.

## Follow-up plan (from the code review) — progress

One branch per phase, stacked on `main`, nothing pushed or merged.

| Phase | Branch | State |
|---|---|---|
| 1 Retrieval and prompt correctness | `feat/phase-1-retrieval-prompts` | done, awaiting your manual check |
| 2 Tutor experience (streaming, markdown, saved chats) | `feat/phase-2-tutor-experience` (on top of phase 1) | done, awaiting your manual check |
| 3 Quizzes (background jobs, DB guard, history screens) | `feat/phase-3-quizzes` (on top of phase 2) | done, awaiting your manual check |
| 4 Prerequisites and learning model | `feat/phase-4-prerequisites` (on top of phase 3) | prerequisites done; **mastery model is a proposal only, waiting for your answer** (`docs/mastery-model-proposal.md`) |
| 5 Retrieval breadth and inputs | `feat/phase-5-retrieval-inputs` (on top of phase 4) | done, awaiting your manual check |
| 6 Tooling and hardening | — | **not started as a branch.** A first, untested draft of the auth half is in `git stash` (`stash@{0}`, see below) |

### Phase 1 — what changed

- **Chunks now fit the embedder.** all-MiniLM-L6-v2 reads 256 tokens; chunks were
  ~650, so over a third (measured: median old chunk 411 tokens, ~62% visible) of
  each was invisible to search. Chosen fix: shrink chunks to ~200 tokens (800
  characters) and verify every chunk with the model's own tokenizer
  (`chunking.fit_to_token_limit`, wired through `services/indexing.py`), splitting
  further anything — maths, code, long numbers — that still overflows. Not a
  longer-input model, because: no new download or remote-code model; MiniLM works
  best on short passages; the 384-dim vectors and stored format stay valid; and on
  this CPU the prompt is read at ~18 tokens/s, so a smaller chunk is also a
  faster answer.
- **Re-indexing.** `backend/reindex.py` rebuilds chunks and embeddings from stored
  text (`services/reindex_service.py`), one transaction per source, idempotent,
  `--dry-run`, backs up a SQLite file first. The server logs a warning at startup
  while oversized chunks exist.
  *Page numbers:* `raw_text` is all pages joined, so they can't be read from it.
  They are rebuilt from the old chunks (a chunk never spans pages; the overlap
  between neighbours is removed again) and the result is checked against `raw_text`
  word for word. Sources that fail the check are skipped and reported, not guessed
  (`--allow-page-loss` overrides). The original upload file isn't stored, so
  re-extracting a PDF isn't possible.
- **Explicit model options.** `OLLAMA_NUM_CTX` (4096), `OLLAMA_TEMPERATURE` (0.2),
  `OLLAMA_MAX_OUTPUT_TOKENS` (600), `QUIZ_TEMPERATURE`, `QUIZ_TOKENS_PER_QUESTION`
  in `config.py` and `.env.example`, sent on every request.
- **Prompts stay inside the window.** `services/context_budget.py` (pessimistic
  3 chars/token) and a budget-aware `prompt_builder.build_budgeted_prompt`: question,
  topic, depth and gaps always stay; old conversation gives way first; study
  material goes in best-first, last chunk trimmed or dropped. The quiz reserves
  reply room per question and gives excerpts the rest; it now uses fewer whole
  excerpts rather than cutting each short. `llm_service` warns before sending a
  prompt over budget.
- **Tutor sends only relevant chunks.** Chunks below `RETRIEVAL_RELEVANCE_THRESHOLD`
  are no longer shown to the model; citations are exactly the chunks that were
  shown (a chunk dropped for room isn't cited).
- **Threshold re-checked, kept at 0.35.** `tests/relevance_corpus.py` (3 notes, 28
  on-topic and 16 off-topic questions) now backs `test_relevance_threshold.py`.
  New chunks: lowest on-topic top match 0.314, highest off-topic 0.290; at 0.35 no
  off-topic question passes and 3 of 28 on-topic ones are refused. 0.30 would
  separate this corpus perfectly but with a 0.01 margin, and a bigger topic (more
  chunks to match by chance) would erode it. Under the old chunks "load factor 0.75"
  scored 0.011.
- Also: `OLLAMA_TIMEOUT_SECONDS` default 120 -> 300 (the first real question timed
  out), tutor system prompt asks for ~250 words so the output cap doesn't cut
  answers mid-sentence.

### Phase 2 — what changed

- **Streaming.** `POST /ask/stream` answers as NDJSON, one object per line: `token`
  lines, then one `done` line (final answer, citations, grounded flag, prerequisite
  gaps) or an `error` line. `llm_service.generate_stream` reads Ollama's streaming
  API; `OLLAMA_TIMEOUT_SECONDS` bounds the wait for each piece, not the whole
  answer. A connection that drops part-way keeps the text that arrived and says so.
  `/ask` (blocking) still exists and behaves as before.
- **Stop / disconnect really stops the model.** `llm_service.StreamAbort` closes the
  connection to Ollama; the async body wrapper (`routers/tutor._stream_body`)
  triggers it when the browser goes away, even while the model is silent. Caveat:
  Ollama only sends headers once it has read the prompt, so a Stop pressed *before
  the first word* takes effect then (up to about a minute on this CPU), not instantly.
  Verified against the stub: the stub saw the connection close.
- **Saved conversations.** Table `chat_messages` (migration 0007 + test), `GET
  /chat/{topic_id}` (newest 200, oldest first; `?limit=`), `DELETE /chat/{topic_id}`.
  Ownership through `get_owned_topic`, listed in the authz route table. A turn (question
  + answer + a `chat` study session) is saved only when its answer completes, so a
  stopped or abandoned answer leaves nothing half-saved.
- **History comes from the server.** The model's follow-up context is the topic's
  last 6 saved messages; the `history` field the client used to send is gone (an
  old client that still sends it is ignored, and a forged "assistant" turn can't be
  injected). `query` is now 1-4000 characters and not blank.
- **UI.** `ChatView` loads the saved conversation, streams, has Stop (hands the
  unanswered question back to edit) and "Clear conversation" (confirm dialog).
  `Markdown.tsx` renders markdown (GFM tables), maths via KaTeX (`$..$`, `$$..$$`,
  and the `\( \)` / `\[ \]` small models write, rewritten by `lib/chat.normalizeMath`)
  and highlighted code; raw HTML is not rendered. New packages: react-markdown,
  remark-gfm, remark-math, rehype-katex, katex, rehype-highlight.
- **Bug found by the browser run:** pressing Stop also re-submitted the question
  (React reused the button element, which turned back into a submit button before the
  click's default action ran). Fixed with distinct keys + `preventDefault`.
- Verified: headless Chromium against a stub Ollama (21 checks: growth while
  streaming, bold/list/KaTeX inline+display/code/table, citations, reload, topic
  switch, Stop, Clear, no console errors, model connection closed) and against the
  real model (first word after 33 s instead of waiting ~119 s for the whole answer).
  Migration 0005-0007 run on a copy of the real `dev.db` (row counts preserved;
  original byte-identical).

### Phase 3 — what changed

- **Quiz generation is a background job.** `POST /quiz/{topic}/generate` returns 202
  with a job; `GET /quiz/jobs/{id}` is what the page polls (every 2.5 s). A daemon
  thread (`services/quiz_jobs.py`) writes the questions; `spawn` is the one place
  that starts it, so tests run it inline. Default is now 3 questions (`count` 1-10).
  **This changed the API:** generate used to return the finished quiz.
- **One model call per question**, each with a fresh few excerpts (`QUIZ_MAX_EXCERPTS`
  is now 3 per question, was 8 for the whole quiz) and a list of the questions
  already written, so they differ. Each question is committed as it is validated, so a
  failure keeps what exists: the job ends `partial` (a ready quiz with fewer
  questions, plus the reason) or `failed` (nothing written, no set left behind).
  A question that comes back unusable twice is skipped and the next gets a try.
  `QUIZ_MIN_VALID_QUESTIONS` is gone.
- **The in-flight guard is the database's.** `quiz_jobs` has a partial unique index
  over the active statuses, so two requests (or two processes) can't both start a
  job for a topic; the loser gets 409. A job that stops reporting progress
  (`QUIZ_JOB_STALE_SECONDS`, default 1500) is closed as dead, and at server start
  every job still marked active is closed (its worker died with the process): the
  questions it had written are kept as a partial quiz. Verified by killing and
  restarting the API mid-job.
- **A quiz being written is invisible** (`quiz_sets.status = 'generating'`): not in
  `GET /quiz`, history, `/quiz/sets/{id}` or grading (404). Migration 0008 + test;
  existing sets become `ready`. The test of the downgrade found that SQLite doesn't
  enforce `ON DELETE CASCADE` inside a migration, so it deletes the questions itself.
- **Past quizzes and history.** `GET /quiz/{topic}/history` (summaries),
  `GET /quiz/sets/{id}` (a taken one shows its results, an untaken one can still be
  taken; answers never before grading), `GET /sessions?topic_id=&course_id=&before_id=&limit=`
  (newest first, keyset paging, ownership-checked). UI: "Past quizzes" under the
  quiz, and a new **History** tab (grouped by day, topic filter, "Show older").
- **Ollama's random HTTP 500.** A real 2-question run died on the second call with an
  HTTP 500 (Ollama logged no reason; it is the failure the earlier handoff noted, probably
  its JSON-constrained sampling). With the new design the first question was kept as a
  partial quiz; and now a 5xx is retried once per question (`LLMResult.retryable`), while
  not-running / not-pulled / timeout still fail at once.
- Bug found by the existing embeddings test: every `commit()` expires ORM objects, so
  chunks loaded with `load_only` were re-read one by one *with* their embeddings;
  the worker now detaches them.
- Verified: headless Chromium against the stub model (24 checks: progress advancing,
  409 on a second start, leave-and-return and full reload resume the job, partial
  failure keeps the question and says why, total failure then Try again, past quizzes,
  history, no console errors) and the API-restart check above.

### Phase 4 — what changed

- **Loops are refused.** `POST /topics/prerequisites` now rejects any link that would
  close a circle, however long (A needs B, B needs A; or A -> B -> C -> A). The 400
  message names the chain, e.g. `That would create a loop (Sets -> Functions -> Sets):
  'Functions' already depends on 'Sets'.` (`graph_service.loop_path`: the new edge
  prerequisite -> topic closes a loop exactly when the topic already leads to the
  prerequisite). The other checks (itself, duplicate, other course, ownership) are
  unchanged and still come first. Old data that already contains a loop doesn't break
  the graph or the learning order, and unrelated links can still be added.
- **Removing a prerequisite.** `DELETE /topics/{topic_id}/prerequisites/{prerequisite_topic_id}`
  -> 204; 404 if either topic isn't the caller's or the link isn't there. In the authz table.
- **Graph UI.** In a topic's panel in the Knowledge graph: an x on each prerequisite and an
  "Add a prerequisite" picker. The picker leaves out the topic itself, its existing
  prerequisites and every topic that already depends on it (those would make a loop), via
  `lib/graph-edit.candidatePrerequisites` (node-tested); if the page is stale and the server
  still refuses, the panel shows the server's reason and nothing changes. After a change the
  whole graph is reloaded, so edges, learning path and the tutor's prerequisite gaps agree.
- **Mastery model: not built.** The proposal (estimate + memory strength with decay, and a
  "what to study next" ranking) is in `docs/mastery-model-proposal.md`, with five decisions
  I need from you. Nothing in the mastery code changed.
- Verified: headless Chromium (13 checks: add, picker leaves out loop candidates, a
  stale-page loop refused with the reason shown, remove; the only "failure" is Chromium
  logging the deliberate HTTP 400).

### Phase 5 — what changed

- **Hybrid search.** An FTS5 index over `chunks.chunk_text` (external-content table, `porter
  unicode61` tokenizer, three triggers so nothing in the app writes to it; migration 0009
  backfills existing chunks and has its own SQL copy, tested to equal `services/fts.ensure_fts`).
  `retrieve_relevant_chunks` merges the vector and keyword rankings by reciprocal rank fusion
  (`RETRIEVAL_HYBRID`, `HYBRID_RRF_K`). SQLite only: on Postgres retrieval stays vector-only.
  Questions are turned into quoted terms (no FTS syntax can leak in; hostile strings are
  tested) after dropping stopwords.
- **What it actually buys.** Not a different top result in my tests (vectors already rank the
  right chunk first for a bare rare word) but a trustworthy *relevance* signal: "tombstone"
  has cosine 0.27, under the 0.35 threshold, so on similarity alone the tutor refused it.
  Results now carry `keyword_match` = the chunk contains *every* searchable word of the
  question, and the tutor treats `similarity >= threshold OR keyword_match` as relevant
  (`tutor_service.is_relevant`). On the labelled corpus: 27 of 28 on-topic questions accepted
  (25 before), still **0 of 16 off-topic**, none of which has any keyword match. The threshold
  stays 0.35.
- **Course-wide fallback.** If nothing in the topic is relevant, the search widens to the same
  course (never another course or user; this topic's chunks are excluded as already judged).
  The prompt says the passages come from other topics, and citations gain a `topic` field,
  shown in the chat as "Source, p. 7 · from Hashing". Saved with the conversation.
- **.docx and .pptx uploads** (python-docx, python-pptx, added to requirements.txt). Word:
  paragraphs and tables (a row per line) in order, one untagged page. PowerPoint: one page
  per slide (slide number = page number), title, text boxes, tables, groups and speaker notes.
  Files are checked as real zip/Office files before parsing, with an expansion-size cap
  against zip bombs; legacy .doc/.ppt are refused.
- **OCR, local.** RapidOCR (ONNX, CPU) in `services/ocr_service.py`, optional via
  `requirements-ocr.txt`. A PDF page with almost no text and a picture is OCR'd; pages with
  text are not; confidence-filtered, reading-order sorted. Limited to `OCR_MAX_PAGES` (30)
  scanned pages per upload because it runs inside the request (a few seconds a page). A fully
  scanned PDF without OCR is refused with instructions. Verified with the real engine on a
  rendered page.
- **Environment trap found:** `pip install rapidocr-onnxruntime` upgraded numpy 1.26.4 to 2.5
  (via OpenCV 5), which could break torch/sentence-transformers. `requirements-ocr.txt` pins
  `opencv-python==4.10.0.84`; `pip check` is clean with numpy 1.26.4 restored.

### Phase 5 — things to know

- Your `dev.db` needs `alembic upgrade head` (it is still on the pre-0005 schema) before it
  has the keyword index; until then the app has no hybrid search.
- OCR is the slow path of an upload; a 30-page scan can take a couple of minutes with no
  progress shown. Not streamed or backgrounded yet.

### Phase 6 — where it was left

Not done: CI workflow, requirements split (dev vs runtime), macOS/Linux README steps, and
the auth items. A draft of the auth half was written and then shelved untested with
`git stash` (on top of `feat/phase-5-retrieval-inputs`; `git stash list` shows it, `git
stash show -p` shows it, `git stash pop` brings it back). What it contains:

- `app/main.py` becomes an app factory (`create_app`) and refuses to start when
  `JWT_SECRET_KEY` is the built-in default or under 32 characters, unless `NUCERA_DEV=true`.
- Emails normalised to lower case (`security.normalize_email`, a case-insensitive lookup
  for old rows, a functional unique index `uq_users_email_lower` in the model).
- `services/login_limiter.py`: in-memory failed-login limit per (address, email) plus a
  looser per-address cap, with a 429 and `Retry-After`; wired into `/auth/login`.
- `CORS_ORIGINS` setting (comma separated, `*` refused).

Still missing before that draft is usable: **migration 0010** (lower-case existing emails,
refusing with a clear message if two accounts differ only by capitalisation, then create the
index) and its test, tests for everything above, `NUCERA_DEV=true` set in `tests/conftest.py`
and `.env.example`, and the full suite run. Nothing in it was run beyond `import app.main`.

### Phase 4 — things to know

- The loop check and the insert are not one atomic step, so two simultaneous adds could in
  theory create a loop between them. Acceptable for a single-user app; a database can't
  express "acyclic" as a constraint.

### Phase 3 — things to know

- No cancel button: a started job runs to the end or to its first model failure.
- One question costs about two minutes on this CPU (prompt ~35 s + ~75 s of writing),
  so 3 questions is about 6 minutes: roughly what 5 used to cost, but with progress and
  without losing everything to one failure.
- A topic deleted mid-run is noticed before the next write; there is a sub-second
  window in which one more question row could be written for a deleted set.

### Phase 2 — things to know

- **Follow-ups are retrieved on their own text.** "Why does that matter?" has no words
  in common with the notes, so it is refused by the relevance threshold. The saved
  history is given to the model, but it doesn't help retrieval. Possible fix: search
  with the previous question prepended for short follow-ups. Not done.
- Switching topic while an answer is being written stops it (nothing is saved).

### Phase 1 — things to know

- **`backend/dev.db` is still on the pre-hierarchy schema** (no `topics.module_id`):
  migrations 0005/0006 were never applied to it. Back it up and run
  `alembic upgrade head` before starting the app on it. `reindex.py` itself only
  needs `sources` and `chunks`, which exist in both schemas. Its one source
  (3 small chunks) already fits, so there is nothing to re-index in it today.
- A 4th, lower-scoring chunk from another document (0.381) was sent and cited for
  a hash-table question. That is the threshold working as specified, but a cut-off
  *relative to the best match* would be tighter. Not done; your call.
- Ollama truncates an oversized prompt to about half the window and keeps only the
  first 4 tokens, i.e. it drops the system prompt. Hence the pre-send warning.

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
- Tutor answers (2026-10-07, Phase 1): prompt processing ~18 tokens/s, generation
  ~4 tokens/s. A grounded answer with an 894-token prompt took 163 s end to end
  (default `OLLAMA_TIMEOUT_SECONDS` of 120 had failed it). Streaming (Phase 2) will
  make that wait readable. Real tokenization was ~4.8 chars/token on prose, so the
  3 chars/token budget estimate is conservative.

## Known limitations and next steps

1. **Quiz speed on CPU.** Progress is now shown and the default is 3 questions
   (Phase 3), but a question still takes about two minutes. A faster model or a GPU
   is the remaining lever.
2. ~~In-flight generation guard is per-process~~ — moved into the database (Phase 3).
3. ~~Tutor prompt received all 5 retrieved chunks~~ — fixed in Phase 1.
   Chat history is now saved server-side (Phase 2).
4. ~~No UI for prerequisites, session history or past quizzes~~ — all have screens now (Phases 3-4).
5. `JWT_SECRET_KEY` has an insecure dev default — set it for anything beyond
   local use. CORS allows only localhost:3000/3002.
6. Minor: `datetime.utcnow()` deprecation warnings in tests; first request after
   startup waits for the embedding model to load. (The unused `UserLogin` /
   `ChunkOut` schemas were removed.)

## Working conventions (for whoever picks this up)

- Run browsers headless and servers in the background — never pop windows
  on the user's screen.
- Never migrate the real `backend/dev.db` without a backup copy first.
- Migrations don't import `app.models`; test them on a populated copy.
- Frontend: check `frontend/node_modules/next/dist/docs/` before using
  Next.js APIs (Next 16 differs from older versions — see `frontend/AGENTS.md`).
