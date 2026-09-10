"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  flagged?: string[];
}

export default function ChatView({ topicId }: { topicId: number | null }) {
  const { topics, refresh } = useAppState();
  const topic = topics.find((t) => t.id === topicId);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([]);
  }, [topicId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleAsk(e: FormEvent) {
    e.preventDefault();
    if (!topicId || !input.trim()) return;
    const question = input.trim();
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setAsking(true);
    try {
      const result = await api.ask({ query: question, topic_id: topicId });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: result.answer,
          flagged: result.flagged_prerequisites.map((t) => t.name),
        },
      ]);
      refresh();
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center gap-1.5">
            <p className="text-sm text-stone-600">Ask anything about {topic?.name ?? "this topic"}.</p>
            <p className="text-xs text-stone-500">Answers are grounded in the material you&apos;ve uploaded.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-lg rounded-2xl px-4 py-2.5 text-sm ${
                m.role === "user" ? "bg-[#FF6D1F] text-[#222222] accent-ring" : "surface text-[#222222]"
              }`}
            >
              <p className="whitespace-pre-wrap">{m.text}</p>
              {m.flagged && m.flagged.length > 0 && (
                <p className="mt-2 text-xs text-[#8a5a0a] bg-[#c9860f]/12 border border-[#c9860f]/25 rounded px-2 py-1">
                  Prerequisite gap: {m.flagged.join(", ")}
                </p>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleAsk} className="p-4 border-t border-[#222222]/10">
        <div className="flex items-center gap-2 rounded-xl linen shadow-sm px-3 py-2 focus-within:border-[#FF6D1F]/50 transition">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={!topicId || asking}
            placeholder={topicId ? "Ask a question..." : "Select a topic to start"}
            className="flex-1 bg-transparent text-sm outline-none text-[#222222] placeholder:text-stone-400 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!topicId || asking || !input.trim()}
            className="rounded-lg bg-[#FF6D1F] hover:bg-[#e6600f] transition text-[#222222] text-xs font-medium px-3.5 py-1.5 disabled:opacity-40"
          >
            {asking ? "..." : "Ask"}
          </button>
        </div>
      </form>
    </div>
  );
}
