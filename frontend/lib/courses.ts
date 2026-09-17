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
// Light pastel chip + dark saturated text (self-contained contrast) rather
// than a dark translucent tint — these badges sit on the dark navy
// sidebar, where a dark-on-dark chip would just wash out.
const BADGE_PALETTE = [
  { bg: "rgba(203, 208, 224, 0.9)", border: "rgba(203, 208, 224, 1)", text: "#2d3348" },
  { bg: "rgba(147, 181, 219, 0.9)", border: "rgba(147, 181, 219, 1)", text: "#1e3a5f" },
  { bg: "rgba(214, 178, 145, 0.9)", border: "rgba(214, 178, 145, 1)", text: "#5c3d1f" },
];

export function badgeColorFor(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return BADGE_PALETTE[hash % BADGE_PALETTE.length];
}
