"""Spatial interaction analyzer: out_of_seat, repeated_direction_change, and proximity rules.
Produces explainable SpatialInteractionObservation records with limitations.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import numpy as np

from app.config import Settings
from app.perception.occupancy import OccupancyStore, SeatRegion
from app.perception.threaded import ThreadedAnalyzer
from app.schemas.events import (
    CameraState,
    SeatState,
    SpatialInteractionObservation,
    utcnow,
)

log = logging.getLogger(__name__)


class SpatialAnalyzer(ThreadedAnalyzer):
    name = "spatial_rules"

    def __init__(
        self,
        camera_id: str,
        settings: Settings,
        regions: list[SeatRegion],
        occupancy_store: OccupancyStore,
        emit: Callable[[object], None],
    ):
        # Sample at ~1.5 fps for spatial tracking
        super().__init__(camera_id, 1.0 / 1.5)
        self._s = settings
        self._regions = regions
        self._occ_store = occupancy_store
        self._emit = emit
        self._lock = threading.Lock()

        # History per seat:
        # seat_id -> list of timestamps when head pose or motion direction reversed
        self._direction_changes: dict[str, list[float]] = {}
        self._occupied_durations: dict[str, float] = {}
        self._last_state_change: dict[str, tuple[SeatState, float]] = {}
        self._last_alert_time: dict[str, float] = {}

    def record_direction_event(self, seat_id: str, timestamp_mono: float) -> None:
        """Called when a significant gaze or head angle switch is observed."""
        with self._lock:
            if seat_id not in self._direction_changes:
                self._direction_changes[seat_id] = []
            self._direction_changes[seat_id].append(timestamp_mono)
            # Prune to last 45s
            self._direction_changes[seat_id] = [
                t for t in self._direction_changes[seat_id] if timestamp_mono - t <= 45.0
            ]

    def _infer(self, image: np.ndarray, ts: datetime) -> None:
        now_mono = time.monotonic()
        now_utc = ts

        # Check for repeated direction changes
        with self._lock:
            for seat_id, times in list(self._direction_changes.items()):
                # Filter last 30s
                recent = [t for t in times if now_mono - t <= 30.0]
                if len(recent) >= 4:
                    last_alert = self._last_alert_time.get(f"{seat_id}_direction", 0.0)
                    if now_mono - last_alert >= 15.0:  # 15s debounce
                        self._last_alert_time[f"{seat_id}_direction"] = now_mono
                        window_start = now_utc - timedelta(seconds=30)
                        self._emit(
                            SpatialInteractionObservation(
                                camera_id=self.camera_id,
                                kind="repeated_direction_change",
                                seat_ids=[seat_id],
                                window_start=window_start,
                                window_end=now_utc,
                                explanation=(
                                    f"Seat {seat_id}: {len(recent)} rapid head/gaze direction shifts observed in 30 seconds."
                                ),
                                limitations=[
                                    "Normal student movements (e.g. stretching or looking at a clock/whiteboard) can trigger this.",
                                    "Requires proctor visual verification."
                                ],
                            )
                        )

        # Check out-of-seat events using occupancy store
        # If a seat was OCCUPIED for at least 30 seconds and transitions to VACANT during exam
        for r in self._regions:
            seat_id = r.seat_id
            curr_state = self._occ_store.get(self.camera_id, seat_id)
            if not curr_state:
                continue

            last = self._last_state_change.get(seat_id)
            if last is None:
                self._last_state_change[seat_id] = (curr_state.state, now_mono)
                continue

            prev_state, prev_time = last
            if curr_state.state != prev_state:
                # State transition occurred
                self._last_state_change[seat_id] = (curr_state.state, now_mono)
                time_in_prev = now_mono - prev_time

                # If was occupied for >= 20 seconds and suddenly became vacant
                if prev_state == SeatState.OCCUPIED and curr_state.state == SeatState.VACANT and time_in_prev >= 20.0:
                    last_alert = self._last_alert_time.get(f"{seat_id}_out_of_seat", 0.0)
                    if now_mono - last_alert >= 30.0:
                        self._last_alert_time[f"{seat_id}_out_of_seat"] = now_mono
                        window_start = now_utc - timedelta(seconds=min(30.0, time_in_prev))
                        self._emit(
                            SpatialInteractionObservation(
                                camera_id=self.camera_id,
                                kind="out_of_seat",
                                seat_ids=[seat_id],
                                window_start=window_start,
                                window_end=now_utc,
                                explanation=(
                                    f"Seat {seat_id}: Student previously seated for {int(time_in_prev)}s has left the seat."
                                ),
                                limitations=[
                                    "Legitimate reasons include authorized restroom break or question submission.",
                                    "Camera occlusions can temporarily report seat as vacant."
                                ],
                            )
                        )

    def _on_state(self, state: CameraState) -> None:
        if state is not CameraState.CONNECTED:
            with self._lock:
                self._direction_changes.clear()
