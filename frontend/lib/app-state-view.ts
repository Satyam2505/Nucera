// What the library (courses, topics, mastery, graph) is doing, as one small state
// machine, so the screens that show it agree about when to say "loading", when to
// say "couldn't load", and when to just show the data. Pure, so it is tested on its
// own under plain Node (see app-state-view.test.ts).

export interface LoadState {
  // A refresh is in flight.
  loading: boolean;
  // The library has loaded successfully at least once. Once true it stays true,
  // so a later failed refresh can never turn real data back into "nothing here".
  loaded: boolean;
  // Why the most recent refresh failed, or null.
  error: string | null;
}

export const INITIAL_LOAD_STATE: LoadState = { loading: true, loaded: false, error: null };

export function refreshStarted(state: LoadState): LoadState {
  return { ...state, loading: true, error: null };
}

export function refreshSucceeded(): LoadState {
  return { loading: false, loaded: true, error: null };
}

export function refreshFailed(state: LoadState, reason: string): LoadState {
  return { loading: false, loaded: state.loaded, error: reason };
}

export type LibraryView =
  // Nothing to show yet and a load is under way.
  | "loading"
  // The first load failed: there is no data, so say so (with a retry), instead of
  // showing an empty library and zero counts.
  | "blocking-error"
  // Data is on screen and a later refresh failed: keep it, add a non-blocking notice.
  | "ready-with-notice"
  | "ready";

export function selectLibraryView(state: LoadState): LibraryView {
  if (!state.loaded) return state.error ? "blocking-error" : "loading";
  return state.error ? "ready-with-notice" : "ready";
}
