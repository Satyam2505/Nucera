// Pure prerequisite-graph queries used by the interactive graph view. This
// is deliberately read-only over the academic data (topics, edges, mastery
// status) — it derives display information from it and never changes it.
// Edge direction everywhere: source -> target means "source is a
// prerequisite of target" (learn source first).

export interface ModelNode {
  id: number;
  status: string;
}

export interface ModelEdge {
  source: number;
  target: number;
}

export interface GraphModel {
  ids: number[];
  prereqs: Map<number, number[]>;
  dependents: Map<number, number[]>;
  statusById: Map<number, string>;
}

export function edgeId(source: number, target: number): string {
  return `${source}-${target}`;
}

export function buildModel(nodes: ModelNode[], edges: ModelEdge[]): GraphModel {
  const prereqs = new Map<number, number[]>();
  const dependents = new Map<number, number[]>();
  const statusById = new Map<number, string>();
  for (const n of nodes) {
    prereqs.set(n.id, []);
    dependents.set(n.id, []);
    statusById.set(n.id, n.status);
  }
  for (const e of edges) {
    // Ignore edges that point outside this node set (e.g. another course).
    if (!prereqs.has(e.source) || !prereqs.has(e.target)) continue;
    prereqs.get(e.target)!.push(e.source);
    dependents.get(e.source)!.push(e.target);
  }
  return { ids: nodes.map((n) => n.id), prereqs, dependents, statusById };
}

function reach(start: number, next: Map<number, number[]>): Set<number> {
  const seen = new Set<number>();
  const stack = [...(next.get(start) ?? [])];
  while (stack.length) {
    const id = stack.pop()!;
    if (seen.has(id) || id === start) continue;
    seen.add(id);
    for (const n of next.get(id) ?? []) stack.push(n);
  }
  return seen;
}

/** Every topic that must be learned before `id`, transitively. */
export function ancestors(model: GraphModel, id: number): Set<number> {
  return reach(id, model.prereqs);
}

/** Every topic that depends on `id`, transitively. */
export function descendants(model: GraphModel, id: number): Set<number> {
  return reach(id, model.dependents);
}

// --- Learning path lens ---------------------------------------------------

export type PathState = "covered" | "attention" | "next" | "later";

const STARTED = new Set(["in_progress", "mastered", "missed"]);

/**
 * A read-only lens over existing mastery + prerequisite data (no new
 * recommendation algorithm):
 *  - covered:   mastered
 *  - attention: not mastered and either "missed", or a prerequisite gap —
 *               some topic downstream of it has already been started
 *  - next:      not mastered, no gap, and either in progress or every
 *               direct prerequisite is mastered (safe to learn now)
 *  - later:     everything else (still blocked by unmastered prerequisites)
 */
export function computePathStates(model: GraphModel): Map<number, PathState> {
  const result = new Map<number, PathState>();
  for (const id of model.ids) {
    const status = model.statusById.get(id) ?? "unmastered";
    if (status === "mastered") {
      result.set(id, "covered");
      continue;
    }
    const gap = [...descendants(model, id)].some((d) => STARTED.has(model.statusById.get(d) ?? ""));
    if (status === "missed" || gap) {
      result.set(id, "attention");
      continue;
    }
    const directPrereqs = model.prereqs.get(id) ?? [];
    const available = directPrereqs.every((p) => model.statusById.get(p) === "mastered");
    result.set(id, status === "in_progress" || available ? "next" : "later");
  }
  return result;
}

// --- Highlighting ---------------------------------------------------------

/**
 * focus:     the topic the highlight is centered on
 * prereq:    learned before the focus topic
 * dependent: learned after the focus topic
 * none:      no highlight active
 * dim:       unrelated, softly de-emphasized (hover)
 * muted:     unrelated, de-emphasized (selection)
 * faded:     outside the neighborhood in focus mode
 */
export type NodeRole = "focus" | "prereq" | "dependent" | "none" | "dim" | "muted" | "faded";
export type EdgeRole = "prereq" | "dependent" | "hover" | "none" | "dim" | "muted" | "faded";

