import { errorDetail, isSessionExpiry } from "./api-errors";
import { parseStreamEvent, SavedChatMessage, StreamDone } from "./chat";
import { readNdjson } from "./ndjson";
import { clearToken, getToken } from "./token";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// The message is the server's readable `detail` (never a JSON blob), so any
// banner that shows `err.message` reads well; `status` lets callers tell "not
// found" or "conflict" from a real failure without parsing anything.
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

// Called when a request that carried a token is rejected with 401 (expired or
// invalid token). AuthProvider registers it to drop back to the login screen.
let onSessionExpired: (() => void) | null = null;

export function setSessionExpiredHandler(handler: (() => void) | null) {
  onSessionExpired = handler;
}

// The one place every response goes through — JSON calls, the login form post
// and the file upload — so error text and sign-out handling can't diverge.
async function handleResponse<T>(res: Response, sentToken: boolean): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    if (isSessionExpiry(res.status, sentToken)) {
      clearToken();
      onSessionExpired?.();
    }
    throw new ApiError(res.status, errorDetail(res.status, body));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = authHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...headers },
    ...options,
  });
  return handleResponse<T>(res, "Authorization" in headers);
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
  // When the topic was last reviewed (a graded quiz or a typed score); null if never.
  last_reviewed_at: string | null;
  // Learned, but faded enough that it is time to review.
  due_for_review: boolean;
}

