"use client";

import Link from "next/link";
import { RefObject } from "react";

import { badgeColorFor, CourseSummary } from "@/lib/courses";

import AccountMenu from "./AccountMenu";
import ThemeToggle from "./ThemeToggle";

function PanelIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M10 4v16" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  );
}

export default function AppSidebar({
  courses,
  loading,
  collapsed,
  onToggle,
  onNewCourse,
  highlight,
  libraryRef,
}: {
  courses: CourseSummary[];
  loading: boolean;
  collapsed: boolean;
  onToggle: () => void;
  onNewCourse: () => void;
  highlight: boolean;
  libraryRef: RefObject<HTMLDivElement | null>;
}) {
  if (collapsed) {
    return (
      <aside className="w-16 shrink-0 surface-deep border-r border-[rgba(var(--ink-rgb),0.10)] flex flex-col h-full">
        <div className="flex-1 flex flex-col items-center py-4 gap-3 overflow-y-auto">
          <button
            onClick={onToggle}
            className="p-2 rounded-lg text-stone-600 dark:text-stone-400 hover:text-[var(--ink)] hover:bg-[rgba(var(--ink-rgb),0.08)] transition"
            aria-label="Expand sidebar"
          >
            <PanelIcon />
          </button>
          <button
            onClick={onNewCourse}
            className="p-2 rounded-lg text-stone-600 dark:text-stone-400 hover:text-[var(--accent-hover)] hover:bg-[rgba(var(--accent-rgb),0.12)] transition"
            aria-label="New course"
          >
            <PlusIcon />
          </button>
          <div className="w-8 h-px bg-[rgba(var(--ink-rgb),0.12)] my-1" />
          {courses.map((course) => {
            const badge = badgeColorFor(course.name);
            return (
              <Link
                key={course.name}
                href={`/course/${encodeURIComponent(course.name)}`}
                title={course.name}
                className="h-8 w-8 rounded-lg border flex items-center justify-center text-xs font-semibold"
                style={{ background: badge.bg, borderColor: badge.border, color: badge.text }}
              >
                {course.name.charAt(0).toUpperCase()}
              </Link>
            );
          })}
        </div>
        <div className="flex justify-center pb-2">
          <ThemeToggle />
        </div>
        <AccountMenu collapsed />
      </aside>
    );
  }

  return (
    <>
      {/* Below md, the expanded sidebar floats above the page instead of
          squeezing it — a fixed 320px column has no business fighting a
          narrow viewport for space. The backdrop closes it on outside tap;
          it's a no-op at md+ where the sidebar is back in normal flow. */}
      <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={onToggle} />
      <aside className="w-80 max-w-[85vw] shrink-0 surface-deep border-r border-[rgba(var(--ink-rgb),0.10)] flex flex-col h-full fixed inset-y-0 left-0 z-40 md:relative md:inset-auto md:z-auto">
      <div className="flex items-center justify-between px-4 py-4">
        <span className="text-base font-semibold tracking-tight text-[var(--ink)]">
          EduPilot <span className="text-[var(--accent)]">AI</span>
        </span>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <button
            onClick={onToggle}
            className="p-1.5 rounded-lg text-stone-500 dark:text-stone-400 hover:text-[var(--ink)] hover:bg-[rgba(var(--ink-rgb),0.08)] transition"
            aria-label="Collapse sidebar"
          >
            <PanelIcon />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div
          ref={libraryRef}
          className={`mt-2 mx-2 rounded-xl transition-shadow ${
            highlight ? "ring-2 ring-[var(--accent)] ring-offset-2 ring-offset-[var(--bg-sidebar)]" : ""
          }`}
        >
          <p className="px-3 pt-2 pb-1 text-[11px] font-medium uppercase tracking-wide text-stone-500 dark:text-stone-400">
            Library
          </p>

          <button
            onClick={onNewCourse}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium text-[var(--ink)] hover:bg-[rgba(var(--ink-rgb),0.08)] transition"
          >
            <PlusIcon />
            New course
          </button>

          <div className="pt-1 pb-2 space-y-0.5">
            {loading && <p className="px-3 py-2 text-xs text-stone-500 dark:text-stone-400">Loading...</p>}
            {!loading && courses.length === 0 && (
              <p className="px-3 py-2 text-xs text-stone-500 dark:text-stone-400">No courses yet.</p>
            )}
            {courses.map((course) => {
              const badge = badgeColorFor(course.name);
              return (
                <Link
                  key={course.name}
                  href={`/course/${encodeURIComponent(course.name)}`}
                  className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-stone-700 dark:text-stone-300 hover:bg-[rgba(var(--ink-rgb),0.08)] transition group"
                >
                  <span
                    className="h-6 w-6 rounded-md border flex items-center justify-center text-[10px] font-semibold shrink-0"
                    style={{ background: badge.bg, borderColor: badge.border, color: badge.text }}
                  >
                    {course.name.charAt(0).toUpperCase()}
                  </span>
                  <span className="truncate group-hover:text-[var(--ink)]">{course.name}</span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>

      <AccountMenu collapsed={false} />
      </aside>
    </>
  );
}
