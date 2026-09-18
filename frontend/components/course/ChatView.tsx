"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ChatTurn, SourceCitation } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";

interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
  flagged?: string[];
  sources?: SourceCitation[];
  grounded?: boolean;
}

const HISTORY_TURNS = 6;

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

    // Short, client-held history for follow-up context — not persisted
    // server-side, just the last few turns already visible on screen.
    const history: ChatTurn[] = messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .slice(-HISTORY_TURNS)
      .map((m) => ({ role: m.role as "user" | "assistant", text: m.text }));

    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setAsking(true);
    try {
      const result = await api.ask({ query: question, topic_id: topicId, history });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: result.answer,
          flagged: result.flagged_prerequisites.map((t) => t.name),
          sources: result.sources,
          grounded: result.grounded,
        },
      ]);
      refresh();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "error",
          text: err instanceof Error ? err.message : "Something went wrong asking the tutor.",
        },
      ]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center gap-1.5">
            <p className="text-sm text-stone-600 dark:text-stone-400">Ask anything about {topic?.name ?? "this topic"}.</p>
            <p className="text-xs text-stone-500 dark:text-stone-500">Answers are grounded in the material you&apos;ve uploaded.</p>
          </div>
        )}
        {messages.map((m, i) => {
          if (m.role === "error") {
            return (
              <div key={i} className="flex justify-start">
                <Alert
                  variant="destructive"
                  className="max-w-lg w-auto rounded-2xl bg-[var(--error-bg)] border-[var(--error-border)]"
                >
                  <AlertDescription className="text-[var(--error-text)] text-sm">{m.text}</AlertDescription>
                </Alert>
              </div>
            );
          }

          return (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-lg rounded-2xl px-4 py-2.5 text-sm ${
                  m.role === "user" ? "bg-[var(--accent)] text-[var(--accent-ink)] accent-ring" : "surface text-[var(--ink)]"
                }`}
              >
                <p className="whitespace-pre-wrap">{m.text}</p>

                {m.role === "assistant" && m.grounded === false && (
                  <p className="mt-2 text-xs text-[var(--warn-text)] bg-[var(--warn-bg)] border border-[var(--warn-border)] rounded px-2 py-1">
                    This answer isn&apos;t grounded in your uploaded material.
                  </p>
                )}

                {m.sources && m.sources.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.sources.map((s, si) => (
                      <Badge
                        key={si}
                        variant="secondary"
                        className="text-[11px] font-normal text-stone-600 dark:text-stone-400"
                      >
                        {s.source}
                        {s.page != null ? `, p. ${s.page}` : ""}
                      </Badge>
                    ))}
                  </div>
                )}

                {m.flagged && m.flagged.length > 0 && (
                  <p className="mt-2 text-xs text-[var(--warn-text)] bg-[var(--warn-bg)] border border-[var(--warn-border)] rounded px-2 py-1">
                    Prerequisite gap: {m.flagged.join(", ")}
                  </p>
                )}
              </div>
            </div>
          );
        })}
        {asking && (
          <div className="flex justify-start">
            <div className="max-w-lg rounded-2xl px-4 py-2.5 text-sm surface text-stone-500 dark:text-stone-400">Thinking...</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleAsk} className="p-4 border-t border-[rgba(var(--ink-rgb),0.10)]">
        <div className="flex items-center gap-2 rounded-xl linen shadow-sm px-3 py-2 focus-within:border-[rgba(var(--accent-rgb),0.50)] transition">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={!topicId || asking}
            placeholder={topicId ? "Ask a question..." : "Select a topic to start"}
            className="flex-1 border-0 shadow-none bg-transparent h-auto p-0 focus-visible:ring-0 text-sm text-[var(--ink)] placeholder:text-stone-400 dark:placeholder:text-stone-500 disabled:opacity-50"
          />
          <Button
            type="submit"
            disabled={!topicId || asking || !input.trim()}
            className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] text-xs font-medium h-auto px-3.5 py-1.5"
          >
            {asking ? "..." : "Ask"}
          </Button>
        </div>
      </form>
    </div>
  );
}
