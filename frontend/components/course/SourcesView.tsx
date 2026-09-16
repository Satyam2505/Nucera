"use client";

import { useEffect, useState } from "react";

import { api, Source } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";

const SOURCE_TYPE_LABEL: Record<string, string> = {
  official_upload: "Official upload",
  self_supplied: "Self-supplied",
  web_fallback: "Web fallback",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6h16Z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function SourcesView({
  topicId,
  refreshKey,
  onAddSource,
}: {
  topicId: number | null;
  refreshKey: number;
  onAddSource: () => void;
}) {
  const { topics } = useAppState();
  const topic = topics.find((t) => t.id === topicId);

  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setConfirmingId(null);
    setError(null);
    if (!topicId) {
      setSources([]);
      return;
    }
    setLoading(true);
    api
      .listSources(topicId)
      .then(setSources)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load sources"))
      .finally(() => setLoading(false));
  }, [topicId, refreshKey]);

  async function handleDelete(sourceId: number) {
    if (confirmingId !== sourceId) {
      setConfirmingId(sourceId);
      setTimeout(() => setConfirmingId((current) => (current === sourceId ? null : current)), 4000);
      return;
    }
    setDeletingId(sourceId);
    setError(null);
    try {
      await api.deleteSource(sourceId);
      setSources((prev) => prev.filter((s) => s.id !== sourceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete source");
    } finally {
      setDeletingId(null);
      setConfirmingId(null);
    }
  }

  if (!topicId) {
    return <div className="p-8 text-sm text-stone-500 dark:text-stone-400">Select a topic to manage its sources.</div>;
  }

  return (
    <div className="p-8 max-w-2xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--ink)]">Sources — {topic?.name}</h2>
        <button
          onClick={onAddSource}
          className="text-xs font-medium px-3.5 py-1.5 rounded-full border border-[rgba(var(--accent-rgb),0.50)] text-[var(--accent-hover)] hover:bg-[rgba(var(--accent-rgb),0.10)] transition shrink-0"
        >
          + Add source
        </button>
      </div>

      {error && (
        <p className="text-xs text-[var(--error-text)] bg-[var(--error-bg)] border border-[var(--error-border)] rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {loading && <p className="text-sm text-stone-500 dark:text-stone-400">Loading sources...</p>}

      {!loading && sources.length === 0 && (
        <p className="text-sm text-stone-500 dark:text-stone-400">
          No sources yet — add one to start building this topic&apos;s material.
        </p>
      )}

      <div className="space-y-2">
        {sources.map((source) => (
          <div key={source.id} className="surface rounded-xl p-4 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-[var(--ink)] truncate">{source.title}</p>
              <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
                {SOURCE_TYPE_LABEL[source.source_type] ?? source.source_type} · {source.chunk_count}{" "}
                {source.chunk_count === 1 ? "chunk" : "chunks"} · added {formatDate(source.created_at)}
              </p>
            </div>
            <button
              onClick={() => handleDelete(source.id)}
              disabled={deletingId === source.id}
              className={`shrink-0 flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border transition disabled:opacity-50 ${
                confirmingId === source.id
                  ? "border-[var(--error-border)] text-[var(--error-text)] bg-[var(--error-bg)]"
                  : "border-[rgba(var(--ink-rgb),0.15)] text-stone-600 dark:text-stone-400 hover:border-[var(--error-border)] hover:text-[var(--error-text)] hover:bg-[var(--error-bg)]"
              }`}
            >
              <TrashIcon />
              {deletingId === source.id ? "Deleting..." : confirmingId === source.id ? "Confirm delete?" : "Delete"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
