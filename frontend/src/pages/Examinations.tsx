import { useEffect, useState } from "react";
import { Card, Stat, btnDanger, btnPrimary, btnSecondary } from "../components/ui";
import { api, ApiError } from "../services/api";
import type { Exam, Room } from "../types";

export default function Examinations({
  rooms,
  onNavigateToReport,
  onNavigateToAlerts,
}: {
  rooms: Room[];
  onNavigateToReport?: (examId: string) => void;
  onNavigateToAlerts?: (examId: string) => void;
}) {
  const [exams, setExams] = useState<Exam[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [courseCode, setCourseCode] = useState("");
  const [selectedRoomId, setSelectedRoomId] = useState("");
  const [notes, setNotes] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadExams = () => {
    setLoading(true);
    api.exams()
      .then((data) => {
        setExams(data);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load exams"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadExams();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createExam({
        title,
        course_code: courseCode || undefined,
        room_id: selectedRoomId || undefined,
        notes: notes || undefined,
      });
      setTitle("");
      setCourseCode("");
      setNotes("");
      setShowCreate(false);
      loadExams();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create exam");
    }
  };

  const handleStart = async (id: string) => {
    setBusyId(id);
    try {
      await api.startExam(id);
      loadExams();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start exam");
    } finally {
      setBusyId(null);
    }
  };

  const handleEnd = async (id: string) => {
    setBusyId(id);
    try {
      await api.endExam(id);
      loadExams();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to end exam");
    } finally {
      setBusyId(null);
    }
  };

  const activeExams = exams.filter((x) => x.status === "IN_PROGRESS");
  const totalAlerts = exams.reduce((acc, curr) => acc + (curr.alert_count || 0), 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Examination Session Management</h1>
          <p className="text-xs text-slate-500">Configure examination schedules, monitor live room sessions, and generate audit reports.</p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className={showCreate ? btnSecondary : btnPrimary}
        >
          {showCreate ? "Cancel" : "+ Schedule New Exam"}
        </button>
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">
          {error}
        </div>
      )}

      {/* Top Level Metrics */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Total Examinations" value={exams.length} />
        <Stat
          label="Active Sessions"
          value={activeExams.length}
          hint={activeExams.length > 0 ? "Monitoring currently active" : "No active exam"}
        />
        <Stat label="Recorded Flags" value={totalAlerts} hint="Across all sessions" />
        <Stat label="Configured Rooms" value={rooms.length} hint="Available for proctoring" />
      </div>

      {/* Create Exam Card */}
      {showCreate && (
        <Card title="Schedule Examination">
          <form onSubmit={handleCreate} className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="text-xs font-semibold text-slate-700">Exam Title *</label>
              <input
                required
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                placeholder="e.g. CS101 Midterm Examination"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700">Course Code</label>
              <input
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                placeholder="e.g. CS101-FALL"
                value={courseCode}
                onChange={(e) => setCourseCode(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700">Assigned Hall / Room</label>
              <select
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                value={selectedRoomId}
                onChange={(e) => setSelectedRoomId(e.target.value)}
              >
                <option value="">— Choose Room —</option>
                {rooms.map((r) => (
                  <option key={r.room_id} value={r.room_id}>
                    {r.name} ({r.seat_count} seats)
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700">Proctoring Notes</label>
              <input
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                placeholder="e.g. Standard closed-book rules apply"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>
            <div className="md:col-span-2 pt-2 flex items-center gap-3">
              <button type="submit" className={btnPrimary}>
                Create Examination
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className={btnSecondary}
              >
                Cancel
              </button>
            </div>
          </form>
        </Card>
      )}

      {/* Examinations List */}
      <Card title="All Examination Sessions">
        {loading ? (
          <p className="text-xs text-slate-400 py-4">Loading examination sessions...</p>
        ) : exams.length === 0 ? (
          <p className="text-sm text-slate-500 py-6 text-center">
            No examinations scheduled yet. Click "+ Schedule New Exam" above to create one.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2.5 px-3">Title / Code</th>
                  <th className="py-2.5 px-3">Room</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Timing</th>
                  <th className="py-2.5 px-3 text-center">Flags</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {exams.map((exam) => (
                  <tr key={exam.exam_id} className="hover:bg-slate-50/50">
                    <td className="py-3 px-3">
                      <div className="font-semibold text-slate-900">{exam.title}</div>
                      <div className="text-xs text-slate-400">{exam.course_code || "No code"} &middot; {exam.exam_id}</div>
                    </td>
                    <td className="py-3 px-3 text-slate-600 font-medium">
                      {exam.room_name || "Unassigned"}
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          exam.status === "IN_PROGRESS"
                            ? "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-600/30 animate-pulse"
                            : exam.status === "COMPLETED"
                            ? "bg-slate-100 text-slate-700 ring-1 ring-slate-400/20"
                            : "bg-sky-100 text-sky-800 ring-1 ring-sky-600/20"
                        }`}
                      >
                        {exam.status.replace("_", " ")}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-xs text-slate-500">
                      {exam.start_time ? (
                        <>
                          <div>Started: {new Date(exam.start_time).toLocaleTimeString()}</div>
                          {exam.end_time && <div>Ended: {new Date(exam.end_time).toLocaleTimeString()}</div>}
                        </>
                      ) : (
                        "Not started"
                      )}
                    </td>
                    <td className="py-3 px-3 text-center">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs font-bold ${
                          exam.alert_count > 0 ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {exam.alert_count}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right space-x-2">
                      {exam.status === "SCHEDULED" && (
                        <button
                          disabled={busyId === exam.exam_id}
                          onClick={() => handleStart(exam.exam_id)}
                          className={btnPrimary}
                        >
                          Start Exam
                        </button>
                      )}
                      {exam.status === "IN_PROGRESS" && (
                        <>
                          {onNavigateToAlerts && (
                            <button
                              onClick={() => onNavigateToAlerts(exam.exam_id)}
                              className={btnSecondary}
                            >
                              Live Alerts
                            </button>
                          )}
                          <button
                            disabled={busyId === exam.exam_id}
                            onClick={() => handleEnd(exam.exam_id)}
                            className={btnDanger}
                          >
                            End Exam
                          </button>
                        </>
                      )}
                      {exam.status === "COMPLETED" && onNavigateToReport && (
                        <button
                          onClick={() => onNavigateToReport(exam.exam_id)}
                          className={btnSecondary}
                        >
                          Audit Report
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
