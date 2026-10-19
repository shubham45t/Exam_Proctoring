from app.cameras.adapters import build_source
from app.cameras.base import SourceType
from app.cameras.probe import probe_source

from .conftest import write_video


def test_video_file_probe_ok(settings, video):
    r = probe_source(build_source(SourceType.VIDEO_FILE, video, settings), max_frames=5)
    assert r.ok and r.frames_read == 5 and (r.width, r.height) == (320, 240) and r.is_live is False


def test_video_file_loops_past_end(settings, tmp_path):
    write_video(settings.media_dir / "short.avi", "moving", frames=5)
    src = build_source(SourceType.VIDEO_FILE, "short.avi", settings)
    src.open()
    got = sum(src.read() is not None for _ in range(12))  # more reads than frames in the file
    src.close()
    assert got == 12


def test_probe_reports_corrupt_file_without_crashing(settings):
    (settings.media_dir / "bad.avi").write_bytes(b"not a video at all")
    r = probe_source(build_source(SourceType.VIDEO_FILE, "bad.avi", settings), max_frames=3, max_seconds=2)
    assert not r.ok and r.error["code"] in {"OPEN_FAILED", "NO_FRAMES"}


def test_http_mjpeg_phone_style_stream(settings, mjpeg_server):
    """Exercises the same adapter a phone camera app would use (HTTP multipart MJPEG)."""
    url = f"http://127.0.0.1:{mjpeg_server.port}/video"
    r = probe_source(build_source(SourceType.HTTP_MJPEG, url, settings), max_frames=8)
    assert r.ok and r.is_live is True and r.frames_read == 8 and r.measured_fps and r.measured_fps > 3


def test_http_wrong_path_fails_with_hints(settings, mjpeg_server):
    url = f"http://127.0.0.1:{mjpeg_server.port}/nope"
    r = probe_source(build_source(SourceType.HTTP_MJPEG, url, settings), max_frames=2, max_seconds=4)
    assert not r.ok and r.error["hints"]


def test_unreachable_host_fails_fast_and_never_leaks_credentials(settings):
    url = "http://user:topsecret@127.0.0.1:9/video"  # port 9 closed
    r = probe_source(build_source(SourceType.HTTP_MJPEG, url, settings), max_frames=2, max_seconds=4)
    assert not r.ok and "topsecret" not in str(r.to_dict())
