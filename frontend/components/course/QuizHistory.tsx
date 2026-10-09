"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api, QuizSummary } from "@/lib/api";
import { parseTimestamp } from "@/lib/history";
import { questionCount, summaryResult } from "@/lib/quiz-jobs";

interface Props {
  topicId: number;
  // Bumped when a quiz was generated or graded, so the list is fetched again.
  refreshKey: number;
  // The past quiz being viewed, if any.
  openId: number | null;
  onOpen: (quizSetId: number) => void;
}

function dateLabel(value: string | null): string {
  const date = parseTimestamp(value);
  return date
    ? date.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : "Unknown date";
}

// The topic's earlier quizzes, newest first. Any of them can be opened: a taken
// one shows its results, an untaken one can still be taken.
export default function QuizHistory({ topicId, refreshKey, openId, onOpen }: Props) {
  const [items, setItems] = useState<QuizSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .getQuizHistory(topicId)
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Couldn't load past quizzes.");
      });
    return () => {
      cancelled = true;
    };
  }, [topicId, refreshKey]);

  if (error) {
    return <p className="text-xs text-[var(--error-text)]">{error}</p>;
  }
  if (items === null || items.length === 0) return null;

  return (
    <section aria-label="Past quizzes" className="space-y-2 pt-2">
      <h3 className="text-sm font-semibold text-[var(--ink)]">Past quizzes</h3>
      <ul className="divide-y divide-[rgba(var(--ink-rgb),0.08)] rounded-xl border border-[rgba(var(--ink-rgb),0.10)] surface">
        {items.map((q) => (
          <li key={q.id} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm text-[var(--ink)]">
                {dateLabel(q.created_at)} <span className="text-fg-tertiary">· {questionCount(q.question_count)}</span>
              </p>
              <p className="text-xs text-stone-600 dark:text-stone-300">{summaryResult(q)}</p>
            </div>
            <Button
              type="button"
              size="sm"
              variant={openId === q.id ? "secondary" : "outline"}
              onClick={() => onOpen(q.id)}
              aria-label={`${q.taken ? "View results of" : "Take"} the quiz from ${dateLabel(q.created_at)}`}
            >
              {q.taken ? "View results" : "Take it"}
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
