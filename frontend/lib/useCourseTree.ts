"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, CourseTree } from "./api";

export type CourseTreeState =
  | { status: "loading" }
  | { status: "notfound" }
  | { status: "error"; message: string }
  | { status: "ready"; tree: CourseTree };

/**
 * Fetches one course's tree. `courseId` is null for an unusable route param,
 * which resolves straight to "notfound" without a request. `reload` refetches
 * without dropping to "loading" (the tree on screen stays put); `setTree`
 * applies a tree a mutation already returned.
 */
export function useCourseTree(courseId: number | null) {
  const [state, setState] = useState<CourseTreeState>({ status: "loading" });
  // Guards against a slow response for a previous course landing after a switch.
  const latest = useRef(0);

  const load = useCallback(
    async (showLoading: boolean) => {
      const requestId = ++latest.current;
      if (courseId === null) {
        setState({ status: "notfound" });
        return;
      }
      if (showLoading) setState({ status: "loading" });
      try {
        const tree = await api.getCourseTree(courseId);
        if (requestId === latest.current) setState({ status: "ready", tree });
      } catch (err) {
        if (requestId !== latest.current) return;
        if (err instanceof ApiError && err.status === 404) setState({ status: "notfound" });
        else
          setState({
            status: "error",
            message: err instanceof Error ? err.message : "Failed to load course",
          });
      }
    },
    [courseId]
  );

  useEffect(() => {
    load(true);
  }, [load]);

  const reload = useCallback(() => load(false), [load]);
  const retry = useCallback(() => load(true), [load]);
  const setTree = useCallback((tree: CourseTree) => {
    latest.current++;
    setState({ status: "ready", tree });
  }, []);

  return { state, reload, retry, setTree };
}
