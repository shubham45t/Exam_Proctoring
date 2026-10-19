"""Central, validated configuration. All values come from OMNI_* environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OMNI_", env_file=".env", extra="ignore")

    env: str = "development"  # development | production
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'data' / 'omniproctor.db'}"
    media_dir: Path = BACKEND_ROOT / "data" / "media"  # prerecorded test videos live here
    evidence_dir: Path = BACKEND_ROOT.parent / "evidence"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    allow_synthetic_events: bool = True  # forced off when env == production

    # --- Camera acquisition / health (all configurable, none hardcoded in logic) ---
    frame_buffer_size: int = Field(2, ge=1, le=32)  # bounded: oldest frame is dropped
    analysis_fps: float = Field(4.0, gt=0, le=30)  # health/quality sampling rate
    open_timeout_s: float = Field(6.0, gt=0)
    read_timeout_s: float = Field(6.0, gt=0)
    reconnect_initial_s: float = Field(1.0, gt=0)
    reconnect_max_s: float = Field(30.0, gt=0)
    read_failure_limit: int = Field(5, ge=1)  # consecutive failed reads before reconnect
    stale_after_s: float = Field(5.0, gt=0)  # no new frame for this long => STALE
    frozen_after_s: float = Field(8.0, gt=0)  # identical frames for this long => FROZEN
    frozen_diff_threshold: float = Field(0.4, ge=0)  # mean abs diff (0-255) on a 32x32 thumbnail
    dark_luma_threshold: float = Field(25.0, ge=0, le=255)
    blur_laplacian_threshold: float = Field(20.0, ge=0)
    quality_confirm_count: int = Field(3, ge=1)  # consecutive analyses before a quality flag is raised
    preview_fps: float = Field(5.0, gt=0, le=15)
    preview_max_width: int = Field(640, ge=160, le=1920)

    # --- Occupancy (heuristic baseline-difference method; thresholds are UNCALIBRATED defaults) ---
    calibration_dir: Path = BACKEND_ROOT / "data" / "calibration"  # empty-room baselines (not evidence)
    occ_analysis_width: int = Field(320, ge=160, le=960)
    occ_pixel_diff: int = Field(25, ge=1, le=255)  # per-pixel change counted as "different from empty"
    occ_enter_fraction: float = Field(0.20, gt=0, le=1)  # changed fraction of seat region => occupied-like
    occ_exit_fraction: float = Field(0.08, ge=0, lt=1)  # at/below this => vacant-like (hysteresis gap between)
    occ_confirm_count: int = Field(6, ge=1)  # consecutive samples before a state change is confirmed
    occ_global_change_limit: float = Field(0.55, gt=0, le=1)  # whole-frame change => lighting/camera moved
    occ_min_region_px: int = Field(150, ge=10)  # reject seat regions smaller than this at analysis size
    occ_freshness_s: float = Field(6.0, gt=0)  # observations older than this are not "current"

    # --- Object detection (YOLOX via OpenCV-DNN; Apache-2.0 model; COCO classes) ---
    detector: str = "yolox_onnx"  # "none" disables object detection entirely
    detector_model_path: Path = BACKEND_ROOT / "models" / "yolox_nano.onnx"
    detector_input_size: int = Field(416, ge=160, le=1280)  # 416 for nano/tiny, 640 for s/m/l
    detector_classes: list[str] = ["cell phone"]  # must be COCO class names; others (e.g. paper notes) are NOT supported
    detect_conf: float = Field(0.30, gt=0, lt=1)  # detector output floor (low: tracker needs weak detections)
    detect_nms: float = Field(0.45, gt=0, lt=1)
    detect_fps: float = Field(2.0, gt=0, le=30)  # max inference rate per camera (frames are dropped, never queued)
    track_high_conf: float = Field(0.45, gt=0, lt=1)  # only detections >= this can START a track
    track_match_iou: float = Field(0.20, gt=0, lt=1)
    track_max_age_s: float = Field(2.0, gt=0)  # unmatched this long => track expires
    track_confirm_hits: int = Field(3, ge=1)  # detections needed before a track is reported
    track_confirm_min_s: float = Field(1.0, ge=0)  # ...and it must persist at least this long
    evidence_jpeg_quality: int = Field(85, ge=30, le=100)
    evidence_max_width: int = Field(1280, ge=320, le=3840)
    evidence_retention_days: int = Field(30, ge=1)

    @property
    def synthetic_enabled(self) -> bool:
        return self.allow_synthetic_events and self.env != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
