import itertools
import threading

from app.cameras.base import FrameSource, SourceError
from app.cameras.worker import CameraWorker
from app.schemas import CameraState, QualityIssue

from .conftest import textured, wait_for


class Scripted(FrameSource):
    """Frame source whose behaviour a test controls."""

    def __init__(self, frame_fn, fail_opens=0, shared=None):
        self.frame_fn, self.shared = frame_fn, shared if shared is not None else {}
        self.shared.setdefault("opens", 0); self.shared.setdefault("closed", 0); self.shared.setdefault("deliver", True)
        self.shared["fail_opens"] = fail_opens if "fail_opens" not in self.shared else self.shared["fail_opens"]
        self._i = itertools.count()

    is_live = True
    nominal_fps = 20.0

    def open(self):
        self.shared["opens"] += 1
        if self.shared["fail_opens"] > 0:
            self.shared["fail_opens"] -= 1
            raise SourceError("OPEN_FAILED", "scripted failure")

    def read(self):
        import time
        if not self.shared["deliver"]:
            time.sleep(0.05)
            return None
        time.sleep(0.04)
        return self.frame_fn(next(self._i))

    def close(self):
        self.shared["closed"] += 1


def run_worker(settings, frame_fn, shared=None, fail_opens=0):
    events, lock = [], threading.Lock()

    def sink(ev):
        with lock:
            events.append(ev)

    shared = shared if shared is not None else {}
    w = CameraWorker("CAM-T", lambda: Scripted(frame_fn, fail_opens, shared), settings, sink)
    w.start()
    return w, events, shared


def states(events):
    return [e.state for e in events]


def test_healthy_camera_reaches_connected(settings):
    w, ev, _ = run_worker(settings, lambda i: textured(i % 7))
    try:
        assert wait_for(lambda: CameraState.CONNECTED in states(ev))
    finally:
        w.stop()
    assert states(ev)[-1] is CameraState.STOPPED


def test_frozen_stream_is_not_reported_as_connected(settings):
    still = textured(3)
    w, ev, _ = run_worker(settings, lambda i: still)
    try:
        assert wait_for(lambda: CameraState.FROZEN in states(ev), timeout=6)
    finally:
        w.stop()


def test_dark_frames_flag_degraded_with_issue(settings):
    w, ev, _ = run_worker(settings, lambda i: (textured(i) // 40).astype("uint8"))
    try:
        assert wait_for(lambda: any(e.state is CameraState.DEGRADED and QualityIssue.DARK in e.quality_issues for e in ev))
    finally:
        w.stop()


def test_blurry_frames_flag_degraded(settings):
    import cv2
    w, ev, _ = run_worker(settings, lambda i: cv2.GaussianBlur(textured(i % 9), (0, 0), 25))
    try:
        assert wait_for(lambda: any(QualityIssue.BLURRY in e.quality_issues for e in ev))
    finally:
        w.stop()


def test_stream_interruption_goes_stale_then_recovers_without_new_worker(settings):
    shared = {"deliver": True}
    w, ev, _ = run_worker(settings, lambda i: textured(i % 7), shared)
    try:
        assert wait_for(lambda: CameraState.CONNECTED in states(ev))
        shared["deliver"] = False  # simulate Wi-Fi drop
        assert wait_for(lambda: any(s in states(ev) for s in (CameraState.STALE, CameraState.RECONNECTING)), timeout=6)
        shared["deliver"] = True
        n = len(ev)
        assert wait_for(lambda: CameraState.CONNECTED in states(ev[n:]), timeout=8), states(ev)
        assert shared["opens"] >= 2  # reconnect really re-opened the source
    finally:
        w.stop()


def test_open_failures_report_failed_then_backoff_then_connect(settings):
    w, ev, shared = run_worker(settings, lambda i: textured(i % 7), fail_opens=2)
    try:
        assert wait_for(lambda: CameraState.CONNECTED in states(ev), timeout=8)
        assert CameraState.FAILED in states(ev) and shared["opens"] == 3
    finally:
        w.stop()


def test_stop_releases_source_and_threads(settings):
    w, ev, shared = run_worker(settings, lambda i: textured(i % 7))
    wait_for(lambda: CameraState.CONNECTED in states(ev))
    w.stop()
    assert shared["closed"] >= 1 and not w.running
    assert not any(t.is_alive() for t in w._threads)


def test_frame_buffer_is_bounded_and_drops_oldest(settings):
    from app.cameras.worker import Frame, FrameBuffer
    b = FrameBuffer(2)
    for i in range(10):
        b.put(Frame(textured(0), i, 0.0))
    assert b.latest().seq == 9 and b.dropped == 8 and len(b._d) == 2
