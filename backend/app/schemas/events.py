"""Shared event contracts (schema_version 1.0).

Every AI module and backend component MUST use these models. Distinctions kept explicit:
  * *Observation  -> raw model/sensor output (high frequency, not a conclusion)
  * CandidateIncident -> fused, explainable group of observations (system output)
  * IncidentReview -> human decision (the only place an outcome is recorded)
Nothing here represents a finding of misconduct. Timestamps must be timezone-aware.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"
REVIEW_NOTICE = (
    "Automated review recommendation only. This is not a finding of misconduct; "
    "a human reviewer must evaluate the evidence."
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


# ----------------------------------------------------------------------------- enums
class CameraState(str, Enum):
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"  # frames arriving but quality flags raised
    STALE = "STALE"  # no new frames
    FROZEN = "FROZEN"  # frames arriving but image not changing
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class QualityIssue(str, Enum):
    DARK = "DARK"
    BLURRY = "BLURRY"


class SeatState(str, Enum):
    VACANT = "VACANT"
    OCCUPIED = "OCCUPIED"
    UNCERTAIN = "UNCERTAIN"
    OCCLUDED = "OCCLUDED"
    UNMONITORED = "UNMONITORED"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlertStatus(str, Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"
    REFERRED = "REFERRED"


class ReviewDecision(str, Enum):
    ACKNOWLEDGE = "ACKNOWLEDGE"
    DISMISS = "DISMISS"
    REFER = "REFER"


# ------------------------------------------------------------------------ building blocks
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BoundingBox(_Strict):
    """Normalised image coordinates in [0, 1]; origin top-left."""

    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> "BoundingBox":
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("bounding box must have x2 > x1 and y2 > y1")
        return self


class ObservationQuality(_Strict):
    status: Literal["ok", "low_quality", "unsupported"] = "ok"
    score: float | None = Field(default=None, ge=0, le=1)
    notes: list[str] = Field(default_factory=list)


class _EventBase(_Strict):
    schema_version: str = SCHEMA_VERSION
    event_id: str = Field(default_factory=lambda: new_id("EVT"), min_length=4, max_length=64)
    camera_id: str | None = Field(default=None, max_length=64)
    seat_id: str | None = Field(default=None, max_length=64)
    timestamp: AwareDatetime = Field(default_factory=utcnow)
    is_synthetic: bool = False  # True => DEMO DATA, never a real detection

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        return v.astimezone(timezone.utc)


# ------------------------------------------------------------------------- observations
class CameraStatusEvent(_EventBase):
    event_type: Literal["camera_status"] = "camera_status"
    camera_id: str = Field(max_length=64)
    state: CameraState
    previous_state: CameraState | None = None
    quality_issues: list[QualityIssue] = Field(default_factory=list)
    detail: str | None = Field(default=None, max_length=500)
    fps: float | None = Field(default=None, ge=0)
    frame_age_ms: float | None = Field(default=None, ge=0)


class OccupancyObservation(_EventBase):
    event_type: Literal["occupancy"] = "occupancy"
    camera_id: str = Field(max_length=64)
    seat_id: str = Field(max_length=64)
    state: SeatState
    confidence: float = Field(ge=0, le=1)
    quality: ObservationQuality = Field(default_factory=ObservationQuality)
    method: str = Field(max_length=100)


class ObjectDetectionObservation(_EventBase):
    event_type: Literal["object_detection"] = "object_detection"
    camera_id: str = Field(max_length=64)
    object_class: str = Field(min_length=1, max_length=64)
    bbox: BoundingBox
    confidence: float = Field(ge=0, le=1)
    tracker_id: int | None = Field(default=None, ge=0)
    model_id: str = Field(max_length=100)
    model_version: str = Field(max_length=50)
    evidence_id: str | None = None


class TrackingObservation(_EventBase):
    event_type: Literal["tracking"] = "tracking"
    camera_id: str = Field(max_length=64)
    tracker_id: int = Field(ge=0)
    object_class: str = Field(max_length=64)
    bbox: BoundingBox
    track_state: Literal["new", "tracked", "lost", "expired"]
    tracker_name: str = Field(max_length=100)


class HeadPoseObservation(_EventBase):
    event_type: Literal["head_pose"] = "head_pose"
    camera_id: str = Field(max_length=64)
    tracker_id: int | None = Field(default=None, ge=0)
    yaw_deg: float | None = Field(default=None, ge=-180, le=180)
    pitch_deg: float | None = Field(default=None, ge=-180, le=180)
    roll_deg: float | None = Field(default=None, ge=-180, le=180)
    quality: ObservationQuality  # required: estimates without quality are not allowed
    method: str = Field(max_length=100)

    @model_validator(mode="after")
    def _no_angles_when_unsupported(self) -> "HeadPoseObservation":
        if self.quality.status == "unsupported" and any(
            a is not None for a in (self.yaw_deg, self.pitch_deg, self.roll_deg)
        ):
            raise ValueError("unsupported observations must not carry angle estimates")
        return self


class SpatialInteractionObservation(_EventBase):
    event_type: Literal["spatial_interaction"] = "spatial_interaction"
    camera_id: str = Field(max_length=64)
    kind: Literal["proximity", "out_of_seat", "repeated_direction_change", "object_handling"]
    seat_ids: list[str] = Field(default_factory=list)
    tracker_ids: list[int] = Field(default_factory=list)
    window_start: AwareDatetime
    window_end: AwareDatetime
    distance: float | None = Field(default=None, ge=0)
    distance_units: Literal["pixels", "normalized", "metres"] | None = None
    explanation: str = Field(max_length=1000)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _checks(self) -> "SpatialInteractionObservation":
        if self.window_end < self.window_start:
            raise ValueError("window_end must not precede window_start")
        if self.distance is not None and self.distance_units is None:
            raise ValueError("distance requires distance_units (pixel values are not metres)")
        return self


ObservationEvent = Annotated[
    Union[
        CameraStatusEvent,
        OccupancyObservation,
        ObjectDetectionObservation,
        TrackingObservation,
        HeadPoseObservation,
        SpatialInteractionObservation,
    ],
    Field(discriminator="event_type"),
]


# -------------------------------------------------------------- evidence / fusion / review
class EvidenceReference(_Strict):
    """Database-backed handle. Deliberately has NO filesystem path field."""

    schema_version: str = SCHEMA_VERSION
    evidence_id: str = Field(default_factory=lambda: new_id("EV"))
    kind: Literal["image", "clip"]
    camera_id: str
    captured_at: AwareDatetime = Field(default_factory=utcnow)
    status: Literal["available", "failed"]
    failure_reason: str | None = None

    @model_validator(mode="after")
    def _failure_has_reason(self) -> "EvidenceReference":
        if self.status == "failed" and not self.failure_reason:
            raise ValueError("failed evidence must record a failure_reason")
        return self


class RuleContribution(_Strict):
    rule_id: str
    description: str
    points: float = Field(ge=0)
    observation_ids: list[str] = Field(default_factory=list)


class CandidateIncident(_Strict):
    schema_version: str = SCHEMA_VERSION
    incident_id: str = Field(default_factory=lambda: new_id("INC"))
    category: str
    camera_id: str
    seat_id: str | None = None
    first_seen: AwareDatetime
    last_seen: AwareDatetime
    observation_ids: list[str] = Field(min_length=1)
    rules_triggered: list[RuleContribution] = Field(default_factory=list)
    # Operational review priority (0-100). NOT a probability of misconduct.
    review_priority_score: float = Field(ge=0, le=100)
    priority: Priority
    explanation: str
    limitations: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    is_synthetic: bool = False


class ReviewAlert(_Strict):
    schema_version: str = SCHEMA_VERSION
    alert_id: str = Field(default_factory=lambda: new_id("ALT"))
    incident_id: str
    title: str
    summary: str
    priority: Priority
    status: AlertStatus = AlertStatus.NEW
    created_at: AwareDatetime = Field(default_factory=utcnow)
    notice: str = REVIEW_NOTICE
    is_synthetic: bool = False


class IncidentReview(_Strict):
    schema_version: str = SCHEMA_VERSION
    review_id: str = Field(default_factory=lambda: new_id("REV"))
    alert_id: str
    reviewer_id: str
    decision: ReviewDecision
    notes: str = Field(default="", max_length=4000)
    reviewed_at: AwareDatetime = Field(default_factory=utcnow)


class AuditLogEntry(_Strict):
    schema_version: str = SCHEMA_VERSION
    audit_id: str = Field(default_factory=lambda: new_id("AUD"))
    actor: str
    action: str
    target_type: str | None = None
    target_id: str | None = None
    timestamp: AwareDatetime = Field(default_factory=utcnow)
    detail: dict = Field(default_factory=dict)
