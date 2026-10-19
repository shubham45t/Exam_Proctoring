"""Incident Fusion Engine (Phase 6).
Fuses multi-modal observations (object detection, head pose, spatial interactions, seat occupancy)
into explainable CandidateIncidents and operational ReviewAlerts for human proctors.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.database.models import CandidateIncidentRow, ExamRow, ReviewAlertRow
from app.schemas.events import (
    AlertStatus,
    CandidateIncident,
    Priority,
    ReviewAlert,
    RuleContribution,
    REVIEW_NOTICE,
    new_id,
    utcnow,
)

log = logging.getLogger(__name__)


class FusionEngine:
    def __init__(self, sessionmaker, hub, broadcast_func: Optional[Callable] = None):
        self._sessionmaker = sessionmaker
        self._hub = hub
        self._broadcast = broadcast_func
        self._lock = threading.Lock()
        # Track recent observations per (camera_id, seat_id) in rolling windows
        # key: (camera_id, seat_id) -> list of {type, id, ts, payload, evidence_id}
        self._window: dict[tuple[str, Optional[str]], list[dict]] = {}
        # Active incidents per key to correlate ongoing patterns
        self._active_incidents: dict[tuple[str, Optional[str]], str] = {}
        self._last_alert_ts: dict[tuple[str, Optional[str], str], float] = {}

    def on_observation(self, event_type: str, event_id: str, camera_id: str, seat_id: Optional[str], payload: dict, is_synthetic: bool = False) -> None:
        """Called whenever an observation event is ingested into OmniProctor."""
        now = time.monotonic()
        key = (camera_id, seat_id)

        with self._lock:
            if key not in self._window:
                self._window[key] = []
            
            entry = {
                "event_type": event_type,
                "event_id": event_id,
                "camera_id": camera_id,
                "seat_id": seat_id,
                "timestamp_mono": now,
                "timestamp_utc": utcnow(),
                "payload": payload,
                "evidence_id": payload.get("evidence_id"),
                "is_synthetic": is_synthetic,
            }
            self._window[key].append(entry)
            
            # Prune window to observations in the last 90 seconds
            self._window[key] = [e for e in self._window[key] if now - e["timestamp_mono"] <= 90.0]

            # Evaluate fusion rules
            self._evaluate(key, entry)

    def _evaluate(self, key: tuple[str, Optional[str]], current_entry: dict) -> None:
        camera_id, seat_id = key
        ev_type = current_entry["event_type"]
        now_mono = time.monotonic()

        # Check for active exam in this room (if any)
        with self._sessionmaker() as db:
            active_exam = db.query(ExamRow).filter(ExamRow.status == "IN_PROGRESS").first()
            exam_id = active_exam.exam_id if active_exam else None

        rules: list[RuleContribution] = []
        obs_ids: list[str] = [current_entry["event_id"]]
        evidence_ids: list[str] = []
        if current_entry.get("evidence_id"):
            evidence_ids.append(current_entry["evidence_id"])

        category = "PROCTORING_OBSERVATION"
        priority = Priority.LOW
        score = 25.0
        explanation_parts = []
        limitations = [
            "AI assessment only. Human review is required before taking any action.",
            "Camera perspectives and angles may not capture full student context.",
        ]

        # -------------------------------------------------------------
        # Rule 1: Prohibited Electronic Device (Cell Phone)
        # -------------------------------------------------------------
        if ev_type == "object_detection" and current_entry["payload"].get("object_class") == "cell phone":
            category = "PROHIBITED_DEVICE"
            priority = Priority.HIGH
            score = 90.0
            rules.append(
                RuleContribution(
                    rule_id="RULE-PHONE-01",
                    description="Mobile phone detected and confirmed by visual tracker in examination area",
                    points=90.0,
                    observation_ids=[current_entry["event_id"]],
                )
            )
            explanation_parts.append(
                f"A cell phone was identified and tracked in {f'seat {seat_id}' if seat_id else 'view of camera ' + camera_id} "
                f"with tracker #{current_entry['payload'].get('tracker_id', 'N/A')} (confidence {current_entry['payload'].get('confidence', 0.0):.2f})."
            )

        # -------------------------------------------------------------
        # Rule 2: Gaze Aversion / Head Turn
        # -------------------------------------------------------------
        elif ev_type == "head_pose":
            yaw = current_entry["payload"].get("yaw_deg", 0.0)
            if abs(yaw) >= 30.0:
                category = "GAZE_ANOMALY"
                priority = Priority.MEDIUM
                score = 55.0
                rules.append(
                    RuleContribution(
                        rule_id="RULE-GAZE-01",
                        description=f"Significant head orientation turn ({abs(yaw):.0f}° {'left' if yaw > 0 else 'right'}) away from desk",
                        points=55.0,
                        observation_ids=[current_entry["event_id"]],
                    )
                )
                explanation_parts.append(
                    f"Candidate at {f'seat {seat_id}' if seat_id else 'camera ' + camera_id} turned their head {abs(yaw):.0f}° "
                    f"away from the standard forward/desk orientation."
                )
                limitations.append("Occasional head rotation is normal for comfort, looking at the board, or reading question papers.")

        # -------------------------------------------------------------
        # Rule 3: Spatial interaction (out of seat or repeated direction change)
        # -------------------------------------------------------------
        elif ev_type == "spatial_interaction":
            kind = current_entry["payload"].get("kind")
            if kind == "out_of_seat":
                category = "OUT_OF_SEAT"
                priority = Priority.MEDIUM
                score = 65.0
                rules.append(
                    RuleContribution(
                        rule_id="RULE-SEAT-01",
                        description="Student left the designated workstation area during examination session",
                        points=65.0,
                        observation_ids=[current_entry["event_id"]],
                    )
                )
                explanation_parts.append(current_entry["payload"].get("explanation", "Student left seat."))
                limitations.append("Candidate may have authorized permission from an in-hall invigilator.")
            elif kind == "repeated_direction_change":
                category = "SUSPICIOUS_MOVEMENT"
                priority = Priority.MEDIUM
                score = 60.0
                rules.append(
                    RuleContribution(
                        rule_id="RULE-DIR-01",
                        description="Repeated rapid alternating direction changes within 30 seconds",
                        points=60.0,
                        observation_ids=[current_entry["event_id"]],
                    )
                )
                explanation_parts.append(current_entry["payload"].get("explanation", "Rapid direction shifts."))
            else:
                return  # don't alert on non-actionable spatial types

        # If synthetic event
        elif current_entry.get("is_synthetic"):
            category = "DEMO_DETECTION"
            priority = Priority.MEDIUM
            score = 50.0
            rules.append(
                RuleContribution(
                    rule_id="RULE-DEMO-01",
                    description="System demonstration event injected for pipeline verification",
                    points=50.0,
                    observation_ids=[current_entry["event_id"]],
                )
            )
            explanation_parts.append("Synthetic demo observation generated for verification.")

        else:
            return  # No alerting rule for this event

        # -------------------------------------------------------------
        # Multi-cue Correlation: Check other events in rolling window
        # -------------------------------------------------------------
        recent_in_window = self._window.get(key, [])
        for other in recent_in_window:
            if other["event_id"] != current_entry["event_id"]:
                if other["event_type"] == "head_pose" and ev_type == "object_detection":
                    score = min(98.0, score + 10.0)
                    rules.append(
                        RuleContribution(
                            rule_id="RULE-CORR-01",
                            description="Simultaneous head gaze shift and prohibited device detected",
                            points=10.0,
                            observation_ids=[other["event_id"]],
                        )
                    )
                    obs_ids.append(other["event_id"])
                    explanation_parts.append("Corroborated by gaze angle diversion in the same time window.")
                if other.get("evidence_id") and other["evidence_id"] not in evidence_ids:
                    evidence_ids.append(other["evidence_id"])

        # Debounce alerts of same category on same seat/camera (minimum 12 seconds between alerts)
        alert_key = (camera_id, seat_id, category)
        last_t = self._last_alert_ts.get(alert_key, 0.0)
        if now_mono - last_t < 12.0:
            return
        self._last_alert_ts[alert_key] = now_mono

        # Persist CandidateIncident and ReviewAlert
        incident_id = new_id("INC")
        alert_id = new_id("ALT")
        title = f"{category.replace('_', ' ').title()}{f' · Seat {seat_id}' if seat_id else ''}"
        summary = " ".join(explanation_parts)

        with self._sessionmaker() as db:
            inc_row = CandidateIncidentRow(
                incident_id=incident_id,
                exam_id=exam_id,
                category=category,
                camera_id=camera_id,
                seat_id=seat_id,
                first_seen=current_entry["timestamp_utc"],
                last_seen=current_entry["timestamp_utc"],
                priority=priority.value,
                review_priority_score=round(score, 1),
                explanation=summary,
                limitations=limitations,
                rules_triggered=[r.model_dump(mode="json") for r in rules],
                observation_ids=obs_ids,
                evidence_ids=evidence_ids,
                is_synthetic=current_entry.get("is_synthetic", False),
                created_at=utcnow(),
            )
            db.add(inc_row)

            alert_row = ReviewAlertRow(
                alert_id=alert_id,
                incident_id=incident_id,
                exam_id=exam_id,
                title=title,
                summary=summary,
                priority=priority.value,
                status=AlertStatus.NEW.value,
                created_at=utcnow(),
                notice=REVIEW_NOTICE,
                is_synthetic=current_entry.get("is_synthetic", False),
            )
            db.add(alert_row)
            db.commit()

        # Broadcast review alert over WebSocket hub
        if self._hub:
            ws_payload = {
                "type": "review_alert",
                "data": {
                    "alert_id": alert_id,
                    "incident_id": incident_id,
                    "title": title,
                    "summary": summary,
                    "priority": priority.value,
                    "status": AlertStatus.NEW.value,
                    "camera_id": camera_id,
                    "seat_id": seat_id,
                    "score": round(score, 1),
                    "evidence_ids": evidence_ids,
                    "created_at": utcnow().isoformat(),
                    "is_synthetic": current_entry.get("is_synthetic", False),
                },
            }
            self._hub.broadcast_sync(ws_payload)
            log.info("Fusion engine generated alert %s: %s (priority %s)", alert_id, title, priority.value)
