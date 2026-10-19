"""Camera-source abstraction. CV code only ever sees FrameSource; protocol details stay in adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

import numpy as np


class SourceType(str, Enum):
    VIDEO_FILE = "VIDEO_FILE"  # prerecorded test video inside the media directory
    WEBCAM = "WEBCAM"  # local device index, e.g. "0"
    HTTP_MJPEG = "HTTP_MJPEG"  # http(s):// stream, e.g. many phone camera apps
    RTSP = "RTSP"  # rtsp(s):// stream, e.g. IP cameras / NVR


class SourceError(Exception):
    """Raised for any source problem. `message` is safe to show to users (no credentials)."""

    def __init__(self, code: str, message: str, hints: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hints = hints or []

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "hints": self.hints}


class FrameSource(ABC):
    @property
    @abstractmethod
    def is_live(self) -> bool: ...

    @property
    @abstractmethod
    def nominal_fps(self) -> float: ...

    @abstractmethod
    def open(self) -> None:
        """Open the source or raise SourceError."""

    @abstractmethod
    def read(self) -> np.ndarray | None:
        """Return one BGR frame, or None if no frame could be read."""

    @abstractmethod
    def close(self) -> None:
        """Release resources. Must be idempotent."""
