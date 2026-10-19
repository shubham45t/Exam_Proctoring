import pytest

from app.perception.detection.base import Detection
from app.perception.detection.tracker import IoUTracker, iou


def d(x=0.4, y=0.4, conf=0.9, cls="cell phone", w=0.1, h=0.1):
    return Detection(cls, conf, x, y, x + w, y + h)


def tr(**kw):
    a = dict(high_conf=0.45, match_iou=0.2, max_age_s=2.0, confirm_hits=3, confirm_min_s=1.0)
    a.update(kw)
    return IoUTracker(**a)


def run(t, frames):
    """frames: list of (ts, [detections]); returns flat list of (kind, track_id)."""
    out = []
    for ts, dets in frames:
        out += [(e.kind, e.track.track_id) for e in t.update(dets, ts)]
    return out


def test_iou_basics():
    assert iou((0, 0, 1, 1), (0, 0, 1, 1)) == 1.0 and iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0.0


def test_confirms_only_after_hits_and_min_duration_with_stable_id():
    t = tr()
    ev = run(t, [(0.0, [d()]), (0.5, [d()])])
    assert ev == []  # 2 hits, 0.5 s: not yet an object
    ev = run(t, [(0.9, [d()])])
    assert ev == []  # 3 hits but only 0.9 s
    ev = run(t, [(1.0, [d()]), (1.5, [d()])])
    assert ev == [("confirmed", 1)]  # reported exactly once, ID 1
    assert run(t, [(2.0 + i * 0.5, [d()]) for i in range(20)]) == []  # 10 more seconds visible: no new events


def test_flicker_is_never_reported():
    t = tr()
    assert run(t, [(0.0, [d()]), (0.5, []), (1.0, []), (3.5, []), (4.0, [])]) == []
    assert t.tentative_dropped == 1 and t.active() == []


def test_occlusion_keeps_id_then_expiry_reports_once():
    t = tr()
    run(t, [(i * 0.5, [d()]) for i in range(5)])  # confirmed
    ev = run(t, [(2.5, []), (3.0, [])])
    assert ev == [("lost", 1)]
    ev = run(t, [(3.5, [d()])])  # phone comes back after 1 s of occlusion
    assert ev == [("reacquired", 1)]
    ev = run(t, [(4.0, []), (6.5, []), (7.0, [])])
    assert ev == [("lost", 1), ("expired", 1)]
    assert t.active() == []


def test_new_object_after_expiry_gets_new_id():
    t = tr()
    run(t, [(i * 0.5, [d()]) for i in range(5)] + [(2.5, []), (5.0, [])])
    ev = run(t, [(6.0 + i * 0.5, [d()]) for i in range(5)])
    assert ev == [("confirmed", 2)]


def test_two_separate_objects_are_tracked_independently():
    t = tr()
    ev = run(t, [(i * 0.5, [d(0.1, 0.1), d(0.7, 0.7)]) for i in range(5)])
    assert sorted(ev) == [("confirmed", 1), ("confirmed", 2)]


def test_class_must_match():
    t = tr(confirm_hits=2, confirm_min_s=0.0)
    ev = run(t, [(0.0, [d(cls="cell phone")]), (0.5, [d(cls="laptop")]), (1.0, [d(cls="laptop")])])
    assert ev == [("confirmed", 2)] and sorted(x.class_name for x in t.active()) == ["cell phone", "laptop"]


def test_low_confidence_keeps_track_alive_but_cannot_start_one():
    t = tr()
    assert run(t, [(i * 0.5, [d(conf=0.35)]) for i in range(6)]) == []  # only weak detections: no track at all
    assert t.active() == []
    run(t, [(10 + i * 0.5, [d()]) for i in range(5)])  # strong detections confirm a track
    ev = run(t, [(12.5 + i * 0.5, [d(conf=0.35)]) for i in range(6)])  # then weak ones keep it alive
    assert ev == [] and t.active()[0].lost is False


def test_reset_expires_confirmed_tracks_only():
    t = tr()
    run(t, [(i * 0.5, [d(0.1, 0.1)]) for i in range(5)])
    run(t, [(2.0, [d(0.1, 0.1), d(0.7, 0.7)])])  # second object, unconfirmed
    ev = t.reset(3.0)
    assert [(e.kind, e.track.track_id) for e in ev] == [("expired", 1)] and t.active() == []
