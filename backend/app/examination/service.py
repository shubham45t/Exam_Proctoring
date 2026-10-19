"""Examination session management & audit report compilation service."""
from __future__ import annotations

import uuid
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import (
    CandidateIncidentRow,
    CameraRow,
    ExamRow,
    IncidentReviewRow,
    ReviewAlertRow,
    RoomRow,
    SeatRow,
)
from app.schemas.events import utcnow


class ExamService:
    @staticmethod
    def create_exam(
        db: Session,
        title: str,
        course_code: Optional[str] = None,
        room_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ExamRow:
        exam = ExamRow(
            exam_id=f"EXAM-{uuid.uuid4().hex[:8].upper()}",
            title=title.strip(),
            course_code=course_code.strip() if course_code else None,
            room_id=room_id,
            status="SCHEDULED",
            notes=notes,
            created_at=utcnow(),
        )
        db.add(exam)
        db.commit()
        db.refresh(exam)
        return exam

    @staticmethod
    def list_exams(db: Session, status: Optional[str] = None) -> list[dict]:
        q = select(ExamRow)
        if status:
            q = q.where(ExamRow.status == status)
        exams = db.scalars(q.order_by(ExamRow.created_at.desc())).all()
        results = []
        for e in exams:
            room_name = None
            if e.room_id:
                rm = db.get(RoomRow, e.room_id)
                if rm:
                    room_name = rm.name
            # Count alerts
            alert_count = db.scalar(
                select(func.count()).select_from(ReviewAlertRow).where(ReviewAlertRow.exam_id == e.exam_id)
            ) or 0
            results.append({
                "exam_id": e.exam_id,
                "title": e.title,
                "course_code": e.course_code,
                "room_id": e.room_id,
                "room_name": room_name,
                "start_time": e.start_time.isoformat() if e.start_time else None,
                "end_time": e.end_time.isoformat() if e.end_time else None,
                "status": e.status,
                "notes": e.notes,
                "alert_count": alert_count,
                "created_at": e.created_at.isoformat(),
            })
        return results

    @staticmethod
    def get_exam(db: Session, exam_id: str) -> Optional[dict]:
        e = db.get(ExamRow, exam_id)
        if not e:
            return None
        room = db.get(RoomRow, e.room_id) if e.room_id else None
        cameras = []
        if e.room_id:
            cams = db.scalars(select(CameraRow).where(CameraRow.room_id == e.room_id)).all()
            cameras = [{"camera_id": c.camera_id, "name": c.name} for c in cams]

        alerts = db.scalars(
            select(ReviewAlertRow).where(ReviewAlertRow.exam_id == exam_id).order_by(ReviewAlertRow.created_at.desc())
        ).all()

        return {
            "exam_id": e.exam_id,
            "title": e.title,
            "course_code": e.course_code,
            "room_id": e.room_id,
            "room_name": room.name if room else None,
            "cameras": cameras,
            "start_time": e.start_time.isoformat() if e.start_time else None,
            "end_time": e.end_time.isoformat() if e.end_time else None,
            "status": e.status,
            "notes": e.notes,
            "alerts": [
                {
                    "alert_id": a.alert_id,
                    "title": a.title,
                    "priority": a.priority,
                    "status": a.status,
                    "created_at": a.created_at.isoformat(),
                }
                for a in alerts
            ],
            "created_at": e.created_at.isoformat(),
        }

    @staticmethod
    def start_exam(db: Session, exam_id: str) -> Optional[ExamRow]:
        exam = db.get(ExamRow, exam_id)
        if not exam:
            return None
        exam.status = "IN_PROGRESS"
        exam.start_time = utcnow()
        db.commit()
        return exam

    @staticmethod
    def end_exam(db: Session, exam_id: str) -> Optional[ExamRow]:
        exam = db.get(ExamRow, exam_id)
        if not exam:
            return None
        exam.status = "COMPLETED"
        exam.end_time = utcnow()
        db.commit()
        return exam

    @staticmethod
    def generate_report(db: Session, exam_id: str) -> Optional[dict]:
        exam = db.get(ExamRow, exam_id)
        if not exam:
            return None

        room = db.get(RoomRow, exam.room_id) if exam.room_id else None
        total_seats = 0
        if exam.room_id:
            total_seats = db.scalar(
                select(func.count()).select_from(SeatRow).where(SeatRow.room_id == exam.room_id)
            ) or 0

        # Incidents & alerts
        alerts = list(
            db.scalars(
                select(ReviewAlertRow)
                .where(ReviewAlertRow.exam_id == exam_id)
                .order_by(ReviewAlertRow.created_at.asc())
            ).all()
        )

        incidents = list(
            db.scalars(
                select(CandidateIncidentRow)
                .where(CandidateIncidentRow.exam_id == exam_id)
                .order_by(CandidateIncidentRow.created_at.asc())
            ).all()
        )

        # Reviews
        reviews = []
        alert_ids = [a.alert_id for a in alerts]
        if alert_ids:
            reviews = list(
                db.scalars(
                    select(IncidentReviewRow).where(IncidentReviewRow.alert_id.in_(alert_ids))
                ).all()
            )

        # Breakdown calculations
        priority_breakdown = {"high": 0, "medium": 0, "low": 0}
        status_breakdown = {"NEW": 0, "ACKNOWLEDGED": 0, "DISMISSED": 0, "REFERRED": 0}
        decision_breakdown = {"ACKNOWLEDGE": 0, "DISMISS": 0, "REFER": 0}

        for a in alerts:
            p = a.priority.lower()
            if p in priority_breakdown:
                priority_breakdown[p] += 1
            if a.status in status_breakdown:
                status_breakdown[a.status] += 1

        for r in reviews:
            if r.decision in decision_breakdown:
                decision_breakdown[r.decision] += 1

        timeline = []
        for inc in incidents:
            linked_alert = next((a for a in alerts if a.incident_id == inc.incident_id), None)
            linked_review = next((r for r in reviews if linked_alert and r.alert_id == linked_alert.alert_id), None)
            timeline.append({
                "incident_id": inc.incident_id,
                "timestamp": inc.created_at.isoformat(),
                "category": inc.category,
                "seat_id": inc.seat_id,
                "priority": inc.priority,
                "score": inc.review_priority_score,
                "explanation": inc.explanation,
                "limitations": inc.limitations,
                "evidence_ids": inc.evidence_ids,
                "status": linked_alert.status if linked_alert else "NEW",
                "review": {
                    "reviewer_id": linked_review.reviewer_id,
                    "decision": linked_review.decision,
                    "notes": linked_review.notes,
                    "reviewed_at": linked_review.reviewed_at.isoformat(),
                } if linked_review else None,
            })

        duration_minutes = None
        if exam.start_time and exam.end_time:
            duration_minutes = round((exam.end_time - exam.start_time).total_seconds() / 60.0, 1)

        return {
            "exam_id": exam.exam_id,
            "title": exam.title,
            "course_code": exam.course_code,
            "room_name": room.name if room else "Unassigned Room",
            "total_seats": total_seats,
            "status": exam.status,
            "start_time": exam.start_time.isoformat() if exam.start_time else None,
            "end_time": exam.end_time.isoformat() if exam.end_time else None,
            "duration_minutes": duration_minutes,
            "notes": exam.notes,
            "metrics": {
                "total_alerts": len(alerts),
                "total_incidents": len(incidents),
                "priority_breakdown": priority_breakdown,
                "status_breakdown": status_breakdown,
                "decision_breakdown": decision_breakdown,
                "reviews_completed": len(reviews),
            },
            "timeline": timeline,
            "compliance_notice": (
                "OmniProctor is an algorithmic assistance framework intended to assist certified educational proctors. "
                "Recorded candidate incidents are review recommendations based on computer vision heuristics and "
                "do not constitute final disciplinary findings without independent human proctor corroboration."
            ),
        }
