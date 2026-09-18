"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";

import { NODE_HEIGHT, NODE_WIDTH } from "@/lib/graph-layout";
import type { NodeRole } from "@/lib/graph-model";
import { STATUS_COLOR, STATUS_LABEL } from "@/lib/status-colors";

import { useGraphUi } from "./graph-context";
import { normalizeStatus, PATH_COLOR, PATH_LABEL, PathIcon, StatusIcon } from "./graph-icons";

export interface TopicNodeData {
  topicId: number;
  name: string;
  status: string;
  score: number;
}

const OPACITY: Partial<Record<NodeRole, number>> = { dim: 0.72, muted: 0.45, faded: 0.14 };
const CHIP: Partial<Record<NodeRole, string>> = { prereq: "Before", dependent: "After" };

// Handles are required for edge geometry but connecting is disabled, so
// they're invisible and inert.
const handleClass = "!h-1 !w-1 !min-h-0 !min-w-0 !border-0 !bg-transparent !opacity-0";

function TopicNode({ data }: NodeProps<TopicNodeData>) {
  const { nodeRoles, pathStates, selectedId } = useGraphUi();
  const role = nodeRoles.get(data.topicId) ?? "none";
  const status = normalizeStatus(data.status);
  const path = pathStates?.get(data.topicId) ?? null;
  const score = Math.max(0, Math.min(100, Math.round(data.score)));
  const selected = selectedId === data.topicId;

  // Two independent signals, both non-color-only: the ring/outline STYLE
  // says how this card relates to the highlighted topic (solid = before,
  // dashed = after, thick = the topic itself) and the small text chip names it.
  let boxShadow = "0 1px 3px rgba(0,0,0,0.18)";
  let outline: string | undefined;
  if (role === "focus" || selected) boxShadow = "0 0 0 2.5px var(--accent), 0 6px 16px -6px rgba(0,0,0,0.35)";
  else if (role === "prereq") boxShadow = "0 0 0 1.5px var(--accent), 0 1px 3px rgba(0,0,0,0.18)";
  else if (role === "dependent") outline = "1.5px dashed var(--accent)";
  else if (path === "attention") boxShadow = "0 0 0 1.5px var(--status-missed), 0 1px 3px rgba(0,0,0,0.18)";

  let opacity = OPACITY[role] ?? 1;
  if (path === "later" && role === "none") opacity = 0.62;

  const chip = selected ? "Selected" : CHIP[role];

  return (
    <div
      className="relative flex h-full w-full cursor-grab select-none flex-col justify-between rounded-xl border bg-[var(--bg-surface)] px-3 py-2.5 transition-[transform,box-shadow,opacity,outline-color] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lg active:cursor-grabbing"
      style={{
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        borderColor: path ? PATH_COLOR[path] : STATUS_COLOR[status],
        borderStyle: status === "unmastered" && !path ? "dashed" : "solid",
        borderWidth: 1.5,
        boxShadow,
        outline,
        outlineOffset: outline ? 3 : undefined,
        opacity,
      }}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} className={handleClass} />
      <Handle type="source" position={Position.Right} isConnectable={false} className={handleClass} />

      {chip && (
        <span className="pointer-events-none absolute -top-2 right-2 rounded-full border border-[rgba(var(--ink-rgb),0.15)] bg-[var(--bg-surface)] px-1.5 text-[9px] font-medium leading-4 text-[var(--ink)]">
          {chip}
        </span>
      )}

      <p className="line-clamp-2 text-[13px] font-medium leading-snug text-[var(--ink)]">{data.name}</p>

      <div>
        <div className="flex items-center gap-1.5 text-[11px] text-[var(--ink)]/70">
          {path ? <PathIcon state={path} /> : <StatusIcon status={status} />}
          <span className="truncate">
            {path ? PATH_LABEL[path] : STATUS_LABEL[status]}
            {!path && status !== "unmastered" ? ` · ${score}%` : ""}
          </span>
        </div>
        <div className="mt-1 h-[3px] overflow-hidden rounded-full bg-[rgba(var(--ink-rgb),0.10)]" aria-hidden>
          <div
            className="h-full rounded-full"
            style={{ width: `${score}%`, background: path ? PATH_COLOR[path] : STATUS_COLOR[status] }}
          />
        </div>
      </div>
    </div>
  );
}

export default memo(TopicNode);
