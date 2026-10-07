// Plain-Node tests for the quiz-job and study-history helpers, in the same style
// as quiz.test.ts (only Node's built-in `assert`). To run ad hoc, Node's ESM
// loader needs the explicit extension on the relative imports (there are none
// at runtime here, only type imports, so the file runs as it is):
//   sed 's#"./\(quiz-jobs\|history\)"#"./\1.ts"#' lib/quiz-jobs.test.ts > lib/_run.test.ts \
//     && node --experimental-strip-types lib/_run.test.ts; rm lib/_run.test.ts

import assert from "node:assert/strict";

import type { QuizJob } from "./api";

import { dayLabel, groupByDay, masteryChange, nextCursor, parseTimestamp, SESSION_LABEL, timeLabel } from "./history";
import {
  isActive,
  jobOutcome,
  MAX_POLL_FAILURES,
  POLL_INTERVAL_MS,
  progressPercent,
  progressText,
  questionCount,
  summaryResult,
} from "./quiz-jobs";

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`ok - ${name}`);
}

const job = (status: QuizJob["status"], completed: number, requested = 3, error: string | null = null) => ({
  status,
  completed,
  requested,
  error,
});

// --- quiz jobs --------------------------------------------------------------------------

test("queued and running jobs are active; finished ones are not", () => {
  for (const status of ["queued", "running"] as const) assert.equal(isActive({ status }), true, status);
  for (const status of ["succeeded", "partial", "failed"] as const) assert.equal(isActive({ status }), false, status);
});

test("the progress bar is a rounded percentage, clamped to 0-100", () => {
  assert.equal(progressPercent({ completed: 0, requested: 3 }), 0);
  assert.equal(progressPercent({ completed: 1, requested: 3 }), 33);
  assert.equal(progressPercent({ completed: 2, requested: 3 }), 67);
  assert.equal(progressPercent({ completed: 3, requested: 3 }), 100);
  assert.equal(progressPercent({ completed: 9, requested: 3 }), 100);
  assert.equal(progressPercent({ completed: 1, requested: 0 }), 0);
});

test("progress text says which question is being written", () => {
  assert.equal(progressText(job("queued", 0)), "Starting...");
  assert.equal(progressText(job("running", 0)), "Writing question 1 of 3");
  assert.equal(progressText(job("running", 1)), "Writing question 2 of 3 (1 done)");
  assert.equal(progressText(job("running", 2)), "Writing question 3 of 3 (2 done)");
});

test("progress text never names a question past the last", () => {
  assert.equal(progressText(job("running", 3)), "Writing question 3 of 3 (3 done)");
});

test("a succeeded job just shows the quiz", () => {
  assert.deepEqual(jobOutcome(job("succeeded", 3)), { kind: "ready" });
});

test("a partial job shows the quiz with a notice that includes the reason", () => {
  assert.deepEqual(jobOutcome(job("partial", 2, 3, "The local model timed out.")), {
    kind: "partial",
    notice: "Only 2 of 3 questions could be written. The local model timed out.",
  });
  assert.deepEqual(jobOutcome(job("partial", 1, 5)), {
    kind: "partial",
    notice: "Only 1 of 5 question could be written.",
  });
});

test("a failed job is an error, with a fallback message", () => {
  assert.deepEqual(jobOutcome(job("failed", 0, 3, "Ollama is not running.")), {
    kind: "failed",
    message: "Ollama is not running.",
  });
  assert.deepEqual(jobOutcome(job("failed", 0)), { kind: "failed", message: "The quiz couldn't be written." });
});

test("an active job has no outcome yet", () => {
  assert.deepEqual(jobOutcome(job("running", 1)), { kind: "active" });
  assert.deepEqual(jobOutcome(job("queued", 0)), { kind: "active" });
});

test("polling gives up only after several failures in a row, and is not frantic", () => {
  assert.ok(MAX_POLL_FAILURES >= 3);
  assert.ok(POLL_INTERVAL_MS >= 1000);
});

