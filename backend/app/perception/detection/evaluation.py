"""Detector evaluation metrics (pure functions; used by scripts/evaluate_detector.py and tested).

Definitions (per class, per image, boxes in pixels):
  * Predictions with confidence >= conf_thr are considered, sorted by confidence (highest first).
  * A prediction is a TRUE POSITIVE if it overlaps an UNMATCHED ground-truth box with IoU >= iou_thr
    (each GT box can be matched once). Otherwise it is a FALSE POSITIVE (this includes duplicates).
  * Unmatched GT boxes are FALSE NEGATIVES (missed objects).
  * precision = TP/(TP+FP), recall = TP/(TP+FN), F1 = harmonic mean. Undefined values are None (not 0).
Images WITHOUT ground-truth objects are essential: they are the only way to measure false positives.
Results on a small or unrepresentative set say nothing about general accuracy."""
from __future__ import annotations

import numpy as np

Box = tuple[float, float, float, float]


def iou_px(a: Box, b: Box) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def evaluate(gt: dict[str, list[Box]], preds: dict[str, list[tuple[Box, float]]], iou_thr: float = 0.5, conf_thr: float = 0.3) -> dict:
    tp = fp = fn = 0
    for img in set(gt) | set(preds):
        truth = list(gt.get(img, []))
        used = [False] * len(truth)
        for box, conf in sorted(preds.get(img, []), key=lambda p: -p[1]):
            if conf < conf_thr:
                continue
            best, best_iou = -1, iou_thr
            for i, g in enumerate(truth):
                v = iou_px(box, g)
                if not used[i] and v >= best_iou:
                    best, best_iou = i, v
            if best >= 0:
                used[best] = True
                tp += 1
            else:
                fp += 1
        fn += used.count(False)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if precision is not None and recall is not None else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1,
            "images": len(set(gt) | set(preds)), "images_without_objects": sum(1 for v in gt.values() if not v)}


def latency_stats(ms: list[float]) -> dict:
    if not ms:
        return {"n": 0}
    return {"n": len(ms), "median_ms": round(float(np.median(ms)), 1), "p95_ms": round(float(np.percentile(ms, 95)), 1),
            "max_ms": round(float(max(ms)), 1)}
