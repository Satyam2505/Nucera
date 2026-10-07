"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { candidateLabel, editErrorText, type EditableTopic } from "@/lib/graph-edit";
import type { PathState } from "@/lib/graph-model";
import { STATUS_COLOR, STATUS_LABEL } from "@/lib/status-colors";

import { normalizeStatus, PATH_LABEL, PathIcon, StatusIcon } from "./graph-icons";

export interface PanelTopic {
  id: number;
  name: string;
  status: string;
  score: number;
}

interface Props {
  topic: PanelTopic;
  pathState: PathState;
  prerequisites: PanelTopic[];
  unlocks: PanelTopic[];
  totalBefore: number;
  totalAfter: number;
  isFocused: boolean;
  // Topics that may be added as a prerequisite (never one that would make a loop).
  candidates: EditableTopic[];
  onAddPrerequisite: (prerequisiteId: number) => Promise<void>;
  onRemovePrerequisite: (prerequisiteId: number) => Promise<void>;
  onClose: () => void;
  onSelectTopic: (id: number) => void;
  onFocus: () => void;
  onShowAll: () => void;
  onAsk: () => void;
  onQuiz: () => void;
}

function TopicLink({
  topic,
  onSelect,
  onRemove,
  removeDisabled,
}: {
  topic: PanelTopic;
  onSelect: (id: number) => void;
  // Given only for the rows that can be removed (the topic's own prerequisites).
  onRemove?: (id: number) => void;
  removeDisabled?: boolean;
}) {
  const status = normalizeStatus(topic.status);
  return (
    <li className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => onSelect(topic.id)}
        className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-[var(--ink)] transition hover:bg-[rgba(var(--ink-rgb),0.06)]"
      >
        <StatusIcon status={status} size={12} />
        <span className="min-w-0 flex-1 truncate">{topic.name}</span>
        <span className="shrink-0 text-[10px] text-[var(--ink)]/60">{STATUS_LABEL[status]}</span>
      </button>
      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove(topic.id)}
          disabled={removeDisabled}
          aria-label={`Remove prerequisite ${topic.name}`}
          title="Remove this prerequisite"
          className="shrink-0 rounded-md p-1 text-[var(--ink)]/50 transition hover:bg-[rgba(var(--ink-rgb),0.08)] hover:text-[var(--status-missed)] disabled:opacity-40"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round" />
          </svg>
        </button>
      )}
    </li>
  );
}

