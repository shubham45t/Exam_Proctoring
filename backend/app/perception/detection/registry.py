from __future__ import annotations

import logging
import threading

from app.config import Settings

from .base import ObjectDetector

log = logging.getLogger(__name__)


class DetectorRegistry:
    """One lazily-loaded detector shared by every camera (avoids duplicate model instances)."""

    def __init__(self, settings: Settings, override: ObjectDetector | None = None):
        self._s = settings
        self._det: ObjectDetector | None = override
        self._error: str | None = None
        self._tried = override is not None
        self._lock = threading.Lock()

    def get(self) -> ObjectDetector | None:
        with self._lock:
            if self._det is not None or self._tried:
                return self._det
            self._tried = True
            s = self._s
            if s.detector == "none":
                self._error = "disabled (OMNI_DETECTOR=none)"
            elif s.detector != "yolox_onnx":
                self._error = f"unknown detector '{s.detector}'"
            elif not s.detector_model_path.is_file():
                self._error = f"model file not found at {s.detector_model_path}; run: python ../scripts/download_model.py"
            else:
                try:
                    from .yolox_onnx import YoloxOnnxDetector
                    self._det = YoloxOnnxDetector(s.detector_model_path, s.detector_input_size, s.detector_classes, s.detect_conf, s.detect_nms)
                except Exception as e:  # bad file / unsupported class: degrade, never crash the app
                    log.exception("detector load failed")
                    self._error = f"failed to load model: {e}"
            return self._det

    def status(self) -> dict:
        s = self._s
        if self._det is not None:
            return {"enabled": True, "loaded": True, "model_id": self._det.model_id, "model_version": self._det.model_version, "classes": s.detector_classes}
        if self._tried:
            return {"enabled": False, "loaded": False, "reason": self._error}
        if s.detector == "none":
            return {"enabled": False, "loaded": False, "reason": "disabled (OMNI_DETECTOR=none)"}
        if not s.detector_model_path.is_file():
            return {"enabled": False, "loaded": False, "reason": f"model file not found at {s.detector_model_path}; run: python ../scripts/download_model.py"}
        return {"enabled": True, "loaded": False, "reason": "model present; loads on first camera start", "classes": s.detector_classes}
