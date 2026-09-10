"use client";

import { useMemo, useRef, useState } from "react";

import AppSidebar from "@/components/AppSidebar";
import CreateCourseModal from "@/components/CreateCourseModal";
import { useAppState } from "@/lib/AppStateContext";
import { summarizeCourses } from "@/lib/courses";

export default function LandingPage() {
  const { topics, masteryByTopic, loading } = useAppState();
  const [query, setQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [highlight, setHighlight] = useState(false);
  const libraryRef = useRef<HTMLDivElement>(null);

  const courses = useMemo(() => summarizeCourses(topics, masteryByTopic), [topics, masteryByTopic]);
  const filtered = query
    ? courses.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()))
    : courses;

  // The library lives in the sidebar now, so "Browse courses" opens and
  // flashes it rather than scrolling the page.
  function browseCourses() {
    setCollapsed(false);
    setHighlight(true);
    setTimeout(() => libraryRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50);
    setTimeout(() => setHighlight(false), 1400);
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <AppSidebar
        courses={filtered}
        loading={loading}
        collapsed={collapsed}
        onToggle={() => setCollapsed((v) => !v)}
        onNewCourse={() => setShowCreate(true)}
        highlight={highlight}
        libraryRef={libraryRef}
      />

      <main className="flex-1 hero-gradient overflow-y-auto">
        <div className="min-h-full flex flex-col items-center justify-center px-6 text-center">
          <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight text-[#222222] mb-8">
            Welcome back!
          </h1>

          <div className="w-full max-w-xl">
            <div className="flex items-center gap-2 rounded-full linen shadow-sm px-5 py-3.5 sheen">
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="text-stone-400 shrink-0"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="m21 21-4.3-4.3" />
              </svg>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && browseCourses()}
                placeholder="Search your courses..."
                className="flex-1 bg-transparent outline-none text-sm placeholder:text-stone-400 text-[#222222]"
              />
            </div>
          </div>

          <button
            onClick={browseCourses}
            className="mt-6 rounded-full bg-[#FF6D1F] hover:bg-[#e6600f] transition text-sm font-medium px-5 py-2.5 text-[#222222] accent-ring"
          >
            Browse courses
          </button>
        </div>
      </main>

      {showCreate && <CreateCourseModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}
