"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { api, QuizQuestion, QuizSubmitResult } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";

export default function QuizView({ topicId }: { topicId: number | null }) {
  const { topics, refresh } = useAppState();
  const topic = topics.find((t) => t.id === topicId);

  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<QuizSubmitResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setQuestions([]);
    setAnswers({});
    setResult(null);
    if (!topicId) return;
    setLoading(true);
    api.getQuiz(topicId).then((qs) => {
      setQuestions(qs);
      setLoading(false);
    });
  }, [topicId]);

  async function handleSubmit() {
    if (!topicId) return;
    setSubmitting(true);
    try {
      const payload = {
        topic_id: topicId,
        answers: Object.entries(answers).map(([qid, selected]) => ({
          question_id: Number(qid),
          selected_option: selected,
        })),
      };
      const data = await api.submitQuiz(payload);
      setResult(data);
      refresh();
    } finally {
      setSubmitting(false);
    }
  }

  if (!topicId) {
    return <div className="p-8 text-sm text-stone-500 dark:text-stone-400">Select a topic to take its quiz.</div>;
  }

  return (
    <div className="p-8 max-w-2xl mx-auto space-y-5">
      <h2 className="text-lg font-semibold text-[var(--ink)]">Quiz — {topic?.name}</h2>

      {loading && <p className="text-sm text-stone-500 dark:text-stone-400">Loading quiz...</p>}

      {!loading &&
        questions.map((q, idx) => (
          <Card key={q.id} className="surface rounded-xl p-4 border-[rgba(var(--ink-rgb),0.09)]">
            <p className="text-sm font-medium text-[var(--ink)] mb-3">
              {idx + 1}. {q.question_text}
            </p>
            <RadioGroup
              value={answers[q.id] ?? ""}
              onValueChange={(value) => setAnswers((prev) => ({ ...prev, [q.id]: value }))}
              className="space-y-2"
            >
              {Object.entries(q.options).map(([key, label]) => (
                <div key={key} className="flex items-center gap-2">
                  <RadioGroupItem
                    value={key}
                    id={`q${q.id}-${key}`}
                    className="border-[rgba(var(--ink-rgb),0.3)] text-[var(--accent)]"
                  />
                  <Label
                    htmlFor={`q${q.id}-${key}`}
                    className="text-sm font-normal text-stone-700 dark:text-stone-300 cursor-pointer"
                  >
                    {key}. {label}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </Card>
        ))}

      {!loading && questions.length > 0 && !result && (
        <Button
          onClick={handleSubmit}
          disabled={submitting}
          className="w-full bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] h-auto py-2.5 accent-ring"
        >
          {submitting ? "Submitting..." : "Submit answers"}
        </Button>
      )}

      {result && (
        <Card className="surface rounded-xl p-4 text-sm text-[var(--ink)] border-[rgba(var(--accent-rgb),0.30)]">
          Score: {result.correct}/{result.total} ({result.score_percent.toFixed(0)}%) — mastery now{" "}
          {result.mastery.score} ({result.mastery.status})
        </Card>
      )}
    </div>
  );
}
