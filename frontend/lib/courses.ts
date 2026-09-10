import { Mastery, Topic } from "./api";

export interface CourseSummary {
  name: string;
  topics: Topic[];
  avgScore: number;
}

export function summarizeCourses(
  topics: Topic[],
  masteryByTopic: Record<number, Mastery>
): CourseSummary[] {
  const byName = new Map<string, Topic[]>();
  for (const topic of topics) {
    byName.set(topic.course, [...(byName.get(topic.course) ?? []), topic]);
  }

  return Array.from(byName.entries()).map(([name, courseTopics]) => {
    const scores = courseTopics.map((t) => masteryByTopic[t.id]?.score ?? 0);
    const avgScore = scores.length
      ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
      : 0;
    return { name, topics: courseTopics, avgScore };
  });
}

// A small identity palette for course avatar badges — deliberately distinct
// from the mastery status colors so a badge is never misread as a status.
// Cycled by a stable hash of the course name so the same course always
// lands on the same color, and a library of several courses reads as
// varied rather than a wall of one accent.
const BADGE_PALETTE = [
  { bg: "rgba(255, 109, 31, 0.15)", border: "rgba(255, 109, 31, 0.35)", text: "#e6600f" },
  { bg: "rgba(60, 91, 122, 0.15)", border: "rgba(60, 91, 122, 0.35)", text: "#3c5b7a" },
  { bg: "rgba(139, 94, 60, 0.15)", border: "rgba(139, 94, 60, 0.35)", text: "#8b5e3c" },
];

export function badgeColorFor(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return BADGE_PALETTE[hash % BADGE_PALETTE.length];
}
