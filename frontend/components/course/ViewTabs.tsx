"use client";

import { ReactNode } from "react";

export type ViewKey = "chat" | "quiz" | "graph" | "mastery" | "history" | "sources";

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
    label: "Knowledge graph",
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
    key: "history",
    label: "History",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" strokeLinecap="round" strokeLinejoin="round" />
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

export default function ViewTabs({ view, onChange }: { view: ViewKey; onChange: (view: ViewKey) => void }) {
  return (
    <div className="flex items-center gap-2 px-6 py-3 border-b border-[rgba(var(--ink-rgb),0.10)] overflow-x-auto">
      {VIEWS.map((v) => (
        <button
          key={v.key}
          onClick={() => onChange(v.key)}
          className={`flex items-center gap-1.5 text-xs font-medium px-3.5 py-2 rounded-lg transition shrink-0 ${
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
  );
}