export interface Highlight {
  nodeRoles: Map<number, NodeRole>;
  edgeRoles: Map<string, EdgeRole>;
}

export interface HighlightInput {
  selectedId: number | null;
  hoveredId: number | null;
  focusId: number | null;
}

export function computeHighlight(model: GraphModel, edges: ModelEdge[], input: HighlightInput): Highlight {
  const nodeRoles = new Map<number, NodeRole>();
  const edgeRoles = new Map<string, EdgeRole>();
  const valid = edges.filter((e) => model.prereqs.has(e.source) && model.prereqs.has(e.target));

  const centerId = input.focusId ?? input.selectedId ?? input.hoveredId;
  if (centerId === null || !model.prereqs.has(centerId)) {
    for (const id of model.ids) nodeRoles.set(id, "none");
    for (const e of valid) edgeRoles.set(edgeId(e.source, e.target), "none");
    return { nodeRoles, edgeRoles };
  }

  if (input.focusId !== null && model.prereqs.has(input.focusId)) {
    // Focus mode: the immediate neighborhood only.
    const direct = new Set(model.prereqs.get(input.focusId));
    const after = new Set(model.dependents.get(input.focusId));
    for (const id of model.ids) {
      if (id === input.focusId) nodeRoles.set(id, "focus");
      else if (direct.has(id)) nodeRoles.set(id, "prereq");
      else if (after.has(id)) nodeRoles.set(id, "dependent");
      else nodeRoles.set(id, "faded");
    }
    for (const e of valid) {
      const role: EdgeRole =
        e.target === input.focusId ? "prereq" : e.source === input.focusId ? "dependent" : "faded";
      edgeRoles.set(edgeId(e.source, e.target), role);
    }
    return { nodeRoles, edgeRoles };
  }

  if (input.selectedId !== null && model.prereqs.has(input.selectedId)) {
    // Selection: the full path before and after the selected topic.
    const sel = input.selectedId;
    const before = ancestors(model, sel);
    const after = descendants(model, sel);
    for (const id of model.ids) {
      if (id === sel) nodeRoles.set(id, "focus");
      else if (before.has(id)) nodeRoles.set(id, "prereq");
      else if (after.has(id)) nodeRoles.set(id, "dependent");
      else nodeRoles.set(id, "muted");
    }
    for (const e of valid) {
      let role: EdgeRole = "muted";
      if (before.has(e.source) && (before.has(e.target) || e.target === sel)) role = "prereq";
      else if ((after.has(e.target) && after.has(e.source)) || (e.source === sel && after.has(e.target)))
        role = "dependent";
      edgeRoles.set(edgeId(e.source, e.target), role);
    }
    // Hovering another topic still lightly emphasizes the edges touching it.
    const hov = input.hoveredId;
    if (hov !== null && hov !== sel) {
      for (const e of valid) {
        const key = edgeId(e.source, e.target);
        if ((e.source === hov || e.target === hov) && edgeRoles.get(key) === "muted") edgeRoles.set(key, "hover");
      }
    }
    return { nodeRoles, edgeRoles };
  }

  // Hover only: direct neighbors, everything else softly dimmed.
  const hov = centerId;
  const direct = new Set(model.prereqs.get(hov));
  const after = new Set(model.dependents.get(hov));
  for (const id of model.ids) {
    if (id === hov) nodeRoles.set(id, "focus");
    else if (direct.has(id)) nodeRoles.set(id, "prereq");
    else if (after.has(id)) nodeRoles.set(id, "dependent");
    else nodeRoles.set(id, "dim");
  }
  for (const e of valid) {
    edgeRoles.set(edgeId(e.source, e.target), e.source === hov || e.target === hov ? "hover" : "dim");
  }
  return { nodeRoles, edgeRoles };
}

/** Topics in a topic's immediate learning neighborhood (itself + direct links). */
export function neighborhood(model: GraphModel, id: number): number[] {
  return [id, ...(model.prereqs.get(id) ?? []), ...(model.dependents.get(id) ?? [])];
}
