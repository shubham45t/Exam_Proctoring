from __future__ import annotations

import logging
import os

import cv2
import numpy as np

from app.config import Settings

from .base import FrameSource, SourceError, SourceType
from .validation import redact_uri, validate_source

log = logging.getLogger(__name__)

NETWORK_HINTS = [
    "Open the same URL in a desktop browser or VLC on this computer to confirm it works independently.",
    "Phone and computer must be on the same Wi-Fi/LAN (guest networks and some campus Wi-Fi isolate clients).",
    "Check the computer firewall and that the phone app's streaming server is still running in the foreground.",
    "If the stream needs a username/password, include it in the URL: scheme://user:pass@host:port/path.",
    "Make sure the URL path matches what the phone app displays (many apps differ, e.g. /video, /stream, /live).",
]


class OpenCVSource(FrameSource):
    """One adapter for everything OpenCV/FFmpeg can open. Subclasses only differ in policy."""

    def __init__(self, target: str | int, display: str, *, live: bool, loop: bool, settings: Settings):
        self._target = target
        self._display = display  # redacted; the only form ever used in messages/logs
        self._live = live
        self._loop = loop
        self._s = settings
        self._cap: cv2.VideoCapture | None = None
        self._fps = 25.0

    is_live = property(lambda self: self._live)  # type: ignore[assignment]
    nominal_fps = property(lambda self: self._fps)  # type: ignore[assignment]

    def open(self) -> None:
        self.close()
        is_url = isinstance(self._target, str) and "://" in self._target
        if is_url:
            cap = cv2.VideoCapture(
                self._target,
                cv2.CAP_FFMPEG,
                [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(self._s.open_timeout_s * 1000),
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(self._s.read_timeout_s * 1000),
                ],
            )
        else:
            cap = cv2.VideoCapture(self._target)
        if not cap.isOpened():
            cap.release()
            hints = NETWORK_HINTS if is_url else ["Check the file/device exists and is not in use by another program."]
            raise SourceError("OPEN_FAILED", f"Could not open source {self._display}.", hints)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # best effort: avoid latency build-up
        self._fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if not (1.0 <= self._fps <= 120.0):
            self._fps = 25.0
        self._cap = cap

    def read(self) -> np.ndarray | None:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok and self._loop and not self._live:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def build_source(source_type: SourceType, uri: str, settings: Settings) -> FrameSource:
    target = validate_source(source_type, uri, settings.media_dir)
    if source_type is SourceType.RTSP:
        # TCP is far more reliable than UDP across Wi-Fi/campus networks.
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    display = redact_uri(uri) if source_type in (SourceType.HTTP_MJPEG, SourceType.RTSP) else str(uri)
    live = source_type is not SourceType.VIDEO_FILE
    return OpenCVSource(target, display, live=live, loop=not live, settings=settings)
