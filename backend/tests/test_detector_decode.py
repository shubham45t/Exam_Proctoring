from pathlib import Path

import numpy as np
import pytest

from app.config import BACKEND_ROOT
from app.perception.detection.evaluation import evaluate, iou_px, latency_stats
from app.perception.detection.yolox_onnx import COCO_CLASSES, YoloxOnnxDetector, decode_yolox, letterbox

PHONE = COCO_CLASSES.index("cell phone")


def raw_with(anchors: dict[int, tuple], n=3549):
    """Raw head output with a few active anchors: idx -> (dx, dy, log_w, log_h, obj, cls_score)."""
    raw = np.zeros((n, 85), np.float32)
    raw[:, 2:4] = -5.0
    for i, (dx, dy, lw, lh, obj, cs) in anchors.items():
        raw[i, :4] = (dx, dy, lw, lh)
        raw[i, 4] = obj
        raw[i, 5 + PHONE] = cs
    return raw


def test_letterbox_geometry():
    img = np.zeros((480, 640, 3), np.uint8)
    img[:] = 50
    canvas, r = letterbox(img, 416)
    assert canvas.shape == (416, 416, 3) and abs(r - 0.65) < 1e-6
    assert (canvas[312:, :] == 114).all() and (canvas[:312, :] == 50).all()  # 480*0.65=312 rows of content on top, padding below


def test_decode_places_box_correctly_in_original_image():
    # stride-8 grid is 52x52: anchor at column 10,row 20 -> index 20*52+10; centre=(10+.5)*8=84, (20+.5)*8=164; w=h=exp(ln 4)*8=32
    idx = 20 * 52 + 10
    dets = decode_yolox(raw_with({idx: (0.5, 0.5, np.log(4), np.log(4), 0.9, 0.8)}), 416, 0.65, 640, 480, {PHONE: "cell phone"}, 0.3, 0.45)
    assert len(dets) == 1
    d = dets[0]
    assert d.class_name == "cell phone" and abs(d.confidence - 0.72) < 1e-4
    # model-space box (68,148)-(100,180) divided by ratio .65, normalised by 640x480
    assert abs(d.x1 - 68 / 0.65 / 640) < 1e-3 and abs(d.y1 - 148 / 0.65 / 480) < 1e-3
    assert abs(d.x2 - 100 / 0.65 / 640) < 1e-3 and abs(d.y2 - 180 / 0.65 / 480) < 1e-3


def test_nms_merges_duplicate_anchors_and_threshold_filters():
    a, b = 20 * 52 + 10, 20 * 52 + 11  # neighbouring anchors, heavily overlapping boxes
    raw = raw_with({a: (0.5, 0.5, np.log(4), np.log(4), 0.9, 0.8), b: (0.2, 0.5, np.log(4), np.log(4), 0.9, 0.7)})
    assert len(decode_yolox(raw, 416, 0.65, 640, 480, {PHONE: "cell phone"}, 0.3, 0.45)) == 1
    assert decode_yolox(raw_with({a: (0.5, 0.5, 1, 1, 0.5, 0.4)}), 416, 0.65, 640, 480, {PHONE: "cell phone"}, 0.3, 0.45) == []  # 0.2 < 0.3


def test_only_requested_classes_are_returned():
    raw = raw_with({20 * 52 + 10: (0.5, 0.5, 1, 1, 0.9, 0.8)})
    assert decode_yolox(raw, 416, 0.65, 640, 480, {COCO_CLASSES.index("laptop"): "laptop"}, 0.3, 0.45) == []


def test_wrong_input_size_gives_clear_error():
    with pytest.raises(ValueError, match="OMNI_DETECTOR_INPUT_SIZE"):
        decode_yolox(raw_with({}), 640, 1.0, 640, 480, {PHONE: "cell phone"}, 0.3, 0.45)


def test_unsupported_class_rejected_before_loading_anything(tmp_path):
    with pytest.raises(ValueError, match="paper note"):
        YoloxOnnxDetector(tmp_path / "missing.onnx", 416, ["paper note"], 0.3, 0.45)


MODEL = Path(BACKEND_ROOT / "models" / "yolox_nano.onnx")


@pytest.mark.skipif(not MODEL.exists(), reason="model not downloaded (python scripts/download_model.py)")
def test_real_model_runs_on_blank_frame_and_reports_version():
    det = YoloxOnnxDetector(MODEL, 416, ["cell phone"], 0.3, 0.45)
    assert det.model_id == "yolox-onnx:yolox_nano" and det.model_version.startswith("sha256:")
    assert det.detect(np.full((480, 640, 3), 120, np.uint8)) == []  # nothing in a flat image


# ---- evaluation metrics
def test_evaluation_counts_tp_fp_fn_and_duplicates():
    gt = {"a": [(0, 0, 100, 100)], "b": [], "c": [(0, 0, 50, 50), (200, 200, 260, 260)]}
    preds = {"a": [((5, 5, 100, 100), 0.9), ((0, 0, 100, 100), 0.8)],  # 1 TP + 1 duplicate (FP)
             "b": [((0, 0, 30, 30), 0.7)],  # FP on an object-free image
             "c": [((0, 0, 50, 50), 0.6), ((0, 0, 10, 10), 0.2)]}  # 1 TP; weak one filtered by conf_thr; 1 FN
    r = evaluate(gt, preds, 0.5, 0.3)
    assert (r["tp"], r["fp"], r["fn"]) == (2, 2, 1) and r["precision"] == 0.5 and abs(r["recall"] - 2 / 3) < 1e-9
    assert evaluate({}, {})["precision"] is None  # undefined, not 0
    assert iou_px((0, 0, 10, 10), (5, 5, 15, 15)) == pytest.approx(25 / 175)
    assert latency_stats([10, 20, 30, 40])["median_ms"] == 25.0
