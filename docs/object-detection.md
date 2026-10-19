# Object detection, tracking and evidence (Phase 4)

## Model (pretrained, unmodified)
**YOLOX** (Megvii, **Apache-2.0**) exported to ONNX, run with OpenCV-DNN on CPU (no PyTorch). Trained on COCO and used **without any fine-tuning**. Chosen over Ultralytics YOLO because that code/weights are AGPL-3.0 (copyleft; needs legal review or a paid licence for a college deployment). Get it: `python scripts/download_model.py [--variant nano|tiny|s]` (SHA-256 verified; weights are never committed). Per-file hashes are in the script. Confirm licensing with your institution before deployment.

| variant | input | CPU time per frame* | notes |
|---|---|---|---|
| nano (default) | 416 | ~90-130 ms | fastest, weakest on small objects |
| tiny | 416 | ~190-230 ms | better recall |
| s | 640 | slower | set `OMNI_DETECTOR_MODEL_PATH` and `OMNI_DETECTOR_INPUT_SIZE=640` |
\*measured on a 1-core sandbox with other work running; your hardware will differ.

## What is and is not supported
* **Supported:** COCO class names, notably `cell phone` (default). Change with `OMNI_DETECTOR_CLASSES='["cell phone"]'`.
* **Not supported:** paper notes/cheat sheets, concealed phones, earpieces. COCO has no such class; a startup check rejects unknown names. Would need custom training data.
* **Hard cases:** small, distant, angled, motion-blurred or partly hidden phones. **Phone accuracy on real classroom footage has NOT been measured.** Verified so far: the decoder/tracker/evidence pipeline on real pixels using `person`/`bus` (a photo played as video), and plumbing with a test stub.

## Pipeline
camera frames -> (own thread, 1-slot mailbox: slow inference drops frames, never queues) -> YOLOX -> tracker -> events
* **Tracker `iou-bytetrack-lite`:** ByteTrack-style two-stage IoU association (high-confidence detections start/continue tracks; weak ones can only keep a track alive). No Kalman filter, so fast motion at low fps can lose an ID. A track is reported only after `TRACK_CONFIRM_HITS` (3) detections over `TRACK_CONFIRM_MIN_S` (1 s). Occlusion up to `TRACK_MAX_AGE_S` (2 s) keeps the same ID.
* **Deduplication:** a continuously visible phone = **one** `object_detection` observation (at confirmation, with evidence). Later events are `tracking` states: `lost`, `tracked` (re-acquired), `expired`. Flickers that never confirm are never stored. When a camera stops/freezes/degrades, all tracks end (`expired`): nothing is claimed to be "still there".
* A phone that disappears for longer than the max age and returns gets a **new** track/observation; merging those into one incident is the job of the Phase 6 fusion engine.
* **Seat association:** the seat whose calibrated region contains the box centre (only `monitored`/`partial` regions). `null` = unknown, not "no seat". A phone on a desk may lie outside a person-shaped region.
* Persisted observations carry model id + file-hash version, tracker id, confidence (the detector's score, **not a probability of rule-breaking**), seat and evidence id.

## Settings (`backend/.env`, all `OMNI_*`)
`DETECTOR` (yolox_onnx|none), `DETECTOR_MODEL_PATH`, `DETECTOR_INPUT_SIZE`, `DETECTOR_CLASSES`, `DETECT_CONF` (0.30 output floor), `DETECT_NMS`, `DETECT_FPS` (2; max inference rate per camera), `TRACK_HIGH_CONF` (0.45), `TRACK_MATCH_IOU`, `TRACK_MAX_AGE_S`, `TRACK_CONFIRM_HITS`, `TRACK_CONFIRM_MIN_S`. Defaults are uncalibrated. Per-camera on/off: Edit camera -> "Detect prohibited objects".
Tuning: missed phones -> lower `TRACK_HIGH_CONF`/`DETECT_CONF`, try `tiny`/`s` or higher input size; false alarms -> raise them or raise `TRACK_CONFIRM_*`. Change one at a time and re-measure.

## Evaluating on your footage
1. With authorisation, collect frames from your camera at the real distance/lighting: some with a phone visible (different positions, partly hidden, in hand/on desk) and **many without**.
2. Label pixel boxes in `labels.json` (`{"a.jpg": [[x1,y1,x2,y2]], "b.jpg": []}`).
3. From `backend/`: `python ../scripts/evaluate_detector.py <folder> --class "cell phone"`.
**Definitions:** TP = prediction with IoU>=0.5 to an unmatched labelled box; FP = any other prediction (incl. duplicates and detections on phone-free images); FN = unmatched labelled box. precision = TP/(TP+FP), recall = TP/(TP+FN); undefined values print as n/a (never 0). Latency = per-image detector time on this CPU, warm-up excluded. Small sets do **not** prove general accuracy. Measuring false alerts per camera-hour and end-to-end alert latency belongs to the fusion phase.
