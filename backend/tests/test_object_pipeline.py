"""Camera -> detector (STUB) -> tracker -> dedup -> evidence -> DB -> WebSocket. The stub proves the
plumbing only; real model quality is measured separately (scripts/evaluate_detector.py)."""
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import SEAT_A, SEAT_B, ColorBlobDetector, wait_for, write_scene

PHONE_IN_SEAT_A = (0.15, 0.4, 0.25, 0.52)


@pytest.fixture
def cfg(settings):
    s = settings.model_copy(update={"detector": "yolox_onnx", "detect_fps": 30, "track_confirm_hits": 3,
                                    "track_confirm_min_s": 0.3, "track_max_age_s": 0.6})
    write_scene(s.media_dir / "phone.avi", None, phone=PHONE_IN_SEAT_A)
    write_scene(s.media_dir / "empty.avi", None)
    return s


def boot(cfg, det):
    return TestClient(create_app(cfg, detector=det))


def mk(c, uri="phone.avi", name="cam", **kw):
    r = c.post("/api/cameras", json={"name": name, "source_type": "VIDEO_FILE", "source_uri": uri, **kw})
    assert r.status_code == 201, r.text
    return r.json()["camera_id"]


def events(c, **p):
    return c.get("/api/events", params={"limit": 500, **p}).json()["items"]


def stats(c, cid):
    rt = c.get(f"/api/cameras/{cid}").json()["runtime"] or {}
    return next((a for a in rt.get("analyzers", []) if a["name"] == "object_detection"), None)


def object_threads(cid):
    return [t for t in threading.enumerate() if t.name == f"object_detection-{cid}" and t.is_alive()]


def test_continuous_phone_is_one_observation_with_evidence_and_seat(cfg):
    det = ColorBlobDetector()
    with boot(cfg, det) as c:
        rid = c.post("/api/rooms", json={"name": "H", "width_m": 5, "depth_m": 5, "generate": {"rows": 1, "cols": 2}}).json()["room_id"]
        cid = mk(c)
        c.put(f"/api/cameras/{cid}/seat-regions", json={"room_id": rid, "regions": [
            {"seat_id": "R1-C1", "polygon": SEAT_A}, {"seat_id": "R1-C2", "polygon": SEAT_B}]})
        with c.websocket_connect("/ws") as ws:
            ws.receive_json()
            assert c.post(f"/api/cameras/{cid}/start").status_code == 200
            got = None
            for _ in range(80):
                m = ws.receive_json()
                if m["type"] == "event" and m["data"]["event_type"] == "object_detection":
                    got = m["data"]; break
        assert got, "no object_detection observation arrived"
        assert got["object_class"] == "cell phone" and got["tracker_id"] == 1 and got["seat_id"] == "R1-C1"
        assert got["model_id"] == "test-stub-colorblob" and got["is_synthetic"] is False and got["evidence_id"]
        assert wait_for(lambda: det.calls >= 25, timeout=10), f"only {det.calls} frames inferred"  # ~25+ frames of a visible phone
        obs = events(c, event_type="object_detection")
        assert len(obs) == 1, f"deduplication failed: {len(obs)} observations for one continuously visible phone"
        assert len([e for e in events(c, event_type="tracking") if e["payload"]["track_state"] == "new"]) == 1
        r = c.get(f"/api/evidence/{got['evidence_id']}")
        assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"
        live = c.get(f"/api/cameras/{cid}/detections").json()
        assert live["running"] and live["tracks"][0]["confirmed"] and live["tracks"][0]["tracker_id"] == 1
        b = live["tracks"][0]["bbox"]
        assert abs(b["x1"] - 0.15) < 0.03 and abs(b["y2"] - 0.52) < 0.03  # box really tracks the painted phone
        c.post(f"/api/cameras/{cid}/stop")
        states = [e["payload"]["track_state"] for e in events(c, event_type="tracking")]
        assert "expired" in states  # stopping the camera ends the track: nothing is "still there"
        assert not object_threads(cid)


def test_no_phone_no_events(cfg):
    with boot(cfg, ColorBlobDetector()) as c:
        cid = mk(c, "empty.avi")
        c.post(f"/api/cameras/{cid}/start")
        assert wait_for(lambda: (stats(c, cid) or {}).get("processed", 0) >= 5)
        assert events(c, event_type="object_detection") == [] and events(c, event_type="tracking") == []
        c.post(f"/api/cameras/{cid}/stop")


def test_weak_detections_never_create_an_incident(cfg):
    with boot(cfg, ColorBlobDetector(conf=0.35)) as c:  # below track_high_conf (0.45)
        cid = mk(c)
        c.post(f"/api/cameras/{cid}/start")
        assert wait_for(lambda: (stats(c, cid) or {}).get("detections_total", 0) >= 10)
        assert events(c, event_type="object_detection") == []
        c.post(f"/api/cameras/{cid}/stop")


