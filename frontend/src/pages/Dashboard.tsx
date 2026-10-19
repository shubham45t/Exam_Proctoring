import { useEffect, useState } from "react";
import { Card, DemoBadge, StateBadge, Stat, btnSecondary } from "../components/ui";
import { api } from "../services/api";
import { useOccupancy } from "../hooks/useOccupancy";
import type { ApiEvent, Camera, CameraState, Exam, ReviewAlert, Room, SystemStatus } from "../types";

function describe(e: ApiEvent): string {
  const p = e.payload as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  if (e.event_type === "camera_status") return `${p.previous_state ?? "—"} → ${p.state}${p.detail ? ` · ${p.detail}` : ""}`;
  if (e.event_type === "occupancy") return `seat ${e.seat_id}: ${p.state}`;
  if (e.event_type === "object_detection") return `possible ${p.object_class} #${p.tracker_id} · conf ${(p.confidence as number).toFixed(2)} · ${p.model_id}${e.seat_id ? ` · seat ${e.seat_id}` : ""}`;
  if (e.event_type === "tracking") return `${p.object_class} #${p.tracker_id} ${p.track_state}${e.seat_id ? ` · seat ${e.seat_id}` : ""}`;
  if (e.event_type === "head_pose") return `head gaze turn ${Math.abs(p.yaw_deg ?? 0).toFixed(0)}° ${p.yaw_deg > 0 ? "left" : "right"}${e.seat_id ? ` · seat ${e.seat_id}` : ""}`;
  if (e.event_type === "spatial_interaction") return `${p.kind}: ${p.explanation}`;
  return e.event_type;
}

