import pytest

from app.cameras.base import SourceError, SourceType
from app.cameras.validation import redact_uri, validate_source


def test_redaction_removes_credentials_and_query_values():
    r = redact_uri("rtsp://admin:s3cret@192.168.1.5:554/live?token=abc")
    assert "s3cret" not in r and "admin" not in r and "abc" not in r and "192.168.1.5:554" in r


@pytest.mark.parametrize("st,uri,code", [
    (SourceType.HTTP_MJPEG, "rtsp://h/x", "UNSUPPORTED_SCHEME"),
    (SourceType.RTSP, "http://h/x", "UNSUPPORTED_SCHEME"),
    (SourceType.HTTP_MJPEG, "http://", "INVALID_URL"),
    (SourceType.HTTP_MJPEG, "http://h:99999/x", "INVALID_URL"),
    (SourceType.WEBCAM, "abc", "INVALID_DEVICE"),
    (SourceType.VIDEO_FILE, "../../etc/passwd", "PATH_OUTSIDE_MEDIA_DIR"),
    (SourceType.VIDEO_FILE, "/etc/passwd", "PATH_OUTSIDE_MEDIA_DIR"),
    (SourceType.VIDEO_FILE, "missing.mp4", "FILE_NOT_FOUND"),
    (SourceType.VIDEO_FILE, "notes.txt", "UNSUPPORTED_FILE_TYPE"),
])
def test_invalid_sources_rejected_with_code(tmp_path, st, uri, code):
    with pytest.raises(SourceError) as e:
        validate_source(st, uri, tmp_path)
    assert e.value.code == code


def test_valid_sources(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    assert validate_source(SourceType.VIDEO_FILE, "a.mp4", tmp_path).endswith("a.mp4")
    assert validate_source(SourceType.WEBCAM, "0", tmp_path) == 0
    assert validate_source(SourceType.RTSP, "rtsp://u:p@h:554/s", tmp_path)
    assert validate_source(SourceType.HTTP_MJPEG, "http://192.168.1.7:8080/video", tmp_path)
