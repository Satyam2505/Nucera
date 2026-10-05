"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { api, Course, GraphData, Mastery, Topic } from "./api";

interface AppState {
  courses: Course[];
  topics: Topic[];
  masteryByTopic: Record<number, Mastery>;
  graph: GraphData | null;
  selectedTopicId: number | null;
  setSelectedTopicId: (id: number) => void;
  loading: boolean;
  refresh: () => Promise<void>;
}

const AppStateContext = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [masteryByTopic, setMasteryByTopic] = useState<Record<number, Mastery>>({});
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [coursesData, topicsData, masteryData, graphData] = await Promise.all([
        api.listCourses(),
        api.listTopics(),
        api.listMastery(),
        api.getGraph(),
      ]);
      setCourses(coursesData);
      setTopics(topicsData);
      setMasteryByTopic(Object.fromEntries(masteryData.map((m) => [m.topic_id, m])));
      setGraph(graphData);
      setSelectedTopicId((prev) => prev ?? topicsData[0]?.id ?? null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AppStateContext.Provider
      value={{ courses, topics, masteryByTopic, graph, selectedTopicId, setSelectedTopicId, loading, refresh }}
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
