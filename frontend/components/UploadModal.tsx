"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";

const SOURCE_TYPES = ["official_upload", "self_supplied", "web_fallback"];

const inputClass =
  "linen text-[var(--ink)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus-visible:ring-[rgba(var(--accent-rgb),0.30)]";

export default function UploadModal({ onClose }: { onClose: () => void }) {
  const { topics, selectedTopicId, refresh } = useAppState();
  const [topicId, setTopicId] = useState<number | null>(selectedTopicId);
  const [sourceType, setSourceType] = useState(SOURCE_TYPES[1]);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!topicId) return;
    setSubmitting(true);
    setStatus(null);
    try {
      if (file) {
        await api.uploadFile(topicId, sourceType, file);
      } else {
        await api.ingestText({
          topic_id: topicId,
          source_type: sourceType,
          title: title || "Pasted notes",
          text,
        });
      }
      await refresh();
      setStatus("Added.");
      setTimeout(onClose, 500);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="bg-[var(--bg-surface)] text-[var(--ink)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[var(--ink)]">Add source</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-stone-600 dark:text-stone-300">Topic</Label>
            <Select value={topicId ? String(topicId) : ""} onValueChange={(v) => setTopicId(Number(v))}>
              <SelectTrigger className={`w-full ${inputClass}`}>
                <SelectValue placeholder="Select a topic" />
              </SelectTrigger>
              <SelectContent>
                {topics.map((t) => (
                  <SelectItem key={t.id} value={String(t.id)}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-stone-600 dark:text-stone-300">Source type</Label>
            <Select value={sourceType} onValueChange={setSourceType}>
              <SelectTrigger className={`w-full ${inputClass}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SOURCE_TYPES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-stone-600 dark:text-stone-300">Title</Label>
            <Input
              className={inputClass}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Lecture 3 notes"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-stone-600 dark:text-stone-300">Paste text</Label>
            <Textarea
              className={`${inputClass} h-28`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste notes here..."
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-stone-600 dark:text-stone-300">Or upload a file</Label>
            <Input
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm text-stone-600 dark:text-stone-300 file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--accent)] file:text-[var(--accent-ink)] file:px-3 file:py-1.5 file:text-xs hover:file:bg-[var(--accent-hover)] h-auto py-1.5"
            />
          </div>

          <Button
            type="submit"
            disabled={submitting || !topicId}
            className="w-full bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] h-auto py-2.5 accent-ring"
          >
            {submitting ? "Adding..." : "Add source"}
          </Button>

          {status && <p className="text-xs text-stone-600 dark:text-stone-300 text-center">{status}</p>}
        </form>
      </DialogContent>
    </Dialog>
  );
}
