// Plain-Node tests for the prerequisite-editing helpers, in the same style as
// quiz.test.ts (only Node's built-in `assert`). To run ad hoc:
//   sed 's#"./graph-edit"#"./graph-edit.ts"#' lib/graph-edit.test.ts > lib/_run.test.ts \
//     && node --experimental-strip-types lib/_run.test.ts; rm lib/_run.test.ts

import assert from "node:assert/strict";

import { candidateLabel, candidatePrerequisites, editErrorText } from "./graph-edit";

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`ok - ${name}`);
}

const t = (id: number, name: string, module_name = "M1") => ({ id, name, module_name });
const all = [t(1, "Sets"), t(2, "Functions"), t(3, "Relations"), t(4, "Graphs", "M2")];
const ids = (list: { id: number }[]) => list.map((x) => x.id);

test("every other topic is a candidate when nothing is linked", () => {
  assert.deepEqual(ids(candidatePrerequisites(all, 3, [], new Set())), [1, 2, 4]);
});

test("the topic itself is never offered", () => {
  assert.ok(!ids(candidatePrerequisites(all, 3, [], new Set())).includes(3));
});

test("topics already required directly are not offered again", () => {
  assert.deepEqual(ids(candidatePrerequisites(all, 3, [1, 2], new Set())), [4]);
});

test("topics that already depend on it are not offered: they would close a loop", () => {
  // Graphs builds on Relations (selected): Relations may not require Graphs.
  assert.deepEqual(ids(candidatePrerequisites(all, 3, [], new Set([4]))), [1, 2]);
});

test("direct prerequisites, dependents and itself can all be excluded at once", () => {
  assert.deepEqual(ids(candidatePrerequisites(all, 2, [1], new Set([3, 4]))), []);
});

test("the order of the topics is kept (reading order)", () => {
  assert.deepEqual(ids(candidatePrerequisites([t(9, "Z"), t(5, "A"), t(7, "M")], 1, [], new Set())), [9, 5, 7]);
});

test("no topics, no candidates", () => {
  assert.deepEqual(candidatePrerequisites([], 1, [], new Set()), []);
});

test("a candidate reads as its name and module", () => {
  assert.equal(candidateLabel(t(1, "Sets", "Foundations")), "Sets · Foundations");
  assert.equal(candidateLabel(t(1, "Sets", "")), "Sets");
});

test("a failed edit shows the server's message, or a fallback", () => {
  assert.equal(editErrorText(new Error("That would create a loop (A → B → A)."), "x"), "That would create a loop (A → B → A).");
  assert.equal(editErrorText(new Error(""), "Couldn't add it."), "Couldn't add it.");
  assert.equal(editErrorText("boom", "Couldn't add it."), "Couldn't add it.");
  assert.equal(editErrorText(undefined, "Couldn't add it."), "Couldn't add it.");
});

console.log(`\n${passed} passed`);
