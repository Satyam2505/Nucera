"use client";

import { FormEvent, useState } from "react";

import { api } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";

import Modal from "./Modal";

const SOURCE_TYPES = ["official_upload", "self_supplied", "web_fallback"];

const inputClass =
  "w-full rounded-lg linen px-3 py-2 text-sm text-[#222222] placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-[#FF6D1F]/30 focus:border-[#FF6D1F]/50 transition";

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
    <Modal title="Add source" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Topic</label>
          <select
            className={inputClass}
            value={topicId ?? ""}
            onChange={(e) => setTopicId(Number(e.target.value))}
          >
            {topics.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Source type</label>
          <select className={inputClass} value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
            {SOURCE_TYPES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Title</label>
          <input
            className={inputClass}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Lecture 3 notes"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Paste text</label>
          <textarea
            className={`${inputClass} h-28`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste notes here..."
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Or upload a file</label>
          <input
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm text-stone-600 file:mr-3 file:rounded-lg file:border-0 file:bg-[#FF6D1F] file:text-[#222222] file:px-3 file:py-1.5 file:text-xs hover:file:bg-[#e6600f]"
          />
        </div>

        <button
          type="submit"
          disabled={submitting || !topicId}
          className="w-full rounded-lg bg-[#FF6D1F] hover:bg-[#e6600f] transition text-[#222222] text-sm font-medium py-2.5 disabled:opacity-50 accent-ring"
        >
          {submitting ? "Adding..." : "Add source"}
        </button>

        {status && <p className="text-xs text-stone-600 text-center">{status}</p>}
      </form>
    </Modal>
  );
}
