"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ReactNode, useEffect, useMemo, useState } from "react";

import ChatView from "@/components/course/ChatView";
import GraphView from "@/components/course/GraphView";
import MasteryView from "@/components/course/MasteryView";
import QuizView from "@/components/course/QuizView";
import SourcesView from "@/components/course/SourcesView";
import UploadModal from "@/components/UploadModal";
import { useAppState } from "@/lib/AppStateContext";
import { STATUS_COLOR, type MasteryStatusKey } from "@/lib/status-colors";

type ViewKey = "chat" | "quiz" | "graph" | "mastery" | "sources";

const VIEWS: { key: ViewKey; label: string; icon: ReactNode }[] = [
  {
    key: "chat",
    label: "Ask a question",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
      </svg>
    ),
  },
  {
    key: "quiz",
    label: "Take quiz",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M9 11l3 3L22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
    ),
  },
  {
    key: "graph",
    label: "Prerequisite graph",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="6" cy="6" r="3" />
        <circle cx="18" cy="6" r="3" />
        <circle cx="12" cy="18" r="3" />
        <path d="M8.5 7.5L12 15M15.5 7.5L12 15" />
      </svg>
    ),
  },
  {
    key: "mastery",
    label: "Mastery level",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 3a9 9 0 0 1 9 9" />
      </svg>
    ),
  },
  {
    key: "sources",
    label: "Sources",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
        <path d="M14 2v6h6M9 13h6M9 17h6" strokeLinecap="round" />
      </svg>
    ),
  },
];

function ListIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
    </svg>
  );
}

