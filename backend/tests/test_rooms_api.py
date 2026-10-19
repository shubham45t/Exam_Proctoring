import cv2
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.database.migrate import run_migrations
from app.main import create_app
from app.perception.wiring import baseline_path

from .conftest import SEAT_A, SEAT_B, wait_for, write_scene


def mkroom(c, name="Hall A", rows=1, cols=2):
    r = c.post("/api/rooms", json={"name": name, "width_m": 10, "depth_m": 8, "generate": {"rows": rows, "cols": cols}})
    assert r.status_code == 201, r.text
    return r.json()


def mkcam(c, uri, name="cam"):
    return c.post("/api/cameras", json={"name": name, "source_type": "VIDEO_FILE", "source_uri": uri}).json()["camera_id"]


def regions(c, cid, room_id, a="monitored", b="monitored"):
    return c.put(f"/api/cameras/{cid}/seat-regions", json={"room_id": room_id, "regions": [
        {"seat_id": "R1-C1", "polygon": SEAT_A, "visibility": a}, {"seat_id": "R1-C2", "polygon": SEAT_B, "visibility": b}]})


@pytest.fixture
def scenes(settings):
    write_scene(settings.media_dir / "empty.avi", None)
    write_scene(settings.media_dir / "occupied_a.avi", SEAT_A)
    return settings


# ---------------------------------------------------------------- rooms & seats
def test_create_room_generates_seats_and_roundtrips(client):
    room = mkroom(client, rows=2, cols=3)
    assert room["seat_count"] == 6 and {s["seat_id"] for s in room["seats"]} >= {"R1-C1", "R2-C3"}
    got = client.get(f"/api/rooms/{room['room_id']}").json()
    assert got["name"] == "Hall A" and len(got["seats"]) == 6
    assert client.get("/api/rooms").json()[0]["seat_count"] == 6
    assert client.put(f"/api/rooms/{room['room_id']}", json={"name": "Hall B", "width_m": 12}).json()["name"] == "Hall B"


def test_room_validation_and_conflicts(client):
    mkroom(client)
    assert client.post("/api/rooms", json={"name": "Hall A", "width_m": 5, "depth_m": 5}).status_code == 409
    assert client.post("/api/rooms", json={"name": "x", "width_m": -1, "depth_m": 5}).status_code == 422
    assert client.post("/api/rooms", json={"name": "y", "width_m": 5, "depth_m": 5, "generate": {"rows": 99, "cols": 1}}).status_code == 422
    assert client.get("/api/rooms/ROOM-NOPE").status_code == 404


def test_put_seats_validates_and_replaces(client):
    rid = mkroom(client)["room_id"]
    s = lambda i, **k: {"seat_id": i, "row": 1, "col": 1, "x": 0.5, "y": 0.5, **k}
    assert client.put(f"/api/rooms/{rid}/seats", json=[s("A1"), s("A1")]).json()["detail"]["code"] == "DUPLICATE_SEAT_ID"
    assert client.put(f"/api/rooms/{rid}/seats", json=[s("../bad")]).json()["detail"]["code"] == "INVALID_SEAT_ID"
    assert client.put(f"/api/rooms/{rid}/seats", json=[s("A1", x=1.5)]).status_code == 422
    out = client.put(f"/api/rooms/{rid}/seats", json=[s("A1"), s("A2", col=2, monitored=False)]).json()
    assert [x["seat_id"] for x in out] == ["A1", "A2"] and out[1]["monitored"] is False


def test_removing_a_seat_removes_its_camera_region(scenes, client):
    room = mkroom(client)
    cid = mkcam(client, "empty.avi")
    assert regions(client, cid, room["room_id"]).status_code == 200
    seats = [s for s in room["seats"] if s["seat_id"] != "R1-C2"]
    client.put(f"/api/rooms/{room['room_id']}/seats", json=seats)
    assert [r["seat_id"] for r in client.get(f"/api/cameras/{cid}/seat-regions").json()["regions"]] == ["R1-C1"]


