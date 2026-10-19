import { useEffect, useState } from "react";
import { Card, StateBadge, btnSecondary } from "../components/ui";
import { api } from "../services/api";
import { useOccupancy } from "../hooks/useOccupancy";
import type { Camera, LiveTrack, ReviewAlert, Room } from "../types";

export default function LiveMonitoring({
  cameras,
  rooms,
  tick,
  onNavigateToAlert,
}: {
  cameras: Camera[];
  rooms: Room[];
  tick: string | undefined;
  onNavigateToAlert?: (alertId: string) => void;
}) {
  const [selectedCamId, setSelectedCamId] = useState<string>(cameras[0]?.camera_id ?? "");
  const [frameKey, setFrameKey] = useState<number>(0);
  const [liveTracks, setLiveTracks] = useState<LiveTrack[]>([]);
  const [showOverlays, setShowOverlays] = useState<boolean>(true);
  const [recentAlert, setRecentAlert] = useState<ReviewAlert | null>(null);
  const [flagSuccess, setFlagSuccess] = useState<string | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<string>(rooms[0]?.room_id ?? "");

  const activeCam = cameras.find((c) => c.camera_id === selectedCamId) ?? cameras[0];
  const { occupancy } = useOccupancy(selectedRoomId || null, tick);

  // Auto-refresh frame snapshot at preview rate when running
  useEffect(() => {
    if (!activeCam || !activeCam.running) return;
    const interval = setInterval(() => {
      setFrameKey((k) => k + 1);
    }, 400); // 2.5 fps preview refresh
    return () => clearInterval(interval);
  }, [activeCam?.camera_id, activeCam?.running]);

  // Poll detections for active camera
  useEffect(() => {
    if (!activeCam || !activeCam.running) {
      setLiveTracks([]);
      return;
    }
    const interval = setInterval(() => {
      api.detections(activeCam.camera_id)
        .then((res) => setLiveTracks(res.tracks))
        .catch(() => {});
    }, 600);
    return () => clearInterval(interval);
  }, [activeCam?.camera_id, activeCam?.running]);

  // Poll recent high-priority alerts
  useEffect(() => {
    api.alerts("NEW")
      .then((res) => {
        if (res.items.length > 0) {
          setRecentAlert(res.items[0]);
        }
      })
      .catch(() => {});
  }, [tick]);

  const handleManualFlag = async () => {
    try {
      await api.syntheticEvent(activeCam?.camera_id);
      setFlagSuccess("Candidate incident observation flagged for review.");
      setTimeout(() => setFlagSuccess(null), 4000);
    } catch {
      setFlagSuccess("Flag failed.");
    }
  };

  return (
    <div className="space-y-6">
      {/* Real-time Alert Banner */}
      {recentAlert && (
        <div
          role="alert"
          className="flex items-center justify-between rounded-xl border border-red-300 bg-red-50 p-4 shadow-sm text-red-900 transition-all animate-pulse"
        >
          <div className="flex items-center gap-3">
            <span className="flex h-3 w-3 rounded-full bg-red-600" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-red-700">Immediate Proctor Attention</span>
                <span className="rounded bg-red-200 px-1.5 py-0.5 text-[10px] font-bold text-red-800">
                  {recentAlert.priority.toUpperCase()} PRIORITY
                </span>
              </div>
              <p className="text-sm font-semibold">{recentAlert.title} &middot; {recentAlert.summary}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {onNavigateToAlert && (
              <button
                onClick={() => onNavigateToAlert(recentAlert.alert_id)}
                className="rounded-lg bg-red-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-900 shadow-sm"
              >
                Inspect Evidence
              </button>
            )}
            <button
              onClick={() => setRecentAlert(null)}
              className="text-xs text-red-600 hover:text-red-800 px-2 py-1"
            >
              Dismiss Banner
            </button>
          </div>
        </div>
      )}

      {/* Main Monitoring Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Live Exam Monitoring Console</h1>
          <p className="text-xs text-slate-500">Real-time camera observation feeds with computer vision tracking overlays.</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg px-3 py-1.5 shadow-sm cursor-pointer">
            <input
              type="checkbox"
              checked={showOverlays}
              onChange={(e) => setShowOverlays(e.target.checked)}
              className="rounded text-sky-600 focus:ring-sky-500"
            />
            Show Detection Overlays
          </label>
          <button
            onClick={handleManualFlag}
            className={btnSecondary}
            disabled={!activeCam?.running}
          >
            Flag Frame for Review
          </button>
        </div>
      </div>

      {flagSuccess && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-2 text-xs text-emerald-800">
          {flagSuccess}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main Video Player (2 Cols) */}
        <div className="lg:col-span-2 space-y-4">
          <Card
            title={activeCam ? `Live Feed: ${activeCam.name}` : "No Camera Selected"}
            action={
              activeCam && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">{activeCam.runtime?.fps ? `${activeCam.runtime.fps} fps` : ""}</span>
                  <StateBadge state={activeCam.running && activeCam.runtime ? activeCam.runtime.state : "NOT RUNNING"} />
                </div>
              )
            }
          >
            {activeCam ? (
              <div className="relative inline-block w-full overflow-hidden rounded-lg bg-slate-950 aspect-video flex items-center justify-center">
                {activeCam.running ? (
                  <>
                    <img
                      key={frameKey}
                      src={`/api/cameras/${activeCam.camera_id}/snapshot?k=${frameKey}`}
                      alt="Live camera stream"
                      className="w-full h-full object-contain"
                    />

                    {/* Detection Box Overlays */}
                    {showOverlays &&
                      liveTracks.map((tr) => (
                        <div
                          key={tr.tracker_id}
                          className={`absolute border-2 transition-all ${
                            tr.object_class === "cell phone" ? "border-red-500 bg-red-500/10" : "border-emerald-400 bg-emerald-400/10"
                          }`}
                          style={{
                            left: `${tr.bbox.x1 * 100}%`,
                            top: `${tr.bbox.y1 * 100}%`,
                            width: `${(tr.bbox.x2 - tr.bbox.x1) * 100}%`,
                            height: `${(tr.bbox.y2 - tr.bbox.y1) * 100}%`,
                          }}
                        >
                          <span className="absolute -top-5 left-0 rounded bg-slate-900/90 px-1 py-0.5 text-[9px] font-bold text-white uppercase tracking-wider">
                            {tr.object_class} #{tr.tracker_id} &middot; {(tr.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      ))}

                    {/* Active Tracks HUD indicator */}
                    <div className="absolute top-2 right-2 flex items-center gap-1.5 rounded-full bg-slate-900/80 px-2.5 py-1 text-[10px] text-white backdrop-blur">
                      <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                      <span>{liveTracks.length} active target{liveTracks.length === 1 ? "" : "s"}</span>
                    </div>
                  </>
                ) : (
                  <div className="text-center p-8 text-slate-400">
                    <p className="text-sm font-medium">Camera is currently stopped.</p>
                    <p className="text-xs mt-1">Start this camera on the Cameras page to resume streaming.</p>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-slate-500 py-6 text-center">No camera registered. Add a camera in the Cameras tab.</p>
            )}

            {/* Camera Switcher Bar */}
            <div className="mt-4 flex flex-wrap gap-2 pt-2 border-t border-slate-100">
              <span className="text-xs font-semibold uppercase text-slate-400 self-center mr-2">Feeds:</span>
              {cameras.map((c) => (
                <button
                  key={c.camera_id}
                  onClick={() => setSelectedCamId(c.camera_id)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                    (selectedCamId || cameras[0]?.camera_id) === c.camera_id
                      ? "bg-slate-900 text-white shadow-sm"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  {c.name} {c.running ? "●" : "○"}
                </button>
              ))}
            </div>
          </Card>
        </div>

        {/* Room Occupancy Mini-HUD (1 Col) */}
        <div className="space-y-4">
          <Card
            title="Workstation Status"
            action={
              <select
                className="rounded border border-slate-300 px-2 py-0.5 text-xs font-normal"
                value={selectedRoomId}
                onChange={(e) => setSelectedRoomId(e.target.value)}
              >
                {rooms.map((r) => (
                  <option key={r.room_id} value={r.room_id}>
                    {r.name}
                  </option>
                ))}
              </select>
            }
          >
            {occupancy ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2 text-center">
                  <div className="rounded-lg bg-slate-50 p-2 border border-slate-100">
                    <div className="text-lg font-bold text-sky-700">{occupancy.summary.occupied}</div>
                    <div className="text-[10px] uppercase font-semibold text-slate-500">Occupied</div>
                  </div>
                  <div className="rounded-lg bg-slate-50 p-2 border border-slate-100">
                    <div className="text-lg font-bold text-emerald-700">{occupancy.summary.vacant}</div>
                    <div className="text-[10px] uppercase font-semibold text-slate-500">Vacant</div>
                  </div>
                </div>

                <div className="border-t border-slate-100 pt-3">
                  <div className="text-xs font-semibold text-slate-700 mb-2">Room Seat Map Overview</div>
                  <div className="grid grid-cols-4 gap-1.5 max-h-48 overflow-y-auto p-1">
                    {occupancy.seats.map((st) => (
                      <div
                        key={st.seat_id}
                        className={`rounded p-1.5 text-center text-[10px] font-bold border transition-all ${
                          st.state === "OCCUPIED"
                            ? "bg-sky-600 text-white border-sky-700"
                            : st.state === "VACANT"
                            ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                            : "bg-amber-100 text-amber-800 border-amber-300"
                        }`}
                        title={`Seat ${st.seat_id}: ${st.state}`}
                      >
                        {st.seat_id}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-500">Select a room with configured seats to view occupancy status.</p>
            )}
          </Card>

          {/* Guidelines Reminder Card */}
          <Card title="Proctoring Protocol">
            <ul className="list-disc pl-4 space-y-1.5 text-xs text-slate-600">
              <li>Computer vision detections are automated review recommendations.</li>
              <li>A high-priority alert does not confirm misconduct without proctor review.</li>
              <li>Verify student environment and physical desk space in person if alerted.</li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