// One suggestion for what to study next. "review": learned but faded, due now. "ready": not
// mastered, every prerequisite mastered.
export interface NextStep {
  topic_id: number;
  topic_name: string;
  module_name: string;
  kind: "review" | "ready";
  reason: string;
  score: number;
  status: Mastery["status"];
  due_for_review: boolean;
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

export interface SourceCitation {
  source: string;
  page: number | null;
  // Set when the passage came from another topic of the same course.
  topic?: string | null;
}

// A question as shown before grading: no answer key and no explanation.
export interface QuizQuestion {
  id: number;
  position: number;
  question_text: string;
  options: Record<string, string>;
}

export interface QuizResultItem {
  question_id: number;
  question_text: string;
  options: Record<string, string>;
  chosen: string | null;
  correct_option: string;
  is_correct: boolean;
  explanation: string | null;
  sources: SourceCitation[];
}

export interface QuizAttempt {
  id: number;
  quiz_set_id: number;
  correct: number;
  total: number;
  score_percent: number;
  score_delta: number;
  created_at: string;
  results: QuizResultItem[];
  // The topic's mastery as it stands now.
  mastery: Mastery | null;
}

export interface QuizSet {
  id: number;
  topic_id: number;
  created_at: string;
  questions: QuizQuestion[];
  // Present once the set has been graded; answers only ever arrive with it.
  attempt: QuizAttempt | null;
}

// A background quiz generation. It carries progress only: the finished quiz is
// read the usual way (getQuiz), so nothing is sent ungraded that wasn't before.
export interface QuizJob {
  id: number;
  topic_id: number;
  status: "queued" | "running" | "succeeded" | "partial" | "failed";
  requested: number;
  completed: number;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface QuizState {
  // The latest quiz that can be taken (never one still being written).
  quiz_set: QuizSet | null;
  has_material: boolean;
  // The topic's running generation, so a reload resumes its progress.
  job: QuizJob | null;
}

// One past quiz in a topic's list.
export interface QuizSummary {
  id: number;
  created_at: string | null;
  question_count: number;
  taken: boolean;
  correct: number | null;
  total: number | null;
  score_percent: number | null;
  attempted_at: string | null;
}

// One entry of the study-session timeline.
export interface SessionHistoryItem {
  id: number;
  topic_id: number;
  topic_name: string;
  type: "chat" | "quiz" | "self_report";
  score_delta: number;
  timestamp: string | null;
}

export interface Source {
  id: number;
  topic_id: number;
  source_type: string;
  title: string;
  created_at: string;
  chunk_count: number;
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
    // No token is sent, so a 401 here (wrong password) is just an error to show.
    return handleResponse<{ access_token: string; token_type: string }>(res, false);
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
  // `prerequisiteTopicId` must be learned before `topicId`. The server refuses a
  // link that would make a loop (400 with a readable message).
  addPrerequisite: (topicId: number, prerequisiteTopicId: number) =>
    request<{ status: string }>("/topics/prerequisites", {
      method: "POST",
      body: JSON.stringify({ topic_id: topicId, prerequisite_topic_id: prerequisiteTopicId }),
    }),
  removePrerequisite: (topicId: number, prerequisiteTopicId: number) =>
    request<void>(`/topics/${topicId}/prerequisites/${prerequisiteTopicId}`, { method: "DELETE" }),
  listMastery: () => request<Mastery[]>("/mastery"),
  getNextSteps: (courseId: number, limit = 3) =>
    request<NextStep[]>(`/courses/${courseId}/next?limit=${limit}`),
  markMissed: (topicId: number) =>
    request<Mastery>(`/mastery/${topicId}/missed`, { method: "POST" }),
  toggleRevision: (topicId: number) =>
    request<Mastery>(`/mastery/${topicId}/toggle-revision`, { method: "POST" }),
  updateMastery: (topicId: number, payload: { score: number }) =>
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
    // No Content-Type here: the browser sets the multipart boundary itself.
    const headers = authHeaders();
    const res = await fetch(`${API_URL}/sources/upload`, {
      method: "POST",
      headers,
      body: formData,
    });
    return handleResponse<Source>(res, "Authorization" in headers);
  },
  ask: (payload: { query: string; topic_id: number }) =>
    request<AskResponse>("/ask", { method: "POST", body: JSON.stringify(payload) }),
  // The answer as it is written: `onToken` gets each piece, and the promise
  // resolves with the final answer, citations and prerequisite gaps. Aborting
  // `signal` closes the connection, which also stops the model.
  askStream: async (
    payload: { query: string; topic_id: number },
    options: { onToken: (text: string) => void; signal?: AbortSignal }
  ): Promise<StreamDone> => {
    const headers = authHeaders();
    const res = await fetch(`${API_URL}/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(payload),
      signal: options.signal,
    });
    if (!res.ok) return handleResponse<StreamDone>(res, "Authorization" in headers);
    if (!res.body) throw new ApiError(0, "Your browser can't read streamed answers.");

    let done: StreamDone | null = null;
    await readNdjson(res.body, parseStreamEvent, (event) => {
      if (event.type === "token") options.onToken(event.text);
      else if (event.type === "done") done = event;
      else throw new ApiError(500, event.message);
    });
    if (!done) throw new ApiError(0, "The answer was interrupted before it finished.");
    return done;
  },
  getChat: (topicId: number) => request<SavedChatMessage[]>(`/chat/${topicId}`),
  clearChat: (topicId: number) => request<void>(`/chat/${topicId}`, { method: "DELETE" }),
  listSources: (topicId: number) => request<Source[]>(`/sources/topic/${topicId}`),
  deleteSource: (sourceId: number) =>
    request<void>(`/sources/${sourceId}`, { method: "DELETE" }),
  // Reading never generates. Generating starts a background job (it takes minutes
  // on a CPU) and returns at once; poll getQuizJob until it is no longer active,
  // then read the quiz with getQuiz.
  getQuiz: (topicId: number) => request<QuizState>(`/quiz/${topicId}`),
  generateQuiz: (topicId: number) =>
    request<QuizJob>(`/quiz/${topicId}/generate`, { method: "POST" }),
  getQuizJob: (jobId: number) => request<QuizJob>(`/quiz/jobs/${jobId}`),
  getQuizHistory: (topicId: number) => request<QuizSummary[]>(`/quiz/${topicId}/history`),
  getQuizSet: (quizSetId: number) => request<QuizSet>(`/quiz/sets/${quizSetId}`),
  listSessions: (params: { topicId?: number; courseId?: number; beforeId?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params.topicId !== undefined) query.set("topic_id", String(params.topicId));
    if (params.courseId !== undefined) query.set("course_id", String(params.courseId));
    if (params.beforeId !== undefined) query.set("before_id", String(params.beforeId));
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    const suffix = query.toString();
    return request<SessionHistoryItem[]>(suffix ? `/sessions?${suffix}` : "/sessions");
  },
  submitQuiz: (payload: {
    quiz_set_id: number;
    answers: { question_id: number; selected_option: string }[];
  }) => request<QuizAttempt>(`/quiz/submit`, { method: "POST", body: JSON.stringify(payload) }),
};
