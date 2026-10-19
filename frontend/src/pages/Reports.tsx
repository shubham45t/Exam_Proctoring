import { useEffect, useState } from "react";
import { Card, Stat, btnPrimary } from "../components/ui";
import { api, ApiError } from "../services/api";
import type { Exam, ExamReport } from "../types";

export default function Reports({ initialExamId }: { initialExamId?: string }) {
  const [exams, setExams] = useState<Exam[]>([]);
  const [selectedExamId, setSelectedExamId] = useState<string>(initialExamId ?? "");
  const [report, setReport] = useState<ExamReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.exams()
      .then((data) => {
        setExams(data);
        if (!selectedExamId && data.length > 0) {
          setSelectedExamId(data[0].exam_id);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedExamId) {
      setReport(null);
      return;
    }
    setLoading(true);
    setError(null);
    api.report(selectedExamId)
      .then((rep) => setReport(rep))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load audit report"))
      .finally(() => setLoading(false));
  }, [selectedExamId]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Academic Integrity Audit Reports</h1>
          <p className="text-xs text-slate-500">Official proctoring summary packages, candidate incident timelines, and compliance declarations.</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs font-semibold text-slate-600">Select Exam:</label>
          <select
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium bg-white"
            value={selectedExamId}
            onChange={(e) => setSelectedExamId(e.target.value)}
          >
            {exams.map((ex) => (
              <option key={ex.exam_id} value={ex.exam_id}>
                {ex.title} ({ex.status})
              </option>
            ))}
          </select>
          {selectedExamId && (
            <a
              href={`/api/reports/exam/${selectedExamId}/html`}
              target="_blank"
              rel="noreferrer"
              className={btnPrimary}
            >
              Export Printable Official PDF/HTML &rarr;
            </a>
          )}
        </div>
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">
          {error}
        </div>
      )}

      {loading ? (
        <Card>
          <p className="text-sm text-slate-500 py-12 text-center">Compiling academic integrity report...</p>
        </Card>
      ) : report ? (
        <div className="space-y-6">
          {/* Header Summary Card */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div>
                <h2 className="text-lg font-bold text-slate-900">{report.title}</h2>
                <div className="text-xs text-slate-500">
                  Course: <span className="font-semibold text-slate-700">{report.course_code || "N/A"}</span> &middot;
                  Hall: <span className="font-semibold text-slate-700">{report.room_name}</span> &middot;
                  Session Status: <span className="font-semibold text-slate-700">{report.status}</span>
                </div>
              </div>
              <div className="text-right text-xs text-slate-500">
                <div>Exam ID: <span className="font-mono text-slate-700">{report.exam_id}</span></div>
                {report.duration_minutes && <div>Duration: <span className="font-semibold text-slate-800">{report.duration_minutes} min</span></div>}
              </div>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 pt-1">
              <Stat label="Monitored Desks" value={report.total_seats} />
              <Stat label="Total Alerts" value={report.metrics.total_alerts} />
              <Stat
                label="High Priority Flags"
                value={report.metrics.priority_breakdown.high}
                hint={report.metrics.priority_breakdown.high > 0 ? "Warrants disciplinary review" : "None detected"}
              />
              <Stat
                label="Reviews Completed"
                value={`${report.metrics.reviews_completed} / ${report.metrics.total_alerts}`}
                hint={`Acknowledged: ${report.metrics.decision_breakdown.ACKNOWLEDGE} &middot; Dismissed: ${report.metrics.decision_breakdown.DISMISS}`}
              />
            </div>
          </div>

          {/* Incident Timeline Table */}
          <Card title="Candidate Incident Chronology &amp; Determinations">
            {report.timeline.length === 0 ? (
              <p className="text-sm text-slate-500 py-8 text-center">
                No candidate incidents or flags were recorded during this examination session. Clean record.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 text-slate-500 uppercase">
                    <tr>
                      <th className="py-2.5 px-3">Time</th>
                      <th className="py-2.5 px-3">Category / Seat</th>
                      <th className="py-2.5 px-3">Priority (Score)</th>
                      <th className="py-2.5 px-3">Observation &amp; Limitations</th>
                      <th className="py-2.5 px-3">Proctor Determination</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {report.timeline.map((item, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/50">
                        <td className="py-3 px-3 text-slate-500 whitespace-nowrap">
                          {new Date(item.timestamp).toLocaleTimeString()}
                        </td>
                        <td className="py-3 px-3">
                          <span className="font-bold text-slate-900">{item.category}</span>
                          <div className="text-slate-500">{item.seat_id ? `Seat ${item.seat_id}` : "General Area"}</div>
                        </td>
                        <td className="py-3 px-3">
                          <span
                            className={`inline-block rounded px-2 py-0.5 font-bold uppercase text-[10px] ${
                              item.priority === "high"
                                ? "bg-red-100 text-red-800"
                                : item.priority === "medium"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-sky-100 text-sky-800"
                            }`}
                          >
                            {item.priority}
                          </span>
                          <span className="ml-1 text-slate-400 font-mono">({item.score})</span>
                        </td>
                        <td className="py-3 px-3 max-w-md">
                          <p className="text-slate-800 font-medium">{item.explanation}</p>
                          {item.limitations.length > 0 && (
                            <p className="text-[11px] text-slate-400 mt-0.5">
                              Limits: {item.limitations.join("; ")}
                            </p>
                          )}
                        </td>
                        <td className="py-3 px-3">
                          {item.review ? (
                            <div className="rounded bg-emerald-50 border border-emerald-200 p-2 text-emerald-950">
                              <span className="font-bold">{item.review.decision}</span> by {item.review.reviewer_id}
                              {item.review.notes && <p className="mt-0.5 text-slate-600 italic">"{item.review.notes}"</p>}
                            </div>
                          ) : (
                            <span className="rounded bg-slate-100 px-2 py-1 text-slate-500 font-medium">
                              Pending Review
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Compliance & Declarations */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 text-xs text-slate-600">
            <h4 className="font-bold uppercase tracking-wider text-slate-800 mb-1">
              Ethical AI &amp; Regulatory Compliance Statement
            </h4>
            <p>{report.compliance_notice}</p>
          </div>
        </div>
      ) : (
        <Card>
          <p className="text-sm text-slate-500 py-12 text-center">
            Select an examination session from the dropdown above to view its comprehensive audit report.
          </p>
        </Card>
      )}
    </div>
  );
}
