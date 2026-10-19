import { useEffect, useState } from "react";
import { Card, DemoBadge, btnPrimary } from "../components/ui";
import { api, ApiError } from "../services/api";
import type { AlertDetail, ReviewAlert } from "../types";

export default function AlertsReview({
  initialAlertId,
  tick,
}: {
  initialAlertId?: string;
  tick: string | undefined;
}) {
  const [alerts, setAlerts] = useState<ReviewAlert[]>([]);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(initialAlertId ?? null);
  const [detail, setDetail] = useState<AlertDetail | null>(null);
  const [filterPriority, setFilterPriority] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [decision, setDecision] = useState<"ACKNOWLEDGE" | "DISMISS" | "REFER">("ACKNOWLEDGE");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitMessage, setSubmitMessage] = useState<string | null>(null);

  const loadAlerts = () => {
    setLoadingList(true);
    const p = filterPriority !== "all" ? filterPriority : undefined;
    const s = filterStatus !== "all" ? filterStatus : undefined;
    api.alerts(s, p)
      .then((res) => {
        setAlerts(res.items);
        if (!selectedAlertId && res.items.length > 0) {
          setSelectedAlertId(res.items[0].alert_id);
        }
      })
      .catch(() => {})
      .finally(() => setLoadingList(false));
  };

  useEffect(() => {
    loadAlerts();
  }, [filterPriority, filterStatus, tick]);

  useEffect(() => {
    if (initialAlertId) setSelectedAlertId(initialAlertId);
  }, [initialAlertId]);

  useEffect(() => {
    if (!selectedAlertId) {
      setDetail(null);
      return;
    }
    setLoadingDetail(true);
    setSubmitMessage(null);
    api.alert(selectedAlertId)
      .then((d) => setDetail(d))
      .catch(() => setDetail(null))
      .finally(() => setLoadingDetail(false));
  }, [selectedAlertId]);

  const handleSubmitReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAlertId) return;
    setSubmitting(true);
    setSubmitMessage(null);
    try {
      const res = await api.reviewAlert(selectedAlertId, decision, notes);
      setDetail(res);
      setSubmitMessage(`Review successfully recorded as ${decision}.`);
      setNotes("");
      loadAlerts();
    } catch (err) {
      setSubmitMessage(err instanceof ApiError ? err.message : "Review submission failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const priorityColor = (p: string) => {
    if (p === "high") return "bg-red-100 text-red-800 ring-red-600/30";
    if (p === "medium") return "bg-amber-100 text-amber-800 ring-amber-600/30";
    return "bg-sky-100 text-sky-800 ring-sky-600/30";
  };

  const statusColor = (s: string) => {
    if (s === "NEW") return "bg-rose-600 text-white animate-pulse";
    if (s === "ACKNOWLEDGED") return "bg-emerald-600 text-white";
    if (s === "DISMISSED") return "bg-slate-500 text-white";
    return "bg-purple-600 text-white";
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Proctor Incident Review Console</h1>
          <p className="text-xs text-slate-500">Evaluate automated candidate incident recommendations, inspect photographic evidence, and log decisions.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium bg-white"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="all">All Statuses</option>
            <option value="NEW">New (Unreviewed)</option>
            <option value="ACKNOWLEDGED">Acknowledged</option>
            <option value="DISMISSED">Dismissed</option>
            <option value="REFERRED">Referred</option>
          </select>
          <select
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium bg-white"
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value)}
          >
            <option value="all">All Priorities</option>
            <option value="high">High Priority</option>
            <option value="medium">Medium Priority</option>
            <option value="low">Low Priority</option>
          </select>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-12">
        {/* Left Column: Alert Feed List (4 cols) */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Candidate Incidents ({alerts.length})
            </span>
            {loadingList && <span className="text-xs text-slate-400">Refreshing...</span>}
          </div>

          <div className="space-y-2 max-h-[750px] overflow-y-auto pr-1">
            {alerts.length === 0 ? (
              <Card>
                <p className="text-xs text-slate-500 py-6 text-center">No alerts matching filter criteria.</p>
              </Card>
            ) : (
              alerts.map((alt) => (
                <div
                  key={alt.alert_id}
                  onClick={() => setSelectedAlertId(alt.alert_id)}
                  className={`cursor-pointer rounded-xl border p-3.5 transition-all ${
                    selectedAlertId === alt.alert_id
                      ? "border-sky-600 bg-sky-50/40 shadow-sm ring-1 ring-sky-600/30"
                      : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/60"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-semibold text-slate-900 text-sm leading-snug">{alt.title}</div>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${statusColor(alt.status)}`}>
                      {alt.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-600 line-clamp-2">{alt.summary}</p>
                  <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-400">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ring-1 ring-inset ${priorityColor(alt.priority)}`}>
                      {alt.priority.toUpperCase()} PRIORITY
                    </span>
                    {alt.is_synthetic && <DemoBadge />}
                    <time>{new Date(alt.created_at).toLocaleTimeString()}</time>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Column: Detailed Review Workspace (7 cols) */}
        <div className="lg:col-span-7">
          {loadingDetail ? (
            <Card>
              <p className="text-sm text-slate-500 py-12 text-center">Loading incident details and evidence...</p>
            </Card>
          ) : detail ? (
            <div className="space-y-4">
              <Card
                title={detail.alert.title}
                action={
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${statusColor(detail.alert.status)}`}>
                    {detail.alert.status}
                  </span>
                }
              >
                {/* Official Ethical Notice Banner */}
                <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900 mb-4">
                  <p className="font-semibold">{detail.alert.notice}</p>
                </div>

                {/* Score & Timing Metrics */}
                <div className="grid grid-cols-3 gap-3 mb-4">
                  <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                    <div className="text-xs text-slate-500 font-medium">Review Score</div>
                    <div className="text-xl font-bold text-slate-900">
                      {detail.incident?.review_priority_score ?? "—"} <span className="text-xs font-normal text-slate-400">/ 100</span>
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                    <div className="text-xs text-slate-500 font-medium">Camera / Seat</div>
                    <div className="text-sm font-bold text-slate-800">
                      {detail.incident?.seat_id ? `Seat ${detail.incident.seat_id}` : detail.incident?.camera_id}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                    <div className="text-xs text-slate-500 font-medium">Recorded At</div>
                    <div className="text-xs font-bold text-slate-700">
                      {new Date(detail.alert.created_at).toLocaleTimeString()}
                    </div>
                  </div>
                </div>

                {/* AI Explanation & Rules Triggered */}
                <div className="space-y-3">
                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">Algorithmic Observation</h3>
                    <p className="mt-1 text-sm text-slate-800 bg-slate-50 p-3 rounded-lg border border-slate-200/80">
                      {detail.alert.summary}
                    </p>
                  </div>

                  {detail.incident?.rules_triggered && detail.incident.rules_triggered.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-slate-700 mb-1.5">Contributing Rule Heuristics</h4>
                      <ul className="space-y-1">
                        {detail.incident.rules_triggered.map((rule, idx) => (
                          <li key={idx} className="flex items-center justify-between text-xs bg-slate-50 px-3 py-1.5 rounded border border-slate-100">
                            <span className="text-slate-800 font-medium">{rule.description}</span>
                            <span className="text-slate-500 font-mono">+{rule.points} pts</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {detail.incident?.limitations && detail.incident.limitations.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-slate-700 mb-1">Model Limitations & Context</h4>
                      <ul className="list-disc pl-4 text-xs text-slate-500 space-y-0.5">
                        {detail.incident.limitations.map((lim, i) => (
                          <li key={i}>{lim}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Photographic Evidence Image */}
                  {detail.evidence && detail.evidence.length > 0 && (
                    <div className="pt-2 border-t border-slate-100">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                        Captured Frame Snapshot Evidence
                      </h4>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {detail.evidence.map((ev) => (
                          <div key={ev.evidence_id} className="group relative rounded-lg overflow-hidden border border-slate-300 bg-black">
                            {ev.url ? (
                              <a href={ev.url} target="_blank" rel="noreferrer">
                                <img
                                  src={ev.url}
                                  alt="Evidence snapshot"
                                  className="w-full h-44 object-contain group-hover:opacity-90 transition-opacity"
                                />
                                <div className="absolute bottom-0 inset-x-0 bg-slate-900/80 p-1.5 text-[10px] text-white flex justify-between">
                                  <span>{ev.evidence_id}</span>
                                  <span className="underline">View Full Resolution &rarr;</span>
                                </div>
                              </a>
                            ) : (
                              <div className="p-4 text-center text-xs text-red-400">
                                Evidence unavailable (status: {ev.status})
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Previous Human Review Log */}
                  {detail.reviews.length > 0 && (
                    <div className="pt-3 border-t border-slate-100">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                        Recorded Review History
                      </h4>
                      <div className="space-y-2">
                        {detail.reviews.map((rev) => (
                          <div key={rev.review_id} className="rounded-lg bg-emerald-50/60 border border-emerald-200 p-2.5 text-xs text-emerald-950">
                            <div className="flex justify-between font-bold">
                              <span>Decision: {rev.decision} &middot; Reviewer: {rev.reviewer_id}</span>
                              <time className="font-normal text-slate-500">{new Date(rev.reviewed_at).toLocaleTimeString()}</time>
                            </div>
                            {rev.notes && <p className="mt-1 text-slate-700">{rev.notes}</p>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Proctor Review Action Form */}
                  <form onSubmit={handleSubmitReview} className="pt-4 border-t border-slate-200 space-y-3">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                      Log Human Proctor Determination
                    </h4>

                    {submitMessage && (
                      <div className="rounded-lg bg-emerald-100 border border-emerald-300 p-2 text-xs font-medium text-emerald-900">
                        {submitMessage}
                      </div>
                    )}

                    <div className="grid grid-cols-3 gap-2">
                      <label
                        className={`flex items-center justify-center gap-1.5 p-2 rounded-lg border text-xs font-semibold cursor-pointer transition-all ${
                          decision === "ACKNOWLEDGE"
                            ? "bg-emerald-600 text-white border-emerald-700 shadow-sm"
                            : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="radio"
                          name="decision"
                          className="sr-only"
                          checked={decision === "ACKNOWLEDGE"}
                          onChange={() => setDecision("ACKNOWLEDGE")}
                        />
                        Acknowledge (Valid)
                      </label>
                      <label
                        className={`flex items-center justify-center gap-1.5 p-2 rounded-lg border text-xs font-semibold cursor-pointer transition-all ${
                          decision === "DISMISS"
                            ? "bg-slate-700 text-white border-slate-800 shadow-sm"
                            : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="radio"
                          name="decision"
                          className="sr-only"
                          checked={decision === "DISMISS"}
                          onChange={() => setDecision("DISMISS")}
                        />
                        Dismiss (Benign)
                      </label>
                      <label
                        className={`flex items-center justify-center gap-1.5 p-2 rounded-lg border text-xs font-semibold cursor-pointer transition-all ${
                          decision === "REFER"
                            ? "bg-purple-700 text-white border-purple-800 shadow-sm"
                            : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="radio"
                          name="decision"
                          className="sr-only"
                          checked={decision === "REFER"}
                          onChange={() => setDecision("REFER")}
                        />
                        Refer (Escalate)
                      </label>
                    </div>

                    <div>
                      <label className="text-xs font-medium text-slate-700">
                        Proctor Verification Notes (Audit Log Record)
                      </label>
                      <textarea
                        rows={2}
                        className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-xs focus:ring-sky-500 focus:border-sky-500"
                        placeholder="Detail observations, candidate explanation if queried, or rationale for determination..."
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                      />
                    </div>

                    <button
                      type="submit"
                      disabled={submitting}
                      className={btnPrimary}
                    >
                      {submitting ? "Submitting..." : "Confirm & Save Determination"}
                    </button>
                  </form>
                </div>
              </Card>
            </div>
          ) : (
            <Card>
              <p className="text-sm text-slate-500 py-16 text-center">
                Select an incident from the left panel to review evidence and log determinations.
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
