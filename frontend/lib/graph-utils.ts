import type { GraphData, GraphNode } from "./api";

/** Ancestors (prerequisites) of a topic, computed client-side from the graph's edges. */
export function getUnmasteredPrereqs(graph: GraphData, topicId: number): GraphNode[] {
  const incoming = new Map<number, number[]>();
  graph.edges.forEach((edge) => {
    incoming.set(edge.target, [...(incoming.get(edge.target) ?? []), edge.source]);
  });
  const nodesById = new Map(graph.nodes.map((n) => [n.id, n]));

  const visited = new Set<number>();
  const result: GraphNode[] = [];

  function walk(id: number) {
    for (const parentId of incoming.get(id) ?? []) {
      if (visited.has(parentId)) continue;
      visited.add(parentId);
      const node = nodesById.get(parentId);
      if (node && node.status !== "mastered") result.push(node);
      walk(parentId);
    }
  }

  walk(topicId);
  return result;
}
