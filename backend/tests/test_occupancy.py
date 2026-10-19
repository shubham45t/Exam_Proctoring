from datetime import timedelta

import cv2
import numpy as np
import pytest

from app.perception.geometry import PolygonError, rasterise, validate_polygon
from app.perception.occupancy import (CameraSeatObs, OccupancyAnalyzer, OccupancyStore, SeatRegion, SeatTracker,
                                      change_map, fuse_seat, prepare, region_fractions)
from app.rooms.seat_ids import generate_grid, seat_id
from app.schemas import CameraState, SeatState, utcnow

from .conftest import textured

A = [(0.1, 0.2), (0.4, 0.2), (0.4, 0.8), (0.1, 0.8)]   # seat A region (left)
B = [(0.6, 0.2), (0.9, 0.2), (0.9, 0.8), (0.6, 0.8)]   # seat B region (right)


def person_at(frame, poly):
    f = frame.copy()
    h, w = f.shape[:2]
    pts = np.array([[int(x * w), int(y * h)] for x, y in poly], np.int32)
    cv2.fillPoly(f, [pts], (250, 250, 250))
    return f


@pytest.fixture
def empty():
    return textured(1, 320, 240)


def make(settings, empty, regions=None, baseline=True, **ovr):
    s = settings.model_copy(update={"occ_confirm_count": 2, **ovr})
    emitted = []
    store = OccupancyStore()
    regions = regions or [SeatRegion("A", A, "monitored"), SeatRegion("B", B, "monitored")]
    base = prepare(empty, s.occ_analysis_width) if baseline else None
    return OccupancyAnalyzer("CAM", regions, base, s, store, emitted.append), store, emitted


# ---- seat ids / geometry
def test_seat_ids_and_grid():
    assert seat_id(2, 4) == "R2-C4"
    g = generate_grid(2, 3)
    assert len(g) == 6 and len({s["seat_id"] for s in g}) == 6 and g[-1]["seat_id"] == "R2-C3"
    for bad in [(0, 3), (31, 1)]:
        with pytest.raises(ValueError):
            generate_grid(*bad)
    with pytest.raises(ValueError):
        seat_id(0, 1)


@pytest.mark.parametrize("pts", [[(0, 0), (1, 1)], [(0, 0), (1, 0), (2, 1)], [(0.1, 0.1), (0.2, 0.2), (0.3, 0.3)],
                                 [(0.1, 0.1), (0.9, 0.9), (0.9, 0.1), (0.1, 0.9)]])  # last one is a bow-tie
def test_invalid_polygons_rejected(pts):
    with pytest.raises(PolygonError):
        validate_polygon([list(p) for p in pts])


def test_rasterise_area_matches_fraction():
    m = rasterise([(0, 0), (0.5, 0), (0.5, 1), (0, 1)], 200, 100)
    assert 0.48 < m.mean() < 0.53


# ---- pure comparison
def test_change_map_detects_person_and_ignores_brightness_shift(empty, settings):
    base = prepare(empty, 320)
    masks = {"A": rasterise(A, 320, 240), "B": rasterise(B, 320, 240)}
    fr = region_fractions(change_map(base, prepare(person_at(empty, A), 320), 25), masks)
    assert fr["A"] > 0.9 and fr["B"] < 0.05
    brighter = np.clip(empty.astype(np.int16) * 1.15, 0, 255).astype(np.uint8)
    fr2 = region_fractions(change_map(base, prepare(brighter, 320), 25), masks)
    assert max(fr2.values()) < 0.08  # global gain compensation


# ---- hysteresis
def test_tracker_needs_consecutive_confirmation_and_ignores_flicker():
    t = SeatTracker(0.2, 0.08, 3)
    for f in [0.9, 0.9]:
        t.update(f)
    assert t.state is SeatState.UNCERTAIN  # 2 < 3 samples
    t.update(0.9)
    assert t.state is SeatState.OCCUPIED
    for f in [0.0, 0.9, 0.0, 0.9, 0.0]:  # flicker never reaches 3 in a row
        t.update(f)
    assert t.state is SeatState.OCCUPIED
    for f in [0.0, 0.0, 0.0]:
        t.update(f)
    assert t.state is SeatState.VACANT


def test_tracker_holds_state_inside_hysteresis_band():
    t = SeatTracker(0.2, 0.08, 2)
    t.update(0.9); t.update(0.9)
    for _ in range(10):
        t.update(0.14)  # between exit and enter
    assert t.state is SeatState.OCCUPIED


# ---- analyzer
def test_analyzer_occupied_vs_vacant_and_events_only_on_change(settings, empty):
    an, store, emitted = make(settings, empty)
    for _ in range(6):
        an.process(person_at(empty, A))
    assert store.get("CAM", "A").state is SeatState.OCCUPIED and store.get("CAM", "B").state is SeatState.VACANT
    assert sorted((e.seat_id, e.state.value) for e in emitted) == [("A", "OCCUPIED"), ("B", "VACANT")]  # one each, not per frame
    for _ in range(6):
        an.process(person_at(empty, A))
    assert len(emitted) == 2
    e = next(e for e in emitted if e.seat_id == "A")
    assert 0.5 <= e.confidence <= 1 and e.method.startswith("baseline-diff") and e.is_synthetic is False


