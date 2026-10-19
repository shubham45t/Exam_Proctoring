from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db
from app.monitoring.service import MonitoringService

router = APIRouter(prefix="/api", tags=["alerts"])


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(ACKNOWLEDGE|DISMISS|REFER)$")
    notes: str = Field(default="", max_length=4000)


@router.get("/alerts")
def list_alerts(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    exam_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = MonitoringService.list_alerts(db, status=status, priority=priority, exam_id=exam_id, limit=limit, offset=offset)
    return {
        "items": [
            {
                "alert_id": a.alert_id,
                "incident_id": a.incident_id,
                "exam_id": a.exam_id,
                "title": a.title,
                "summary": a.summary,
                "priority": a.priority,
                "status": a.status,
                "created_at": a.created_at.isoformat(),
                "notice": a.notice,
                "is_synthetic": a.is_synthetic,
            }
            for a in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    detail = MonitoringService.get_alert_detail(db, alert_id)
    if not detail:
        raise HTTPException(404, detail={"code": "ALERT_NOT_FOUND", "message": "Alert not found."})
    return detail


@router.post("/alerts/{alert_id}/review")
def review_alert(
    alert_id: str,
    body: ReviewRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    detail = MonitoringService.review_alert(
        db,
        alert_id=alert_id,
        reviewer_id=current.username,
        decision=body.decision,
        notes=body.notes,
    )
    if not detail:
        raise HTTPException(404, detail={"code": "ALERT_NOT_FOUND", "message": "Alert not found."})

    # Broadcast review update over WebSocket
    request.app.state.events.publish_message({
        "type": "alert_reviewed",
        "data": {
            "alert_id": alert_id,
            "decision": body.decision,
            "status": detail["alert"]["status"],
            "reviewer_id": current.username,
        },
    })
    request.app.state.events.audit(db, current.username, "alert.review", "alert", alert_id, {"decision": body.decision})
    return detail


@router.get("/incidents")
def list_incidents(
    exam_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = MonitoringService.list_incidents(db, exam_id=exam_id, limit=limit, offset=offset)
    return {
        "items": [
            {
                "incident_id": inc.incident_id,
                "exam_id": inc.exam_id,
                "category": inc.category,
                "camera_id": inc.camera_id,
                "seat_id": inc.seat_id,
                "first_seen": inc.first_seen.isoformat(),
                "last_seen": inc.last_seen.isoformat(),
                "priority": inc.priority,
                "review_priority_score": inc.review_priority_score,
                "explanation": inc.explanation,
                "limitations": inc.limitations,
                "rules_triggered": inc.rules_triggered,
                "observation_ids": inc.observation_ids,
                "evidence_ids": inc.evidence_ids,
                "created_at": inc.created_at.isoformat(),
                "is_synthetic": inc.is_synthetic,
            }
            for inc in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
