from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import CameraRow, CameraSeatRegionRow, RoomRow, SeatRow
from app.perception.occupancy import fuse_seat
from app.rooms.seat_ids import SEAT_ID_RE, generate_grid
from app.schemas.events import SeatState, utcnow

from .deps import DEV_ACTOR, get_db

router = APIRouter(prefix="/api", tags=["rooms"])


def _err(status: int, code: str, msg: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": msg})


class SeatIn(BaseModel):
    seat_id: str = Field(min_length=1, max_length=32)
    row: int = Field(ge=1, le=100)
    col: int = Field(ge=1, le=100)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    monitored: bool = True


class SeatOut(SeatIn):
    pass


class GridSpec(BaseModel):
    rows: int = Field(ge=1, le=30)
    cols: int = Field(ge=1, le=30)


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    width_m: float = Field(gt=0, le=200)
    depth_m: float = Field(gt=0, le=200)
    generate: GridSpec | None = None  # convenience: auto-create an R{row}-C{col} grid of seats


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    width_m: float | None = Field(default=None, gt=0, le=200)
    depth_m: float | None = Field(default=None, gt=0, le=200)


class RoomOut(BaseModel):
    room_id: str
    name: str
    width_m: float
    depth_m: float
    created_at: datetime
    seat_count: int


class RoomDetail(RoomOut):
    seats: list[SeatOut]


def _room(db: Session, room_id: str) -> RoomRow:
    r = db.get(RoomRow, room_id)
    if not r:
        raise _err(404, "ROOM_NOT_FOUND", "Room not found.")
    return r


def _seats(db: Session, room_id: str) -> list[SeatRow]:
    return list(db.scalars(select(SeatRow).where(SeatRow.room_id == room_id).order_by(SeatRow.row, SeatRow.col)))


def _out(db: Session, r: RoomRow) -> RoomOut:
    n = len(_seats(db, r.room_id))
    return RoomOut(room_id=r.room_id, name=r.name, width_m=r.width_m, depth_m=r.depth_m, created_at=r.created_at, seat_count=n)


def _reload(request: Request, db: Session, camera_ids: list[str]) -> None:
    """Hot-reload analyzers of running cameras after calibration/seat changes."""
    from app.perception.wiring import build_analyzers
    st = request.app.state
    for cid in camera_ids:
        if st.cameras.is_running(cid):
            st.cameras.set_analyzers(cid, build_analyzers(st, db, cid))


@router.get("/rooms", response_model=list[RoomOut])
def list_rooms(db: Session = Depends(get_db)):
    return [_out(db, r) for r in db.scalars(select(RoomRow).order_by(RoomRow.created_at))]


@router.post("/rooms", response_model=RoomDetail, status_code=201)
def create_room(body: RoomCreate, request: Request, db: Session = Depends(get_db)):
    room = RoomRow(room_id=f"ROOM-{uuid.uuid4().hex[:6].upper()}", name=body.name.strip(), width_m=body.width_m, depth_m=body.depth_m)
    db.add(room)
    if body.generate:
        for s in generate_grid(body.generate.rows, body.generate.cols):
            db.add(SeatRow(room_id=room.room_id, **s))
    request.app.state.events.audit(db, DEV_ACTOR, "room.create", "room", room.room_id, {"name": room.name})
    try:  # flush happens inside commit, so a duplicate name is caught here (-> 409, not 500)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _err(409, "DUPLICATE_NAME", "A room with this name already exists.") from None
    return RoomDetail(**_out(db, room).model_dump(), seats=[SeatOut.model_validate(s, from_attributes=True) for s in _seats(db, room.room_id)])


@router.get("/rooms/{room_id}", response_model=RoomDetail)
def get_room(room_id: str, db: Session = Depends(get_db)):
    r = _room(db, room_id)
    return RoomDetail(**_out(db, r).model_dump(), seats=[SeatOut.model_validate(s, from_attributes=True) for s in _seats(db, room_id)])


@router.put("/rooms/{room_id}", response_model=RoomOut)
def update_room(room_id: str, body: RoomUpdate, request: Request, db: Session = Depends(get_db)):
    r = _room(db, room_id)
    for f in ("name", "width_m", "depth_m"):
        v = getattr(body, f)
        if v is not None:
            setattr(r, f, v.strip() if isinstance(v, str) else v)
    request.app.state.events.audit(db, DEV_ACTOR, "room.update", "room", room_id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _err(409, "DUPLICATE_NAME", "A room with this name already exists.") from None
    return _out(db, r)


@router.get("/rooms/{room_id}/seats", response_model=list[SeatOut])
def get_seats(room_id: str, db: Session = Depends(get_db)):
    _room(db, room_id)
    return [SeatOut.model_validate(s, from_attributes=True) for s in _seats(db, room_id)]


@router.put("/rooms/{room_id}/seats", response_model=list[SeatOut])
def put_seats(room_id: str, body: list[SeatIn], request: Request, db: Session = Depends(get_db)):
    """Replace the room's seat list. Seats omitted here are deleted along with their camera regions."""
    _room(db, room_id)
    ids = [s.seat_id for s in body]
    if len(set(ids)) != len(ids):
        raise _err(422, "DUPLICATE_SEAT_ID", "Seat IDs must be unique within a room.")
    bad = [i for i in ids if not SEAT_ID_RE.match(i)]
    if bad:
        raise _err(422, "INVALID_SEAT_ID", f"Invalid seat ID(s): {', '.join(bad[:5])}. Use letters, digits, '-' or '_'.")
    existing = {s.seat_id: s for s in _seats(db, room_id)}
    for sid in set(existing) - set(ids):
        db.delete(existing[sid])
    for s in body:
        if s.seat_id in existing:
            row = existing[s.seat_id]
            row.row, row.col, row.x, row.y, row.monitored = s.row, s.col, s.x, s.y, s.monitored
        else:
            db.add(SeatRow(room_id=room_id, **s.model_dump()))
    cams = [c for (c,) in db.execute(select(CameraRow.camera_id).where(CameraRow.room_id == room_id))]
    request.app.state.events.audit(db, DEV_ACTOR, "room.seats.replace", "room", room_id, {"count": len(body)})
    db.commit()
    _reload(request, db, cams)
    return [SeatOut.model_validate(s, from_attributes=True) for s in _seats(db, room_id)]


@router.get("/rooms/{room_id}/occupancy")
def occupancy(room_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Current fused seat states. A seat is counted once even if several cameras see it, and a
    seat whose cameras are stopped/stale is UNCERTAIN, never the last-known state."""
    st = request.app.state
    _room(db, room_id)
    seats = _seats(db, room_id)
    regions = db.scalars(select(CameraSeatRegionRow).where(CameraSeatRegionRow.room_id == room_id)).all()
    by_seat: dict[str, list[tuple[str, str]]] = {}
    for g in regions:
        by_seat.setdefault(g.seat_id, []).append((g.camera_id, g.visibility))
    now = utcnow()
    out, counts = [], {s.value: 0 for s in SeatState}
    for s in seats:
        f = fuse_seat(s.seat_id, s.monitored, by_seat.get(s.seat_id, []), st.occupancy, now, st.settings.occ_freshness_s)
        counts[f.state.value] += 1
        out.append({"seat_id": s.seat_id, "state": f.state.value, "confidence": round(f.confidence, 3), "reason": f.reason,
                    "cameras": f.cameras, "updated_at": f.updated_at})
    cams = []
    for c in db.scalars(select(CameraRow).where(CameraRow.room_id == room_id)):
        rt = st.cameras.snapshot(c.camera_id)
        cams.append({"camera_id": c.camera_id, "name": c.name, "running": st.cameras.is_running(c.camera_id),
                     "state": rt["state"] if rt else None, "baseline_at": c.baseline_at,
                     "seats_covered": sum(1 for g in regions if g.camera_id == c.camera_id)})
    return {"room_id": room_id, "generated_at": now, "method": "baseline-diff-v1 (heuristic)",
            "summary": {"total": len(seats), **{k.lower(): v for k, v in counts.items()}}, "seats": out, "cameras": cams}
