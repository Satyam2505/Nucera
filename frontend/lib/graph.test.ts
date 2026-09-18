// Plain-Node tests for the pure graph modules (graph-model, graph-layout) —
// same approach as greeting.test.ts: only Node's built-in `assert`, no test
// framework. To run ad hoc, Node's ESM loader needs explicit extensions:
//   sed 's#"./graph-\([a-z]*\)"#"./graph-\1.ts"#' lib/graph.test.ts > lib/_run.test.ts \
//     && node --experimental-strip-types lib/_run.test.ts; rm lib/_run.test.ts

import assert from "node:assert/strict";

import {
  ancestors,
  buildModel,
  computeHighlight,
  computePathStates,
  descendants,
  edgeId,
  neighborhood,
} from "./graph-model";
import {
  clearLayout,
  computeDefaultPositions,
  loadLayout,
  saveLayout,
  snapToNeighbors,
  type StorageLike,
} from "./graph-layout";

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`ok - ${name}`);
}

function memoryStorage(): StorageLike & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

// Diamond + tail + a disconnected topic:
//   1 -> 2 -> 4 -> 5        6 (isolated)
//   1 -> 3 -> 4
const nodes = [
  { id: 1, status: "mastered" },
  { id: 2, status: "in_progress" },
  { id: 3, status: "unmastered" },
  { id: 4, status: "unmastered" },
  { id: 5, status: "unmastered" },
  { id: 6, status: "unmastered" },
];
const edges = [
  { source: 1, target: 2 },
  { source: 1, target: 3 },
  { source: 2, target: 4 },
  { source: 3, target: 4 },
  { source: 4, target: 5 },
];
const model = buildModel(nodes, edges);

// --- model ---------------------------------------------------------------
test("ancestors of a topic with multiple prerequisites", () =>
  assert.deepEqual([...ancestors(model, 4)].sort(), [1, 2, 3]));
test("descendants of a prerequisite that unlocks several topics", () =>
  assert.deepEqual([...descendants(model, 1)].sort(), [2, 3, 4, 5]));
test("disconnected topic has no ancestors or descendants", () => {
  assert.equal(ancestors(model, 6).size, 0);
  assert.equal(descendants(model, 6).size, 0);
});
test("edges pointing outside the node set are ignored", () => {
  const m = buildModel([{ id: 1, status: "unmastered" }], [{ source: 1, target: 99 }]);
  assert.equal(descendants(m, 1).size, 0);
});
test("cycles do not hang traversal", () => {
  const m = buildModel(
    [
      { id: 1, status: "unmastered" },
      { id: 2, status: "unmastered" },
    ],
    [
      { source: 1, target: 2 },
      { source: 2, target: 1 },
    ]
  );
  assert.deepEqual([...descendants(m, 1)], [2]);
});
test("neighborhood is the topic plus direct links only", () =>
  assert.deepEqual(neighborhood(model, 4).sort(), [2, 3, 4, 5]));

// --- learning path -----------------------------------------------------------
test("learning path states", () => {
  const p = computePathStates(model);
  assert.equal(p.get(1), "covered"); // mastered
  assert.equal(p.get(2), "next"); // in progress, prereq mastered
  assert.equal(p.get(3), "next"); // prereq mastered, nothing blocking
  assert.equal(p.get(4), "later"); // prereqs 2,3 not mastered
  assert.equal(p.get(5), "later");
  assert.equal(p.get(6), "next"); // no prerequisites at all
});
test("unmastered prerequisite of a started topic needs attention", () => {
  const m = buildModel(
    [
      { id: 1, status: "unmastered" },
      { id: 2, status: "in_progress" },
    ],
    [{ source: 1, target: 2 }]
  );
  assert.equal(computePathStates(m).get(1), "attention");
});
test("missed topics need attention", () => {
  const m = buildModel([{ id: 1, status: "missed" }], []);
  assert.equal(computePathStates(m).get(1), "attention");
});
test("unknown status strings are treated as not started", () => {
  const m = buildModel([{ id: 1, status: "weird" }], []);
  assert.equal(computePathStates(m).get(1), "next");
});

// --- highlighting -----------------------------------------------------------
test("no selection: everything neutral", () => {
  const h = computeHighlight(model, edges, { selectedId: null, hoveredId: null, focusId: null });
  assert.ok([...h.nodeRoles.values()].every((r) => r === "none"));
  assert.ok([...h.edgeRoles.values()].every((r) => r === "none"));
});
test("selection highlights the whole path before and after", () => {
  const h = computeHighlight(model, edges, { selectedId: 4, hoveredId: null, focusId: null });
  assert.equal(h.nodeRoles.get(4), "focus");
  assert.equal(h.nodeRoles.get(1), "prereq");
  assert.equal(h.nodeRoles.get(2), "prereq");
  assert.equal(h.nodeRoles.get(5), "dependent");
  assert.equal(h.nodeRoles.get(6), "muted");
  assert.equal(h.edgeRoles.get(edgeId(1, 2)), "prereq");
  assert.equal(h.edgeRoles.get(edgeId(2, 4)), "prereq");
  assert.equal(h.edgeRoles.get(edgeId(4, 5)), "dependent");
});
test("selecting a mid-path topic does not highlight its sibling branch", () => {
  const h = computeHighlight(model, edges, { selectedId: 2, hoveredId: null, focusId: null });
  assert.equal(h.nodeRoles.get(3), "muted");
  assert.equal(h.edgeRoles.get(edgeId(1, 3)), "muted");
  assert.equal(h.edgeRoles.get(edgeId(3, 4)), "muted");
  assert.equal(h.edgeRoles.get(edgeId(2, 4)), "dependent");
});
test("hover only: direct neighbors highlighted, rest dimmed", () => {
  const h = computeHighlight(model, edges, { selectedId: null, hoveredId: 4, focusId: null });
  assert.equal(h.nodeRoles.get(2), "prereq");
  assert.equal(h.nodeRoles.get(5), "dependent");
  assert.equal(h.nodeRoles.get(1), "dim");
  assert.equal(h.edgeRoles.get(edgeId(2, 4)), "hover");
  assert.equal(h.edgeRoles.get(edgeId(1, 2)), "dim");
});
test("hovering while selected boosts touching edges but keeps selection roles", () => {
  const h = computeHighlight(model, edges, { selectedId: 5, hoveredId: 6, focusId: null });
  assert.equal(h.nodeRoles.get(5), "focus");
  assert.equal(h.nodeRoles.get(6), "muted");
});
test("focus mode shows only the immediate neighborhood", () => {
  const h = computeHighlight(model, edges, { selectedId: null, hoveredId: null, focusId: 4 });
  assert.equal(h.nodeRoles.get(2), "prereq");
  assert.equal(h.nodeRoles.get(5), "dependent");
  assert.equal(h.nodeRoles.get(1), "faded");
  assert.equal(h.edgeRoles.get(edgeId(1, 2)), "faded");
  assert.equal(h.edgeRoles.get(edgeId(4, 5)), "dependent");
});
test("highlighting an unknown id degrades to neutral", () => {
  const h = computeHighlight(model, edges, { selectedId: 999, hoveredId: null, focusId: null });
  assert.ok([...h.nodeRoles.values()].every((r) => r === "none"));
});

