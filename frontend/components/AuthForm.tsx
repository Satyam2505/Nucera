"use client";

import { FormEvent, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
      <Card className="w-full max-w-sm bg-[var(--bg-surface)] border-[rgba(var(--ink-rgb),0.12)] shadow-lg">
        <CardHeader>
          <div className="flex items-center justify-center gap-2 mb-1">
            <img src="/nucera-mark.svg" alt="" className="h-8 w-8" />
            <h1 className="text-lg font-semibold tracking-tight text-[var(--ink)]">nucera</h1>
          </div>
          <p className="text-sm text-stone-500 dark:text-stone-400">
            {mode === "login" ? "Log in to your courses." : "Create an account to get started."}
          </p>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-xs font-medium text-stone-600 dark:text-stone-300">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="linen text-[var(--ink)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus-visible:ring-[rgba(var(--accent-rgb),0.30)]"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-xs font-medium text-stone-600 dark:text-stone-300">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === "register" ? "At least 8 characters" : "••••••••"}
                className="linen text-[var(--ink)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus-visible:ring-[rgba(var(--accent-rgb),0.30)]"
              />
            </div>

            {error && (
              <Alert variant="destructive" className="bg-[var(--error-bg)] border-[var(--error-border)]">
                <AlertDescription className="text-[var(--error-text)]">{error}</AlertDescription>
              </Alert>
            )}

            <Button
              type="submit"
              disabled={submitting}
              className="w-full bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] h-auto py-2.5 accent-ring"
            >
              {submitting
                ? mode === "login"
                  ? "Logging in..."
                  : "Creating account..."
                : mode === "login"
                  ? "Log in"
                  : "Create account"}
            </Button>
          </form>

          <Button
            variant="link"
            onClick={() => {
              setMode((m) => (m === "login" ? "register" : "login"));
              setError(null);
            }}
            className="w-full text-center text-xs text-stone-500 dark:text-stone-400 hover:text-[var(--ink)] mt-5 h-auto no-underline hover:no-underline"
          >
            {mode === "login" ? "No account yet? Create one" : "Already have an account? Log in"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
