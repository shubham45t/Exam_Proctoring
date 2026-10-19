from __future__ import annotations

import cv2
import numpy as np

Polygon = list[tuple[float, float]]


class PolygonError(ValueError):
    pass


def validate_polygon(points: list[list[float]] | list[tuple[float, float]]) -> Polygon:
    """Normalised image polygon: 3-50 points in [0,1], non-degenerate, not self-intersecting."""
    if not (3 <= len(points) <= 50):
        raise PolygonError("A seat region needs between 3 and 50 points.")
    poly: Polygon = []
    for p in points:
        if len(p) != 2 or not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in p):
            raise PolygonError("Polygon points must be [x, y] pairs with values between 0 and 1.")
        poly.append((float(p[0]), float(p[1])))
    if polygon_area(poly) < 1e-4:
        raise PolygonError("The region is too small or degenerate.")
    if _self_intersects(poly):
        raise PolygonError("The region outline crosses itself.")
    return poly


def polygon_area(poly: Polygon) -> float:
    a = 0.0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def _ccw(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _self_intersects(poly: Polygon) -> bool:
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            c, d = poly[j], poly[(j + 1) % n]
            if _ccw(a, b, c) * _ccw(a, b, d) < 0 and _ccw(c, d, a) * _ccw(c, d, b) < 0:
                return True
    return False


def rasterise(poly: Polygon, width: int, height: int) -> np.ndarray:
    """Boolean mask of the polygon at the given pixel size."""
    pts = np.array([[round(x * (width - 1)), round(y * (height - 1))] for x, y in poly], dtype=np.int32)
    m = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(m, [pts], 1)
    return m.astype(bool)
