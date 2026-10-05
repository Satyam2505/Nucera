"use client";

import { Check, Minus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { QuizAttempt, QuizResultItem } from "@/lib/api";
import { citationLabel, formatDelta, RESULT_LABEL, resultMark, type ResultMark } from "@/lib/quiz";
import { STATUS_COLOR, STATUS_FILL, STATUS_LABEL, type MasteryStatusKey } from "@/lib/status-colors";

const MARK_ICON: Record<ResultMark, typeof Check> = { correct: Check, incorrect: X, unanswered: Minus };
const MARK_COLOR: Record<ResultMark, string> = {
  correct: STATUS_COLOR.mastered,
  incorrect: STATUS_COLOR.missed,
  unanswered: STATUS_COLOR.unmastered,
};

interface Props {
  attempt: QuizAttempt;
  onNewQuiz: () => void;
}

export default function QuizResults({ attempt, onNewQuiz }: Props) {
  const { mastery } = attempt;
  return (
    <div className="space-y-4">
      <Card className="surface rounded-xl p-4 border-[rgba(var(--accent-rgb),0.30)] text-sm text-[var(--ink)] space-y-1">
        <p className="font-medium">
          You got {attempt.correct} of {attempt.total} right ({Math.round(attempt.score_percent)}%).
        </p>
        <p className="text-stone-600 dark:text-stone-300">
          Mastery {formatDelta(attempt.score_delta)}
          {mastery && (
            <>
              {" "}
              — now {mastery.score} ({STATUS_LABEL[mastery.status as MasteryStatusKey]})
            </>
          )}
          .
        </p>
      </Card>

      <ol className="space-y-3" aria-label="Question results">
        {attempt.results.map((result, index) => (
          <li key={result.question_id}>
            <ResultCard index={index} result={result} />
          </li>
        ))}
      </ol>

      <Button
        onClick={onNewQuiz}
        className="w-full bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] h-auto py-2.5 accent-ring"
      >
        New quiz
      </Button>
    </div>
  );
}

function ResultCard({ index, result }: { index: number; result: QuizResultItem }) {
  const mark = resultMark(result);
  const Icon = MARK_ICON[mark];

  return (
    <Card className="surface rounded-xl p-4 border-[rgba(var(--ink-rgb),0.09)]">
      <div className="flex items-start justify-between gap-3 mb-3">
        <p className="text-sm font-medium text-[var(--ink)]">
          {index + 1}. {result.question_text}
        </p>
        {/* Words and an icon carry the result; the colour only reinforces it. */}
        <span
          className="flex shrink-0 items-center gap-1 text-xs font-medium"
          style={{ color: MARK_COLOR[mark] }}
        >
          <Icon size={14} aria-hidden />
          {RESULT_LABEL[mark]}
        </span>
      </div>

      <ul className="space-y-1.5">
        {Object.entries(result.options).map(([key, label]) => {
          const isCorrect = key === result.correct_option;
          const isChosen = key === result.chosen;
          return (
            <li
              key={key}
              className="flex items-start justify-between gap-3 rounded-lg border px-3 py-2 text-sm text-[var(--ink)]"
              style={{
                borderColor: isCorrect
                  ? STATUS_COLOR.mastered
                  : isChosen
                    ? STATUS_COLOR.missed
                    : "rgba(var(--ink-rgb), 0.12)",
                background: isCorrect ? STATUS_FILL.mastered : isChosen ? STATUS_FILL.missed : undefined,
              }}
            >
              <span>
                {key}. {label}
              </span>
              <span className="shrink-0 text-[11px] font-medium text-stone-600 dark:text-stone-300">
                {[isChosen && "Your answer", isCorrect && "Correct answer"].filter(Boolean).join(" · ")}
              </span>
            </li>
          );
        })}
      </ul>

      {result.explanation && (
        <p className="mt-3 text-sm text-stone-700 dark:text-stone-300">
          <span className="font-medium text-[var(--ink)]">Why: </span>
          {result.explanation}
        </p>
      )}
      {result.sources.length > 0 && (
        <p className="mt-1.5 text-xs text-stone-500 dark:text-stone-400">
          Source: {result.sources.map(citationLabel).join("; ")}
        </p>
      )}
    </Card>
  );
}
