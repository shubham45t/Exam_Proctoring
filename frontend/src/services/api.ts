import type {
  AlertDetail,
  Camera,
  CandidateIncident,
  EventPage,
  Exam,
  ExamDetail,
  ExamReport,
  LiveTrack,
  Occupancy,
  ProbeResult,
  Region,
  RegionsDoc,
  ReviewAlert,
  Room,
  RoomDetail,
  Seat,
  SourceType,
  SystemStatus,
  User,
} from "../types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public hints: string[] = []) {
    super(message);
  }
}

let authToken: string | null = localStorage.getItem("omni_token");

export function setToken(token: string | null) {
  authToken = token;
  if (token) localStorage.setItem("omni_token", token);
  else localStorage.removeItem("omni_token");
}

export function getToken(): string | null {
  return authToken;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  try {
    res = await fetch(path, { headers, ...init });
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach the OmniProctor backend. Is it running?");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const d = body?.detail;
    if (Array.isArray(d)) throw new ApiError(res.status, "VALIDATION", d.map((x) => x.msg).join("; "));
    throw new ApiError(res.status, d?.code ?? "ERROR", d?.message ?? res.statusText, d?.hints ?? []);
  }
  return body as T;
}

export const api = {
  // System & Health
  status: () => request<SystemStatus>("/api/system/status"),

  // Auth
  login: (username: string, password: string) =>
    request<{ token: string; user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<User>("/api/auth/me"),
  users: () => request<User[]>("/api/auth/users"),
  createUser: (data: { username: string; password: string; full_name: string; role: string }) =>
    request<User>("/api/auth/users", { method: "POST", body: JSON.stringify(data) }),
  seedUsers: () => request<{ ok: boolean }>("/api/auth/seed", { method: "POST" }),

  // Cameras
  cameras: () => request<Camera[]>("/api/cameras"),
  media: () => request<{ files: string[] }>("/api/media"),
  createCamera: (b: {
    name: string;
    source_type: SourceType;
    source_uri: string;
    object_detection?: boolean;
    head_pose_enabled?: boolean;
    spatial_rules_enabled?: boolean;
  }) => request<Camera>("/api/cameras", { method: "POST", body: JSON.stringify(b) }),
  patchCamera: (
    id: string,
    b: {
      name?: string;
      source_type?: SourceType;
      source_uri?: string;
      object_detection?: boolean;
      head_pose_enabled?: boolean;
      spatial_rules_enabled?: boolean;
    }
  ) => request<Camera>(`/api/cameras/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  detections: (id: string) => request<{ running: boolean; tracks: LiveTrack[] }>(`/api/cameras/${id}/detections`),
  deleteCamera: (id: string) => request<void>(`/api/cameras/${id}`, { method: "DELETE" }),
  testCamera: (id: string) => request<ProbeResult>(`/api/cameras/${id}/test`, { method: "POST" }),
  startCamera: (id: string) => request<Camera>(`/api/cameras/${id}/start`, { method: "POST" }),
  stopCamera: (id: string) => request<Camera>(`/api/cameras/${id}/stop`, { method: "POST" }),

  // Events
  events: (limit = 50, extra = "") => request<EventPage>(`/api/events?limit=${limit}${extra}`),
  syntheticEvent: (camera_id?: string) =>
    request("/api/events/synthetic", { method: "POST", body: JSON.stringify({ camera_id: camera_id ?? null }) }),

  // Rooms & Calibration
  rooms: () => request<Room[]>("/api/rooms"),
  room: (id: string) => request<RoomDetail>(`/api/rooms/${id}`),
  createRoom: (b: { name: string; width_m: number; depth_m: number; generate?: { rows: number; cols: number } }) =>
    request<RoomDetail>("/api/rooms", { method: "POST", body: JSON.stringify(b) }),
  putSeats: (id: string, seats: Seat[]) =>
    request<Seat[]>(`/api/rooms/${id}/seats`, { method: "PUT", body: JSON.stringify(seats) }),
  occupancy: (id: string) => request<Occupancy>(`/api/rooms/${id}/occupancy`),
  regions: (cam: string) => request<RegionsDoc>(`/api/cameras/${cam}/seat-regions`),
  putRegions: (cam: string, room_id: string | null, regions: Region[]) =>
    request(`/api/cameras/${cam}/seat-regions`, { method: "PUT", body: JSON.stringify({ room_id, regions }) }),
  captureBaseline: (cam: string) => request<{ baseline_at: string }>(`/api/cameras/${cam}/baseline`, { method: "POST" }),
  deleteBaseline: (cam: string) => request<void>(`/api/cameras/${cam}/baseline`, { method: "DELETE" }),

  // Examinations
  exams: (status?: string) => request<Exam[]>(`/api/exams${status ? `?status=${status}` : ""}`),
  exam: (id: string) => request<ExamDetail>(`/api/exams/${id}`),
  createExam: (b: { title: string; course_code?: string; room_id?: string; notes?: string }) =>
    request<ExamDetail>("/api/exams", { method: "POST", body: JSON.stringify(b) }),
  startExam: (id: string) => request<ExamDetail>(`/api/exams/${id}/start`, { method: "POST" }),
  endExam: (id: string) => request<ExamDetail>(`/api/exams/${id}/end`, { method: "POST" }),

  // Alerts & Incidents
  alerts: (status?: string, priority?: string) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (priority) params.set("priority", priority);
    const qs = params.toString();
    return request<{ items: ReviewAlert[]; total: number }>(`/api/alerts${qs ? `?${qs}` : ""}`);
  },
  alert: (id: string) => request<AlertDetail>(`/api/alerts/${id}`),
  reviewAlert: (id: string, decision: "ACKNOWLEDGE" | "DISMISS" | "REFER", notes: string) =>
    request<AlertDetail>(`/api/alerts/${id}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, notes }),
    }),
  incidents: (exam_id?: string) =>
    request<{ items: CandidateIncident[]; total: number }>(`/api/incidents${exam_id ? `?exam_id=${exam_id}` : ""}`),

  // Reports
  report: (exam_id: string) => request<ExamReport>(`/api/reports/exam/${exam_id}`),
};
