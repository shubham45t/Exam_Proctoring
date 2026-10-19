from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from .base import FrameSource, SourceError


@dataclass
class ProbeResult:
    ok: bool
    frames_read: int = 0
    width: int | None = None
    height: int | None = None
    measured_fps: float | None = None
    is_live: bool | None = None
    elapsed_s: float = 0.0
    error: dict | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def probe_source(source: FrameSource, max_frames: int = 10, max_seconds: float = 8.0) -> ProbeResult:
    """Open the source, read a few frames, report what we got. Always closes the source."""
    t0 = time.monotonic()
    try:
        source.open()
    except SourceError as e:
        return ProbeResult(False, error=e.to_dict(), elapsed_s=round(time.monotonic() - t0, 2))
    try:
        n = 0
        first_t = last_t = None
        w = h = None
        while n < max_frames and time.monotonic() - t0 < max_seconds:
            frame = source.read()
            if frame is None:
                time.sleep(0.05)
                continue
            now = time.monotonic()
            first_t = first_t or now
            last_t = now
            h, w = frame.shape[:2]
            n += 1
        elapsed = round(time.monotonic() - t0, 2)
        if n == 0:
            err = SourceError(
                "NO_FRAMES",
                "The source opened but delivered no frames.",
                ["Authentication may have failed silently, or the stream path is wrong.", "Try the URL in VLC first."],
            )
            return ProbeResult(False, elapsed_s=elapsed, error=err.to_dict())
        fps = round((n - 1) / (last_t - first_t), 1) if n > 1 and last_t > first_t else None
        notes = []
        if source.is_live and fps is not None and fps < 5:
            notes.append("Low frame rate: consider lowering stream resolution/quality in the phone app.")
        return ProbeResult(True, n, w, h, fps, source.is_live, elapsed, None, notes)
    finally:
        source.close()
