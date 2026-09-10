"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { api } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";

import Modal from "./Modal";

const inputClass =
  "w-full rounded-lg linen px-3 py-2 text-sm text-[#222222] placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-[#FF6D1F]/30 focus:border-[#FF6D1F]/50 transition";

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
    <Modal title="List a new course" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Course name</label>
          <input
            className={inputClass}
            value={courseName}
            onChange={(e) => setCourseName(e.target.value)}
            placeholder="e.g. Operating Systems"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">First topic name</label>
          <input
            className={inputClass}
            value={topicName}
            onChange={(e) => setTopicName(e.target.value)}
            placeholder="e.g. Processes and Threads"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Description (optional)</label>
          <textarea
            className={`${inputClass} h-20`}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={submitting || !courseName.trim() || !topicName.trim()}
          className="w-full rounded-lg bg-[#FF6D1F] hover:bg-[#e6600f] transition text-[#222222] text-sm font-medium py-2.5 disabled:opacity-50 accent-ring"
        >
          {submitting ? "Creating..." : "Create course"}
        </button>
        {error && <p className="text-xs text-[#b23a2f] text-center">{error}</p>}
        <p className="text-[11px] text-stone-500 text-center">
          You can add more topics and prerequisites to it from inside the course.
        </p>
      </form>
    </Modal>
  );
}
