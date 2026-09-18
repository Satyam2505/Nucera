"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import ReactFlow, {
  applyNodeChanges,
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeChange,
} from "reactflow";
import "reactflow/dist/style.css";

import { Button } from "@/components/ui/button";
import type { GraphData } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";
import {
  clearLayout,
  computeDefaultPositions,
  loadLayout,
  NODE_HEIGHT,
  NODE_WIDTH,
  saveLayout,
  snapToNeighbors,
  type Positions,
} from "@/lib/graph-layout";
import {
  ancestors,
  buildModel,
  computeHighlight,
  computePathStates,
  descendants,
  edgeId,
  neighborhood,
  type PathState,
} from "@/lib/graph-model";
import { STATUS_COLOR, STATUS_LABEL, type MasteryStatusKey } from "@/lib/status-colors";

import { GraphUiContext, type GraphUi } from "./graph/graph-context";
import { normalizeStatus, PATH_LABEL, PathIcon, StatusIcon } from "./graph/graph-icons";
import PrerequisiteEdge, { GraphMarkers, type PrerequisiteEdgeData } from "./graph/PrerequisiteEdge";
import TopicDetailPanel, { type PanelTopic } from "./graph/TopicDetailPanel";
import TopicNode, { type TopicNodeData } from "./graph/TopicNode";

// Defined once at module scope so React Flow doesn't see new type objects
// on every render.
const nodeTypes = { topic: TopicNode };
const edgeTypes = { prerequisite: PrerequisiteEdge };

const LEGEND_ORDER: MasteryStatusKey[] = ["mastered", "in_progress", "unmastered", "missed"];
const PATH_ORDER: PathState[] = ["covered", "attention", "next", "later"];

const MINIMAP_THRESHOLD = 12;
const SNAP_SCREEN_PX = 6;
const FIT_OPTIONS = { padding: 0.08, maxZoom: 1.1 } as const;

export type GraphOpenView = "chat" | "quiz";

interface Props {
  courseName: string;
  onOpenTopic?: (topicId: number, view: GraphOpenView) => void;
}

