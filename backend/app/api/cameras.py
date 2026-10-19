from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cameras.adapters import build_source
from app.cameras.base import SourceError, SourceType
from app.cameras.probe import probe_source
from app.cameras.validation import VIDEO_EXTENSIONS, redact_uri, validate_source
from app.database.models import CameraRow, CameraSeatRegionRow, RoomRow, SeatRow
from app.perception.geometry import PolygonError, validate_polygon
from app.perception.occupancy import VISIBILITIES
from app.perception.wiring import baseline_path, build_analyzers, delete_baseline, save_baseline

from .deps import DEV_ACTOR, get_db

router = APIRouter(prefix="/api", tags=["cameras"])


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source_type: SourceType
    source_uri: str = Field(min_length=1, max_length=2048)
    object_detection: bool = True
    head_pose_enabled: bool = True
    spatial_rules_enabled: bool = True


class CameraPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    source_type: SourceType | None = None
    source_uri: str | None = Field(default=None, min_length=1, max_length=2048)
    object_detection: bool | None = None
    head_pose_enabled: bool | None = None
    spatial_rules_enabled: bool | None = None


class CameraOut(BaseModel):
    camera_id: str
    name: str
    source_type: SourceType
    source_display: str  # credentials and query values removed
    created_at: datetime
    room_id: str | None = None
    baseline_at: datetime | None = None
    object_detection: bool = True
    head_pose_enabled: bool = True
    spatial_rules_enabled: bool = True
    running: bool
    runtime: dict[str, Any] | None = None


def _display(row: CameraRow) -> str:
    st = SourceType(row.source_type)
    return redact_uri(row.source_uri) if st in (SourceType.HTTP_MJPEG, SourceType.RTSP) else row.source_uri


def _out(row: CameraRow, request: Request) -> CameraOut:
    mgr = request.app.state.cameras
    return CameraOut(
        camera_id=row.camera_id, name=row.name, source_type=SourceType(row.source_type),
        source_display=_display(row), created_at=row.created_at, room_id=row.room_id, baseline_at=row.baseline_at,
        object_detection=getattr(row, "object_detection", True),
        head_pose_enabled=getattr(row, "head_pose_enabled", True),
        spatial_rules_enabled=getattr(row, "spatial_rules_enabled", True),
        running=mgr.is_running(row.camera_id), runtime=mgr.snapshot(row.camera_id),
    )


def _err(status: int, e: SourceError) -> HTTPException:
    return HTTPException(status, detail=e.to_dict())


def _get(db: Session, camera_id: str) -> CameraRow:
    row = db.get(CameraRow, camera_id)
    if not row:
        raise HTTPException(404, detail={"code": "CAMERA_NOT_FOUND", "message": "Camera not found."})
    return row


def _validate(request: Request, st: SourceType, uri: str) -> None:
    try:
        validate_source(st, uri, request.app.state.settings.media_dir)
    except SourceError as e:
        raise _err(422, e) from None


@router.get("/media")
def list_media(request: Request) -> dict:
    d = request.app.state.settings.media_dir
    files = sorted(p.name for p in d.glob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS) if d.exists() else []
    return {"files": files}


@router.get("/cameras", response_model=list[CameraOut])
def list_cameras(request: Request, db: Session = Depends(get_db)):
    return [_out(r, request) for r in db.scalars(select(CameraRow).order_by(CameraRow.created_at))]


@router.post("/cameras", response_model=CameraOut, status_code=201)
def create_camera(body: CameraCreate, request: Request, db: Session = Depends(get_db)):
    _validate(request, body.source_type, body.source_uri)
    row = CameraRow(
        camera_id=f"CAM-{uuid.uuid4().hex[:6].upper()}",
        name=body.name.strip(),
        source_type=body.source_type.value,
        source_uri=body.source_uri.strip(),
        object_detection=body.object_detection,
        head_pose_enabled=body.head_pose_enabled,
        spatial_rules_enabled=body.spatial_rules_enabled,
    )
    db.add(row)
    request.app.state.events.audit(db, DEV_ACTOR, "camera.create", "camera", row.camera_id, {"name": row.name})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail={"code": "DUPLICATE_NAME", "message": "A camera with this name already exists."}) from None
    return _out(row, request)


