"""Evidence storage: annotated JPEG per confirmed detection. Privacy-minimising by design:
one image per confirmed track (no continuous recording), retention-limited, and never served by
file path: only through a database id."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database.models import EvidenceRow
from app.schemas.events import EvidenceReference, utcnow

log = logging.getLogger(__name__)
_CAM_RE = re.compile(r"^CAM-[A-Z0-9]{6}$")
_FILE_RE = re.compile(r"^EV-[A-Z0-9]{12}\.jpg$")


class EvidenceService:
    def __init__(self, sessions: sessionmaker, settings: Settings):
        self._sessions, self._s = sessions, settings

    # -------------------------------------------------------------------- write
    def save_image(self, camera_id: str, image: np.ndarray, boxes: list[tuple[tuple[float, float, float, float], str]],
                   captured_at: datetime | None = None) -> EvidenceReference | None:
        """Never raises. On failure a 'failed' record with the reason is stored (no file, no path)."""
        captured_at = captured_at or utcnow()
        evidence_id = f"EV-{uuid.uuid4().hex[:12].upper()}"
        try:
            if not _CAM_RE.match(camera_id):
                raise ValueError("invalid camera id for evidence")
            data = self._encode(image, boxes)
            folder = self._s.evidence_dir / camera_id
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{evidence_id}.jpg"
            tmp = folder / f".{name}.tmp"
            tmp.write_bytes(data)
            os.replace(tmp, folder / name)  # atomic: a half-written file is never visible under its final name
            row = EvidenceRow(evidence_id=evidence_id, camera_id=camera_id, kind="image", status="available",
                              captured_at=captured_at, file_name=name, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
        except Exception as e:
            log.warning("evidence write failed for %s: %s", camera_id, e)
            row = EvidenceRow(evidence_id=evidence_id, camera_id=camera_id, kind="image", status="failed",
                              failure_reason=f"{type(e).__name__}: {e}"[:300], captured_at=captured_at)
        try:
            with self._sessions() as db:
                db.add(row)
                db.commit()
        except Exception:
            log.exception("could not persist evidence record")
            if row.status == "available" and row.file_name:  # don't leave an unreferenced file behind
                (self._s.evidence_dir / camera_id / row.file_name).unlink(missing_ok=True)
            return None
        return self.to_ref(row)

    def _encode(self, image: np.ndarray, boxes) -> bytes:
        h, w = image.shape[:2]
        scale = min(1.0, self._s.evidence_max_width / w)
        img = cv2.resize(image, (int(w * scale), int(h * scale))) if scale < 1.0 else image.copy()
        H, W = img.shape[:2]
        for (x1, y1, x2, y2), label in boxes:
            p1, p2 = (int(x1 * W), int(y1 * H)), (int(x2 * W), int(y2 * H))
            cv2.rectangle(img, p1, p2, (0, 0, 255), 2)
            cv2.putText(img, label, (p1[0], max(14, p1[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, self._s.evidence_jpeg_quality])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buf.tobytes()

    # --------------------------------------------------------------------- read
    @staticmethod
    def to_ref(row: EvidenceRow) -> EvidenceReference:
        return EvidenceReference(evidence_id=row.evidence_id, kind=row.kind, camera_id=row.camera_id,
                                 captured_at=row.captured_at, status=row.status, failure_reason=row.failure_reason)

    def path_for(self, row: EvidenceRow) -> Path | None:
        """Safe path or None. Names are re-validated against strict patterns and the resolved path must stay inside evidence_dir."""
        if row.status != "available" or not row.file_name or not _FILE_RE.match(row.file_name) or not _CAM_RE.match(row.camera_id):
            return None
        base = self._s.evidence_dir.resolve()
        p = (base / row.camera_id / row.file_name).resolve()
        return p if base in p.parents and p.is_file() else None

    # ---------------------------------------------------------------- retention
    def cleanup(self, now: datetime | None = None) -> dict:
        """Delete evidence older than the retention period (files first, then rows). Safe to re-run."""
        now = now or utcnow()
        cutoff = now - timedelta(days=self._s.evidence_retention_days)
        counts = {"rows_deleted": 0, "files_deleted": 0, "files_missing": 0, "errors": 0}
        with self._sessions() as db:
            for row in db.scalars(select(EvidenceRow).where(EvidenceRow.captured_at < cutoff)).all():
                try:
                    if row.status == "available" and row.file_name and _FILE_RE.match(row.file_name) and _CAM_RE.match(row.camera_id):
                        f = self._s.evidence_dir / row.camera_id / row.file_name
                        if f.exists():
                            f.unlink()
                            counts["files_deleted"] += 1
                        else:
                            counts["files_missing"] += 1
                    db.delete(row)
                    counts["rows_deleted"] += 1
                except OSError:
                    counts["errors"] += 1  # keep the row so a later run retries
            db.commit()
        return counts
