from contextlib import asynccontextmanager
from dataclasses import asdict
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .models import Inventory, TriageUpdate
from .rules import RULES
from .store import Store

ROOT = Path(__file__).resolve().parents[2]
MAX_IMPORT_BYTES = 2 * 1024 * 1024


def create_app(db_path: Path | None = None) -> FastAPI:
    store = Store(db_path or Path(os.environ.get("CLOUDSENTINEL_DB", ROOT / ".runtime/cloudsentinel.db")))

    @asynccontextmanager
    async def lifespan(app):
        if store.get_scan() is None:
            inventory = Inventory.model_validate_json((ROOT / "data/demo_inventory.json").read_text())
            store.scan(inventory, "demo")
        yield

    app = FastAPI(title="CloudSentinel Phase 1 API", version="0.1.0", lifespan=lifespan,
                  description="Local configuration baseline prototype. Demo and imported snapshots only; no live cloud calls or ML.")
    app.state.store = store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def browser_protection(request: Request, call_next):
        # A local app still needs protection against websites sending write requests.
        origin = request.headers.get("origin")
        if request.method in {"POST", "PATCH", "DELETE", "PUT"} and origin:
            allowed = {f"http://{host}:{port}" for host in ("127.0.0.1", "localhost") for port in (5173, 8000)}
            allowed.add(f"{request.url.scheme}://{request.url.netloc}")
            if origin not in allowed:
                return JSONResponse({"detail": "Write requests must originate from this local workspace."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request, exc):
        return JSONResponse({"detail": "Invalid request. Check the supplied fields and values."}, status_code=422)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "version": "0.1.0", "phase": 1, "mode": "local"}

    @app.get("/api/v1/scans")
    def scans():
        return store.list_scans()

    @app.get("/api/v1/scans/latest")
    def latest():
        result = store.get_scan()
        if result is None:
            raise HTTPException(404, "No scans yet. Run a demo scan to begin.")
        return result

    @app.get("/api/v1/scans/{scan_id}")
    def scan(scan_id: str):
        result = store.get_scan(scan_id)
        if result is None:
            raise HTTPException(404, "Scan not found.")
        return result

    @app.post("/api/v1/scans/demo", status_code=201)
    def demo_scan():
        return store.scan(Inventory.model_validate_json((ROOT / "data/demo_inventory.json").read_text()), "demo")

    @app.post("/api/v1/scans/import", status_code=201)
    async def import_scan(request: Request):
        content_type = request.headers.get("content-type", "").split(";")[0].strip()
        if content_type != "application/json":
            raise HTTPException(415, "Import requires an application/json inventory.")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_IMPORT_BYTES:
                raise HTTPException(413, "Inventory exceeds the 2 MB limit.")
        try:
            inventory = Inventory.model_validate_json(bytes(body))
        except ValidationError as exc:
            errors = [{"field": ".".join(str(v) for v in e["loc"]), "message": e["msg"]} for e in exc.errors()]
            return JSONResponse({"detail": "Inventory validation failed.", "errors": errors[:20]}, status_code=422)
        return await run_in_threadpool(store.scan, inventory, "import")

    @app.patch("/api/v1/findings/{finding_id}")
    def update_finding(finding_id: str, body: TriageUpdate):
        result = store.triage(finding_id, body.status)
        if result is None:
            raise HTTPException(404, "Finding not found in the latest scan.")
        return result

    @app.get("/api/v1/findings/{finding_id}/events")
    def triage_events(finding_id: str):
        return store.events(finding_id)

    @app.get("/api/v1/rules")
    def rules():
        return [asdict(rule) for rule in RULES]

    @app.get("/api/v1/export")
    def export():
        result = store.get_scan()
        if result is None:
            raise HTTPException(404, "No scan to export.")
        payload = {"product": "CloudSentinel", "phase": 1, "detection_method": "deterministic configuration baseline",
                   "notice": "Synthetic demo or user-imported snapshot. No live cloud collection, ML, or verification of remediation.",
                   "triage_notice": "Statuses reflect current user dispositions; scan evidence is immutable.", "scan": result}
        return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="cloudsentinel-{result["id"]}.json"'})

    dist = ROOT / "frontend/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app


app = create_app()
