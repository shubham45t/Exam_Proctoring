from __future__ import annotations

import platform
import time

import psutil
from fastapi import APIRouter, Request
from sqlalchemy import func, select, text

from app import __version__
from app.database.models import CameraRow, EventRow

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/system/status")
def system_status(request: Request) -> dict:
    st = request.app.state
    db_ok, events_total, cameras_total = True, 0, 0
    try:
        with st.sessions() as db:
            db.execute(text("SELECT 1"))
            events_total = db.scalar(select(func.count()).select_from(EventRow)) or 0
            cameras_total = db.scalar(select(func.count()).select_from(CameraRow)) or 0
    except Exception:
        db_ok = False
    states: dict[str, int] = {}
    for cid in st.cameras.running_ids():
        s = st.cameras.snapshot(cid)
        if s:
            states[s["state"]] = states.get(s["state"], 0) + 1
    vm = psutil.virtual_memory()
    return {
        "version": __version__,
        "environment": st.settings.env,
        "uptime_s": round(time.time() - st.started_at, 1),
        "python": platform.python_version(),
        "database": {"ok": db_ok, "dialect": st.engine.dialect.name},
        "cameras": {"registered": cameras_total, "running": len(st.cameras.running_ids()), "by_state": states},
        "events_total": events_total,
        "websocket_clients": st.hub.client_count,
        "detector": st.detectors.status(),
        "synthetic_events_enabled": st.settings.synthetic_enabled,
        "resources": {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": vm.percent,
            "process_rss_mb": round(psutil.Process().memory_info().rss / 1e6, 1),
        },
    }
