# Architecture (Phase 1)

Modular monolith (FastAPI). Video acquisition and analysis run in per-camera threads; API requests never block on video.

```
FrameSource adapter (file | webcam | HTTP-MJPEG | RTSP)
   -> acquisition thread -> FrameBuffer (bounded, drops oldest)
   -> analysis thread (sampled at analysis_fps): stale / frozen / dark / blurry -> CameraState
   -> CameraStatusEvent -> EventService.ingest -> SQLite (events) -> Hub -> WebSocket /ws -> dashboard
```
* **Single owner of camera state**: the analysis thread. STALE = no frames; FROZEN = frames but identical picture. A quiet scene is not a dead camera.
* **Schemas** (`app/schemas/events.py`) are the only payload contract. Observations, candidate incidents and human reviews are distinct types.
* **events.camera_id is not a foreign key** so deleting a camera does not erase history.
* **Preview** uses a low-rate MJPEG endpoint, never the event WebSocket.
* Dashboard re-fetches a REST snapshot on every WebSocket (re)connect.
* AI modules (`ai_modules/*`) are empty placeholders until Phases 3-5.
