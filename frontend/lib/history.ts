// Pure helpers for the study-session history screen. No React, no fetch, no
// runtime imports: testable under plain Node (see history.test.ts).

import type { SessionHistoryItem } from "./api";

export const SESSION_LABEL: Record<SessionHistoryItem["type"], string> = {
  chat: "Asked the tutor",
  quiz: "Took a quiz",
  self_report: "Self-reported progress",
};

/** The mastery change a session caused, as text, or null when it changed nothing. */
export function masteryChange(item: Pick<SessionHistoryItem, "score_delta">): string | null {
  if (item.score_delta === 0) return null;
  return item.score_delta > 0 ? `+${item.score_delta} mastery` : `${item.score_delta} mastery`;
}

// The server stores timestamps as UTC without a zone marker ("2026-10-08T09:30:00").
// Read as-is, a browser would treat that as local time, so mark it as UTC first.
export function parseTimestamp(value: string | null): Date | null {
  if (!value) return null;
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** "Today", "Yesterday", or a date such as "Mon 5 Oct 2026" (local time). */
export function dayLabel(date: Date, now: Date): string {
  const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

export interface DayGroup {
  label: string;
  items: SessionHistoryItem[];
}

/** Sessions (newest first, as the server sends them) grouped under their day, order kept. */
export function groupByDay(items: SessionHistoryItem[], now: Date): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const item of items) {
    const when = parseTimestamp(item.timestamp);
    const label = when ? dayLabel(when, now) : "Earlier";
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(item);
    else groups.push({ label, items: [item] });
  }
  return groups;
}

/** The time of day, e.g. "09:30" (local time). */
export function timeLabel(item: Pick<SessionHistoryItem, "timestamp">): string {
  const when = parseTimestamp(item.timestamp);
  return when ? when.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "";
}

/** The `before_id` for the next page: the oldest id received, or null when the page was short. */
export function nextCursor(items: SessionHistoryItem[], pageSize: number): number | null {
  if (items.length < pageSize || items.length === 0) return null;
  return items[items.length - 1].id;
}
