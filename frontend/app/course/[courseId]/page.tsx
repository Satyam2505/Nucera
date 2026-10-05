"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import ChatView from "@/components/course/ChatView";
import CourseMenu from "@/components/course/CourseMenu";
import GraphView from "@/components/course/GraphView";
import MasteryView from "@/components/course/MasteryView";
import ModuleRail from "@/components/course/ModuleRail";
import NameDialog from "@/components/course/NameDialog";
import QuizView from "@/components/course/QuizView";
import SourcesView from "@/components/course/SourcesView";
import ViewTabs, { type ViewKey } from "@/components/course/ViewTabs";
import { Button } from "@/components/ui/button";
import UploadModal from "@/components/UploadModal";
import { api, CourseTree } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";
import { useCourseTree } from "@/lib/useCourseTree";

function HomeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
    </svg>
  );
}

// The route param must be a plain positive integer; anything else (a stale
// name-based link, "abc", "1.5") is treated as an unknown course.
function parseCourseId(raw: string | undefined): number | null {
  return raw && /^[1-9]\d*$/.test(raw) ? Number(raw) : null;
}

function HomeLink() {
  return (
    <Button
      variant="ghost"
      size="icon"
      asChild
      className="shrink-0 text-stone-500 dark:text-stone-400 hover:text-[var(--ink)] hover:bg-[rgba(var(--ink-rgb),0.08)]"
    >
      <Link href="/" aria-label="Home" title="Home">
        <HomeIcon />
      </Link>
    </Button>
  );
}

function PageMessage({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="h-screen hero-gradient text-[var(--ink)] flex flex-col">
      <header className="flex items-center gap-4 px-6 py-4 border-b border-[rgba(var(--ink-rgb),0.10)] surface-strong">
        <HomeLink />
      </header>
      <div className="flex-1 flex flex-col items-center justify-center gap-3 px-6 text-center">
        <h1 className="text-base font-semibold text-[var(--ink)]">{title}</h1>
        {children}
      </div>
    </div>
  );
}

