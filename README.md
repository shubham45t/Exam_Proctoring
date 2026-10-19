# OmniProctor

AI-assisted examination-hall monitoring and candidate integrity support for **human review**.
Outputs are review recommendations and explainable observations, never final disciplinary findings of misconduct.

**Platform Status:** Completed across all phases (Phases 1-8: Foundation, Cameras, Occupancy, Object Detection, Head Pose & Spatial Rules, Fusion & Alerts, Examination Sessions, Audit Reports, and Auth/RBAC).

---

## Architecture Overview

OmniProctor is structured as a modular monolith pairing a high-throughput Python FastAPI backend with a responsive React 18 + Vite proctoring operations console:

1. **Camera Ingestion & Health Engine (`app.cameras`)**:
   - Supports HTTP/MJPEG (smartphones as IP webcams), RTSP streams (IP cameras / NVRs), USB/built-in webcams, and prerecorded test video files.
   - Per-camera multi-threading (Acquisition thread + Analysis thread) with bounded `FrameBuffer` dropping oldest frames to prevent memory leaks and latency backlog.
   - Continuous camera quality and health analysis: Detects disconnected, frozen, stale, dark, and blurry video feeds with exponential backoff auto-reconnect.

2. **Perception & Computer Vision (`app.perception`)**:
   - **Seat Occupancy (`baseline-diff-v1`)**: Compares live frames against empty-room calibration baselines to track seat status (`VACANT`, `OCCUPIED`, `UNCERTAIN`, `OCCLUDED`, `UNMONITORED`) with multi-camera fusion.
   - **Prohibited Device Detection**: YOLOX ONNX inference executed purely on CPU via OpenCV DNN. Detects mobile phones in candidate workstations.
   - **Visual Tracking & Dedup (`IoUTracker`)**: ByteTrack-style two-stage tracker preventing event flooding. A persistently visible phone creates a single confirmed observation and subsequent track state events.
   - **Head Pose & Gaze Analysis (`HeadPoseAnalyzer`)**: Lightweight OpenCV face & feature geometry computing yaw, pitch, and roll angles to identify significant or sustained gaze aversions away from exam papers.
   - **Spatial Rules (`SpatialAnalyzer`)**: Tracks out-of-seat departures during active exams and rapid alternating direction shifts.

3. **Incident Fusion Engine & Review Alerts (`app.monitoring`)**:
   - Subscribes to multi-modal observations and executes explainable correlation rules.
   - Correlates multi-cue observations (e.g. suspicious gaze + prohibited object) to calculate transparent operational review priority scores (0–100).
   - Generates `CandidateIncident` records and active `ReviewAlert` notifications broadcasted in real time via WebSocket to proctor consoles.
   - Human proctors record official determinations (`ACKNOWLEDGE`, `DISMISS`, `REFER`) with mandatory audit log attribution.

4. **Examinations & Audit Reports (`app.examination`, `app.api.reports`)**:
   - Schedule, start, and conclude official examination sessions tied to calibrated rooms.
   - Compiles comprehensive, court-admissible integrity audit packages with incident timelines, photographic evidence links, reviewer notes, and ethical AI compliance declarations.
   - Generates exportable printable official HTML/PDF reports.

5. **Authentication & RBAC (`app.auth`)**:
   - Standard PBKDF2-HMAC-SHA256 password hashing with signed bearer tokens.
   - Role-Based Access Control: `admin`, `proctor`, and `auditor`.
   - Seeded demo operator accounts:
     - **Proctor**: `proctor` / `proctor123`
     - **Administrator**: `admin` / `admin123`
     - **Auditor**: `auditor` / `auditor123`

6. **Frontend Operations Console (`frontend/src/`)**:
   - **Dashboard**: System telemetry, camera status overview, room occupancy HUD, and event stream.
   - **Live Monitoring**: Real-time camera feeds, detection bounding box overlays, active target HUD, and urgent alert banners.
   - **Alerts & Review**: Dedicated proctor review console with side-by-side photographic evidence viewer and determination form.
   - **Examinations**: Schedule and control live exam sessions with real-time flag counters.
   - **Rooms & Seat Map**: Visual room dimensioning, seat grid coordinate editor, and fused occupancy states.
   - **Calibration**: Interactive polygon drawing directly onto camera snapshots to map seats, plus empty-room baseline capture.
   - **Cameras**: Multi-source registration, connection probing, and per-camera AI detection toggles.
   - **Audit Reports**: Examination summary reports with printable export view.

---

## Quick Start (Development)

### Requirements
* Python 3.11+ (Python 3.12 recommended)
* Node.js 18+ (Node 22 recommended)

### 1. Backend Setup
```bash
cd backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
# source venv/bin/activate

pip install -r requirements.txt
python ../scripts/download_model.py          # optional: downloads YOLOX nano model (~3.6 MB)
python ../scripts/make_test_video.py          # optional: creates synthetic test video

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5
```
* Interactive API documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* Default SQLite database is automatically migrated to the latest schema at startup.

### 2. Frontend Setup
In a second terminal:
```bash
cd frontend
npm install
npm run dev
```
* Dashboard console: [http://127.0.0.1:5173](http://127.0.0.1:5173) (proxies `/api` and `/ws` to port 8000).

---

## Ethical Principles & Safety Notice
OmniProctor is strictly designed as an **operator-assistive review tool**. Algorithmic observations, bounding boxes, and priority scores are calculated heuristics intended to focus proctor attention where anomalies occur. They **never** constitute a legal or disciplinary finding of academic dishonesty without direct, verified corroboration by human educational authorities.