// --- default layout -------------------------------------------------------------
test("default layout places prerequisites in earlier columns", () => {
  const pos = computeDefaultPositions(nodes, edges);
  assert.ok(pos[1].x < pos[2].x);
  assert.ok(pos[2].x < pos[4].x);
  assert.ok(pos[4].x < pos[5].x);
  assert.equal(pos[2].x, pos[3].x);
});
test("default layout gives every node a distinct spot", () => {
  const pos = computeDefaultPositions(nodes, edges);
  const spots = new Set(Object.values(pos).map((p) => `${p.x},${p.y}`));
  assert.equal(spots.size, nodes.length);
});
test("default layout handles 2-3 topics, none, and cycles", () => {
  assert.equal(Object.keys(computeDefaultPositions([], [])).length, 0);
  assert.equal(Object.keys(computeDefaultPositions([{ id: 1 }, { id: 2 }], [{ source: 1, target: 2 }])).length, 2);
  const cyc = computeDefaultPositions(
    [{ id: 1 }, { id: 2 }],
    [
      { source: 1, target: 2 },
      { source: 2, target: 1 },
    ]
  );
  assert.equal(Object.keys(cyc).length, 2);
});
test("default layout copes with 120 topics", () => {
  const many = Array.from({ length: 120 }, (_, i) => ({ id: i + 1 }));
  const chain = many.slice(1).map((n, i) => ({ source: i + 1, target: n.id }));
  assert.equal(Object.keys(computeDefaultPositions(many, chain)).length, 120);
});

// --- snapping ------------------------------------------------------------------
test("snaps to a neighbor's edge within tolerance, per axis", () => {
  const others = [{ id: 2, position: { x: 100, y: 200 } }];
  assert.deepEqual(snapToNeighbors(1, { x: 103, y: 500 }, others, 6), { x: 100, y: 500 });
  assert.deepEqual(snapToNeighbors(1, { x: 500, y: 197 }, others, 6), { x: 500, y: 200 });
});
test("does not snap beyond tolerance or to itself", () => {
  const others = [
    { id: 1, position: { x: 100, y: 100 } },
    { id: 2, position: { x: 300, y: 300 } },
  ];
  assert.deepEqual(snapToNeighbors(1, { x: 110, y: 110 }, others, 6), { x: 110, y: 110 });
});

// --- persistence ------------------------------------------------------------------
test("layout round-trips per course and courses are independent", () => {
  const s = memoryStorage();
  saveLayout("DBMS", { 1: { x: 10, y: 20 } }, s);
  saveLayout("DSA", { 1: { x: 99, y: 88 } }, s);
  assert.deepEqual(loadLayout("DBMS", s), { 1: { x: 10, y: 20 } });
  assert.deepEqual(loadLayout("DSA", s), { 1: { x: 99, y: 88 } });
  clearLayout("DBMS", s);
  assert.equal(loadLayout("DBMS", s), null);
  assert.deepEqual(loadLayout("DSA", s), { 1: { x: 99, y: 88 } });
});
test("corrupt or hostile stored layouts are ignored", () => {
  const s = memoryStorage();
  s.setItem("nucera:graph-layout:A", "not json");
  s.setItem("nucera:graph-layout:B", JSON.stringify({ 1: { x: "a", y: null }, 2: { x: Infinity, y: 0 } }));
  s.setItem("nucera:graph-layout:C", JSON.stringify([1, 2]));
  assert.equal(loadLayout("A", s), null);
  assert.equal(loadLayout("B", s), null);
  assert.equal(loadLayout("C", s), null);
});
test("missing storage never throws", () => {
  assert.equal(loadLayout("X", null), null);
  saveLayout("X", { 1: { x: 0, y: 0 } }, null);
  clearLayout("X", null);
});
test("storage that throws never breaks callers", () => {
  const bad: StorageLike = {
    getItem: () => {
      throw new Error("blocked");
    },
    setItem: () => {
      throw new Error("quota");
    },
    removeItem: () => {
      throw new Error("blocked");
    },
  };
  assert.equal(loadLayout("X", bad), null);
  saveLayout("X", { 1: { x: 0, y: 0 } }, bad);
  clearLayout("X", bad);
});

console.log(`\n${passed} passed`);
