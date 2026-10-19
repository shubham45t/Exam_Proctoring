from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Detection:
    """Normalised [0,1] box, origin top-left."""

    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)


class ObjectDetector(Protocol):
    model_id: str
    model_version: str

    def detect(self, image: np.ndarray) -> list[Detection]: ...
