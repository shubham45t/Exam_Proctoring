from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .base import SourceError, SourceType

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}
_SCHEMES = {SourceType.HTTP_MJPEG: {"http", "https"}, SourceType.RTSP: {"rtsp", "rtsps"}}


def redact_uri(uri: str) -> str:
    """Remove credentials and query values so the result is safe for logs, APIs and the UI."""
    try:
        parts = urlsplit(uri)
    except ValueError:
        return "<invalid>"
    if not parts.scheme or not parts.hostname:
        return uri if "://" not in uri and "@" not in uri else "<redacted>"
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    query = "?…" if parts.query else ""
    return urlunsplit((parts.scheme, host, parts.path, "", "")) + query


def resolve_video_path(name: str, media_dir: Path) -> Path:
    """Only files directly inside media_dir are allowed (blocks ../ traversal and absolute paths)."""
    media_root = media_dir.resolve()
    candidate = (media_root / name).resolve()
    if candidate.parent != media_root:
        raise SourceError("PATH_OUTSIDE_MEDIA_DIR", "Video files must be placed directly in the media directory.")
    if candidate.suffix.lower() not in VIDEO_EXTENSIONS:
        raise SourceError("UNSUPPORTED_FILE_TYPE", f"Supported video types: {', '.join(sorted(VIDEO_EXTENSIONS))}.")
    if not candidate.is_file():
        raise SourceError("FILE_NOT_FOUND", f"Video file '{name}' was not found in the media directory.")
    return candidate


def validate_source(source_type: SourceType, uri: str, media_dir: Path) -> str | int:
    """Validate and normalise a user-supplied source. Returns what OpenCV should open."""
    uri = uri.strip()
    if not uri:
        raise SourceError("INVALID_URL", "Source is empty.")
    if source_type is SourceType.WEBCAM:
        if not uri.isdigit() or int(uri) > 16:
            raise SourceError("INVALID_DEVICE", "Webcam source must be a device index such as 0.")
        return int(uri)
    if source_type is SourceType.VIDEO_FILE:
        return str(resolve_video_path(uri, media_dir))
    try:
        parts = urlsplit(uri)
        _ = parts.port  # raises ValueError for a bad port
    except ValueError:
        raise SourceError("INVALID_URL", "The URL could not be parsed.") from None
    allowed = _SCHEMES[source_type]
    if parts.scheme.lower() not in allowed:
        raise SourceError(
            "UNSUPPORTED_SCHEME",
            f"{source_type.value} sources must start with {' or '.join(s + '://' for s in sorted(allowed))}.",
            ["Check you selected the right source type for this URL."],
        )
    if not parts.hostname:
        raise SourceError("INVALID_URL", "The URL has no host.")
    return uri
