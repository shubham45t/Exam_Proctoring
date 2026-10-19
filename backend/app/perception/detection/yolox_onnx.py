"""YOLOX (Apache-2.0, Megvii) ONNX detector run through OpenCV-DNN: no PyTorch needed, CPU-friendly.

Pretrained on COCO and used UNMODIFIED. It detects COCO classes only ("cell phone" is one of them).
Small/distant/occluded phones are the hard case; accuracy on YOUR camera footage is unknown until
you run scripts/evaluate_detector.py on labelled authorised footage."""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import cv2
import numpy as np

from .base import Detection

COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]
_STRIDES = (8, 16, 32)


def letterbox(image: np.ndarray, size: int) -> tuple[np.ndarray, float]:
    """Resize keeping aspect ratio, pad bottom/right with 114 (YOLOX convention). Returns (canvas, ratio)."""
    h, w = image.shape[:2]
    r = min(size / h, size / w)
    rh, rw = max(1, int(h * r)), max(1, int(w * r))
    canvas = np.full((size, size, 3), 114, np.uint8)
    canvas[:rh, :rw] = cv2.resize(image, (rw, rh), interpolation=cv2.INTER_LINEAR)
    return canvas, r


def decode_yolox(raw: np.ndarray, size: int, ratio: float, img_w: int, img_h: int, class_ids: dict[int, str],
                 conf: float, nms: float) -> list[Detection]:
    """raw: (N, 85) = [cx, cy, w, h (grid-relative), objectness, 80 class scores] straight from the ONNX head."""
    out = raw.astype(np.float32).copy()
    grids, strides = [], []
    for s in _STRIDES:
        n = size // s
        xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((n * n, 1), s))
    grid, stride = np.concatenate(grids), np.concatenate(strides)
    if out.shape[0] != grid.shape[0]:
        raise ValueError(f"model output has {out.shape[0]} anchors but input size {size} implies {grid.shape[0]}; "
                         "set OMNI_DETECTOR_INPUT_SIZE to the size the model was exported for")
    out[:, :2] = (out[:, :2] + grid) * stride
    out[:, 2:4] = np.exp(out[:, 2:4]) * stride
    cx, cy, bw, bh = out[:, 0], out[:, 1], out[:, 2], out[:, 3]
    x1, y1, x2, y2 = (cx - bw / 2) / ratio, (cy - bh / 2) / ratio, (cx + bw / 2) / ratio, (cy + bh / 2) / ratio
    result: list[Detection] = []
    for cid, name in class_ids.items():
        scores = out[:, 4] * out[:, 5 + cid]
        idx = np.where(scores >= conf)[0]
        if idx.size == 0:
            continue
        boxes = [[float(x1[i]), float(y1[i]), float(x2[i] - x1[i]), float(y2[i] - y1[i])] for i in idx]
        keep = cv2.dnn.NMSBoxes(boxes, [float(scores[i]) for i in idx], conf, nms)
        for k in np.array(keep).reshape(-1):
            i = idx[k]
            bx1, by1 = max(0.0, float(x1[i])), max(0.0, float(y1[i]))
            bx2, by2 = min(float(img_w), float(x2[i])), min(float(img_h), float(y2[i]))
            if bx2 - bx1 < 2 or by2 - by1 < 2:  # degenerate after clipping
                continue
            result.append(Detection(name, float(scores[i]), bx1 / img_w, by1 / img_h, bx2 / img_w, by2 / img_h))
    return sorted(result, key=lambda d: -d.confidence)


class YoloxOnnxDetector:
    def __init__(self, model_path: Path, input_size: int, classes: list[str], conf: float, nms: float):
        unknown = [c for c in classes if c not in COCO_CLASSES]
        if unknown:
            raise ValueError(f"Unsupported class(es) {unknown}: this COCO-pretrained model cannot detect them. "
                             f"Supported names include 'cell phone', 'laptop', 'book', ...")
        self._ids = {COCO_CLASSES.index(c): c for c in classes}
        self._size, self._conf, self._nms = input_size, conf, nms
        digest = hashlib.sha256(Path(model_path).read_bytes()).hexdigest()
        self.model_id = f"yolox-onnx:{Path(model_path).stem}"
        self.model_version = f"sha256:{digest[:12]}"
        self._net = cv2.dnn.readNetFromONNX(str(model_path))
        self._lock = threading.Lock()  # cv2.dnn.Net is not thread-safe; one shared instance serves all cameras

    def detect(self, image: np.ndarray) -> list[Detection]:
        h, w = image.shape[:2]
        canvas, ratio = letterbox(image, self._size)
        blob = cv2.dnn.blobFromImage(canvas.astype(np.float32), 1.0, (self._size, self._size), swapRB=False)  # BGR, 0-255
        with self._lock:
            self._net.setInput(blob)
            raw = self._net.forward()
        return decode_yolox(raw[0], self._size, ratio, w, h, self._ids, self._conf, self._nms)
