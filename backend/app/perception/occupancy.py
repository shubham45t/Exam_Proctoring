"""Seat occupancy from a fixed camera: HEURISTIC baseline-difference method (method id below).

How it works: the operator captures an image of the EMPTY room (baseline). For every seat region
we measure what fraction of pixels differ from the baseline (after global brightness matching).
A seat becomes OCCUPIED/VACANT only after `occ_confirm_count` consecutive consistent samples
(hysteresis), so flicker never flips the state.

Honest limits: this detects *change from the empty baseline*, not "a person". Bags, coats, moved
chairs, shadows, or lighting drift can look like occupancy; a student sitting very still in
baseline-coloured clothes can look vacant. It cannot detect occlusion by itself (OCCLUDED is set
manually in calibration). Thresholds are uncalibrated defaults. It is designed to be replaced or
supplemented by a person-detector behind the same observation contract.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import cv2
import numpy as np

from app.config import Settings
from app.schemas.events import (CameraState, ObservationQuality, OccupancyObservation, SeatState, utcnow)

from .geometry import Polygon, rasterise

log = logging.getLogger(__name__)
METHOD_ID = "baseline-diff-v1 (heuristic)"
VISIBILITIES = ("monitored", "partial", "not_visible")


# --------------------------------------------------------------------------- pure functions
def prepare(image: np.ndarray, width: int) -> np.ndarray:
    """BGR frame -> blurred grayscale at the analysis width (float32)."""
    h, w = image.shape[:2]
    if w != width:
        image = cv2.resize(image, (width, max(1, int(h * width / w))), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)


def change_map(base: np.ndarray, cur: np.ndarray, pixel_diff: int) -> np.ndarray:
    """Boolean map of pixels that differ from the empty baseline, after matching global brightness."""
    gain = float(np.clip(np.median(base) / max(float(np.median(cur)), 1.0), 0.5, 2.0))
    return np.abs(cur * gain - base) > pixel_diff


def region_fractions(changed: np.ndarray, masks: dict[str, np.ndarray]) -> dict[str, float]:
    return {sid: float(changed[m].mean()) if m.any() else 0.0 for sid, m in masks.items()}


# -------------------------------------------------------------------------- state machine
@dataclass
class SeatTracker:
    enter: float
    exit: float
    confirm: int
    state: SeatState = SeatState.UNCERTAIN
    reason: str | None = "no confirmed observation yet"
    confidence: float = 0.0
    _occ: int = 0
    _vac: int = 0

    def update(self, fraction: float) -> None:
        if fraction >= self.enter:
            self._occ, self._vac = self._occ + 1, 0
        elif fraction <= self.exit:
            self._vac, self._occ = self._vac + 1, 0
        else:  # between thresholds: neither streak advances, state is held
            self._occ = self._vac = 0
        if self._occ >= self.confirm:
            self.state, self.reason = SeatState.OCCUPIED, None
        elif self._vac >= self.confirm:
            self.state, self.reason = SeatState.VACANT, None
        # margin-based score: how far past the threshold, capped. NOT a calibrated probability.
        if self.state is SeatState.OCCUPIED:
            self.confidence = min(1.0, 0.5 + 0.5 * (fraction - self.enter) / max(self.enter, 1e-6))
        elif self.state is SeatState.VACANT:
            self.confidence = min(1.0, 0.5 + 0.5 * (self.exit - fraction) / max(self.exit, 1e-6))
        else:
            self.confidence = 0.0

    def force_uncertain(self, reason: str) -> None:
        self.state, self.reason, self.confidence = SeatState.UNCERTAIN, reason, 0.0
        self._occ = self._vac = 0


@dataclass
class SeatRegion:
    seat_id: str
    polygon: Polygon
    visibility: str  # monitored | partial | not_visible


# ------------------------------------------------------------------------- shared store
@dataclass
class CameraSeatObs:
    state: SeatState
    confidence: float
    ts: datetime
    reason: str | None = None


class OccupancyStore:
    """Latest per-(camera, seat) observation. Thread-safe; read by the REST API."""

    def __init__(self) -> None:
        self._d: dict[tuple[str, str], CameraSeatObs] = {}
        self._lock = threading.Lock()

    def set(self, camera_id: str, seat_id: str, obs: CameraSeatObs) -> None:
        with self._lock:
            self._d[(camera_id, seat_id)] = obs

    def get(self, camera_id: str, seat_id: str) -> CameraSeatObs | None:
        with self._lock:
            return self._d.get((camera_id, seat_id))

    def clear_camera(self, camera_id: str) -> None:
        with self._lock:
            for k in [k for k in self._d if k[0] == camera_id]:
                del self._d[k]


@dataclass
class FusedSeat:
    seat_id: str
    state: SeatState
    confidence: float
    reason: str | None
    cameras: list[dict] = field(default_factory=list)
    updated_at: datetime | None = None


def fuse_seat(seat_id: str, monitored: bool, mappings: list[tuple[str, str]], store: OccupancyStore,
              now: datetime, freshness_s: float) -> FusedSeat:
    """Combine every camera's view of ONE seat into one state (a seat is counted exactly once).

    mappings: [(camera_id, visibility)]. Rules, in order:
      not monitored / no camera mapping -> UNMONITORED (nobody is looking)
      every mapping marked not_visible  -> OCCLUDED (covered, but the view is blocked)
      no fresh observation              -> UNCERTAIN (never reports a stale state as current)
      any fresh OCCUPIED                -> OCCUPIED
      all fresh VACANT                  -> VACANT
      otherwise                         -> UNCERTAIN
    """
    if not monitored or not mappings:
        return FusedSeat(seat_id, SeatState.UNMONITORED, 0.0, "not monitored" if not monitored else "no camera covers this seat")
    usable = [(c, v) for c, v in mappings if v != "not_visible"]
    if not usable:
        return FusedSeat(seat_id, SeatState.OCCLUDED, 0.0, "seat marked as not adequately visible", [{"camera_id": c, "visibility": v} for c, v in mappings])
    cams, fresh = [], []
    for cam, vis in usable:
        o = store.get(cam, seat_id)
        age = None if o is None else (now - o.ts).total_seconds()
        cams.append({"camera_id": cam, "visibility": vis, "state": o.state.value if o else None,
                     "age_s": None if age is None else round(age, 1), "reason": o.reason if o else "no observation yet"})
        if o is not None and age is not None and age <= freshness_s:
            fresh.append(o)
    if not fresh:
        return FusedSeat(seat_id, SeatState.UNCERTAIN, 0.0, "no current observation (camera stopped, stale or not analysed yet)", cams)
    updated = max(o.ts for o in fresh)
    occ = [o for o in fresh if o.state is SeatState.OCCUPIED]
    if occ:
        return FusedSeat(seat_id, SeatState.OCCUPIED, max(o.confidence for o in occ), None, cams, updated)
    if all(o.state is SeatState.VACANT for o in fresh):
        return FusedSeat(seat_id, SeatState.VACANT, min(o.confidence for o in fresh), None, cams, updated)
    why = next((o.reason for o in fresh if o.reason), "cameras disagree or are uncertain")
    return FusedSeat(seat_id, SeatState.UNCERTAIN, 0.0, why, cams, updated)


# ----------------------------------------------------------------------------- analyzer
class OccupancyAnalyzer:
    """Per-camera analyzer plugged into CameraWorker (see worker.FrameAnalyzer)."""

    def __init__(self, camera_id: str, regions: list[SeatRegion], baseline: np.ndarray | None,
                 settings: Settings, store: OccupancyStore, emit: Callable[[OccupancyObservation], None]):
        self.camera_id, self._s, self._store, self._emit = camera_id, settings, store, emit
        self._lock = threading.Lock()
        self._regions = regions
        self._baseline = baseline  # prepared float32 gray at occ_analysis_width, or None
        self._masks: dict[str, np.ndarray] = {}
        if baseline is not None:
            h, w = baseline.shape
            self._masks = {r.seat_id: rasterise(r.polygon, w, h) for r in regions if r.visibility != "not_visible"}
        self._trackers = {r.seat_id: SeatTracker(settings.occ_enter_fraction, settings.occ_exit_fraction,
                                                 settings.occ_confirm_count) for r in regions if r.visibility != "not_visible"}
        self._last_emitted: dict[str, SeatState | None] = {}
        self._vis = {r.seat_id: r.visibility for r in regions}
        self.last_global_fraction: float | None = None
        self.small_regions = [sid for sid, m in self._masks.items() if int(m.sum()) < settings.occ_min_region_px]

    # -- worker hooks
    def on_state(self, state: CameraState) -> None:
        """Camera not CONNECTED => nothing it reports is current. Never keep the last state."""
        if state is CameraState.CONNECTED:
            return
        with self._lock:
            for sid, t in self._trackers.items():
                t.force_uncertain(f"camera {state.value.lower()}")
                self._publish(sid, t, quality_status="low_quality", note=f"camera {state.value}")

    def process(self, image: np.ndarray, ts: datetime | None = None) -> None:
        ts = ts or utcnow()
        with self._lock:
            if self._baseline is None:
                for sid, t in self._trackers.items():
                    if t.reason != "no empty-room baseline captured":
                        t.force_uncertain("no empty-room baseline captured")
                    self._publish(sid, t, ts, "low_quality", "no empty-room baseline captured")
                return
            cur = prepare(image, self._s.occ_analysis_width)
            if cur.shape != self._baseline.shape:
                for sid, t in self._trackers.items():
                    t.force_uncertain("frame size differs from baseline; recapture baseline")
                    self._publish(sid, t, ts, "low_quality", "frame size differs from baseline")
                return
            changed = change_map(self._baseline, cur, self._s.occ_pixel_diff)
            self.last_global_fraction = float(changed.mean())
            if self.last_global_fraction > self._s.occ_global_change_limit:
                for sid, t in self._trackers.items():  # lighting jump or camera moved: don't guess
                    t.force_uncertain("whole scene changed (lighting or camera moved?)")
                    self._publish(sid, t, ts, "low_quality", "whole scene changed")
                return
            fr = region_fractions(changed, self._masks)
            for sid, t in self._trackers.items():
                t.update(fr[sid])
                note = None
                status = "ok"
                if self._vis[sid] == "partial":
                    status, note = "low_quality", "seat only partially visible"
                    if t.state is SeatState.VACANT:  # an empty-looking visible part proves nothing about the rest
                        t.state, t.reason, t.confidence = SeatState.UNCERTAIN, "seat only partially visible; cannot confirm vacant", 0.0
                if sid in self.small_regions:
                    status, note = "low_quality", "seat region very small in image"
                self._publish(sid, t, ts, status, note, fr[sid])

    # -- internals
    def _publish(self, sid: str, t: SeatTracker, ts: datetime | None = None, quality_status: str = "ok",
                 note: str | None = None, fraction: float | None = None) -> None:
        ts = ts or utcnow()
        self._store.set(self.camera_id, sid, CameraSeatObs(t.state, t.confidence, ts, t.reason))
        if self._last_emitted.get(sid, SeatState.UNCERTAIN) != t.state:  # on change only; 'unknown' == UNCERTAIN, so no initial event
            self._last_emitted[sid] = t.state
            notes = [n for n in (note, t.reason, None if fraction is None else f"changed-pixel fraction {fraction:.2f}") if n]
            try:
                self._emit(OccupancyObservation(
                    camera_id=self.camera_id, seat_id=sid, state=t.state, confidence=round(t.confidence, 3),
                    quality=ObservationQuality(status=quality_status, notes=notes), method=METHOD_ID, timestamp=ts))
            except Exception:
                log.exception("occupancy emit failed")