export default function Dashboard({
  cameras,
  events,
  status,
  refresh,
  rooms,
  tick,
}: {
  cameras: Camera[];
  events: ApiEvent[];
  status: SystemStatus | null;
  refresh: () => Promise<void>;
  rooms: Room[];
  tick: string | undefined;
}) {
  const room = rooms[0];
  const { occupancy } = useOccupancy(room?.room_id ?? null, tick);
  const sm = occupancy?.summary;
  const [busy, setBusy] = useState(false);
  const [activeExam, setActiveExam] = useState<Exam | null>(null);
  const [unreviewedAlerts, setUnreviewedAlerts] = useState<ReviewAlert[]>([]);

  const failing = cameras.filter((c) => c.running && c.runtime && !["CONNECTED", "CONNECTING"].includes(c.runtime.state));
  const names = Object.fromEntries(cameras.map((c) => [c.camera_id, c.name]));

  useEffect(() => {
    api.exams("IN_PROGRESS")
      .then((exs) => setActiveExam(exs[0] ?? null))
      .catch(() => {});
    api.alerts("NEW")
      .then((res) => setUnreviewedAlerts(res.items))
      .catch(() => {});
  }, [tick]);

  return (
    <div className="space-y-6">
      {/* Active Exam Ribbon */}
      {activeExam ? (
        <div className="flex items-center justify-between rounded-xl bg-gradient-to-r from-sky-900 to-indigo-900 p-4 text-white shadow-md">
          <div className="flex items-center gap-3">
            <span className="flex h-3 w-3 rounded-full bg-emerald-400 animate-pulse" />
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-sky-300">Live Examination in Session</div>
              <div className="text-base font-bold">{activeExam.title} ({activeExam.course_code || "Active"})</div>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs text-sky-200">
            <span>Room: <strong className="text-white">{activeExam.room_name || "Assigned Hall"}</strong></span>
            <span>Started: <strong className="text-white">{activeExam.start_time ? new Date(activeExam.start_time).toLocaleTimeString() : "—"}</strong></span>
          </div>
        </div>
      ) : unreviewedAlerts.length > 0 ? (
        <div className="flex items-center justify-between rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-900 shadow-sm">
          <div className="flex items-center gap-3">
            <span className="text-lg">⚠️</span>
            <div>
              <div className="text-xs font-bold uppercase tracking-wider text-amber-800">Pending Proctor Reviews</div>
              <div className="text-sm font-semibold">{unreviewedAlerts.length} candidate incident alert(s) awaiting determination</div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">System Status &amp; Metrics</h1>
          <p className="text-xs text-slate-500">Live health indicators, computer vision pipelines, and workstation states.</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Cameras running"
          value={status ? `${status.cameras.running} / ${status.cameras.registered}` : "—"}
        />
        <Stat
          label="Cameras needing attention"
          value={failing.length}
          hint={failing.length > 0 ? "Check connectivity" : "All active feeds healthy"}
        />
        <Stat
          label="Object detector"
          value={status ? (status.detector.enabled ? "Ready" : "Off") : "—"}
          hint={status ? (status.detector.enabled ? `${status.detector.model_id ?? "loaded"}` : status.detector.reason) : undefined}
        />
        <Stat
          label="Backend Health"
          value={status ? (status.database.ok ? "Healthy" : "DB error") : "—"}
          hint={status ? `CPU ${status.resources.cpu_percent}% · RAM ${status.resources.memory_percent}%` : undefined}
        />
      </div>

      {room && sm && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-800">Workstation Occupancy &middot; {room.name}</h2>
            <span className="text-xs text-slate-500 font-medium">{sm.total} calibrated desks</span>
          </div>
          <div className="grid grid-cols-3 gap-3 lg:grid-cols-6">
            <Stat label="Total" value={sm.total} />
            <Stat label="Occupied" value={sm.occupied} />
            <Stat label="Vacant" value={sm.vacant} />
            <Stat label="Uncertain" value={sm.uncertain} />
            <Stat label="Occluded" value={sm.occluded} />
            <Stat label="Unmonitored" value={sm.unmonitored} />
          </div>
        </div>
      )}

      <Card title="Registered Camera Sources">
        {cameras.length === 0 ? (
          <p className="text-sm text-slate-500 py-4 text-center">No cameras registered. Add one on the Cameras page.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {cameras.map((c) => (
              <li key={c.camera_id} className="flex items-center justify-between py-2.5 text-sm">
                <span className="font-medium text-slate-900">
                  {c.name} <span className="font-normal text-slate-400 text-xs">({c.camera_id})</span>
                </span>
                <span className="flex items-center gap-3 text-xs text-slate-500">
                  {c.runtime?.fps != null && <span className="font-mono">{c.runtime.fps} fps</span>}
                  {c.runtime?.quality_issues.length ? (
                    <span className="text-amber-600 font-medium">{c.runtime.quality_issues.join(", ")}</span>
                  ) : null}
                  <StateBadge state={c.running && c.runtime ? (c.runtime.state as CameraState) : "NOT RUNNING"} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card
        title="Live System Ingestion Stream"
        action={
          status?.synthetic_events_enabled ? (
            <button
              className={btnSecondary}
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api.syntheticEvent();
                  await refresh();
                } finally {
                  setBusy(false);
                }
              }}
            >
              Inject synthetic test event
            </button>
          ) : undefined
        }
      >
        {events.length === 0 ? (
          <p className="text-sm text-slate-500 py-6 text-center">No events yet. Start a camera to see real camera-status and observation events.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm" aria-live="polite">
            {events.slice(0, 20).map((e) => (
              <li key={e.event_id} className="flex items-start justify-between gap-4 py-2.5">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-800 text-xs uppercase tracking-wide">
                      {e.event_type.replace("_", " ")}
                    </span>
                    {e.is_synthetic && <DemoBadge />}
                    {e.camera_id && <span className="text-xs text-slate-400">{names[e.camera_id] ?? e.camera_id}</span>}
                  </div>
                  <div className="truncate text-xs text-slate-600 mt-0.5">
                    {describe(e)}
                    {typeof e.payload.evidence_id === "string" && (
                      <a
                        className="ml-2 text-sky-700 underline font-medium"
                        href={`/api/evidence/${e.payload.evidence_id}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        view evidence image &rarr;
                      </a>
                    )}
                  </div>
                </div>
                <time className="shrink-0 text-xs text-slate-400 font-mono" dateTime={e.timestamp}>
                  {new Date(e.timestamp).toLocaleTimeString()}
                </time>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
