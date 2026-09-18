"use client";

import { Maximize2, Minus, Plus } from "lucide-react";
import { useRef, type ReactNode } from "react";
import { useReactFlow, useStore } from "reactflow";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { stepZoom, zoomPercent } from "@/lib/graph-viewport";

interface Props {
  min: number;
  max: number;
  /** Additive zoom step per +/- click, e.g. 0.15 = 15 percentage points. */
  step: number;
  duration: number;
  onFit: () => void;
  /** Called right after a zoom command so the graph can save the final camera. */
  onZoomed: () => void;
}

const buttonClass =
  "inline-flex h-7 items-center justify-center rounded-full text-[var(--ink)]/70 transition-colors " +
  "hover:bg-[rgba(var(--accent-rgb),0.14)] hover:text-[var(--accent-hover)] " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(var(--accent-rgb),0.5)] " +
  "disabled:pointer-events-none disabled:opacity-35";

function Tip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="top" sideOffset={6}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Small floating zoom control: + / live percentage / − / Fit. Every
 * zoom goes through React Flow's viewport API (zoomTo), which scales about the
 * center of the canvas, so the view never jumps somewhere else.
 */
export default function GraphZoomControls({ min, max, step, duration, onFit, onZoomed }: Props) {
  const { zoomTo } = useReactFlow();
  const zoom = useStore((s) => s.transform[2]);
  // While a zoom animation is running the store still reports the in-between
  // zoom; basing rapid consecutive clicks on the last requested target keeps
  // the steps predictable (100 -> 115 -> 130) instead of swallowing clicks.
  const pending = useRef<{ target: number; at: number } | null>(null);

  const base = () => {
    const p = pending.current;
    return p && Date.now() - p.at < duration + 60 ? p.target : zoom;
  };

  const zoomBy = (direction: 1 | -1) => {
    const target = stepZoom(base(), direction, step, min, max);
    pending.current = { target, at: Date.now() };
    zoomTo(target, { duration });
    onZoomed();
  };

  const resetTo100 = () => {
    pending.current = { target: 1, at: Date.now() };
    zoomTo(1, { duration });
    onZoomed();
  };

  const atMax = zoom >= max - 0.001;
  const atMin = zoom <= min + 0.001;

  return (
    <div
      className="nopan nowheel flex items-center gap-0.5 rounded-full border border-[rgba(var(--ink-rgb),0.12)] bg-[var(--bg-surface)] p-1 shadow-sm"
      role="group"
      aria-label="Graph zoom"
    >
      <Tip label="Zoom in">
        <button type="button" className={`${buttonClass} w-7`} onClick={() => zoomBy(1)} disabled={atMax} aria-label="Zoom in">
          <Plus size={15} strokeWidth={2} />
        </button>
      </Tip>
      <Tip label="Reset zoom">
        <button
          type="button"
          className={`${buttonClass} min-w-[3.1rem] px-1.5 text-xs font-medium tabular-nums`}
          onClick={resetTo100}
          aria-label={`Zoom ${zoomPercent(zoom)} percent. Reset zoom to 100 percent`}
        >
          {zoomPercent(zoom)}%
        </button>
      </Tip>
      <Tip label="Zoom out">
        <button type="button" className={`${buttonClass} w-7`} onClick={() => zoomBy(-1)} disabled={atMin} aria-label="Zoom out">
          <Minus size={15} strokeWidth={2} />
        </button>
      </Tip>
      <span className="mx-0.5 h-4 w-px bg-[rgba(var(--ink-rgb),0.14)]" aria-hidden />
      <Tip label="Fit graph to view">
        <button type="button" className={`${buttonClass} w-7`} onClick={onFit} aria-label="Fit graph to view">
          <Maximize2 size={14} strokeWidth={2} />
        </button>
      </Tip>
    </div>
  );
}
