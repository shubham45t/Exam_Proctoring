export type CameraState =
  | "CONNECTING" | "CONNECTED" | "DEGRADED" | "STALE" | "FROZEN" | "RECONNECTING" | "FAILED" | "STOPPED";
export type SourceType = "VIDEO_FILE" | "WEBCAM" | "HTTP_MJPEG" | "RTSP";

export interface CameraRuntime {
  state: CameraState; quality_issues: string[]; fps: number | null; frame_age_s: number | null;
  frames_total: number; frames_overwritten: number; analysis_ms: number; detail: string | null;
  analyzers?: AnalyzerStats[];
}
export interface AnalyzerStats {
  name: string; processed: number; dropped: number; errors: number; infer_ms_median: number | null; infer_ms_p95: number | null;
  model_id?: string; detections_total?: number; tentative_dropped?: number;
}
export interface LiveTrack {
  tracker_id: number; object_class: string; confidence: number; confirmed: boolean; lost: boolean;
  bbox: { x1: number; y1: number; x2: number; y2: number };
}
export interface Camera {
  camera_id: string; name: string; source_type: SourceType; source_display: string;
  created_at: string; running: boolean; runtime: CameraRuntime | null; room_id: string | null; baseline_at: string | null; object_detection: boolean;
}
export interface ApiEvent {
  event_id: string; event_type: string; camera_id: string | null; seat_id: string | null;
  timestamp: string; is_synthetic: boolean; payload: Record<string, unknown>;
}
export interface EventPage { items: ApiEvent[]; total: number; limit: number; offset: number }
export interface SystemStatus {
  version: string; environment: string; uptime_s: number; python: string;
  database: { ok: boolean; dialect: string };
  cameras: { registered: number; running: number; by_state: Record<string, number> };
  detector: { enabled: boolean; loaded: boolean; model_id?: string; model_version?: string; reason?: string; classes?: string[] };
  events_total: number; websocket_clients: number; synthetic_events_enabled: boolean;
  resources: { cpu_percent: number; memory_percent: number; process_rss_mb: number };
}
export interface ProbeResult {
  ok: boolean; frames_read?: number; width?: number; height?: number; measured_fps?: number | null;
  is_live?: boolean; elapsed_s?: number; notes?: string[];
  error?: { code: string; message: string; hints: string[] } | null; note?: string;
}
export type WsMessage =
  | { type: "hello"; data: unknown }
  | { type: "camera_status"; data: Record<string, unknown> & { camera_id: string } }
  | { type: "event"; data: Record<string, unknown> & { event_id: string } };

export type SeatState = "VACANT" | "OCCUPIED" | "UNCERTAIN" | "OCCLUDED" | "UNMONITORED";
export type Visibility = "monitored" | "partial" | "not_visible";
export interface Seat { seat_id: string; row: number; col: number; x: number; y: number; monitored: boolean }
export interface Room { room_id: string; name: string; width_m: number; depth_m: number; created_at: string; seat_count: number }
export interface RoomDetail extends Room { seats: Seat[] }
export interface FusedSeat {
  seat_id: string; state: SeatState; confidence: number; reason: string | null; updated_at: string | null;
  cameras: { camera_id: string; visibility: Visibility; state?: string | null; age_s?: number | null; reason?: string | null }[];
}
export interface Occupancy {
  room_id: string; generated_at: string; method: string;
  summary: { total: number; vacant: number; occupied: number; uncertain: number; occluded: number; unmonitored: number };
  seats: FusedSeat[];
  cameras: { camera_id: string; name: string; running: boolean; state: string | null; baseline_at: string | null; seats_covered: number }[];
}
export interface Region { seat_id: string; polygon: [number, number][]; visibility: Visibility }
export interface RegionsDoc { camera_id: string; room_id: string | null; baseline_at: string | null; regions: Region[] }

export interface User {
  user_id: string;
  username: string;
  full_name: string;
  role: "admin" | "proctor" | "auditor";
  is_active: boolean;
}

export type ExamStatus = "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
export interface Exam {
  exam_id: string;
  title: string;
  course_code: string | null;
  room_id: string | null;
  room_name?: string | null;
  start_time: string | null;
  end_time: string | null;
  status: ExamStatus;
  notes: string | null;
  alert_count: number;
  created_at: string;
}

export interface ExamDetail extends Exam {
  cameras: { camera_id: string; name: string }[];
  alerts: { alert_id: string; title: string; priority: string; status: string; created_at: string }[];
}

export type AlertPriority = "low" | "medium" | "high";
export type AlertState = "NEW" | "ACKNOWLEDGED" | "DISMISSED" | "REFERRED";

export interface ReviewAlert {
  alert_id: string;
  incident_id: string;
  exam_id: string | null;
  title: string;
  summary: string;
  priority: AlertPriority;
  status: AlertState;
  created_at: string;
  notice: string;
  is_synthetic: boolean;
}

export interface RuleContribution {
  rule_id: string;
  description: string;
  points: number;
  observation_ids: string[];
}

export interface CandidateIncident {
  incident_id: string;
  category: string;
  camera_id: string;
  seat_id: string | null;
  first_seen: string;
  last_seen: string;
  priority: string;
  review_priority_score: number;
  explanation: string;
  limitations: string[];
  rules_triggered: RuleContribution[];
  observation_ids: string[];
  evidence_ids: string[];
}

export interface IncidentReview {
  review_id: string;
  reviewer_id: string;
  decision: "ACKNOWLEDGE" | "DISMISS" | "REFER";
  notes: string;
  reviewed_at: string;
}

export interface EvidenceItem {
  evidence_id: string;
  kind: string;
  status: string;
  captured_at: string;
  url: string | null;
}

export interface AlertDetail {
  alert: ReviewAlert;
  incident: CandidateIncident | null;
  reviews: IncidentReview[];
  evidence: EvidenceItem[];
}

export interface ExamReport {
  exam_id: string;
  title: string;
  course_code: string | null;
  room_name: string;
  total_seats: number;
  status: string;
  start_time: string | null;
  end_time: string | null;
  duration_minutes: number | null;
  notes: string | null;
  metrics: {
    total_alerts: number;
    total_incidents: number;
    priority_breakdown: { high: number; medium: number; low: number };
    status_breakdown: { NEW: number; ACKNOWLEDGED: number; DISMISSED: number; REFERRED: number };
    decision_breakdown: { ACKNOWLEDGE: number; DISMISS: number; REFER: number };
    reviews_completed: number;
  };
  timeline: {
    incident_id: string;
    timestamp: string;
    category: string;
    seat_id: string | null;
    priority: string;
    score: number;
    explanation: string;
    limitations: string[];
    evidence_ids: string[];
    status: string;
    review: {
      reviewer_id: string;
      decision: string;
      notes: string;
      reviewed_at: string;
    } | null;
  }[];
  compliance_notice: string;
}
