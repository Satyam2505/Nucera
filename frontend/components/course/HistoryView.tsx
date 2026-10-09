"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api, CourseTree, SessionHistoryItem } from "@/lib/api";
import { groupByDay, masteryChange, nextCursor, SESSION_LABEL, timeLabel } from "@/lib/history";

const PAGE_SIZE = 30;

// The course's study sessions, newest first and grouped by day: every question
// asked of the tutor, every graded quiz and every self-report, with the mastery
// change each one caused. Can be narrowed to one topic.
export default function HistoryView({ tree }: { tree: CourseTree }) {
  const [topicFilter, setTopicFilter] = useState<number | "all">("all");
  const [items, setItems] = useState<SessionHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  // Bumped by every (re)load so a slow response for an earlier filter is ignored.
  const latest = useRef(0);

  const topics = useMemo(() => tree.modules.flatMap((m) => m.topics.map((t) => ({ id: t.id, name: t.name }))), [tree]);

  const fetchPage = useCallback(
    (beforeId?: number) =>
      api.listSessions({
        courseId: tree.id,
        topicId: topicFilter === "all" ? undefined : topicFilter,
        beforeId,
        limit: PAGE_SIZE,
      }),
    [tree.id, topicFilter]
  );

  const load = useCallback(async () => {
    const requestId = ++latest.current;
    setLoading(true);
    setError(null);
    try {
      const page = await fetchPage();
      if (requestId !== latest.current) return;
      setItems(page);
      setHasMore(nextCursor(page, PAGE_SIZE) !== null);
    } catch (err) {
      if (requestId === latest.current) setError(err instanceof Error ? err.message : "Couldn't load your history.");
    } finally {
      if (requestId === latest.current) setLoading(false);
    }
  }, [fetchPage]);

  useEffect(() => {
    load();
  }, [load]);

  async function loadMore() {
    const cursor = nextCursor(items, PAGE_SIZE) ?? items[items.length - 1]?.id;
    if (cursor === undefined || loadingMore) return;
    const requestId = latest.current;
    setLoadingMore(true);
    try {
      const page = await fetchPage(cursor);
      if (requestId !== latest.current) return;
      setItems((prev) => [...prev, ...page]);
      setHasMore(page.length >= PAGE_SIZE);
    } catch (err) {
      if (requestId === latest.current) setError(err instanceof Error ? err.message : "Couldn't load more.");
    } finally {
      setLoadingMore(false);
    }
  }

  const groups = useMemo(() => groupByDay(items, new Date()), [items]);

  return (
    <div className="p-8 max-w-2xl mx-auto space-y-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-[var(--ink)]">Study history</h2>
        <label className="flex items-center gap-2 text-xs text-fg-secondary">
          Topic
          <select
            value={topicFilter}
            onChange={(e) => setTopicFilter(e.target.value === "all" ? "all" : Number(e.target.value))}
            className="rounded-md border border-[rgba(var(--ink-rgb),0.15)] bg-[var(--bg-linen)] px-2 py-1 text-xs text-[var(--ink)]"
          >
            <option value="all">All topics</option>
            {topics.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <div className="space-y-3">
          <Alert variant="destructive" className="bg-[var(--error-bg)] border-[var(--error-border)]">
            <AlertDescription className="text-[var(--error-text)]">{error}</AlertDescription>
          </Alert>
          <Button variant="outline" onClick={load}>
            Try again
          </Button>
        </div>
      )}

      {loading && !error && (
        <p role="status" className="text-sm text-fg-secondary">
          Loading history...
        </p>
      )}

      {!loading && !error && items.length === 0 && (
        <p className="text-sm text-fg-secondary">
          Nothing here yet. Ask the tutor a question or take a quiz and it will show up.
        </p>
      )}

      {!error &&
        groups.map((group) => (
          <section key={group.label} aria-label={group.label} className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-tertiary">
              {group.label}
            </h3>
            <ul className="divide-y divide-[rgba(var(--ink-rgb),0.08)] rounded-xl border border-[rgba(var(--ink-rgb),0.10)] surface">
              {group.items.map((s) => {
                const change = masteryChange(s);
                return (
                  <li key={s.id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <p className="text-sm text-[var(--ink)]">{SESSION_LABEL[s.type]}</p>
                      <p className="text-xs text-fg-secondary truncate">{s.topic_name}</p>
                    </div>
                    <div className="text-right shrink-0">
                      {change && (
                        <p
                          className={`text-xs font-medium ${
                            s.score_delta > 0 ? "text-[var(--status-mastered)]" : "text-[var(--status-missed)]"
                          }`}
                        >
                          {change}
                        </p>
                      )}
                      <p className="text-xs text-fg-tertiary">{timeLabel(s)}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}

      {!loading && !error && hasMore && (
        <Button variant="outline" onClick={loadMore} disabled={loadingMore} className="w-full">
          {loadingMore ? "Loading..." : "Show older"}
        </Button>
      )}
    </div>
  );
}
