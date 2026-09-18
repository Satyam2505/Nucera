"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";

const inputClass =
  "linen text-[var(--ink)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus-visible:ring-[rgba(var(--accent-rgb),0.30)]";

export default function CreateCourseModal({ onClose }: { onClose: () => void }) {
  const { refresh } = useAppState();
  const router = useRouter();
  const [courseName, setCourseName] = useState("");
  const [topicName, setTopicName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!courseName.trim() || !topicName.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createTopic({
        name: topicName.trim(),
        course: courseName.trim(),
        description: description.trim() || undefined,
      });
      await refresh();
      onClose();
      router.push(`/course/${encodeURIComponent(courseName.trim())}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create course");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="bg-[var(--bg-surface)] text-[var(--ink)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[var(--ink)]">List a new course</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-stone-600 dark:text-stone-300">Course name</Label>
            <Input
              className={inputClass}
              value={courseName}
              onChange={(e) => setCourseName(e.target.value)}
              placeholder="e.g. Operating Systems"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-stone-600 dark:text-stone-300">First topic name</Label>
            <Input
              className={inputClass}
              value={topicName}
              onChange={(e) => setTopicName(e.target.value)}
              placeholder="e.g. Processes and Threads"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-stone-600 dark:text-stone-300">Description (optional)</Label>
            <Textarea
              className={`${inputClass} h-20`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <Button
            type="submit"
            disabled={submitting || !courseName.trim() || !topicName.trim()}
            className="w-full bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] h-auto py-2.5 accent-ring"
          >
            {submitting ? "Creating..." : "Create course"}
          </Button>
          {error && (
            <Alert variant="destructive" className="bg-[var(--error-bg)] border-[var(--error-border)]">
              <AlertDescription className="text-[var(--error-text)] text-center w-full">{error}</AlertDescription>
            </Alert>
          )}
          <p className="text-[11px] text-stone-500 dark:text-stone-400 text-center">
            You can add more topics and prerequisites to it from inside the course.
          </p>
        </form>
      </DialogContent>
    </Dialog>
  );
}
