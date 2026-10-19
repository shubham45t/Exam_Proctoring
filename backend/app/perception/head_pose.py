"""Lightweight CPU-based face and head pose estimator using OpenCV Haar Cascades and feature geometry.
Computes yaw, pitch, and roll angles without requiring PyTorch or heavy dependencies.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import cv2
import numpy as np

from app.config import Settings
from app.perception.occupancy import SeatRegion
from app.perception.threaded import ThreadedAnalyzer
from app.schemas.events import (
    BoundingBox,
    CameraState,
    HeadPoseObservation,
    ObservationQuality,
    utcnow,
)

log = logging.getLogger(__name__)


def point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def seat_for_point(cx: float, cy: float, regions: list[SeatRegion]) -> Optional[str]:
    for r in regions:
        if r.visibility != "not_visible" and point_in_polygon(cx, cy, r.polygon):
            return r.seat_id
    return None


class HeadPoseAnalyzer(ThreadedAnalyzer):
    name = "head_pose"

    def __init__(
        self,
        camera_id: str,
        settings: Settings,
        regions: list[SeatRegion],
        emit: Callable[[object], None],
    ):
        # Sample at ~2 fps to conserve CPU
        super().__init__(camera_id, 1.0 / 2.0)
        self._s = settings
        self._regions = regions
        self._emit = emit
        self._last_state: CameraState = CameraState.CONNECTED
        self._lock = threading.Lock()

        # Load cascade classifiers
        self._face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self._eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
        self._profile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")

        # Track history per seat: seat_id -> list of (timestamp, yaw)
        self._gaze_history: dict[str, list[tuple[float, float]]] = {}
        self._last_alert_time: dict[str, float] = {}

    def _infer(self, image: np.ndarray, ts: datetime) -> None:
        h, w = image.shape[:2]
        if w > 640:
            scale = 640.0 / w
            small = cv2.resize(image, (640, int(h * scale)))
        else:
            scale = 1.0
            small = image

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        # Detect frontal faces
        faces = self._face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.15,
            minNeighbors=4,
            minSize=(30, 30),
        )

        detected_seats = set()

        for (fx, fy, fw, fh) in faces:
            # Map face center to normalised coordinates [0, 1]
            orig_cx = (fx + fw / 2.0) / (small.shape[1])
            orig_cy = (fy + fh / 2.0) / (small.shape[0])
            seat_id = seat_for_point(orig_cx, orig_cy, self._regions)
            if not seat_id:
                continue

            detected_seats.add(seat_id)

            # Analyze face ROI for eye positions to estimate horizontal yaw
            face_roi = gray[fy : fy + int(fh * 0.6), fx : fx + fw]
            eyes = self._eye_cascade.detectMultiScale(face_roi, scaleFactor=1.1, minNeighbors=3, minSize=(12, 12))

            yaw_deg = 0.0
            pitch_deg = -5.0  # slight downward gaze to exam paper is standard
            roll_deg = 0.0

            if len(eyes) >= 2:
                # Sort eyes by x coordinate
                eyes_sorted = sorted(eyes, key=lambda e: e[0])
                left_eye = eyes_sorted[0]
                right_eye = eyes_sorted[-1]
                
                # Eye center x offset from face center
                eye_mid_x = (left_eye[0] + left_eye[2] / 2.0 + right_eye[0] + right_eye[2] / 2.0) / 2.0
                face_mid_x = fw / 2.0
                offset_ratio = (eye_mid_x - face_mid_x) / (fw / 2.0)
                yaw_deg = float(np.clip(offset_ratio * 45.0, -60.0, 60.0))

                # Eye horizontal slant gives roll
                dy = (right_eye[1] + right_eye[3] / 2.0) - (left_eye[1] + left_eye[3] / 2.0)
                dx = (right_eye[0] + right_eye[2] / 2.0) - (left_eye[0] + left_eye[2] / 2.0)
                if dx > 0:
                    roll_deg = float(np.degrees(np.arctan2(dy, dx)))
            elif len(eyes) == 1:
                # One eye visible often means a profile or turned head
                eye = eyes[0]
                eye_center_x = eye[0] + eye[2] / 2.0
                if eye_center_x < fw / 2.0:
                    yaw_deg = 35.0  # turned left
                else:
                    yaw_deg = -35.0  # turned right

            # Record in history
            now_mono = time.monotonic()
            if seat_id not in self._gaze_history:
                self._gaze_history[seat_id] = []
            self._gaze_history[seat_id].append((now_mono, yaw_deg))
            # Keep last 30s
            self._gaze_history[seat_id] = [(t, y) for (t, y) in self._gaze_history[seat_id] if now_mono - t <= 30.0]

            # Emit HeadPoseObservation if significant turn (|yaw| >= 20 deg)
            if abs(yaw_deg) >= 20.0:
                last_alert = self._last_alert_time.get(seat_id, 0.0)
                # Rate limit emission to once every 3 seconds per seat
                if now_mono - last_alert >= 3.0:
                    self._last_alert_time[seat_id] = now_mono
                    obs = HeadPoseObservation(
                        camera_id=self.camera_id,
                        seat_id=seat_id,
                        timestamp=ts,
                        yaw_deg=round(yaw_deg, 1),
                        pitch_deg=round(pitch_deg, 1),
                        roll_deg=round(roll_deg, 1),
                        quality=ObservationQuality(
                            status="ok",
                            score=0.80,
                            notes=[f"Head turned {abs(yaw_deg):.0f}° {'left' if yaw_deg > 0 else 'right'}"],
                        ),
                        method="opencv-haar-geometry-v1",
                    )
                    self._emit(obs)

        # Also check profile cascade for seats where frontal face wasn't found
        for r in self._regions:
            if r.seat_id in detected_seats or r.visibility == "not_visible":
                continue
            # Look for profile face
            # We check polygon bounds to crop ROI
            xs = [p[0] for p in r.polygon]
            ys = [p[1] for p in r.polygon]
            rx1, ry1 = int(min(xs) * small.shape[1]), int(min(ys) * small.shape[0])
            rx2, ry2 = int(max(xs) * small.shape[1]), int(max(ys) * small.shape[0])
            if rx2 <= rx1 or ry2 <= ry1:
                continue
            roi = gray[max(0, ry1) : min(small.shape[0], ry2), max(0, rx1) : min(small.shape[1], rx2)]
            if roi.shape[0] < 30 or roi.shape[1] < 30:
                continue

            profiles = self._profile_cascade.detectMultiScale(roi, scaleFactor=1.2, minNeighbors=3, minSize=(25, 25))
            if len(profiles) > 0:
                now_mono = time.monotonic()
                last_alert = self._last_alert_time.get(r.seat_id, 0.0)
                if now_mono - last_alert >= 4.0:
                    self._last_alert_time[r.seat_id] = now_mono
                    self._emit(
                        HeadPoseObservation(
                            camera_id=self.camera_id,
                            seat_id=r.seat_id,
                            timestamp=ts,
                            yaw_deg=55.0,  # profile turn
                            pitch_deg=0.0,
                            roll_deg=0.0,
                            quality=ObservationQuality(
                                status="ok",
                                score=0.75,
                                notes=["Profile view detected (head turned away)"],
                            ),
                            method="opencv-profile-cascade-v1",
                        )
                    )

    def _on_state(self, state: CameraState) -> None:
        self._last_state = state
        if state is not CameraState.CONNECTED:
            with self._lock:
                self._gaze_history.clear()
