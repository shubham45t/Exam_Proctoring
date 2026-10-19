"""Per-camera pipeline: acquisition thread -> bounded FrameBuffer -> health/analysis thread.

Acquisition never waits for analysis (oldest frame is dropped instead of queueing), so a slow
consumer cannot cause unbounded memory growth or stale-frame backlog.
The analysis thread is the single owner of the camera *state*; it derives state from facts
published by the acquisition thread. A quiet scene is never mistaken for a dead camera:
STALE means no frames arrive, FROZEN means frames arrive but the picture is pixel-identical.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

import cv2
import numpy as np

from app.config import Settings
from app.schemas.events import CameraState, CameraStatusEvent, QualityIssue

from .base import FrameSource, SourceError

log = logging.getLogger(__name__)


class FrameAnalyzer(Protocol):
    """Pluggable per-frame consumer (occupancy now; detection/head-pose later)."""

    def on_state(self, state: CameraState) -> None: ...
    def process(self, image: np.ndarray, ts: datetime) -> None: ...


@dataclass
class Frame:
    image: np.ndarray
    seq: int
    captured_mono: float


class FrameBuffer:
    def __init__(self, maxlen: int):
        self._d: deque[Frame] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self.dropped = 0
        self.total = 0

    def put(self, f: Frame) -> None:
        with self._lock:
            if len(self._d) == self._d.maxlen:
                self.dropped += 1
            self._d.append(f)
            self.total += 1

    def latest(self) -> Frame | None:
        with self._lock:
            return self._d[-1] if self._d else None


def analyse_quality(image: np.ndarray, s: Settings) -> tuple[set[QualityIssue], float, float]:
    """Return (raw issues, mean brightness, blur score = variance of Laplacian) on a downscaled frame."""
    h, w = image.shape[:2]
    scale = 320 / w if w > 320 else 1.0
    small = cv2.resize(image, (int(w * scale), int(h * scale))) if scale != 1.0 else image
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    luma = float(gray.mean())
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    issues: set[QualityIssue] = set()
    if luma < s.dark_luma_threshold:
        issues.add(QualityIssue.DARK)
    elif blur < s.blur_laplacian_threshold:  # a dark frame is trivially "blurry"; report one cause
        issues.add(QualityIssue.BLURRY)
    return issues, luma, blur


class CameraWorker:
    def __init__(
        self,
        camera_id: str,
        source_factory: Callable[[], FrameSource],
        settings: Settings,
        on_event: Callable[[CameraStatusEvent], None],
    ):
        self.camera_id = camera_id
        self._factory = source_factory
        self._s = settings
        self._on_event = on_event
        self.buffer = FrameBuffer(settings.frame_buffer_size)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        # facts written by the acquisition thread, read by the analysis thread
        self._acq_status = "connecting"  # connecting | open | failed | reconnecting
        self._acq_detail: str | None = None
        self._ever_connected = False
        self._seq = 0
        self._last_frame_mono: float | None = None
        self._fps_window: deque[float] = deque(maxlen=60)
        # analysis-thread state
        self._state: CameraState | None = None
        self._issues: tuple[QualityIssue, ...] = ()
        self._streaks: dict[QualityIssue, int] = {}
        self._prev_thumb: np.ndarray | None = None
        self._last_change_mono = time.monotonic()
        self._last_analysed_seq = -1
        self._proc_ms = 0.0
        self._lock = threading.Lock()
        self._analyzers: list[FrameAnalyzer] = []
        self._analyzers_lock = threading.Lock()

    def set_analyzers(self, analyzers: list[FrameAnalyzer]) -> None:
        """Hot-swap analyzers (e.g. after calibration changes). Brings new ones up to date with the current state."""
        with self._analyzers_lock:
            old, self._analyzers = self._analyzers, list(analyzers)
        for a in old:
            if a not in analyzers:
                self._close(a)
        if self._state is not None:
            for a in analyzers:
                self._safe(a.on_state, self._state)

    def _safe(self, fn, *args) -> None:
        try:
            fn(*args)
        except Exception:  # a faulty analyzer must never take the camera pipeline down
            log.exception("camera %s analyzer error (continuing)", self.camera_id)

    def _close(self, a) -> None:
        close = getattr(a, "close", None)
        if close:
            self._safe(close)

    def analyzers(self) -> list:
        with self._analyzers_lock:
            return list(self._analyzers)

    def current_frame(self) -> np.ndarray | None:
        f = self.buffer.latest()
        return None if f is None else f.image.copy()

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._acquire, name=f"acq-{self.camera_id}", daemon=True),
            threading.Thread(target=self._analyse, name=f"ana-{self.camera_id}", daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=self._s.read_timeout_s + 3)
        self._emit(CameraState.STOPPED, "Stopped by operator")
        with self._analyzers_lock:
            analyzers = list(self._analyzers)
        for a in analyzers:  # their last observation is no longer current
            self._safe(a.on_state, CameraState.STOPPED)
        for a in analyzers:
            self._close(a)

    @property
    def running(self) -> bool:
        return any(t.is_alive() for t in self._threads) and not self._stop.is_set()

    # -------------------------------------------------------------------- acquisition
    def _acquire(self) -> None:
        backoff = self._s.reconnect_initial_s
        source: FrameSource | None = None
        while not self._stop.is_set():
            self._acq_status = "reconnecting" if self._ever_connected else "connecting"
            try:
                source = self._factory()
                source.open()
            except SourceError as e:
                self._acq_status, self._acq_detail = "failed", e.message
                log.warning("camera %s open failed (%s); retry in %.1fs", self.camera_id, e.code, backoff)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, self._s.reconnect_max_s)
                continue
            except Exception:  # never let an adapter bug kill the thread
                log.exception("camera %s unexpected open error", self.camera_id)
                self._acq_status, self._acq_detail = "failed", "Unexpected error opening source"
                self._stop.wait(backoff)
                backoff = min(backoff * 2, self._s.reconnect_max_s)
                continue
            backoff = self._s.reconnect_initial_s
            self._acq_status, self._acq_detail, self._ever_connected = "open", None, True
            failures = 0
            period = 1.0 / source.nominal_fps
            try:
                while not self._stop.is_set():
                    t0 = time.monotonic()
                    image = source.read()
                    if image is None:
                        failures += 1
                        if failures >= self._s.read_failure_limit:
                            self._acq_detail = "Stream stopped delivering frames; reconnecting"
                            break
                        self._stop.wait(0.05)
                        continue
                    failures = 0
                    now = time.monotonic()
                    self._seq += 1
                    self.buffer.put(Frame(image, self._seq, now))
                    self._last_frame_mono = now
                    self._fps_window.append(now)
                    if not source.is_live:  # pace prerecorded video to real time
                        self._stop.wait(max(0.0, period - (time.monotonic() - t0)))
            except Exception:
                log.exception("camera %s read error", self.camera_id)
                self._acq_detail = "Read error; reconnecting"
            finally:
                source.close()
        if source is not None:
            source.close()

    # ---------------------------------------------------------------------- analysis
    def measured_fps(self) -> float | None:
        w = list(self._fps_window)
        if len(w) < 2 or time.monotonic() - w[-1] > 2.0 or w[-1] <= w[0]:
            return None
        return round((len(w) - 1) / (w[-1] - w[0]), 1)

    def _analyse(self) -> None:
        interval = 1.0 / self._s.analysis_fps
        while not self._stop.wait(interval):
            try:
                self._analyse_once()
            except Exception:
                log.exception("camera %s analysis error (continuing)", self.camera_id)

    def _analyse_once(self) -> None:
        s, now = self._s, time.monotonic()
        frame = self.buffer.latest()
        detail = self._acq_detail
        new_frame = frame is not None and frame.seq != self._last_analysed_seq
        if frame is not None and frame.seq != self._last_analysed_seq:
            t0 = time.monotonic()
            self._last_analysed_seq = frame.seq
            raw, _luma, _blur = analyse_quality(frame.image, s)
            for issue in QualityIssue:
                self._streaks[issue] = self._streaks.get(issue, 0) + 1 if issue in raw else 0
            thumb = cv2.resize(cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY), (32, 32)).astype(np.float32)
            if self._prev_thumb is None or float(np.abs(thumb - self._prev_thumb).mean()) > s.frozen_diff_threshold:
                self._last_change_mono = now
            self._prev_thumb = thumb
            self._proc_ms = (time.monotonic() - t0) * 1000
        confirmed = tuple(i for i in QualityIssue if self._streaks.get(i, 0) >= s.quality_confirm_count)

        age = None if self._last_frame_mono is None else now - self._last_frame_mono
        status = self._acq_status
        if status in ("failed",):
            state = CameraState.FAILED
        elif status == "reconnecting" and (age is None or age > s.stale_after_s):
            state = CameraState.RECONNECTING
        elif status == "connecting" or frame is None:
            state = CameraState.CONNECTING
        elif age is not None and age > s.stale_after_s:
            state = CameraState.STALE
            detail = detail or f"No new frame for {age:.0f}s"
        elif now - self._last_change_mono > s.frozen_after_s:
            state = CameraState.FROZEN
            detail = "Frames are arriving but the image has not changed"
        elif confirmed:
            state = CameraState.DEGRADED
            detail = "Image quality: " + ", ".join(i.value for i in confirmed)
        else:
            state = CameraState.CONNECTED
        if state is not CameraState.DEGRADED:
            confirmed = ()  # quality flags are only meaningful while frames are current
        changed = state != self._state
        if changed or confirmed != self._issues:
            self._emit(state, detail, confirmed)
        with self._analyzers_lock:
            analyzers = list(self._analyzers)
        if changed:
            for a in analyzers:
                self._safe(a.on_state, state)
        if new_frame and state is CameraState.CONNECTED:  # only current, healthy frames feed analyzers
            for a in analyzers:
                self._safe(a.process, frame.image, datetime.now(timezone.utc))

    def _emit(self, state: CameraState, detail: str | None, issues: tuple[QualityIssue, ...] = ()) -> None:
        with self._lock:
            prev, self._state, self._issues = self._state, state, issues
            age = None if self._last_frame_mono is None else (time.monotonic() - self._last_frame_mono) * 1000
            ev = CameraStatusEvent(
                camera_id=self.camera_id,
                state=state,
                previous_state=prev,
                quality_issues=list(issues),
                detail=detail,
                fps=self.measured_fps(),
                frame_age_ms=None if age is None else round(age, 0),
            )
        try:
            self._on_event(ev)
        except Exception:
            log.exception("camera %s event sink failed", self.camera_id)

    # ------------------------------------------------------------------------ views
    def snapshot(self) -> dict:
        age = None if self._last_frame_mono is None else round(time.monotonic() - self._last_frame_mono, 2)
        return {
            "state": (self._state or CameraState.CONNECTING).value,
            "quality_issues": [i.value for i in self._issues],
            "fps": self.measured_fps(),
            "frame_age_s": age,
            "frames_total": self.buffer.total,
            "frames_overwritten": self.buffer.dropped,  # replaced before analysis (normal when analysis < capture fps)
            "analysis_ms": round(self._proc_ms, 1),
            "detail": self._acq_detail,
            "analyzers": [a.stats() for a in self.analyzers() if hasattr(a, "stats")],
        }

    def latest_jpeg(self, max_width: int, quality: int = 70) -> bytes | None:
        f = self.buffer.latest()
        if f is None:
            return None
        img = f.image
        h, w = img.shape[:2]
        if w > max_width:
            img = cv2.resize(img, (max_width, int(h * max_width / w)))
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None
