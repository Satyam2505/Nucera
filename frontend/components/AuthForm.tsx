"use client";

import { FormEvent, useState } from "react";

import { useAuth } from "@/lib/AuthContext";

export default function AuthForm() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex h-screen items-center justify-center hero-gradient px-4">
      <div className="w-full max-w-sm surface-strong rounded-2xl p-8">
        <h1 className="text-lg font-semibold tracking-tight text-[var(--ink)] mb-1">
          EduPilot <span className="text-[var(--accent)]">AI</span>
        </h1>
        <p className="text-sm text-stone-500 dark:text-stone-400 mb-6">
          {mode === "login" ? "Log in to your courses." : "Create an account to get started."}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-stone-600 dark:text-stone-300 mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full rounded-lg linen px-3 py-2 text-sm text-[var(--ink)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none focus:ring-2 focus:ring-[rgba(var(--accent-rgb),0.30)] focus:border-[rgba(var(--accent-rgb),0.50)] transition"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-stone-600 dark:text-stone-300 mb-1">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "register" ? "At least 8 characters" : "••••••••"}
              className="w-full rounded-lg linen px-3 py-2 text-sm text-[var(--ink)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none focus:ring-2 focus:ring-[rgba(var(--accent-rgb),0.30)] focus:border-[rgba(var(--accent-rgb),0.50)] transition"
            />
          </div>

          {error && (
            <p className="text-xs text-[var(--error-text)] bg-[var(--error-bg)] border border-[var(--error-border)] rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] transition text-[var(--accent-ink)] text-sm font-medium py-2.5 disabled:opacity-50 accent-ring"
          >
            {submitting ? (mode === "login" ? "Logging in..." : "Creating account...") : mode === "login" ? "Log in" : "Create account"}
          </button>
        </form>

        <button
          onClick={() => {
            setMode((m) => (m === "login" ? "register" : "login"));
            setError(null);
          }}
          className="w-full text-center text-xs text-stone-500 dark:text-stone-400 hover:text-[var(--ink)] transition mt-5"
        >
          {mode === "login" ? "No account yet? Create one" : "Already have an account? Log in"}
        </button>
      </div>
    </div>
  );
}
