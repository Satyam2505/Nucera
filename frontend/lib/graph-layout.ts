// Visual-only graph state: where each topic card sits on the canvas. Kept
// completely separate from academic state (topics, prerequisites, mastery)
// — nothing here ever reads or writes those.

export interface Position {
  x: number;
  y: number;
}
export type Positions = Record<number, Position>;

export const NODE_WIDTH = 190;
export const NODE_HEIGHT = 84;
const X_GAP = 250;
const Y_GAP = 112;

interface LayoutNode {
  id: number;
}
interface LayoutEdge {
  source: number;
  target: number;
}

/**
 * Default layout: columns by prerequisite depth (left to right), rows
 * ordered by the average row of each topic's prerequisites to keep edges
 * short, each column centered on the tallest one. Purely cosmetic.
 */
export function computeDefaultPositions(nodes: LayoutNode[], edges: LayoutEdge[]): Positions {
  const ids = new Set(nodes.map((n) => n.id));
  const incoming = new Map<number, number[]>();
  for (const e of edges) {
    if (!ids.has(e.source) || !ids.has(e.target)) continue;
    incoming.set(e.target, [...(incoming.get(e.target) ?? []), e.source]);
  }

  const level = new Map<number, number>();
  function levelOf(id: number, stack: Set<number>): number {
    const known = level.get(id);
    if (known !== undefined) return known;
    if (stack.has(id)) return 0; // cycle guard
    stack.add(id);
    const parents = incoming.get(id) ?? [];
    const value = parents.length === 0 ? 0 : Math.max(...parents.map((p) => levelOf(p, stack))) + 1;
    stack.delete(id);
    level.set(id, value);
    return value;
  }
  nodes.forEach((n) => levelOf(n.id, new Set()));

  const columns = new Map<number, number[]>();
  for (const n of nodes) {
    const l = level.get(n.id) ?? 0;
    columns.set(l, [...(columns.get(l) ?? []), n.id]);
  }

  const rowOf = new Map<number, number>();
  const maxLevel = Math.max(0, ...columns.keys());
  for (let l = 0; l <= maxLevel; l++) {
    const col = columns.get(l) ?? [];
    if (l > 0) {
      const score = (id: number) => {
        const parents = incoming.get(id) ?? [];
        if (!parents.length) return 0;
        return parents.reduce((sum, p) => sum + (rowOf.get(p) ?? 0), 0) / parents.length;
      };
      col.sort((a, b) => score(a) - score(b));
    }
    col.forEach((id, i) => rowOf.set(id, i));
    columns.set(l, col);
  }

  const tallest = Math.max(1, ...[...columns.values()].map((c) => c.length));
  const positions: Positions = {};
  for (const [l, col] of columns) {
    const offset = ((tallest - col.length) * Y_GAP) / 2;
    col.forEach((id, i) => {
      positions[id] = { x: l * X_GAP, y: offset + i * Y_GAP };
    });
  }
  return positions;
}

/**
 * Gentle alignment assist while dragging: if the dragged card is within
 * `tolerance` (flow units) of another card's left edge or top edge, pull it
 * onto that line. Each axis snaps independently and only within the small
 * tolerance, so movement stays free-form.
 */
export function snapToNeighbors(
  id: number,
  position: Position,
  others: { id: number; position: Position }[],
  tolerance: number
): Position {
  let x = position.x;
  let y = position.y;
  let bestX = tolerance;
  let bestY = tolerance;
  for (const other of others) {
    if (other.id === id) continue;
    const dx = Math.abs(position.x - other.position.x);
    if (dx < bestX) {
      bestX = dx;
      x = other.position.x;
    }
    const dy = Math.abs(position.y - other.position.y);
    if (dy < bestY) {
      bestY = dy;
      y = other.position.y;
    }
  }
  return { x, y };
}

// --- Persistence (localStorage, per course) ---------------------------------

const KEY_PREFIX = "nucera:graph-layout:";

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function defaultStorage(): StorageLike | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

function keyFor(course: string): string {
  return `${KEY_PREFIX}${course}`;
}

/** Saved positions for a course, or null when none / unreadable / corrupt. */
export function loadLayout(course: string, storage: StorageLike | null = defaultStorage()): Positions | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(keyFor(course));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const positions: Positions = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      const v = value as { x?: unknown; y?: unknown } | null;
      if (v && typeof v.x === "number" && typeof v.y === "number" && Number.isFinite(v.x) && Number.isFinite(v.y)) {
        positions[Number(key)] = { x: v.x, y: v.y };
      }
    }
    return Object.keys(positions).length ? positions : null;
  } catch {
    return null;
  }
}

export function saveLayout(course: string, positions: Positions, storage: StorageLike | null = defaultStorage()): void {
  if (!storage) return;
  try {
    const rounded: Positions = {};
    for (const [id, p] of Object.entries(positions)) {
      rounded[Number(id)] = { x: Math.round(p.x * 100) / 100, y: Math.round(p.y * 100) / 100 };
    }
    storage.setItem(keyFor(course), JSON.stringify(rounded));
  } catch {
    // Quota exceeded / storage blocked: the layout just won't persist.
  }
}

export function clearLayout(course: string, storage: StorageLike | null = defaultStorage()): void {
  if (!storage) return;
  try {
    storage.removeItem(keyFor(course));
  } catch {
    // ignore
  }
}
