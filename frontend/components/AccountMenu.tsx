"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/lib/AuthContext";

function ChevronIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function AccountMenu({ collapsed }: { collapsed: boolean }) {
  // AccountMenu only ever renders inside AuthGate's authenticated branch,
  // so `user` is guaranteed non-null here.
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);

  const initial = user?.email.charAt(0).toUpperCase() ?? "?";

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="relative border-t border-[rgba(var(--ink-rgb),0.10)] p-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-[rgba(var(--ink-rgb),0.08)] transition ${
          collapsed ? "justify-center" : "text-left"
        }`}
      >
        <span className="h-8 w-8 rounded-full bg-[rgba(var(--accent-rgb),0.2)] border border-[rgba(var(--accent-rgb),0.4)] flex items-center justify-center text-xs font-semibold text-[var(--accent-hover)] shrink-0">
          {initial}
        </span>
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium text-[var(--ink)] truncate">{user?.email}</span>
              <span className="block text-[11px] text-stone-500 dark:text-stone-400 truncate">Signed in</span>
            </span>
            <span className="text-stone-500 dark:text-stone-400 shrink-0">
              <ChevronIcon />
            </span>
          </>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div
            className={`absolute z-40 bottom-full mb-2 surface-strong rounded-xl overflow-hidden py-1 ${
              collapsed ? "left-2 w-48" : "left-2 right-2"
            }`}
          >
            <div className="px-3 py-2 border-b border-[rgba(var(--ink-rgb),0.10)]">
              <p className="text-sm font-medium text-[var(--ink)] truncate">{user?.email}</p>
            </div>
            <button
              onClick={() => {
                logout();
                setOpen(false);
              }}
              className="w-full text-left px-3 py-2 text-sm text-[var(--ink)] hover:bg-[rgba(var(--ink-rgb),0.06)] transition"
            >
              Log out
            </button>
          </div>
        </>
      )}
    </div>
  );
}
