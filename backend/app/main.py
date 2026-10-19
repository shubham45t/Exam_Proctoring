from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import alerts, auth, cameras, events, evidence, examination, reports, rooms, system
from app.auth.service import AuthService
from app.cameras.manager import CameraManager
from app.config import Settings, get_settings
from app.database.migrate import run_migrations
from app.database.session import make_engine, make_sessionmaker
from app.events.hub import Hub
from app.events.service import EventService
from app.evidence.service import EvidenceService
from app.monitoring.fusion import FusionEngine
from app.perception.detection.registry import DetectorRegistry
from app.perception.occupancy import OccupancyStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, detector=None) -> FastAPI:
    """`detector` lets tests inject a stub; production uses the configured model."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        settings.calibration_dir.mkdir(parents=True, exist_ok=True)
        run_migrations(settings.database_url)
        app.state.engine = engine = make_engine(settings.database_url)
        app.state.sessions = sessions = make_sessionmaker(engine)
        app.state.hub = hub = Hub()
        app.state.events = service = EventService(sessions, hub)
        service.bind_loop(asyncio.get_running_loop())
        app.state.fusion = fusion = FusionEngine(sessions, hub)
        service.set_fusion_engine(fusion)
        with sessions() as db:
            AuthService.ensure_default_users(db)
        app.state.occupancy = OccupancyStore()
        app.state.detectors = DetectorRegistry(settings, override=detector)
        app.state.evidence = EvidenceService(sessions, settings)
        app.state.cameras = CameraManager(settings, service.ingest)
        app.state.settings = settings
        app.state.started_at = time.time()
        yield
        await asyncio.to_thread(app.state.cameras.stop_all)  # graceful: release every camera
        engine.dispose()

    app = FastAPI(title="OmniProctor API", version=__version__, lifespan=lifespan,
                  description="Review-support system. Outputs are recommendations for human review, never findings of misconduct.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                       allow_headers=["Content-Type", "Authorization"])
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(cameras.router)
    app.include_router(rooms.router)
    app.include_router(examination.router)
    app.include_router(alerts.router)
    app.include_router(reports.router)
    app.include_router(evidence.router)
    app.include_router(events.router)
    app.include_router(events.ws_router)
    return app


app = create_app()