export default function GraphView({ courseName, onOpenTopic }: Props) {
  const { graph } = useAppState();

  const data = useMemo<GraphData | null>(() => {
    if (!graph) return null;
    const nodes = graph.nodes.filter((n) => n.course === courseName);
    const ids = new Set(nodes.map((n) => n.id));
    const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return { nodes, edges };
  }, [graph, courseName]);

  if (!data) return <p className="p-6 text-sm text-stone-500 dark:text-stone-400">Loading graph...</p>;
  if (data.nodes.length === 0) {
    return <p className="p-6 text-sm text-stone-500 dark:text-stone-400">No topics in this course yet.</p>;
  }

  // Keyed by course so each course gets its own canvas state and layout.
  return (
    <ReactFlowProvider key={courseName}>
      <GraphCanvas courseName={courseName} data={data} onOpenTopic={onOpenTopic} />
    </ReactFlowProvider>
  );
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function toNodes(
  data: GraphData,
  positions: Positions,
  previous?: Node<TopicNodeData>[]
): Node<TopicNodeData>[] {
  const old = new Map((previous ?? []).map((n) => [n.id, n]));
  return data.nodes.map((n) => {
    const id = String(n.id);
    const nodeData: TopicNodeData = { topicId: n.id, name: n.name, status: n.status, score: n.score };
    const existing = old.get(id);
    // Existing nodes keep their current (possibly user-dragged) position and
    // measured size; only their academic display data refreshes.
    if (existing) return { ...existing, data: nodeData };
    return { id, type: "topic", position: positions[n.id] ?? { x: 0, y: 0 }, data: nodeData };
  });
}

function GraphCanvas({ courseName, data, onOpenTopic }: { courseName: string; data: GraphData; onOpenTopic?: Props["onOpenTopic"] }) {
  const { fitView, setCenter, getZoom } = useReactFlow();

  // --- visual state (separate from academic data) ---------------------------
  const [nodes, setNodes] = useState<Node<TopicNodeData>[]>(() => {
    const saved = loadLayout(courseName);
    const defaults = computeDefaultPositions(data.nodes, data.edges);
    const merged: Positions = {};
    for (const n of data.nodes) merged[n.id] = saved?.[n.id] ?? defaults[n.id];
    return toNodes(data, merged);
  });
  const [customized, setCustomized] = useState(() => loadLayout(courseName) !== null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const [focusId, setFocusId] = useState<number | null>(null);
  const [pathMode, setPathMode] = useState(false);

  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const canvasRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const movedRef = useRef(false);
  const suppressClickRef = useRef(false);

  // Academic data refreshes (e.g. after a quiz) update each card's mastery
  // display but never its position.
  useEffect(() => {
    setNodes((prev) => {
      const saved = loadLayout(courseName);
      const defaults = computeDefaultPositions(data.nodes, data.edges);
      const positions: Positions = {};
      for (const n of data.nodes) positions[n.id] = saved?.[n.id] ?? defaults[n.id];
      return toNodes(data, positions, prev);
    });
  }, [data, courseName]);

  // --- academic-derived, read-only ----------------------------------------------
  const model = useMemo(() => buildModel(data.nodes, data.edges), [data]);
  const allPathStates = useMemo(() => computePathStates(model), [model]);
  const nameById = useMemo(() => new Map(data.nodes.map((n) => [n.id, n])), [data]);

  const edges = useMemo<Edge<PrerequisiteEdgeData>[]>(
    () =>
      data.edges.map((e) => ({
        id: edgeId(e.source, e.target),
        source: String(e.source),
        target: String(e.target),
        type: "prerequisite",
        selectable: false,
        focusable: false,
        updatable: false,
        data: {
          sourceName: nameById.get(e.source)?.name ?? "",
          targetName: nameById.get(e.target)?.name ?? "",
        },
      })),
    [data, nameById]
  );

  const highlight = useMemo(
    () => computeHighlight(model, data.edges, { selectedId, hoveredId, focusId }),
    [model, data.edges, selectedId, hoveredId, focusId]
  );

  const ui = useMemo<GraphUi>(
    () => ({
      nodeRoles: highlight.nodeRoles,
      edgeRoles: highlight.edgeRoles,
      pathStates: pathMode ? allPathStates : null,
      selectedId,
    }),
    [highlight, pathMode, allPathStates, selectedId]
  );

  // --- camera helpers ---------------------------------------------------------------
  const duration = useCallback((ms: number) => (prefersReducedMotion() ? 0 : ms), []);

  const fitAll = useCallback(
    () => fitView({ ...FIT_OPTIONS, duration: duration(450) }),
    [fitView, duration]
  );

  const enterFocus = useCallback(
    (id: number) => {
      setSelectedId(id);
      setFocusId(id);
      fitView({
        nodes: neighborhood(model, id).map((n) => ({ id: String(n) })),
        padding: 0.3,
        maxZoom: 1.25,
        duration: duration(450),
      });
    },
    [fitView, model, duration]
  );

  const exitFocus = useCallback(() => {
    setFocusId(null);
    fitAll();
  }, [fitAll]);

  const clearAll = useCallback(() => {
    setSelectedId(null);
    if (focusId !== null) exitFocus();
  }, [focusId, exitFocus]);

  const centerOn = useCallback(
    (id: number) => {
      const n = nodesRef.current.find((x) => x.id === String(id));
      if (!n) return;
      const zoom = Math.max(getZoom(), 0.8);
      // Below md the details panel is a bottom sheet covering roughly the
      // lower half, so aim the card at the upper quarter of the canvas.
      const narrow = typeof window !== "undefined" && window.innerWidth < 768;
      const shift = narrow ? ((canvasRef.current?.clientHeight ?? 0) * 0.25) / zoom : 0;
      setCenter(n.position.x + NODE_WIDTH / 2, n.position.y + NODE_HEIGHT / 2 + shift, {
        zoom,
        duration: duration(350),
      });
    },
    [setCenter, getZoom, duration]
  );

  // --- dragging (position only) ------------------------------------------------------
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((current) => {
        const tolerance = SNAP_SCREEN_PX / Math.max(getZoom(), 0.1);
        const adjusted = changes.map((change) => {
          if (change.type === "position" && change.dragging && change.position) {
            const others = current.map((n) => ({ id: Number(n.id), position: n.position }));
            return { ...change, position: snapToNeighbors(Number(change.id), change.position, others, tolerance) };
          }
          return change;
        });
        return applyNodeChanges(adjusted, current);
      });
    },
    [getZoom]
  );

  const onNodeDragStart = useCallback(() => {
    draggingRef.current = true;
    movedRef.current = false;
  }, []);

  const onNodeDrag = useCallback(() => {
    movedRef.current = true;
  }, []);

  const onNodeDragStop = useCallback(() => {
    draggingRef.current = false;
    if (!movedRef.current) return;
    // Swallow the click that some browsers still emit right after a drag.
    suppressClickRef.current = true;
    window.setTimeout(() => (suppressClickRef.current = false), 60);
    // Persist once, at the end of the drag — never per pixel.
    const positions: Positions = {};
    for (const n of nodesRef.current) positions[Number(n.id)] = n.position;
    saveLayout(courseName, positions);
    setCustomized(true);
  }, [courseName]);

  const resetLayout = useCallback(() => {
    clearLayout(courseName);
    const defaults = computeDefaultPositions(data.nodes, data.edges);
    setNodes((current) => current.map((n) => ({ ...n, position: defaults[Number(n.id)] ?? n.position })));
    setCustomized(false);
    window.requestAnimationFrame(() => fitAll());
  }, [courseName, data, fitAll]);

  // --- selection ----------------------------------------------------------------------
  const onNodeClick = useCallback(
    (_: unknown, node: Node) => {
      if (suppressClickRef.current) return;
      setSelectedId(Number(node.id));
      if (window.innerWidth < 768) centerOn(Number(node.id));
    },
    [centerOn]
  );

  const onNodeDoubleClick = useCallback(
    (_: unknown, node: Node) => {
      if (suppressClickRef.current) return;
      enterFocus(Number(node.id));
    },
    [enterFocus]
  );

  const selectFromPanel = useCallback(
    (id: number) => {
      if (focusId !== null) enterFocus(id);
      else {
        setSelectedId(id);
        centerOn(id);
      }
    },
    [focusId, enterFocus, centerOn]
  );

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      const el = e.target as HTMLElement;
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") return;
      if (e.key === "Escape") clearAll();
      else if ((e.key === "f" || e.key === "F") && !e.metaKey && !e.ctrlKey && !e.altKey) fitAll();
    },
    [clearAll, fitAll]
  );

  // --- panel data ------------------------------------------------------------------------
  const selected = selectedId !== null ? nameById.get(selectedId) : undefined;
  const toPanel = (id: number): PanelTopic => {
    const n = nameById.get(id)!;
    return { id: n.id, name: n.name, status: n.status, score: n.score };
  };

  const legendPath = pathMode;

  return (
    <div className="flex h-full min-h-[440px] flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-[rgba(var(--ink-rgb),0.10)] px-4 py-2.5 text-xs md:px-6">
        <ul className="flex flex-wrap items-center gap-x-3.5 gap-y-1 text-[var(--ink)]/70" aria-label="Legend">
          {legendPath
            ? PATH_ORDER.map((p) => (
                <li key={p} className="flex items-center gap-1.5">
                  <PathIcon state={p} />
                  {PATH_LABEL[p]}
                </li>
              ))
            : LEGEND_ORDER.map((s) => (
                <li key={s} className="flex items-center gap-1.5">
                  <StatusIcon status={s} />
                  {STATUS_LABEL[s]}
                </li>
              ))}
        </ul>

        <div className="ml-auto flex items-center gap-1.5">
          <span className="mr-2 hidden text-[11px] text-[var(--ink)]/45 xl:inline">
            Drag cards · scroll to zoom · double-click to focus
          </span>
          {focusId !== null && (
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={exitFocus}>
              Show all
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            aria-pressed={pathMode}
            onClick={() => setPathMode((v) => !v)}
            className={`h-7 rounded-full px-3 text-xs ${
              pathMode
                ? "border-[var(--accent)] bg-[rgba(var(--accent-rgb),0.12)] text-[var(--accent-hover)]"
                : "text-[var(--ink)]/70"
            }`}
          >
            Learning path
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs text-[var(--ink)]/60"
            onClick={resetLayout}
            disabled={!customized}
            title={customized ? "Restore the default arrangement" : "Layout is already the default"}
          >
            Reset layout
          </Button>
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col md:flex-row">
      <div
        ref={canvasRef}
        className="relative min-h-0 min-w-0 flex-1 select-none outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[rgba(var(--accent-rgb),0.45)]"
        tabIndex={0}
        onKeyDown={onKeyDown}
        aria-label="Prerequisite graph. Drag cards to rearrange, scroll to zoom, press F to fit and Escape to clear selection."
      >
        <GraphMarkers />
        <GraphUiContext.Provider value={ui}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            onNodeDragStart={onNodeDragStart}
            onNodeDrag={onNodeDrag}
            onNodeDragStop={onNodeDragStop}
            onNodeMouseEnter={(_, n) => {
              if (!draggingRef.current) setHoveredId(Number(n.id));
            }}
            onNodeMouseLeave={() => {
              if (!draggingRef.current) setHoveredId(null);
            }}
            onPaneClick={() => setSelectedId(null)}
            nodesDraggable
            nodesConnectable={false}
            edgesUpdatable={false}
            edgesFocusable={false}
            elementsSelectable={false}
            selectNodesOnDrag={false}
            deleteKeyCode={null}
            selectionKeyCode={null}
            multiSelectionKeyCode={null}
            nodeDragThreshold={3}
            zoomOnDoubleClick={false}
            minZoom={0.25}
            maxZoom={2}
            fitView
            fitViewOptions={FIT_OPTIONS}
          >
            <Background color="rgba(var(--ink-rgb), 0.14)" gap={20} />
            <Controls showInteractive={false} />
            {nodes.length >= MINIMAP_THRESHOLD && (
              <MiniMap
                pannable
                zoomable
                className="!hidden md:!block"
                nodeColor={(n) => STATUS_COLOR[normalizeStatus((n.data as TopicNodeData).status)]}
                nodeStrokeWidth={0}
                maskColor="rgba(var(--ink-rgb), 0.08)"
                style={{ background: "var(--bg-surface)", border: "1px solid rgba(var(--ink-rgb), 0.12)", borderRadius: 8 }}
              />
            )}
          </ReactFlow>
        </GraphUiContext.Provider>
      </div>

        {selected && selectedId !== null && (
          <TopicDetailPanel
            topic={toPanel(selectedId)}
            pathState={allPathStates.get(selectedId) ?? "later"}
            prerequisites={(model.prereqs.get(selectedId) ?? []).map(toPanel)}
            unlocks={(model.dependents.get(selectedId) ?? []).map(toPanel)}
            totalBefore={ancestors(model, selectedId).size}
            totalAfter={descendants(model, selectedId).size}
            isFocused={focusId === selectedId}
            onClose={clearAll}
            onSelectTopic={selectFromPanel}
            onFocus={() => enterFocus(selectedId)}
            onShowAll={exitFocus}
            onAsk={() => onOpenTopic?.(selectedId, "chat")}
            onQuiz={() => onOpenTopic?.(selectedId, "quiz")}
          />
        )}
      </div>
    </div>
  );
}
