"""Measure object-detector precision/recall and latency on YOUR labelled, authorised images.

Folder layout:  <dir>/*.jpg|png   and   <dir>/labels.json  =
  {"img1.jpg": [[x1,y1,x2,y2], ...], "img2.jpg": []}      (pixel boxes of the target class; [] = no object present)
Include plenty of images WITHOUT the object, otherwise false positives cannot be measured.
Usage (from backend/):  python ../scripts/evaluate_detector.py <dir> [--class "cell phone"] [--iou 0.5]
Reports a confidence sweep + latency (first call excluded as warm-up). See app/perception/detection/evaluation.py for definitions."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import cv2  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.perception.detection.evaluation import evaluate, latency_stats  # noqa: E402
from app.perception.detection.yolox_onnx import YoloxOnnxDetector  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("folder")
ap.add_argument("--class", dest="cls", default="cell phone")
ap.add_argument("--iou", type=float, default=0.5)
a = ap.parse_args()
s = get_settings()
labels = json.loads((Path(a.folder) / "labels.json").read_text())
det = YoloxOnnxDetector(s.detector_model_path, s.detector_input_size, [a.cls], 0.05, s.detect_nms)  # low floor: sweep thresholds below
gt, preds, lat = {}, {}, []
first = True
for name, boxes in labels.items():
    img = cv2.imread(str(Path(a.folder) / name))
    if img is None:
        print("cannot read", name); continue
    h, w = img.shape[:2]
    t = time.perf_counter(); ds = det.detect(img); ms = (time.perf_counter() - t) * 1000
    if not first:
        lat.append(ms)
    first = False
    gt[name] = [tuple(map(float, b)) for b in boxes]
    preds[name] = [((d.x1 * w, d.y1 * h, d.x2 * w, d.y2 * h), d.confidence) for d in ds]
print(f"model {det.model_id} {det.model_version}; class '{a.cls}'; {len(gt)} images; IoU>={a.iou}")
print(f"{'conf>=':>7} {'TP':>5} {'FP':>5} {'FN':>5} {'precision':>10} {'recall':>8} {'F1':>6}")
fmt = lambda v: "  n/a" if v is None else f"{v:.2f}"  # noqa: E731
for c in (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
    r = evaluate(gt, preds, a.iou, c)
    print(f"{c:>7} {r['tp']:>5} {r['fp']:>5} {r['fn']:>5} {fmt(r['precision']):>10} {fmt(r['recall']):>8} {fmt(r['f1']):>6}")
print("latency (CPU, per image):", latency_stats(lat))
print("NOTE: valid only for this image set. Small sets are not evidence of real-world accuracy.")
