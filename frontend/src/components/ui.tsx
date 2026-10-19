import type { CameraState } from "../types";

const COLORS: Record<CameraState, string> = {
  CONNECTED: "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
  CONNECTING: "bg-sky-100 text-sky-800 ring-sky-600/20",
  DEGRADED: "bg-amber-100 text-amber-900 ring-amber-600/30",
  STALE: "bg-orange-100 text-orange-900 ring-orange-600/30",
  FROZEN: "bg-orange-100 text-orange-900 ring-orange-600/30",
  RECONNECTING: "bg-sky-100 text-sky-800 ring-sky-600/20",
  FAILED: "bg-red-100 text-red-800 ring-red-600/20",
  STOPPED: "bg-slate-100 text-slate-700 ring-slate-500/20",
};

export function StateBadge({ state }: { state: CameraState | "NOT RUNNING" }) {
  const cls = state === "NOT RUNNING" ? COLORS.STOPPED : COLORS[state];
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}>{state}</span>;
}

export const DemoBadge = () => (
  <span className="rounded bg-fuchsia-100 px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-fuchsia-800 ring-1 ring-fuchsia-600/30">DEMO DATA</span>
);

export function Card({ title, children, action }: { title?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      {title && (
        <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>{action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export const Stat = ({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) => (
  <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
    <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
    <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
    {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
  </div>
);

export const btn =
  "inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 disabled:opacity-50";
export const btnPrimary = `${btn} bg-slate-900 text-white hover:bg-slate-700`;
export const btnSecondary = `${btn} border border-slate-300 bg-white text-slate-800 hover:bg-slate-50`;
export const btnDanger = `${btn} border border-red-300 bg-white text-red-700 hover:bg-red-50`;

import type { SeatState } from "../types";
export const SEAT_STYLE: Record<SeatState, { bg: string; ring: string; label: string; swatch: string }> = {
  OCCUPIED: { bg: "bg-sky-600 text-white", ring: "ring-sky-700", label: "Occupied", swatch: "#0284c7" },
  VACANT: { bg: "bg-emerald-100 text-emerald-900", ring: "ring-emerald-500", label: "Vacant", swatch: "#10b981" },
  UNCERTAIN: { bg: "bg-amber-200 text-amber-900", ring: "ring-amber-500", label: "Uncertain", swatch: "#f59e0b" },
  OCCLUDED: { bg: "bg-violet-200 text-violet-900", ring: "ring-violet-500", label: "Occluded", swatch: "#8b5cf6" },
  UNMONITORED: { bg: "bg-slate-200 text-slate-600", ring: "ring-slate-400", label: "Unmonitored", swatch: "#94a3b8" },
};

export function Legend() {
  return (
    <ul className="flex flex-wrap gap-3 text-xs text-slate-600" aria-label="Seat state legend">
      {(Object.keys(SEAT_STYLE) as SeatState[]).map((k) => (
        <li key={k} className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: SEAT_STYLE[k].swatch }} />{SEAT_STYLE[k].label}</li>
      ))}
    </ul>
  );
}
