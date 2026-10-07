"use client";

import { Check } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import ReactFlow, {
  applyNodeChanges,
  Background,
  MiniMap,
  Panel,
  ReactFlowProvider,
  useReactFlow,
  useStoreApi,
  type Edge,
  type Node,
  type NodeChange,
  type Viewport,
} from "reactflow";
import "reactflow/dist/style.css";

import { Button } from "@/components/ui/button";
import { api, type GraphData } from "@/lib/api";
import { useAppState } from "@/lib/AppStateContext";
import { candidatePrerequisites } from "@/lib/graph-edit";
import {
  clearLayout,
  clearViewport,
  computeDefaultPositions,
  loadLayout,
  loadViewport,
  NODE_HEIGHT,
  NODE_WIDTH,
  saveLayout,
  saveViewport,
  type Positions,
  type SavedViewport,
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
import { groupNodesByModule, moduleTintIndex, tintFor, visibleNodes } from "@/lib/graph-modules";
import { anyRectVisible, clampZoom, rectFits, revealDelta, unionRects, type Rect } from "@/lib/graph-viewport";
import { STATUS_COLOR, STATUS_LABEL, type MasteryStatusKey } from "@/lib/status-colors";

import { GraphUiContext, type GraphUi } from "./graph/graph-context";
import GraphTopicList, { type TopicListItem } from "./graph/GraphTopicList";
import GraphZoomControls from "./graph/GraphZoomControls";
import { normalizeStatus, PATH_LABEL, PathIcon, StatusIcon } from "./graph/graph-icons";
import PrerequisiteEdge, { GraphMarkers, type PrerequisiteEdgeData } from "./graph/PrerequisiteEdge";
import TopicDetailPanel, { type PanelTopic } from "./graph/TopicDetailPanel";
import TopicNode, { type TopicNodeData } from "./graph/TopicNode";

// Defined once at module scope so React Flow sees stable type objects.
const nodeTypes = { topic: TopicNode };
const edgeTypes = { prerequisite: PrerequisiteEdge };

const LEGEND_ORDER: MasteryStatusKey[] = ["mastered", "in_progress", "unmastered", "missed"];
const PATH_ORDER: PathState[] = ["covered", "attention", "next", "later"];

const MINIMAP_THRESHOLD = 12;

// Zoom bounds. At 25% the whole structure of a large course (60+ topics)
// still fits the canvas; at 175% a 190px card is ~330px wide — comfortably
// readable without becoming absurd.
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 1.75;
const ZOOM_STEP = 0.15;
const FIT_OPTIONS = { padding: 0.08, maxZoom: 1.1 } as const;
// One duration for every programmatic camera move (fit, focus, reset, zoom
// buttons, revealing a selected topic) so the graph feels consistent.
const ANIM_MS = 320;
const REVEAL_MARGIN = 24;

export type GraphOpenView = "chat" | "quiz";

// What a programmatic camera move means for persistence:
//  - "default":   back to the default (fitted) view — forget any saved camera
//  - "persist":   a deliberate zoom worth restoring after a refresh
//  - "transient": a helper move (focus, keeping a topic visible) — not saved
// React Flow only reports moves the user makes (drag-pan, pinch) through
// onMoveEnd; programmatic ones (fitView, zoomTo, setViewport) never do, so
// we settle those ourselves once their animation has finished.
type MoveIntent = "default" | "persist" | "transient";

interface Props {
  courseId: number;
  onOpenTopic?: (topicId: number, view: GraphOpenView) => void;
}

export default function GraphView({ courseId, onOpenTopic }: Props) {
  const { graph } = useAppState();

  const data = useMemo<GraphData | null>(() => {
    if (!graph) return null;
    const nodes = graph.nodes.filter((n) => n.course_id === courseId);
    const ids = new Set(nodes.map((n) => n.id));
    const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return { nodes, edges };
  }, [graph, courseId]);

  if (!data) return <p className="p-6 text-sm text-stone-500 dark:text-stone-400">Loading graph...</p>;
  if (data.nodes.length === 0) {
    return <p className="p-6 text-sm text-stone-500 dark:text-stone-400">No topics in this course yet.</p>;
  }

  // Keyed by course so each course gets its own canvas state and layout.
  return (
    <ReactFlowProvider key={courseId}>
      <GraphCanvas courseId={courseId} data={data} onOpenTopic={onOpenTopic} />
    </ReactFlowProvider>
  );
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function nodeRect(n: Node, vp: Viewport): Rect {
  const left = n.position.x * vp.zoom + vp.x;
  const top = n.position.y * vp.zoom + vp.y;
  return { left, top, right: left + NODE_WIDTH * vp.zoom, bottom: top + NODE_HEIGHT * vp.zoom };
}

function toNodes(
  data: GraphData,
  positions: Positions,
  tintIndex: Map<number, number>,
  hiddenModules: ReadonlySet<number>,
  previous?: Node<TopicNodeData>[]
): Node<TopicNodeData>[] {
  const old = new Map((previous ?? []).map((n) => [n.id, n]));
  return data.nodes.map((n) => {
    const id = String(n.id);
    const moduleIndex = tintIndex.get(n.module_id) ?? 0;
    const nodeData: TopicNodeData = {
      topicId: n.id,
      name: n.name,
      status: n.status,
      score: n.score,
      moduleNumber: moduleIndex + 1,
      moduleName: n.module_name,
      tint: tintFor(moduleIndex),
    };
    const hidden = hiddenModules.has(n.module_id);
    const existing = old.get(id);
    // Existing nodes keep their current (possibly user-dragged) position and
    // measured size; only their academic display data refreshes.
    if (existing) return { ...existing, data: nodeData, hidden };
    return { id, type: "topic", position: positions[n.id] ?? { x: 0, y: 0 }, data: nodeData, hidden };
  });
}

function GraphCanvas({
  courseId,
  data,
  onOpenTopic,
}: {
  courseId: number;
  data: GraphData;
  onOpenTopic?: Props["onOpenTopic"];
}) {
  const flow = useReactFlow();
  const { fitView, setViewport, getViewport } = flow;
  // React Flow hands out placeholder helpers (fitView() === false) until its
  // viewport is initialized, so anything running from a stale closure must
  // read the latest instance through this ref.
  const flowRef = useRef(flow);
  flowRef.current = flow;
  const storeApi = useStoreApi();

  // --- modules (visual grouping + filter; never changes academic data) -------
  const moduleGroups = useMemo(() => groupNodesByModule(data.nodes), [data]);
  const tintIndex = useMemo(() => moduleTintIndex(moduleGroups), [moduleGroups]);
  const [hiddenModules, setHiddenModules] = useState<ReadonlySet<number>>(() => new Set());

  // --- visual state (separate from academic data) ---------------------------
  const [nodes, setNodes] = useState<Node<TopicNodeData>[]>(() => {
    const saved = loadLayout(courseId);
    const defaults = computeDefaultPositions(data.nodes, data.edges);
    const merged: Positions = {};
    for (const n of data.nodes) merged[n.id] = saved?.[n.id] ?? defaults[n.id];
    return toNodes(data, merged, moduleTintIndex(groupNodesByModule(data.nodes)), new Set());
  });
  const [initialViewport] = useState<SavedViewport | null>(() => {
    const saved = loadViewport(courseId);
    return saved ? { ...saved, zoom: clampZoom(saved.zoom, MIN_ZOOM, MAX_ZOOM) } : null;
  });
  const [customized, setCustomized] = useState(() => loadLayout(courseId) !== null);
  const [viewportSaved, setViewportSaved] = useState(initialViewport !== null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const [focusId, setFocusId] = useState<number | null>(null);
  const [pathMode, setPathMode] = useState(false);

  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const canvasRef = useRef<HTMLDivElement>(null);
  const mapSectionRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const movedRef = useRef(false);
  const suppressClickRef = useRef(false);
  const settleTimerRef = useRef<number | undefined>(undefined);

  // Academic data refreshes (e.g. after a quiz) update each card's mastery
  // display but never its position; hiding a module only flips `hidden`, so
  // its cards keep their places when it is shown again.
  useEffect(() => {
    setNodes((prev) => {
      const saved = loadLayout(courseId);
      const defaults = computeDefaultPositions(data.nodes, data.edges);
      const positions: Positions = {};
      for (const n of data.nodes) positions[n.id] = saved?.[n.id] ?? defaults[n.id];
      return toNodes(data, positions, tintIndex, hiddenModules, prev);
    });
  }, [data, courseId, tintIndex, hiddenModules]);

  // --- academic-derived, read-only ----------------------------------------------
  const model = useMemo(() => buildModel(data.nodes, data.edges), [data]);
  const { refresh } = useAppState();
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
        hidden:
          hiddenModules.has(nameById.get(e.source)?.module_id ?? -1) ||
          hiddenModules.has(nameById.get(e.target)?.module_id ?? -1),
        data: {
          sourceName: nameById.get(e.source)?.name ?? "",
          targetName: nameById.get(e.target)?.name ?? "",
        },
      })),
    [data, nameById, hiddenModules]
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

  // --- camera -----------------------------------------------------------------------
  const duration = useCallback((ms: number) => (prefersReducedMotion() ? 0 : ms), []);

  // Runs `fn` once React Flow's stored canvas size matches the real element.
  // Opening/closing the details panel resizes the canvas, and a fit computed
  // against the stale size would leave the graph too small or off-center.
  const afterLayout = useCallback(
    (fn: () => void) => {
      let frame = 0;
      let tries = 0;
      const check = () => {
        const el = canvasRef.current;
        const { width, height } = storeApi.getState();
        const settled = !el || (Math.abs(width - el.clientWidth) < 1 && Math.abs(height - el.clientHeight) < 1);
        if (settled || ++tries > 12) fn();
        else frame = requestAnimationFrame(check);
      };
      frame = requestAnimationFrame(check);
      return () => cancelAnimationFrame(frame);
    },
    [storeApi]
  );

  // Called right after a programmatic camera command. When its animation has
  // finished, save the resulting camera ("persist"), forget it ("default"),
  // or ignore it ("transient"). A newer command or a user drag supersedes a
  // pending one, so rapid zoom clicks save only the final camera.
  const commitView = useCallback(
    (intent: MoveIntent, ms: number) => {
      window.clearTimeout(settleTimerRef.current);
      if (intent === "transient") return;
      settleTimerRef.current = window.setTimeout(() => {
        if (intent === "default") {
          clearViewport(courseId);
          setViewportSaved(false);
        } else {
          saveViewport(courseId, getViewport());
          setViewportSaved(true);
        }
      }, ms + 80);
    },
    [courseId, getViewport]
  );

  useEffect(() => () => window.clearTimeout(settleTimerRef.current), []);

  const fitAll = useCallback(() => {
    afterLayout(() => {
      fitView({ ...FIT_OPTIONS, duration: duration(ANIM_MS) });
      commitView("default", duration(ANIM_MS));
    });
  }, [fitView, duration, commitView, afterLayout]);

  const enterFocus = useCallback(
    (id: number) => {
      setSelectedId(id);
      setFocusId(id);
      // Wait for the details panel to mount (it narrows the canvas) so the
      // neighborhood is centered in the space that's actually left.
      afterLayout(() => {
        commitView("transient", 0);
        fitView({
          nodes: neighborhood(model, id).map((n) => ({ id: String(n) })),
          padding: 0.3,
          maxZoom: 1.25,
          duration: duration(ANIM_MS),
        });
      });
    },
    [fitView, model, duration, commitView, afterLayout]
  );

  const exitFocus = useCallback(() => {
    setFocusId(null);
    fitAll();
  }, [fitAll]);

  const clearAll = useCallback(() => {
    setSelectedId(null);
    if (focusId !== null) exitFocus();
  }, [focusId, exitFocus]);

  // Keep a newly selected topic (and, when it fits, its direct neighbors)
  // in view when the details panel narrows the canvas or a topic is picked
  // from the panel's lists. Moves the camera only — never a topic.
  const revealSelected = useCallback(
    (id: number) => {
      const el = canvasRef.current;
      if (!el) return;
      const vp = getViewport();
      const visible: Rect = { left: 0, top: 0, right: el.clientWidth, bottom: el.clientHeight };
      // Below md the details panel is a bottom sheet overlaying the canvas.
      const sheet = window.innerWidth < 768 ? el.parentElement?.querySelector("aside") : null;
      if (sheet) {
        const sheetTop = sheet.getBoundingClientRect().top - el.getBoundingClientRect().top;
        visible.bottom = Math.max(0, Math.min(visible.bottom, sheetTop));
      }
      const byId = new Map(nodesRef.current.map((n) => [n.id, n]));
      const self = byId.get(String(id));
      if (!self) return;
      const selfRect = nodeRect(self, vp);
      const hood = neighborhood(model, id)
        .map((n) => byId.get(String(n)))
        .filter((n): n is Node<TopicNodeData> => n !== undefined)
        .map((n) => nodeRect(n, vp));
      const hoodRect = hood.length ? unionRects(hood) : selfRect;
      const target = rectFits(hoodRect, visible, REVEAL_MARGIN) ? hoodRect : selfRect;
      const { dx, dy } = revealDelta(target, visible, REVEAL_MARGIN);
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      commitView("transient", 0);
      setViewport({ x: vp.x + dx, y: vp.y + dy, zoom: vp.zoom }, { duration: duration(ANIM_MS) });
    },
    [getViewport, setViewport, model, duration, commitView]
  );

  useEffect(() => {
    if (selectedId === null || focusId !== null) return;
    return afterLayout(() => revealSelected(selectedId));
  }, [selectedId, focusId, revealSelected, afterLayout]);

  // The user finished a drag-pan or pinch: save the camera right away
  // (and drop any pending programmatic save — the user took over).
  const onMoveEnd = useCallback(
    (_event: unknown, viewport: Viewport) => {
      window.clearTimeout(settleTimerRef.current);
      saveViewport(courseId, viewport);
      setViewportSaved(true);
    },
    [courseId]
  );

  // A saved camera can outlive the layout it was saved for (topics moved or
  // removed). If it would show none of the topics, discard it and fit.
  useEffect(() => {
    if (!initialViewport) return;
    const el = canvasRef.current;
    if (!el) return;
    const visible: Rect = { left: 0, top: 0, right: el.clientWidth, bottom: el.clientHeight };
    const vp: Viewport = initialViewport;
    if (anyRectVisible(nodesRef.current.map((n) => nodeRect(n, vp)), visible)) return;
    clearViewport(courseId);
    setViewportSaved(false);
    let tries = 0;
    let frame = 0;
    const attempt = () => {
      // fitView returns false until React Flow has measured the nodes.
      if (flowRef.current.fitView({ ...FIT_OPTIONS, duration: 0 }) || ++tries > 30) return;
      frame = requestAnimationFrame(attempt);
    };
    frame = requestAnimationFrame(attempt);
    return () => cancelAnimationFrame(frame);
    // Mount-only: validates the camera restored at startup.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- dragging (position only, completely free-form) ---------------------------------
  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);

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
    saveLayout(courseId, positions);
    setCustomized(true);
  }, [courseId]);

  // Reset everything visual: node positions, saved camera and zoom.
  const resetLayout = useCallback(() => {
    clearLayout(courseId);
    clearViewport(courseId);
    setCustomized(false);
    setViewportSaved(false);
    setFocusId(null);
    const defaults = computeDefaultPositions(data.nodes, data.edges);
    setNodes((current) => current.map((n) => ({ ...n, position: defaults[Number(n.id)] ?? n.position })));
    fitAll();
  }, [courseId, data, fitAll]);

  // --- selection ----------------------------------------------------------------------
  const onNodeClick = useCallback((_: unknown, node: Node) => {
    if (suppressClickRef.current) return;
    setSelectedId(Number(node.id));
  }, []);

  const onNodeDoubleClick = useCallback(
    (_: unknown, node: Node) => {
      if (suppressClickRef.current) return;
      enterFocus(Number(node.id));
    },
    [enterFocus]
  );

  // Double-clicking empty canvas returns to the full graph.
  const onCanvasDoubleClick = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (!(e.target as HTMLElement).classList.contains("react-flow__pane")) return;
      if (focusId !== null) exitFocus();
      else fitAll();
    },
    [focusId, exitFocus, fitAll]
  );

  const selectFromPanel = useCallback(
    (id: number) => {
      if (focusId !== null) enterFocus(id);
      else setSelectedId(id); // the reveal effect brings it into view
    },
    [focusId, enterFocus]
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

  // Editing the selected topic's prerequisites. The picker only offers topics that
  // can't make a loop (the server checks again); after a change the whole graph is
  // reloaded, so the edges, the learning path and the tutor's gaps all agree.
  const prerequisiteCandidates = useMemo(
    () =>
      selectedId === null
        ? []
        : candidatePrerequisites(
            data.nodes.map((n) => ({ id: n.id, name: n.name, module_name: n.module_name })),
            selectedId,
            model.prereqs.get(selectedId) ?? [],
            descendants(model, selectedId)
          ),
    [data.nodes, model, selectedId]
  );
  const addPrerequisite = useCallback(
    async (prerequisiteId: number) => {
      if (selectedId === null) return;
      await api.addPrerequisite(selectedId, prerequisiteId);
      await refresh();
    },
    [selectedId, refresh]
  );
  const removePrerequisite = useCallback(
    async (prerequisiteId: number) => {
      if (selectedId === null) return;
      await api.removePrerequisite(selectedId, prerequisiteId);
      await refresh();
    },
    [selectedId, refresh]
  );

  const topicList = useMemo<TopicListItem[]>(
    () =>
      visibleNodes(data.nodes, hiddenModules).map((n) => ({
        id: n.id,
        name: n.name,
        status: n.status,
        score: n.score,
        path: allPathStates.get(n.id) ?? "later",
        moduleName: n.module_name,
      })),
    [data, allPathStates, hiddenModules]
  );

  // Show or hide one module's cards. Anything selected or focused inside a
  // module that is being hidden is cleared so no panel points at a card that
  // is no longer on the canvas.
  const toggleModule = useCallback(
    (moduleId: number) => {
      const next = new Set(hiddenModules);
      if (next.has(moduleId)) {
        next.delete(moduleId);
      } else {
        next.add(moduleId);
        const owns = (topicId: number | null) =>
          topicId !== null && nameById.get(topicId)?.module_id === moduleId;
        if (owns(selectedId)) setSelectedId(null);
        if (owns(focusId)) setFocusId(null);
      }
      setHiddenModules(next);
    },
    [hiddenModules, nameById, selectedId, focusId]
  );

  // Refit the camera to whatever is visible after the filter changes. Comparing
  // against the last-seen set (rather than a "mounted" flag) keeps the
  // restored camera on first render, including under StrictMode's re-run.
  const fitAllRef = useRef(fitAll);
  fitAllRef.current = fitAll;
  const seenHiddenRef = useRef(hiddenModules);
  useEffect(() => {
    if (seenHiddenRef.current === hiddenModules) return;
    seenHiddenRef.current = hiddenModules;
    fitAllRef.current();
  }, [hiddenModules]);

  // Picking a topic from the list selects it on the map and scrolls the map
  // back into view.
  const selectFromList = useCallback(
    (id: number) => {
      selectFromPanel(id);
      mapSectionRef.current?.scrollIntoView({
        behavior: prefersReducedMotion() ? "auto" : "smooth",
        block: "start",
      });
    },
    [selectFromPanel]
  );

  const canReset = customized || viewportSaved;

  return (
    <div className="flex flex-col">
      {/* The map is a bounded block rather than the whole pane, so the page
          keeps normal scrolling; the topic list below is the rest of the page. */}
      <div ref={mapSectionRef} className="flex h-[clamp(440px,calc(100dvh-15rem),780px)] flex-col">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-[rgba(var(--ink-rgb),0.10)] px-4 py-2.5 text-xs md:px-6">
          <ul className="flex flex-wrap items-center gap-x-3.5 gap-y-1 text-[var(--ink)]/70" aria-label="Legend">
            {pathMode
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

          {moduleGroups.length > 1 && (
            <ul className="flex flex-wrap items-center gap-1.5" aria-label="Filter by module">
              {moduleGroups.map((group, index) => {
                const shown = !hiddenModules.has(group.id);
                return (
                  <li key={group.id}>
                    <button
                      type="button"
                      aria-pressed={shown}
                      onClick={() => toggleModule(group.id)}
                      title={shown ? `Hide ${group.name}` : `Show ${group.name}`}
                      className={`flex max-w-44 items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(var(--accent-rgb),0.45)] ${
                        shown
                          ? "border-[rgba(var(--ink-rgb),0.18)] text-[var(--ink)]"
                          : "border-dashed border-[rgba(var(--ink-rgb),0.18)] text-[var(--ink)]/45 line-through"
                      }`}
                    >
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ background: tintFor(index), opacity: shown ? 1 : 0.4 }}
                        aria-hidden
                      />
                      <span className="shrink-0 tabular-nums">{index + 1}.</span>
                      <span className="truncate">{group.name}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="ml-auto flex items-center gap-1.5">
            <span className="mr-2 hidden text-[11px] text-[var(--ink)]/45 xl:inline">
              Drag cards to move · double-click a topic to focus
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
              className={`h-7 rounded-lg px-3 text-xs ${
                pathMode
                  ? "border-[var(--accent)] bg-[rgba(var(--accent-rgb),0.12)] text-[var(--accent-hover)]"
                  : "text-[var(--ink)]/70"
              }`}
            >
              Learning path
            </Button>
            {canReset ? (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs text-[var(--ink)]/70"
                onClick={resetLayout}
              >
                Reset layout
              </Button>
            ) : (
              <span className="flex h-7 items-center gap-1 px-2 text-[11px] text-[var(--ink)]/45">
                <Check size={12} aria-hidden /> Default layout
              </span>
            )}
          </div>
        </div>

        <div className="relative flex min-h-0 flex-1 flex-col md:flex-row">
          <div
            ref={canvasRef}
            className="relative min-h-0 min-w-0 flex-1 select-none outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[rgba(var(--accent-rgb),0.45)]"
            tabIndex={0}
            onKeyDown={onKeyDown}
            onDoubleClick={onCanvasDoubleClick}
            aria-label="Knowledge graph. Drag cards to rearrange and drag the background to pan. Use the zoom controls to zoom, F to fit, and Escape to clear selection."
          >
            <GraphMarkers />
            <GraphUiContext.Provider value={ui}>
              {/*
                Interaction model:
                - plain mouse wheel / two-finger scroll: NOT handled here, so the
                  page scrolls. preventScrolling={false} stops React Flow from
                  calling preventDefault() on ordinary wheel events (its default
                  does, even with zoomOnScroll off, which trapped page scrolling).
                - trackpad pinch: browsers deliver it as a wheel event with
                  ctrlKey set; zoomOnPinch keeps handling exactly those events.
                - empty-canvas drag pans, card drag moves, zoom via the controls.
              */}
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
                onMoveEnd={onMoveEnd}
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
                panOnDrag
                panOnScroll={false}
                zoomOnScroll={false}
                zoomOnPinch
                zoomOnDoubleClick={false}
                preventScrolling={false}
                minZoom={MIN_ZOOM}
                maxZoom={MAX_ZOOM}
                defaultViewport={initialViewport ?? undefined}
                fitView={initialViewport === null}
                fitViewOptions={FIT_OPTIONS}
              >
                <Background color="rgba(var(--ink-rgb), 0.14)" gap={20} />
                <Panel position="bottom-left" className="!m-3">
                  <GraphZoomControls
                    min={MIN_ZOOM}
                    max={MAX_ZOOM}
                    step={ZOOM_STEP}
                    duration={duration(ANIM_MS)}
                    onFit={fitAll}
                    onZoomed={() => commitView("persist", duration(ANIM_MS))}
                  />
                </Panel>
                {nodes.length >= MINIMAP_THRESHOLD && (
                  <MiniMap
                    pannable
                    zoomable={false}
                    className="!hidden md:!block"
                    nodeColor={(n) => STATUS_COLOR[normalizeStatus((n.data as TopicNodeData).status)]}
                    nodeStrokeWidth={0}
                    maskColor="rgba(var(--ink-rgb), 0.08)"
                    style={{
                      background: "var(--bg-surface)",
                      border: "1px solid rgba(var(--ink-rgb), 0.12)",
                      borderRadius: 8,
                    }}
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
              candidates={prerequisiteCandidates}
              onAddPrerequisite={addPrerequisite}
              onRemovePrerequisite={removePrerequisite}
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
      <GraphTopicList topics={topicList} selectedId={selectedId} onSelect={selectFromList} />
    </div>
  );
}
