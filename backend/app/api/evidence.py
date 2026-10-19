from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.models import EvidenceRow

from .deps import get_db

router = APIRouter(prefix="/api", tags=["evidence"])
_NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def _row(db: Session, evidence_id: str) -> EvidenceRow:
    row = db.get(EvidenceRow, evidence_id)
    if not row:
        raise HTTPException(404, detail={"code": "EVIDENCE_NOT_FOUND", "message": "Evidence not found."})
    return row


@router.get("/evidence/{evidence_id}/meta")
def evidence_meta(evidence_id: str, request: Request, db: Session = Depends(get_db)):
    """Metadata only: never includes a filesystem path."""
    row = _row(db, evidence_id)
    ref = request.app.state.evidence.to_ref(row).model_dump(mode="json")
    ref.update(size_bytes=row.size_bytes, sha256=row.sha256)
    return ref


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str, request: Request, db: Session = Depends(get_db)):
    """Serves the image by database id. TODO(Phase 8): require an authorised reviewer role."""
    row = _row(db, evidence_id)
    if row.status == "failed":
        raise HTTPException(410, detail={"code": "EVIDENCE_UNAVAILABLE", "message": f"Evidence capture failed: {row.failure_reason}"})
    path = request.app.state.evidence.path_for(row)
    if path is None:
        raise HTTPException(410, detail={"code": "EVIDENCE_FILE_MISSING", "message": "The evidence file is no longer available (deleted by retention policy or storage problem)."})
    return FileResponse(path, media_type="image/jpeg", headers=_NO_STORE)