export default function CourseWorkspace() {
  const params = useParams<{ course: string }>();
  const courseName = decodeURIComponent(params.course);

  const { topics, masteryByTopic, loading, selectedTopicId, setSelectedTopicId } = useAppState();
  const [view, setView] = useState<ViewKey>("chat");
  const [showUpload, setShowUpload] = useState(false);
  const [topicsOpen, setTopicsOpen] = useState(true);
  // Bumped whenever the upload modal closes so SourcesView (which keeps its
  // own fetched list, not part of global AppState) refetches — otherwise
  // adding a source via the header button wouldn't show up there.
  const [sourcesRefreshKey, setSourcesRefreshKey] = useState(0);

  // Same reasoning as the landing page's AppSidebar: this 256px topics
  // column is an overlay below md, so it should default closed there
  // instead of covering the page on first paint. Done post-mount to avoid
  // an SSR/client mismatch.
  useEffect(() => {
    if (window.innerWidth < 768) setTopicsOpen(false);
  }, []);

  const courseTopics = useMemo(
    () => topics.filter((t) => t.course === courseName),
    [topics, courseName]
  );

  useEffect(() => {
    if (courseTopics.length && !courseTopics.some((t) => t.id === selectedTopicId)) {
      setSelectedTopicId(courseTopics[0].id);
    }
  }, [courseTopics, selectedTopicId, setSelectedTopicId]);

  const activeTopicId = courseTopics.some((t) => t.id === selectedTopicId) ? selectedTopicId : null;

  return (
    <div className="min-h-screen hero-gradient text-[var(--ink)] flex flex-col">
      <header className="flex items-center justify-between px-6 py-4 border-b border-[rgba(var(--ink-rgb),0.10)] surface-strong sticky top-0 z-20">
        <div className="flex items-center gap-4 min-w-0">
          <button
            onClick={() => setTopicsOpen((v) => !v)}
            className="md:hidden p-1.5 -ml-1.5 rounded-lg text-stone-500 dark:text-stone-400 hover:text-[var(--ink)] hover:bg-[rgba(var(--ink-rgb),0.08)] transition shrink-0"
            aria-label={topicsOpen ? "Hide topics" : "Show topics"}
          >
            <ListIcon />
          </button>
          <Link href="/" className="text-sm text-stone-500 dark:text-stone-400 hover:text-[var(--ink)] transition shrink-0">
            ← Library
          </Link>
          <h1 className="text-base font-semibold text-[var(--ink)] truncate">{courseName}</h1>
        </div>
        <button
          onClick={() => setShowUpload(true)}
          className="text-xs font-medium px-3.5 py-1.5 rounded-full border border-[rgba(var(--accent-rgb),0.50)] text-[var(--accent-hover)] hover:bg-[rgba(var(--accent-rgb),0.10)] transition shrink-0"
        >
          + Add source
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden relative">
        {/* Positioned `absolute` within this already-below-header `relative`
            row (not `fixed`), so it fills exactly the remaining viewport
            height without hardcoding the header's pixel height anywhere. */}
        {topicsOpen && (
          <div className="absolute inset-0 z-30 bg-black/40 md:hidden" onClick={() => setTopicsOpen(false)} />
        )}

        {topicsOpen && (
          <aside className="w-64 max-w-[80vw] shrink-0 border-r border-[rgba(var(--ink-rgb),0.10)] surface-deep overflow-y-auto p-3 space-y-1 absolute inset-y-0 left-0 z-40 md:relative md:inset-auto md:z-auto">
            {loading && <p className="px-3 py-2 text-xs text-stone-500 dark:text-stone-400">Loading topics...</p>}
            {!loading && courseTopics.length === 0 && (
              <p className="px-3 py-2 text-xs text-stone-500 dark:text-stone-400">No topics yet — add a source to get started.</p>
            )}
            {courseTopics.map((topic) => {
              const status = (masteryByTopic[topic.id]?.status ?? "unmastered") as MasteryStatusKey;
              const active = topic.id === activeTopicId;
              return (
                <button
                  key={topic.id}
                  onClick={() => {
                    setSelectedTopicId(topic.id);
                    if (window.innerWidth < 768) setTopicsOpen(false);
                  }}
                  className={`w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm transition border ${
                    active
                      ? "bg-[rgba(var(--accent-rgb),0.12)] text-[var(--accent-hover)] border-[rgba(var(--accent-rgb),0.30)]"
                      : "text-stone-600 dark:text-stone-400 hover:bg-[rgba(var(--ink-rgb),0.05)] border-transparent"
                  }`}
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full shrink-0"
                    style={{ background: STATUS_COLOR[status] }}
                    aria-hidden
                  />
                  <span className="truncate">{topic.name}</span>
                </button>
              );
            })}
          </aside>
        )}

        <main className="flex-1 flex flex-col min-w-0">
          <div className="flex items-center gap-2 px-6 py-3 border-b border-[rgba(var(--ink-rgb),0.10)] overflow-x-auto">
            {VIEWS.map((v) => (
              <button
                key={v.key}
                onClick={() => setView(v.key)}
                className={`flex items-center gap-1.5 text-xs font-medium px-3.5 py-2 rounded-full transition shrink-0 ${
                  view === v.key
                    ? "bg-[var(--accent)] text-[var(--accent-ink)] accent-ring"
                    : "text-stone-600 dark:text-stone-400 hover:text-[var(--ink)] hover:bg-[rgba(var(--ink-rgb),0.05)]"
                }`}
              >
                {v.icon}
                {v.label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto">
            {view === "chat" && <ChatView topicId={activeTopicId} />}
            {view === "quiz" && <QuizView topicId={activeTopicId} />}
            {view === "graph" && <GraphView courseName={courseName} />}
            {view === "mastery" && <MasteryView courseTopics={courseTopics} />}
            {view === "sources" && (
              <SourcesView
                topicId={activeTopicId}
                refreshKey={sourcesRefreshKey}
                onAddSource={() => setShowUpload(true)}
              />
            )}
          </div>
        </main>
      </div>

      {showUpload && (
        <UploadModal
          onClose={() => {
            setShowUpload(false);
            setSourcesRefreshKey((k) => k + 1);
          }}
        />
      )}
    </div>
  );
}
