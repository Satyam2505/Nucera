const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface Topic {
  id: number;
  name: string;
  course: string;
  description: string | null;
  created_at: string;
}

export interface Mastery {
  topic_id: number;
  score: number;
  status: "unmastered" | "in_progress" | "mastered" | "missed";
  last_updated: string;
}

export interface GraphNode {
  id: number;
  name: string;
  course: string;
  status: string;
  score: number;
}

export interface GraphEdge {
  source: number;
  target: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface QuizQuestion {
  id: number;
  topic_id: number;
  question_text: string;
  options: Record<string, string>;
}

export interface QuizSubmitResult {
  total: number;
  correct: number;
  score_percent: number;
  mastery: Mastery;
}

export interface SourceCitation {
  source: string;
  page: number | null;
}

export interface Source {
  id: number;
  topic_id: number;
  source_type: string;
  title: string;
  created_at: string;
  chunk_count: number;
}

export interface ChatTurn {
  role: "user" | "assistant";
  text: string;
}

export interface AskResponse {
  answer: string;
  flagged_prerequisites: Topic[];
  sources: SourceCitation[];
  grounded: boolean;
}

export const api = {
  listTopics: () => request<Topic[]>("/topics"),
  createTopic: (payload: { name: string; course: string; description?: string }) =>
    request<Topic>("/topics", { method: "POST", body: JSON.stringify(payload) }),
  getGraph: () => request<GraphData>("/topics/graph/json"),
  listMastery: () => request<Mastery[]>("/mastery"),
  markMissed: (topicId: number) =>
    request<Mastery>(`/mastery/${topicId}/missed`, { method: "POST" }),
  updateMastery: (topicId: number, payload: Partial<Pick<Mastery, "score" | "status">>) =>
    request<Mastery>(`/mastery/${topicId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  ingestText: (payload: {
    topic_id: number;
    source_type: string;
    title: string;
    text: string;
  }) => request(`/sources/text`, { method: "POST", body: JSON.stringify(payload) }),
  uploadFile: async (topicId: number, sourceType: string, file: File) => {
    const formData = new FormData();
    formData.append("topic_id", String(topicId));
    formData.append("source_type", sourceType);
    formData.append("file", file);
    const res = await fetch(`${API_URL}/sources/upload`, { method: "POST", body: formData });
    if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
    return res.json();
  },
  ask: (payload: { query: string; topic_id: number; history?: ChatTurn[] }) =>
    request<AskResponse>("/ask", { method: "POST", body: JSON.stringify(payload) }),
  listSources: (topicId: number) => request<Source[]>(`/sources/topic/${topicId}`),
  deleteSource: (sourceId: number) =>
    request<void>(`/sources/${sourceId}`, { method: "DELETE" }),
  getQuiz: (topicId: number) => request<QuizQuestion[]>(`/quiz/${topicId}`),
  submitQuiz: (payload: {
    topic_id: number;
    answers: { question_id: number; selected_option: string }[];
  }) => request<QuizSubmitResult>(`/quiz/submit`, { method: "POST", body: JSON.stringify(payload) }),
};
