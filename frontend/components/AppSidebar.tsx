"use client";

import Link from "next/link";
import { RefObject } from "react";

import { badgeColorFor, CourseSummary } from "@/lib/courses";

import AccountMenu from "./AccountMenu";

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
      <aside className="w-16 shrink-0 surface-deep border-r border-[#222222]/10 flex flex-col h-full">
        <div className="flex-1 flex flex-col items-center py-4 gap-3 overflow-y-auto">
          <button
            onClick={onToggle}
            className="p-2 rounded-lg text-stone-600 hover:text-[#222222] hover:bg-[#222222]/8 transition"
            aria-label="Expand sidebar"
          >
            <PanelIcon />
          </button>
          <button
            onClick={onNewCourse}
            className="p-2 rounded-lg text-stone-600 hover:text-[#e6600f] hover:bg-[#FF6D1F]/12 transition"
            aria-label="New course"
          >
            <PlusIcon />
          </button>
          <div className="w-8 h-px bg-[#222222]/12 my-1" />
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
        <AccountMenu collapsed />
      </aside>
    );
  }

  return (
    <aside className="w-80 shrink-0 surface-deep border-r border-[#222222]/10 flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-4">
        <span className="text-base font-semibold tracking-tight text-[#222222]">
          EduPilot <span className="text-[#FF6D1F]">AI</span>
        </span>
        <button
          onClick={onToggle}
          className="p-1.5 rounded-lg text-stone-500 hover:text-[#222222] hover:bg-[#222222]/8 transition"
          aria-label="Collapse sidebar"
        >
          <PanelIcon />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div
          ref={libraryRef}
          className={`mt-2 mx-2 rounded-xl transition-shadow ${
            highlight ? "ring-2 ring-[#FF6D1F] ring-offset-2 ring-offset-[#DBCBAF]" : ""
          }`}
        >
          <p className="px-3 pt-2 pb-1 text-[11px] font-medium uppercase tracking-wide text-stone-500">
            Library
          </p>

          <button
            onClick={onNewCourse}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium text-[#222222] hover:bg-[#222222]/8 transition"
          >
            <PlusIcon />
            New course
          </button>

          <div className="pt-1 pb-2 space-y-0.5">
            {loading && <p className="px-3 py-2 text-xs text-stone-500">Loading...</p>}
            {!loading && courses.length === 0 && (
              <p className="px-3 py-2 text-xs text-stone-500">No courses yet.</p>
            )}
            {courses.map((course) => {
              const badge = badgeColorFor(course.name);
              return (
                <Link
                  key={course.name}
                  href={`/course/${encodeURIComponent(course.name)}`}
                  className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-stone-700 hover:bg-[#222222]/8 transition group"
                >
                  <span
                    className="h-6 w-6 rounded-md border flex items-center justify-center text-[10px] font-semibold shrink-0"
                    style={{ background: badge.bg, borderColor: badge.border, color: badge.text }}
                  >
                    {course.name.charAt(0).toUpperCase()}
                  </span>
                  <span className="truncate group-hover:text-[#222222]">{course.name}</span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>

      <AccountMenu collapsed={false} />
    </aside>
  );
}
