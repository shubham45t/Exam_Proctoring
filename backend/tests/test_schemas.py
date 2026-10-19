from datetime import datetime, timedelta, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas import (
    REVIEW_NOTICE, BoundingBox, CameraState, CameraStatusEvent, CandidateIncident, EvidenceReference,
    HeadPoseObservation, ObjectDetectionObservation, ObservationEvent, ObservationQuality, Priority,
    ReviewAlert, SpatialInteractionObservation,
)

NOW = datetime.now(timezone.utc)
BOX = dict(x1=0.1, y1=0.1, x2=0.3, y2=0.3)


def det(**kw):
    base = dict(camera_id="C1", object_class="cell phone", bbox=BOX, confidence=0.8, model_id="m", model_version="1")
    return ObjectDetectionObservation(**{**base, **kw})


def test_valid_detection_roundtrip_and_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    e = det(timestamp=datetime(2026, 10, 15, 10, 32, 15, tzinfo=ist))
    assert e.timestamp.utcoffset() == timedelta(0)
    assert e.timestamp.hour == 5 and e.timestamp.minute == 2
    assert e.schema_version == "1.0" and e.is_synthetic is False


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError):
        det(timestamp=datetime(2026, 1, 1, 10, 0, 0))


@pytest.mark.parametrize("conf", [-0.1, 1.01])
def test_confidence_range(conf):
    with pytest.raises(ValidationError):
        det(confidence=conf)


def test_unknown_fields_forbidden():
    with pytest.raises(ValidationError):
        det(verdict="cheating")


def test_bbox_must_be_ordered_and_normalised():
    with pytest.raises(ValidationError):
        BoundingBox(x1=0.5, y1=0.1, x2=0.4, y2=0.3)
    with pytest.raises(ValidationError):
        BoundingBox(x1=0, y1=0, x2=1.5, y2=1)


def test_discriminated_union_parses_by_event_type():
    ta = TypeAdapter(ObservationEvent)
    ev = ta.validate_python(CameraStatusEvent(camera_id="C", state=CameraState.CONNECTED).model_dump(mode="json"))
    assert isinstance(ev, CameraStatusEvent)
    with pytest.raises(ValidationError):
        ta.validate_python({"event_type": "nonsense"})


def test_head_pose_requires_quality_and_no_angles_when_unsupported():
    with pytest.raises(ValidationError):
        HeadPoseObservation(camera_id="C", yaw_deg=10, method="x")  # quality missing
    with pytest.raises(ValidationError):
        HeadPoseObservation(camera_id="C", yaw_deg=10, method="x", quality=ObservationQuality(status="unsupported"))
    ok = HeadPoseObservation(camera_id="C", method="x", quality=ObservationQuality(status="unsupported"))
    assert ok.yaw_deg is None


def test_spatial_pixel_distance_needs_units_and_window_order():
    kw = dict(camera_id="C", kind="proximity", window_start=NOW, window_end=NOW, explanation="x")
    with pytest.raises(ValidationError):
        SpatialInteractionObservation(**kw, distance=12.0)
    with pytest.raises(ValidationError):
        SpatialInteractionObservation(**{**kw, "window_end": NOW - timedelta(seconds=1)})
    SpatialInteractionObservation(**kw, distance=12.0, distance_units="pixels")


def test_evidence_has_no_path_and_failure_needs_reason():
    assert not any("path" in f for f in EvidenceReference.model_fields)
    with pytest.raises(ValidationError):
        EvidenceReference(kind="image", camera_id="C", status="failed")
    EvidenceReference(kind="image", camera_id="C", status="failed", failure_reason="disk full")


def test_incident_score_bounds_and_alert_carries_notice():
    with pytest.raises(ValidationError):
        CandidateIncident(category="x", camera_id="C", first_seen=NOW, last_seen=NOW, observation_ids=["a"],
                          review_priority_score=101, priority=Priority.HIGH, explanation="e")
    with pytest.raises(ValidationError):
        CandidateIncident(category="x", camera_id="C", first_seen=NOW, last_seen=NOW, observation_ids=[],
                          review_priority_score=5, priority=Priority.LOW, explanation="e")
    a = ReviewAlert(incident_id="INC-1", title="t", summary="s", priority=Priority.LOW)
    assert a.notice == REVIEW_NOTICE and "not a finding of misconduct" in a.notice
