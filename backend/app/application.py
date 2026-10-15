"""Compose adapters, services, HTTP routes, and application lifecycle in one place."""

from contextlib import asynccontextmanager
from pathlib import Path
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api.body import MAX_IMPORT_BYTES
from backend.app.api.dependencies import Services
from backend.app.api.observability import install_observability
from backend.app.api.oidc import install_oidc
from backend.app.api.openapi import install_openapi
from backend.app.api.routes import (
    authentication,
    cloud,
    models,
    operations as operations_routes,
    scans,
    system,
)
from backend.app.api.security import install_security
from backend.app.core.config import Settings, VERSION
from backend.app.core.paths import PROJECT_ROOT as ROOT
from backend.app.infrastructure.connections import Connections
from backend.app.infrastructure.notifications import EmailDelivery
from backend.app.repositories.store import Store
from backend.app.services.auth import AuthService
from backend.app.services.engine import ScanEngine
from backend.app.services.jobs import CollectionJobs
from backend.app.services.model import ModelService
from backend.app.services.monitoring import MonitorWorker
from backend.app.services.operations import Operations

__all__ = ["create_app", "MAX_IMPORT_BYTES"]


def create_app(
    db_path: Path | None = None,
    model_dir: Path | None = None,
    monitoring_enabled: bool | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env(
        database_path=db_path, model_dir=model_dir, embedded_worker=monitoring_enabled
    )
    store = Store(
        settings.database_path,
        settings.database_url.get_secret_value() if settings.database_url else None,
    )
    model = ModelService(
        settings.model_dir or store.path.parent / "models",
        load_existing=not settings.production or settings.live_ml_enabled,
    )
    auth = AuthService(store, settings.session_ttl_seconds, settings.idle_timeout_seconds)
    delivery = EmailDelivery()
    operations = Operations(
        store, delivery.enabled, os.environ.get("CLOUDSENTINEL_ALERT_MIN_SEVERITY", "high")
    )
    connections = Connections(settings.accounts_file, required=settings.production)
    jobs = CollectionJobs(store, connections, settings, operations)
    engine = ScanEngine(store, model, operations, settings, connections)
    worker = MonitorWorker(
        operations, engine, delivery, enabled=settings.embedded_worker, jobs=jobs
    )
    allowed_hosts = list(settings.allowed_hosts)

    @asynccontextmanager
    async def lifespan(app):
        if settings.mode == "demo":
            await run_in_threadpool(model.ensure_default)
        elif settings.live_ml_enabled and (
            not model.status().get("ready") or model.status().get("provenance") != "user_labeled"
        ):
            raise RuntimeError("Production ML needs an explicitly reviewed non-synthetic model.")
        if settings.mode == "demo" and store.get_scan() is None:
            await run_in_threadpool(engine.demo, "system", "initial-synthetic-snapshot")
        worker.start()
        try:
            yield
        finally:
            await run_in_threadpool(worker.stop)
            await run_in_threadpool(store.database.close)

    app = FastAPI(
        title="CloudSentinel API",
        version=VERSION,
        lifespan=lifespan,
        description="Authenticated cloud security, activity analysis, scheduled monitoring, and alerts.",
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.store, app.state.model, app.state.auth = store, model, auth
    app.state.operations, app.state.engine, app.state.worker = operations, engine, worker
    app.state.settings, app.state.connections, app.state.jobs = settings, connections, jobs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    app.state.services = Services(
        settings, store, model, auth, operations, engine, worker, connections, jobs
    )
    install_security(app, settings, auth)

    install_oidc(app, settings, auth)
    install_observability(app, enabled=settings.production)
    for routes in (authentication, cloud, models, operations_routes, scans, system):
        app.include_router(routes.router)

    install_openapi(app)

    dist = ROOT / "frontend/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app
