"use client";

import { useEffect, useState } from "react";

// STUB — no real authentication is wired up yet. This just simulates the
// logged-in/logged-out UI states locally so the account menu has somewhere
// to live once real auth (and a real user) is added later.
const STUB_USER = { name: "Guest User", email: "guest@edupilot.ai" };

function ChevronIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const [loggedIn, setLoggedIn] = useState(false);
  const [open, setOpen] = useState(false);

  const initial = loggedIn ? STUB_USER.name.charAt(0).toUpperCase() : "?";

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="relative border-t border-[#222222]/10 p-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-[#222222]/8 transition ${
          collapsed ? "justify-center" : "text-left"
        }`}
      >
        <span className="h-8 w-8 rounded-full bg-[#FF6D1F]/20 border border-[#FF6D1F]/40 flex items-center justify-center text-xs font-semibold text-[#e6600f] shrink-0">
          {initial}
        </span>
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium text-[#222222] truncate">
                {loggedIn ? STUB_USER.name : "Guest"}
              </span>
              <span className="block text-[11px] text-stone-500 truncate">
                {loggedIn ? STUB_USER.email : "Not signed in"}
              </span>
            </span>
            <span className="text-stone-500 shrink-0">
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
            {loggedIn ? (
              <>
                <div className="px-3 py-2 border-b border-[#222222]/10">
                  <p className="text-sm font-medium text-[#222222] truncate">{STUB_USER.name}</p>
                  <p className="text-xs text-stone-500 truncate">{STUB_USER.email}</p>
                </div>
                <button
                  onClick={() => {
                    setLoggedIn(false);
                    setOpen(false);
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-[#222222] hover:bg-[#222222]/6 transition"
                >
                  Log out
                </button>
              </>
            ) : (
              <button
                onClick={() => {
                  setLoggedIn(true);
                  setOpen(false);
                }}
                className="w-full text-left px-3 py-2 text-sm text-[#222222] hover:bg-[#222222]/6 transition"
              >
                Log in
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
