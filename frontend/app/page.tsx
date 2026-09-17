"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import AppSidebar from "@/components/AppSidebar";
import CreateCourseModal from "@/components/CreateCourseModal";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useAppState } from "@/lib/AppStateContext";
import { summarizeCourses } from "@/lib/courses";

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
  const { topics, masteryByTopic, loading, refresh } = useAppState();
  const [query, setQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Server-rendered state always starts expanded (matches desktop) — on a
  // narrow window the sidebar is an overlay (Sidebar's own mobile mode), so
  // it should default closed rather than covering the page on first paint.
  // Done in an effect, after hydration, so there's no SSR/client mismatch.
  useEffect(() => {
    if (window.innerWidth < 768) setSidebarOpen(false);
  }, []);

  const courses = useMemo(() => summarizeCourses(topics, masteryByTopic), [topics, masteryByTopic]);
  const filtered = query
    ? courses.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()))
    : courses;

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

  async function toggleRevision(topicId: number) {
    await api.toggleRevision(topicId);
    refresh();
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
        onNewCourse={() => setShowCreate(true)}
        query={query}
        onQueryChange={setQuery}
      />

      <SidebarInset className="hero-gradient min-w-0 overflow-y-auto">
        <div className="min-h-full flex flex-col items-center px-6 py-16 gap-8">
          <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight text-[var(--ink)] text-center">
            Welcome back!
          </h1>

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
                  <span className="text-base font-normal text-stone-500 dark:text-stone-400">
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
                {revisionList.map((topic) => (
                  <div
                    key={topic.id}
                    className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-[rgba(var(--ink-rgb),0.05)] transition group"
                  >
                    <Link href={`/course/${encodeURIComponent(topic.course)}`} className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-[var(--ink)] truncate">{topic.name}</p>
                      <p className="text-xs text-stone-500 dark:text-stone-400 truncate">{topic.course}</p>
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
                      href={`/course/${encodeURIComponent(topic.course)}`}
                      className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-[rgba(var(--ink-rgb),0.05)] transition"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-[var(--ink)] truncate">{topic.name}</p>
                        <p className="text-xs text-stone-500 dark:text-stone-400 truncate">{topic.course}</p>
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
        </div>
      </SidebarInset>

      {showCreate && <CreateCourseModal onClose={() => setShowCreate(false)} />}
    </SidebarProvider>
  );
}