test("question counts and past-quiz results read naturally", () => {
  assert.equal(questionCount(1), "1 question");
  assert.equal(questionCount(3), "3 questions");
  assert.equal(summaryResult({ taken: false, correct: null, total: null, score_percent: null }), "Not taken yet");
  assert.equal(summaryResult({ taken: true, correct: 2, total: 3, score_percent: 66.6667 }), "2 of 3 right (67%)");
  assert.equal(summaryResult({ taken: true, correct: 0, total: 3, score_percent: 0 }), "0 of 3 right (0%)");
});

// --- study history ------------------------------------------------------------------------------

const item = (id: number, timestamp: string | null, type = "chat", score_delta = 0) => ({
  id,
  topic_id: 1,
  topic_name: "Hash tables",
  type: type as "chat" | "quiz" | "self_report",
  score_delta,
  timestamp,
});

test("every session type has a label", () => {
  assert.deepEqual(Object.keys(SESSION_LABEL).sort(), ["chat", "quiz", "self_report"]);
});

test("a mastery change shows its sign, and nothing when there was none", () => {
  assert.equal(masteryChange({ score_delta: 0 }), null);
  assert.equal(masteryChange({ score_delta: 7 }), "+7 mastery");
  assert.equal(masteryChange({ score_delta: -4 }), "-4 mastery");
});

test("server timestamps without a zone are read as UTC", () => {
  assert.equal(parseTimestamp("2026-10-08T09:30:00")?.toISOString(), "2026-10-08T09:30:00.000Z");
  assert.equal(parseTimestamp("2026-10-08T09:30:00.123456")?.toISOString(), "2026-10-08T09:30:00.123Z");
  assert.equal(parseTimestamp("2026-10-08T09:30:00Z")?.toISOString(), "2026-10-08T09:30:00.000Z");
  assert.equal(parseTimestamp("2026-10-08T15:00:00+05:30")?.toISOString(), "2026-10-08T09:30:00.000Z");
  assert.equal(parseTimestamp(null), null);
  assert.equal(parseTimestamp("not a date"), null);
});

test("days are labelled Today, Yesterday, then by date", () => {
  const now = new Date(2026, 9, 8, 12, 0); // local noon, 8 Oct 2026
  assert.equal(dayLabel(new Date(2026, 9, 8, 0, 5), now), "Today");
  assert.equal(dayLabel(new Date(2026, 9, 8, 23, 59), now), "Today");
  assert.equal(dayLabel(new Date(2026, 9, 7, 23, 59), now), "Yesterday");
  assert.equal(dayLabel(new Date(2026, 9, 7, 0, 1), now), "Yesterday");
  assert.equal(dayLabel(new Date(2026, 9, 5, 10, 0), now), "Mon, 5 Oct 2026");
});

test("sessions are grouped under their day with the order kept", () => {
  const now = new Date(2026, 9, 8, 12, 0);
  const local = (d: number, h: number) => new Date(2026, 9, d, h, 0).toISOString();
  const groups = groupByDay(
    [item(5, local(8, 11)), item(4, local(8, 9)), item(3, local(7, 20)), item(2, local(5, 10)), item(1, local(5, 9))],
    now
  );
  assert.deepEqual(
    groups.map((g) => [g.label, g.items.map((i) => i.id)]),
    [
      ["Today", [5, 4]],
      ["Yesterday", [3]],
      ["Mon, 5 Oct 2026", [2, 1]],
    ]
  );
});

test("a session with no timestamp goes under Earlier rather than breaking the list", () => {
  const groups = groupByDay([item(2, null), item(1, null)], new Date(2026, 9, 8));
  assert.deepEqual(groups.map((g) => [g.label, g.items.length]), [["Earlier", 2]]);
});

test("no sessions, no groups", () => {
  assert.deepEqual(groupByDay([], new Date()), []);
});

test("the time of day is hours and minutes, blank when unknown", () => {
  assert.match(timeLabel({ timestamp: "2026-10-08T09:30:00" }), /^\d{2}:\d{2}$/);
  assert.equal(timeLabel({ timestamp: null }), "");
});

test("paging continues from the oldest id only after a full page", () => {
  const page = [item(9, null), item(8, null)];
  assert.equal(nextCursor(page, 2), 8);
  assert.equal(nextCursor(page, 3), null); // a short page was the last
  assert.equal(nextCursor([], 2), null);
});

console.log(`\n${passed} passed`);
