"use client";

import { FormEvent, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const inputClass =
  "linen text-[var(--ink)] placeholder:text-fg-placeholder focus-visible:ring-[rgba(var(--accent-rgb),0.30)]";

interface Props {
  title: string;
  nameLabel: string;
  namePlaceholder?: string;
  submitLabel: string;
  initialName?: string;
  initialDescription?: string | null;
  // When set, the dialog also asks for an optional description.
  withDescription?: boolean;
  onSubmit: (name: string, description: string) => Promise<void>;
  onClose: () => void;
}

// One small form for every "give this a name" action (add or rename a
// course, module or topic). Enter submits, Esc closes, a blank name can't be
// submitted, and the form locks while the request is in flight.
export default function NameDialog({
  title,
  nameLabel,
  namePlaceholder,
  submitLabel,
  initialName = "",
  initialDescription,
  withDescription = false,
  onSubmit,
  onClose,
}: Props) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(name.trim(), description.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setSubmitting(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !submitting && onClose()}>
      <DialogContent className="bg-[var(--bg-surface)] text-[var(--ink)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[var(--ink)]">{title}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="name-dialog-name" className="text-xs font-medium text-fg-secondary">
              {nameLabel}
            </Label>
            <Input
              id="name-dialog-name"
              autoFocus
              className={inputClass}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={namePlaceholder}
              maxLength={255}
            />
          </div>
          {withDescription && (
            <div className="space-y-1.5">
              <Label
                htmlFor="name-dialog-description"
                className="text-xs font-medium text-fg-secondary"
              >
                Description (optional)
              </Label>
              <Textarea
                id="name-dialog-description"
                className={`${inputClass} h-20`}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          )}
          <Button
            type="submit"
            disabled={submitting || !name.trim()}
            className="w-full bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] h-auto py-2.5 accent-ring"
          >
            {submitting ? "Saving..." : submitLabel}
          </Button>
          {error && (
            <Alert variant="destructive" className="bg-[var(--error-bg)] border-[var(--error-border)]">
              <AlertDescription className="text-[var(--error-text)] text-center w-full">{error}</AlertDescription>
            </Alert>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}
