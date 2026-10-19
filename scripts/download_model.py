"""Download a YOLOX ONNX model (Apache-2.0, Megvii) into backend/models/ and verify its SHA-256.
Usage: python scripts/download_model.py [--variant nano|tiny|s]
nano: fastest/least accurate (416 px).  tiny: better (416 px).  s: best of these, slower (640 px; set OMNI_DETECTOR_INPUT_SIZE=640).
After downloading a non-default variant, set OMNI_DETECTOR_MODEL_PATH (and OMNI_DETECTOR_INPUT_SIZE) in backend/.env."""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/"
MODELS = {  # SHA-256 recorded from the files downloaded and verified in the development sandbox
    "nano": ("yolox_nano.onnx", "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d", 416),
    "tiny": ("yolox_tiny.onnx", "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7", 416),
    "s": ("yolox_s.onnx", "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063", 640),
}

ap = argparse.ArgumentParser()
ap.add_argument("--variant", choices=MODELS, default="nano")
a = ap.parse_args()
name, sha, size = MODELS[a.variant]
dest = Path(__file__).resolve().parents[1] / "backend" / "models" / name
dest.parent.mkdir(parents=True, exist_ok=True)
if not dest.exists():
    print("Downloading", BASE + name)
    urllib.request.urlretrieve(BASE + name, dest)
got = hashlib.sha256(dest.read_bytes()).hexdigest()
if got != sha:
    dest.unlink()
    sys.exit(f"SHA-256 mismatch for {name} (got {got}). File deleted; do not use an unverified model.")
print(f"OK {dest} ({dest.stat().st_size} bytes, sha256 verified)")
if a.variant != "nano":
    print(f"Add to backend/.env:\nOMNI_DETECTOR_MODEL_PATH={dest}\nOMNI_DETECTOR_INPUT_SIZE={size}")
print("License: Apache-2.0 (https://github.com/Megvii-BaseDetection/YOLOX). Trained on COCO; used unmodified.")
