"""Object detection + tracking + dedup + evidence for one camera.

Persisted output is deliberately sparse: per *confirmed track* exactly one ObjectDetectionObservation
(with evidence) and TrackingObservations for lost/reacquired/expired. A phone that stays in view for
10 minutes is ONE observation, not thousands. Unconfirmed flickers are never persisted."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable

import numpy as np

from app.config import Settings
from app.perception.occupancy import SeatRegion
from app.perception.threaded import ThreadedAnalyzer
from app.schemas.events import (BoundingBox, CameraState, EvidenceReference, ObjectDetectionObservation,
                                TrackingObservation, utcnow)

from .base import ObjectDetector
from .tracker import IoUTracker, Track, TrackEvent

log = logging.getLogger(__name__)
_TRACK_STATE = {"confirmed": "new", "lost": "lost", "reacquired": "tracked", "expired": "expired"}


def point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def seat_for_box(box: tuple[float, float, float, float], regions: list[SeatRegion]) -> str | None:
    """Seat whose calibrated region contains the box CENTRE (smallest region wins). None if unmapped or
    only 'not_visible' regions match. A phone lying on a desk may sit outside the person-shaped region:
    None means 'unknown', never 'no seat involved'."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    best: tuple[float, str] | None = None
    for r in regions:
        if r.visibility == "not_visible" or not point_in_polygon(cx, cy, r.polygon):
            continue
        area = abs(sum(r.polygon[i][0] * r.polygon[(i + 1) % len(r.polygon)][1] - r.polygon[(i + 1) % len(r.polygon)][0] * r.polygon[i][1]
                       for i in range(len(r.polygon)))) / 2
        if best is None or area < best[0]:
            best = (area, r.seat_id)
    return best[1] if best else None


def _bbox(box: tuple[float, float, float, float]) -> BoundingBox:
    c = lambda v: min(1.0, max(0.0, v))  # noqa: E731
    return BoundingBox(x1=c(box[0]), y1=c(box[1]), x2=c(box[2]), y2=c(box[3]))


class ObjectAnalyzer(ThreadedAnalyzer):
    name = "object_detection"

    def __init__(self, camera_id: str, detector: ObjectDetector, settings: Settings, regions: list[SeatRegion],
                 emit: Callable[[object], None],
                 save_evidence: Callable[[str, np.ndarray, list, datetime], EvidenceReference | None]):
        super().__init__(camera_id, 1.0 / settings.detect_fps)
        s = settings
        self._det, self._regions, self._emit, self._save = detector, regions, emit, save_evidence
        self.tracker = IoUTracker(s.track_high_conf, s.track_match_iou, s.track_max_age_s, s.track_confirm_hits, s.track_confirm_min_s)
        self._active: list[Track] = []
        self._alock = threading.Lock()
        self.detections_total = 0
        self.model_id = detector.model_id

    # -- API view for live overlays
    def active_tracks(self) -> list[Track]:
        with self._alock:
            return list(self._active)

    def stats(self) -> dict:
        d = super().stats()
        d.update(model_id=self.model_id, detections_total=self.detections_total,
                 tentative_dropped=self.tracker.tentative_dropped, tracker=self.tracker.name)
        return d

    # -- worker thread
    def _infer(self, image: np.ndarray, ts: datetime) -> None:
        dets = self._det.detect(image)
        self.detections_total += len(dets)
        events = self.tracker.update(dets, ts.timestamp())
        with self._alock:
            self._active = self.tracker.active()
        for ev in events:
            self._handle(ev, image, ts)

    def _on_state(self, state: CameraState) -> None:
        if state is CameraState.CONNECTED:
            return
        ts = utcnow()  # camera unhealthy: no object is "still there" as far as we can know
        events = self.tracker.reset(ts.timestamp())
        with self._alock:
            self._active = []
        for ev in events:
            self._handle(ev, None, ts)

    def _handle(self, ev: TrackEvent, image: np.ndarray | None, ts: datetime) -> None:
        t = ev.track
        seat = seat_for_box(t.box, self._regions)
        try:
            if ev.kind == "confirmed":
                evidence = self._save(self.camera_id, image, [(t.box, f"{t.class_name} {t.confidence:.2f} #{t.track_id}")], ts) if image is not None else None
                self._emit(ObjectDetectionObservation(
                    camera_id=self.camera_id, seat_id=seat, timestamp=ts, object_class=t.class_name, bbox=_bbox(t.box),
                    confidence=round(t.confidence, 4), tracker_id=t.track_id, model_id=self._det.model_id,
                    model_version=self._det.model_version,
                    evidence_id=evidence.evidence_id if evidence else None))
            self._emit(TrackingObservation(
                camera_id=self.camera_id, seat_id=seat, timestamp=ts, tracker_id=t.track_id, object_class=t.class_name,
                bbox=_bbox(t.box), track_state=_TRACK_STATE[ev.kind], tracker_name=self.tracker.name))
        except Exception:
            log.exception("object analyzer emit failed")
