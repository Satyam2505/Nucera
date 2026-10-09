"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import ConfirmDeleteDialog from "@/components/course/ConfirmDeleteDialog";
import Markdown from "@/components/course/Markdown";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";
import { ChatMessage, fromSaved } from "@/lib/chat";

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

export default function ChatView({ topicId }: { topicId: number | null }) {
  const { topics, refresh } = useAppState();
  const topic = topics.find((t) => t.id === topicId);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  // The answer being written. null = not answering; "" = waiting for the first words.
  const [streaming, setStreaming] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // A topic's saved conversation is loaded when it is opened. Switching away
  // stops any answer still being written: the server saves a turn only once its
  // answer is complete, so there is nothing half-saved to come back to.
  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setStreaming(null);
    setAsking(false);
    setInput("");
    if (topicId === null) return;

    let cancelled = false;
    setLoadingHistory(true);
    api
      .getChat(topicId)
      .then((saved) => {
        if (!cancelled) setMessages(saved.map(fromSaved));
      })
      .catch((err) => {
        if (!cancelled) {
          setMessages([
            {
              role: "error",
              text: err instanceof Error ? err.message : "Couldn't load this conversation.",
            },
          ]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [topicId]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    // "auto" while words are arriving: a smooth scroll can't keep up with them.
    bottomRef.current?.scrollIntoView({ behavior: streaming === null ? "smooth" : "auto" });
  }, [messages, streaming]);

  async function handleAsk(e: FormEvent) {
    e.preventDefault();
    if (!topicId || asking || !input.trim()) return;
    const question = input.trim();

    const controller = new AbortController();
    abortRef.current = controller;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setAsking(true);
    setStreaming("");
    try {
      const done = await api.askStream(
        { query: question, topic_id: topicId },
        { onToken: (text) => setStreaming((prev) => (prev ?? "") + text), signal: controller.signal }
      );
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: done.answer,
          flagged: done.flagged_prerequisites.map((t) => t.name),
          sources: done.sources,
          grounded: done.grounded,
        },
      ]);
      refresh();
    } catch (err) {
      if (isAbort(err)) {
        // Stopped by the user (or by leaving the topic): the question was never
        // saved, so take it back out and hand the text back to edit.
        if (abortRef.current === controller) {
          setMessages((prev) => prev.slice(0, -1));
          setInput(question);
        }
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: "error",
            text: err instanceof Error ? err.message : "Something went wrong asking the tutor.",
          },
        ]);
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setAsking(false);
        setStreaming(null);
      }
    }
  }

  async function clearConversation() {
    if (topicId === null) return;
    await api.clearChat(topicId);
    setMessages([]);
  }

  const canClear = !asking && !loadingHistory && messages.some((m) => m.role !== "error");

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-4">
        {canClear && (
          <div className="flex justify-end -mt-2">
            <button
              type="button"
              onClick={() => setConfirmClear(true)}
              className="text-xs text-fg-secondary hover:text-[var(--ink)] underline-offset-2 hover:underline"
            >
              Clear conversation
            </button>
          </div>
        )}
        {messages.length === 0 && !asking && !loadingHistory && (
          <div className="h-full flex flex-col items-center justify-center text-center gap-1.5">
            <p className="text-sm text-stone-600 dark:text-stone-400">Ask anything about {topic?.name ?? "this topic"}.</p>
            <p className="text-xs text-fg-secondary">Answers are grounded in the material you&apos;ve uploaded.</p>
          </div>
        )}
        {loadingHistory && (
          <p className="text-xs text-fg-secondary text-center">Loading conversation...</p>
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
                className={`max-w-2xl rounded-2xl px-4 py-2.5 text-sm ${
                  m.role === "user" ? "bg-[var(--accent)] text-[var(--accent-ink)] accent-ring" : "surface text-[var(--ink)]"
                }`}
              >
                {m.role === "user" ? <p className="whitespace-pre-wrap">{m.text}</p> : <Markdown>{m.text}</Markdown>}

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
                        {s.topic ? ` · from ${s.topic}` : ""}
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
        {streaming !== null && (
          <div className="flex justify-start" aria-live="polite">
            <div className="max-w-2xl rounded-2xl px-4 py-2.5 text-sm surface text-[var(--ink)]">
              {streaming === "" ? (
                <span className="text-fg-secondary">
                  Thinking... this can take a minute on a CPU.
                </span>
              ) : (
                <Markdown>{streaming}</Markdown>
              )}
            </div>
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
            maxLength={4000}
            placeholder={topicId ? "Ask a question..." : "Select a topic to start"}
            className="flex-1 border-0 shadow-none bg-transparent h-auto p-0 focus-visible:ring-0 text-sm text-[var(--ink)] placeholder:text-fg-placeholder disabled:opacity-50"
          />
          {asking ? (
            // Distinct keys: otherwise React reuses this very element for the
            // Ask button once the answer stops, and the click that pressed Stop
            // then lands on a submit button and asks the question again.
            <Button
              key="stop"
              type="button"
              variant="outline"
              onClick={(e) => {
                e.preventDefault();
                abortRef.current?.abort();
              }}
              className="text-xs font-medium h-auto px-3.5 py-1.5"
            >
              Stop
            </Button>
          ) : (
            <Button
              key="ask"
              type="submit"
              disabled={!topicId || !input.trim()}
              className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-ink)] text-xs font-medium h-auto px-3.5 py-1.5"
            >
              Ask
            </Button>
          )}
        </div>
      </form>

      {confirmClear && (
        <ConfirmDeleteDialog
          title="Clear this conversation?"
          description="This deletes the saved questions and answers for this topic. Your material, quizzes and mastery are not affected."
          onConfirm={clearConversation}
          onClose={() => setConfirmClear(false)}
        />
      )}
    </div>
  );
}
