# Seat occupancy: method, states and limits

**Method id:** `baseline-diff-v1 (heuristic)`. Implemented and unit/integration tested on *synthetic* footage only. **Not evaluated on real classroom footage; accuracy is unknown.**

## How
Frame -> grayscale/blur at 320 px -> global brightness matching against the empty-room baseline -> per-pixel difference (>25) -> fraction of changed pixels inside each seat polygon. A seat changes state only after N (default 6) consecutive samples beyond the enter (0.20) / exit (0.08) thresholds, so flicker is ignored. The score is a *margin heuristic, not a probability*. Whole-scene change (>55% of pixels) means lighting/camera movement, so all seats become UNCERTAIN. All thresholds are `OMNI_OCC_*` settings, uncalibrated defaults.

## States
| State | Meaning |
|---|---|
| OCCUPIED / VACANT | Confirmed by a current, healthy camera |
| UNCERTAIN | Cannot tell now: camera stopped/stale/frozen/degraded, no baseline, scene changed, partial view, or cameras disagree |
| OCCLUDED | Seat covered by a camera but manually marked not adequately visible (not auto-detected) |
| UNMONITORED | No camera covers the seat, or seat marked unmonitored |

## Multi-camera rule (a seat is counted once)
Any fresh OCCUPIED => OCCUPIED; all fresh VACANT => VACANT; otherwise UNCERTAIN. Observations older than `OMNI_OCC_FRESHNESS_S` (6 s) are ignored. Events are stored per camera on change only.

## Known limits
Detects *change from empty*, not people: bags, coats, moved chairs, shadows, screens or lighting drift can read as occupied; a very still person in baseline-like colours can read as vacant. Occlusion by standing people is not detected automatically. Needs a fixed camera. Planned: replace/augment with a person detector behind the same `OccupancyObservation` contract (needs model weights and licence review).
