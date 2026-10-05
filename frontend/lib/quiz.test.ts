// Plain-Node tests for the quiz helpers, in the same style as graph.test.ts
// (only Node's built-in `assert`). To run ad hoc, Node's ESM loader needs the
// explicit extension on the relative import:
//   sed 's#"./quiz"#"./quiz.ts"#' lib/quiz.test.ts > lib/_run.test.ts \
//     && node --experimental-strip-types lib/_run.test.ts; rm lib/_run.test.ts

import assert from "node:assert/strict";

import {
  allAnswered,
  answerPayload,
  answeredCount,
  citationLabel,
  formatDelta,
  RESULT_LABEL,
  resultMark,
} from "./quiz";

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`ok - ${name}`);
}

const questions = [{ id: 11 }, { id: 12 }, { id: 13 }];

test("citations show the page when there is one", () => {
  assert.equal(citationLabel({ source: "Notes A", page: 3 }), "Notes A, p. 3");
  assert.equal(citationLabel({ source: "Notes B", page: null }), "Notes B");
});

test("submitting needs every question answered", () => {
  assert.equal(allAnswered(questions, {}), false);
  assert.equal(allAnswered(questions, { 11: "A", 12: "B" }), false);
  assert.equal(allAnswered(questions, { 11: "A", 12: "B", 13: "D" }), true);
  assert.equal(answeredCount(questions, { 11: "A", 13: "C" }), 2);
});

test("an empty quiz can never be submitted", () => {
  assert.equal(allAnswered([], {}), false);
});

test("answers left over from another quiz don't count", () => {
  assert.equal(allAnswered(questions, { 99: "A", 98: "B", 97: "C" }), false);
  assert.deepEqual(answerPayload(questions, { 99: "A", 12: "C" }), [{ question_id: 12, selected_option: "C" }]);
});

test("the payload lists answers in question order", () => {
  assert.deepEqual(answerPayload(questions, { 13: "D", 11: "A", 12: "B" }), [
    { question_id: 11, selected_option: "A" },
    { question_id: 12, selected_option: "B" },
    { question_id: 13, selected_option: "D" },
  ]);
});

test("mastery changes read as plain text", () => {
  assert.equal(formatDelta(10), "+10");
  assert.equal(formatDelta(-4), "-4");
  assert.equal(formatDelta(0), "no change");
});

test("each result is marked correct, incorrect or not answered, with a word for each", () => {
  assert.equal(resultMark({ chosen: "A", is_correct: true }), "correct");
  assert.equal(resultMark({ chosen: "B", is_correct: false }), "incorrect");
  assert.equal(resultMark({ chosen: null, is_correct: false }), "unanswered");
  assert.deepEqual(
    ["correct", "incorrect", "unanswered"].map((m) => RESULT_LABEL[m as keyof typeof RESULT_LABEL]),
    ["Correct", "Incorrect", "Not answered"]
  );
});

console.log(`\n${passed} passed`);
