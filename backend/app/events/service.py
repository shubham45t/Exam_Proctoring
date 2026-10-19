"""Single ingestion path: validate (already done by Pydantic) -> persist -> publish to dashboards."""
from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import AuditLogRow, EventRow
from app.schemas.events import AuditLogEntry

from .hub import Hub

log = logging.getLogger(__name__)


def to_row(event: BaseModel) -> EventRow:
    return EventRow(
        event_id=event.event_id,
        event_type=event.event_type,
        schema_version=event.schema_version,
        camera_id=event.camera_id,
        seat_id=event.seat_id,
        timestamp=event.timestamp,
        is_synthetic=event.is_synthetic,
        payload=event.model_dump(mode="json"),
    )


class EventService:
    def __init__(self, sessions: sessionmaker, hub: Hub):
        self._sessions = sessions
        self._hub = hub
        self._loop: asyncio.AbstractEventLoop | None = None
        self._fusion = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def set_fusion_engine(self, engine) -> None:
        self._fusion = engine

    def publish_message(self, message: dict) -> None:
        self._publish(message)

    def ingest(self, event: BaseModel) -> None:
        """Thread-safe: callable from camera worker threads or request handlers."""
        with self._sessions() as db:
            db.add(to_row(event))
            db.commit()
        message = {
            "type": "camera_status" if event.event_type == "camera_status" else "event",
            "data": event.model_dump(mode="json"),
        }
        self._publish(message)

        if self._fusion is not None and getattr(event, "event_type", None) != "camera_status":
            try:
                self._fusion.on_observation(
                    event_type=event.event_type,
                    event_id=event.event_id,
                    camera_id=getattr(event, "camera_id", None),
                    seat_id=getattr(event, "seat_id", None),
                    payload=event.model_dump(mode="json"),
                    is_synthetic=getattr(event, "is_synthetic", False),
                )
            except Exception:
                log.exception("Fusion handler exception (continuing)")

    def _publish(self, message: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._hub.publish(message)
        else:
            loop.call_soon_threadsafe(self._hub.publish, message)

    def audit(self, db: Session, actor: str, action: str, target_type: str | None = None,
              target_id: str | None = None, detail: dict | None = None) -> None:
        e = AuditLogEntry(actor=actor, action=action, target_type=target_type, target_id=target_id, detail=detail or {})
        db.add(AuditLogRow(**e.model_dump(exclude={"schema_version"})))
