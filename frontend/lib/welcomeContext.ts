// Chooses the landing page's secondary message + optional CTA + optional
// context line from data the app already has loaded (topics, mastery,
// prerequisite graph) — no new fetches, no invented data. Kept separate
// from app/page.tsx so the priority logic is testable on its own.

import type { GraphData, Mastery, Topic } from "./api";
import type { CourseSummary } from "./courses";
import { getUnmasteredPrereqs } from "./graph-utils";
import type { TimePeriod } from "./greeting";

export interface WelcomeContext {
  message: string;
  cta?: { label: string; href: string };
  contextLine?: string;
}

const TIME_FALLBACK: Record<TimePeriod, string> = {
  morning: "Start with one concept and build from there.",
  afternoon: "Pick up where you left off.",
  evening: "A good time for a quick study session.",
  night: "Keep it light. A quick review might be enough.",
};

function courseHref(course: string): string {
  return `/course/${encodeURIComponent(course)}`;
}

// "Touched" means the learner has actually done something with this topic —
// a fresh topic's mastery row exists from the moment it's created (score 0,
// status "unmastered"), so last_updated alone would just reflect topic
// creation order, not real activity.
function isTouched(mastery: Mastery): boolean {
  return mastery.score > 0 || mastery.status !== "unmastered" || mastery.flagged_for_revision;
}

function mostRecentActiveTopic(
  topics: Topic[],
  masteryByTopic: Record<number, Mastery>
): { topic: Topic; mastery: Mastery } | null {
  let best: { topic: Topic; mastery: Mastery } | null = null;
  for (const topic of topics) {
    const mastery = masteryByTopic[topic.id];
    if (!mastery || !isTouched(mastery)) continue;
    if (!best || new Date(mastery.last_updated).getTime() > new Date(best.mastery.last_updated).getTime()) {
      best = { topic, mastery };
    }
  }
  return best;
}

export function getWelcomeContext(
  period: TimePeriod,
  topics: Topic[],
  masteryByTopic: Record<number, Mastery>,
  graph: GraphData | null,
  courses: CourseSummary[]
): WelcomeContext {
  if (courses.length === 0) {
    return { message: "What would you like to learn today?" };
  }

  const recent = mostRecentActiveTopic(topics, masteryByTopic);

  if (!recent) {
    // Courses/topics exist, but nothing has been studied yet — a plain
    // time-of-day message reads better than pushing a "continue" CTA that
    // has nothing real to continue.
    return { message: TIME_FALLBACK[period] };
  }

  const course = courses.find((c) => c.name === recent.topic.course);
  const contextLine = course ? `${course.name} · ${course.avgScore}% mastery` : undefined;

  // Graph is already loaded app-wide for the prerequisite view — this is a
  // single small walk over that in-memory data, not a new fetch or an
  // expensive recomputation.
  const gap = graph ? getUnmasteredPrereqs(graph, recent.topic.id)[0] : undefined;
  if (gap) {
    return {
      message: `${gap.name} could use another look before you move ahead.`,
      cta: { label: "Review topic", href: courseHref(gap.course) },
      contextLine,
    };
  }

  if (recent.mastery.status === "mastered") {
    const hasMoreToLearn = course?.topics.some((t) => masteryByTopic[t.id]?.status !== "mastered") ?? false;
    return {
      message: `You're making steady progress in ${recent.topic.course}.`,
      cta: hasMoreToLearn
        ? { label: `Continue ${recent.topic.course}`, href: courseHref(recent.topic.course) }
        : undefined,
      contextLine,
    };
  }

  return {
    message: `Ready to continue ${recent.topic.name}?`,
    cta: { label: `Continue ${recent.topic.course}`, href: courseHref(recent.topic.course) },
    contextLine,
  };
}
