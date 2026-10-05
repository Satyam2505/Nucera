// Plain-Node tests for the API error helpers, in the same style as
// graph.test.ts (only Node's built-in `assert`). To run ad hoc, Node's ESM
// loader needs the explicit extension on the relative import:
//   sed 's#"./api-errors"#"./api-errors.ts"#' lib/api-errors.test.ts > lib/_run.test.ts \
//     && node --experimental-strip-types lib/_run.test.ts; rm lib/_run.test.ts

import assert from "node:assert/strict";

import { errorDetail, isSessionExpiry } from "./api-errors";

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`ok - ${name}`);
}

test("a string detail is shown as-is", () => {
  assert.equal(errorDetail(409, JSON.stringify({ detail: "Add study material first" })), "Add study material first");
  assert.equal(errorDetail(401, JSON.stringify({ detail: "  Incorrect email or password " })), "Incorrect email or password");
});

test("validation errors list the field and message", () => {
  const body = JSON.stringify({
    detail: [
      { loc: ["body", "name"], msg: "String should have at least 1 character", type: "string_too_short" },
      { loc: ["body", "module_id"], msg: "Field required", type: "missing" },
    ],
  });
  assert.equal(
    errorDetail(422, body),
    "name: String should have at least 1 character; module_id: Field required"
  );
});

test("a validation item without a field name still shows its message", () => {
  assert.equal(errorDetail(422, JSON.stringify({ detail: [{ msg: "Bad input" }] })), "Bad input");
});

test("plain-text bodies are shown but capped", () => {
  assert.equal(errorDetail(502, "Bad gateway"), "Bad gateway");
  assert.equal(errorDetail(500, "x".repeat(500)).length, 200);
});

test("an HTML error page falls back to the generic line, not markup", () => {
  assert.equal(errorDetail(502, "<html><body>Bad Gateway</body></html>"), "Request failed (502)");
  assert.equal(errorDetail(503, "  \n<!DOCTYPE html><title>x</title>"), "Request failed (503)");
});

test("JSON without a usable detail falls back to a generic line, never a blob", () => {
  assert.equal(errorDetail(500, JSON.stringify({ error: "boom" })), "Request failed (500)");
  assert.equal(errorDetail(500, JSON.stringify({ detail: "" })), "Request failed (500)");
  assert.equal(errorDetail(500, JSON.stringify({ detail: [] })), "Request failed (500)");
  assert.equal(errorDetail(500, "[1,2]"), "Request failed (500)");
  assert.equal(errorDetail(500, ""), "Request failed (500)");
  assert.equal(errorDetail(404, "null"), "Request failed (404)");
});

test("only a 401 that carried a token ends the session", () => {
  assert.equal(isSessionExpiry(401, true), true);
  assert.equal(isSessionExpiry(401, false), false); // wrong password / logged out
  assert.equal(isSessionExpiry(403, true), false);
  assert.equal(isSessionExpiry(404, true), false);
  assert.equal(isSessionExpiry(500, true), false);
});

console.log(`\n${passed} passed`);
