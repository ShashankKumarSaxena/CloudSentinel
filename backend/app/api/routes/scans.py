"""Scans HTTP routes; business logic stays in services."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.app.api.body import bounded_json
from backend.app.api.dependencies import actor, get_services
from backend.app.domain.rules import RULES
from backend.app.domain.schemas import CollectionRequest, Inventory, TriageUpdate
from backend.app.infrastructure.collectors import CollectionError
from backend.app.services.auth import audit
from backend.app.services.monitoring import BusyOperation

router = APIRouter()


@router.get("/api/v1/scans")
def scans(
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1000000),
):
    services = get_services(request)
    return services.store.list_scans(limit, offset)


@router.get("/api/v1/scans/latest")
def latest(request: Request):
    services = get_services(request)
    result = services.store.get_scan()
    if result is None:
        raise HTTPException(
            404, "No scans yet. Collect an approved account or import an inventory."
        )
    return result


@router.get("/api/v1/scans/{scan_id}")
def scan(request: Request, scan_id: str):
    services = get_services(request)
    result = services.store.get_scan(scan_id)
    if result is None:
        raise HTTPException(404, "Scan not found.")
    return result


@router.post("/api/v1/scans/demo", status_code=201)
def demo_scan(request: Request):
    services = get_services(request)
    return services.engine.demo(actor(request))


@router.post("/api/v1/scans/import", status_code=201)
async def import_scan(request: Request):
    services = get_services(request)
    inventory = await bounded_json(request, Inventory)
    if isinstance(inventory, JSONResponse):
        return inventory
    return await run_in_threadpool(services.engine.scan, inventory, "import", actor(request))


@router.post("/api/v1/scans/collect", status_code=201)
def collect_scan(request: Request, body: CollectionRequest):
    services = get_services(request)
    if services.settings.production:
        raise HTTPException(409, "Submit a background collection job at /api/v1/cloud/jobs.")
    try:
        return services.engine.collect(body, actor(request))
    except (BusyOperation, CollectionError):
        raise
    except Exception:
        raise HTTPException(
            502,
            "Collection failed. Check local credentials and read permissions. The previous scan was preserved.",
        ) from None


@router.patch("/api/v1/findings/{finding_id}")
def update_finding(finding_id: str, request: Request, body: TriageUpdate):
    services = get_services(request)
    result = services.store.triage(
        finding_id,
        body.status,
        body.scan_id,
        on_change=lambda conn, _: audit(conn, actor(request), "finding." + body.status, finding_id),
    )
    if result is None:
        raise HTTPException(
            404, "Finding not found in the current account snapshot. Refresh and try again."
        )
    return result


@router.get("/api/v1/findings/{finding_id}/events")
def triage_events(request: Request, finding_id: str):
    services = get_services(request)
    return services.store.events(finding_id)


@router.get("/api/v1/rules")
def rules(request: Request):
    services = get_services(request)
    return [asdict(rule) for rule in RULES]


@router.get("/api/v1/export")
def export(request: Request, scan_id: str | None = None):
    services = get_services(request)
    result = services.store.get_scan(scan_id)
    if result is None:
        raise HTTPException(404, "No scan to export.")
    with services.store.connection() as conn:
        audit(conn, actor(request), "report.exported", result["id"])
    payload = {
        "product": "CloudSentinel",
        "phase": result["phase"],
        "detection_method": (
            "deterministic configuration baseline + Isolation Forest activity analysis"
            if result.get("activity", {}).get("model")
            else "deterministic configuration baseline"
        ),
        "notice": "Source identifies synthetic, imported, or live data. A synthetic-trained model is experimental on live activity. Team triage does not verify remediation.",
        "triage_notice": "Statuses reflect current user dispositions; scan evidence is immutable.",
        "scan": result,
    }
    return JSONResponse(
        payload,
        headers={
            "Content-Disposition": f'attachment; filename="cloudsentinel-{result['id']}.json"'
        },
    )
