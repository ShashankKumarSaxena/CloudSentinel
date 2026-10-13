from contextlib import asynccontextmanager
from dataclasses import asdict
import os
from pathlib import Path
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .models import Inventory, TriageUpdate, CollectionRequest, TrainingDataset
from .ml import ModelService
from .collectors import collect, CollectionError
from .rules import RULES
from .store import Store

ROOT = Path(__file__).resolve().parents[2]
MAX_IMPORT_BYTES = 2 * 1024 * 1024


def create_app(db_path: Path | None = None, model_dir: Path | None = None) -> FastAPI:
    store = Store(db_path or Path(os.environ.get("CLOUDSENTINEL_DB", ROOT / ".runtime/cloudsentinel.db")))
    model = ModelService(model_dir or store.path.parent / "models")
    mutation_lock = threading.Lock()

    def perform_scan(inventory, source, collection=None):
        if not mutation_lock.acquire(blocking=False):
            raise HTTPException(409, "Another collection, scan, or training operation is running. Try again when it completes.")
        try:
            model.ensure_default()
            return store.scan(inventory, source, model=model, collection=collection)
        finally:
            mutation_lock.release()

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(model.ensure_default)
        if store.get_scan() is None:
            inventory = Inventory.model_validate_json((ROOT / "data/demo_activity_inventory.json").read_text())
            store.scan(inventory, "demo", model=model)
        yield

    app = FastAPI(title="CloudSentinel API", version="0.2.0", lifespan=lifespan,
                  description="Configuration baseline and Isolation Forest activity analysis. Opt-in read-only AWS, Azure, and GCP collection.")
    app.state.store = store
    app.state.model = model
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
        return {"status": "ok", "version": "0.2.0", "phase": 2, "mode": "local", "model_ready": model.status()["ready"]}

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
        return perform_scan(Inventory.model_validate_json((ROOT / "data/demo_activity_inventory.json").read_text()), "demo")

    @app.get("/api/v1/model")
    def model_status():
        return model.status()

    async def bounded_json(request, schema):
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise HTTPException(415, "This operation requires application/json.")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_IMPORT_BYTES:
                raise HTTPException(413, "JSON input exceeds the 2 MB limit.")
        try:
            return schema.model_validate_json(bytes(body))
        except ValidationError as exc:
            errors = [{"field": ".".join(str(v) for v in e["loc"]), "message": e["msg"]} for e in exc.errors()]
            return JSONResponse({"detail": "Input validation failed.", "errors": errors[:20]}, status_code=422)

    @app.post("/api/v1/model/train")
    async def train_model(request: Request):
        dataset = await bounded_json(request, TrainingDataset)
        if isinstance(dataset, JSONResponse):
            return dataset
        if not mutation_lock.acquire(blocking=False):
            raise HTTPException(409, "A scan or training operation is already running.")
        try:
            return await run_in_threadpool(model.train, dataset)
        finally:
            mutation_lock.release()

    @app.post("/api/v1/model/train/demo")
    def train_demo_model():
        if not mutation_lock.acquire(blocking=False):
            raise HTTPException(409, "A scan or training operation is already running.")
        try:
            return model.train(TrainingDataset.model_validate_json((ROOT / "data/ml/synthetic_dataset.json").read_text()))
        finally:
            mutation_lock.release()

    @app.get("/api/v1/connectors")
    def connectors():
        import shutil
        return [
            {"provider": "aws", "credential_source": "Local boto3 profile or role", "configured": bool(os.environ.get("AWS_PROFILE") or os.environ.get("AWS_ACCESS_KEY_ID") or (Path.home() / ".aws/config").exists()), "scope": "One AWS region plus global IAM users", "requires": "Local read-only AWS profile/role and a region. Configuration status does not verify credentials."},
            {"provider": "azure", "credential_source": "Local Azure CLI", "configured": bool(shutil.which("az") and os.environ.get("AZURE_SUBSCRIPTION_ID")), "scope": "One Azure subscription", "requires": "Azure CLI signed in; subscription ID via form or AZURE_SUBSCRIPTION_ID."},
            {"provider": "gcp", "credential_source": "Local gcloud CLI", "configured": bool(shutil.which("gcloud") and os.environ.get("GOOGLE_CLOUD_PROJECT")), "scope": "One GCP project", "requires": "gcloud signed in; project ID via form or GOOGLE_CLOUD_PROJECT."},
        ]

    @app.post("/api/v1/scans/collect", status_code=201)
    def collect_scan(body: CollectionRequest):
        if not mutation_lock.acquire(blocking=False):
            raise HTTPException(409, "Another collection, scan, or training operation is running.")
        try:
            inventory, metadata = collect(body)
            model.ensure_default()
            return store.scan(inventory, "live", model=model, collection=metadata)
        except CollectionError as exc:
            raise HTTPException(502, str(exc)) from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, "Collection failed. Check the local provider configuration and read permissions. The previous scan was preserved.") from None
        finally:
            mutation_lock.release()

    @app.post("/api/v1/scans/import", status_code=201)
    async def import_scan(request: Request):
        inventory = await bounded_json(request, Inventory)
        if isinstance(inventory, JSONResponse):
            return inventory
        return await run_in_threadpool(perform_scan, inventory, "import")

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
        payload = {"product": "CloudSentinel", "phase": result["phase"], "detection_method": "deterministic configuration baseline + Isolation Forest activity analysis" if result["phase"] == 2 else "deterministic configuration baseline",
                   "notice": "Source identifies synthetic, imported, or live data. A synthetic-trained model is experimental on live activity. Team triage does not verify remediation.",
                   "triage_notice": "Statuses reflect current user dispositions; scan evidence is immutable.", "scan": result}
        return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="cloudsentinel-{result["id"]}.json"'})

    dist = ROOT / "frontend/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app


app = create_app()
