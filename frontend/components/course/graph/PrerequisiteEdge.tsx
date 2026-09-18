"use client";

import { memo, useState } from "react";
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from "reactflow";

import type { EdgeRole } from "@/lib/graph-model";

import { useGraphUi } from "./graph-context";

export interface PrerequisiteEdgeData {
  sourceName: string;
  targetName: string;
}

export const ARROW_DEFAULT = "nucera-arrow-default";
export const ARROW_ACCENT = "nucera-arrow-accent";

/** Arrowhead definitions, referenced by id from the edge paths. Rendered once. */
export function GraphMarkers() {
  const common = {
    viewBox: "0 0 10 10",
    refX: 9,
    refY: 5,
    markerWidth: 9,
    markerHeight: 9,
    markerUnits: "userSpaceOnUse" as const,
    orient: "auto-start-reverse",
  };
  return (
    <svg aria-hidden style={{ position: "absolute", width: 0, height: 0 }}>
      <defs>
        <marker id={ARROW_DEFAULT} {...common}>
          <path d="M1 1.5 9 5 1 8.5z" style={{ fill: "rgba(var(--ink-rgb), 0.45)" }} />
        </marker>
        <marker id={ARROW_ACCENT} {...common}>
          <path d="M1 1.5 9 5 1 8.5z" style={{ fill: "var(--accent)" }} />
        </marker>
      </defs>
    </svg>
  );
}

interface EdgeStyle {
  stroke: string;
  width: number;
  dash?: string;
  opacity: number;
  marker: string;
}

// prereq edges are solid and dependent edges dashed (matching the solid /
// dashed node outlines), so direction of the highlighted path is readable
// without relying on color.
function styleFor(role: EdgeRole): EdgeStyle {
  switch (role) {
    case "prereq":
      return { stroke: "var(--accent)", width: 2.4, opacity: 1, marker: ARROW_ACCENT };
    case "dependent":
      return { stroke: "var(--accent)", width: 2.4, dash: "7 5", opacity: 1, marker: ARROW_ACCENT };
    case "hover":
      return { stroke: "var(--accent)", width: 2, opacity: 0.85, marker: ARROW_ACCENT };
    case "dim":
      return { stroke: "rgba(var(--ink-rgb), 0.30)", width: 1.5, opacity: 0.5, marker: ARROW_DEFAULT };
    case "muted":
      return { stroke: "rgba(var(--ink-rgb), 0.30)", width: 1.5, opacity: 0.3, marker: ARROW_DEFAULT };
    case "faded":
      return { stroke: "rgba(var(--ink-rgb), 0.30)", width: 1.5, opacity: 0.1, marker: ARROW_DEFAULT };
    default:
      return { stroke: "rgba(var(--ink-rgb), 0.30)", width: 1.5, opacity: 1, marker: ARROW_DEFAULT };
  }
}

function PrerequisiteEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<PrerequisiteEdgeData>) {
  const { edgeRoles } = useGraphUi();
  const [hovered, setHovered] = useState(false);
  const role = edgeRoles.get(id) ?? "none";
  const style = styleFor(role);

  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={`url(#${style.marker})`}
        style={{
          stroke: style.stroke,
          strokeWidth: hovered && role !== "faded" ? style.width + 0.8 : style.width,
          strokeDasharray: style.dash,
          opacity: style.opacity,
          transition: "opacity 200ms ease-out, stroke-width 150ms ease-out",
        }}
      />
      {/* Wide invisible hit area so thin edges are easy to hover. Purely
          informational: edges can't be dragged, reconnected or deleted. */}
      <path
        d={path}
        fill="none"
        stroke="transparent"
        strokeWidth={16}
        style={{ pointerEvents: "stroke" }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      {hovered && data && (
        <EdgeLabelRenderer>
          <div
            role="tooltip"
            className="pointer-events-none absolute z-50 max-w-[15rem] rounded-lg border border-[rgba(var(--ink-rgb),0.15)] bg-[var(--bg-surface)] px-2.5 py-1.5 text-xs shadow-lg"
            style={{ transform: `translate(-50%, calc(-100% - 8px)) translate(${labelX}px, ${labelY}px)` }}
          >
            <p className="font-medium text-[var(--ink)]">
              {data.sourceName} → {data.targetName}
            </p>
            <p className="mt-0.5 text-[var(--ink)]/70">
              {data.sourceName} is a prerequisite for {data.targetName}.
            </p>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export default memo(PrerequisiteEdge);
