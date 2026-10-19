import hashlib
from datetime import timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.models import EvidenceRow
from app.main import create_app
from app.schemas import utcnow

from .conftest import textured


@pytest.fixture
def app_client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield app, c


def save(app, cam="CAM-ABC123", **kw):
    return app.state.evidence.save_image(cam, textured(1), [((0.1, 0.1, 0.4, 0.4), "cell phone 0.90 #1")], **kw)


def test_save_writes_file_row_and_matching_hash(app_client, settings):
    app, c = app_client
    ref = save(app)
    assert ref.status == "available" and ref.failure_reason is None
    with app.state.sessions() as db:
        row = db.get(EvidenceRow, ref.evidence_id)
    path = app.state.evidence.path_for(row)
    assert path and path.parent == (settings.evidence_dir / "CAM-ABC123").resolve() and path.stat().st_size == row.size_bytes
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row.sha256
    assert not list(path.parent.glob(".*.tmp"))  # no half-written temp files left behind


def test_api_serves_image_by_id_and_meta_has_no_path(app_client):
    app, c = app_client
    ref = save(app)
    r = c.get(f"/api/evidence/{ref.evidence_id}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"
    meta = c.get(f"/api/evidence/{ref.evidence_id}/meta").json()
    assert meta["status"] == "available" and "path" not in str(meta).lower() and "file_name" not in meta
    assert c.get("/api/evidence/EV-NOPE").status_code == 404


def test_failed_capture_is_recorded_without_a_file_reference(settings, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, so a directory cannot be created beneath me")
    bad = settings.model_copy(update={"evidence_dir": blocker / "sub"})
    app = create_app(bad)
    with TestClient(app) as c:
        ref = save(app)
        assert ref.status == "failed" and ref.failure_reason
        with app.state.sessions() as db:
            row = db.get(EvidenceRow, ref.evidence_id)
        assert row.file_name is None and row.sha256 is None  # no reference to a file that doesn't exist
        r = c.get(f"/api/evidence/{ref.evidence_id}")
        assert r.status_code == 410 and r.json()["detail"]["code"] == "EVIDENCE_UNAVAILABLE"
        assert c.get(f"/api/evidence/{ref.evidence_id}/meta").json()["failure_reason"]


def test_invalid_camera_id_cannot_choose_a_path(app_client):
    app, _ = app_client
    ref = app.state.evidence.save_image("../../etc", textured(1), [])
    assert ref.status == "failed"


def test_tampered_database_row_cannot_escape_evidence_dir(app_client, settings):
    app, c = app_client
    ref = save(app)
    secret = settings.evidence_dir.parent / "secret.jpg"
    secret.write_bytes(b"top secret")
    for bad in ["../../secret.jpg", "/etc/passwd", "EV-ABCDEF123456.jpg/../../../secret.jpg"]:
        with app.state.sessions() as db:
            row = db.get(EvidenceRow, ref.evidence_id)
            row.file_name = bad
            db.commit()
        r = c.get(f"/api/evidence/{ref.evidence_id}")
        assert r.status_code == 410 and b"top secret" not in r.content


def test_missing_file_is_reported_not_crashed(app_client, settings):
    app, c = app_client
    ref = save(app)
    for f in settings.evidence_dir.rglob("*.jpg"):
        f.unlink()
    assert c.get(f"/api/evidence/{ref.evidence_id}").json()["detail"]["code"] == "EVIDENCE_FILE_MISSING"


def test_retention_cleanup_deletes_only_expired_evidence(app_client, settings):
    app, _ = app_client
    old = save(app, captured_at=utcnow() - timedelta(days=settings.evidence_retention_days + 1))
    new = save(app, captured_at=utcnow() - timedelta(days=1))
    failed_old = app.state.evidence.save_image("bad id", textured(1), [], captured_at=utcnow() - timedelta(days=99))
    counts = app.state.evidence.cleanup()
    assert counts["rows_deleted"] == 2 and counts["files_deleted"] == 1 and counts["errors"] == 0
    with app.state.sessions() as db:
        ids = set(db.scalars(select(EvidenceRow.evidence_id)))
    assert ids == {new.evidence_id} and old.evidence_id not in ids and failed_old.evidence_id not in ids
    assert len(list(settings.evidence_dir.rglob("*.jpg"))) == 1
    assert app.state.evidence.cleanup()["rows_deleted"] == 0  # idempotent


def test_cleanup_tolerates_already_missing_files(app_client, settings):
    app, _ = app_client
    save(app, captured_at=utcnow() - timedelta(days=100))
    for f in settings.evidence_dir.rglob("*.jpg"):
        f.unlink()
    counts = app.state.evidence.cleanup()
    assert counts["rows_deleted"] == 1 and counts["files_missing"] == 1
