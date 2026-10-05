// Small pure helpers for the quiz view, kept free of React and of runtime
// imports so they can be tested under plain Node (see quiz.test.ts).

import type { QuizResultItem, SourceCitation } from "./api";

/** "Notes A, p. 3", or just "Notes B" for a source with no page. */
export function citationLabel(citation: SourceCitation): string {
  return citation.page ? `${citation.source}, p. ${citation.page}` : citation.source;
}

export function answeredCount(questions: { id: number }[], answers: Record<number, string>): number {
  return questions.filter((q) => answers[q.id] !== undefined).length;
}

/** Submitting is only allowed once every question has an answer. */
export function allAnswered(questions: { id: number }[], answers: Record<number, string>): boolean {
  return questions.length > 0 && answeredCount(questions, answers) === questions.length;
}

/** The submit body's answers, in question order (stale answers for other quizzes are ignored). */
export function answerPayload(
  questions: { id: number }[],
  answers: Record<number, string>
): { question_id: number; selected_option: string }[] {
  return questions
    .filter((q) => answers[q.id] !== undefined)
    .map((q) => ({ question_id: q.id, selected_option: answers[q.id] }));
}

/** A mastery change as text: "+10", "-4", or "no change". */
export function formatDelta(delta: number): string {
  if (delta === 0) return "no change";
  return delta > 0 ? `+${delta}` : `${delta}`;
}

export type ResultMark = "correct" | "incorrect" | "unanswered";

// Correct / incorrect / not answered. The view shows this as words and icons
// as well as colour, so the result never depends on colour alone.
export function resultMark(result: Pick<QuizResultItem, "chosen" | "is_correct">): ResultMark {
  if (result.chosen === null) return "unanswered";
  return result.is_correct ? "correct" : "incorrect";
}

export const RESULT_LABEL: Record<ResultMark, string> = {
  correct: "Correct",
  incorrect: "Incorrect",
  unanswered: "Not answered",
};
