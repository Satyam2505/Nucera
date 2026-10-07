// Pure helpers for the background quiz job and the past-quiz list. No React, no
// fetch, no runtime imports: testable under plain Node (see quiz-jobs.test.ts).

import type { QuizJob, QuizSummary } from "./api";

/** How often the page asks how far the job has got. */
export const POLL_INTERVAL_MS = 2500;
/** Failed polls in a row (a network blip, the server restarting) before giving up. */
export const MAX_POLL_FAILURES = 4;

export function isActive(job: Pick<QuizJob, "status">): boolean {
  return job.status === "queued" || job.status === "running";
}

/** 0-100, for the progress bar. */
export function progressPercent(job: Pick<QuizJob, "completed" | "requested">): number {
  if (job.requested <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((job.completed / job.requested) * 100)));
}

/** What the job is doing, in words: "Starting...", "Writing question 2 of 3 (1 done)". */
export function progressText(job: Pick<QuizJob, "status" | "completed" | "requested">): string {
  if (job.status === "queued") return "Starting...";
  const next = Math.min(job.completed + 1, job.requested);
  const done = job.completed === 0 ? "" : ` (${job.completed} done)`;
  return `Writing question ${next} of ${job.requested}${done}`;
}

export type JobOutcome =
  | { kind: "active" }
  // Every question was written: just show the quiz.
  | { kind: "ready" }
  // Some questions were written before a failure: show the quiz, with this notice.
  | { kind: "partial"; notice: string }
  // Nothing was written: show this as the error.
  | { kind: "failed"; message: string };

export function jobOutcome(job: Pick<QuizJob, "status" | "completed" | "requested" | "error">): JobOutcome {
  if (isActive(job)) return { kind: "active" };
  if (job.status === "succeeded") return { kind: "ready" };
  if (job.status === "partial") {
    const noun = job.completed === 1 ? "question" : "questions";
    const why = job.error ? ` ${job.error}` : "";
    return {
      kind: "partial",
      notice: `Only ${job.completed} of ${job.requested} ${noun} could be written.${why}`,
    };
  }
  return { kind: "failed", message: job.error || "The quiz couldn't be written." };
}

/** "3 questions", "1 question". */
export function questionCount(n: number): string {
  return `${n} ${n === 1 ? "question" : "questions"}`;
}

/** A past quiz's result line: "2 of 3 right (67%)" or "Not taken yet". */
export function summaryResult(summary: Pick<QuizSummary, "taken" | "correct" | "total" | "score_percent">): string {
  if (!summary.taken || summary.correct === null || summary.total === null) return "Not taken yet";
  const percent = summary.score_percent === null ? "" : ` (${Math.round(summary.score_percent)}%)`;
  return `${summary.correct} of ${summary.total} right${percent}`;
}
