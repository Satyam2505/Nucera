"use client";

import { createContext, useContext } from "react";

import type { EdgeRole, NodeRole, PathState } from "@/lib/graph-model";

// Visual highlight state shared with the custom nodes/edges. Kept in
// context (not in the node objects) so that hover/selection changes don't
// rebuild node data, and dragging — which only changes positions — never
// re-renders any node except the one being moved.
export interface GraphUi {
  nodeRoles: Map<number, NodeRole>;
  edgeRoles: Map<string, EdgeRole>;
  pathStates: Map<number, PathState> | null;
  selectedId: number | null;
}

export const GraphUiContext = createContext<GraphUi>({
  nodeRoles: new Map(),
  edgeRoles: new Map(),
  pathStates: null,
  selectedId: null,
});

export function useGraphUi(): GraphUi {
  return useContext(GraphUiContext);
}
