import { useEffect, useState } from "react";
import { Card, Legend, SEAT_STYLE, Stat, StateBadge, btnPrimary, btnSecondary } from "../components/ui";
import { useOccupancy } from "../hooks/useOccupancy";
import { ApiError, api } from "../services/api";
import type { ApiEvent, CameraState, FusedSeat, RoomDetail, Room, Seat } from "../types";

function NewRoom({ onCreated }: { onCreated: (r: RoomDetail) => void }) {
  const [f, setF] = useState({ name: "", width_m: 10, depth_m: 8, rows: 4, cols: 6 });
  const [err, setErr] = useState<string | null>(null);
  const inp = "mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm";
  const num = (k: "width_m" | "depth_m" | "rows" | "cols") => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: Number(e.target.value) });
  return (
    <Card title="New room">
      <form className="grid grid-cols-2 gap-2 text-sm font-medium md:grid-cols-6" onSubmit={async (e) => {
        e.preventDefault(); setErr(null);
        try { onCreated(await api.createRoom({ name: f.name, width_m: f.width_m, depth_m: f.depth_m, generate: { rows: f.rows, cols: f.cols } })); setF({ ...f, name: "" }); }
        catch (x) { setErr(x instanceof ApiError ? x.message : "Failed"); }
      }}>
        <label className="col-span-2">Name<input className={inp} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label>Width (m)<input className={inp} type="number" min={1} step={0.5} value={f.width_m} onChange={num("width_m")} /></label>
        <label>Depth (m)<input className={inp} type="number" min={1} step={0.5} value={f.depth_m} onChange={num("depth_m")} /></label>
        <label>Rows<input className={inp} type="number" min={1} max={30} value={f.rows} onChange={num("rows")} /></label>
        <label>Columns<input className={inp} type="number" min={1} max={30} value={f.cols} onChange={num("cols")} /></label>
        <div className="col-span-2 md:col-span-6"><button className={btnPrimary}>Create room with seat grid</button>
          {err && <span role="alert" className="ml-3 text-sm text-red-700">{err}</span>}</div>
      </form>
    </Card>
  );
}

function SeatPanel({ room, seat, fused, onSaved }: { room: RoomDetail; seat: Seat; fused: FusedSeat | undefined; onSaved: () => void }) {
  const [events, setEvents] = useState<ApiEvent[]>([]);
  const [draft, setDraft] = useState(seat);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { setDraft(seat); setMsg(null); api.events(8, `&seat_id=${encodeURIComponent(seat.seat_id)}&event_type=occupancy`).then((p) => setEvents(p.items)).catch(() => setEvents([])); }, [seat, fused?.state]);
  const save = async () => {
    try { await api.putSeats(room.room_id, room.seats.map((s) => (s.seat_id === seat.seat_id ? draft : s))); setMsg("Saved"); onSaved(); }
    catch (e) { setMsg(e instanceof ApiError ? e.message : "Save failed"); }
  };
  const num = "w-20 rounded border border-slate-300 px-1 py-0.5";
  return (
    <Card title={`Seat ${seat.seat_id}`}>
      <dl className="space-y-1 text-sm">
        <div className="flex justify-between"><dt className="text-slate-500">State</dt><dd className="font-medium">{fused ? SEAT_STYLE[fused.state].label : "—"}</dd></div>
        {fused?.reason && <div className="text-xs text-slate-600">Reason: {fused.reason}</div>}
        {fused && fused.confidence > 0 && <div className="text-xs text-slate-500">Heuristic score {fused.confidence.toFixed(2)} (not a probability)</div>}
        <div className="pt-2 text-xs font-semibold uppercase text-slate-500">Cameras</div>
        {fused?.cameras.length ? fused.cameras.map((c) => (
          <div key={c.camera_id} className="text-xs text-slate-600">{c.camera_id} · {c.visibility}{c.state ? ` · ${c.state}` : ""}{c.age_s != null ? ` · ${c.age_s}s ago` : ""}</div>
        )) : <div className="text-xs text-slate-500">No camera covers this seat.</div>}
        <div className="pt-2 text-xs font-semibold uppercase text-slate-500">Recent observations</div>
        {events.length ? events.map((e) => (
          <div key={e.event_id} className="text-xs text-slate-600">{new Date(e.timestamp).toLocaleTimeString()} · {String(e.payload.state)}</div>
        )) : <div className="text-xs text-slate-500">None recorded.</div>}
      </dl>
      <div className="mt-3 space-y-2 border-t border-slate-100 pt-3 text-xs">
        <div className="flex items-center gap-2">x <input className={num} type="number" step={0.01} min={0} max={1} value={draft.x} onChange={(e) => setDraft({ ...draft, x: Number(e.target.value) })} />
          y <input className={num} type="number" step={0.01} min={0} max={1} value={draft.y} onChange={(e) => setDraft({ ...draft, y: Number(e.target.value) })} /></div>
        <label className="flex items-center gap-2"><input type="checkbox" checked={draft.monitored} onChange={(e) => setDraft({ ...draft, monitored: e.target.checked })} />Monitored</label>
        <button className={btnSecondary} onClick={save}>Save seat</button>{msg && <span className="ml-2 text-slate-600">{msg}</span>}
      </div>
    </Card>
  );
}

