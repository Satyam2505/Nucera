import type { PathState } from "@/lib/graph-model";
import { STATUS_COLOR, STATUS_LABEL, type MasteryStatusKey } from "@/lib/status-colors";

// Every status/path state pairs its color with a distinct SHAPE and a text
// label, so meaning never depends on color perception alone.

export function normalizeStatus(status: string): MasteryStatusKey {
  return status in STATUS_LABEL ? (status as MasteryStatusKey) : "unmastered";
}

export function StatusIcon({ status, size = 13 }: { status: MasteryStatusKey; size?: number }) {
  const color = STATUS_COLOR[status];
  const common = { width: size, height: size, viewBox: "0 0 16 16", fill: "none", "aria-hidden": true } as const;
  switch (status) {
    case "mastered":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6.5" fill={color} />
          <path d="m5 8.2 2.2 2.2L11 6.2" stroke="var(--bg-surface)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "in_progress":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6" stroke={color} strokeWidth="1.5" />
          <path d="M8 2a6 6 0 0 1 0 12z" fill={color} />
        </svg>
      );
    case "missed":
      return (
        <svg {...common}>
          <path d="M8 1.8 15 14H1z" fill={color} stroke={color} strokeWidth="1.2" strokeLinejoin="round" />
          <path d="M8 6.2v3.4M8 11.6v.1" stroke="var(--bg-surface)" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6" stroke={color} strokeWidth="1.5" strokeDasharray="2.6 2.4" />
        </svg>
      );
  }
}

export const PATH_LABEL: Record<PathState, string> = {
  covered: "Covered",
  attention: "Needs attention",
  next: "Up next",
  later: "Later",
};

export const PATH_COLOR: Record<PathState, string> = {
  covered: "var(--status-mastered)",
  attention: "var(--status-missed)",
  next: "var(--accent)",
  later: "var(--status-unmastered)",
};

export function PathIcon({ state, size = 13 }: { state: PathState; size?: number }) {
  const color = PATH_COLOR[state];
  const common = { width: size, height: size, viewBox: "0 0 16 16", fill: "none", "aria-hidden": true } as const;
  switch (state) {
    case "covered":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6.5" fill={color} />
          <path d="m5 8.2 2.2 2.2L11 6.2" stroke="var(--bg-surface)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "attention":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6.5" fill={color} />
          <path d="M8 4.6v4M8 11v.1" stroke="var(--bg-surface)" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      );
    case "next":
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6.2" stroke={color} strokeWidth="1.6" />
          <path d="M5.6 8h4.6M8.6 5.8 10.8 8l-2.2 2.2" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="5.6" stroke={color} strokeWidth="1.4" strokeDasharray="1.6 2.6" strokeLinecap="round" />
        </svg>
      );
  }
}
