import { useEffect, useState } from "react";
import { Card, StateBadge, btnDanger, btnPrimary, btnSecondary } from "../components/ui";
import { ApiError, api } from "../services/api";
import type { Camera, CameraState, LiveTrack, ProbeResult, SourceType } from "../types";

const TYPES: { value: SourceType; label: string; placeholder: string }[] = [
  { value: "HTTP_MJPEG", label: "Phone / HTTP (MJPEG)", placeholder: "http://192.168.x.x:8080/video" },
  { value: "RTSP", label: "RTSP (IP camera / NVR)", placeholder: "rtsp://user:pass@192.168.x.x:554/stream" },
  { value: "VIDEO_FILE", label: "Prerecorded video file", placeholder: "" },
  { value: "WEBCAM", label: "USB / built-in webcam", placeholder: "0" },
];

function ErrorBox({ e }: { e: { message: string; hints?: string[] } }) {
  return (
    <div role="alert" className="mt-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <p className="font-medium">{e.message}</p>
      {e.hints && e.hints.length > 0 && <ul className="mt-1 list-disc pl-5 text-xs">{e.hints.map((h) => <li key={h}>{h}</li>)}</ul>}
    </div>
  );
}

function AddCamera({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<SourceType>("HTTP_MJPEG");
  const [uri, setUri] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [err, setErr] = useState<{ message: string; hints?: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [det, setDet] = useState(true);

  useEffect(() => { api.media().then((m) => setFiles(m.files)).catch(() => {}); }, []);
  useEffect(() => { setUri(type === "VIDEO_FILE" ? files[0] ?? "" : type === "WEBCAM" ? "0" : ""); }, [type, files]);
  const meta = TYPES.find((t) => t.value === type)!;
  const field = "mt-1 block w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm";

  const submit = async (ev: React.SyntheticEvent) => {
    ev.preventDefault(); setBusy(true); setErr(null);
    try { await api.createCamera({ name, source_type: type, source_uri: uri, object_detection: det }); setName(""); onAdded(); }
    catch (e) { setErr(e instanceof ApiError ? e : { message: "Unexpected error" }); }
    finally { setBusy(false); }
  };

  return (
    <Card title="Add camera source">
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-3">
        <label className="text-sm font-medium">Display name
          <input className={field} value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} placeholder="Hall A – phone" />
        </label>
        <label className="text-sm font-medium">Source type
          <select className={field} value={type} onChange={(e) => setType(e.target.value as SourceType)}>
            {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium">{type === "VIDEO_FILE" ? "File (from backend media folder)" : "Address"}
          {type === "VIDEO_FILE" ? (
            <select className={field} value={uri} onChange={(e) => setUri(e.target.value)} required>
              {files.length === 0 && <option value="">No video files found</option>}
              {files.map((f) => <option key={f}>{f}</option>)}
            </select>
          ) : (
            <input className={field} value={uri} onChange={(e) => setUri(e.target.value)} required placeholder={meta.placeholder} autoComplete="off" />
          )}
        </label>
        <div className="flex flex-wrap gap-4 text-sm md:col-span-3">
          <label className="flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={det} onChange={(e) => setDet(e.target.checked)} />Detect prohibited phones</label>
        </div>
        <div className="md:col-span-3">
          <button className={btnPrimary} disabled={busy}>Add camera</button>
          <span className="ml-3 text-xs text-slate-500">Credentials in the address are stored on the server and never shown again.</span>
          {err && <ErrorBox e={err} />}
        </div>
      </form>
    </Card>
  );
}

function EditCamera({ cam, onDone }: { cam: Camera; onDone: () => void }) {
  const [name, setName] = useState(cam.name);
  const [type, setType] = useState<SourceType>(cam.source_type);
  const [uri, setUri] = useState(cam.source_type === "VIDEO_FILE" ? cam.source_display : "");
  const [det, setDet] = useState(cam.object_detection);
  const [files, setFiles] = useState<string[]>([]);
  const [err, setErr] = useState<{ message: string; hints?: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.media().then((m) => setFiles(m.files)).catch(() => {}); }, []);
  const meta = TYPES.find((t) => t.value === type)!;
  const keepable = type === cam.source_type && type !== "VIDEO_FILE" && type !== "WEBCAM"; // credentials are hidden, so blank = keep
  const field = "mt-1 block w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm";
  const save = async (ev: React.SyntheticEvent) => {
    ev.preventDefault(); setErr(null);
    if (!uri.trim() && !keepable) return setErr({ message: "Enter the address / choose the file for this source type." });
    setBusy(true);
    try {
      await api.patchCamera(cam.camera_id, { name, source_type: type, ...(uri.trim() ? { source_uri: uri } : {}), object_detection: det });
      onDone();
    } catch (e) { setErr(e instanceof ApiError ? e : { message: "Unexpected error" }); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={save} className="mt-3 grid gap-3 rounded-md border border-slate-200 bg-slate-50 p-3 md:grid-cols-3">
      <label className="text-sm font-medium">Display name
        <input className={field} value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} /></label>
      <label className="text-sm font-medium">Source type
        <select className={field} value={type} onChange={(e) => { setType(e.target.value as SourceType); setUri(e.target.value === "VIDEO_FILE" ? files[0] ?? "" : e.target.value === "WEBCAM" ? "0" : ""); }}>
          {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select></label>
      <label className="text-sm font-medium">{type === "VIDEO_FILE" ? "File" : "Address"}
        {type === "VIDEO_FILE" ? (
          <select className={field} value={uri} onChange={(e) => setUri(e.target.value)}>
            {files.map((f) => <option key={f}>{f}</option>)}</select>
        ) : (
          <input className={field} value={uri} onChange={(e) => setUri(e.target.value)} autoComplete="off"
            placeholder={keepable ? "Leave blank to keep the current address" : meta.placeholder} />)}
      </label>
      <label className="flex items-center gap-2 text-sm md:col-span-3">
        <input type="checkbox" checked={det} onChange={(e) => setDet(e.target.checked)} />
        Detect prohibited objects (visible mobile phones) on this camera
      </label>
      <div className="md:col-span-3">
        <button className={btnPrimary} disabled={busy}>Save changes</button>
        <button type="button" className={`${btnSecondary} ml-2`} onClick={onDone}>Cancel</button>
        <span className="ml-3 text-xs text-slate-500">Seat regions and the empty-room baseline are kept. Recapture the baseline if the new source shows a different view.</span>
        {err && <ErrorBox e={err} />}
      </div>
    </form>
  );
}

function DetectionOverlay({ camId }: { camId: string }) {
  const [tracks, setTracks] = useState<LiveTrack[]>([]);
  useEffect(() => {
    let live = true;
    const tick = () => api.detections(camId).then((d) => { if (live) setTracks(d.tracks); }).catch(() => {});
    tick(); const t = window.setInterval(tick, 700);
    return () => { live = false; clearInterval(t); };
  }, [camId]);
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="Detected objects">
      {tracks.map((t) => (
        <g key={t.tracker_id}>
          <rect x={t.bbox.x1} y={t.bbox.y1} width={t.bbox.x2 - t.bbox.x1} height={t.bbox.y2 - t.bbox.y1} fill="none"
            stroke={t.confirmed ? "#ef4444" : "#facc15"} strokeWidth={0.004} strokeDasharray={t.lost ? "0.01" : undefined} vectorEffect="non-scaling-stroke" />
          <text x={t.bbox.x1} y={Math.max(0.03, t.bbox.y1 - 0.01)} fontSize={0.035} fill="white" stroke="black" strokeWidth={0.003} paintOrder="stroke">
            {t.object_class} {t.confidence.toFixed(2)}{t.confirmed ? "" : " (tentative)"}
          </text>
        </g>))}
    </svg>
  );
}

function CameraCard({ cam, onChange }: { cam: Camera; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<{ message: string; hints?: string[] } | null>(null);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await fn(); onChange(); }
    catch (e) { setErr(e instanceof ApiError ? e : { message: "Unexpected error" }); }
    finally { setBusy(false); }
  };
  const rt = cam.runtime;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold">{cam.name}</h3>
            <StateBadge state={cam.running && rt ? (rt.state as CameraState) : "NOT RUNNING"} />
          </div>
          <p className="truncate text-xs text-slate-500">{cam.camera_id} · {cam.source_type} · {cam.source_display}</p>
          {!cam.object_detection && <p className="mt-1 text-xs text-slate-500">Object detection is off for this camera.</p>}
          {cam.running && rt && rt.analyzers?.filter((a) => a.name === "object_detection").map((a) => (
            <p key={a.name} className="mt-1 text-xs text-slate-600">
              Object detection: {a.model_id} · inference {a.infer_ms_median ?? "—"} ms (p95 {a.infer_ms_p95 ?? "—"}) · processed {a.processed} · skipped while busy {a.dropped} · errors {a.errors}
            </p>))}
          {cam.running && rt && (
            <p className="mt-1 text-xs text-slate-600">
              {rt.fps != null ? `${rt.fps} fps` : "no fps yet"} · frame age {rt.frame_age_s ?? "—"}s · dropped {rt.frames_overwritten} · analysis {rt.analysis_ms} ms
              {rt.quality_issues.length > 0 && ` · quality: ${rt.quality_issues.join(", ")}`}
              {rt.detail && ` · ${rt.detail}`}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {!cam.running && <button className={btnSecondary} disabled={busy} onClick={() => run(async () => setProbe(await api.testCamera(cam.camera_id)))}>Test connection</button>}
          {cam.running
            ? <button className={btnSecondary} disabled={busy} onClick={() => run(() => api.stopCamera(cam.camera_id))}>Stop</button>
            : <button className={btnPrimary} disabled={busy} onClick={() => run(() => api.startCamera(cam.camera_id))}>Start</button>}
          <button className={btnSecondary} disabled={busy || cam.running} title={cam.running ? "Stop the camera to edit it" : "Edit this camera"} onClick={() => setEditing((v) => !v)}>Edit</button>
          <button className={btnDanger} disabled={busy} onClick={() => confirm(`Delete ${cam.name}?`) && run(() => api.deleteCamera(cam.camera_id))}>Delete</button>
        </div>
      </div>
      {editing && !cam.running && <EditCamera cam={cam} onDone={() => { setEditing(false); onChange(); }} />}
      {probe && !cam.running && (probe.ok ? (
        <p className="mt-2 rounded-md bg-emerald-50 p-2 text-sm text-emerald-800">
          Connection OK: {probe.width}×{probe.height}{probe.measured_fps ? `, ~${probe.measured_fps} fps` : ""}, {probe.frames_read} frames in {probe.elapsed_s}s.
          {probe.notes?.map((n) => <span key={n} className="block text-xs text-emerald-900">{n}</span>)}
        </p>) : probe.error && <ErrorBox e={probe.error} />)}
      {err && <ErrorBox e={err} />}
      {cam.running && (
        <div className="mt-3">
          <div className="relative inline-block max-w-full">
            <img src={`/api/cameras/${cam.camera_id}/preview.mjpg`} alt={`Live preview of ${cam.name}`} className="block max-h-72 rounded-md border border-slate-200 bg-slate-900" />
            {cam.object_detection && <DetectionOverlay camId={cam.camera_id} />}
          </div>
          <p className="mt-1 text-xs text-slate-500">Low-rate preview; the last frame is not current if the badge above is not CONNECTED.</p>
        </div>
      )}
    </Card>
  );
}

export default function Cameras({ cameras, refresh }: { cameras: Camera[]; refresh: () => Promise<void> }) {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Camera management</h1>
      <AddCamera onAdded={refresh} />
      {cameras.length === 0 && <p className="text-sm text-slate-500">No cameras yet. Add a phone stream, webcam, or prerecorded video above.</p>}
      <div className="space-y-4">{cameras.map((c) => <CameraCard key={c.camera_id} cam={c} onChange={refresh} />)}</div>
    </div>
  );
}
