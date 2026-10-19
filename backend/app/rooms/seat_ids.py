"""Seat-ID generation and validation. Convention: R{row}-C{col}, 1-based (e.g. R2-C4)."""
from __future__ import annotations

import re

SEAT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")


def seat_id(row: int, col: int) -> str:
    if row < 1 or col < 1:
        raise ValueError("row and col are 1-based")
    return f"R{row}-C{col}"


def generate_grid(rows: int, cols: int) -> list[dict]:
    """Seats laid out evenly; x/y are normalised room coordinates (centre of each grid cell)."""
    if not (1 <= rows <= 30 and 1 <= cols <= 30):
        raise ValueError("rows and cols must each be between 1 and 30")
    return [
        {"seat_id": seat_id(r, c), "row": r, "col": c, "x": round((c - 0.5) / cols, 4),
         "y": round((r - 0.5) / rows, 4), "monitored": True}
        for r in range(1, rows + 1) for c in range(1, cols + 1)
    ]