def test_no_baseline_is_uncertain_not_vacant(settings, empty):
    an, store, _ = make(settings, empty, baseline=False)
    for _ in range(5):
        an.process(empty)
    assert store.get("CAM", "A").state is SeatState.UNCERTAIN and "baseline" in store.get("CAM", "A").reason


def test_global_scene_change_is_uncertain(settings, empty):
    an, store, _ = make(settings, empty)
    for _ in range(4):
        an.process(empty)
    assert store.get("CAM", "A").state is SeatState.VACANT
    moved = np.zeros((240, 320, 3), np.uint8)
    moved[:, 160:] = 255  # genuinely different structure (camera moved / lights switched)
    an.process(moved)
    assert store.get("CAM", "A").state is SeatState.UNCERTAIN and "scene" in store.get("CAM", "A").reason


def test_camera_not_connected_clears_current_state(settings, empty):
    an, store, emitted = make(settings, empty)
    for _ in range(4):
        an.process(person_at(empty, A))
    assert store.get("CAM", "A").state is SeatState.OCCUPIED
    an.on_state(CameraState.FROZEN)
    assert store.get("CAM", "A").state is SeatState.UNCERTAIN  # last observation is NOT reported as current
    assert emitted[-1].state is SeatState.UNCERTAIN and emitted[-1].quality.status == "low_quality"
    an.on_state(CameraState.CONNECTED)  # recovery does not invent a state either
    assert store.get("CAM", "A").state is SeatState.UNCERTAIN


def test_partial_visibility_cannot_confirm_vacant_but_can_confirm_occupied(settings, empty):
    an, store, _ = make(settings, empty, [SeatRegion("A", A, "partial"), SeatRegion("B", B, "partial")])
    for _ in range(5):
        an.process(person_at(empty, A))
    assert store.get("CAM", "A").state is SeatState.OCCUPIED
    assert store.get("CAM", "B").state is SeatState.UNCERTAIN and "partial" in store.get("CAM", "B").reason


def test_not_visible_region_is_not_analysed(settings, empty):
    an, store, _ = make(settings, empty, [SeatRegion("A", A, "not_visible"), SeatRegion("B", B, "monitored")])
    for _ in range(4):
        an.process(empty)
    assert store.get("CAM", "A") is None and store.get("CAM", "B").state is SeatState.VACANT


def test_frame_size_mismatch_demands_new_baseline(settings, empty):
    an, store, _ = make(settings, empty)
    an.process(cv2.resize(empty, (320, 100)))
    assert "recapture" in store.get("CAM", "A").reason


# ---- fusion across cameras
NOW = utcnow()


def put(store, cam, seat, state, age=0.0, conf=0.8):
    store.set(cam, seat, CameraSeatObs(state, conf, NOW - timedelta(seconds=age)))


def fuse(store, mappings, monitored=True):
    return fuse_seat("A", monitored, mappings, store, NOW, 6.0)


def test_fusion_unmonitored_and_occluded():
    st = OccupancyStore()
    assert fuse(st, []).state is SeatState.UNMONITORED
    assert fuse(st, [("C1", "monitored")], monitored=False).state is SeatState.UNMONITORED
    assert fuse(st, [("C1", "not_visible")]).state is SeatState.OCCLUDED


def test_fusion_counts_a_seat_once_when_two_cameras_see_it():
    st = OccupancyStore()
    put(st, "C1", "A", SeatState.OCCUPIED); put(st, "C2", "A", SeatState.OCCUPIED)
    f = fuse(st, [("C1", "monitored"), ("C2", "monitored")])
    assert f.state is SeatState.OCCUPIED and len(f.cameras) == 2  # one fused seat, two supporting views


def test_fusion_rules_disagreement_and_staleness():
    st = OccupancyStore()
    put(st, "C1", "A", SeatState.VACANT); put(st, "C2", "A", SeatState.OCCUPIED)
    assert fuse(st, [("C1", "monitored"), ("C2", "monitored")]).state is SeatState.OCCUPIED
    put(st, "C2", "A", SeatState.UNCERTAIN)
    assert fuse(st, [("C1", "monitored"), ("C2", "monitored")]).state is SeatState.UNCERTAIN
    st2 = OccupancyStore()
    put(st2, "C1", "A", SeatState.OCCUPIED, age=60)  # last seen a minute ago
    assert fuse(st2, [("C1", "monitored")]).state is SeatState.UNCERTAIN
    assert fuse(OccupancyStore(), [("C1", "monitored")]).state is SeatState.UNCERTAIN  # never observed
