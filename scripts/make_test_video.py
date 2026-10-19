"""Generate a SYNTHETIC test video (moving shapes on noise). Not real footage; for pipeline tests only.
Usage: python scripts/make_test_video.py [output.avi]"""
import sys
from pathlib import Path

import cv2
import numpy as np

out = Path(sys.argv[1] if len(sys.argv) > 1 else "backend/data/media/synthetic_demo.avi")
out.parent.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(7)
base = rng.integers(60, 200, (480, 640, 3), dtype=np.uint8)
base = cv2.GaussianBlur(base, (0, 0), 3)
vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"MJPG"), 15, (640, 480))
for i in range(150):
    f = base.copy()
    cv2.rectangle(f, (20 + i * 3 % 500, 200), (100 + i * 3 % 500, 280), (240, 240, 240), -1)
    cv2.putText(f, "SYNTHETIC TEST VIDEO", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    cv2.putText(f, f"frame {i}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    vw.write(f)
vw.release()
print("wrote", out, out.stat().st_size, "bytes")
