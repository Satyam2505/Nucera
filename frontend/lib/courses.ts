import type { Topic } from "./api";

export function courseHref(courseId: number): string {
  return `/course/${courseId}`;
}

/** "Course · Module" — shown under a topic name wherever topics from several courses mix. */
export function topicLocation(topic: Pick<Topic, "course_name" | "module_name">): string {
  return `${topic.course_name} · ${topic.module_name}`;
}

export interface ModuleTopics {
  courseId: number;
  courseName: string;
  moduleId: number;
  moduleName: string;
  topics: Topic[];
}

/**
 * Groups topics by module, keeping the order they arrive in (the API sorts by
 * course, module position, then topic position), so a picker can render
 * course/module headings without re-sorting.
 */
export function groupTopicsByModule(topics: Topic[]): ModuleTopics[] {
  const groups = new Map<number, ModuleTopics>();
  for (const topic of topics) {
    let group = groups.get(topic.module_id);
    if (!group) {
      group = {
        courseId: topic.course_id,
        courseName: topic.course_name,
        moduleId: topic.module_id,
        moduleName: topic.module_name,
        topics: [],
      };
      groups.set(topic.module_id, group);
    }
    group.topics.push(topic);
  }
  return Array.from(groups.values());
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