# ------------------------------------------------------------------ calibration validation
@pytest.mark.parametrize("payload,code", [
    ({"regions": [{"seat_id": "NOPE", "polygon": SEAT_A}]}, "UNKNOWN_SEAT"),
    ({"regions": [{"seat_id": "R1-C1", "polygon": [[0, 0], [1, 1]]}]}, "INVALID_POLYGON"),
    ({"regions": [{"seat_id": "R1-C1", "polygon": [[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]]}]}, "INVALID_POLYGON"),
    ({"regions": [{"seat_id": "R1-C1", "polygon": SEAT_A, "visibility": "great"}]}, "INVALID_VISIBILITY"),
    ({"regions": [{"seat_id": "R1-C1", "polygon": SEAT_A}, {"seat_id": "R1-C1", "polygon": SEAT_B}]}, "DUPLICATE_SEAT_REGION"),
])
def test_region_validation(scenes, client, payload, code):
    room = mkroom(client)
    cid = mkcam(client, "empty.avi")
    r = client.put(f"/api/cameras/{cid}/seat-regions", json={"room_id": room["room_id"], **payload})
    assert r.status_code == 422 and r.json()["detail"]["code"] == code


def test_region_requires_existing_room_and_camera(scenes, client):
    cid = mkcam(client, "empty.avi")
    assert client.put(f"/api/cameras/{cid}/seat-regions", json={"room_id": "ROOM-NOPE", "regions": []}).status_code == 404
    assert client.put(f"/api/cameras/{cid}/seat-regions", json={"regions": [{"seat_id": "R1-C1", "polygon": SEAT_A}]}).json()["detail"]["code"] == "ROOM_REQUIRED"
    assert client.get("/api/cameras/CAM-NOPE00/seat-regions").status_code == 404


def test_baseline_needs_running_camera_and_path_is_safe(scenes, client):
    cid = mkcam(client, "empty.avi")
    assert client.post(f"/api/cameras/{cid}/baseline").json()["detail"]["code"] == "CAMERA_NOT_READY"
    assert client.get(f"/api/cameras/{cid}/baseline").status_code == 404
    with pytest.raises(ValueError):
        baseline_path(scenes, "../../etc/passwd")


# ------------------------------------------------------------------- occupancy summaries
def test_unmonitored_and_occluded_and_summary_adds_up(scenes, client):
    room = mkroom(client, rows=1, cols=3)
    occ = client.get(f"/api/rooms/{room['room_id']}/occupancy").json()
    assert occ["summary"]["unmonitored"] == 3 and occ["summary"]["total"] == 3  # nothing mapped yet
    cid = mkcam(client, "empty.avi")
    client.put(f"/api/cameras/{cid}/seat-regions", json={"room_id": room["room_id"], "regions": [
        {"seat_id": "R1-C1", "polygon": SEAT_A, "visibility": "not_visible"}, {"seat_id": "R1-C2", "polygon": SEAT_B}]})
    occ = client.get(f"/api/rooms/{room['room_id']}/occupancy").json()
    st = {s["seat_id"]: s["state"] for s in occ["seats"]}
    assert st == {"R1-C1": "OCCLUDED", "R1-C2": "UNCERTAIN", "R1-C3": "UNMONITORED"}  # C2 mapped but camera not running
    assert sum(v for k, v in occ["summary"].items() if k != "total") == occ["summary"]["total"]


def test_two_cameras_one_seat_is_counted_once(scenes, client):
    room = mkroom(client)
    c1, c2 = mkcam(client, "empty.avi", "cam1"), mkcam(client, "empty.avi", "cam2")
    for c in (c1, c2):
        regions(client, c, room["room_id"])
    occ = client.get(f"/api/rooms/{room['room_id']}/occupancy").json()
    seat = next(s for s in occ["seats"] if s["seat_id"] == "R1-C1")
    assert occ["summary"]["total"] == 2 and len(seat["cameras"]) == 2  # two supporting views, still one seat


