import { useEffect, useState } from "react";
import type { Connection } from "../hooks/useLive";
import { api, setToken } from "../services/api";
import type { User } from "../types";

export type PageId =
  | "dashboard"
  | "monitoring"
  | "cameras"
  | "rooms"
  | "calibration"
  | "examinations"
  | "alerts"
  | "reports";

interface NavItem {
  id: PageId;
  label: string;
  icon: string;
  badge?: number;
}

const CONN_STYLE: Record<Connection, string> = {
  live: "bg-emerald-500 ring-2 ring-emerald-500/20",
  connecting: "bg-sky-500 animate-pulse",
  reconnecting: "bg-amber-500 animate-ping",
};

export default function Shell({
  page,
  onNav,
  conn,
  newAlertsCount = 0,
  children,
}: {
  page: PageId;
  onNav: (p: PageId) => void;
  conn: Connection;
  newAlertsCount?: number;
  children: React.ReactNode;
}) {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);

  useEffect(() => {
    api.me()
      .then(setCurrentUser)
      .catch(() => {
        // default fallback proctor in dev
        setCurrentUser({
          user_id: "USR-PROC001",
          username: "proctor",
          full_name: "Dr. Jane Smith (Proctor)",
          role: "proctor",
          is_active: true,
        });
      });
    api.users().then(setUsers).catch(() => {});
  }, []);

  const handleSwitchUser = async (username: string) => {
    try {
      // login as chosen role demo account
      const pwd = username === "admin" ? "admin123" : username === "auditor" ? "auditor123" : "proctor123";
      const res = await api.login(username, pwd);
      setToken(res.token);
      setCurrentUser(res.user);
    } catch {
      // ignore
    }
  };

  const navItems: NavItem[] = [
    { id: "dashboard", label: "Dashboard", icon: "📊" },
    { id: "monitoring", label: "Live Monitoring", icon: "📹" },
    { id: "alerts", label: "Alerts & Review", icon: "🚨", badge: newAlertsCount },
    { id: "examinations", label: "Examinations", icon: "📝" },
    { id: "rooms", label: "Rooms & Seat Map", icon: "🏛️" },
    { id: "calibration", label: "Calibration", icon: "🎯" },
    { id: "cameras", label: "Cameras", icon: "📷" },
    { id: "reports", label: "Audit Reports", icon: "📋" },
  ];

  return (
    <div className="flex min-h-screen bg-slate-50 font-sans antialiased text-slate-900">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 bg-slate-950 p-4 text-slate-300 flex flex-col justify-between border-r border-slate-900">
        <div>
          {/* Logo & Brand Header */}
          <div className="mb-6 px-3 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500 font-extrabold text-white text-base shadow-lg shadow-sky-500/30">
                Ω
              </span>
              <div>
                <div className="text-base font-bold tracking-tight text-white leading-tight">OmniProctor</div>
                <div className="text-[10px] uppercase font-semibold text-sky-400 tracking-wider">Review Console</div>
              </div>
            </div>
            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9px] font-mono text-slate-400 border border-slate-700">
              v1.0
            </span>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1" aria-label="Main">
            {navItems.map((n) => {
              const active = page === n.id;
              return (
                <button
                  key={n.id}
                  onClick={() => onNav(n.id)}
                  aria-current={active ? "page" : undefined}
                  className={`group flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-xs font-semibold transition-all ${
                    active
                      ? "bg-sky-600 text-white shadow-md shadow-sky-600/30"
                      : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <span className="text-sm">{n.icon}</span>
                    <span>{n.label}</span>
                  </div>
                  {n.badge !== undefined && n.badge > 0 && (
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                        active ? "bg-white text-sky-700" : "bg-red-500 text-white animate-pulse"
                      }`}
                    >
                      {n.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* User Role Card at bottom */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-3 text-xs">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Active Operator</span>
            <span className="rounded-full bg-sky-950 border border-sky-800/80 px-2 py-0.5 text-[9px] font-bold uppercase text-sky-300">
              {currentUser?.role ?? "Proctor"}
            </span>
          </div>
          <div className="font-semibold text-white truncate">{currentUser?.full_name ?? "Proctor on Duty"}</div>
          
          <div className="mt-2 pt-2 border-t border-slate-800 flex items-center justify-between">
            <span className="text-[10px] text-slate-500">Switch Persona:</span>
            <select
              className="bg-slate-950 border border-slate-700 rounded px-1.5 py-0.5 text-[10px] text-slate-300 focus:outline-none"
              value={currentUser?.username ?? "proctor"}
              onChange={(e) => handleSwitchUser(e.target.value)}
            >
              <option value="proctor">Proctor (Jane)</option>
              <option value="admin">Chief Admin</option>
              <option value="auditor">Auditor</option>
              {users
                .filter((u) => !["proctor", "admin", "auditor"].includes(u.username))
                .map((u) => (
                  <option key={u.user_id} value={u.username}>
                    {u.full_name} ({u.role})
                  </option>
                ))}
            </select>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Header Bar */}
        <header className="flex items-center justify-between border-b border-slate-200/90 bg-white/80 backdrop-blur px-8 py-3.5 sticky top-0 z-10">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-700">OmniProctor Algorithmic Review System</span>
            <span className="text-slate-300">&middot;</span>
            <span className="text-xs text-slate-500">Official Institutional Human-in-the-Loop Mode</span>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs font-medium text-slate-600" role="status">
              <span className={`h-2.5 w-2.5 rounded-full ${CONN_STYLE[conn]}`} />
              <span>{conn === "live" ? "System Live & Streaming" : conn === "connecting" ? "Connecting…" : "Reconnecting…"}</span>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-8 max-w-7xl w-full mx-auto">{children}</main>
      </div>
    </div>
  );
}
