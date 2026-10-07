// Pure helpers for the tutor chat: the shape of the streamed answer, turning
// saved messages into what the view shows, and tidying maths delimiters in
// model output. No DOM, no fetch — testable under plain Node.

import type { SourceCitation } from "./api";

// One line of the /ask/stream response.
export type StreamEvent =
  | { type: "token"; text: string }
  | {
      type: "done";
      answer: string;
      sources: SourceCitation[];
      grounded: boolean;
      flagged_prerequisites: { id: number; name: string }[];
    }
  | { type: "error"; message: string };

export type StreamDone = Extract<StreamEvent, { type: "done" }>;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function citations(value: unknown): SourceCitation[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) =>
    isObject(item) && typeof item.source === "string"
      ? [
          {
            source: item.source,
            page: typeof item.page === "number" ? item.page : null,
            topic: typeof item.topic === "string" && item.topic ? item.topic : null,
          },
        ]
      : []
  );
}

/** A stream line as a typed event, or null if it isn't one (skipped, not fatal). */
export function parseStreamEvent(line: string): StreamEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(line);
  } catch {
    return null;
  }
  if (!isObject(data)) return null;

  if (data.type === "token" && typeof data.text === "string") {
    return { type: "token", text: data.text };
  }
  if (data.type === "error") {
    return {
      type: "error",
      message: typeof data.message === "string" && data.message ? data.message : "The answer failed.",
    };
  }
  if (data.type === "done" && typeof data.answer === "string") {
    return {
      type: "done",
      answer: data.answer,
      sources: citations(data.sources),
      grounded: data.grounded !== false,
      flagged_prerequisites: Array.isArray(data.flagged_prerequisites)
        ? data.flagged_prerequisites.flatMap((t) =>
            isObject(t) && typeof t.name === "string" ? [{ id: Number(t.id), name: t.name }] : []
          )
        : [],
    };
  }
  return null;
}

// A saved message as GET /chat returns it.
export interface SavedChatMessage {
  id: number;
  role: string;
  content: string;
  sources: SourceCitation[];
  flagged: string[];
  grounded: boolean | null;
}

// What the chat view renders.
export interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
  flagged?: string[];
  sources?: SourceCitation[];
  grounded?: boolean;
}

export function fromSaved(saved: SavedChatMessage): ChatMessage {
  if (saved.role === "user") return { role: "user", text: saved.content };
  return {
    role: "assistant",
    text: saved.content,
    flagged: saved.flagged ?? [],
    sources: saved.sources ?? [],
    grounded: saved.grounded ?? true,
  };
}

/**
 * Models often write maths as \( ... \) and \[ ... \], which the markdown maths
 * plugin doesn't read (it wants $ ... $ and $$ ... $$). Rewrites the former to
 * the latter, leaving code (fenced or inline) exactly as written. An unclosed
 * delimiter, as on a half-streamed answer, is left alone.
 */
export function normalizeMath(text: string): string {
  const parts = text.split(/(```[\s\S]*?```|`[^`\n]*`)/g);
  return parts
    .map((part, i) => {
      if (i % 2 === 1) return part; // a code span or fence
      return part
        // Display maths must sit on lines of its own, or it is read as inline.
        .replace(/\\\[([\s\S]+?)\\\]/g, (_m, inner: string) => `\n$$\n${inner.trim()}\n$$\n`)
        .replace(/\\\(([\s\S]+?)\\\)/g, (_m, inner: string) => `$${inner}$`);
    })
    .join("");
}
