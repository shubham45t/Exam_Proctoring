"""Multi-object tracker, ByteTrack-style association WITHOUT a Kalman filter ("iou-bytetrack-lite").

* Stage 1 matches high-confidence detections to existing tracks by IoU (Hungarian assignment).
* Stage 2 matches remaining LOW-confidence detections to still-unmatched tracks (keeps a track alive
  through weak frames), but low detections can never create a track.
* Tracks are reported only after `confirm_hits` detections spanning `confirm_min_s` (flicker filter).
* Missing detections make a confirmed track LOST; after `max_age_s` it EXPIRES. A re-matched LOST
  track keeps its ID (temporary occlusion). Time is explicit (seconds), so behaviour does not depend on fps.
Simplifications vs real ByteTrack: no motion prediction, so fast-moving objects at low fps may lose their ID."""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.optimize import linear_sum_assignment

from .base import Detection


@dataclass
class Track:
    track_id: int
    class_name: str
    box: tuple[float, float, float, float]
    confidence: float
    max_confidence: float
    first_ts: float
    last_seen_ts: float
    hits: int = 1
    confirmed: bool = False
    lost: bool = False


@dataclass
class TrackEvent:
    kind: str  # confirmed | lost | reacquired | expired
    track: Track  # snapshot at the time of the event
    ts: float


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class IoUTracker:
    name = "iou-bytetrack-lite"

    def __init__(self, high_conf: float, match_iou: float, max_age_s: float, confirm_hits: int, confirm_min_s: float):
        self.high, self.match_iou, self.max_age = high_conf, match_iou, max_age_s
        self.confirm_hits, self.confirm_min_s = confirm_hits, confirm_min_s
        self._tracks: list[Track] = []
        self._next = 1
        self.tentative_dropped = 0

    def active(self) -> list[Track]:
        return [replace(t) for t in self._tracks]

    def _associate(self, tracks: list[int], dets: list[int], all_dets: list[Detection]) -> list[tuple[int, int]]:
        if not tracks or not dets:
            return []
        cost = np.ones((len(tracks), len(dets)))
        for i, ti in enumerate(tracks):
            for j, dj in enumerate(dets):
                if self._tracks[ti].class_name == all_dets[dj].class_name:
                    cost[i, j] = 1.0 - iou(self._tracks[ti].box, all_dets[dj].box)
        rows, cols = linear_sum_assignment(cost)
        return [(tracks[r], dets[c]) for r, c in zip(rows, cols) if 1.0 - cost[r, c] >= self.match_iou]

    def update(self, detections: list[Detection], ts: float) -> list[TrackEvent]:
        events: list[TrackEvent] = []
        high = [i for i, d in enumerate(detections) if d.confidence >= self.high]
        low = [i for i, d in enumerate(detections) if d.confidence < self.high]
        all_tracks = list(range(len(self._tracks)))
        m1 = self._associate(all_tracks, high, detections)
        matched_t = {t for t, _ in m1}
        m2 = self._associate([t for t in all_tracks if t not in matched_t], low, detections)
        matched_t |= {t for t, _ in m2}
        matched_d = {d for _, d in m1}

        for ti, di in m1 + m2:
            t, d = self._tracks[ti], detections[di]
            t.box, t.confidence, t.last_seen_ts, t.hits = d.box, d.confidence, ts, t.hits + 1
            t.max_confidence = max(t.max_confidence, d.confidence)
            if t.lost:
                t.lost = False
                events.append(TrackEvent("reacquired", replace(t), ts))
            if not t.confirmed and t.hits >= self.confirm_hits and ts - t.first_ts >= self.confirm_min_s:
                t.confirmed = True
                events.append(TrackEvent("confirmed", replace(t), ts))

        survivors: list[Track] = []
        for ti, t in enumerate(self._tracks):
            if ti in matched_t:
                survivors.append(t)
            elif ts - t.last_seen_ts > self.max_age:
                if t.confirmed:
                    events.append(TrackEvent("expired", replace(t), ts))
                else:
                    self.tentative_dropped += 1  # never reported: a flicker, not an object
            else:
                if t.confirmed and not t.lost:
                    t.lost = True
                    events.append(TrackEvent("lost", replace(t), ts))
                survivors.append(t)
        self._tracks = survivors

        for di in high:
            if di not in matched_d:
                d = detections[di]
                self._tracks.append(Track(self._next, d.class_name, d.box, d.confidence, d.confidence, ts, ts))
                self._next += 1
        return events

    def reset(self, ts: float) -> list[TrackEvent]:
        """End every track (e.g. camera went down). Confirmed tracks produce an 'expired' event."""
        ev = [TrackEvent("expired", replace(t), ts) for t in self._tracks if t.confirmed]
        self._tracks = []
        return ev
