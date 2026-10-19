import { useEffect, useState } from "react";
import Shell, { type PageId } from "./layouts/Shell";
import { useLive } from "./hooks/useLive";
import Dashboard from "./pages/Dashboard";
import LiveMonitoring from "./pages/LiveMonitoring";
import AlertsReview from "./pages/AlertsReview";
import Examinations from "./pages/Examinations";
import Reports from "./pages/Reports";
import Cameras from "./pages/Cameras";
import Rooms from "./pages/Rooms";
import Calibration from "./pages/Calibration";
import { api } from "./services/api";
import type { Room } from "./types";

export default function App() {
  const [page, setPage] = useState<PageId>("dashboard");
  const live = useLive();
  const [rooms, setRooms] = useState<Room[]>([]);
  const [targetedAlertId, setTargetedAlertId] = useState<string | undefined>();
  const [targetedExamId, setTargetedExamId] = useState<string | undefined>();
  const [newAlertsCount, setNewAlertsCount] = useState<number>(0);

  const reloadRooms = () => {
    api.rooms().then(setRooms).catch(() => {});
  };

  useEffect(() => {
    reloadRooms();
  }, []);

  const tick = live.events[0]?.event_id;

  // Poll count of new alerts for badge
  useEffect(() => {
    api.alerts("NEW")
      .then((res) => setNewAlertsCount(res.total))
      .catch(() => {});
  }, [tick]);

  const handleNavigateToAlert = (alertId: string) => {
    setTargetedAlertId(alertId);
    setPage("alerts");
  };

  const handleNavigateToReport = (examId: string) => {
    setTargetedExamId(examId);
    setPage("reports");
  };

  const handleNavigateToAlerts = (_examId: string) => {
    setPage("alerts");
  };

  return (
    <Shell
      page={page}
      onNav={setPage}
      conn={live.conn}
      newAlertsCount={newAlertsCount}
    >
      {live.error && (
        <div
          role="alert"
          className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-xs font-medium text-red-800 shadow-sm"
        >
          {live.error}
        </div>
      )}

      {page === "dashboard" && (
        <Dashboard
          cameras={live.cameras}
          events={live.events}
          status={live.status}
          refresh={live.refresh}
          rooms={rooms}
          tick={tick}
        />
      )}

      {page === "monitoring" && (
        <LiveMonitoring
          cameras={live.cameras}
          rooms={rooms}
          tick={tick}
          onNavigateToAlert={handleNavigateToAlert}
        />
      )}

      {page === "alerts" && (
        <AlertsReview
          initialAlertId={targetedAlertId}
          tick={tick}
        />
      )}

      {page === "examinations" && (
        <Examinations
          rooms={rooms}
          onNavigateToReport={handleNavigateToReport}
          onNavigateToAlerts={handleNavigateToAlerts}
        />
      )}

      {page === "reports" && (
        <Reports
          initialExamId={targetedExamId}
        />
      )}

      {page === "rooms" && (
        <Rooms
          tick={tick}
          rooms={rooms}
          reloadRooms={reloadRooms}
        />
      )}

      {page === "calibration" && (
        <Calibration
          cameras={live.cameras}
          rooms={rooms}
          tick={tick}
          refresh={live.refresh}
        />
      )}

      {page === "cameras" && (
        <Cameras
          cameras={live.cameras}
          refresh={live.refresh}
        />
      )}
    </Shell>
  );
}
