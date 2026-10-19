"""Builds analyzers for a camera from persisted calibration (regions + baseline)."""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.database.models import CameraSeatRegionRow

from .geometry import validate_polygon
from .occupancy import OccupancyAnalyzer, OccupancyStore, SeatRegion, prepare

_CAM_RE = re.compile(r"^CAM-[A-Z0-9]{6}$")


def baseline_path(settings: Settings, camera_id: str) -> Path:
    if not _CAM_RE.match(camera_id):  # path-traversal guard: only ids we generated are accepted
        raise ValueError("invalid camera id")
    return settings.calibration_dir / f"{camera_id}.png"


def save_baseline(settings: Settings, camera_id: str, image: np.ndarray) -> None:
    settings.calibration_dir.mkdir(parents=True, exist_ok=True)
    gray = prepare(image, settings.occ_analysis_width)
    if not cv2.imwrite(str(baseline_path(settings, camera_id)), np.clip(gray, 0, 255).astype(np.uint8)):
        raise OSError("could not write baseline image")


def load_baseline(settings: Settings, camera_id: str) -> np.ndarray | None:
    p = baseline_path(settings, camera_id)
    if not p.is_file():
        return None
    img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    return None if img is None else img.astype(np.float32)


def delete_baseline(settings: Settings, camera_id: str) -> None:
    baseline_path(settings, camera_id).unlink(missing_ok=True)


def build_analyzers(st, db: Session, camera_id: str) -> list:
    """Occupancy (if the camera has seat regions) + object detection + head pose + spatial rules.
    `st` is app.state. Analyzer threads are started here; whoever drops them must call close()."""
    from app.database.models import CameraRow
    from app.perception.detection.analyzer import ObjectAnalyzer
    from app.perception.head_pose import HeadPoseAnalyzer
    from app.perception.spatial import SpatialAnalyzer

    settings = st.settings
    rows = db.scalars(select(CameraSeatRegionRow).where(CameraSeatRegionRow.camera_id == camera_id)).all()
    regions = [SeatRegion(r.seat_id, validate_polygon(r.polygon), r.visibility) for r in rows]
    out: list = []
    if regions:
        out.append(OccupancyAnalyzer(camera_id, regions, load_baseline(settings, camera_id), settings, st.occupancy, st.events.ingest))
    cam = db.get(CameraRow, camera_id)
    if cam is not None and cam.object_detection:
        det = st.detectors.get()
        if det is not None:
            out.append(ObjectAnalyzer(camera_id, det, settings, regions, st.events.ingest, st.evidence.save_image).start())
    if cam is not None and getattr(cam, "head_pose_enabled", True) and regions:
        out.append(HeadPoseAnalyzer(camera_id, settings, regions, st.events.ingest).start())
    if cam is not None and getattr(cam, "spatial_rules_enabled", True) and regions:
        out.append(SpatialAnalyzer(camera_id, settings, regions, st.occupancy, st.events.ingest).start())
    return out
