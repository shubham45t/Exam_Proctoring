"""Base for analyzers that do heavy work (model inference) off the camera's health-analysis thread.

Back-pressure design: a ONE-slot mailbox. If inference is slower than frames arrive, the older
waiting frame is replaced (counted in `dropped`) instead of queueing, so memory and latency stay
bounded and the camera's health/state analysis is never blocked by a slow model."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime

import numpy as np

from app.schemas.events import CameraState

log = logging.getLogger(__name__)


class ThreadedAnalyzer:
    name = "analyzer"

    def __init__(self, camera_id: str, min_interval_s: float):
        self.camera_id = camera_id
        self._min = min_interval_s
        self._last_accept = 0.0
        self._cv = threading.Condition()
        self._mail: tuple[np.ndarray, datetime] | None = None
        self._state: CameraState | None = None
        self._closed = False
        self._thread: threading.Thread | None = None
        self.processed = self.dropped = self.errors = 0
        self._lat: deque[float] = deque(maxlen=200)

    # -- FrameAnalyzer protocol (called from the camera's analysis thread; must return fast)
    def process(self, image: np.ndarray, ts: datetime) -> None:
        now = time.monotonic()
        if now - self._last_accept < self._min:  # frame-rate cap for this analyzer (not a "drop")
            return
        self._last_accept = now
        with self._cv:
            if self._mail is not None:
                self.dropped += 1  # inference is behind: replace the waiting frame
            self._mail = (image, ts)
            self._cv.notify()

    def on_state(self, state: CameraState) -> None:
        with self._cv:
            self._state = state
            self._cv.notify()

    # -- lifecycle
    def start(self) -> "ThreadedAnalyzer":
        self._thread = threading.Thread(target=self._run, name=f"{self.name}-{self.camera_id}", daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        with self._cv:
            self._closed = True
            self._cv.notify()
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=5)

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._closed and self._mail is None and self._state is None:
                    self._cv.wait()
                closing = self._closed
                state, self._state = self._state, None
                mail, self._mail = self._mail, None
            if closing:
                mail = None  # on shutdown a pending state change (e.g. STOPPED -> end tracks) is still handled; frames are not
            try:
                if state is not None:
                    self._on_state(state)
                    if state is not CameraState.CONNECTED:
                        mail = None  # a frame queued before the camera went unhealthy is no longer current
                if mail is not None:
                    t0 = time.monotonic()
                    self._infer(*mail)
                    self._lat.append((time.monotonic() - t0) * 1000)
                    self.processed += 1
            except Exception:  # one bad frame/model error must not kill the analyzer or the camera
                self.errors += 1
                log.exception("%s analyzer error on %s (continuing)", self.name, self.camera_id)
            if closing:
                return

    def _infer(self, image: np.ndarray, ts: datetime) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _on_state(self, state: CameraState) -> None:
        pass

    def stats(self) -> dict:
        lat = list(self._lat)
        return {"name": self.name, "processed": self.processed, "dropped": self.dropped, "errors": self.errors,
                "infer_ms_median": round(float(np.median(lat)), 1) if lat else None,
                "infer_ms_p95": round(float(np.percentile(lat, 95)), 1) if lat else None}
