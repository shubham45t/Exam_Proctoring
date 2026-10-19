from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import EventRow
from app.schemas.events import ObjectDetectionObservation, BoundingBox

from .deps import DEV_ACTOR, get_db

router = APIRouter(prefix="/api", tags=["events"])


class EventOut(BaseModel):
    event_id: str
    event_type: str
    camera_id: str | None
    seat_id: str | None
    timestamp: datetime
    is_synthetic: bool
    payload: dict[str, Any]


class EventPage(BaseModel):
    items: list[EventOut]
    total: int
    limit: int
    offset: int


@router.get("/events", response_model=EventPage)
def list_events(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: str | None = None,
    camera_id: str | None = None,
    seat_id: str | None = None,
    is_synthetic: bool | None = None,
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    q = select(EventRow)
    for col, val in ((EventRow.event_type, event_type), (EventRow.camera_id, camera_id), (EventRow.seat_id, seat_id), (EventRow.is_synthetic, is_synthetic)):
        if val is not None:
            q = q.where(col == val)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(EventRow.timestamp.desc() if order == "desc" else EventRow.timestamp.asc()).limit(limit).offset(offset)
    items = [EventOut.model_validate(r, from_attributes=True) for r in db.scalars(q)]
    return EventPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: str, db: Session = Depends(get_db)):
    row = db.get(EventRow, event_id)
    if not row:
        raise HTTPException(404, detail={"code": "EVENT_NOT_FOUND", "message": "Event not found."})
    return EventOut.model_validate(row, from_attributes=True)


class SyntheticRequest(BaseModel):
    camera_id: str | None = None


@router.post("/events/synthetic", response_model=EventOut, status_code=201)
def create_synthetic(body: SyntheticRequest, request: Request, db: Session = Depends(get_db)):
    """DEMO DATA ONLY. Injects a clearly flagged fake object-detection observation to test the
    ingest -> database -> WebSocket -> dashboard path. It is not produced by any AI model."""
    st = request.app.state
    if not st.settings.synthetic_enabled:
        raise HTTPException(403, detail={"code": "SYNTHETIC_DISABLED", "message": "Synthetic events are disabled."})
    ev = ObjectDetectionObservation(
        camera_id=body.camera_id or "SYNTHETIC", object_class="DEMO_DATA", confidence=0.5,
        bbox=BoundingBox(x1=0.4, y1=0.4, x2=0.6, y2=0.6), model_id="synthetic-generator",
        model_version="none", is_synthetic=True,
    )
    st.events.ingest(ev)
    st.events.audit(db, DEV_ACTOR, "event.synthetic", "event", ev.event_id)
    db.commit()
    return EventOut(event_id=ev.event_id, event_type=ev.event_type, camera_id=ev.camera_id, seat_id=None,
                    timestamp=ev.timestamp, is_synthetic=True, payload=ev.model_dump(mode="json"))


ws_router = APIRouter()


@ws_router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    st = ws.app.state
    origin = ws.headers.get("origin")
    if origin and origin not in st.settings.cors_origins and not origin.startswith(("http://testserver",)):
        await ws.close(code=1008)  # browser cross-site WebSocket from an unlisted origin
        return
    await ws.accept()
    q = st.hub.subscribe()

    async def sender() -> None:
        await ws.send_json({"type": "hello", "data": {"schema_version": "1.0"}})
        while True:
            await ws.send_json(await q.get())

    async def receiver() -> None:
        # Needed so we notice client disconnects AND server shutdown (uvicorn closes the socket,
        # which surfaces here). Without it the handler blocks on q.get() and shutdown hangs.
        while (await ws.receive())["type"] != "websocket.disconnect":
            pass

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
    for t in tasks:  # mark exceptions as retrieved (send on a closed socket is expected at teardown)
        t.add_done_callback(lambda f: f.cancelled() or f.exception())
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        # Synchronous cleanup on purpose: awaiting here would re-raise CancelledError if this
        # handler is itself being cancelled (server shutdown / test-client teardown).
        for t in tasks:
            t.cancel()
        st.hub.unsubscribe(q)
