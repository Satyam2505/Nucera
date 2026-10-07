// Plain-Node tests for the "Up next" helpers, in the same style as quiz.test.ts (only
// Node's built-in `assert`). To run ad hoc:
//   sed 's#"./next-steps"#"./next-steps.ts"#' lib/next-steps.test.ts > lib/_run.test.ts \
//     && node --experimental-strip-types lib/_run.test.ts; rm lib/_run.test.ts

import assert from "node:assert/strict";

import { fadingNote, stepAction, stepBadge } from "./next-steps";

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`ok - ${name}`);
}

test("a review is called out and anything else is just up next", () => {
  assert.equal(stepBadge({ kind: "review" }), "Review");
  assert.equal(stepBadge({ kind: "ready" }), "Up next");
});

test("reviewing a faded topic goes to its quiz; a ready topic goes to the tutor", () => {
  assert.deepEqual(stepAction({ kind: "review" }), { view: "quiz", label: "Review with a quiz" });
  assert.deepEqual(stepAction({ kind: "ready" }), { view: "chat", label: "Start with the tutor" });
});

test("only a topic that is due gets a note", () => {
  assert.equal(fadingNote({ due_for_review: true }), "Due for review");
  assert.equal(fadingNote({ due_for_review: false }), null);
  assert.equal(fadingNote(undefined), null);
});

console.log(`\n${passed} passed`);
