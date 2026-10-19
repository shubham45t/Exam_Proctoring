from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def textured(seed: int, w=320, h=240) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(40, 220, (h, w, 3), dtype=np.uint8)


def write_video(path: Path, kind: str = "moving", frames: int = 45, fps: int = 15) -> Path:
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (320, 240))
    base = textured(1)
    for i in range(frames):
        if kind == "moving":
            f = base.copy()
            cv2.rectangle(f, (10 + i * 5, 80), (70 + i * 5, 140), (255, 255, 255), -1)
        elif kind == "static":
            f = base.copy()
        elif kind == "dark":
            f = (textured(i) // 40).astype(np.uint8)
        vw.write(f)
    vw.release()
    assert path.exists() and path.stat().st_size > 0
    return path


@pytest.fixture
def settings(tmp_path) -> Settings:
    media = tmp_path / "media"
    media.mkdir()
    return Settings(
        env="development", database_url=f"sqlite:///{tmp_path / 'test.db'}", media_dir=media,
        evidence_dir=tmp_path / "evidence", calibration_dir=tmp_path / "calib", detector="none", analysis_fps=20, open_timeout_s=3, read_timeout_s=3,
        reconnect_initial_s=0.1, reconnect_max_s=0.4, stale_after_s=0.6, frozen_after_s=0.8,
        quality_confirm_count=2, read_failure_limit=3, occ_confirm_count=3, occ_freshness_s=3.0,
    )


@pytest.fixture
def video(settings) -> str:
    write_video(settings.media_dir / "moving.avi", "moving")
    return "moving.avi"


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def wait_for(cond, timeout=8.0, interval=0.05):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(interval)
    return None


class FakeMjpegServer:
    """Stands in for a phone camera app: serves multipart/x-mixed-replace JPEG at /video."""

    def __init__(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence
                pass

            def do_GET(self):
                if self.path != "/video":
                    self.send_response(404); self.end_headers(); return
                outer.last_auth = self.headers.get("Authorization")
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                i = 0
                try:
                    while not outer.stopped:
                        f = textured(i % 5)
                        cv2.rectangle(f, (i * 3 % 250, 50), (i * 3 % 250 + 40, 100), (255, 255, 255), -1)
                        jpg = cv2.imencode(".jpg", f)[1].tobytes()
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg + b"\r\n")
                        i += 1
                        time.sleep(0.05)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.stopped = False
        self.last_auth = None
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.stopped = True
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def mjpeg_server():
    s = FakeMjpegServer()
    yield s
    s.stop()


SEAT_A = [[0.05, 0.2], [0.45, 0.2], [0.45, 0.8], [0.05, 0.8]]
SEAT_B = [[0.55, 0.2], [0.95, 0.2], [0.95, 0.8], [0.55, 0.8]]


def write_scene(path: Path, occupied: list | None, frames: int = 60, fps: int = 15, phone: tuple | None = None) -> Path:
    """Synthetic room: textured empty background + sensor noise; optionally a bright 'person' blob in one seat region."""
    import cv2
    rng = np.random.default_rng(5)
    base = textured(1)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (320, 240))
    for _ in range(frames):
        f = np.clip(base.astype(np.int16) + rng.integers(-3, 4, base.shape), 0, 255).astype(np.uint8)
        if occupied:
            pts = np.array([[int(x * 320), int(y * 240)] for x, y in occupied], np.int32)
            cv2.fillPoly(f, [pts], (250, 250, 250))
        if phone:  # magenta rectangle (x1,y1,x2,y2 normalised) that ColorBlobDetector treats as "a phone"
            cv2.rectangle(f, (int(phone[0] * 320), int(phone[1] * 240)), (int(phone[2] * 320), int(phone[3] * 240)), (255, 0, 255), -1)
        vw.write(f)
    vw.release()
    return path


class ColorBlobDetector:
    """TEST-ONLY STUB. 'Detects' a magenta rectangle painted into synthetic video and reports it as a phone.
    It exercises tracker/dedup/evidence/API plumbing; it is NOT an AI model and proves nothing about accuracy."""

    model_id = "test-stub-colorblob"
    model_version = "0"

    def __init__(self, conf: float = 0.9, delay_s: float = 0.0, fail: bool = False):
        self.conf, self.delay_s, self.fail, self.calls = conf, delay_s, fail, 0

    def detect(self, image):
        import time as _t
        from app.perception.detection.base import Detection
        self.calls += 1
        if self.delay_s:
            _t.sleep(self.delay_s)
        if self.fail:
            raise RuntimeError("stub detector failure")
        import cv2
        b, g, r = image[..., 0].astype(int), image[..., 1].astype(int), image[..., 2].astype(int)
        mask = ((b > 170) & (r > 170) & (g < 110)).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))  # drop speckle from background noise
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return []
        x, y, bw, bh = cv2.boundingRect(max(cnts, key=cv2.contourArea))
        if bw * bh < 100:
            return []
        h, w = image.shape[:2]
        xs, ys = np.array([x, x + bw]), np.array([y, y + bh])
        return [Detection("cell phone", self.conf, xs[0] / w, ys[0] / h, xs[1] / w, ys[1] / h)]
