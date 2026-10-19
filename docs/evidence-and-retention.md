# Evidence, privacy and retention

* **What is stored:** one annotated JPEG (red box + label) per *confirmed* detection, scaled to <=1280 px wide. No continuous recording. Clips are not implemented.
* **Where:** `OMNI_EVIDENCE_DIR/<camera id>/EV-XXXXXXXXXXXX.jpg`, written atomically (temp file then rename). Metadata (id, camera, time, SHA-256, size) is in the `evidence` table. File names are server-generated; user input never forms a path.
* **Access:** only `GET /api/evidence/{id}` (image) and `/meta` (no paths). Responses are `no-store` + `nosniff`. Re-validates names and refuses anything resolving outside the evidence directory. **No authentication yet: restricted to authorised reviewers in Phase 8; keep the API on localhost until then.**
* **Failures are recorded:** if saving fails, a `failed` record with the reason is stored (no file, no path); the API answers `410` with that reason. A missing file also gives `410`, never a crash.
* **Retention:** `python ../scripts/cleanup_evidence.py` deletes evidence older than `OMNI_EVIDENCE_RETENTION_DAYS` (default 30; **set the period your college approves**). Idempotent; run it daily. Event rows are kept (their evidence link then answers 410).
* **Before any real exam:** institutional authorisation, notice to students, access control and an approved retention policy are required. Use synthetic data or authorised mock exams for development.
