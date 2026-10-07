// Pure helpers for the "Up next" suggestions. No React, no fetch, and no runtime imports,
// so they are testable under plain Node (next-steps.test.ts).

import type { NextStep } from "./api";

/** The small label on a suggestion: reviews are called out; everything else is "Up next". */
export function stepBadge(step: Pick<NextStep, "kind">): string {
  return step.kind === "review" ? "Review" : "Up next";
}

/** What the suggestion's main button does: reviewing a faded topic means taking a quiz on
 * it; a topic that is simply ready is best started by asking the tutor about it. */
export function stepAction(step: Pick<NextStep, "kind">): { view: "chat" | "quiz"; label: string } {
  return step.kind === "review"
    ? { view: "quiz", label: "Review with a quiz" }
    : { view: "chat", label: "Start with the tutor" };
}

/** A line for a topic's row in the mastery list: "fading" says why a score has dropped. */
export function fadingNote(mastery: { due_for_review: boolean } | undefined): string | null {
  return mastery?.due_for_review ? "Due for review" : null;
}
