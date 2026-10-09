"use client";

import { FormEvent, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";
import { groupTopicsByModule } from "@/lib/courses";

const SOURCE_TYPES = ["official_upload", "self_supplied", "web_fallback"];

const inputClass =
  "linen text-[var(--ink)] placeholder:text-fg-placeholder focus-visible:ring-[rgba(var(--accent-rgb),0.30)]";

export default function UploadModal({
  onClose,
  initialTopicId,
}: {
  onClose: () => void;
  // The topic to preselect (the course page passes the one it is showing);
  // falls back to the app-wide selection.
  initialTopicId?: number | null;
}) {
  const { topics, selectedTopicId, refresh } = useAppState();
  const [topicId, setTopicId] = useState<number | null>(initialTopicId ?? selectedTopicId);
  const groups = useMemo(() => groupTopicsByModule(topics), [topics]);
  // Course names only earn their place in the headings when topics from
  // several courses can appear in the picker.
  const multipleCourses = new Set(groups.map((g) => g.courseId)).size > 1;
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
            <Label className="text-xs font-medium text-fg-secondary">Topic</Label>
            <Select
              value={topicId ? String(topicId) : ""}
              onValueChange={(v) => setTopicId(Number(v))}
              disabled={topics.length === 0}
            >
              <SelectTrigger className={`w-full ${inputClass}`}>
                <SelectValue placeholder={topics.length === 0 ? "No topics yet" : "Select a topic"} />
              </SelectTrigger>
              <SelectContent>
                {groups.map((group) => (
                  <SelectGroup key={group.moduleId}>
                    <SelectLabel>
                      {multipleCourses ? `${group.courseName} · ${group.moduleName}` : group.moduleName}
                    </SelectLabel>
                    {group.topics.map((t) => (
                      <SelectItem key={t.id} value={String(t.id)}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
            {topics.length === 0 && (
              <p className="text-xs text-fg-tertiary">
                Add a module and a topic inside a course first, then attach sources to it.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-fg-secondary">Source type</Label>
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
            <Label className="text-xs font-medium text-fg-secondary">Title</Label>
            <Input
              className={inputClass}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Lecture 3 notes"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-fg-secondary">Paste text</Label>
            <Textarea
              className={`${inputClass} h-28`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste notes here..."
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-fg-secondary">Or upload a file</Label>
            <Input
              type="file"
              // What the server accepts; it still checks, this just keeps the picker honest.
              accept=".pdf,.docx,.pptx,.txt,.md"
              aria-describedby="upload-file-hint"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm text-fg-secondary file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--accent)] file:text-[var(--accent-ink)] file:px-3 file:py-1.5 file:text-xs hover:file:bg-[var(--accent-hover)] h-auto py-1.5"
            />
            <p id="upload-file-hint" className="text-[11px] text-fg-tertiary">
              PDF, Word (.docx), PowerPoint (.pptx), .txt or .md files. Scanned PDFs are read with OCR when it is installed.
            </p>
          </div>

          <Button
            type="submit"
            disabled={submitting || !topicId}
            className="w-full bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] h-auto py-2.5 accent-ring"
          >
            {submitting ? "Adding..." : "Add source"}
          </Button>

          {status && <p className="text-xs text-fg-secondary text-center">{status}</p>}
        </form>
      </DialogContent>
    </Dialog>
  );
}
