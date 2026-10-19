"""Phase 1 tables: cameras, events, audit_logs.
Remaining entities (users, rooms, seats, exams, incidents, evidence, reviews) are added in the
phases that need them, each via a new Alembic revision.

events.camera_id is intentionally NOT a foreign key: deleting a camera must not erase or
orphan the historical observation record (see docs/architecture.md)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, Text, ForeignKey, ForeignKeyConstraint, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.database.session import UTCDateTime
from app.schemas.events import utcnow


class Base(DeclarativeBase):
    pass


class CameraRow(Base):
    __tablename__ = "cameras"
    camera_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    source_type: Mapped[str] = mapped_column(String(20))
    # May contain credentials (e.g. rtsp://user:pass@host). Never returned by the API.
    # TODO(Phase 8): encrypt at rest.
    source_uri: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    room_id: Mapped[str | None] = mapped_column(ForeignKey("rooms.room_id", ondelete="SET NULL"), nullable=True)
    baseline_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)  # empty-room baseline capture time
    object_detection: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    head_pose_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    spatial_rules_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class RoomRow(Base):
    __tablename__ = "rooms"
    room_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    width_m: Mapped[float] = mapped_column(Float)
    depth_m: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SeatRow(Base):
    __tablename__ = "seats"
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.room_id", ondelete="CASCADE"), primary_key=True)
    seat_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    row: Mapped[int] = mapped_column(Integer)
    col: Mapped[int] = mapped_column(Integer)
    x: Mapped[float] = mapped_column(Float)  # 0..1 across the room width (multiply by width_m for metres)
    y: Mapped[float] = mapped_column(Float)  # 0..1 across the room depth
    monitored: Mapped[bool] = mapped_column(Boolean, default=True)


class CameraSeatRegionRow(Base):
    """Manual calibration: where a seat appears in a camera image. Several cameras may map one seat."""

    __tablename__ = "camera_seat_regions"
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id", ondelete="CASCADE"), primary_key=True)
    room_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seat_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    polygon: Mapped[list] = mapped_column(JSON)  # [[x, y], ...] normalised image coordinates
    visibility: Mapped[str] = mapped_column(String(20))  # monitored | partial | not_visible
    __table_args__ = (
        ForeignKeyConstraint(["room_id", "seat_id"], ["seats.room_id", "seats.seat_id"], ondelete="CASCADE"),
    )


class EventRow(Base):
    __tablename__ = "events"
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    schema_version: Mapped[str] = mapped_column(String(10))
    camera_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        Index("ix_events_camera_ts", "camera_id", "timestamp"),
        Index("ix_events_ts", "timestamp"),
    )


class AuditLogRow(Base):
    __tablename__ = "audit_logs"
    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class EvidenceRow(Base):
    """Evidence metadata. The file path is NEVER stored from user input: it is derived from
    camera_id + evidence_id (both server-generated). camera_id is not an FK so history survives camera deletion."""

    __tablename__ = "evidence"
    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    camera_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # image | clip
    status: Mapped[str] = mapped_column(String(10))  # available | failed
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    file_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # None when status == failed
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class UserRow(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))  # admin | proctor | auditor
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ExamRow(Base):
    __tablename__ = "exams"
    exam_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    course_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    room_id: Mapped[str | None] = mapped_column(ForeignKey("rooms.room_id", ondelete="SET NULL"), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="SCHEDULED", server_default="SCHEDULED")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CandidateIncidentRow(Base):
    __tablename__ = "candidate_incidents"
    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    exam_id: Mapped[str | None] = mapped_column(ForeignKey("exams.exam_id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String(50))
    camera_id: Mapped[str] = mapped_column(String(64))
    seat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime)
    priority: Mapped[str] = mapped_column(String(20))
    review_priority_score: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    rules_triggered: Mapped[list] = mapped_column(JSON, default=list)
    observation_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ReviewAlertRow(Base):
    __tablename__ = "review_alerts"
    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("candidate_incidents.incident_id", ondelete="CASCADE"))
    exam_id: Mapped[str | None] = mapped_column(ForeignKey("exams.exam_id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="NEW", server_default="NEW")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    notice: Mapped[str] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class IncidentReviewRow(Base):
    __tablename__ = "incident_reviews"
    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("review_alerts.alert_id", ondelete="CASCADE"))
    reviewer_id: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(20))  # ACKNOWLEDGE | DISMISS | REFER
    notes: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
