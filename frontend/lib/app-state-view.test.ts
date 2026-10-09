// Plain-Node tests for the library load state machine. Run with `npm test`
// (or `npm test -- app-state-view`); see scripts/test-lib.mjs.

import assert from "node:assert/strict";

import {
  INITIAL_LOAD_STATE,
  refreshFailed,
  refreshStarted,
  refreshSucceeded,
  selectLibraryView,
  type LoadState,
} from "./app-state-view";

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed++;
  console.log(`ok - ${name}`);
}

test("before anything has loaded, the view is loading", () => {
  assert.equal(selectLibraryView(INITIAL_LOAD_STATE), "loading");
});

test("a first load that succeeds is ready", () => {
  assert.equal(selectLibraryView(refreshSucceeded()), "ready");
});

test("a first load that fails is a blocking error, never an empty library", () => {
  const failed = refreshFailed(refreshStarted(INITIAL_LOAD_STATE), "Can't reach the server.");
  assert.equal(failed.loaded, false);
  assert.equal(failed.error, "Can't reach the server.");
  assert.equal(selectLibraryView(failed), "blocking-error");
});

test("retrying after a failed first load goes back to loading, then to ready", () => {
  const failed = refreshFailed(INITIAL_LOAD_STATE, "down");
  const retrying = refreshStarted(failed);
  assert.deepEqual(retrying, { loading: true, loaded: false, error: null });
  assert.equal(selectLibraryView(retrying), "loading");
  assert.equal(selectLibraryView(refreshSucceeded()), "ready");
});

test("a retry that fails again stays a blocking error", () => {
  const second = refreshFailed(refreshStarted(refreshFailed(INITIAL_LOAD_STATE, "down")), "still down");
  assert.equal(selectLibraryView(second), "blocking-error");
  assert.equal(second.error, "still down");
});

test("a failed refresh after a successful load keeps the data on screen with a notice", () => {
  const failed = refreshFailed(refreshStarted(refreshSucceeded()), "Request failed (500).");
  assert.equal(failed.loaded, true); // the loaded data is still trusted
  assert.equal(selectLibraryView(failed), "ready-with-notice");
});

test("while a later refresh runs, the notice clears and the data stays", () => {
  const noticed = refreshFailed(refreshSucceeded(), "oops");
  const retrying = refreshStarted(noticed);
  assert.equal(retrying.error, null);
  assert.equal(retrying.loaded, true);
  assert.equal(selectLibraryView(retrying), "ready");
});

test("success after a notice returns to plain ready", () => {
  assert.equal(selectLibraryView(refreshSucceeded()), "ready");
});

test("loaded never goes back to false, however many refreshes fail", () => {
  let state: LoadState = refreshSucceeded();
  for (let i = 0; i < 5; i++) state = refreshFailed(refreshStarted(state), `fail ${i}`);
  assert.equal(state.loaded, true);
  assert.equal(selectLibraryView(state), "ready-with-notice");
});

test("an error always wins over loading when nothing has loaded", () => {
  assert.equal(selectLibraryView({ loading: true, loaded: false, error: "x" }), "blocking-error");
  assert.equal(selectLibraryView({ loading: false, loaded: false, error: null }), "loading");
});

console.log(`\n${passed} passed`);
