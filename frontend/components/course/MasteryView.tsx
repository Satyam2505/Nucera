"use client";

import { useMemo, useState } from "react";

import { Card } from "@/components/ui/card";
import type { CourseTree } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";
import { STATUS_COLOR, STATUS_LABEL, type MasteryStatusKey } from "@/lib/status-colors";

const ORDER: MasteryStatusKey[] = ["mastered", "in_progress", "unmastered", "missed"];
const RADIUS = 80;
const STROKE = 16;
const SIZE = (RADIUS + STROKE) * 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

interface Entry {
  topic: { id: number; name: string };
  score: number;
  status: MasteryStatusKey;
}

interface ModuleEntries {
  id: number;
  name: string;
  entries: Entry[];
  avgScore: number;
}

export default function MasteryView({ tree }: { tree: CourseTree }) {
  const { masteryByTopic } = useAppState();
  const [expanded, setExpanded] = useState(false);

  // App-wide mastery is the freshest source (quiz results land there first);
  // the tree's own values cover topics it hasn't caught up with yet.
  const modules: ModuleEntries[] = useMemo(
    () =>
      tree.modules.map((module) => {
        const entries = module.topics.map((topic) => {
          const mastery = masteryByTopic[topic.id];
          return {
            topic,
            score: mastery?.score ?? topic.score,
            status: (mastery?.status ?? topic.status) as MasteryStatusKey,
          };
        });
        const avgScore = entries.length
          ? Math.round(entries.reduce((sum, e) => sum + e.score, 0) / entries.length)
          : 0;
        return { id: module.id, name: module.name, entries, avgScore };
      }),
    [tree, masteryByTopic]
  );
  const entries: Entry[] = useMemo(() => modules.flatMap((m) => m.entries), [modules]);

  const counts = useMemo(() => {
    const acc = { mastered: 0, in_progress: 0, unmastered: 0, missed: 0 } as Record<MasteryStatusKey, number>;
    entries.forEach((e) => acc[e.status]++);
    return acc;
  }, [entries]);

  const total = entries.length || 1;
  const avgScore = entries.length
    ? Math.round(entries.reduce((sum, e) => sum + e.score, 0) / entries.length)
    : 0;

  const excelling = [...entries].filter((e) => e.score >= 70).sort((a, b) => b.score - a.score);
  const developing = [...entries]
    .filter((e) => e.score >= 40 && e.score < 70)
    .sort((a, b) => b.score - a.score);
  const lagging = [...entries].filter((e) => e.score < 40).sort((a, b) => a.score - b.score);

  if (entries.length === 0) {
    return <div className="p-8 text-sm text-stone-500 dark:text-stone-400">No topics in this course yet.</div>;
  }

  let cumulative = 0;

  return (
    <div className="p-8 flex flex-col items-center gap-8">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="relative group focus:outline-none"
        aria-label="Toggle mastery breakdown"
      >
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} className="-rotate-90">
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="rgba(var(--ink-rgb), 0.08)"
            strokeWidth={STROKE}
          />
          {ORDER.map((status) => {
            const count = counts[status];
            if (!count) return null;
            const length = (count / total) * CIRCUMFERENCE;
            const offset = -cumulative;
            cumulative += length;
            return (
              <circle
                key={status}
                cx={SIZE / 2}
                cy={SIZE / 2}
                r={RADIUS}
                fill="none"
                stroke={STATUS_COLOR[status]}
                strokeWidth={STROKE}
                strokeDasharray={`${length} ${CIRCUMFERENCE - length}`}
                strokeDashoffset={offset}
                style={{ transition: "stroke-dashoffset 0.4s ease" }}
              />
            );
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-semibold text-[var(--ink)]">{avgScore}</span>
          <span className="text-[11px] text-stone-500 dark:text-stone-400 mt-0.5">course mastery</span>
          <span className="text-[10px] text-[var(--accent-hover)] mt-2 group-hover:underline">
            {expanded ? "Hide breakdown" : "Click for breakdown"}
          </span>
        </div>
      </button>

      <div className="flex items-center gap-4 flex-wrap justify-center">
        {ORDER.map((status) => (
          <div key={status} className="flex items-center gap-1.5 text-xs text-stone-600 dark:text-stone-400">
            <span className="h-2 w-2 rounded-full" style={{ background: STATUS_COLOR[status] }} />
            {STATUS_LABEL[status]} ({counts[status]})
          </div>
        ))}
      </div>

      {expanded && (
        <div className="w-full max-w-3xl grid grid-cols-1 md:grid-cols-3 gap-4">
          <BreakdownList title="Excelling" tone="mastered" items={excelling} empty="No standout topics yet." />
          <BreakdownList
            title="Steady progress"
            tone="in_progress"
            items={developing}
            empty="Nothing in this band yet."
          />
          <BreakdownList title="Lagging behind" tone="missed" items={lagging} empty="Nothing lagging — nice." />
        </div>
      )}

      <div className="w-full max-w-3xl space-y-3">
        <h2 className="text-sm font-semibold text-[var(--ink)]">By module</h2>
        {modules.map((module, index) => (
          <ModuleCard key={module.id} index={index} module={module} />
        ))}
      </div>
    </div>
  );
}

function ModuleCard({ index, module }: { index: number; module: ModuleEntries }) {
  return (
    <Card className="surface rounded-2xl p-4 border-[rgba(var(--ink-rgb),0.09)]">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-[var(--ink)] truncate">
          {index + 1}. {module.name}
        </p>
        <span className="text-xs text-stone-500 dark:text-stone-400 shrink-0">
          {module.entries.length === 0 ? "No topics" : `${module.avgScore}% average`}
        </span>
      </div>
      {module.entries.length > 0 && (
        <>
          <div
            className="mt-2 h-1.5 rounded-full bg-[rgba(var(--ink-rgb),0.08)] overflow-hidden"
            role="progressbar"
            aria-label={`${module.name} average mastery`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={module.avgScore}
          >
            <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${module.avgScore}%` }} />
          </div>
          <ul className="mt-3 space-y-1.5">
            {module.entries.map(({ topic, score, status }) => (
              <li key={topic.id} className="flex items-center justify-between gap-3 text-sm text-[var(--ink)]">
                <span className="flex items-center gap-2 min-w-0">
                  <span
                    className="h-1.5 w-1.5 rounded-full shrink-0"
                    style={{ background: STATUS_COLOR[status] }}
                    aria-hidden
                  />
                  <span className="truncate">{topic.name}</span>
                </span>
                <span className="text-xs text-stone-500 dark:text-stone-400 shrink-0">
                  {STATUS_LABEL[status]} · {score}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

function BreakdownList({
  title,
  tone,
  items,
  empty,
}: {
  title: string;
  tone: MasteryStatusKey;
  items: Entry[];
  empty: string;
}) {
  return (
    <Card className="surface rounded-2xl p-4 border-[rgba(var(--ink-rgb),0.09)]">
      <p className="text-xs font-medium mb-3" style={{ color: STATUS_COLOR[tone] }}>
        {title}
      </p>
      {items.length === 0 && <p className="text-xs text-stone-500 dark:text-stone-400">{empty}</p>}
      <ul className="space-y-2">
        {items.map(({ topic, score }) => (
          <li key={topic.id} className="flex items-center justify-between text-sm text-[var(--ink)]">
            <span className="truncate pr-2">{topic.name}</span>
            <span className="text-xs text-stone-500 dark:text-stone-400 shrink-0">{score}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
