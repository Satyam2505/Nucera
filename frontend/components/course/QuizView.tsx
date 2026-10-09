"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import QuizHistory from "@/components/course/QuizHistory";
import QuizResults from "@/components/course/QuizResults";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { api, ApiError, QuizAttempt, QuizJob, QuizSet, QuizState } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";
import { allAnswered, answerPayload, answeredCount } from "@/lib/quiz";
import {
  isActive,
  jobOutcome,
  MAX_POLL_FAILURES,
  POLL_INTERVAL_MS,
  progressPercent,
  progressText,
} from "@/lib/quiz-jobs";

type Phase =
  | { kind: "loading" }
  | { kind: "load-error"; message: string }
  | { kind: "no-material" }
  | { kind: "empty" }
  | { kind: "generating"; job: QuizJob }
  | { kind: "generate-error"; status: number; message: string }
  | { kind: "quiz"; set: QuizSet }
  | { kind: "results"; attempt: QuizAttempt };

interface Props {
  topicId: number | null;
  // Bumped by the page when the upload modal closes, so a topic that just got
  // its first source stops showing the "add study material" state.
  refreshKey?: number;
  onAddSource: () => void;
}

const primaryButton =
  "bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] h-auto py-2.5 accent-ring";

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export default function QuizView({ topicId, refreshKey = 0, onAddSource }: Props) {
  const { topics, refresh } = useAppState();
  const topic = topics.find((t) => t.id === topicId);

  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Said when a quiz came out shorter than asked for (the model failed part-way).
  const [notice, setNotice] = useState<string | null>(null);
  // The id of the past quiz being viewed, or null for the topic's latest.
  const [pastId, setPastId] = useState<number | null>(null);
  // Bumped whenever the list of past quizzes may have changed.
  const [historyKey, setHistoryKey] = useState(0);
  // Bumped by every load and generate, so a slow response for a topic the user
  // has since left (or for a quiz they replaced) is ignored when it lands.
  const latest = useRef(0);

  const applyState = useCallback((state: QuizState) => {
    setAnswers({});
    setSubmitError(null);
    setPastId(null);
    if (state.job && isActive(state.job)) setPhase({ kind: "generating", job: state.job });
    else if (state.quiz_set?.attempt) setPhase({ kind: "results", attempt: state.quiz_set.attempt });
    else if (state.quiz_set) setPhase({ kind: "quiz", set: state.quiz_set });
    else setPhase(state.has_material ? { kind: "empty" } : { kind: "no-material" });
  }, []);

  const load = useCallback(async () => {
    if (topicId === null) return;
    const requestId = ++latest.current;
    setPhase({ kind: "loading" });
    try {
      const state = await api.getQuiz(topicId);
      if (requestId === latest.current) {
        applyState(state);
        setHistoryKey((k) => k + 1);
      }
    } catch (err) {
      if (requestId === latest.current) {
        setPhase({ kind: "load-error", message: errorText(err, "Couldn't load the quiz.") });
      }
    }
  }, [topicId, applyState]);

  // Reading is safe to repeat (it never generates), so refetching on a topic
  // switch or an upload is cheap. A generation still running on the server is
  // picked up here too: leaving the page doesn't stop it.
  useEffect(() => {
    setNotice(null);
    load();
  }, [load, refreshKey]);

  // While a job runs, ask how far it has got. The effect depends on the job's id
  // only, so the timer isn't restarted by every progress update it causes.
  const generatingJobId = phase.kind === "generating" ? phase.job.id : null;
  useEffect(() => {
    if (generatingJobId === null || topicId === null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    const finish = async (job: QuizJob) => {
      const outcome = jobOutcome(job);
      if (outcome.kind === "failed") {
        setPhase({ kind: "generate-error", status: 0, message: outcome.message });
        return;
      }
      // The notice is set before reloading: the reload moves the page out of its
      // "generating" state, which tears this effect down (`cancelled`), so
      // anything after the await would never run.
      if (outcome.kind === "partial") setNotice(outcome.notice);
      await load();
    };

    const tick = async () => {
      try {
        const job = await api.getQuizJob(generatingJobId);
        if (cancelled) return;
        failures = 0;
        if (isActive(job)) {
          setPhase({ kind: "generating", job });
          timer = setTimeout(tick, POLL_INTERVAL_MS);
        } else {
          await finish(job);
        }
      } catch (err) {
        if (cancelled) return;
        failures += 1;
        if (failures >= MAX_POLL_FAILURES) {
          setPhase({
            kind: "generate-error",
            status: err instanceof ApiError ? err.status : 0,
            message: errorText(err, "Lost contact with the server while the quiz was being written."),
          });
        } else {
          timer = setTimeout(tick, POLL_INTERVAL_MS);
        }
      }
    };

    timer = setTimeout(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [generatingJobId, topicId, load]);

  async function generate() {
    if (topicId === null || phase.kind === "generating") return;
    const requestId = ++latest.current;
    setAnswers({});
    setSubmitError(null);
    setNotice(null);
    setPastId(null);
    try {
      const job = await api.generateQuiz(topicId);
      if (requestId === latest.current) setPhase({ kind: "generating", job });
    } catch (err) {
      if (requestId !== latest.current) return;
      setPhase({
        kind: "generate-error",
        status: err instanceof ApiError ? err.status : 0,
        message: errorText(err, "Couldn't start the quiz."),
      });
    }
  }

  async function openPast(quizSetId: number) {
    const requestId = ++latest.current;
    setAnswers({});
    setSubmitError(null);
    setNotice(null);
    try {
      const set = await api.getQuizSet(quizSetId);
      if (requestId !== latest.current) return;
      setPastId(quizSetId);
      setPhase(set.attempt ? { kind: "results", attempt: set.attempt } : { kind: "quiz", set });
    } catch (err) {
      if (requestId === latest.current) {
        setPhase({ kind: "load-error", message: errorText(err, "Couldn't open that quiz.") });
      }
    }
  }

  async function submit(set: QuizSet) {
    if (submitting || !allAnswered(set.questions, answers)) return;
    const requestId = latest.current;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const attempt = await api.submitQuiz({
        quiz_set_id: set.id,
        answers: answerPayload(set.questions, answers),
      });
      if (requestId !== latest.current) return;
      setPhase({ kind: "results", attempt });
      setNotice(null);
      setHistoryKey((k) => k + 1);
      await refresh();
    } catch (err) {
      if (requestId !== latest.current) return;
      // Already graded elsewhere (another tab): show that attempt instead.
      if (err instanceof ApiError && err.status === 409) await load();
      else setSubmitError(errorText(err, "Couldn't submit your answers."));
    } finally {
      setSubmitting(false);
    }
  }

  if (topicId === null) {
    return <div className="p-8 text-sm text-fg-secondary">Select a topic to take its quiz.</div>;
  }

  return (
    <div className="p-8 max-w-2xl mx-auto space-y-5">
      <h2 className="text-lg font-semibold text-[var(--ink)]">Quiz — {topic?.name}</h2>

      {pastId !== null && (phase.kind === "quiz" || phase.kind === "results") && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-[rgba(var(--ink-rgb),0.12)] px-3 py-2 text-xs text-stone-600 dark:text-stone-300">
          <span>You are looking at a past quiz.</span>
          <button type="button" onClick={load} className="font-medium text-[var(--accent)] hover:underline">
            Back to the latest quiz
          </button>
        </div>
      )}

      {notice && (
        <Alert className="bg-[var(--warn-bg)] border-[var(--warn-border)]">
          <AlertDescription className="text-[var(--warn-text)]">{notice}</AlertDescription>
        </Alert>
      )}

      {phase.kind === "loading" && (
        <p role="status" className="text-sm text-fg-secondary">
          Loading quiz...
        </p>
      )}

      {phase.kind === "load-error" && (
        <div className="space-y-3">
          <Alert variant="destructive" className="bg-[var(--error-bg)] border-[var(--error-border)]">
            <AlertDescription className="text-[var(--error-text)]">{phase.message}</AlertDescription>
          </Alert>
          <Button variant="outline" onClick={load}>
            Try again
          </Button>
        </div>
      )}

      {phase.kind === "no-material" && (
        <Card className="surface rounded-xl p-5 space-y-3 border-[rgba(var(--ink-rgb),0.09)]">
          <p className="text-sm font-medium text-[var(--ink)]">Add study material first</p>
          <p className="text-sm text-stone-600 dark:text-stone-300">
            A quiz is written from the notes you upload for this topic, and there is nothing here yet.
          </p>
          <Button onClick={onAddSource} className={primaryButton}>
            Add study material
          </Button>
        </Card>
      )}

      {phase.kind === "empty" && (
        <Card className="surface rounded-xl p-5 space-y-3 border-[rgba(var(--ink-rgb),0.09)]">
          <p className="text-sm font-medium text-[var(--ink)]">No quiz yet</p>
          <p className="text-sm text-stone-600 dark:text-stone-300">
            Generate a short quiz written from your uploaded material for this topic.
          </p>
          <Button onClick={generate} className={primaryButton}>
            Generate quiz
          </Button>
        </Card>
      )}

      {phase.kind === "generating" && <GeneratingCard job={phase.job} />}

      {phase.kind === "generate-error" && (
        <div className="space-y-3">
          <Alert variant="destructive" className="bg-[var(--error-bg)] border-[var(--error-border)]">
            <AlertDescription className="text-[var(--error-text)]">{phase.message}</AlertDescription>
          </Alert>
          {phase.status === 409 ? (
            // A 409 means no material or a generation already running; reloading
            // shows which (and picks up the finished quiz if it just landed).
            <Button variant="outline" onClick={load}>
              Check again
            </Button>
          ) : (
            <Button variant="outline" onClick={generate}>
              Try again
            </Button>
          )}
        </div>
      )}

      {phase.kind === "quiz" && (
        <QuizForm
          set={phase.set}
          answers={answers}
          onAnswer={(questionId, option) => setAnswers((prev) => ({ ...prev, [questionId]: option }))}
          submitting={submitting}
          error={submitError}
          onSubmit={() => submit(phase.set)}
        />
      )}

      {phase.kind === "results" && <QuizResults attempt={phase.attempt} onNewQuiz={generate} />}

      {phase.kind !== "no-material" && phase.kind !== "loading" && (
        <QuizHistory topicId={topicId} refreshKey={historyKey} openId={pastId} onOpen={openPast} />
      )}
    </div>
  );
}

// Progress of the background job. Leaving the page doesn't stop it: coming back
// to this topic picks the same job up again.
function GeneratingCard({ job }: { job: QuizJob }) {
  const percent = progressPercent(job);
  return (
    <Card className="surface rounded-xl p-5 space-y-3 border-[rgba(var(--ink-rgb),0.09)]">
      <p role="status" className="text-sm font-medium text-[var(--ink)]">
        {progressText(job)}
      </p>
      <div
        role="progressbar"
        aria-label="Quiz progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2 w-full overflow-hidden rounded-full bg-[rgba(var(--ink-rgb),0.10)]"
      >
        <div
          className="h-full rounded-full bg-[var(--accent)] transition-all duration-500"
          style={{ width: `${Math.max(percent, 4)}%` }}
        />
      </div>
      <p className="text-sm text-stone-600 dark:text-stone-300">
        Each question takes a couple of minutes on a CPU. You can leave this page; the quiz keeps being written
        and will be here when you come back.
      </p>
    </Card>
  );
}

interface FormProps {
  set: QuizSet;
  answers: Record<number, string>;
  onAnswer: (questionId: number, option: string) => void;
  submitting: boolean;
  error: string | null;
  onSubmit: () => void;
}

// Questions only: the answer key and explanations are not part of what the
// server sends until the quiz has been graded.
function QuizForm({ set, answers, onAnswer, submitting, error, onSubmit }: FormProps) {
  const done = answeredCount(set.questions, answers);
  const complete = allAnswered(set.questions, answers);

  return (
    <div className="space-y-4">
      <p aria-live="polite" className="text-sm text-stone-600 dark:text-stone-300">
        {done} of {set.questions.length} answered
      </p>

      {set.questions.map((q, idx) => (
        <Card key={q.id} className="surface rounded-xl p-4 border-[rgba(var(--ink-rgb),0.09)]">
          <p id={`q${q.id}-text`} className="text-sm font-medium text-[var(--ink)] mb-3">
            {idx + 1}. {q.question_text}
          </p>
          <RadioGroup
            value={answers[q.id] ?? ""}
            onValueChange={(value) => onAnswer(q.id, value)}
            aria-labelledby={`q${q.id}-text`}
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

      {error && (
        <Alert variant="destructive" className="bg-[var(--error-bg)] border-[var(--error-border)]">
          <AlertDescription className="text-[var(--error-text)]">{error}</AlertDescription>
        </Alert>
      )}

      <Button onClick={onSubmit} disabled={!complete || submitting} className={`w-full ${primaryButton}`}>
        {submitting ? "Submitting..." : "Submit answers"}
      </Button>
      {!complete && (
        <p className="text-xs text-center text-fg-tertiary">
          Answer every question to submit.
        </p>
      )}
    </div>
  );
}