export default function CourseWorkspace() {
  const params = useParams<{ courseId: string }>();
  const router = useRouter();
  const courseId = parseCourseId(params.courseId);

  const { masteryByTopic, selectedTopicId, setSelectedTopicId, refresh } = useAppState();
  const { state, reload, retry, setTree } = useCourseTree(courseId);
  const tree = state.status === "ready" ? state.tree : null;

  const [view, setView] = useState<ViewKey>("chat");
  const [showUpload, setShowUpload] = useState(false);
  const [emptyDialog, setEmptyDialog] = useState<"module" | "topic" | null>(null);
  const [topicsOpen, setTopicsOpen] = useState(true);
  // Bumped whenever the upload modal closes so SourcesView (which keeps its
  // own fetched list, not part of global AppState) refetches — otherwise
  // adding a source via the header button wouldn't show up there.
  const [sourcesRefreshKey, setSourcesRefreshKey] = useState(0);

  // Same reasoning as the landing page's AppSidebar: this 256px rail is an
  // overlay below md, so it should default closed there instead of covering
  // the page on first paint. Done post-mount to avoid an SSR/client mismatch.
  useEffect(() => {
    if (window.innerWidth < 768) setTopicsOpen(false);
  }, []);

  const topicIds = useMemo(
    () => tree?.modules.flatMap((m) => m.topics.map((t) => t.id)) ?? [],
    [tree]
  );
  // Selection is resolved against this course's own topics every render, so a
  // topic from another course (the global selection) or one that was just
  // deleted can never reach the views — they fall back to the first topic.
  const activeTopicId =
    selectedTopicId !== null && topicIds.includes(selectedTopicId) ? selectedTopicId : (topicIds[0] ?? null);

  // After any structure change: show the new tree, then refresh app-wide state
  // so the sidebar counts and the landing page stay in step.
  const handleChanged = useCallback(
    async (updated?: CourseTree) => {
      if (updated) setTree(updated);
      else await reload();
      await refresh();
    },
    [reload, setTree, refresh]
  );

  async function handleToggleRevision(topicId: number) {
    await api.toggleRevision(topicId);
    await refresh();
  }

  if (state.status === "notfound") {
    return (
      <PageMessage title="Course not found">
        <p className="text-sm text-stone-500 dark:text-stone-400">It may have been deleted, or the link is wrong.</p>
        <Button asChild variant="outline">
          <Link href="/">Back to your courses</Link>
        </Button>
      </PageMessage>
    );
  }
  if (state.status === "error") {
    return (
      <PageMessage title="Couldn't load this course">
        <p role="alert" className="text-sm text-[var(--error-text)] max-w-md">
          {state.message}
        </p>
        <Button onClick={retry} variant="outline">
          Try again
        </Button>
      </PageMessage>
    );
  }
  if (!tree) {
    return (
      <PageMessage title="Loading course...">
        <span className="sr-only">Loading</span>
      </PageMessage>
    );
  }

  const topicCount = topicIds.length;

  return (
    <div className="h-screen hero-gradient text-[var(--ink)] flex flex-col">
      <header className="flex items-center justify-between gap-3 px-6 py-4 border-b border-[rgba(var(--ink-rgb),0.10)] surface-strong sticky top-0 z-20">
        <div className="flex items-center gap-4 min-w-0">
          <button
            onClick={() => setTopicsOpen((v) => !v)}
            className="md:hidden p-1.5 -ml-1.5 rounded-lg text-stone-500 dark:text-stone-400 hover:text-[var(--ink)] hover:bg-[rgba(var(--ink-rgb),0.08)] transition shrink-0"
            aria-label={topicsOpen ? "Hide modules" : "Show modules"}
          >
            <ListIcon />
          </button>
          <HomeLink />
          <div className="min-w-0">
            <h1 className="text-base font-semibold text-[var(--ink)] truncate">{tree.name}</h1>
            {tree.description && (
              <p className="text-xs text-stone-500 dark:text-stone-400 truncate">{tree.description}</p>
            )}
          </div>
        </div>
        <CourseMenu
          course={{ id: tree.id, name: tree.name, description: tree.description, topicCount }}
          onRenamed={handleChanged}
          onDeleted={async () => {
            await refresh();
            router.push("/");
          }}
        />
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden relative">
        {/* Positioned `absolute` within this already-below-header `relative`
            row (not `fixed`), so it fills exactly the remaining viewport
            height without hardcoding the header's pixel height anywhere. */}
        {topicsOpen && (
          <div className="absolute inset-0 z-30 bg-black/40 md:hidden" onClick={() => setTopicsOpen(false)} />
        )}

        {topicsOpen && (
          <aside className="w-64 max-w-[80vw] shrink-0 border-r border-sidebar-border bg-sidebar text-sidebar-foreground overflow-y-auto p-3 absolute inset-y-0 left-0 z-40 md:relative md:inset-auto md:z-auto">
            <ModuleRail
              tree={tree}
              activeTopicId={activeTopicId}
              masteryByTopic={masteryByTopic}
              onSelectTopic={(id) => {
                setSelectedTopicId(id);
                if (window.innerWidth < 768) setTopicsOpen(false);
              }}
              onToggleRevision={handleToggleRevision}
              onChanged={handleChanged}
            />
          </aside>
        )}

        <main className="flex-1 flex flex-col min-w-0">
          {topicCount === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-3 px-6 text-center">
              <h2 className="text-base font-semibold text-[var(--ink)]">
                {tree.modules.length === 0 ? "Add your first module" : "Add your first topic"}
              </h2>
              <p className="text-sm text-stone-500 dark:text-stone-400 max-w-sm">
                {tree.modules.length === 0
                  ? "Modules are the chapters of this course. Add one, then fill it with topics."
                  : "Topics are the sections inside a module. Add one to start learning."}
              </p>
              <Button
                onClick={() => setEmptyDialog(tree.modules.length === 0 ? "module" : "topic")}
                className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] accent-ring"
              >
                {tree.modules.length === 0 ? "Add module" : `Add topic to ${tree.modules[0].name}`}
              </Button>
            </div>
          ) : (
            <>
              <ViewTabs view={view} onChange={setView} />

              <div className="flex-1 overflow-y-auto">
                {view === "chat" && <ChatView topicId={activeTopicId} />}
                {view === "quiz" && (
                  <QuizView
                    topicId={activeTopicId}
                    refreshKey={sourcesRefreshKey}
                    onAddSource={() => setShowUpload(true)}
                  />
                )}
                {view === "graph" && (
                  <GraphView
                    courseId={tree.id}
                    onOpenTopic={(topicId, target) => {
                      setSelectedTopicId(topicId);
                      setView(target);
                    }}
                  />
                )}
                {view === "mastery" && <MasteryView tree={tree} />}
                {view === "sources" && (
                  <SourcesView
                    topicId={activeTopicId}
                    refreshKey={sourcesRefreshKey}
                    onAddSource={() => setShowUpload(true)}
                  />
                )}
              </div>
            </>
          )}
        </main>
      </div>

      {emptyDialog === "module" && (
        <NameDialog
          title="Add a module"
          nameLabel="Module name"
          namePlaceholder="e.g. Processes and Threads"
          submitLabel="Add module"
          onSubmit={async (name) => {
            await api.createModule(tree.id, { name });
            await handleChanged();
          }}
          onClose={() => setEmptyDialog(null)}
        />
      )}
      {emptyDialog === "topic" && tree.modules[0] && (
        <NameDialog
          title={`Add a topic to ${tree.modules[0].name}`}
          nameLabel="Topic name"
          namePlaceholder="e.g. Scheduling"
          submitLabel="Add topic"
          onSubmit={async (name) => {
            await api.createTopic({ name, module_id: tree.modules[0].id });
            await handleChanged();
          }}
          onClose={() => setEmptyDialog(null)}
        />
      )}
      {showUpload && (
        <UploadModal
          initialTopicId={activeTopicId}
          onClose={() => {
            setShowUpload(false);
            setSourcesRefreshKey((k) => k + 1);
          }}
        />
      )}
    </div>
  );
}
