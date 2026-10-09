"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import AppSidebar from "@/components/AppSidebar";
import CreateCourseModal from "@/components/CreateCourseModal";
import LoadErrorNotice from "@/components/LoadErrorNotice";
import { api } from "@/lib/api";
import { failureReason } from "@/lib/api-errors";
import { selectLibraryView } from "@/lib/app-state-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useAppState } from "@/lib/AppStateContext";
import { useAuth } from "@/lib/AuthContext";
import { courseHref, topicLocation } from "@/lib/courses";
import { getGreeting, getTimePeriod } from "@/lib/greeting";
import { useDynamicGreeting } from "@/lib/useDynamicGreeting";
import { getWelcomeContext } from "@/lib/welcomeContext";

function BookmarkIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="2"
    >
      <path d="M19 21 12 16 5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" strokeLinejoin="round" />
    </svg>
  );
}

export default function LandingPage() {
  const { courses, topics, masteryByTopic, graph, loading, loaded, error, refresh } = useAppState();
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [revisionError, setRevisionError] = useState<string | null>(null);

  const now = useDynamicGreeting();
  const period = useMemo(() => getTimePeriod(now), [now]);
  const greeting = useMemo(() => getGreeting(now, user?.name), [now, user?.name]);

  // Server-rendered state always starts expanded (matches desktop) — on a
  // narrow window the sidebar is an overlay (Sidebar's own mobile mode), so
  // it should default closed rather than covering the page on first paint.
  // Done in an effect, after hydration, so there's no SSR/client mismatch.
  useEffect(() => {
    if (window.innerWidth < 768) setSidebarOpen(false);
  }, []);

  const filtered = query
    ? courses.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()))
    : courses;

  const welcome = useMemo(
    () => getWelcomeContext(period, topics, masteryByTopic, graph, courses),
    [period, topics, masteryByTopic, graph, courses]
  );

  const masteredCount = topics.filter((t) => masteryByTopic[t.id]?.status === "mastered").length;

  const needsAttention = useMemo(
    () =>
      topics
        .filter((t) => (masteryByTopic[t.id]?.status ?? "unmastered") !== "mastered")
        .sort((a, b) => (masteryByTopic[a.id]?.score ?? 0) - (masteryByTopic[b.id]?.score ?? 0))
        .slice(0, 5),
    [topics, masteryByTopic]
  );

  const revisionList = useMemo(
    () => topics.filter((t) => masteryByTopic[t.id]?.flagged_for_revision),
    [topics, masteryByTopic]
  );

  // If the library could not be loaded at all there is nothing true to show
  // (no courses, no counts), so say that instead of an empty library.
  const view = selectLibraryView({ loading, loaded, error });
  const retry = () => {
    void refresh();
  };

  async function toggleRevision(topicId: number) {
    setRevisionError(null);
    try {
      await api.toggleRevision(topicId);
    } catch (err) {
      setRevisionError(`Couldn't update the revision list. ${failureReason(err)}`);
      return;
    }
    await refresh();
  }

  return (
    <SidebarProvider
      open={sidebarOpen}
      onOpenChange={setSidebarOpen}
      style={{ "--sidebar-width": "20rem", "--sidebar-width-icon": "4rem" } as React.CSSProperties}
      className="min-h-screen"
    >
      <AppSidebar
        courses={filtered}
        loading={loading}
        loadError={view === "blocking-error" ? error : null}
        onRetry={retry}
        onNewCourse={() => setShowCreate(true)}
        query={query}
        onQueryChange={setQuery}
      />

      <SidebarInset className="hero-gradient min-w-0 overflow-y-auto">
        <div className="min-h-full flex flex-col items-center px-6 py-16 gap-8">
          {view === "blocking-error" && (
            <div className="w-full max-w-xl pt-8">
              <LoadErrorNotice variant="load" reason={error ?? ""} onRetry={retry} />
            </div>
          )}
          {view === "ready-with-notice" && (
            <div className="w-full max-w-3xl">
              <LoadErrorNotice variant="refresh" reason={error ?? ""} onRetry={retry} />
            </div>
          )}
          {/* Until the library has loaded there is nothing true to show: a greeting
              and zero counts here would read as an empty library. */}
          {view === "loading" && (
            <p role="status" className="pt-8 text-sm text-fg-secondary">
              Loading your courses...
            </p>
          )}
          {(view === "ready" || view === "ready-with-notice") && (
            <>
              <div className="flex flex-col items-center gap-3 text-center">
                <h1
                  key={greeting}
                  className="font-brand animate-in fade-in-0 duration-200 text-4xl sm:text-5xl font-semibold tracking-tight text-[var(--ink)]"
                >
                  {greeting}
                </h1>
                <p
                  key={welcome.message}
                  className="animate-in fade-in-0 duration-200 text-base text-fg-secondary max-w-md"
                >
                  {welcome.message}
                </p>
                {welcome.cta && (
                  <Button asChild size="sm" className="mt-1">
                    <Link href={welcome.cta.href}>{welcome.cta.label}</Link>
                  </Button>
                )}
                {welcome.contextLine && (
                  <p className="text-xs text-fg-tertiary">{welcome.contextLine}</p>
                )}
              </div>

              <div className="w-full max-w-3xl grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Card className="bg-[var(--bg-surface)] border-[rgba(var(--ink-rgb),0.1)]">
                  <CardHeader className="pb-2">
                    <CardDescription>Courses</CardDescription>
                    <CardTitle className="text-3xl text-[var(--ink)]">{courses.length}</CardTitle>
                  </CardHeader>
                </Card>
                <Card className="bg-[var(--bg-surface)] border-[rgba(var(--ink-rgb),0.1)]">
                  <CardHeader className="pb-2">
                    <CardDescription>Topics mastered</CardDescription>
                    <CardTitle className="text-3xl text-[var(--ink)]">
                      {masteredCount}
                      <span className="text-base font-normal text-fg-secondary">
                        {" "}
                        / {topics.length}
                      </span>
                    </CardTitle>
                  </CardHeader>
                </Card>
                <Card className="bg-[var(--bg-surface)] border-[rgba(var(--ink-rgb),0.1)]">
                  <CardHeader className="pb-2">
                    <CardDescription>Revision list</CardDescription>
                    <CardTitle className="text-3xl text-[var(--ink)]">{revisionList.length}</CardTitle>
                  </CardHeader>
                </Card>
              </div>

              {revisionList.length > 0 && (
                <Card className="w-full max-w-3xl bg-[var(--bg-surface)] border-[rgba(var(--ink-rgb),0.1)]">
                  <CardHeader>
                    <CardTitle className="text-base text-[var(--ink)]">Revision list</CardTitle>
                    <CardDescription>Topics you&apos;ve flagged to come back to</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-1">
                    {revisionError && (
                      <p role="alert" className="px-3 pb-1 text-xs text-[var(--error-text)]">
                        {revisionError}
                      </p>
                    )}
                    {revisionList.map((topic) => (
                      <div
                        key={topic.id}
                        className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-[rgba(var(--ink-rgb),0.05)] transition group"
                      >
                        <Link href={courseHref(topic.course_id)} className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-[var(--ink)] truncate">{topic.name}</p>
                          <p className="text-xs text-fg-tertiary truncate">{topicLocation(topic)}</p>
                        </Link>
                        <button
                          onClick={() => toggleRevision(topic.id)}
                          className="shrink-0 ml-3 p-1.5 rounded-lg text-[var(--accent)] hover:bg-[rgba(var(--accent-rgb),0.1)] transition"
                          aria-label="Remove from revision list"
                          title="Remove from revision list"
                        >
                          <BookmarkIcon filled />
                        </button>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {needsAttention.length > 0 && (
                <Card className="w-full max-w-3xl bg-[var(--bg-surface)] border-[rgba(var(--ink-rgb),0.1)]">
                  <CardHeader>
                    <CardTitle className="text-base text-[var(--ink)]">Needs attention</CardTitle>
                    <CardDescription>Your lowest-mastery topics across every course</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-1">
                    {needsAttention.map((topic) => {
                      const mastery = masteryByTopic[topic.id];
                      return (
                        <Link
                          key={topic.id}
                          href={courseHref(topic.course_id)}
                          className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-[rgba(var(--ink-rgb),0.05)] transition"
                        >
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-[var(--ink)] truncate">{topic.name}</p>
                            <p className="text-xs text-fg-tertiary truncate">{topicLocation(topic)}</p>
                          </div>
                          <Badge variant="outline" className="shrink-0 ml-3">
                            {mastery?.score ?? 0}%
                          </Badge>
                        </Link>
                      );
                    })}
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      </SidebarInset>

      {showCreate && <CreateCourseModal onClose={() => setShowCreate(false)} />}
    </SidebarProvider>
  );
}
