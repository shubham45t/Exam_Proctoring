from __future__ import annotations

import threading
from typing import Callable

from app.config import Settings
from app.schemas.events import CameraStatusEvent

from .base import FrameSource
from .worker import CameraWorker


class CameraManager:
    def __init__(self, settings: Settings, on_event: Callable[[CameraStatusEvent], None]):
        self._s = settings
        self._on_event = on_event
        self._workers: dict[str, CameraWorker] = {}
        self._lock = threading.Lock()

    def is_running(self, camera_id: str) -> bool:
        w = self._workers.get(camera_id)
        return bool(w and w.running)

    def start(self, camera_id: str, source_factory: Callable[[], FrameSource], analyzers: list | None = None) -> None:
        with self._lock:
            if self.is_running(camera_id):
                raise RuntimeError("already running")
            w = CameraWorker(camera_id, source_factory, self._s, self._on_event)
            self._workers[camera_id] = w
            w.set_analyzers(analyzers or [])
            w.start()

    def stop(self, camera_id: str) -> None:
        with self._lock:
            w = self._workers.pop(camera_id, None)
        if w:
            w.stop()

    def stop_all(self) -> None:
        for cid in list(self._workers):
            self.stop(cid)

    def set_analyzers(self, camera_id: str, analyzers: list) -> bool:
        w = self._workers.get(camera_id)
        if not w or not w.running:
            for a in analyzers:  # nobody will own these: release their threads
                getattr(a, "close", lambda: None)()
            return False
        w.set_analyzers(analyzers)
        return True

    def active_tracks(self, camera_id: str) -> list:
        w = self._workers.get(camera_id)
        out: list = []
        for a in (w.analyzers() if w else []):
            if hasattr(a, "active_tracks"):
                out.extend(a.active_tracks())
        return out

    def current_frame(self, camera_id: str):
        w = self._workers.get(camera_id)
        return w.current_frame() if w else None

    def runtime_state(self, camera_id: str) -> str | None:
        s = self.snapshot(camera_id)
        return s["state"] if s else None

    def snapshot(self, camera_id: str) -> dict | None:
        w = self._workers.get(camera_id)
        return w.snapshot() if w else None

    def latest_jpeg(self, camera_id: str) -> bytes | None:
        w = self._workers.get(camera_id)
        return w.latest_jpeg(self._s.preview_max_width) if w else None

    def running_ids(self) -> list[str]:
        return [c for c in self._workers if self.is_running(c)]
