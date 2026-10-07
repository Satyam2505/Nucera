// Pure helpers for editing prerequisites in the graph view. No React, no fetch,
// and no runtime imports, so they are testable under plain Node (graph-edit.test.ts).

export interface EditableTopic {
  id: number;
  name: string;
  module_name: string;
}

/**
 * The topics that can be offered as a new prerequisite of `selectedId`, in the
 * order given. Left out: the topic itself, those it already requires directly,
 * and every topic that (through any chain) already depends on it, because making
 * one of those a prerequisite would close a loop. The server checks this too;
 * leaving them out here just means the picker never offers a link that will fail.
 */
export function candidatePrerequisites(
  topics: EditableTopic[],
  selectedId: number,
  directPrerequisiteIds: readonly number[],
  dependentIds: ReadonlySet<number>
): EditableTopic[] {
  const taken = new Set(directPrerequisiteIds);
  return topics.filter((t) => t.id !== selectedId && !taken.has(t.id) && !dependentIds.has(t.id));
}

/** "Hash tables · Module 2": how a candidate reads in the picker. */
export function candidateLabel(topic: EditableTopic): string {
  return topic.module_name ? `${topic.name} · ${topic.module_name}` : topic.name;
}

/** The text to show for a failed add/remove (the server's readable message, else a fallback). */
export function editErrorText(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}
