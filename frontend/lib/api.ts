import { getToken } from "./token";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders() },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface User {
  id: number;
  email: string;
  created_at: string;
  // Not returned by the backend yet — optional so the landing page's
  // greeting can use a first name the moment auth adds one, with no
  // further wiring needed.
  name?: string;
}

export interface Topic {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  module_id: number;
  position: number;
  // Denormalised so "Course · Module" and course links need no extra fetch.
  module_name: string;
  course_id: number;
  course_name: string;
}

export interface Course {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  module_count: number;
  topic_count: number;
  avg_score: number;
}

export interface TreeTopic {
  id: number;
  name: string;
  description: string | null;
  position: number;
  status: Mastery["status"];
  score: number;
  flagged_for_revision: boolean;
}

export interface TreeModule {
  id: number;
  name: string;
  description: string | null;
  position: number;
  topics: TreeTopic[];
}

// A course with its modules in order, each with its topics in order.
export interface CourseTree {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  modules: TreeModule[];
}

export interface Mastery {
  topic_id: number;
  score: number;
  status: "unmastered" | "in_progress" | "mastered" | "missed";
  last_updated: string;
  flagged_for_revision: boolean;
}

export interface GraphNode {
  id: number;
  name: string;
  course_id: number;
  module_id: number;
  module_name: string;
  module_position: number;
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
  register: (email: string, password: string) =>
    request<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: async (email: string, password: string) => {
    const body = new URLSearchParams({ username: email, password });
    const res = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
    return res.json() as Promise<{ access_token: string; token_type: string }>;
  },
  me: () => request<User>("/auth/me"),
  listCourses: () => request<Course[]>("/courses"),
  createCourse: (payload: { name: string; description?: string }) =>
    request<Course>("/courses", { method: "POST", body: JSON.stringify(payload) }),
  updateCourse: (courseId: number, payload: { name?: string; description?: string | null }) =>
    request<Course>(`/courses/${courseId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteCourse: (courseId: number) =>
    request<void>(`/courses/${courseId}`, { method: "DELETE" }),
  getCourseTree: (courseId: number) => request<CourseTree>(`/courses/${courseId}/tree`),
  createModule: (courseId: number, payload: { name: string; description?: string }) =>
    request<TreeModule>(`/courses/${courseId}/modules`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  // The module routes that change structure answer with the refreshed tree.
  updateModule: (
    moduleId: number,
    payload: { name?: string; description?: string | null; position?: number }
  ) =>
    request<CourseTree>(`/modules/${moduleId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteModule: (moduleId: number) =>
    request<void>(`/modules/${moduleId}`, { method: "DELETE" }),
  reorderModules: (courseId: number, ids: number[]) =>
    request<CourseTree>(`/courses/${courseId}/modules/order`, {
      method: "PUT",
      body: JSON.stringify({ ids }),
    }),
  reorderTopics: (moduleId: number, ids: number[]) =>
    request<CourseTree>(`/modules/${moduleId}/topics/order`, {
      method: "PUT",
      body: JSON.stringify({ ids }),
    }),
  listTopics: () => request<Topic[]>("/topics"),
  createTopic: (payload: { name: string; module_id: number; description?: string }) =>
    request<Topic>("/topics", { method: "POST", body: JSON.stringify(payload) }),
  updateTopic: (
    topicId: number,
    payload: { name?: string; description?: string | null; module_id?: number }
  ) => request<Topic>(`/topics/${topicId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteTopic: (topicId: number) =>
    request<void>(`/topics/${topicId}`, { method: "DELETE" }),
  getGraph: (courseId?: number) =>
    request<GraphData>(
      courseId === undefined ? "/topics/graph/json" : `/topics/graph/json?course_id=${courseId}`
    ),
  listMastery: () => request<Mastery[]>("/mastery"),
  markMissed: (topicId: number) =>
    request<Mastery>(`/mastery/${topicId}/missed`, { method: "POST" }),
  toggleRevision: (topicId: number) =>
    request<Mastery>(`/mastery/${topicId}/toggle-revision`, { method: "POST" }),
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
    const res = await fetch(`${API_URL}/sources/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    });
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
