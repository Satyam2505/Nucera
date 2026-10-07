# Proposal: a mastery model with decay, and "what to study next"

Status: **implemented on branch `feat/mastery-model`, using my recommended answers.**
The owner asked for the remaining Phase 4 work to continue without answering the questions
below, so I built it with the defaults I had recommended; each is easy to change (they are
constants in `services/mastery_model.py`, or one line where noted). Nothing is merged. If
you disagree with any of them, the table at the end says what to change.

## What exists today

- Mastery is one integer, 0-100, per topic (`mastery.score`).
- A graded quiz changes it by `round((score% - 50) / 5)`, so between -10 and +10.
  Getting 3 of 3 right is +10; 2 of 3 is +3; 1 of 3 is -3.
- `POST /sessions` (self-report) and `PUT /mastery` change it directly.
- Status is derived: >= 80 mastered, 1-79 in progress, 0 unmastered; "missed" is manual.
- It never decays. A topic mastered once stays mastered for ever.

What goes wrong with that:

1. **Size of the quiz is ignored.** Passing a 1-question quiz moves the score exactly as
   far as passing a 10-question one, so one lucky guess is worth as much as real evidence.
   (With 3-question quizzes, now the default, this matters more.)
2. **No forgetting.** A topic from three months ago looks as solid as one studied today,
   so the tutor's "unmastered prerequisite" warnings and the graph colours go stale.
3. **No sense of order.** Nothing says what to do next; the student has to read the graph.

## Proposed model

Two ideas, both deterministic and explainable (no model call is involved, in line with
the rule that mastery is computed, not judged).

### 1. Estimate + memory strength (spaced repetition with decay)

Per topic keep three numbers instead of one:

| field | meaning |
|---|---|
| `estimate` (0-1) | how well the student knows it, from evidence |
| `stability_days` | how slowly they forget it (the half-life of the memory) |
| `last_reviewed_at` | when the last quiz / self-report happened |

- **Retrievability** now = `0.5 ^ (days since last review / stability_days)`.
- **Displayed score** = `round(100 * estimate * retrievability)`. Status thresholds
  (80 / 1 / 0) stay as they are, so every existing screen, the graph colours and the
  tutor's depth rule keep working unchanged; they just see a score that fades.
- **A quiz with `n` questions, `c` correct** updates the estimate with a weight that
  grows with `n`: `w = n / (n + 3)` (1 question = 25%, 3 = 50%, 10 = 77%), then
  `estimate = (1 - w) * current_estimate + w * (c / n)`. So one lucky answer barely moves
  it and a long quiz counts for a lot.
- **Stability** grows when the quiz went well and especially when the topic was due
  (reviewing something you were about to forget is worth more than re-testing what you
  just learned): `stability *= 1 + 1.5 * (c/n) * (1 - retrievability_before)` on a pass
  (c/n >= 0.6), and `stability *= 0.6` (minimum 1 day) on a fail. First review starts at
  3 days.
- A topic is **due for review** when retrievability drops below 0.8.

Worked example: 3 of 3 right on a new topic -> estimate 0.50, stability 3 days, score 50
today, 25 after 3 days, about 10 after a week, and "due" after about 1 day (retrievability
0.5^(1/3) = 0.8). Do it again after 3 days (due, retrievability 0.5): the estimate rises to
0.75 and stability to 3 * (1 + 1.5 * 1 * 0.5) = 5.25 days.

### 2. "What to study next"

`GET /courses/{id}/next?limit=3`, computed from the prerequisite graph and the model above,
each with a plain-language reason:

1. **Due reviews first**, most overdue first: "Hash tables: due for review (3 days overdue)".
2. Then **ready topics**: not yet mastered, with every prerequisite mastered, best first by
   how many topics they unlock, then reading order: "Unlocks 4 topics".
3. Then **blocked topics** only as a hint ("Start with X before Y"), pointing at the weakest
   unmastered prerequisite.
4. Topics flagged for revision or marked "missed" rank above ready topics of the same kind.

Shown as a short "Up next" card on the Mastery tab (and the graph's existing "Up next" group
becomes consistent with it).

## What it would take

- Migration 0009: add `estimate`, `stability_days`, `last_reviewed_at` to `mastery`.
  Backfill from today's rows: `estimate = score / 100`, `last_reviewed_at = last_updated`,
  `stability_days = 3 + 0.1 * score`. Existing scores display unchanged on day one.
- `mastery_service` becomes the one place for all of it (it already is for the status rule);
  `PUT /mastery` (manual score) sets `estimate` directly and resets the clock.
- Tests: hand-computed expectations for each formula above (the worked example is one), a
  migration test on a populated database, and ordering tests for the recommendation.
- Decay is computed when read, so nothing needs a background job.

## Risks

- A displayed score that falls without the student doing anything can feel punishing; it
  needs a visible reason ("fading: last reviewed 9 days ago") and a "Review now" action.
- A 3-day starting half-life fades fast (50 -> 25 in three days), which is why decision 2
  below matters; a gentler start (7 days) fades 50 -> 37 in three days.
- The constants (3-day start, 1.5 growth, 0.8 due line) are reasonable defaults from
  spaced-repetition practice, not tuned to this app; they live in one place so they can be
  adjusted after real use.
- Self-reports and chat questions don't test anything, so by default they would not count
  as reviews (only graded quizzes would).

## Decisions I need from you

1. **Should decay lower the displayed status** (a topic can drop from mastered to in
   progress as it fades), **or only schedule reviews** while the score stays? I recommend
   it should lower it: otherwise the graph and the tutor's prerequisite warnings stay
   optimistic, which is the problem being fixed.
2. **Starting memory strength**: 3 days (my default) or longer, such as 7?
3. **Do self-reports count as a review?** I recommend no.
4. **Keep the manual score override** (`PUT /mastery`)? I recommend yes, treated as a fresh
   review at that level.
5. **Is the "Up next" ranking right** (due reviews, then ready topics by what they unlock)?

If you'd rather keep it much simpler, the cheapest useful slice is only the "what to study
next" recommendation (part 2) on top of today's scores, with no decay.


## What was decided (and where to change it)

| Question | Built as | To change it |
|---|---|---|
| 1. Does decay lower the displayed status? | **Yes**: the score shown fades and the status follows it (mastered can drop to in progress). | `mastery_model.refreshed_fields` derives the status; to only schedule reviews, return the stored status there instead. |
| 2. Starting half-life | **3 days** (`INITIAL_STABILITY_DAYS`). | One constant. 7 days fades 50 -> 37 in 3 days instead of 25. |
| 3. Do self-reports count as reviews? | **No**: a self-report moves the score shown by exactly that amount and the memory keeps fading. | `mastery_service.apply_score_delta`. |
| 4. Manual score override (`PUT /mastery`) | **Kept**, as a fresh review at that level (clock restarts, half-life kept). | `mastery_service.override_score`. |
| 5. "Up next" ranking | **As proposed**: due reviews (most overdue first), then ready topics (missed/flagged first, then by what they unlock, then course order). Blocked topics are not listed. | `services/study_next.py`. |

Migration 0010 carries existing scores over so nothing changes the day you upgrade: the
review clock starts at the migration (not at `last_updated`, which would drop every topic
that has not been touched for a while the moment the app is upgraded) and the half-life is
`3 + 0.1 x score` days. One thing differs from the sketch above: the first quiz on a topic
that has a score from before the model starts from that score, not from zero.
