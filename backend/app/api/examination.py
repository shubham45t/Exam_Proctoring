from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db
from app.examination.service import ExamService

router = APIRouter(prefix="/api/exams", tags=["examination"])


class ExamCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    course_code: Optional[str] = Field(default=None, max_length=50)
    room_id: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
def list_exams(status: Optional[str] = None, db: Session = Depends(get_db)):
    return ExamService.list_exams(db, status=status)


@router.post("", status_code=201)
def create_exam(
    body: ExamCreate,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = ExamService.create_exam(
        db,
        title=body.title,
        course_code=body.course_code,
        room_id=body.room_id,
        notes=body.notes,
    )
    request.app.state.events.audit(db, current.username, "exam.create", "exam", exam.exam_id, {"title": exam.title})
    return ExamService.get_exam(db, exam.exam_id)


@router.get("/{exam_id}")
def get_exam(exam_id: str, db: Session = Depends(get_db)):
    res = ExamService.get_exam(db, exam_id)
    if not res:
        raise HTTPException(404, detail={"code": "EXAM_NOT_FOUND", "message": "Examination not found."})
    return res


@router.post("/{exam_id}/start")
def start_exam(
    exam_id: str,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = ExamService.start_exam(db, exam_id)
    if not exam:
        raise HTTPException(404, detail={"code": "EXAM_NOT_FOUND", "message": "Examination not found."})
    
    request.app.state.events.publish_message({
        "type": "exam_started",
        "data": {"exam_id": exam_id, "title": exam.title, "start_time": exam.start_time.isoformat()},
    })
    request.app.state.events.audit(db, current.username, "exam.start", "exam", exam_id)
    return ExamService.get_exam(db, exam_id)


@router.post("/{exam_id}/end")
def end_exam(
    exam_id: str,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = ExamService.end_exam(db, exam_id)
    if not exam:
        raise HTTPException(404, detail={"code": "EXAM_NOT_FOUND", "message": "Examination not found."})
    
    request.app.state.events.publish_message({
        "type": "exam_ended",
        "data": {"exam_id": exam_id, "title": exam.title, "end_time": exam.end_time.isoformat()},
    })
    request.app.state.events.audit(db, current.username, "exam.end", "exam", exam_id)
    return ExamService.get_exam(db, exam_id)
