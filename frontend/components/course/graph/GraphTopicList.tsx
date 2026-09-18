"use client";

import type { PathState } from "@/lib/graph-model";
import { STATUS_LABEL } from "@/lib/status-colors";

import { normalizeStatus, PATH_LABEL, PathIcon, StatusIcon } from "./graph-icons";

export interface TopicListItem {
  id: number;
  name: string;
  status: string;
  score: number;
  path: PathState;
}

const GROUP_ORDER: PathState[] = ["attention", "next", "later", "covered"];

interface Props {
  topics: TopicListItem[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

/**
 * The same topics as the map, as a plain list grouped by learning-path state.
 * It sits below the graph so the workspace behaves like a normal page (the
 * graph is a bounded block, not the whole viewport), and gives a keyboard-
 * and screen-reader-friendly way to reach any topic.
 */
export default function GraphTopicList({ topics, selectedId, onSelect }: Props) {
  const groups = GROUP_ORDER.map((state) => ({
    state,
    items: topics.filter((t) => t.path === state),
  })).filter((g) => g.items.length > 0);

  return (
    <section aria-label="Topics in this course" className="mx-auto w-full max-w-3xl px-4 py-8 md:px-6">
      <h2 className="text-sm font-semibold text-[var(--ink)]">Topics in this course</h2>
      <p className="mt-1 text-xs text-[var(--ink)]/60">Grouped by your learning path. Pick one to find it on the map.</p>

      <div className="mt-5 space-y-5">
        {groups.map(({ state, items }) => (
          <div key={state}>
            <h3 className="flex items-center gap-1.5 text-xs font-medium text-[var(--ink)]/70">
              <PathIcon state={state} />
              {PATH_LABEL[state]}
              <span className="text-[var(--ink)]/40">· {items.length}</span>
            </h3>
            <ul className="mt-2 divide-y divide-[rgba(var(--ink-rgb),0.08)] overflow-hidden rounded-xl border border-[rgba(var(--ink-rgb),0.10)] bg-[var(--bg-surface)]">
              {items.map((t) => {
                const status = normalizeStatus(t.status);
                const selected = t.id === selectedId;
                return (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(t.id)}
                      aria-current={selected ? "true" : undefined}
                      className={`flex w-full items-center gap-3 px-3.5 py-2.5 text-left text-sm transition-colors hover:bg-[rgba(var(--ink-rgb),0.05)] focus-visible:bg-[rgba(var(--ink-rgb),0.05)] focus-visible:outline-none ${
                        selected ? "bg-[rgba(var(--accent-rgb),0.10)]" : ""
                      }`}
                    >
                      <StatusIcon status={status} size={14} />
                      <span className="min-w-0 flex-1 truncate text-[var(--ink)]">{t.name}</span>
                      <span className="shrink-0 text-xs tabular-nums text-[var(--ink)]/60">
                        {STATUS_LABEL[status]}
                        {status !== "unmastered" ? ` · ${Math.round(t.score)}%` : ""}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
