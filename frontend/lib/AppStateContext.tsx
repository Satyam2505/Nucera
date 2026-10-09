"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";

import { api, Course, GraphData, Mastery, Topic } from "./api";
import { failureReason } from "./api-errors";
import {
  INITIAL_LOAD_STATE,
  refreshFailed,
  refreshStarted,
  refreshSucceeded,
  type LoadState,
} from "./app-state-view";

interface AppState {
  courses: Course[];
  topics: Topic[];
  masteryByTopic: Record<number, Mastery>;
  graph: GraphData | null;
  selectedTopicId: number | null;
  setSelectedTopicId: (id: number) => void;
  loading: boolean;
  // Why the most recent refresh failed (a readable sentence), or null. Whatever
  // was loaded before stays in the fields above, so check `loaded` to tell "the
  // first load failed, there is no data" from "a later refresh failed, this is
  // the last good data".
  error: string | null;
  // True once the library has loaded successfully at least once.
  loaded: boolean;
  // Never rejects: a failure is reported through `error` instead.
  refresh: () => Promise<void>;
}

const AppStateContext = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [masteryByTopic, setMasteryByTopic] = useState<Record<number, Mastery>>({});
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState<number | null>(null);
  const [status, setStatus] = useState<LoadState>(INITIAL_LOAD_STATE);
  // Only the most recent refresh may change what is shown, so a slow older one
  // finishing late (or failing late) can't overwrite a newer result.
  const latest = useRef(0);

  const refresh = useCallback(async () => {
    const requestId = ++latest.current;
    setStatus(refreshStarted);
    try {
      const [coursesData, topicsData, masteryData, graphData] = await Promise.all([
        api.listCourses(),
        api.listTopics(),
        api.listMastery(),
        api.getGraph(),
      ]);
      if (requestId !== latest.current) return;
      setCourses(coursesData);
      setTopics(topicsData);
      setMasteryByTopic(Object.fromEntries(masteryData.map((m) => [m.topic_id, m])));
      setGraph(graphData);
      setSelectedTopicId((prev) => prev ?? topicsData[0]?.id ?? null);
      setStatus(refreshSucceeded());
    } catch (err) {
      // A 401 has already cleared the token and signed the user out (api.ts); this
      // provider is unmounting then, so the message below is simply never seen.
      // On any other failure the previously loaded data is left exactly as it was.
      if (requestId !== latest.current) return;
      setStatus((current) => refreshFailed(current, failureReason(err)));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AppStateContext.Provider
      value={{
        courses,
        topics,
        masteryByTopic,
        graph,
        selectedTopicId,
        setSelectedTopicId,
        loading: status.loading,
        error: status.error,
        loaded: status.loaded,
        refresh,
      }}
    >
      {children}
    </AppStateContext.Provider>
  );
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within AppStateProvider");
  return ctx;
}
