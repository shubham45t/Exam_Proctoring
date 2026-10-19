"""Vertical slice: camera -> worker -> persistence -> WebSocket -> (dashboard consumes the same stream)."""
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import wait_for


def test_migrations_create_expected_tables(client):
    names = sa.inspect(client.app.state.engine).get_table_names()
    assert {"cameras", "events", "audit_logs", "alembic_version"} <= set(names)


def test_real_camera_status_flows_to_websocket_and_database(client, video):
    cid = client.post("/api/cameras", json={"name": "v", "source_type": "VIDEO_FILE", "source_uri": video}).json()["camera_id"]
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        client.post(f"/api/cameras/{cid}/start")
        seen = []
        for _ in range(10):
            m = ws.receive_json()
            seen.append(m)
            if m["type"] == "camera_status" and m["data"]["state"] == "CONNECTED":
                break
        last = seen[-1]
        assert last["data"]["state"] == "CONNECTED" and last["data"]["camera_id"] == cid
        assert last["data"]["is_synthetic"] is False
        client.post(f"/api/cameras/{cid}/stop")
    rows = client.get("/api/events", params={"event_type": "camera_status", "camera_id": cid}).json()
    assert {"CONNECTED", "STOPPED"} <= {r["payload"]["state"] for r in rows["items"]}


def test_synthetic_event_is_labelled_and_reaches_websocket(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        e = client.post("/api/events/synthetic", json={}).json()
        m = ws.receive_json()
    assert m["type"] == "event" and m["data"]["event_id"] == e["event_id"]
    assert m["data"]["is_synthetic"] is True and m["data"]["object_class"] == "DEMO_DATA"
    assert m["data"]["model_id"] == "synthetic-generator"


def test_records_survive_application_restart(settings, video):
    with TestClient(create_app(settings)) as c1:
        cid = c1.post("/api/cameras", json={"name": "persist", "source_type": "VIDEO_FILE", "source_uri": video}).json()["camera_id"]
        ev = c1.post("/api/events/synthetic", json={}).json()["event_id"]
    with TestClient(create_app(settings)) as c2:  # new process-equivalent, same database file
        assert c2.get(f"/api/cameras/{cid}").status_code == 200
        assert c2.get(f"/api/events/{ev}").status_code == 200


def test_shutdown_stops_running_cameras(settings, video):
    app = create_app(settings)
    with TestClient(app) as c:
        cid = c.post("/api/cameras", json={"name": "s", "source_type": "VIDEO_FILE", "source_uri": video}).json()["camera_id"]
        c.post(f"/api/cameras/{cid}/start")
        mgr = app.state.cameras
        assert mgr.is_running(cid)
    assert mgr.running_ids() == []


def test_phone_style_mjpeg_end_to_end(client, mjpeg_server):
    url = f"http://127.0.0.1:{mjpeg_server.port}/video"
    cid = client.post("/api/cameras", json={"name": "phone", "source_type": "HTTP_MJPEG", "source_uri": url}).json()["camera_id"]
    assert client.post(f"/api/cameras/{cid}/test").json()["ok"]
    assert client.post(f"/api/cameras/{cid}/start").status_code == 200
    assert wait_for(lambda: (client.get(f"/api/cameras/{cid}").json()["runtime"] or {}).get("state") == "CONNECTED", timeout=10)
    assert client.get(f"/api/cameras/{cid}/snapshot").status_code == 200
    mjpeg_server.stopped = True  # phone app killed / Wi-Fi lost
    assert wait_for(lambda: (client.get(f"/api/cameras/{cid}").json()["runtime"] or {}).get("state") in {"STALE", "RECONNECTING", "FAILED"}, timeout=15)
    client.post(f"/api/cameras/{cid}/stop")
