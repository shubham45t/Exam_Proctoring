from .conftest import wait_for


def cam(client, video, name="Test cam", st="VIDEO_FILE"):
    return client.post("/api/cameras", json={"name": name, "source_type": st, "source_uri": video})


def test_health_and_status(client):
    assert client.get("/api/health").json() == {"status": "ok", "version": "0.1.0"}
    s = client.get("/api/system/status").json()
    assert s["database"]["ok"] and s["cameras"]["running"] == 0 and "memory_percent" in s["resources"]


def test_openapi_documents_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ["/api/health", "/api/cameras", "/api/cameras/{camera_id}/test", "/api/events"]:
        assert p in paths


def test_camera_crud_and_credentials_never_returned(client):
    r = client.post("/api/cameras", json={"name": "Phone", "source_type": "HTTP_MJPEG",
                                          "source_uri": "http://admin:hunter2@192.168.1.9:8080/video?key=zzz"})
    assert r.status_code == 201
    body = r.json()
    assert "hunter2" not in r.text and "zzz" not in r.text and "admin" not in r.text
    assert body["source_display"].startswith("http://192.168.1.9:8080/video")
    assert "hunter2" not in client.get("/api/cameras").text
    cid = body["camera_id"]
    assert client.patch(f"/api/cameras/{cid}", json={"name": "Phone 2"}).json()["name"] == "Phone 2"
    assert client.delete(f"/api/cameras/{cid}").status_code == 204
    assert client.get(f"/api/cameras/{cid}").status_code == 404


def test_validation_errors_are_meaningful(client):
    r = client.post("/api/cameras", json={"name": "x", "source_type": "RTSP", "source_uri": "http://nope/x"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "UNSUPPORTED_SCHEME"
    r = client.post("/api/cameras", json={"name": "x", "source_type": "VIDEO_FILE", "source_uri": "../../etc/passwd"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "PATH_OUTSIDE_MEDIA_DIR"
    assert client.post("/api/cameras", json={"name": "", "source_type": "WEBCAM", "source_uri": "0"}).status_code == 422


def test_duplicate_name_conflict(client, video):
    assert cam(client, video).status_code == 201
    assert cam(client, video).status_code == 409


def test_test_endpoint_does_not_start_processing(client, video):
    cid = cam(client, video).json()["camera_id"]
    r = client.post(f"/api/cameras/{cid}/test").json()
    assert r["ok"] and r["frames_read"] >= 1
    assert client.get(f"/api/cameras/{cid}").json()["running"] is False


def test_start_refuses_unreachable_source_with_hints(client):
    cid = client.post("/api/cameras", json={"name": "dead", "source_type": "HTTP_MJPEG",
                                            "source_uri": "http://127.0.0.1:9/video"}).json()["camera_id"]
    r = client.post(f"/api/cameras/{cid}/start")
    assert r.status_code == 502 and r.json()["detail"]["hints"]
    assert client.get(f"/api/cameras/{cid}").json()["running"] is False


def test_start_snapshot_stop_cycle(client, video):
    cid = cam(client, video).json()["camera_id"]
    assert client.post(f"/api/cameras/{cid}/start").status_code == 200
    assert client.post(f"/api/cameras/{cid}/start").status_code == 409
    assert wait_for(lambda: client.get(f"/api/cameras/{cid}/snapshot").status_code == 200)
    jpg = client.get(f"/api/cameras/{cid}/snapshot")
    assert jpg.headers["content-type"] == "image/jpeg" and jpg.content[:2] == b"\xff\xd8"
    assert client.patch(f"/api/cameras/{cid}", json={"name": "new"}).status_code == 409  # can't edit while running
    assert client.post(f"/api/cameras/{cid}/stop").json()["running"] is False
    assert client.get(f"/api/cameras/{cid}/snapshot").status_code == 409


def test_media_listing(client, video):
    assert client.get("/api/media").json()["files"] == [video]


def test_events_pagination_and_filtering(client):
    for _ in range(3):
        assert client.post("/api/events/synthetic", json={}).status_code == 201
    p = client.get("/api/events", params={"limit": 2}).json()
    assert p["total"] == 3 and len(p["items"]) == 2
    assert client.get("/api/events", params={"is_synthetic": False}).json()["total"] == 0
    assert client.get("/api/events", params={"limit": 0}).status_code == 422
    assert client.get("/api/events/EVT-NOPE").status_code == 404


def test_synthetic_disabled_in_production(settings):
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app(settings.model_copy(update={"env": "production"}))) as c:
        assert c.post("/api/events/synthetic", json={}).status_code == 403
