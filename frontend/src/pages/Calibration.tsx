import { useEffect, useRef, useState } from "react";
import { Card, SEAT_STYLE, btnDanger, btnPrimary, btnSecondary } from "../components/ui";
import { useOccupancy } from "../hooks/useOccupancy";
import { ApiError, api } from "../services/api";
import type { Camera, Region, Room, RoomDetail, Visibility } from "../types";

export default function Calibration({ cameras, rooms, tick, refresh }: { cameras: Camera[]; rooms: Room[]; tick: string | undefined; refresh: () => Promise<void> }) {
  const [camId, setCamId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [room, setRoom] = useState<RoomDetail | null>(null);
  const [regions, setRegions] = useState<Region[]>([]);
  const [seat, setSeat] = useState("");
  const [vis, setVis] = useState<Visibility>("monitored");
  const [pts, setPts] = useState<[number, number][]>([]);
  const [frameKey, setFrameKey] = useState(0);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [showBase, setShowBase] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const cam = cameras.find((c) => c.camera_id === camId);
  const { occupancy } = useOccupancy(roomId || null, tick);
  const stateOf = Object.fromEntries((occupancy?.seats ?? []).map((s) => [s.seat_id, s.state]));

  useEffect(() => { if (!camId && cameras[0]) setCamId(cameras[0].camera_id); }, [cameras, camId]);
  useEffect(() => { if (!camId) return; api.regions(camId).then((d) => { setRegions(d.regions); if (d.room_id) setRoomId(d.room_id); }).catch(() => setRegions([])); setPts([]); setFrameKey((k) => k + 1); }, [camId]);
  useEffect(() => { if (roomId) api.room(roomId).then((r) => { setRoom(r); setSeat((s) => (r.seats.some((x) => x.seat_id === s) ? s : r.seats[0]?.seat_id ?? "")); }).catch(() => setRoom(null)); else setRoom(null); }, [roomId]);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); setMsg({ ok: true, text: ok }); await refresh(); } catch (e) { setMsg({ ok: false, text: e instanceof ApiError ? e.message : "Failed" }); }
  };
  const click = (e: React.MouseEvent) => {
    if (!box.current || !seat) return;
    const r = box.current.getBoundingClientRect();
    setPts((p) => [...p, [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]]);
  };
  const finish = () => {
    if (pts.length < 3) return setMsg({ ok: false, text: "A region needs at least 3 points." });
    setRegions((rs) => [...rs.filter((r) => r.seat_id !== seat), { seat_id: seat, polygon: pts, visibility: vis }]); setPts([]); setMsg(null);
  };
  const poly = (p: [number, number][]) => p.map(([x, y]) => `${x},${y}`).join(" ");
  const sel = "rounded-md border border-slate-300 px-2 py-1 text-sm";

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Camera-to-seat calibration</h1>
      <Card>
        <div className="flex flex-wrap items-end gap-4 text-sm font-medium">
          <label>Camera<select className={`${sel} ml-2`} value={camId} onChange={(e) => setCamId(e.target.value)}>{cameras.length === 0 && <option value="">No cameras</option>}{cameras.map((c) => <option key={c.camera_id} value={c.camera_id}>{c.name}</option>)}</select></label>
          <label>Room<select className={`${sel} ml-2`} value={roomId} onChange={(e) => setRoomId(e.target.value)}><option value="">— choose —</option>{rooms.map((r) => <option key={r.room_id} value={r.room_id}>{r.name}</option>)}</select></label>
          {cam && !cam.running && <button className={btnPrimary} onClick={() => run(() => api.startCamera(cam.camera_id).then(() => setFrameKey((k) => k + 1)), "Camera started")}>Start camera</button>}
          {cam?.running && <button className={btnSecondary} onClick={() => setFrameKey((k) => k + 1)}>Refresh frame</button>}
        </div>
        {msg && <p role="status" className={`mt-2 text-sm ${msg.ok ? "text-emerald-700" : "text-red-700"}`}>{msg.text}</p>}
      </Card>
      {cam && room && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Card title="1 · Outline each seat on the camera image" action={<span className="text-xs text-slate-500">{pts.length ? `${pts.length} points` : "click to add points"}</span>}>
              {!cam.running ? <p className="text-sm text-slate-500">Start the camera to get a frame to draw on.</p> : (
                <div ref={box} onClick={click} className="relative inline-block max-w-full cursor-crosshair select-none">
                  <img key={frameKey} src={`/api/cameras/${cam.camera_id}/snapshot?k=${frameKey}`} alt="Camera frame for calibration" draggable={false} className="block max-h-[480px] max-w-full rounded-md border border-slate-300" />
                  <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1 1" preserveAspectRatio="none">
                    {regions.map((r) => (
                      <g key={r.seat_id}>
                        <polygon points={poly(r.polygon)} fill={SEAT_STYLE[stateOf[r.seat_id] ?? "UNCERTAIN"].swatch} fillOpacity={0.3} stroke={SEAT_STYLE[stateOf[r.seat_id] ?? "UNCERTAIN"].swatch} strokeWidth={0.004} vectorEffect="non-scaling-stroke" />
                        <text x={r.polygon[0][0]} y={r.polygon[0][1] + 0.03} fontSize={0.03} fill="white" stroke="black" strokeWidth={0.002}>{r.seat_id}</text>
                      </g>))}
                    {pts.length > 0 && <polyline points={poly(pts)} fill="none" stroke="#f43f5e" strokeWidth={0.006} vectorEffect="non-scaling-stroke" />}
                    {pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={0.008} fill="#f43f5e" />)}
                  </svg>
                </div>)}
              <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
                <label>Seat <select className={sel} value={seat} onChange={(e) => { setSeat(e.target.value); setPts([]); }}>{room.seats.map((s) => <option key={s.seat_id}>{s.seat_id}</option>)}</select></label>
                <label>Visibility <select className={sel} value={vis} onChange={(e) => setVis(e.target.value as Visibility)}>
                  <option value="monitored">Fully visible</option><option value="partial">Partially visible</option><option value="not_visible">Not adequately visible</option></select></label>
                <button className={btnSecondary} onClick={finish} disabled={pts.length < 3}>Finish region</button>
                <button className={btnSecondary} onClick={() => setPts([])} disabled={!pts.length}>Clear points</button>
              </div>
            </Card>
          </div>
          <div className="space-y-4">
            <Card title="2 · Regions for this camera">
              {regions.length === 0 ? <p className="text-sm text-slate-500">None yet.</p> : (
                <ul className="divide-y divide-slate-100 text-sm">{regions.map((r) => (
                  <li key={r.seat_id} className="flex items-center justify-between py-1"><span>{r.seat_id} <span className="text-xs text-slate-400">{r.visibility}</span></span>
                    <button className="text-xs text-red-700 underline" onClick={() => setRegions(regions.filter((x) => x.seat_id !== r.seat_id))}>remove</button></li>))}</ul>)}
              <button className={`${btnPrimary} mt-3`} onClick={() => run(() => api.putRegions(cam.camera_id, roomId, regions), "Regions saved (applied live if the camera is running)")}>Save regions</button>
            </Card>
            <Card title="3 · Empty-room baseline">
              <p className="text-xs text-slate-600">Occupancy compares each seat with an image of the <strong>empty</strong> room. Capture it with nobody in view, in the same lighting as the exam. Recapture if the camera moves or lighting changes.</p>
              <p className="mt-2 text-xs">Status: {cam.baseline_at ? `captured ${new Date(cam.baseline_at).toLocaleString()}` : <span className="font-medium text-amber-700">not captured: seats will show UNCERTAIN</span>}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button className={btnPrimary} disabled={!cam.running || cam.runtime?.state !== "CONNECTED"}
                  onClick={() => confirm("Is the room completely empty (no people in the camera's view)?") && run(() => api.captureBaseline(cam.camera_id), "Baseline captured")}>Capture baseline</button>
                {cam.baseline_at && <><button className={btnSecondary} onClick={() => setShowBase((v) => !v)}>{showBase ? "Hide" : "View"}</button>
                  <button className={btnDanger} onClick={() => run(() => api.deleteBaseline(cam.camera_id), "Baseline removed")}>Remove</button></>}
              </div>
              {showBase && cam.baseline_at && <img src={`/api/cameras/${cam.camera_id}/baseline?t=${cam.baseline_at}`} alt="Stored empty-room baseline" className="mt-3 w-full rounded border border-slate-300" />}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