@router.get("/cameras/{camera_id}", response_model=CameraOut)
def get_camera(camera_id: str, request: Request, db: Session = Depends(get_db)):
    return _out(_get(db, camera_id), request)


@router.patch("/cameras/{camera_id}", response_model=CameraOut)
def patch_camera(camera_id: str, body: CameraPatch, request: Request, db: Session = Depends(get_db)):
    row = _get(db, camera_id)
    if request.app.state.cameras.is_running(camera_id):
        raise HTTPException(409, detail={"code": "CAMERA_RUNNING", "message": "Stop the camera before editing it."})
    st = body.source_type or SourceType(row.source_type)
    uri = body.source_uri or row.source_uri
    _validate(request, st, uri)
    if body.name:
        row.name = body.name.strip()
    row.source_type, row.source_uri = st.value, uri.strip()
    if body.object_detection is not None:
        row.object_detection = body.object_detection
    if body.head_pose_enabled is not None:
        row.head_pose_enabled = body.head_pose_enabled
    if body.spatial_rules_enabled is not None:
        row.spatial_rules_enabled = body.spatial_rules_enabled
    request.app.state.events.audit(db, DEV_ACTOR, "camera.update", "camera", camera_id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail={"code": "DUPLICATE_NAME", "message": "A camera with this name already exists."}) from None
    return _out(row, request)


@router.delete("/cameras/{camera_id}", status_code=204)
def delete_camera(camera_id: str, request: Request, db: Session = Depends(get_db)):
    row = _get(db, camera_id)
    request.app.state.cameras.stop(camera_id)
    request.app.state.occupancy.clear_camera(camera_id)
    delete_baseline(request.app.state.settings, camera_id)
    db.delete(row)
    request.app.state.events.audit(db, DEV_ACTOR, "camera.delete", "camera", camera_id)
    db.commit()
    return Response(status_code=204)


def _probe(request: Request, row: CameraRow, max_frames: int):
    s = request.app.state.settings
    try:
        src = build_source(SourceType(row.source_type), row.source_uri, s)
    except SourceError as e:
        return None, e
    return probe_source(src, max_frames=max_frames, max_seconds=s.open_timeout_s + 4), None