def test_slow_detector_drops_frames_but_never_hurts_camera_health(cfg):
    det = ColorBlobDetector(delay_s=0.4)  # far slower than the frame rate
    with boot(cfg, det) as c:
        cid = mk(c)
        c.post(f"/api/cameras/{cid}/start")
        assert wait_for(lambda: (stats(c, cid) or {}).get("dropped", 0) >= 5 and (stats(c, cid) or {}).get("processed", 0) >= 1, timeout=12), stats(c, cid)
        st = stats(c, cid)
        assert st["processed"] >= 1 and st["infer_ms_median"] >= 300  # latency is measured and reported
        assert c.get(f"/api/cameras/{cid}").json()["runtime"]["state"] == "CONNECTED"  # health analysis never blocked
        c.post(f"/api/cameras/{cid}/stop")


def test_detector_exceptions_are_contained(cfg):
    det = ColorBlobDetector(fail=True)
    with boot(cfg, det) as c:
        cid = mk(c)
        c.post(f"/api/cameras/{cid}/start")
        assert wait_for(lambda: (stats(c, cid) or {}).get("errors", 0) >= 3)
        assert c.get(f"/api/cameras/{cid}").json()["runtime"]["state"] == "CONNECTED"
        assert c.get("/api/health").status_code == 200
        c.post(f"/api/cameras/{cid}/stop")


def test_disabled_detector_does_not_block_cameras_and_says_why(cfg):
    off = cfg.model_copy(update={"detector": "none"})
    with TestClient(create_app(off)) as c:
        cid = mk(c)
        assert c.post(f"/api/cameras/{cid}/start").status_code == 200
        assert stats(c, cid) is None
        d = c.get("/api/system/status").json()["detector"]
        assert d["enabled"] is False and "disabled" in d["reason"]
        c.post(f"/api/cameras/{cid}/stop")


def test_missing_model_file_degrades_gracefully(cfg, tmp_path):
    s = cfg.model_copy(update={"detector_model_path": tmp_path / "nope.onnx"})
    with TestClient(create_app(s)) as c:
        cid = mk(c)
        assert c.post(f"/api/cameras/{cid}/start").status_code == 200
        d = c.get("/api/system/status").json()["detector"]
        assert d["enabled"] is False and "download_model.py" in d["reason"]
        c.post(f"/api/cameras/{cid}/stop")


def test_per_camera_toggle_and_edit(cfg):
    with boot(cfg, ColorBlobDetector()) as c:
        cid = mk(c, object_detection=False)
        assert c.get(f"/api/cameras/{cid}").json()["object_detection"] is False
        c.post(f"/api/cameras/{cid}/start")
        assert stats(c, cid) is None  # opted out: no analyzer
        c.post(f"/api/cameras/{cid}/stop")
        assert c.patch(f"/api/cameras/{cid}", json={"object_detection": True, "name": "renamed"}).json()["object_detection"] is True
        c.post(f"/api/cameras/{cid}/start")
        assert wait_for(lambda: stats(c, cid) is not None)
        c.post(f"/api/cameras/{cid}/stop")


def test_hot_reload_does_not_leak_analyzer_threads(cfg):
    with boot(cfg, ColorBlobDetector()) as c:
        rid = c.post("/api/rooms", json={"name": "H", "width_m": 5, "depth_m": 5, "generate": {"rows": 1, "cols": 2}}).json()["room_id"]
        cid = mk(c)
        c.post(f"/api/cameras/{cid}/start")
        for _ in range(4):  # every calibration save rebuilds analyzers
            c.put(f"/api/cameras/{cid}/seat-regions", json={"room_id": rid, "regions": [{"seat_id": "R1-C1", "polygon": SEAT_A}]})
        assert wait_for(lambda: len(object_threads(cid)) == 1), len(object_threads(cid))
        c.post(f"/api/cameras/{cid}/stop")
        assert wait_for(lambda: not object_threads(cid))


def test_migration_0002_to_0003_preserves_cameras(tmp_path):
    import sqlalchemy as sa
    from app.database.migrate import run_migrations
    url = f"sqlite:///{tmp_path/'m.db'}"
    run_migrations(url, "0002")
    e = sa.create_engine(url)
    with e.begin() as cx:
        cx.execute(sa.text("INSERT INTO cameras (camera_id,name,source_type,source_uri,created_at,updated_at) VALUES ('CAM-OLD002','o','WEBCAM','0','2026-01-01','2026-01-01')"))
    run_migrations(url)
    with e.connect() as cx:
        assert tuple(cx.execute(sa.text("SELECT camera_id, object_detection FROM cameras")).one()) == ("CAM-OLD002", 1)  # defaults to ON
    assert "evidence" in sa.inspect(e).get_table_names()
