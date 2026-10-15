"""System HTTP routes; business logic stays in services."""

from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from string import Template

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from backend.app.api.dependencies import get_services
from backend.app.core.config import VERSION

router = APIRouter()


@router.get("/api/v1/health")
def health(request: Request):
    services = get_services(request)
    return {
        "status": "ok",
        "version": VERSION,
        "phase": 3,
        "mode": services.settings.mode,
        "model_ready": services.model.status()["ready"],
    }


@router.get("/docs", include_in_schema=False, response_class=HTMLResponse)
def api_reference(request: Request):
    services = get_services(request)
    if not services.settings.docs_enabled:
        raise HTTPException(404, "API reference is disabled.")
    rows = "".join(
        (
            f"<tr><td>{escape(method.upper())}</td><td><code>{escape(path)}</code></td><td>{escape(operation.get('summary', ''))}</td></tr>"
            for path, methods in request.app.openapi()["paths"].items()
            for method, operation in methods.items()
        )
    )
    template = Path(__file__).resolve().parents[1] / "templates/reference.html"
    return Template(template.read_text()).substitute(rows=rows)


@router.get("/api/v1/ready")
def ready(request: Request):
    services = get_services(request)
    try:
        with services.store.connection() as conn:
            conn.execute("SELECT 1")
        configured = not services.auth.setup_required()
        services.connections.read()
        heartbeat = services.jobs.worker_status()
        if services.settings.production:
            running = bool(
                heartbeat
                and heartbeat["status"] == "running"
                and (
                    datetime.fromisoformat(heartbeat["updated_at"])
                    > datetime.now(timezone.utc)
                    - timedelta(seconds=services.settings.worker_stale_seconds)
                )
            )
        else:
            running = not services.worker.enabled or services.worker.status()["running"]
        valid = (
            configured
            and running
            and (services.settings.production or services.model.status()["ready"])
        )
    except Exception:
        return JSONResponse(
            {"ready": False, "detail": "A required workspace dependency is unavailable."},
            status_code=503,
        )
    return JSONResponse(
        {
            "ready": valid,
            "accounts_configured": configured,
            "model_ready": services.model.status()["ready"],
            "monitor_running": running,
        },
        status_code=200 if valid else 503,
    )


@router.get("/api/v1/workspace")
def workspace(request: Request):
    services = get_services(request)
    return {
        "mode": services.settings.mode,
        "version": VERSION,
        "demo_enabled": not services.settings.production,
        "live_ml_enabled": services.settings.live_ml_enabled,
        "cloud_accounts": services.connections.list(),
    }
