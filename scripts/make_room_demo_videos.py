"""Create two SYNTHETIC videos for trying occupancy without a real room (not real footage):
  empty_room.avi    - empty textured scene with sensor noise
  person_seat_a.avi - same scene with a bright blob standing in for a person in the LEFT seat area
Seat regions that match (normalised image coords):  A = [[.05,.2],[.45,.2],[.45,.8],[.05,.8]]   B = [[.55,.2],[.95,.2],[.95,.8],[.55,.8]]
Usage: python scripts/make_room_demo_videos.py   (writes into backend/data/media/)"""
from pathlib import Path

import cv2
import numpy as np

OUT = Path("backend/data/media")
OUT.mkdir(parents=True, exist_ok=True)
A = [[0.05, 0.2], [0.45, 0.2], [0.45, 0.8], [0.05, 0.8]]


def write(name, person):
    rng = np.random.default_rng(5)
    base = rng.integers(40, 220, (240, 320, 3), dtype=np.uint8)
    vw = cv2.VideoWriter(str(OUT / name), cv2.VideoWriter_fourcc(*"MJPG"), 15, (320, 240))
    for _ in range(90):
        f = np.clip(base.astype(np.int16) + rng.integers(-3, 4, base.shape), 0, 255).astype(np.uint8)
        if person:
            cv2.fillPoly(f, [np.array([[int(x * 320), int(y * 240)] for x, y in A], np.int32)], (250, 250, 250))
        cv2.putText(f, "SYNTHETIC DEMO", (8, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        vw.write(f)
    vw.release()
    print("wrote", OUT / name)


write("empty_room.avi", False)
write("person_seat_a.avi", True)