# ---------------------------------------------------------------------------- full pipeline
def test_end_to_end_baseline_then_person_in_seat(scenes, client):
    """empty-room baseline -> camera sees a person in seat A -> fused occupancy, event, WebSocket; then camera stops."""
    room = mkroom(client)
    rid = room["room_id"]
    cid = mkcam(client, "empty.avi")
    assert regions(client, cid, rid).status_code == 200
    assert client.post(f"/api/cameras/{cid}/start").status_code == 200
    assert wait_for(lambda: client.get(f"/api/cameras/{cid}").json()["runtime"]["state"] == "CONNECTED")
    assert client.post(f"/api/cameras/{cid}/baseline").status_code == 200  # hot-reloads the running analyzer
    assert client.get(f"/api/cameras/{cid}/baseline").headers["content-type"] == "image/png"
    assert wait_for(lambda: {s["state"] for s in client.get(f"/api/rooms/{rid}/occupancy").json()["seats"]} == {"VACANT"}), \
        client.get(f"/api/rooms/{rid}/occupancy").json()["seats"]
    client.post(f"/api/cameras/{cid}/stop")

    client.patch(f"/api/cameras/{cid}", json={"source_uri": "occupied_a.avi"})  # same camera now "sees" a person in seat A
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        assert client.post(f"/api/cameras/{cid}/start").status_code == 200  # baseline persisted across stop/start
        got = None
        for _ in range(60):
            m = ws.receive_json()
            if m["type"] == "event" and m["data"]["event_type"] == "occupancy" and m["data"]["state"] == "OCCUPIED":
                got = m["data"]; break
        assert got and got["seat_id"] == "R1-C1" and got["is_synthetic"] is False and got["method"].startswith("baseline-diff")

    def seats():
        return {s["seat_id"]: s["state"] for s in client.get(f"/api/rooms/{rid}/occupancy").json()["seats"]}
    assert wait_for(lambda: seats() == {"R1-C1": "OCCUPIED", "R1-C2": "VACANT"}), seats()
    assert client.get("/api/events", params={"seat_id": "R1-C1", "event_type": "occupancy"}).json()["total"] >= 1

    client.post(f"/api/cameras/{cid}/stop")
    after = client.get(f"/api/rooms/{rid}/occupancy").json()
    assert {s["state"] for s in after["seats"]} == {"UNCERTAIN"}  # stopped camera: last state is NOT shown as current
    assert after["summary"]["occupied"] == 0


def test_calibration_survives_restart(scenes):
    from fastapi.testclient import TestClient
    with TestClient(create_app(scenes)) as c1:
        room = mkroom(c1)
        cid = mkcam(c1, "empty.avi")
        regions(c1, cid, room["room_id"], b="partial")
    with TestClient(create_app(scenes)) as c2:
        got = c2.get(f"/api/cameras/{cid}/seat-regions").json()
        assert got["room_id"] == room["room_id"] and {r["visibility"] for r in got["regions"]} == {"monitored", "partial"}
        assert c2.get(f"/api/rooms/{room['room_id']}").json()["seat_count"] == 2


def test_migration_0001_to_0002_preserves_existing_data(tmp_path):
    url = f"sqlite:///{tmp_path/'old.db'}"
    run_migrations(url, "0001")
    eng = sa.create_engine(url)
    with eng.begin() as cx:
        cx.execute(sa.text("INSERT INTO cameras (camera_id,name,source_type,source_uri,created_at,updated_at) VALUES ('CAM-OLD001','old','WEBCAM','0','2026-01-01','2026-01-01')"))
    run_migrations(url)
    with eng.connect() as cx:
        row = cx.execute(sa.text("SELECT camera_id, room_id, baseline_at FROM cameras")).one()
    assert tuple(row) == ("CAM-OLD001", None, None)
    assert {"rooms", "seats", "camera_seat_regions"} <= set(sa.inspect(eng).get_table_names())