export default function TopicDetailPanel({
  topic,
  pathState,
  prerequisites,
  unlocks,
  totalBefore,
  totalAfter,
  isFocused,
  candidates,
  onAddPrerequisite,
  onRemovePrerequisite,
  onClose,
  onSelectTopic,
  onFocus,
  onShowAll,
  onAsk,
  onQuiz,
}: Props) {
  const status = normalizeStatus(topic.status);
  const score = Math.max(0, Math.min(100, Math.round(topic.score)));

  // Editing the topic's prerequisites. A failed change (a loop the picker couldn't
  // foresee, a dropped connection) is shown here and nothing else on screen moves.
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  useEffect(() => {
    // Another topic was selected: its picker starts clean.
    setChoice("");
    setEditError(null);
  }, [topic.id]);
  useEffect(() => {
    // The chosen topic stopped being a candidate (just added): clear the picker.
    if (choice && !candidates.some((c) => String(c.id) === choice)) setChoice("");
  }, [candidates, choice]);

  async function change(action: () => Promise<void>, fallback: string) {
    setBusy(true);
    setEditError(null);
    try {
      await action();
    } catch (err) {
      setEditError(editErrorText(err, fallback));
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside
      aria-label={`Details for ${topic.name}`}
      className="absolute inset-x-0 bottom-0 z-10 max-h-[55%] overflow-y-auto rounded-t-2xl border border-[rgba(var(--ink-rgb),0.12)] bg-[var(--bg-surface)] p-4 shadow-xl md:static md:max-h-none md:w-72 md:shrink-0 md:rounded-none md:border-0 md:border-l md:shadow-none"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold leading-snug text-[var(--ink)]">{topic.name}</h3>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close details"
          className="-mr-1 -mt-1 rounded-md p-1 text-[var(--ink)]/60 transition hover:bg-[rgba(var(--ink-rgb),0.08)] hover:text-[var(--ink)]"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <dl className="mt-3 space-y-2 text-xs">
        <div className="flex items-center justify-between gap-3">
          <dt className="text-[var(--ink)]/60">Mastery</dt>
          <dd className="flex items-center gap-1.5 font-medium text-[var(--ink)]">
            <StatusIcon status={status} size={12} />
            {score}% · {STATUS_LABEL[status]}
          </dd>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-[rgba(var(--ink-rgb),0.10)]" aria-hidden>
          <div className="h-full rounded-full" style={{ width: `${score}%`, background: STATUS_COLOR[status] }} />
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-[var(--ink)]/60">Learning path</dt>
          <dd className="flex items-center gap-1.5 font-medium text-[var(--ink)]">
            <PathIcon state={pathState} size={12} />
            {PATH_LABEL[pathState]}
          </dd>
        </div>
      </dl>

      <section className="mt-4">
        <h4 className="text-[11px] font-medium text-[var(--ink)]/60">
          Prerequisites{totalBefore > prerequisites.length ? ` · ${totalBefore} topics lead here` : ""}
        </h4>
        {prerequisites.length ? (
          <ul className="mt-1 -mx-1">
            {prerequisites.map((t) => (
              <TopicLink
                key={t.id}
                topic={t}
                onSelect={onSelectTopic}
                removeDisabled={busy}
                onRemove={(id) => change(() => onRemovePrerequisite(id), "Couldn't remove that prerequisite.")}
              />
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-[var(--ink)]/60">None — a good place to start.</p>
        )}

        {candidates.length > 0 ? (
          <form
            className="mt-2 flex items-center gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              if (!choice) return;
              change(() => onAddPrerequisite(Number(choice)), "Couldn't add that prerequisite.");
            }}
          >
            <label className="sr-only" htmlFor={`add-prereq-${topic.id}`}>
              Add a prerequisite
            </label>
            <select
              id={`add-prereq-${topic.id}`}
              value={choice}
              onChange={(e) => setChoice(e.target.value)}
              disabled={busy}
              className="min-w-0 flex-1 rounded-md border border-[rgba(var(--ink-rgb),0.15)] bg-[var(--bg-linen)] px-2 py-1 text-xs text-[var(--ink)]"
            >
              <option value="">Add a prerequisite...</option>
              {candidates.map((c) => (
                <option key={c.id} value={c.id}>
                  {candidateLabel(c)}
                </option>
              ))}
            </select>
            <Button type="submit" size="sm" variant="outline" disabled={!choice || busy}>
              Add
            </Button>
          </form>
        ) : (
          <p className="mt-2 text-[11px] text-[var(--ink)]/50">No other topics can be added here.</p>
        )}
        {editError && (
          <p role="alert" className="mt-1.5 text-xs text-[var(--error-text)]">
            {editError}
          </p>
        )}
      </section>

      <section className="mt-3">
        <h4 className="text-[11px] font-medium text-[var(--ink)]/60">
          Unlocks{totalAfter > unlocks.length ? ` · ${totalAfter} topics build on this` : ""}
        </h4>
        {unlocks.length ? (
          <ul className="mt-1 -mx-1">
            {unlocks.map((t) => (
              <TopicLink key={t.id} topic={t} onSelect={onSelectTopic} />
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-[var(--ink)]/60">Nothing depends on this yet.</p>
        )}
      </section>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" onClick={onAsk}>
          Ask about this
        </Button>
        <Button size="sm" variant="outline" onClick={onQuiz}>
          Take quiz
        </Button>
        {isFocused ? (
          <Button size="sm" variant="ghost" onClick={onShowAll}>
            Show all
          </Button>
        ) : (
          <Button size="sm" variant="ghost" onClick={onFocus}>
            Focus
          </Button>
        )}
      </div>
    </aside>
  );
}
