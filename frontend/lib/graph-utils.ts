import type { Edge, Node } from "reactflow";
import { MarkerType } from "reactflow";

import type { GraphData, GraphNode } from "./api";
import { STATUS_COLOR, STATUS_FILL, type MasteryStatusKey } from "./status-colors";

export function layoutNodes(data: GraphData, xGap = 220, yGap = 110, compact = false): Node[] {
  const levels: Record<number, number> = {};
  const incoming = new Map<number, number[]>();
  data.edges.forEach((edge) => {
    incoming.set(edge.target, [...(incoming.get(edge.target) ?? []), edge.source]);
  });

  function computeLevel(nodeId: number, seen = new Set<number>()): number {
    if (levels[nodeId] !== undefined) return levels[nodeId];
    if (seen.has(nodeId)) return 0;
    seen.add(nodeId);
    const parents = incoming.get(nodeId) ?? [];
    const level =
      parents.length === 0 ? 0 : Math.max(...parents.map((p) => computeLevel(p, seen))) + 1;
    levels[nodeId] = level;
    return level;
  }

  data.nodes.forEach((node) => computeLevel(node.id));

  const countPerLevel: Record<number, number> = {};

  return data.nodes.map((node) => {
    const level = levels[node.id] ?? 0;
    const index = countPerLevel[level] ?? 0;
    countPerLevel[level] = index + 1;

    const status = (node.status as MasteryStatusKey) ?? "unmastered";

    return {
      id: String(node.id),
      position: { x: level * xGap, y: index * yGap },
      data: { label: compact ? node.name : `${node.name}\n(${node.status})` },
      style: {
        background: STATUS_FILL[status] ?? STATUS_FILL.unmastered,
        border: `1.5px solid ${STATUS_COLOR[status] ?? STATUS_COLOR.unmastered}`,
        borderRadius: 10,
        padding: compact ? 6 : 10,
        fontSize: compact ? 10 : 12,
        whiteSpace: "pre-line" as const,
        color: "var(--ink)",
        boxShadow: "0 1px 3px rgba(0,0,0,0.25)",
      },
    };
  });
}

export function buildEdges(data: GraphData): Edge[] {
  return data.edges.map((edge) => ({
    id: `${edge.source}-${edge.target}`,
    source: String(edge.source),
    target: String(edge.target),
    markerEnd: { type: MarkerType.ArrowClosed, color: "rgba(var(--ink-rgb), 0.4)" },
    style: { stroke: "rgba(var(--ink-rgb), 0.3)" },
  }));
}

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
