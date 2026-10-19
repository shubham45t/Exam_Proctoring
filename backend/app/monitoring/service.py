"""Monitoring & Alert Review service."""
from __future__ import annotations

import uuid
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import CandidateIncidentRow, EvidenceRow, IncidentReviewRow, ReviewAlertRow
from app.schemas.events import AlertStatus, ReviewDecision, utcnow


class MonitoringService:
    @staticmethod
    def list_alerts(
        db: Session,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        exam_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ReviewAlertRow], int]:
        q = select(ReviewAlertRow)
        if status:
            q = q.where(ReviewAlertRow.status == status)
        if priority:
            q = q.where(ReviewAlertRow.priority == priority)
        if exam_id:
            q = q.where(ReviewAlertRow.exam_id == exam_id)
        
        total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items = list(
            db.scalars(
                q.order_by(ReviewAlertRow.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return items, total

    @staticmethod
    def get_alert_detail(db: Session, alert_id: str) -> Optional[dict]:
        alert = db.get(ReviewAlertRow, alert_id)
        if not alert:
            return None
        incident = db.get(CandidateIncidentRow, alert.incident_id)
        reviews = list(
            db.scalars(
                select(IncidentReviewRow)
                .where(IncidentReviewRow.alert_id == alert_id)
                .order_by(IncidentReviewRow.reviewed_at.desc())
            ).all()
        )
        
        # Fetch evidence metadata if available
        evidence_list = []
        if incident and incident.evidence_ids:
            for evid in incident.evidence_ids:
                erow = db.get(EvidenceRow, evid)
                if erow:
                    evidence_list.append({
                        "evidence_id": erow.evidence_id,
                        "kind": erow.kind,
                        "status": erow.status,
                        "captured_at": erow.captured_at.isoformat(),
                        "url": f"/api/evidence/{erow.evidence_id}" if erow.status == "available" else None,
                    })

        return {
            "alert": {
                "alert_id": alert.alert_id,
                "incident_id": alert.incident_id,
                "exam_id": alert.exam_id,
                "title": alert.title,
                "summary": alert.summary,
                "priority": alert.priority,
                "status": alert.status,
                "created_at": alert.created_at.isoformat(),
                "notice": alert.notice,
                "is_synthetic": alert.is_synthetic,
            },
            "incident": {
                "incident_id": incident.incident_id,
                "category": incident.category,
                "camera_id": incident.camera_id,
                "seat_id": incident.seat_id,
                "first_seen": incident.first_seen.isoformat(),
                "last_seen": incident.last_seen.isoformat(),
                "priority": incident.priority,
                "review_priority_score": incident.review_priority_score,
                "explanation": incident.explanation,
                "limitations": incident.limitations,
                "rules_triggered": incident.rules_triggered,
                "observation_ids": incident.observation_ids,
                "evidence_ids": incident.evidence_ids,
            } if incident else None,
            "reviews": [
                {
                    "review_id": r.review_id,
                    "reviewer_id": r.reviewer_id,
                    "decision": r.decision,
                    "notes": r.notes,
                    "reviewed_at": r.reviewed_at.isoformat(),
                }
                for r in reviews
            ],
            "evidence": evidence_list,
        }

    @staticmethod
    def review_alert(
        db: Session,
        alert_id: str,
        reviewer_id: str,
        decision: str,
        notes: str,
    ) -> Optional[dict]:
        alert = db.get(ReviewAlertRow, alert_id)
        if not alert:
            return None

        # Map decision to alert status
        status_map = {
            "ACKNOWLEDGE": AlertStatus.ACKNOWLEDGED.value,
            "DISMISS": AlertStatus.DISMISSED.value,
            "REFER": AlertStatus.REFERRED.value,
        }
        new_status = status_map.get(decision, alert.status)
        alert.status = new_status

        review_row = IncidentReviewRow(
            review_id=f"REV-{uuid.uuid4().hex[:12].upper()}",
            alert_id=alert_id,
            reviewer_id=reviewer_id,
            decision=decision,
            notes=notes,
            reviewed_at=utcnow(),
        )
        db.add(review_row)
        db.commit()
        return MonitoringService.get_alert_detail(db, alert_id)

    @staticmethod
    def list_incidents(
        db: Session,
        exam_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CandidateIncidentRow], int]:
        q = select(CandidateIncidentRow)
        if exam_id:
            q = q.where(CandidateIncidentRow.exam_id == exam_id)
        total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items = list(
            db.scalars(
                q.order_by(CandidateIncidentRow.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return items, total
