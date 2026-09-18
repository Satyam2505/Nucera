// Plain-Node smoke tests for the pure greeting utilities — this project has
// no frontend test runner yet, so these use only Node's built-in `assert`
// rather than pulling in Jest/Vitest for one small feature. To run ad hoc,
// Node's ESM loader (unlike this project's bundler) requires an explicit
// extension on relative imports — temporarily suffix the import below with
// ".ts" and run: node --experimental-strip-types lib/greeting.test.ts
// Written so a real runner (Jest/Vitest) could adopt these cases directly
// later — just swap `test(name, fn)` for `it(name, fn)`.

import assert from "node:assert/strict";

import { getFirstName, getGreeting, getTimePeriod } from "./greeting";

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`ok - ${name}`);
}

function at(hour: number, minute = 0): Date {
  const d = new Date(2026, 0, 1, hour, minute, 0);
  return d;
}

// --- getTimePeriod boundaries -------------------------------------------
test("04:00 is night", () => assert.equal(getTimePeriod(at(4, 0)), "night"));
test("07:00 is morning", () => assert.equal(getTimePeriod(at(7, 0)), "morning"));
test("11:59 is morning", () => assert.equal(getTimePeriod(at(11, 59)), "morning"));
test("12:00 is afternoon", () => assert.equal(getTimePeriod(at(12, 0)), "afternoon"));
test("16:59 is afternoon", () => assert.equal(getTimePeriod(at(16, 59)), "afternoon"));
test("17:00 is evening", () => assert.equal(getTimePeriod(at(17, 0)), "evening"));
test("21:59 is evening", () => assert.equal(getTimePeriod(at(21, 59)), "evening"));
test("22:00 is night", () => assert.equal(getTimePeriod(at(22, 0)), "night"));
test("23:59 is night", () => assert.equal(getTimePeriod(at(23, 59)), "night"));
test("00:00 is night", () => assert.equal(getTimePeriod(at(0, 0)), "night"));
test("04:59 is night", () => assert.equal(getTimePeriod(at(4, 59)), "night"));

// --- getFirstName ---------------------------------------------------------
test("first name: simple", () => assert.equal(getFirstName("Aditya"), "Aditya"));
test("first name: lowercase normalized", () => assert.equal(getFirstName("aditya"), "Aditya"));
test("first name: all caps normalized", () => assert.equal(getFirstName("ADITYA KUMAR"), "Aditya"));
test("first name: extra whitespace", () => assert.equal(getFirstName("  aditya   kumar  "), "Aditya"));
test("first name: missing", () => assert.equal(getFirstName(undefined), null));
test("first name: null", () => assert.equal(getFirstName(null), null));
test("first name: empty string", () => assert.equal(getFirstName(""), null));
test("first name: whitespace only", () => assert.equal(getFirstName("   "), null));

// --- getGreeting ------------------------------------------------------------
test("greeting: morning with name", () =>
  assert.equal(getGreeting(at(7, 0), "Aditya"), "Good morning, Aditya."));
test("greeting: morning without name", () =>
  assert.equal(getGreeting(at(7, 0)), "Good morning."));
test("greeting: afternoon with name", () =>
  assert.equal(getGreeting(at(14, 0), "Aditya"), "Good afternoon, Aditya."));
test("greeting: evening with name", () =>
  assert.equal(getGreeting(at(19, 0), "Aditya"), "Good evening, Aditya."));
test("greeting: night with name is a question", () =>
  assert.equal(getGreeting(at(23, 30), "Aditya"), "Still studying, Aditya?"));
test("greeting: night without name is a question", () =>
  assert.equal(getGreeting(at(23, 30)), "Still studying?"));
test("greeting: messy name input still normalizes", () =>
  assert.equal(getGreeting(at(7, 0), "  ADITYA kumar"), "Good morning, Aditya."));

console.log(`\n${passed} passed`);
