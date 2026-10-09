"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface Props {
  // "load": the first load failed, so nothing was ever loaded.
  // "refresh": a later refresh failed; what loaded earlier is still on screen.
  variant: "load" | "refresh";
  reason: string;
  onRetry: () => void;
  retrying?: boolean;
  className?: string;
}

// The one way the app says "couldn't load your library", so the dashboard and the
// course page word it the same way and both offer the same retry.
export default function LoadErrorNotice({ variant, reason, onRetry, retrying = false, className = "" }: Props) {
  const title = variant === "load" ? "Couldn't load your courses" : "Couldn't refresh your courses";
  const detail = variant === "load" ? reason : `Showing what loaded earlier. ${reason}`;

  return (
    <Alert
      variant="destructive"
      className={`bg-[var(--error-bg)] border-[var(--error-border)] ${className}`}
    >
      <AlertTitle className="text-[var(--error-text)]">{title}</AlertTitle>
      <AlertDescription className="text-[var(--error-text)]">
        <span className="block">{detail}</span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onRetry}
          disabled={retrying}
          className="mt-3 w-fit"
        >
          {retrying ? "Trying again..." : "Try again"}
        </Button>
      </AlertDescription>
    </Alert>
  );
}
