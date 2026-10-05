// Pure module grouping for the knowledge graph: which module each node
// belongs to, a stable tint order, and the module filter. Visual-only —
// like graph-layout, it never reads or writes academic state.

// Soft hues for telling modules apart on the canvas. They are a visual aid
// only: every card also carries its module number as text, and none of them
// is a mastery-status color.
export const MODULE_TINTS = ["#6c8ebf", "#c98b5b", "#7ba88b", "#a98bc9", "#c9a64b", "#5ba8b5"];

export function tintFor(index: number): string {
  return MODULE_TINTS[index % MODULE_TINTS.length];
}

export interface ModuleNode {
  module_id: number;
  module_name: string;
  module_position: number;
}

export interface ModuleGroup {
  id: number;
  name: string;
  position: number;
  nodeCount: number;
}

/** Distinct modules present in `nodes`, in course order (position, then id). */
export function groupNodesByModule(nodes: ModuleNode[]): ModuleGroup[] {
  const groups = new Map<number, ModuleGroup>();
  for (const node of nodes) {
    const group = groups.get(node.module_id);
    if (group) group.nodeCount++;
    else
      groups.set(node.module_id, {
        id: node.module_id,
        name: node.module_name,
        position: node.module_position,
        nodeCount: 1,
      });
  }
  return Array.from(groups.values()).sort((a, b) => a.position - b.position || a.id - b.id);
}

/** Module id -> index in course order, for picking a tint from a palette. */
export function moduleTintIndex(groups: ModuleGroup[]): Map<number, number> {
  return new Map(groups.map((g, i) => [g.id, i]));
}

/** Nodes left after hiding the given modules. */
export function visibleNodes<T extends { module_id: number }>(
  nodes: T[],
  hiddenModuleIds: ReadonlySet<number>
): T[] {
  return hiddenModuleIds.size === 0 ? nodes : nodes.filter((n) => !hiddenModuleIds.has(n.module_id));
}