export default function Rooms({ tick, rooms, reloadRooms }: { tick: string | undefined; rooms: Room[]; reloadRooms: () => void }) {
  const [roomId, setRoomId] = useState<string | null>(null);
  const [room, setRoom] = useState<RoomDetail | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const { occupancy, error } = useOccupancy(roomId, tick);
  useEffect(() => { if (!roomId && rooms[0]) setRoomId(rooms[0].room_id); }, [rooms, roomId]);
  const loadRoom = () => { if (roomId) api.room(roomId).then(setRoom).catch(() => setRoom(null)); };
  useEffect(loadRoom, [roomId]); // eslint-disable-line react-hooks/exhaustive-deps
  const fused = Object.fromEntries((occupancy?.seats ?? []).map((s) => [s.seat_id, s]));
  const sm = occupancy?.summary;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Rooms &amp; seat map</h1>
        <select aria-label="Select room" className="rounded-md border border-slate-300 px-2 py-1 text-sm" value={roomId ?? ""} onChange={(e) => { setRoomId(e.target.value); setSel(null); }}>
          {rooms.length === 0 && <option value="">No rooms yet</option>}
          {rooms.map((r) => <option key={r.room_id} value={r.room_id}>{r.name} ({r.seat_count} seats)</option>)}
        </select>
      </div>
      <NewRoom onCreated={(r) => { reloadRooms(); setRoomId(r.room_id); }} />
      {error && <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      {room && sm && (
        <>
          <div className="grid grid-cols-3 gap-3 lg:grid-cols-6">
            <Stat label="Total seats" value={sm.total} /><Stat label="Occupied" value={sm.occupied} /><Stat label="Vacant" value={sm.vacant} />
            <Stat label="Uncertain" value={sm.uncertain} /><Stat label="Occluded" value={sm.occluded} /><Stat label="Unmonitored" value={sm.unmonitored} />
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-3 lg:col-span-2">
              <Card title={`${room.name} · ${room.width_m} m × ${room.depth_m} m`} action={<Legend />}>
                <div className="relative mx-auto w-full rounded-md border border-slate-300 bg-slate-50" style={{ aspectRatio: `${room.width_m} / ${room.depth_m}`, maxHeight: 460 }}>
                  <div className="absolute left-1/2 top-0 -translate-x-1/2 rounded-b bg-slate-300 px-2 text-[10px] text-slate-700">front</div>
                  {room.seats.map((s) => {
                    const st = SEAT_STYLE[fused[s.seat_id]?.state ?? "UNCERTAIN"];
                    return (
                      <button key={s.seat_id} onClick={() => setSel(s.seat_id)} title={`${s.seat_id}: ${st.label}`}
                        aria-label={`Seat ${s.seat_id}, ${st.label}`} aria-pressed={sel === s.seat_id}
                        className={`absolute flex h-9 w-11 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded text-[10px] font-medium ring-1 ${st.bg} ${st.ring} ${sel === s.seat_id ? "ring-4" : ""}`}
                        style={{ left: `${s.x * 100}%`, top: `${s.y * 100}%` }}>{s.seat_id}</button>
                    );
                  })}
                </div>
                <p className="mt-2 text-xs text-slate-500">Method: {occupancy.method}. A change-from-empty-room heuristic: bags, shadows or lighting changes can mimic occupancy. Treat as a guide, not a count of record. UNCERTAIN means “cannot tell right now” (camera stopped/unhealthy, no baseline, or disagreement).</p>
              </Card>
              <Card title="Camera coverage">
                {occupancy.cameras.length === 0 ? <p className="text-sm text-slate-500">No camera is calibrated to this room yet. Use Calibration.</p> : (
                  <ul className="divide-y divide-slate-100 text-sm">{occupancy.cameras.map((c) => (
                    <li key={c.camera_id} className="flex items-center justify-between py-1.5">
                      <span>{c.name} <span className="text-xs text-slate-400">covers {c.seats_covered} seats · baseline {c.baseline_at ? new Date(c.baseline_at).toLocaleString() : "NOT captured"}</span></span>
                      <StateBadge state={c.running && c.state ? (c.state as CameraState) : "NOT RUNNING"} />
                    </li>))}</ul>)}
              </Card>
            </div>
            <div>{sel && room.seats.find((s) => s.seat_id === sel)
              ? <SeatPanel room={room} seat={room.seats.find((s) => s.seat_id === sel)!} fused={fused[sel]} onSaved={loadRoom} />
              : <Card title="Seat details"><p className="text-sm text-slate-500">Select a seat on the map.</p></Card>}</div>
          </div>
        </>
      )}
    </div>
  );
}
