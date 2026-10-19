import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import type { ApiEvent, Camera, SystemStatus, WsMessage } from "../types";

export type Connection = "connecting" | "live" | "reconnecting";

/** Loads a REST snapshot, then applies WebSocket updates. Every (re)connect re-fetches the
 *  snapshot so nothing is missed during a disconnect (the hub drops messages for dead clients). */
export function useLive() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [events, setEvents] = useState<ApiEvent[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [conn, setConn] = useState<Connection>("connecting");
  const [error, setError] = useState<string | null>(null);
  const closed = useRef(false);

  const snapshot = useCallback(async () => {
    try {
      const [c, e, s] = await Promise.all([api.cameras(), api.events(50), api.status()]);
      setCameras(c); setEvents(e.items); setStatus(s); setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    }
  }, []);

  useEffect(() => {
    closed.current = false;
    let ws: WebSocket | null = null;
    let retry = 0;
    let timer: number | undefined;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => { retry = 0; setConn("live"); void snapshot(); };
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data) as WsMessage;
        if (msg.type === "hello") return;
        const d = msg.data as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
        const ev: ApiEvent = {
          event_id: d.event_id, event_type: d.event_type, camera_id: d.camera_id ?? null,
          seat_id: d.seat_id ?? null, timestamp: d.timestamp, is_synthetic: !!d.is_synthetic, payload: d,
        };
        setEvents((prev) => [ev, ...prev.filter((p) => p.event_id !== ev.event_id)].slice(0, 200));
        if (msg.type === "camera_status") void api.cameras().then(setCameras).catch(() => {});
      };
      ws.onclose = () => {
        if (closed.current) return;
        setConn("reconnecting");
        const delay = Math.min(1000 * 2 ** retry++, 15000);
        timer = window.setTimeout(connect, delay);
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    void snapshot();
    const poll = window.setInterval(() => { void api.status().then(setStatus).catch(() => {}); }, 5000);
    return () => { closed.current = true; clearTimeout(timer); clearInterval(poll); ws?.close(); };
  }, [snapshot]);

  return { cameras, events, status, conn, error, refresh: snapshot, setCameras };
}
