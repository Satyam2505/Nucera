"use client";

import { useMemo } from "react";
import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";

import { Badge } from "@/components/ui/badge";
import { useAppState } from "@/lib/AppStateContext";
import { buildEdges, layoutNodes } from "@/lib/graph-utils";
import { STATUS_COLOR, STATUS_LABEL, type MasteryStatusKey } from "@/lib/status-colors";

const LEGEND_ORDER: MasteryStatusKey[] = ["mastered", "in_progress", "unmastered", "missed"];

export default function GraphView({ courseName }: { courseName: string }) {
  const { graph } = useAppState();

  const filtered = useMemo(() => {
    if (!graph) return null;
    const nodes = graph.nodes.filter((n) => n.course === courseName);
    const ids = new Set(nodes.map((n) => n.id));
    const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return { nodes, edges };
  }, [graph, courseName]);

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-4 px-6 py-3 border-b border-[rgba(var(--ink-rgb),0.10)] text-xs">
        {LEGEND_ORDER.map((status) => (
          <Badge key={status} variant="secondary" className="gap-1.5 font-normal text-stone-600 dark:text-stone-400">
            <span className="h-2 w-2 rounded-full" style={{ background: STATUS_COLOR[status] }} aria-hidden />
            {STATUS_LABEL[status]}
          </Badge>
        ))}
      </div>

      <div className="flex-1">
        {!filtered && <p className="p-6 text-sm text-stone-500 dark:text-stone-400">Loading graph...</p>}
        {filtered && filtered.nodes.length === 0 && (
          <p className="p-6 text-sm text-stone-500 dark:text-stone-400">No topics in this course yet.</p>
        )}
        {filtered && filtered.nodes.length > 0 && (
          <ReactFlow nodes={layoutNodes(filtered)} edges={buildEdges(filtered)} fitView>
            <Background color="rgba(var(--ink-rgb), 0.14)" gap={20} />
            <Controls />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}
