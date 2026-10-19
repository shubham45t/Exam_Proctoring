import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { Occupancy } from "../types";

/** Polls occupancy and also refreshes immediately whenever a live event arrives (`tick`). */
export function useOccupancy(roomId: string | null, tick: string | undefined) {
  const [data, setData] = useState<Occupancy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!roomId) { setData(null); return; }
    try { setData(await api.occupancy(roomId)); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Failed to load occupancy"); }
  }, [roomId]);
  useEffect(() => { void load(); const t = window.setInterval(load, 3000); return () => clearInterval(t); }, [load]);
  useEffect(() => { void load(); }, [tick, load]);
  return { occupancy: data, error, reload: load };
}