@router.post("/cameras/{camera_id}/test")
def test_camera(camera_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Independent connectivity test; does not start processing."""
    row = _get(db, camera_id)
    if request.app.state.cameras.is_running(camera_id):
        return {"ok": True, "note": "Camera is already running; see runtime status.", "runtime": request.app.state.cameras.snapshot(camera_id)}
    result, err = _probe(request, row, max_frames=10)
    return {"ok": False, "error": err.to_dict()} if err else result.to_dict()


@router.post("/cameras/{camera_id}/start", response_model=CameraOut)
def start_camera(camera_id: str, request: Request, db: Session = Depends(get_db)):
    row = _get(db, camera_id)
    mgr, s = request.app.state.cameras, request.app.state.settings
    if mgr.is_running(camera_id):
        raise HTTPException(409, detail={"code": "ALREADY_RUNNING", "message": "Camera is already running."})
    result, err = _probe(request, row, max_frames=1)  # must prove connectivity before processing is enabled
    if err or not result.ok:
        raise HTTPException(502, detail=(err.to_dict() if err else result.error))
    st, uri = SourceType(row.source_type), row.source_uri
    analyzers = build_analyzers(request.app.state, db, camera_id)
    mgr.start(camera_id, lambda: build_source(st, uri, s), analyzers)
    request.app.state.events.audit(db, DEV_ACTOR, "camera.start", "camera", camera_id)
    db.commit()
    return _out(row, request)


@router.post("/cameras/{camera_id}/stop", response_model=CameraOut)
def stop_camera(camera_id: str, request: Request, db: Session = Depends(get_db)):
    row = _get(db, camera_id)
    request.app.state.cameras.stop(camera_id)
    request.app.state.events.audit(db, DEV_ACTOR, "camera.stop", "camera", camera_id)
    db.commit()
    return _out(row, request)


@router.get("/cameras/{camera_id}/detections")
def live_detections(camera_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Current tracked objects (for live overlays). Not persisted; persisted observations are in /api/events."""
    _get(db, camera_id)
    mgr = request.app.state.cameras
    tracks = mgr.active_tracks(camera_id) if mgr.is_running(camera_id) else []
    return {"camera_id": camera_id, "running": mgr.is_running(camera_id), "tracks": [
        {"tracker_id": t.track_id, "object_class": t.class_name, "confidence": round(t.confidence, 3), "confirmed": t.confirmed,
         "lost": t.lost, "bbox": {"x1": t.box[0], "y1": t.box[1], "x2": t.box[2], "y2": t.box[3]}} for t in tracks]}


@router.get("/cameras/{camera_id}/snapshot")
def snapshot(camera_id: str, request: Request, db: Session = Depends(get_db)):
    _get(db, camera_id)
    jpg = request.app.state.cameras.latest_jpeg(camera_id)
    if jpg is None:
        raise HTTPException(409, detail={"code": "NO_FRAME", "message": "No frame available; the camera is not running."})
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/cameras/{camera_id}/preview.mjpg")
async def preview(camera_id: str, request: Request, db: Session = Depends(get_db)):
    """Low-rate MJPEG preview (video frames never travel over the event WebSocket)."""
    _get(db, camera_id)
    mgr, fps = request.app.state.cameras, request.app.state.settings.preview_fps

    async def gen():
        while not await request.is_disconnected():
            jpg = await asyncio.to_thread(mgr.latest_jpeg, camera_id)
            if jpg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(1.0 / fps)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


# ----------------------------------------------------------------- calibration (seat regions, baseline)
class RegionIn(BaseModel):
    seat_id: str = Field(min_length=1, max_length=64)
    polygon: list[list[float]]
    visibility: str = "monitored"


class RegionsIn(BaseModel):
    room_id: str | None = None
    regions: list[RegionIn] = Field(default_factory=list, max_length=500)


@router.get("/cameras/{camera_id}/seat-regions")
def get_regions(camera_id: str, db: Session = Depends(get_db)) -> dict:
    row = _get(db, camera_id)
    rs = db.scalars(select(CameraSeatRegionRow).where(CameraSeatRegionRow.camera_id == camera_id)).all()
    return {"camera_id": camera_id, "room_id": row.room_id, "baseline_at": row.baseline_at,
            "regions": [{"seat_id": r.seat_id, "polygon": r.polygon, "visibility": r.visibility} for r in rs]}


@router.put("/cameras/{camera_id}/seat-regions")
def put_regions(camera_id: str, body: RegionsIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Replace this camera's seat calibration atomically. Works while the camera is running (hot reload)."""
    row = _get(db, camera_id)
    if body.room_id is None:
        if body.regions:
            raise HTTPException(422, detail={"code": "ROOM_REQUIRED", "message": "room_id is required when regions are given."})
    elif not db.get(RoomRow, body.room_id):
        raise HTTPException(404, detail={"code": "ROOM_NOT_FOUND", "message": "Room not found."})
    valid_seats = set(db.scalars(select(SeatRow.seat_id).where(SeatRow.room_id == body.room_id))) if body.room_id else set()
    seen, clean = set(), []
    for r in body.regions:
        if r.seat_id not in valid_seats:
            raise HTTPException(422, detail={"code": "UNKNOWN_SEAT", "message": f"Seat '{r.seat_id}' does not exist in this room."})
        if r.seat_id in seen:
            raise HTTPException(422, detail={"code": "DUPLICATE_SEAT_REGION", "message": f"Seat '{r.seat_id}' has more than one region for this camera."})
        if r.visibility not in VISIBILITIES:
            raise HTTPException(422, detail={"code": "INVALID_VISIBILITY", "message": f"visibility must be one of {', '.join(VISIBILITIES)}."})
        try:
            poly = validate_polygon(r.polygon)
        except PolygonError as e:
            raise HTTPException(422, detail={"code": "INVALID_POLYGON", "message": f"{r.seat_id}: {e}"}) from None
        seen.add(r.seat_id)
        clean.append((r.seat_id, [list(p) for p in poly], r.visibility))
    for old in db.scalars(select(CameraSeatRegionRow).where(CameraSeatRegionRow.camera_id == camera_id)):
        db.delete(old)
    db.flush()
    for sid, poly, vis in clean:
        db.add(CameraSeatRegionRow(camera_id=camera_id, room_id=body.room_id, seat_id=sid, polygon=poly, visibility=vis))
    row.room_id = body.room_id
    request.app.state.events.audit(db, DEV_ACTOR, "camera.regions.replace", "camera", camera_id, {"room_id": body.room_id, "count": len(clean)})
    db.commit()
    st = request.app.state
    st.occupancy.clear_camera(camera_id)
    if st.cameras.is_running(camera_id):
        st.cameras.set_analyzers(camera_id, build_analyzers(st, db, camera_id))
    return {"camera_id": camera_id, "room_id": body.room_id, "count": len(clean)}


@router.post("/cameras/{camera_id}/baseline")
def capture_baseline(camera_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Capture the EMPTY-room reference from the live camera. The operator must ensure nobody is in view."""
    from app.schemas.events import utcnow
    st = request.app.state
    row = _get(db, camera_id)
    if not st.cameras.is_running(camera_id) or st.cameras.runtime_state(camera_id) != "CONNECTED":
        raise HTTPException(409, detail={"code": "CAMERA_NOT_READY", "message": "Start the camera and wait until it is CONNECTED before capturing a baseline."})
    img = st.cameras.current_frame(camera_id)
    if img is None:
        raise HTTPException(409, detail={"code": "NO_FRAME", "message": "No frame available yet."})
    try:
        save_baseline(st.settings, camera_id, img)
    except OSError as e:
        raise HTTPException(500, detail={"code": "BASELINE_WRITE_FAILED", "message": str(e)}) from None
    row.baseline_at = utcnow()
    st.events.audit(db, DEV_ACTOR, "camera.baseline.capture", "camera", camera_id)
    db.commit()
    st.occupancy.clear_camera(camera_id)
    st.cameras.set_analyzers(camera_id, build_analyzers(st, db, camera_id))
    return {"camera_id": camera_id, "baseline_at": row.baseline_at}


@router.get("/cameras/{camera_id}/baseline")
def get_baseline(camera_id: str, request: Request, db: Session = Depends(get_db)):
    _get(db, camera_id)
    p = baseline_path(request.app.state.settings, camera_id)
    if not p.is_file():
        raise HTTPException(404, detail={"code": "NO_BASELINE", "message": "No baseline captured for this camera."})
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.delete("/cameras/{camera_id}/baseline", status_code=204)
def remove_baseline(camera_id: str, request: Request, db: Session = Depends(get_db)):
    row = _get(db, camera_id)
    st = request.app.state
    delete_baseline(st.settings, camera_id)
    row.baseline_at = None
    db.commit()
    st.occupancy.clear_camera(camera_id)
    if st.cameras.is_running(camera_id):
        st.cameras.set_analyzers(camera_id, build_analyzers(st, db, camera_id))
    return Response(status_code=204)
